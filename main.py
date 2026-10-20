import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests
import steam
import nintendo
from dotenv import load_dotenv

load_dotenv()

TAIWAN_TZ = timezone(timedelta(hours=8))

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "notification_state.json"
WATCHLIST_PATH = BASE_DIR / "games_track_list.json"

STEAM_API_URL = (
    "https://store.steampowered.com/api/appdetails"
)


def get_steam_price(app_id, region="TW"):
    """Return a verified regional Steam price using the shared provider adapter."""
    game = steam.get_price(
        app_id,
        region=region,
        language="zh-tw",
        expiration_resolver=get_steam_discount_expiration,
    )
    if game is None or not game.get("price_available"):
        print(f"No usable price available: {app_id}")
        return None
    return game


def is_nintendo_digital(config):
    """Whether a watch-list row is an eligible Nintendo digital product."""
    platform = str(config.get("platform", "")).lower()
    store = str(config.get("store") or platform).lower()
    price_mode = str(config.get("price_mode") or "digital").lower()
    product_id = str(config.get("product_id", config.get("app_id", ""))).strip()
    return (
        platform in {"nintendo", "ns", "ns2"}
        and store in {"nintendo_eshop", "nintendo"}
        and price_mode == "digital"
        and product_id.isdigit()
    )


def get_nintendo_price(config):
    """Return a verified Taiwan Nintendo eShop price for a tracked digital title."""
    product_id = str(config.get("product_id", config.get("app_id", ""))).strip()
    region = str(config.get("region") or "TW").upper()
    if region != "TW":
        raise ValueError(
            "Scheduled Nintendo notifications currently require region TW and currency TWD"
        )

    result = nintendo.get_nintendo_digital_price(
        product_id,
        country="TW",
        lang="zh",
    )
    if result is None:
        return None

    normalized = dict(result)
    normalized["name"] = str(config.get("name") or f"Nintendo title {product_id}")
    regular = normalized.get("regular_price")
    current = normalized.get("current_price")
    if (
        normalized.get("available")
        and regular is not None
        and current is not None
        and normalized.get("currency") == "TWD"
        and regular > 0
        and current < regular
    ):
        normalized["discount"] = max(1, round((regular - current) / regular * 100))
    else:
        normalized["discount"] = 0
    return normalized


def send_discord_message(message):
    if not WEBHOOK_URL:
        raise RuntimeError("Missing DISCORD_WEBHOOK_URL")

    response = requests.post(
        WEBHOOK_URL,
        json={"content": message},
        timeout=20,
    )
    response.raise_for_status()


def product_state_key(game_config):
    platform = str(game_config.get("platform", "steam")).lower()
    store = str(game_config.get("store") or platform).lower()
    region = str(game_config.get("region") or "TW").upper()
    product_id = game_config.get("product_id", game_config.get("app_id"))
    if product_id is None or not str(product_id).strip():
        raise ValueError("Tracked game is missing product_id/app_id")
    return f"{platform}:{store}:{region}:{str(product_id).strip()}"


def load_notification_state():
    try:
        with STATE_PATH.open("r", encoding="utf-8") as file:
            state = json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "notification_state.json is invalid JSON; refusing to reset notification history"
        ) from error
    if not isinstance(state, dict):
        raise RuntimeError("notification_state.json must contain a JSON object")
    migrated = {}
    for key, value in state.items():
        if str(key).isdigit():
            migrated[f"steam:steam:TW:{key}"] = value
        else:
            migrated[key] = value
    return migrated


def save_notification_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".notification_state.", suffix=".tmp", dir=str(STATE_PATH.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, STATE_PATH)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise



def get_steam_discount_expiration(app_id, region="TW"):
    """Compatibility wrapper for the shared Steam provider's best-effort parser."""
    return steam.get_discount_expiration(app_id, region)


def format_taiwan_datetime(expiration):
    if not expiration:
        return "商店未提供結束時間"

    dt = datetime.fromtimestamp(
        int(expiration),
        tz=timezone.utc,
    ).astimezone(TAIWAN_TZ)

    return dt.strftime("%Y/%m/%d %H:%M")


