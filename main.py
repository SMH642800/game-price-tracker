import json
import re
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests

TAIWAN_TZ = timezone(timedelta(hours=8))

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "notification_state.json"
WATCHLIST_PATH = BASE_DIR / "games_track_list.json"

STEAM_API_URL = (
    "https://store.steampowered.com/api/appdetails"
)


def get_steam_price(app_id, region="TW"):
    response = requests.get(
        STEAM_API_URL,
        params={
            "appids": app_id,
            "cc": region.lower(),
            "l": "zh-tw",
        },
        timeout=20,
    )
    response.raise_for_status()

    payload = response.json().get(str(app_id), {})

    if not payload.get("success"):
        print(f"Steam API returned no usable data: {app_id}")
        return None

    game = payload["data"]
    price = game.get("price_overview")

    if not price:
        print(f"No price available: {game.get('name', app_id)}")
        return None

    return {
        "name": game.get("name", f"Steam App {app_id}"),
        "currency": price.get("currency", ""),
        "final_price": price["final"] / 100,
        "initial_price": price["initial"] / 100,
        "discount": price.get("discount_percent", 0),
        "discount_expiration": (
            price.get("discount_expiration")
            or get_steam_discount_expiration(app_id, region)
        ),
        "url": f"https://store.steampowered.com/app/{app_id}/",
    }


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
    url = f"https://store.steampowered.com/app/{app_id}/"

    try:
        response = requests.get(
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
        month_name = match.group(2)

        month = datetime.strptime(month_name, "%B").month
        now = datetime.now(timezone.utc)

        year = now.year
        expiration = datetime(
            year, month, day, 23, 59, 59, tzinfo=timezone.utc
        )

        if expiration < now:
            expiration = datetime(
                year + 1, month, day, 23, 59, 59,
                tzinfo=timezone.utc,
            )

        return int(expiration.timestamp())

    except (requests.RequestException, ValueError) as error:
        print(f"Could not parse Steam sale expiration for {app_id}: {error}")
        return None


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
        if str(game.get("platform", "steam")).lower() == "steam"
        and (game.get("product_id") or game.get("app_id"))
    }
    for key in list(notification_state):
        if key.startswith("steam:steam:") and key not in active_keys:
            notification_state.pop(key, None)
            print(f"Removed stale notification state: {key}")

    failures = []
    for config in games:
        platform = str(config.get("platform", "steam")).lower()
        if platform != "steam":
            if platform in {"ps5", "ns", "ns2"} and (
                config.get("price_mode") == "links_only"
                or config.get("store") == "link_only"
            ):
                print(
                    f"Skipped link-only platform entry: "
                    f"{config.get('name', 'unknown game')} ({platform})"
                )
                continue
            failure = (
                f"Price provider is not configured for platform '{platform}' "
                f"({config.get('name', 'unknown game')})"
            )
            print(f"ERROR: {failure}")
            failures.append(failure)
            continue

        try:
            state_key = product_state_key(config)
            app_id = str(config.get("product_id", config.get("app_id"))).strip()
            region = str(config.get("region") or "TW").upper()
            game = get_steam_price(app_id, region)
            if game is None:
                failures.append(f"No usable price data for Steam App ID {app_id}")
                print(f"WARNING: No usable price data for Steam App ID {app_id}")
                continue

            if game["discount"] <= 0:
                notification_state.pop(state_key, None)
                print(f"No discount: {game['name']}")
                continue

            current_deal = {"discount": game["discount"], "final_price": game["final_price"]}
            if notification_state.get(state_key) == current_deal:
                print(f"Already notified: {game['name']}")
                continue

            message = (
                f"🎮 **Steam 特價通知：{game['name']}**\n"
                f"目前價格：{game['currency']} {game['final_price']:.2f}\n"
                f"原價：{game['currency']} {game['initial_price']:.2f}\n"
                f"折扣：{game['discount']}%\n"
                f"截止時間：{format_taiwan_datetime(game.get('discount_expiration'))}（台灣時間）\n"
                f"剩餘時間：{format_time_remaining(game.get('discount_expiration'))}\n"
                f"{game['url']}"
            )
            send_discord_message(message)
            notification_state[state_key] = current_deal
            save_notification_state(notification_state)
            print(f"Notification sent: {game['name']}")
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
            failure = f"{config.get('name', 'unknown game')}: {type(error).__name__}: {error}"
            failures.append(failure)
            print(f"ERROR: Failed to check {config.get('name', 'unknown game')}: {type(error).__name__}: {error}")

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
