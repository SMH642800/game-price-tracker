#!/usr/bin/env python3
"""One-off, low-rate feasibility probe for Nintendo Taiwan catalogue/prices.

This is a manual diagnostic, not a production scraper. It requests the public
Nintendo Taiwan software catalogue page-by-page with a delay, then asks the
Nintendo price endpoint only for title IDs matching the configured test names.
It does not save a dataset, run in CI, or enable price lookup in the Discord bot.
"""
from __future__ import annotations

import json
import time
import unicodedata
from urllib.parse import urlencode

import requests

CATALOG_URL = "https://www.nintendo.com/tw/api/software"
PRICE_URL = "https://api.ec.nintendo.com/v1/price"
PAGE_SIZE = 24
REQUEST_DELAY_SECONDS = 0.2
TIMEOUT_SECONDS = 15
MAX_PAGES = 250
TEST_QUERIES = (
    "時之笛",
    "亰都幻都",
    "京都幻都",
    "Kyoto Xanadu",
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
            "User-Agent": "game-price-tracker-source-probe/0.1",
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object from {url}")
    return payload


def load_catalogue(session: requests.Session) -> tuple[list[dict], dict]:
    first = get_json(session, CATALOG_URL, {"sftab": "all", "spage": 1})
    items = first.get("items")
    total = first.get("total")
    if not isinstance(items, list) or not isinstance(total, int) or total < 0:
        raise ValueError("Nintendo catalogue response has an unexpected schema")

    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page_count > MAX_PAGES:
        raise ValueError(f"Catalogue reports {page_count} pages; safety cap is {MAX_PAGES}")

    rows = [row for row in items if isinstance(row, dict)]
    for page in range(2, page_count + 1):
        time.sleep(REQUEST_DELAY_SECONDS)
        payload = get_json(session, CATALOG_URL, {"sftab": "all", "spage": page})
        page_items = payload.get("items")
        if not isinstance(page_items, list):
            raise ValueError(f"Catalogue page {page} has an unexpected schema")
        rows.extend(row for row in page_items if isinstance(row, dict))

    return rows, {
        "reported_total": total,
        "pages_requested": page_count,
        "rows_received": len(rows),
    }


def title_of(row: dict) -> str:
    for key in ("title", "name", "title_name"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def matching_rows(rows: list[dict], query: str) -> list[dict]:
    needle = normalize(query)
    if not needle:
        return []
    found = []
    for row in rows:
        title = title_of(row)
        if needle in normalize(title):
            found.append(row)
    return found


def get_prices(session: requests.Session, rows: list[dict]) -> dict:
    ids = []
    for row in rows:
        nsuid = str(row.get("nsuid", "")).strip()
        if nsuid.isdigit() and nsuid not in ids:
            ids.append(nsuid)
    if not ids:
        return {"requested_ids": [], "prices": []}

    params = {"country": "TW", "lang": "zh", "ids": ",".join(ids[:30])}
    payload = get_json(session, PRICE_URL, params)
    prices = payload.get("prices")
    if not isinstance(prices, list):
        raise ValueError("Nintendo price response has an unexpected schema")
    return {"requested_ids": ids[:30], "prices": prices}


def main() -> int:
    with requests.Session() as session:
        rows, catalogue_summary = load_catalogue(session)
        output = {
            "notice": (
                "Undocumented endpoints: this probe tests current behaviour only; "
                "it does not establish Nintendo permission for automated reuse."
            ),
            "catalogue": catalogue_summary,
            "queries": {},
        }

        for query in TEST_QUERIES:
            matches = matching_rows(rows, query)
            price_result = get_prices(session, matches)
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
            }
            if query != TEST_QUERIES[-1]:
                time.sleep(REQUEST_DELAY_SECONDS)

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
