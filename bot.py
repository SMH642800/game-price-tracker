import asyncio
import base64
import copy
import json
import os
import time

import discord
import requests
from discord import app_commands
from dotenv import load_dotenv

import nintendo
import steam
from nintendo_catalogue import NintendoCatalogueError, get_nintendo_game_by_id, search_nintendo_games

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ADMIN_ID = os.getenv("DISCORD_ADMIN_ID")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "SMH642800/game-price-tracker"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_FILE_PATH = "games_track_list.json"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
GITHUB_CONTENTS_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents"
SUPPORTED_PLATFORMS = {
    "steam": "Steam",
    "ps5": "PlayStation 5",
    "ns": "Nintendo Switch",
    "ns2": "Nintendo Switch 2",
    "nintendo": "Nintendo Switch／Switch 2（平台未標註）",
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
    response = requests.get(
        GITHUB_API_URL, headers=github_headers(), params={"ref": GITHUB_BRANCH}, timeout=15
    )
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

def get_steam_current_price(product_id):
    """Return current Taiwan Steam price details using the shared provider adapter."""
    return steam.get_price(product_id, region="TW", language="tchinese")


def update_github_watchlist(mutator, retries=5):
    """Re-read and re-apply the mutation after SHA conflicts to avoid lost updates."""
    last_error = None
    for attempt in range(retries):
        games, sha = fetch_github_watchlist_with_sha()
        # A shallow copy misses in-place edits to nested watchlist records.
        original_games = copy.deepcopy(games)
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
                "branch": GITHUB_BRANCH,
            },
            timeout=15,
        )
        # 409 is GitHub's explicit content conflict. A 422 can also mean
        # invalid content or validation failure, so do not mask it as a race.
        if response.status_code == 409:
            last_error = requests.HTTPError(
                f"GitHub watchlist changed concurrently (HTTP {response.status_code})"
            )
            time.sleep(0.2 * (attempt + 1))
            continue
        response.raise_for_status()
        return result
    raise RuntimeError("Could not update watchlist after concurrent changes") from last_error


def search_steam_games(query):
    """Search the Taiwan Steam store through the shared provider adapter."""
    return steam.search_games(query, region="TW", language="tchinese")


def get_steam_game(product_id):
    """Return the Steam product name for a valid Taiwan-store App ID."""
    return steam.get_game_name(product_id, region="TW", language="tchinese")


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
    if platform in ("ns", "ns2", "nintendo"):
        try:
            results = await asyncio.to_thread(search_nintendo_games, current.strip(), platform)
            return [
                app_commands.Choice(
                    name=f"{item['name']}｜{SUPPORTED_PLATFORMS.get(item['platform'], SUPPORTED_PLATFORMS['nintendo'])}｜{'平台未標註' if not item['platform_verified'] else '數位版'}"[:100],
                    value=item["product_id"],
                )
                for item in results[:25]
            ]
        except (requests.RequestException, ValueError, RuntimeError, TypeError, KeyError):
            return []
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
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
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
            if platform == "nintendo":
                if platform_of(game) not in {"ns", "ns2", "nintendo"}:
                    continue
            elif platform_of(game) != platform:
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
                name = str(item.get("name", "未知遊戲")).replace("\n", " ").strip()
                region = str(item.get("region", "TW"))
                lines.append(f"• **{name[:120]}** — ID: `{product_id or '未知'}`（{region}）")

        if not games:
            lines.append("目前沒有追蹤任何遊戲。")

        # Discord message content is limited to 2,000 characters. Split at line
        # boundaries to keep large watchlists usable instead of exceeding embed limits.
        chunks = []
        current = ""
        for line in lines:
            candidate = f"{current}\n{line}" if current else line
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


ADD_LOOKUP_PLATFORM_CHOICES = [
    app_commands.Choice(name="Steam", value="steam"),
    app_commands.Choice(name="Nintendo Switch／Switch 2（合併搜尋）", value="nintendo"),
]

REMOVE_PLATFORM_CHOICES = [
    app_commands.Choice(name="Steam", value="steam"),
    app_commands.Choice(name="PlayStation 5（手動追蹤項目）", value="ps5"),
    app_commands.Choice(name="Nintendo Switch／Switch 2（合併）", value="nintendo"),
]


