import asyncio
import base64
import json
import os
import time

import discord
import requests
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ADMIN_ID = os.getenv("DISCORD_ADMIN_ID")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "SMH642800/game-price-tracker"
GITHUB_FILE_PATH = "games_track_list.json"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
GITHUB_CONTENTS_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents"
SUPPORTED_PLATFORMS = {
    "steam": "Steam",
    "ps5": "PlayStation 5",
    "ns2": "Nintendo Switch 2",
}

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def github_headers():
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_github_watchlist_with_sha():
    response = requests.get(GITHUB_API_URL, headers=github_headers(), timeout=15)
    response.raise_for_status()
    payload = response.json()
    content = base64.b64decode(payload["content"]).decode("utf-8")
    games = json.loads(content)
    if not isinstance(games, list) or any(not isinstance(item, dict) for item in games):
        raise ValueError("games_track_list.json must be a JSON array of objects")
    return games, payload["sha"]


def load_github_watchlist():
    games, _ = fetch_github_watchlist_with_sha()
    return games


def fetch_github_json_file(path):
    """Fetch and decode a JSON file from this repository's default branch."""
    response = requests.get(
        f"{GITHUB_CONTENTS_URL}/{path}",
        headers=github_headers(),
        timeout=15,
    )
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    payload = response.json()
    content = base64.b64decode(payload["content"]).decode("utf-8")
    return json.loads(content)


def get_steam_current_price(product_id):
    """Return current Taiwan Steam price details for a valid App ID."""
    if not str(product_id).isdigit():
        raise ValueError("Steam App ID must contain digits only")
    response = requests.get(
        "https://store.steampowered.com/api/appdetails/",
        params={"appids": str(product_id), "l": "tchinese", "cc": "tw"},
        timeout=15,
    )
    response.raise_for_status()
    result = response.json().get(str(product_id), {})
    if not isinstance(result, dict) or not result.get("success"):
        return None
    data = result.get("data", {})
    if not isinstance(data, dict):
        return None
    price = data.get("price_overview")
    if not isinstance(price, dict):
        return {
            "name": data.get("name", f"Steam App {product_id}"),
            "price_available": False,
            "url": f"https://store.steampowered.com/app/{product_id}/",
        }
    return {
        "name": data.get("name", f"Steam App {product_id}"),
        "price_available": True,
        "currency": price.get("currency", "TWD"),
        "final_price": price.get("final", 0) / 100,
        "initial_price": price.get("initial", 0) / 100,
        "discount": price.get("discount_percent", 0),
        "url": f"https://store.steampowered.com/app/{product_id}/",
    }


def update_github_watchlist(mutator, retries=5):
    """Re-read and re-apply the mutation after SHA conflicts to avoid lost updates."""
    last_error = None
    for attempt in range(retries):
        games, sha = fetch_github_watchlist_with_sha()
        original_games = list(games)
        updated_games, result = mutator(games)
        if updated_games == original_games:
            return result

        content = json.dumps(updated_games, ensure_ascii=False, indent=2) + "\n"
        response = requests.put(
            GITHUB_API_URL,
            headers=github_headers(),
            json={
                "message": "Update tracked games via Discord bot",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "sha": sha,
            },
            timeout=15,
        )
        if response.status_code in (409, 422):
            last_error = requests.HTTPError(
                f"GitHub watchlist changed concurrently (HTTP {response.status_code})"
            )
            time.sleep(0.2 * (attempt + 1))
            continue
        response.raise_for_status()
        return result
    raise RuntimeError("Could not update watchlist after concurrent changes") from last_error


