import json
import os
import sys
from datetime import datetime, timezone
import requests

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

STEAM_API_URL = (
    "https://store.steampowered.com/api/appdetails"
)


def get_steam_price(app_id):
    response = requests.get(
        STEAM_API_URL,
        params={
            "appids": app_id,
            "cc": "tw",
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
        "discount_expiration": price.get("discount_expiration"),
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


def load_notification_state():
    try:
        with open("notification_state.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_notification_state(state):
    with open("notification_state.json", "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


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

    with open("games_track_list.json", "r", encoding="utf-8") as file:
        games = json.load(file)

    for game_config in games:
        if game_config.get("platform") != "steam":
            print(f"Skipping unsupported platform: {game_config.get('platform')}")
            continue

        app_id = str(game_config["app_id"])
        game = get_steam_price(app_id)

        if game is None:
            continue

        # 記錄每款遊戲目前的折扣狀態
        if game["discount"] <= 0:
            notification_state.pop(app_id, None)
            print(f"No discount: {game['name']}")
            continue

        # 同一價格、同一折扣只通知一次
        current_deal = {
            "discount": game["discount"],
            "final_price": game["final_price"],
        }

        if notification_state.get(app_id) == current_deal:
            print(f"Already notified: {game['name']}")
            continue

        remaining_text = format_time_remaining(
            game.get("discount_expiration")
        )

        message = (
            f"🎮 **Steam 特價通知：{game['name']}**\n"
            f"目前價格：{game['currency']} {game['final_price']:.2f}\n"
            f"原價：{game['currency']} {game['initial_price']:.2f}\n"
            f"折扣：{game['discount']}%\n"
            f"剩餘時間：{remaining_text}\n"
            f"{game['url']}"
        )

        # 先發送成功，再更新紀錄
        send_discord_message(message)

        notification_state[app_id] = current_deal
        save_notification_state(notification_state)

        print(f"Notification sent: {game['name']}")

    # 即使沒有新通知，也保存恢復原價後清除的紀錄
    save_notification_state(notification_state)


def test_notification():
    state = load_notification_state()
    test_key = "__discord_test_notification__"

    if test_key in state:
        print("Test notification already sent. Skipping.")
        return

    message = (
        "🧪 **Discord 通知測試**\n"
        "這是一則測試訊息，不代表任何 Steam 遊戲正在特價。\n"
        "如果你看到這則訊息，代表 Discord Webhook 可以正常運作。"
    )

    send_discord_message(message)

    state[test_key] = {"sent": True}
    save_notification_state(state)

    print("Test notification sent and saved.")


if __name__ == "__main__":
    if "--test-notification" in sys.argv:
        test_notification()
    else:
        main()