def format_time_remaining(expiration):
    if not expiration:
        return "商店未提供結束時間"

    seconds_left = int(expiration) - int(
        datetime.now(timezone.utc).timestamp()
    )

    if seconds_left <= 0:
        return "結束時間已到，請重新確認商店"

    days, remainder = divmod(seconds_left, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60

    parts = []

    if days:
        parts.append(f"{days} 天")

    if hours:
        parts.append(f"{hours} 小時")

    if minutes or not parts:
        parts.append(f"{minutes} 分鐘")

    return " ".join(parts)


def main():
    notification_state = load_notification_state()
    with WATCHLIST_PATH.open("r", encoding="utf-8") as file:
        games = json.load(file)
    if not isinstance(games, list) or any(not isinstance(item, dict) for item in games):
        raise RuntimeError("games_track_list.json must be a JSON array of objects")

    print("=== Current watch list ===")
    print(json.dumps(games, ensure_ascii=False, indent=2))
    active_keys = {
        product_state_key(game)
        for game in games
        if (
            (
                str(game.get("platform", "steam")).lower() == "steam"
                and (game.get("product_id") or game.get("app_id"))
            )
            or is_nintendo_digital(game)
        )
    }
    managed_state_prefixes = (
        "steam:steam:",
        "nintendo:nintendo_eshop:",
        "nintendo:nintendo:",
        "ns:nintendo_eshop:",
        "ns:nintendo:",
        "ns2:nintendo_eshop:",
        "ns2:nintendo:",
    )
    for key in list(notification_state):
        if key.startswith(managed_state_prefixes) and key not in active_keys:
            notification_state.pop(key, None)
            print(f"Removed stale notification state: {key}")

    failures = []
    for config in games:
        platform = str(config.get("platform", "steam")).lower()
        if platform != "steam" and not is_nintendo_digital(config):
            print(
                f"Skipped scheduled price check: {config.get('name', 'unknown game')} "
                f"({platform}); this product has no supported automatic price provider"
            )
            continue

        try:
            state_key = product_state_key(config)
            if platform == "steam":
                product_id = str(config.get("product_id", config.get("app_id"))).strip()
                region = str(config.get("region") or "TW").upper()
                game = get_steam_price(product_id, region)
                if game is None:
                    failures.append(f"No usable price data for Steam App ID {product_id}")
                    print(f"WARNING: No usable price data for Steam App ID {product_id}")
                    continue

                if game["discount"] <= 0:
                    notification_state.pop(state_key, None)
                    print(f"No discount: {game['name']}")
                    continue

                current_deal = {
                    "discount": game["discount"],
                    "final_price": game["final_price"],
                }
                message = (
                    f"🎮 **Steam 特價通知：{game['name']}**\n"
                    f"目前價格：{game['currency']} {game['final_price']:.2f}\n"
                    f"原價：{game['currency']} {game['initial_price']:.2f}\n"
                    f"折扣：{game['discount']}%\n"
                    f"截止時間：{format_taiwan_datetime(game.get('discount_expiration'))}（台灣時間）\n"
                    f"剩餘時間：{format_time_remaining(game.get('discount_expiration'))}\n"
                    f"{game['url']}"
                )
            else:
                game = get_nintendo_price(config)
                product_id = str(config.get("product_id", config.get("app_id"))).strip()
                if game is None:
                    failure = f"No usable Taiwan Nintendo price data for NSUID {product_id}"
                    failures.append(failure)
                    print(f"WARNING: {failure}")
                    continue

                if not game.get("available"):
                    sales_status = str(game.get("sales_status") or "").lower()
                    confirmed_unavailable_statuses = {
                        "not_for_sale",
                        "notforsale",
                        "not_available",
                        "unavailable",
                        "discontinued",
                    }
                    if sales_status in confirmed_unavailable_statuses:
                        notification_state.pop(state_key, None)
                        print(f"Not currently for sale: {game['name']} ({sales_status})")
                    else:
                        failure = (
                            f"Unrecognized Nintendo sales status for NSUID {product_id}: "
                            f"{sales_status or 'missing'}"
                        )
                        failures.append(failure)
                        print(f"WARNING: {failure}; keeping previous notification state")
                    continue

                if (
                    game.get("currency") != "TWD"
                    or game.get("regular_price") is None
                    or game.get("current_price") is None
                ):
                    failure = f"Unverified Taiwan Nintendo price data for NSUID {product_id}"
                    failures.append(failure)
                    print(f"WARNING: {failure}")
                    continue

                if game["discount"] <= 0:
                    notification_state.pop(state_key, None)
                    print(f"No discount: {game['name']}")
                    continue

                current_deal = {
                    "discount": game["discount"],
                    "final_price": game["current_price"],
                }
                message = (
                    f"🎮 **Nintendo Switch 特價通知：{game['name']}**\n"
                    f"目前價格：TWD {game['current_price']:,.0f}\n"
                    f"原價：TWD {game['regular_price']:,.0f}\n"
                    f"折扣：約 {game['discount']}%\n"
                    f"截止時間：Nintendo 商店未提供\n"
                    f"{game['url']}"
                )

            if notification_state.get(state_key) == current_deal:
                print(f"Already notified: {game['name']}")
                continue

            send_discord_message(message)
            notification_state[state_key] = current_deal
            save_notification_state(notification_state)
            print(f"Notification sent: {game['name']}")
        except (
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            RuntimeError,
        ) as error:
            failure = f"{config.get('name', 'unknown game')}: {type(error).__name__}: {error}"
            failures.append(failure)
            print(
                f"ERROR: Failed to check {config.get('name', 'unknown game')}: "
                f"{type(error).__name__}: {error}"
            )

    # Persist successes even if another game failed, preventing duplicate notifications next run.
    save_notification_state(notification_state)
    if failures:
        print(f"ERROR: {len(failures)} game check(s) failed:")
        for failure in failures:
            print(f" - {failure}")
        raise SystemExit(1)

def test_notification():
    message = (
        "🧪 **Discord 通知測試**\n"
        "這是一則測試訊息，不代表任何遊戲正在特價。\n"
        "如果你看到這則訊息，代表 Discord Webhook 可以正常運作。"
    )
    send_discord_message(message)
    print("Test notification sent.")


if __name__ == "__main__":
    if "--test-notification" in sys.argv:
        test_notification()
    else:
        main()
