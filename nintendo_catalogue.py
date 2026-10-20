"""Cached search helpers for Nintendo regional software catalogues.

The catalogue endpoints are undocumented. The loader prefers local caches and
falls back to the repository's weekly cache; this does not establish permission
for automated reuse or guarantee API stability.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

CATALOG_URL = "https://www.nintendo.com/tw/api/software"
PAGE_SIZE = 24
REQUEST_DELAY_SECONDS = 0.2
TIMEOUT_SECONDS = 15
MAX_PAGES = 250
CACHE_TTL_SECONDS = 8 * 24 * 60 * 60
CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "nintendo_tw_catalogue.json"
HK_CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "nintendo_hk_catalogue.json"
REMOTE_CACHE_URLS = {
    "TW": "https://raw.githubusercontent.com/SMH642800/game-price-tracker/main/.cache/nintendo_tw_catalogue.json",
    "HK": "https://raw.githubusercontent.com/SMH642800/game-price-tracker/main/.cache/nintendo_hk_catalogue.json",
}

# Curated fallback entries for verified digital editions omitted by the bulk Taiwan
# catalogue endpoint. These entries are kept separate from downloaded cache data;
# prices are still fetched live and validated by nintendo.py.
# HK eShop fallback listing: https://ec.nintendo.com/HK/zh/titles/70010000128495
# The Taiwan price endpoint was independently confirmed to return TWD 1,880 for this ID.
# Additional HK catalogue rows can be merged from the optional HK cache below.
MANUAL_CATALOGUE_ENTRIES: tuple[dict[str, Any], ...] = (
    {
        "title": "空之軌跡 the 2nd",
        "nsuid": "70010000128495",
        "platform": "Nintendo Switch",
        "catalogue_source": "curated",
    },
)


class NintendoCatalogueError(RuntimeError):
    """Nintendo catalogue cache or response cannot be used safely."""


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(char for char in value if char.isalnum())


def title_of(row: dict[str, Any]) -> str:
    for key in ("title", "name", "title_name"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def inferred_platform(row: dict[str, Any]) -> str:
    """Return a generation only when metadata or an explicit edition marker supports it."""
    value = row.get("platform")
    if isinstance(value, str) and value.strip():
        normalized = normalize(value)
        if "2" in normalized or "switch2" in normalized:
            return "ns2"
        if "switch" in normalized or "任天堂" in normalized:
            return "ns"
    title = normalize(title_of(row))
    if any(marker in title for marker in ("switch2edition", "nintendoswitch2", "ns2edition")):
        return "ns2"
    return "nintendo"


def platform_matches(row: dict[str, Any], platform: str) -> bool:
    """Treat NS, NS2 and the unified Nintendo selector as one searchable library.

    The platform argument remains accepted for existing callers and saved watchlists.
    Edition wording stays in the title, but platform metadata does not hide a result:
    an NS2 console can play compatible NS games, and price lookup is keyed by NSUID.
    """
    return platform in {"nintendo", "ns", "ns2"}


def _fresh_cache_rows(payload: Any, *, now: float) -> list[dict[str, Any]] | None:
    if not isinstance(payload, dict):
        return None
    fetched_at = payload.get("fetched_at")
    rows = payload.get("rows")
    if (
        payload.get("schema_version") != 1
        or not isinstance(fetched_at, (int, float))
        or now - fetched_at < 0
        or now - fetched_at > CACHE_TTL_SECONDS
        or not isinstance(rows, list)
        or not all(isinstance(row, dict) for row in rows)
    ):
        return None
    return rows


def _read_local_cache(path: Path, *, now: float) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return _fresh_cache_rows(payload, now=now)


def _atomic_write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _download_cache(region: str, path: Path, *, now: float) -> list[dict[str, Any]] | None:
    """Fetch the latest weekly cache from the repository and save it locally."""
    try:
        response = requests.get(
            REMOTE_CACHE_URLS[region],
            headers={"Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return None
    rows = _fresh_cache_rows(payload, now=now)
    if rows is None:
        return None
    try:
        _atomic_write_cache(path, payload)
    except OSError:
        # A valid remote response can still be used even if local persistence fails.
        pass
    return rows


def load_cached_catalogue(*, now: float | None = None) -> list[dict[str, Any]]:
    """Use a fresh local cache first, then fetch the latest weekly GitHub cache."""
    current = time.time() if now is None else now
    rows = _read_local_cache(CACHE_PATH, now=current)
    if rows is not None:
        return rows
    rows = _download_cache("TW", CACHE_PATH, now=current)
    if rows is not None:
        return rows
    raise NintendoCatalogueError(
        "Nintendo 台灣目錄快取已過期、缺失或格式不正確，且無法取得 GitHub 上的每週快取；"
        "請確認每週更新 Action 已成功，或執行 "
        "python scripts/probe_nintendo_sources.py --refresh-cache"
    )


def load_optional_hk_catalogue(*, now: float | None = None) -> list[dict[str, Any]]:
    """Load the optional HK catalogue locally or from the latest weekly GitHub cache."""
    current = time.time() if now is None else now
    rows = _read_local_cache(HK_CACHE_PATH, now=current)
    if rows is None:
        rows = _download_cache("HK", HK_CACHE_PATH, now=current)
    if rows is None:
        return []
    normalized = []
    for row in rows:
        item = dict(row)
        item.setdefault("catalogue_source", "HK")
        normalized.append(item)
    return normalized


def search_nintendo_games(
    query: str,
    platform: str,
    *,
    rows: list[dict[str, Any]] | None = None,
    hk_rows: list[dict[str, Any]] | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return real catalogue entries with stable NSUIDs, deduplicated by ID."""
    if platform not in {"ns", "ns2", "nintendo"}:
        raise ValueError("Nintendo catalogue search supports nintendo, ns and ns2")
    needle = normalize(query)
    if not needle:
        return []
    # TW remains the primary source. HK only supplements missing NSUIDs and is
    # deliberately optional, so an absent/expired HK cache cannot break TW search.
    tw_catalogue = [
        *MANUAL_CATALOGUE_ENTRIES,
        *(load_cached_catalogue() if rows is None else rows),
    ]
    supplemental_hk = (
        load_optional_hk_catalogue()
        if hk_rows is None and rows is None
        else (hk_rows or [])
    )
    catalogue = [*tw_catalogue, *supplemental_hk]
    matches: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for row in catalogue:
        title = title_of(row)
        nsuid = str(row.get("nsuid", "")).strip()
        if not title or not nsuid.isdigit() or nsuid in seen_ids:
            continue
        if not platform_matches(row, platform) or needle not in normalize(title):
            continue
        seen_ids.add(nsuid)
        matches.append({
            "product_id": nsuid,
            "name": title,
            "platform": "nintendo",
            "platform_verified": isinstance(row.get("platform"), str) and bool(row.get("platform", "").strip()),
        })
        if len(matches) >= max(1, min(limit, 25)):
            break
    return matches


