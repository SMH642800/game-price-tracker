import json
import os
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


def main():
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

        message = (
            f"🎮 **Steam 價格測試：{game['name']}**\n"
            f"目前價格：{game['currency']} {game['final_price']:.2f}\n"
            f"原價：{game['currency']} {game['initial_price']:.2f}\n"
            f"折扣：{game['discount']}%\n"
            f"{game['url']}"
        )

        send_discord_message(message)
        print(f"Notification sent: {game['name']}")


if __name__ == "__main__":
    main()