def search_steam_games(query):
    response = requests.get(
        "https://store.steampowered.com/api/storesearch/",
        params={"term": query, "l": "tchinese", "cc": "tw"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    results = []
    for item in data.get("items", [])[:25]:
        product_id = str(item.get("id", ""))
        name = item.get("name", "")
        if product_id.isdigit() and name:
            results.append({"product_id": product_id, "name": name})
    return results


def get_steam_game(product_id):
    response = requests.get(
        "https://store.steampowered.com/api/appdetails",
        params={"appids": product_id, "l": "tchinese", "cc": "tw"},
        timeout=15,
    )
    response.raise_for_status()
    result = response.json().get(str(product_id), {})
    if not isinstance(result, dict) or not result.get("success"):
        return None
    data = result.get("data", {})
    return data.get("name") if isinstance(data, dict) else None


def platform_of(game):
    return str(game.get("platform", "steam")).lower()


def product_id_of(game):
    return str(game.get("product_id", game.get("app_id", ""))).strip()


def is_admin(user):
    return ADMIN_ID is not None and str(user.id) == ADMIN_ID


async def platform_autocomplete(interaction, current):
    if not current.strip():
        return []
    platform = str(getattr(interaction.namespace, "platform", "steam")).lower()
    # Only Steam has a live, verified search adapter for now.
    if platform != "steam":
        return []
    try:
        results = await asyncio.to_thread(search_steam_games, current.strip())
        return [
            app_commands.Choice(
                name=f"{item['name']} (ID: {item['product_id']})"[:100],
                value=item["product_id"],
            )
            for item in results[:25]
        ]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return []


async def remove_game_autocomplete(interaction, current):
    if not is_admin(interaction.user):
        return []
    platform = str(getattr(interaction.namespace, "platform", "steam")).lower()
    query = current.strip().casefold()
    try:
        games = await asyncio.to_thread(load_github_watchlist)
        choices = []
        for game in games:
            if platform_of(game) != platform:
                continue
            product_id = product_id_of(game)
            name = str(game.get("name", ""))
            if not product_id or not name:
                continue
            if query and query not in name.casefold() and query not in product_id.casefold():
                continue
            choices.append(
                app_commands.Choice(name=f"{name} ({product_id})"[:100], value=product_id)
            )
        return choices[:25]
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError):
        return []


@tree.command(name="ping", description="測試 Game Price Tracker Bot 是否正常運作")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong！Game Price Tracker Bot 正常運作。", ephemeral=True)


@tree.command(name="admincheck", description="檢查自己是否具有 Bot 管理員權限")
async def admincheck(interaction: discord.Interaction):
    message = "✅ 你已通過管理員驗證。" if is_admin(interaction.user) else "⛔ 你沒有 Bot 管理員權限。"
    await interaction.response.send_message(message, ephemeral=True)


@tree.command(name="list", description="查看目前追蹤的遊戲")
async def list_games(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        games = await asyncio.to_thread(load_github_watchlist)
        lines = [f"🎮 **遊戲追蹤清單**（共 {len(games)} 款）"]
        for platform, platform_name in SUPPORTED_PLATFORMS.items():
            platform_games = [item for item in games if platform_of(item) == platform]
            if not platform_games:
                continue
            lines.append("")
            lines.append(f"🕹️ **{platform_name}（{len(platform_games)} 款）**")
            for item in platform_games:
                product_id = product_id_of(item)
                name = str(item.get("name", "未知遊戲")).replace("\\n", " ").strip()
                region = str(item.get("region", "TW"))
                lines.append(f"• **{name[:120]}** — ID: `{product_id or '未知'}`（{region}）")

        if not games:
            lines.append("目前沒有追蹤任何遊戲。")

        # Discord message content is limited to 2,000 characters. Split at line
        # boundaries to keep large watchlists usable instead of exceeding embed limits.
        chunks = []
        current = ""
        for line in lines:
            candidate = f"{current}\\n{line}" if current else line
            if len(candidate) > 1800 and current:
                chunks.append(current)
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)

        await interaction.followup.send(chunks[0], ephemeral=True)
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)
    except requests.RequestException:
        await interaction.followup.send("❌ 暫時無法連線至 GitHub，請稍後再試。", ephemeral=True)
    except (ValueError, KeyError, TypeError, RuntimeError):
        await interaction.followup.send("❌ 遊戲清單格式或設定有誤，請檢查 GitHub 上的 JSON 與 Token。", ephemeral=True)


PLATFORM_CHOICES = [
    app_commands.Choice(name="Steam", value="steam"),
    app_commands.Choice(name="PlayStation 5", value="ps5"),
    app_commands.Choice(name="Nintendo Switch 2", value="ns2"),
]