def get_nintendo_game_by_id(
    product_id: str,
    platform: str,
    *,
    rows: list[dict[str, Any]] | None = None,
    hk_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    product_id = str(product_id).strip()
    if not product_id.isdigit():
        return None
    tw_catalogue = [
        *MANUAL_CATALOGUE_ENTRIES,
        *(load_cached_catalogue() if rows is None else rows),
    ]
    # Prefer TW/curated metadata for an ID. Only consult HK if TW has no match.
    for row in tw_catalogue:
        if (
            str(row.get("nsuid", "")).strip() == product_id
            and platform_matches(row, platform)
            and title_of(row)
        ):
            return {
                "product_id": product_id,
                "name": title_of(row),
                "platform": "nintendo",
                "platform_verified": isinstance(row.get("platform"), str) and bool(row.get("platform", "").strip()),
            }

    supplemental_hk = (
        load_optional_hk_catalogue()
        if hk_rows is None and rows is None
        else (hk_rows or [])
    )
    for row in supplemental_hk:
        if (
            str(row.get("nsuid", "")).strip() == product_id
            and platform_matches(row, platform)
            and title_of(row)
        ):
            return {
                "product_id": product_id,
                "name": title_of(row),
                "platform": "nintendo",
                "platform_verified": isinstance(row.get("platform"), str) and bool(row.get("platform", "").strip()),
            }
    return None
