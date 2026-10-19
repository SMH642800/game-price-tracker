import os
import requests

APP_ID = os.getenv("STEAM_APP_ID", "413150")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

API_URL = (
    "https://store.steampowered.com/api/appdetails" f"?appids={APP_ID}&cc=tw&l=zh-tw"
)


def main():
    if not WEBHOOK_URL:
        raise RuntimeError("Missing DISCORD_WEBHOOK_URL")

    response = requests.get(API_URL, timeout=20)
    response.raise_for_status()

    payload = response.json().get(APP_ID, {})
    print("DEBUG APP_ID:", APP_ID)
    print("DEBUG API success:", payload.get("success"))
    print("DEBUG game name:", payload.get("data", {}).get("name"))
    print("DEBUG price_overview:", payload.get("data", {}).get("price_overview"))

    if not payload.get("success"):
        raise RuntimeError(f"Steam returned no usable data for app {APP_ID}")

    game = payload["data"]
    price = game.get("price_overview")

    if not price:
        print("No price available; skipping notification.")
        return

    name = game.get("name", f"Steam App {APP_ID}")
    currency = price.get("currency", "")
    final_price = price.get("final", 0) / 100
    initial_price = price.get("initial", 0) / 100
    discount = price.get("discount_percent", 0)

    message = (
        f"🎮 **Steam 價格測試：{name}**\n"
        f"目前價格：{currency} {final_price:.2f}\n"
        f"原價：{currency} {initial_price:.2f}\n"
        f"折扣：{discount}%\n"
        f"https://store.steampowered.com/app/{APP_ID}/"
    )

    result = requests.post(
        WEBHOOK_URL,
        json={"content": message},
        timeout=20,
    )
    result.raise_for_status()

    print(f"Notification sent: {name}")


if __name__ == "__main__":
    main()
