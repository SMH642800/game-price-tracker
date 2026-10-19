
import os
import json
import requests

import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ADMIN_ID = os.getenv("DISCORD_ADMIN_ID")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = "SMH642800/game-price-tracker"
GITHUB_FILE_PATH = "games_track_list.json"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


WATCHLIST_FILE = "games_track_list.json"

def load_watchlist():
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as file:
        return json.load(file)
    

def load_github_watchlist():
    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
    )

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )
    response.raise_for_status()

    import base64
    import json

    content = base64.b64decode(
        response.json()["content"]
    ).decode("utf-8")

    return json.loads(content)


def save_github_watchlist(games):
    import base64
    import json

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
    )
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    # 取得目前檔案的 SHA，GitHub 更新檔案時需要它
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    sha = response.json()["sha"]

    content = json.dumps(
        games,
        ensure_ascii=False,
        indent=2,
    )

    response = requests.put(
        url,
        headers=headers,
        json={
            "message": "Update tracked games via Discord bot",
            "content": base64.b64encode(
                content.encode("utf-8")
            ).decode("ascii"),
            "sha": sha,
        },
        timeout=15,
    )
    response.raise_for_status()


def get_steam_game(app_id: str):
    url = "https://store.steampowered.com/api/appdetails"

    response = requests.get(
        url,
        params={
            "appids": app_id,
            "l": "english",
        },
        timeout=15,
    )
    response.raise_for_status()

    result = response.json().get(app_id, {})

    if not result.get("success"):
        return None

    data = result.get("data", {})
    if not data.get("name"):
        return None

    return data["name"]


def search_steam_games(query: str):
    url = "https://store.steampowered.com/api/storesearch/"

    response = requests.get(
        url,
        params={
            "term": query,
            "l": "tchinese",
            "cc": "tw",
        },
        timeout=15,
    )
    response.raise_for_status()

    data = response.json()
    results = []

    for game in data.get("items", [])[:25]:
        app_id = str(game.get("id", ""))
        name = game.get("name", "")

        if app_id.isdigit() and name:
            results.append({
                "app_id": app_id,
                "name": name,
            })

    return results


def is_admin(user: discord.abc.User) -> bool:
    """確認使用者是否為指定管理員。"""
    return ADMIN_ID is not None and str(user.id) == ADMIN_ID


@tree.command(
    name="ping",
    description="測試 Game Price Tracker Bot 是否正常運作",
)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🏓 Pong！Game Price Tracker Bot 正常運作。",
        ephemeral=True,
    )


@tree.command(
    name="admincheck",
    description="檢查自己是否具有 Bot 管理員權限",
)
async def admincheck(interaction: discord.Interaction):
    if is_admin(interaction.user):
        message = "✅ 你已通過管理員驗證。"
    else:
        message = "⛔ 你沒有 Bot 管理員權限。"

    await interaction.response.send_message(
        message,
        ephemeral=True,
    )