@tree.command(name="add", description="選擇平台並搜尋要追蹤的遊戲（管理員限定）")
@app_commands.describe(
    platform="先選擇遊戲平台",
    game="輸入遊戲名稱，並從搜尋結果中選擇",
)
@app_commands.choices(platform=ADD_LOOKUP_PLATFORM_CHOICES)
@app_commands.autocomplete(game=platform_autocomplete)
async def add_game(interaction: discord.Interaction, platform: str, game: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("⛔ 你沒有 Bot 管理員權限。", ephemeral=True)
        return
    platform = platform.lower()
    if platform in ("ns", "ns2", "nintendo"):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            product_id = game.strip()
            entry = await asyncio.to_thread(get_nintendo_game_by_id, product_id, platform)
            actual_platform = entry["platform"] if entry else platform
            if entry is None:
                await interaction.followup.send(
                    f"❌ 請從 {SUPPORTED_PLATFORMS[platform]} 的目錄搜尋結果中選擇遊戲。",
                    ephemeral=True,
                )
                return

            def add_nintendo_mutation(games):
                valid_platforms = {"ns", "ns2", "nintendo"} if platform == "nintendo" else {platform}
                if any(platform_of(item) in valid_platforms and product_id_of(item) == product_id for item in games):
                    return games, False
                games.append({
                    "platform": actual_platform,
                    "store": "nintendo_eshop",
                    "product_id": product_id,
                    "region": "TW",
                    "name": entry["name"],
                    "edition": "digital",
                    "price_mode": "digital",
                    "catalogue_platform_verified": entry["platform_verified"],
                })
                return games, True

            added = await asyncio.to_thread(update_github_watchlist, add_nintendo_mutation)
            status = "已新增到追蹤清單" if added else "已在追蹤清單中"
            verification_note = "" if entry["platform_verified"] else "\n⚠️ Nintendo 目錄未標註平台世代，請先確認商品是否屬於所選平台。"
            await interaction.followup.send(
                f"✅ {entry['name']}（{SUPPORTED_PLATFORMS.get(actual_platform, SUPPORTED_PLATFORMS['nintendo'])}／台灣數位版，NSUID：{product_id}）{status}。\n"
                "實體版價格不包含在內；Nintendo 數位價格介面尚未公開文件化。"
                f"{verification_note}",
                ephemeral=True,
            )
        except (requests.RequestException, NintendoCatalogueError, ValueError, KeyError, TypeError, RuntimeError) as error:
            await interaction.followup.send(
                f"❌ 新增失敗：{type(error).__name__}。請確認目錄快取並稍後再試。",
                ephemeral=True,
            )
        return
    if platform != "steam":
        await interaction.response.send_message("❌ 不支援的平台。", ephemeral=True)
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
@app_commands.choices(platform=REMOVE_PLATFORM_CHOICES)
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
                if platform_of(item) in ({"ns", "ns2", "nintendo"} if platform == "nintendo" else {platform}) and product_id_of(item) == product_id
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

async def handle_steam_price_query(interaction: discord.Interaction, product_id: str):
    """Shared Steam price lookup flow for slash commands."""
    product_id = product_id.strip()
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
                f"查詢時間（UTC）：{result['retrieved_at']}\n"
                f"{result['url']}"
            )
        await interaction.followup.send(message, ephemeral=True)
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"Steam price query failed for {product_id}: {type(error).__name__}: {error}")
        await interaction.followup.send("❌ 查價服務暫時無法使用，請稍後再試。", ephemeral=True)


