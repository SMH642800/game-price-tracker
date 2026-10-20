"""Cached search helpers for the Nintendo Taiwan software catalogue.

The catalogue endpoint is undocumented. Use this module only with the existing
manual probe/cache workflow; a catalogue match is not proof of API stability or
permission for automated reuse.
"""
from __future__ import annotations

import json
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
CACHE_TTL_SECONDS = 24 * 60 * 60
CACHE_PATH = Path(__file__).resolve().parent / ".cache" / "nintendo_tw_catalogue.json"


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


def platform_matches(row: dict[str, Any], platform: str) -> bool:
    value = row.get("platform")
    title = normalize(title_of(row))
    # Some valid catalogue entries (including probe-confirmed priced titles)
    # omit platform metadata. Keep those searchable, but mark them unverified
    # in the returned choice/result rather than asserting a generation.
    if not isinstance(value, str) or not value.strip():
        is_explicit_switch_2_edition = any(
            marker in title for marker in ("switch2edition", "nintendoswitch2", "ns2edition")
        )
        return not (platform == "ns" and is_explicit_switch_2_edition)
    normalized = normalize(value)
    is_switch_2 = "2" in normalized or "switch2" in normalized
    if platform == "ns2":
        return is_switch_2
    if platform == "ns":
        return not is_switch_2 and ("switch" in normalized or "任天堂" in normalized)
    return False


def load_cached_catalogue(*, now: float | None = None) -> list[dict[str, Any]]:
    """Read the probe-generated cache; do not start a multi-minute crawl in autocomplete."""
    current = time.time() if now is None else now
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NintendoCatalogueError(
            "找不到 Nintendo 目錄快取；請先在專案根目錄執行 "
            "python scripts/probe_nintendo_sources.py"
        ) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NintendoCatalogueError("Nintendo 目錄快取無法讀取，請重新執行來源探測腳本") from exc

    fetched_at = payload.get("fetched_at") if isinstance(payload, dict) else None
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if (
        not isinstance(fetched_at, (int, float))
        or current - fetched_at < 0
        or current - fetched_at > CACHE_TTL_SECONDS
        or not isinstance(rows, list)
        or not all(isinstance(row, dict) for row in rows)
    ):
        raise NintendoCatalogueError(
            "Nintendo 目錄快取已過期或格式不正確；請執行 "
            "python scripts/probe_nintendo_sources.py --refresh-cache"
        )
    return rows


def search_nintendo_games(
    query: str, platform: str, *, rows: list[dict[str, Any]] | None = None, limit: int = 25
) -> list[dict[str, str]]:
    """Return real catalogue entries with stable NSUIDs, deduplicated by ID."""
    if platform not in {"ns", "ns2"}:
        raise ValueError("Nintendo catalogue search supports ns and ns2 only")
    needle = normalize(query)
    if not needle:
        return []
    catalogue = load_cached_catalogue() if rows is None else rows
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
            "platform": platform,
            "platform_verified": isinstance(row.get("platform"), str) and bool(row.get("platform", "").strip()),
        })
        if len(matches) >= max(1, min(limit, 25)):
            break
    return matches


def get_nintendo_game_by_id(
    product_id: str, platform: str, *, rows: list[dict[str, Any]] | None = None
) -> dict[str, str] | None:
    product_id = str(product_id).strip()
    if not product_id.isdigit():
        return None
    catalogue = load_cached_catalogue() if rows is None else rows
    for row in catalogue:
        if (
            str(row.get("nsuid", "")).strip() == product_id
            and platform_matches(row, platform)
            and title_of(row)
        ):
            return {
                "product_id": product_id,
                "name": title_of(row),
                "platform": platform,
                "platform_verified": isinstance(row.get("platform"), str) and bool(row.get("platform", "").strip()),
            }
    return None