@tree.command(name="add", description="選擇平台並搜尋要追蹤的遊戲（管理員限定）")
@app_commands.describe(
    platform="先選擇遊戲平台",
    game="輸入遊戲名稱，並從搜尋結果中選擇",
)
@app_commands.choices(platform=PLATFORM_CHOICES)
@app_commands.autocomplete(game=platform_autocomplete)
async def add_game(interaction: discord.Interaction, platform: str, game: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("⛔ 你沒有 Bot 管理員權限。", ephemeral=True)
        return
    platform = platform.lower()
    if platform != "steam":
        await interaction.response.send_message(
            f"ℹ️ 已選擇 {SUPPORTED_PLATFORMS.get(platform, platform)}，但目前尚未接入可驗證的台灣商店搜尋與查價來源。尚未修改清單；Steam 功能不受影響。",
            ephemeral=True,
        )
        return
    product_id = game.strip()
    if not product_id.isdigit():
        await interaction.response.send_message("❌ 請從 Steam 搜尋結果中選擇遊戲。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        steam_name = await asyncio.to_thread(get_steam_game, product_id)
        if steam_name is None:
            await interaction.followup.send(f"❌ Steam 查不到 App ID `{product_id}`，請重新搜尋。", ephemeral=True)
            return

        def add_mutation(games):
            if any(platform_of(item) == "steam" and product_id_of(item) == product_id for item in games):
                return games, False
            games.append({
                "platform": "steam",
                "store": "steam",
                "product_id": product_id,
                "region": "TW",
                "name": steam_name,
            })
            return games, True

        added = await asyncio.to_thread(update_github_watchlist, add_mutation)
        if not added:
            await interaction.followup.send("⚠️ 這款遊戲已經在追蹤清單中。", ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ 已新增 **{steam_name}**（Steam App ID：`{product_id}`，台灣商店）到追蹤清單。",
            ephemeral=True,
        )
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError) as error:
        await interaction.followup.send(f"❌ 新增失敗：{type(error).__name__}。請稍後再試。", ephemeral=True)


@tree.command(name="remove", description="依平台移除追蹤遊戲（管理員限定）")
@app_commands.describe(platform="選擇遊戲平台", game="選擇該平台已追蹤的遊戲")
@app_commands.choices(platform=PLATFORM_CHOICES)
@app_commands.autocomplete(game=remove_game_autocomplete)
async def remove_game(interaction: discord.Interaction, platform: str, game: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("⛔ 你沒有 Bot 管理員權限。", ephemeral=True)
        return
    platform = platform.lower()
    product_id = game.strip()
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        def remove_mutation(games):
            removed = [
                item for item in games
                if platform_of(item) == platform and product_id_of(item) == product_id
            ]
            if not removed:
                return games, None
            return [
                item for item in games
                if not (platform_of(item) == platform and product_id_of(item) == product_id)
            ], removed[0]

        removed = await asyncio.to_thread(update_github_watchlist, remove_mutation)
        if removed is None:
            await interaction.followup.send("⚠️ 找不到該平台的追蹤遊戲，清單未變更。", ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ 已從 {SUPPORTED_PLATFORMS.get(platform, platform)} 移除 **{removed.get('name', '未知遊戲')}**。",
            ephemeral=True,
        )
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError):
        await interaction.followup.send("❌ 移除失敗，請稍後再試並檢查 GitHub Token 權限。", ephemeral=True)



async def tracked_game_autocomplete(interaction, current):
    """Suggest tracked Steam games to every user without granting watchlist edit access."""
    query = current.strip().casefold()
    try:
        games = await asyncio.to_thread(load_github_watchlist)
        choices = []
        for item in games:
            if platform_of(item) != "steam":
                continue
            product_id = product_id_of(item)
            name = str(item.get("name", ""))
            if not product_id or not name:
                continue
            if query and query not in name.casefold() and query not in product_id.casefold():
                continue
            choices.append(
                app_commands.Choice(name=f"{name} ({product_id})"[:100], value=product_id)
            )
        return choices[:25]
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError):
        return []


