"""Nintendo eShop digital-price adapter.

This module is deliberately isolated from Discord commands. It consumes a stable
Nintendo title ID supplied by a separately verified catalogue and never treats a
physical retailer listing as a digital price. The endpoint is undocumented; do
not enable production lookup until its current behaviour and permitted use have
been reviewed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

PRICE_API_URL = "https://api.ec.nintendo.com/v1/price"
ALLOWED_COUNTRIES = {"TW", "JP"}
ALLOWED_LANGUAGES = {"zh", "en", "ja"}


class NintendoPriceError(RuntimeError):
    """The Nintendo price endpoint returned an unusable response."""


def _price_amount(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("raw_value")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    return None


def get_nintendo_digital_price(
    title_id: str,
    country: str = "TW",
    lang: str = "zh",
    *,
    session: Any = requests,
) -> dict[str, Any] | None:
    """Return a normalized regional digital price for a known Nintendo title ID.

    Returns None only when the response explicitly has no matching title record.
    An explicit regional non-sale record is returned with available=False so the
    caller can distinguish it from network/API failure. This function never
    silently falls back to another country.
    """
    title_id = str(title_id).strip()
    country = str(country).upper()
    lang = str(lang).lower()
    if not title_id.isdigit():
        raise ValueError("Nintendo title ID must contain digits only")
    if country not in ALLOWED_COUNTRIES:
        raise ValueError("Unsupported Nintendo price region")
    if lang not in ALLOWED_LANGUAGES:
        raise ValueError("Unsupported Nintendo API language")

    response = session.get(
        PRICE_API_URL,
        params={"country": country, "lang": lang, "ids": title_id},
        timeout=12,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except (ValueError, TypeError) as exc:
        raise NintendoPriceError("Nintendo price API returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise NintendoPriceError("Nintendo price API response must be an object")
    prices = payload.get("prices")
    if not isinstance(prices, list):
        raise NintendoPriceError("Nintendo price API response has no prices list")

    record = next(
        (
            item for item in prices
            if isinstance(item, dict)
            and str(item.get("title_id", "")) == title_id
        ),
        None,
    )
    if record is None:
        return None

    sales_status = str(record.get("sales_status", "")).lower()
    regular = record.get("regular_price")
    discount = record.get("discount_price")
    regular_amount = _price_amount(regular)
    discount_amount = _price_amount(discount)
    currency = None
    for candidate in (discount, regular):
        if isinstance(candidate, dict) and candidate.get("currency"):
            currency = str(candidate["currency"])
            break

    # Only these known positive statuses count as currently purchasable.
    available = sales_status in {"onsale", "on_sale", "preorder", "pre_order"}
    selected_amount = discount_amount if discount_amount is not None else regular_amount
    return {
        "provider": "Nintendo eShop price API (undocumented)",
        "title_id": title_id,
        "region": country,
        "currency": currency or ("TWD" if country == "TW" else "JPY"),
        "sales_status": sales_status or "unknown",
        "available": available,
        "regular_price": regular_amount,
        "discount_price": discount_amount,
        "current_price": selected_amount if available else None,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "url": (
            f"https://ec.nintendo.com/{country}/"
            f"{'zh' if country == 'TW' else 'ja'}/titles/{title_id}"
        ),
    }