@tree.command(
    name="list",
    description="查看目前追蹤的遊戲",
)
async def list_games(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        games = load_github_watchlist()

        embed = discord.Embed(
            title="🎮 遊戲追蹤清單",
            description=f"目前共追蹤 **{len(games)}** 款遊戲",
            color=discord.Color.blurple(),
        )

        if not games:
            embed.description = "目前沒有追蹤任何遊戲。"

        else:
            platform_names = {
                "steam": "Steam",
                "ns2": "Nintendo Switch 2",
                "ps5": "PlayStation 5",
            }

            grouped_games = {}

            for game in games:
                platform = str(
                    game.get("platform", "unknown")
                ).lower()

                grouped_games.setdefault(platform, []).append(game)

            for platform, platform_games in grouped_games.items():
                platform_name = platform_names.get(
                    platform,
                    platform.upper(),
                )

                embed.add_field(
                    name=f"🕹️ {platform_name}（{len(platform_games)} 款）",
                    value="\u200b",
                    inline=False,
                )

                for index, game in enumerate(platform_games, start=1):
                    name = game.get("name", "未知遊戲")
                    app_id = game.get("app_id")

                    details = f"**{index}. {name}**"

                    if platform == "steam" and app_id:
                        details += f"\nApp ID：`{app_id}`"

                    embed.add_field(
                        name="\u200b",
                        value=details,
                        inline=False,
                    )

        embed.set_footer(text="Game Price Tracker")

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    except requests.RequestException:
        await interaction.followup.send(
            "❌ 暫時無法連線至 GitHub，請稍後再試。",
            ephemeral=True,
        )
    except (ValueError, KeyError, TypeError):
        await interaction.followup.send(
            "❌ 遊戲清單格式有誤，請檢查 GitHub 上的 JSON 檔案。",
            ephemeral=True,
        )



async def add_game_autocomplete(
    interaction: discord.Interaction,
    current: str,
):
    if not is_admin(interaction.user) or not current.strip():
        return []

    try:
        games = await __import__("asyncio").to_thread(
            search_steam_games,
            current.strip(),
        )

        return [
            app_commands.Choice(
                name=f"{game['name']} (ID: {game['app_id']})"[:100],
                value=game["app_id"],
            )
            for game in games[:25]
        ]

    except (requests.RequestException, ValueError, KeyError, TypeError):
        return []
    

async def remove_game_autocomplete(
    interaction: discord.Interaction,
    current: str,
):
    if not is_admin(interaction.user):
        return []

    try:
        games = await __import__("asyncio").to_thread(
            load_github_watchlist,
        )

        query = current.strip().casefold()
        choices = []

        for game in games:
            if game.get("platform") != "steam":
                continue

            app_id = str(game.get("app_id", ""))
            name = str(game.get("name", ""))

            if not app_id.isdigit() or not name:
                continue

            if query and query not in name.casefold() and query not in app_id:
                continue

            choices.append(
                app_commands.Choice(
                    name=f"{name} (ID: {app_id})"[:100],
                    value=app_id,
                )
            )

        return choices[:25]

    except (
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
    ):
        return []


@tree.command(
    name="add",
    description="新增要追蹤的 Steam 遊戲（管理員限定）",
)
@app_commands.describe(
    game_name="搜尋並選擇要追蹤的 Steam 遊戲",
)
@app_commands.autocomplete(game_name=add_game_autocomplete)
async def add_game(
    interaction: discord.Interaction,
    game_name: str,
):
    app_id = game_name
    if not is_admin(interaction.user):
        await interaction.response.send_message(
            "⛔ 你沒有 Bot 管理員權限。",
            ephemeral=True,
        )
        return

    app_id = app_id.strip()

    if not app_id.isdigit():
        await interaction.response.send_message(
            f"❌ 請從 Steam 搜尋結果中選擇有效的遊戲。",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        steam_name = get_steam_game(app_id)

        if steam_name is None:
            await interaction.followup.send(
                f"❌ Steam 查不到 App ID `{app_id}`，請確認 ID 是否正確。",
                ephemeral=True,
            )
            return

        games = load_github_watchlist()

        if any(
            game.get("platform") == "steam"
            and str(game.get("app_id")) == app_id
            for game in games
        ):
            await interaction.followup.send(
                "⚠️ 這款遊戲已經在追蹤清單中。",
                ephemeral=True,
            )
            return

        games.append({
            "platform": "steam",
            "app_id": app_id,
            "name": steam_name,
        })

        save_github_watchlist(games)

        await interaction.followup.send(
            f"✅ 已新增 **{steam_name}**（App ID：`{app_id}`）到 GitHub 遊戲清單。",
            ephemeral=True,
        )

    except requests.RequestException:
        await interaction.followup.send(
            "❌ GitHub 連線或更新失敗，請檢查 Token 權限及網路。",
            ephemeral=True,
        )
    except (ValueError, KeyError, TypeError):
        await interaction.followup.send(
            "❌ 讀取遊戲清單時發生資料格式錯誤，尚未確認更新成功。",
            ephemeral=True,
        )


@tree.command(
    name="remove",
    description="移除追蹤的 Steam 遊戲（管理員限定）",
)
@app_commands.describe(
    game="選擇 Watch List 中已追蹤的遊戲",
)
@app_commands.autocomplete(game=remove_game_autocomplete)
async def remove_game(
    interaction: discord.Interaction,
    game: str,
):
    app_id = game
    if not is_admin(interaction.user):
        await interaction.response.send_message(
            "⛔ 你沒有 Bot 管理員權限。",
            ephemeral=True,
        )
        return

    app_id = app_id.strip()

    if not app_id.isdigit():
        await interaction.response.send_message(
            "❌ 請輸入有效的 Steam App ID。",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        games = load_github_watchlist()

        removed_games = [
            game for game in games
            if (
                game.get("platform") == "steam"
                and str(game.get("app_id")) == app_id
            )
        ]

        remaining_games = [
            game for game in games
            if not (
                game.get("platform") == "steam"
                and str(game.get("app_id")) == app_id
            )
        ]

        if len(remaining_games) == len(games):
            await interaction.followup.send(
                f"⚠️ 找不到 App ID 為 `{app_id}` 的追蹤遊戲。",
                ephemeral=True,
            )
            return

        save_github_watchlist(remaining_games)

        removed_name = removed_games[0].get("name", "未知遊戲")

        await interaction.followup.send(
            f"✅ 已移除 **{removed_name}**（App ID：`{app_id}`）。",
            ephemeral=True,
        )

    except requests.RequestException:
        await interaction.followup.send(
            "❌ GitHub 連線或更新失敗，請檢查 Token 權限及網路。",
            ephemeral=True,
        )
    except (ValueError, KeyError, TypeError):
        await interaction.followup.send(
            "❌ 讀取遊戲清單時發生資料格式錯誤。",
            ephemeral=True,
        )


@tree.command(
    name="help",
    description="查看 Game Price Tracker 的使用說明",
)
async def help_command(interaction: discord.Interaction):
    message = (
        "🎮 **Game Price Tracker 使用說明**\n\n"
        "**一般指令**\n"
        "• `/ping` — 測試 Bot 是否正常運作\n"
        "• `/list` — 查看目前追蹤的 Steam 遊戲\n"
        "• `/help` — 顯示這份使用說明\n\n"
        "**管理員限定指令**\n"
        "• `/admincheck` — 檢查管理員權限\n"
        "• `/add game_name` — 新增追蹤遊戲\n"
        "• `/remove game_name` — 移除追蹤遊戲\n\n"
        "📌 新增遊戲時，請使用正確的 Steam App ID。\n"
        "📌 遊戲清單儲存在 GitHub，供每日自動查價流程使用。"
    )

    await interaction.response.send_message(
        message,
        ephemeral=True,
    )


@client.event
async def on_ready():
    guild = discord.Object(id=int(GUILD_ID))
    tree.copy_global_to(guild=guild)
    synced = await tree.sync(guild=guild)

    print(f"已登入 Discord：{client.user}")
    print(f"已同步 {len(synced)} 個斜線指令到指定伺服器。")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError(
            "找不到 DISCORD_BOT_TOKEN，請檢查 .env 檔案。"
        )
    
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "找不到 GITHUB_TOKEN，請檢查 .env 檔案。"
        )

    if not ADMIN_ID or not ADMIN_ID.isdigit():
        raise RuntimeError(
            "DISCORD_ADMIN_ID 尚未正確設定，請檢查 .env 檔案。"
        )
    
    if not GUILD_ID or not GUILD_ID.isdigit():
        raise RuntimeError(
            "DISCORD_GUILD_ID 尚未正確設定，請檢查 .env 檔案。"
        )

    client.run(TOKEN)