@tree.command(name="price", description="查詢 Steam 台灣商店目前價格")
@app_commands.describe(game="輸入遊戲名稱，並從 Steam 搜尋結果中選擇")
@app_commands.autocomplete(game=platform_autocomplete)
async def price_command(interaction: discord.Interaction, game: str):
    product_id = game.strip()
    if not product_id.isdigit():
        await interaction.response.send_message("❌ 請從 Steam 搜尋結果中選擇遊戲。", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        result = await asyncio.to_thread(get_steam_current_price, product_id)
        if result is None:
            await interaction.followup.send("❌ Steam 找不到這款遊戲或目前無法取得資料。", ephemeral=True)
            return
        if not result["price_available"]:
            message = (
                f"🎮 **{result['name']}**\n"
                "台灣商店目前沒有可用的價格資料（可能是免費遊戲、尚未發售或地區限制）。\n"
                f"{result['url']}"
            )
        else:
            message = (
                f"🎮 **{result['name']}**\n"
                f"目前價格：**{result['currency']} {result['final_price']:.2f}**\n"
                f"原價：{result['currency']} {result['initial_price']:.2f}\n"
                f"折扣：**{result['discount']}%**\n"
                f"{result['url']}"
            )
        await interaction.followup.send(message, ephemeral=True)
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        print(f"Steam price query failed for {product_id}: {type(error).__name__}: {error}")
        await interaction.followup.send("❌ 查價服務暫時無法使用，請稍後再試。", ephemeral=True)


@tree.command(name="history", description="查看已記錄的 Steam 遊戲價格歷史")
@app_commands.describe(game="選擇目前追蹤清單中的遊戲")
@app_commands.autocomplete(game=tracked_game_autocomplete)
async def history_command(interaction: discord.Interaction, game: str):
    product_id = game.strip()
    if not product_id.isdigit():
        await interaction.response.send_message("❌ 請從追蹤清單的搜尋結果中選擇遊戲。", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        games, history = await asyncio.gather(
            asyncio.to_thread(load_github_watchlist),
            asyncio.to_thread(fetch_github_json_file, "price_history.json"),
        )
        config = next((
            item for item in games
            if platform_of(item) == "steam" and product_id_of(item) == product_id
        ), None)
        if config is None:
            await interaction.followup.send("⚠️ 這款遊戲目前不在追蹤清單中。", ephemeral=True)
            return
        key = f"steam:steam:{str(config.get('region') or 'TW').upper()}:{product_id}"
        samples = history.get(key, []) if isinstance(history, dict) else []
        if not samples:
            await interaction.followup.send(
                f"📉 **{config.get('name', '未知遊戲')}** 尚無歷史價格紀錄。\n"
                "紀錄會從下一次成功的自動查價開始累積，不會自動補出過去價格。",
                ephemeral=True,
            )
            return
        valid = [sample for sample in samples if isinstance(sample, dict) and isinstance(sample.get("final_price"), (int, float))]
        if not valid:
            await interaction.followup.send("⚠️ 歷史資料格式異常，暫時無法顯示。", ephemeral=True)
            return
        latest = valid[-1]
        lowest = min(valid, key=lambda sample: sample["final_price"])
        currency = latest.get("currency", "TWD")
        lines = [
            f"📉 **{config.get('name', '未知遊戲')}｜價格紀錄**",
            f"目前記錄價格：**{currency} {latest['final_price']:.2f}**（{latest.get('date_taiwan', '日期未知')}）",
            f"紀錄期間最低：**{lowest.get('currency', currency)} {lowest['final_price']:.2f}**（{lowest.get('date_taiwan', '日期未知')}）",
            f"已記錄 {len(valid)} 筆每日觀測；歷史低價僅代表本 Bot 開始記錄以來。",
            "",
            "**最近紀錄**",
        ]
        for sample in valid[-7:][::-1]:
            lines.append(
                f"• {sample.get('date_taiwan', '日期未知')} — "
                f"{sample.get('currency', currency)} {sample['final_price']:.2f} "
                f"（折扣 {sample.get('discount', 0)}%）"
            )
        lines.append(f"https://store.steampowered.com/app/{product_id}/")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(f"Price history query failed for {product_id}: {type(error).__name__}: {error}")
        await interaction.followup.send("❌ 無法讀取價格歷史，請稍後再試。", ephemeral=True)


@tree.command(name="help", description="查看 Game Price Tracker 的使用說明")
async def help_command(interaction: discord.Interaction):
    message = (
        "🎮 **Game Price Tracker 使用說明**\n\n"
        "**一般指令**\n"
        "• `/ping` — 測試 Bot 是否正常運作\n"
        "• `/list` — 查看目前追蹤的遊戲（依平台分組）\n"
        "• `/help` — 顯示使用說明\n\n"
        "**管理員限定指令**\n"
        "• `/admincheck` — 檢查管理員權限\n"
        "• `/add platform game` — 先選平台，再搜尋遊戲\n"
        "• `/remove platform game` — 依平台移除追蹤遊戲\n\n"
        "📌 目前只有 Steam 已接入即時搜尋與查價；PS5、NS2 尚待可靠的台灣商店資料來源確認。\n"
        "📌 遊戲清單儲存在 GitHub，供自動查價流程使用。"
    )
    await interaction.response.send_message(message, ephemeral=True)


@client.event
async def on_ready():
    guild = discord.Object(id=int(GUILD_ID))
    tree.copy_global_to(guild=guild)
    synced = await tree.sync(guild=guild)
    print(f"已登入 Discord：{client.user}")
    print(f"已同步 {len(synced)} 個斜線指令到指定伺服器。")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("找不到 DISCORD_BOT_TOKEN，請檢查 .env 檔案。")
    if not GITHUB_TOKEN:
        raise RuntimeError("找不到 GITHUB_TOKEN，請檢查 .env 檔案。")
    if not ADMIN_ID or not ADMIN_ID.isdigit():
        raise RuntimeError("DISCORD_ADMIN_ID 尚未正確設定，請檢查 .env 檔案。")
    if not GUILD_ID or not GUILD_ID.isdigit():
        raise RuntimeError("DISCORD_GUILD_ID 尚未正確設定，請檢查 .env 檔案。")
    client.run(TOKEN)
