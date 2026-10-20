#!/usr/bin/env python3
"""Manual, low-rate feasibility probe for Nintendo Taiwan catalogue/prices.

The catalogue is cached locally for 24 hours to avoid repeatedly fetching every
page during development. This diagnostic is not a production scraper: it does
not run in CI, does not enable price lookup in the Discord bot, and does not
establish Nintendo permission for automated reuse.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import unicodedata
import warnings
from pathlib import Path
from typing import Any

import requests

CATALOG_URLS = {
    "TW": "https://www.nintendo.com/tw/api/software",
    "HK": "https://www.nintendo.com/hk/api/software",
}
CATALOG_URL = CATALOG_URLS["TW"]
PRICE_URL = "https://api.ec.nintendo.com/v1/price"
PAGE_SIZE = 24
REQUEST_DELAY_SECONDS = 0.2
TIMEOUT_SECONDS = 15
WARNING_PAGES = 800
MAX_PAGES = 1000
CACHE_TTL_SECONDS = 24 * 60 * 60
CACHE_SCHEMA_VERSION = 1
DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[1] / ".cache" / "nintendo_tw_catalogue.json"
TEST_QUERIES = (
    "時之笛",
    "亰都幻都",
    "京都幻都",
    "Kyoto Xanadu",
    "空之軌跡",
)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in value if char.isalnum())


def get_json(session: requests.Session, url: str, params: dict) -> dict:
    response = session.get(
        url,
        params=params,
        headers={
            "Accept": "application/json",
            "User-Agent": "game-price-tracker-source-probe/0.2",
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object from {url}")
    return payload


def _read_cache(cache_path: Path, now: float) -> tuple[list[dict], dict] | None:
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(cached, dict) or cached.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        fetched_at = cached.get("fetched_at")
        rows = cached.get("rows")
        summary = cached.get("summary")
        if (
            not isinstance(fetched_at, (int, float))
            or now - fetched_at < 0
            or now - fetched_at > CACHE_TTL_SECONDS
            or not isinstance(rows, list)
            or not all(isinstance(row, dict) for row in rows)
            or not isinstance(summary, dict)
        ):
            return None
        return rows, {
            **summary,
            "cache_hit": True,
            "cache_age_seconds": round(now - fetched_at, 3),
        }
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _write_cache(cache_path: Path, rows: list[dict], summary: dict, now: float) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "fetched_at": now,
        "summary": {
            key: value for key, value in summary.items()
            if key not in {"cache_hit", "cache_age_seconds", "request_seconds", "sleep_seconds"}
        },
        "rows": rows,
    }
    # Atomic replacement prevents an interrupted run from leaving a partial cache.
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{cache_path.name}.", suffix=".tmp", dir=str(cache_path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(temporary_name, cache_path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def load_catalogue(
    session: requests.Session,
    *,
    cache_path: Path | None = DEFAULT_CACHE_PATH,
    refresh_cache: bool = False,
    catalogue_url: str = CATALOG_URL,
) -> tuple[list[dict], dict]:
    """Load the catalogue, preferring a fresh local cache unless explicitly refreshed."""
    now = time.time()
    if cache_path is not None and not refresh_cache:
        cached = _read_cache(cache_path, now)
        if cached is not None:
            return cached

    request_seconds = 0.0
    sleep_seconds = 0.0
    started = time.perf_counter()
    first = get_json(session, catalogue_url, {"sftab": "all", "spage": 1})
    request_seconds += time.perf_counter() - started

    items = first.get("items")
    total = first.get("total")
    if not isinstance(items, list) or not isinstance(total, int) or total < 0:
        raise ValueError("Nintendo catalogue response has an unexpected schema")

    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page_count > MAX_PAGES:
        raise ValueError(f"Catalogue reports {page_count} pages; safety cap is {MAX_PAGES}")
    if page_count > WARNING_PAGES:
        warnings.warn(
            f"Catalogue reports {page_count} pages, above the warning threshold "
            f"of {WARNING_PAGES}; continuing because it is within the hard cap "
            f"of {MAX_PAGES}.",
            RuntimeWarning,
            stacklevel=2,
        )

    rows = [row for row in items if isinstance(row, dict)]
    for page in range(2, page_count + 1):
        started = time.perf_counter()
        time.sleep(REQUEST_DELAY_SECONDS)
        sleep_seconds += time.perf_counter() - started

        started = time.perf_counter()
        payload = get_json(session, catalogue_url, {"sftab": "all", "spage": page})
        request_seconds += time.perf_counter() - started
        page_items = payload.get("items")
        if not isinstance(page_items, list):
            raise ValueError(f"Catalogue page {page} has an unexpected schema")
        rows.extend(row for row in page_items if isinstance(row, dict))

    ids = [
        str(row.get("nsuid", "")).strip()
        for row in rows
        if str(row.get("nsuid", "")).strip().isdigit()
    ]
    summary = {
        "reported_total": total,
        "pages_requested": page_count,
        "rows_received": len(rows),
        "unique_nsuid_count": len(set(ids)),
        "duplicate_nsuid_rows": len(ids) - len(set(ids)),
        "cache_hit": False,
        "cache_age_seconds": None,
        "request_seconds": round(request_seconds, 3),
        "sleep_seconds": round(sleep_seconds, 3),
    }
    if cache_path is not None:
        _write_cache(cache_path, rows, summary, time.time())
    return rows, summary


def title_of(row: dict) -> str:
    for key in ("title", "name", "title_name"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def matching_rows(rows: list[dict], query: str) -> list[dict]:
    """Match by normalized title and return one row per stable NSUID."""
    needle = normalize(query)
    if not needle:
        return []
    found: list[dict] = []
    seen_ids: set[str] = set()
    for row in rows:
        if needle not in normalize(title_of(row)):
            continue
        nsuid = str(row.get("nsuid", "")).strip()
        if nsuid.isdigit():
            if nsuid in seen_ids:
                continue
            seen_ids.add(nsuid)
        found.append(row)
    return found


def get_prices(session: requests.Session, rows: list[dict]) -> dict:
    ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        nsuid = str(row.get("nsuid", "")).strip()
        if nsuid.isdigit() and nsuid not in seen:
            seen.add(nsuid)
            ids.append(nsuid)
    if not ids:
        return {"requested_ids": [], "prices": []}

    params = {"country": "TW", "lang": "zh", "ids": ",".join(ids[:30])}
    payload = get_json(session, PRICE_URL, params)
    prices = payload.get("prices")
    if not isinstance(prices, list):
        raise ValueError("Nintendo price response has an unexpected schema")
    return {"requested_ids": ids[:30], "prices": prices}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    cache_group = parser.add_mutually_exclusive_group()
    cache_group.add_argument(
        "--refresh-cache", action="store_true",
        help="ignore the cached catalogue and fetch all pages again (then refresh cache)",
    )
    cache_group.add_argument(
        "--no-cache", action="store_true",
        help="neither read nor write a local catalogue cache",
    )
    parser.add_argument(
        "--country", choices=("TW", "HK"), default="TW",
        help="catalogue region to probe; price lookups still query Taiwan (TW)",
    )
    parser.add_argument(
        "--cache-path", type=Path, default=None,
        help="local cache path (default: .cache/nintendo_{country.lower()}_catalogue.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    default_cache = DEFAULT_CACHE_PATH.parent / f"nintendo_{args.country.lower()}_catalogue.json"
    cache_path = None if args.no_cache else (args.cache_path or default_cache)
    catalogue_url = CATALOG_URLS[args.country]
    run_started = time.perf_counter()
    with requests.Session() as session:
        catalogue_started = time.perf_counter()
        rows, catalogue_summary = load_catalogue(
            session, cache_path=cache_path, refresh_cache=args.refresh_cache,
            catalogue_url=catalogue_url,
        )
        catalogue_elapsed = time.perf_counter() - catalogue_started
        output: dict[str, Any] = {
            "notice": (
                "Undocumented endpoints: this probe tests current behaviour only; "
                "it does not establish Nintendo permission for automated reuse."
            ),
            "catalogue_region": args.country,
            "catalogue_url": catalogue_url,
            "price_region": "TW",
            "catalogue": catalogue_summary,
            "queries": {},
        }

        for index, query in enumerate(TEST_QUERIES):
            matches = matching_rows(rows, query)
            price_started = time.perf_counter()
            price_result = get_prices(session, matches)
            price_elapsed = time.perf_counter() - price_started
            prices_by_id = {
                str(item.get("title_id", "")): item
                for item in price_result["prices"]
                if isinstance(item, dict)
            }
            output["queries"][query] = {
                "match_count": len(matches),
                "matches": [
                    {
                        "title": title_of(row),
                        "nsuid": str(row.get("nsuid", "")),
                        "platform": row.get("platform"),
                        "price_record": prices_by_id.get(str(row.get("nsuid", ""))),
                    }
                    for row in matches[:10]
                ],
                "requested_ids": price_result["requested_ids"],
                "price_records_returned": len(price_result["prices"]),
                "elapsed_seconds": round(price_elapsed, 3),
            }
            if index < len(TEST_QUERIES) - 1:
                time.sleep(REQUEST_DELAY_SECONDS)

    output["timing"] = {
        "catalogue_elapsed_seconds": round(catalogue_elapsed, 3),
        "total_elapsed_seconds": round(time.perf_counter() - run_started, 3),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (requests.RequestException, ValueError, TypeError) as error:
        print(json.dumps({
            "probe_failed": type(error).__name__,
            "message": str(error),
            "hint": "No price integration should be enabled from this result alone.",
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)
