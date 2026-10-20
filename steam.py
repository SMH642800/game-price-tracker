"""Steam store provider adapter.

HTTP access and response normalization live here so Discord commands and the
scheduled notifier share the same parsing rules. This module has no Discord,
watchlist, or notification-state dependencies.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

import requests

APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails/"
STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
REQUEST_TIMEOUT_SECONDS = 15


def _integer_field(value: Any, field: str, *, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"Steam API returned malformed {field}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError(f"Steam API returned malformed {field}")


def _app_details(
    product_id: str,
    *,
    region: str = "TW",
    language: str = "tchinese",
    session: Any = requests,
) -> dict[str, Any] | None:
    product_id = str(product_id).strip()
    if not product_id.isdigit():
        raise ValueError("Steam App ID must contain digits only")
    response = session.get(
        APP_DETAILS_URL,
        params={"appids": product_id, "cc": region.lower(), "l": language},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Steam API response must be a JSON object")
    result = payload.get(product_id)
    if not isinstance(result, dict) or not result.get("success"):
        return None
    data = result.get("data")
    return data if isinstance(data, dict) else None


def get_price(
    product_id: str,
    region: str = "TW",
    language: str = "tchinese",
    *,
    session: Any = requests,
    expiration_resolver: Callable[[str, str], int | None] | None = None,
) -> dict[str, Any] | None:
    """Return normalized regional price details, or None if app details are absent."""
    product_id = str(product_id).strip()
    data = _app_details(
        product_id, region=region, language=language, session=session
    )
    if data is None:
        return None

    url = f"https://store.steampowered.com/app/{product_id}/"
    name = data.get("name", f"Steam App {product_id}")
    price = data.get("price_overview")
    if not isinstance(price, dict):
        return {"name": name, "price_available": False, "url": url}

    currency = price.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError(f"Steam API returned no currency for {product_id}")
    currency = currency.strip().upper()
    # A Taiwan request with a different or absent currency is not a verified
    # Taiwan numeric price. Never silently relabel it as TWD.
    if region.upper() == "TW" and currency != "TWD":
        return {"name": name, "price_available": False, "url": url}

    final_minor = _integer_field(price.get("final"), "final price")
    initial_minor = _integer_field(price.get("initial"), "initial price")
    discount = _integer_field(
        price.get("discount_percent", 0), "discount percentage", default=0
    )
    if final_minor < 0 or initial_minor < 0 or not 0 <= discount <= 100:
        raise ValueError(f"Steam API returned out-of-range price fields for {product_id}")

    expiration = price.get("discount_expiration")
    if isinstance(expiration, bool) or not isinstance(expiration, int) or expiration <= 0:
        expiration = (
            expiration_resolver(product_id, region)
            if expiration_resolver is not None else None
        )

    return {
        "name": name,
        "price_available": True,
        "currency": currency,
        "final_price": final_minor / 100,
        "initial_price": initial_minor / 100,
        "discount": discount,
        "discount_expiration": expiration,
        "url": url,
    }


def search_games(
    query: str,
    region: str = "TW",
    language: str = "tchinese",
    *,
    session: Any = requests,
) -> list[dict[str, str]]:
    response = session.get(
        STORE_SEARCH_URL,
        params={"term": query, "l": language, "cc": region.lower()},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Steam search response must be a JSON object")
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Steam search response items must be a list")
    results = []
    for item in items[:25]:
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("id", ""))
        name = item.get("name", "")
        if product_id.isdigit() and isinstance(name, str) and name.strip():
            results.append({"product_id": product_id, "name": name.strip()})
    return results


def get_game_name(
    product_id: str,
    region: str = "TW",
    language: str = "tchinese",
    *,
    session: Any = requests,
) -> str | None:
    data = _app_details(
        product_id, region=region, language=language, session=session
    )
    if data is None:
        return None
    name = data.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def get_discount_expiration(
    product_id: str,
    region: str = "TW",
    *,
    session: Any = requests,
) -> int | None:
    """Best-effort parse of Steam's English sale-countdown text."""
    url = f"https://store.steampowered.com/app/{product_id}/"
    try:
        response = session.get(
            url,
            params={"cc": region.lower(), "l": "english"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        match = re.search(
            r'<p class="game_purchase_discount_countdown">'
            r'\s*SPECIAL PROMOTION!\s*Offer ends '
            r'(\d{1,2}) ([A-Za-z]+)',
            response.text,
            re.IGNORECASE,
        )
        if not match:
            return None
        day = int(match.group(1))
        month = datetime.strptime(match.group(2), "%B").month
        now = datetime.now(timezone.utc)
        expiration = datetime(
            now.year, month, day, 23, 59, 59, tzinfo=timezone.utc
        )
        if expiration < now:
            expiration = datetime(
                now.year + 1, month, day, 23, 59, 59, tzinfo=timezone.utc
            )
        return int(expiration.timestamp())
    except (requests.RequestException, ValueError):
        return None