async def handle_nintendo_price_query(interaction: discord.Interaction, platform: str, product_id: str):
    """Look up a catalogue-selected Nintendo digital edition by stable NSUID."""
    product_id = product_id.strip()
    if not product_id.isdigit():
        await interaction.response.send_message(
            f"❌ 請從 {SUPPORTED_PLATFORMS[platform]} 的目錄搜尋結果中選擇遊戲。",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        entry = await asyncio.to_thread(get_nintendo_game_by_id, product_id, platform)
        if entry is None:
            await interaction.followup.send(
                "❌ 找不到這個平台與 NSUID 對應的目錄項目；請重新搜尋並選擇正確版本。",
                ephemeral=True,
            )
            return
        actual_platform = entry["platform"]
        display_platform = SUPPORTED_PLATFORMS.get(actual_platform, SUPPORTED_PLATFORMS["nintendo"])
        result = await asyncio.to_thread(nintendo.get_nintendo_digital_price, product_id, "TW", "zh")
        if result is None:
            message = (
                f"🎮 **{entry['name']}**｜{display_platform} 台灣數位版\n"
                "目錄已找到遊戲，但價格介面沒有回傳對應的台灣價格紀錄。\n"
                f"{entry_url(product_id)}"
            )
        elif not result["available"] or result["current_price"] is None:
            message = (
                f"🎮 **{entry['name']}**｜{display_platform} 台灣數位版\n"
                "目前沒有可用的台灣數位售價；不會以其他地區或實體版價格代替。\n"
                f"{result['url']}"
            )
        else:
            current = result["current_price"]
            regular = result["regular_price"]
            message = (
                f"🎮 **{entry['name']}**｜{display_platform} 台灣數位版\n"
                f"目前價格：**{result['currency']} {current:,.0f}**\n"
            )
            if regular is not None and regular > current:
                discount = round((1 - current / regular) * 100)
                message += f"原價：{result['currency']} {regular:,.0f}（約 {discount}% off）\n"
            elif regular is not None:
                message += f"原價：{result['currency']} {regular:,.0f}\n"
            status_labels = {
                "onsale": "販售中",
                "on_sale": "販售中",
                "preorder": "預購中",
                "pre_order": "預購中",
            }
            status_label = status_labels.get(result["sales_status"], result["sales_status"])
            message += (
                f"狀態：{status_label}｜區域：台灣（{result['region']}）｜版本：數位版\n"
                f"來源：{result['provider']}（未公開文件化介面）\n"
                f"查詢時間：{result['retrieved_at']}\n"
                f"{result['url']}\n"
                "注意：這是數位版價格，不代表實體卡帶／零售商價格。"
            )
        if not entry["platform_verified"]:
            message += "\n⚠️ Nintendo 目錄未標註平台世代；價格紀錄對應此 NSUID，但請先確認商品版本。"
        await interaction.followup.send(message, ephemeral=True)
    except (requests.RequestException, NintendoCatalogueError, nintendo.NintendoPriceError,
            ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
        print(f"Nintendo price query failed for {platform}/{product_id}: {type(error).__name__}: {error}")
        await interaction.followup.send(
            "❌ Nintendo 查價暫時無法使用。請確認目錄快取未過期、價格介面正常，稍後再試。",
            ephemeral=True,
        )


def entry_url(product_id: str) -> str:
    return f"https://ec.nintendo.com/TW/zh/titles/{product_id}"


@tree.command(name="lookup", description="查詢遊戲目前價格或平台商店連結")
@app_commands.describe(platform="選擇遊戲平台", game="輸入遊戲名稱並從目錄／搜尋結果中選擇")
@app_commands.choices(platform=ADD_LOOKUP_PLATFORM_CHOICES)
@app_commands.autocomplete(game=platform_autocomplete)
async def lookup_command(interaction: discord.Interaction, platform: str, game: str):
    platform = platform.lower()
    query = game.strip()
    if not query:
        await interaction.response.send_message("❌ 請輸入遊戲名稱。", ephemeral=True)
        return
    if platform == "steam":
        await handle_steam_price_query(interaction, query)
        return
    if platform in ("ns", "ns2", "nintendo"):
        await handle_nintendo_price_query(interaction, platform, query)
        return
    await interaction.response.send_message("❌ 不支援的平台，請選擇 Steam、Nintendo Switch 或 Nintendo Switch 2。", ephemeral=True)


@tree.command(name="help", description="查看 Game Price Tracker 的使用說明")
async def help_command(interaction: discord.Interaction):
    message = (
        "🎮 **Game Price Tracker 使用說明**\n\n"
        "**一般指令**\n"
        "• `/ping` — 測試 Bot 是否正常運作\n"
        "• `/list` — 查看目前追蹤的遊戲（依平台分組）\n"
        "• `/lookup platform game` — 統一查詢遊戲價格；Nintendo Switch／Switch 2 使用合併搜尋\n"
        "• `/help` — 顯示使用說明\n\n"
        "**管理員限定指令**\n"
        "• `/admincheck` — 檢查管理員權限\n"
        "• `/add platform game` — 先選平台，再搜尋遊戲；Nintendo Switch／Switch 2 使用合併搜尋\n"
        "• `/remove platform game` — 依平台移除追蹤遊戲\n\n"
        "📌 /lookup 是統一查價入口：Steam 回傳台灣現價；NS／NS2 以目錄項目及 NSUID 查台灣數位版價格。PS5 不提供 Bot 自動搜尋或查價，既有手動追蹤項目仍可在清單中查看。\n"
        "📌 Nintendo 數位價格介面未公開文件化；不代表實體版價格。\n"
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
