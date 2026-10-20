import unittest
from unittest.mock import AsyncMock, patch

import bot


class WatchlistUpdateTests(unittest.TestCase):
    @patch.object(bot.requests, "get")
    def test_current_price_parses_steam_price(self, get):
        response = get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {"123": {"success": True, "data": {
            "name": "Example Game",
            "price_overview": {
                "currency": "TWD", "final": 9900, "initial": 19900,
                "discount_percent": 50,
            },
        }}}
        result = bot.get_steam_current_price("123")
        self.assertEqual(result["name"], "Example Game")
        self.assertEqual(result["final_price"], 99.0)
        self.assertEqual(result["discount"], 50)
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["params"]["cc"], "tw")

    @patch.object(bot.requests, "get")
    def test_current_price_handles_no_price_data_without_inventing_price(self, get):
        response = get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {"123": {"success": True, "data": {
            "name": "Free or unavailable game",
        }}}
        result = bot.get_steam_current_price("123")
        self.assertFalse(result["price_available"])
        self.assertNotIn("final_price", result)

    @patch.object(bot.requests, "get")
    def test_missing_or_non_twd_currency_is_not_reported_as_taiwan_price(self, get):
        for currency in (None, "JPY"):
            with self.subTest(currency=currency):
                response = get.return_value
                response.raise_for_status.return_value = None
                price = {"final": 9900, "initial": 9900, "discount_percent": 0}
                if currency is not None:
                    price["currency"] = currency
                response.json.return_value = {"123": {"success": True, "data": {
                    "name": "Example Game", "price_overview": price,
                }}}
                result = bot.get_steam_current_price("123")
                self.assertFalse(result["price_available"])
                self.assertNotIn("final_price", result)

    def test_invalid_steam_id_is_rejected_before_request(self):
        with patch.object(bot.requests, "get") as get:
            with self.assertRaisesRegex(ValueError, "digits only"):
                bot.get_steam_current_price("not-an-id")
        get.assert_not_called()

    @patch.object(bot.requests, "get")
    def test_malformed_steam_api_payload_is_rejected(self, get):
        response = get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = []
        with self.assertRaisesRegex(ValueError, "JSON object"):
            bot.get_steam_current_price("123")

    @patch.object(bot.requests, "get")
    def test_malformed_steam_price_fields_are_rejected(self, get):
        response = get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {"123": {"success": True, "data": {
            "name": "Example Game",
            "price_overview": {"currency": "TWD", "final": "bad", "initial": 100},
        }}}
        with self.assertRaisesRegex(ValueError, "malformed price fields"):
            bot.get_steam_current_price("123")

    @patch.object(bot.requests, "get")
    def test_steam_search_rejects_unexpected_payload_shape(self, get):
        response = get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = []
        with self.assertRaisesRegex(ValueError, "JSON object"):
            bot.search_steam_games("Example")

    def test_ps5_is_not_offered_in_add_lookup_or_remove_choices(self):
        add_lookup = {choice.value for choice in bot.ADD_LOOKUP_PLATFORM_CHOICES}
        remove = {choice.value for choice in bot.REMOVE_PLATFORM_CHOICES}
        self.assertEqual(add_lookup, {"steam", "nintendo"})
        self.assertEqual(remove, {"steam", "nintendo"})
        self.assertEqual(bot.SUPPORTED_PLATFORMS["ps5"], "PlayStation 5")

    def test_nintendo_lookup_uses_one_unified_platform_choice(self):
        self.assertEqual(bot.SUPPORTED_PLATFORMS["nintendo"], "Nintendo Switch／Switch 2")
        values = {choice.value for choice in bot.ADD_LOOKUP_PLATFORM_CHOICES}
        self.assertEqual(values, {"steam", "nintendo"})

    def test_history_and_separate_price_commands_are_not_registered(self):
        self.assertIsNone(bot.tree.get_command("history"))
        self.assertIsNone(bot.tree.get_command("price_history"))
        self.assertIsNone(bot.tree.get_command("price"))
        self.assertIsNotNone(bot.tree.get_command("lookup"))

    @patch.object(bot, "github_headers", return_value={"Accept": "application/vnd.github+json"})
    @patch.object(bot.requests, "put")
    @patch.object(bot, "fetch_github_watchlist_with_sha")
    def test_add_mutation_writes_updated_list(self, fetch_watchlist, put, _headers):
        original = [
            {"platform": "steam", "product_id": "1", "name": "Existing"}
        ]
        fetch_watchlist.return_value = (original.copy(), "current-sha")
        response = put.return_value
        response.status_code = 200
        response.raise_for_status.return_value = None

        def add_game(games):
            games.append({"platform": "steam", "product_id": "2", "name": "New"})
            return games, True

        result = bot.update_github_watchlist(add_game)

        self.assertTrue(result)
        put.assert_called_once()
        payload = put.call_args.kwargs["json"]
        self.assertEqual(payload["branch"], bot.GITHUB_BRANCH)
        import base64
        import json
        written = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
        self.assertEqual([game["product_id"] for game in written], ["1", "2"])

    @patch.object(bot, "github_headers", return_value={"Accept": "application/vnd.github+json"})
    @patch.object(bot.requests, "get")
    def test_watchlist_read_uses_configured_branch(self, get, _headers):
        import base64
        import json
        response = get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "content": base64.b64encode(b"[]").decode("ascii"),
            "sha": "watchlist-sha",
        }
        with patch.object(bot, "GITHUB_BRANCH", "feature/stability-price-history-commands"):
            games, sha = bot.fetch_github_watchlist_with_sha()
        self.assertEqual(games, [])
        self.assertEqual(sha, "watchlist-sha")
        self.assertEqual(
            get.call_args.kwargs["params"],
            {"ref": "feature/stability-price-history-commands"},
        )

    @patch.object(bot, "github_headers", return_value={"Accept": "application/vnd.github+json"})
    @patch.object(bot.requests, "put")
    @patch.object(bot, "fetch_github_watchlist_with_sha")
    def test_duplicate_add_does_not_write(self, fetch_watchlist, put, _headers):
        original = [{"platform": "steam", "product_id": "1", "name": "Existing"}]
        fetch_watchlist.return_value = (original.copy(), "current-sha")

        def duplicate(games):
            return games, False

        result = bot.update_github_watchlist(duplicate)
        self.assertFalse(result)
        put.assert_not_called()

    @patch.object(bot, "github_headers", return_value={"Accept": "application/vnd.github+json"})
    @patch.object(bot.requests, "put")
    @patch.object(bot, "fetch_github_watchlist_with_sha")
    def test_nested_mutation_is_detected_and_persisted(self, fetch_watchlist, put, _headers):
        original = [{"platform": "steam", "product_id": "1", "metadata": {"enabled": True}}]
        fetch_watchlist.return_value = (original, "current-sha")
        put.return_value.status_code = 200
        put.return_value.raise_for_status.return_value = None

        def mutate(games):
            games[0]["metadata"]["enabled"] = False
            return games, True

        self.assertTrue(bot.update_github_watchlist(mutate))
        put.assert_called_once()
        import base64
        import json
        written = json.loads(base64.b64decode(
            put.call_args.kwargs["json"]["content"]
        ).decode("utf-8"))
        self.assertFalse(written[0]["metadata"]["enabled"])

    @patch.object(bot, "github_headers", return_value={"Accept": "application/vnd.github+json"})
    @patch.object(bot.requests, "put")
    @patch.object(bot, "fetch_github_watchlist_with_sha")
    def test_github_422_validation_error_is_not_retried_as_a_conflict(
        self, fetch_watchlist, put, _headers
    ):
        fetch_watchlist.return_value = (
            [{"platform": "steam", "product_id": "1", "name": "Existing"}],
            "current-sha",
        )
        response = put.return_value
        response.status_code = 422
        response.raise_for_status.side_effect = bot.requests.HTTPError("validation failed")

        def mutate(games):
            games.append({"platform": "steam", "product_id": "2", "name": "New"})
            return games, True

        with self.assertRaises(bot.requests.HTTPError):
            bot.update_github_watchlist(mutate)
        self.assertEqual(fetch_watchlist.call_count, 1)
        self.assertEqual(put.call_count, 1)

    @patch.object(bot, "github_headers", return_value={"Accept": "application/vnd.github+json"})
    @patch.object(bot.requests, "put")
    @patch.object(bot, "fetch_github_watchlist_with_sha")
    @patch.object(bot.time, "sleep")
    def test_watchlist_update_retries_sha_conflict(self, sleep, fetch_watchlist, put, _headers):
        first = [{"platform": "steam", "product_id": "1", "name": "Existing"}]
        second = [{"platform": "steam", "product_id": "1", "name": "Existing"}]
        fetch_watchlist.side_effect = [(first, "old-sha"), (second, "new-sha")]
        put.side_effect = [
            type("Conflict", (), {
                "status_code": 409,
                "raise_for_status": lambda self: None,
            })(),
            type("Success", (), {
                "status_code": 200,
                "raise_for_status": lambda self: None,
            })(),
        ]

        def add_game(games):
            games.append({"platform": "steam", "product_id": "2", "name": "New"})
            return games, True

        self.assertTrue(bot.update_github_watchlist(add_game))
        self.assertEqual(fetch_watchlist.call_count, 2)
        self.assertEqual(put.call_count, 2)
        sleep.assert_called_once()

class NintendoCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_nintendo_autocomplete_returns_catalogue_ids_not_raw_query(self):
        interaction = AsyncMock()
        interaction.namespace.platform = "ns"
        with patch.object(bot, "search_nintendo_games", return_value=[
            {"name": "薩爾達傳說 時之笛", "product_id": "70010000012345", "platform": "ns", "platform_verified": True}
        ]) as search:
            choices = await bot.platform_autocomplete(interaction, "時之笛")
        search.assert_called_once_with("時之笛", "ns")
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0].value, "70010000012345")
        self.assertIn("Nintendo Switch", choices[0].name)

    async def test_nintendo_lookup_renders_digital_price_and_source_caveat(self):
        interaction = AsyncMock()
        entry = {"name": "時之笛", "product_id": "70010000012345", "platform": "ns", "platform_verified": True}
        price = {
            "available": True, "current_price": 1290.0, "regular_price": 1790.0,
            "discount_price": 1290.0, "currency": "TWD", "region": "TW",
            "sales_status": "onsale",
            "provider": "Nintendo eShop price API (undocumented)",
            "retrieved_at": "2026-10-20T00:00:00+00:00",
            "url": "https://ec.nintendo.com/TW/zh/titles/70010000012345",
        }
        with patch.object(bot, "get_nintendo_game_by_id", return_value=entry), \
             patch.object(bot.nintendo, "get_nintendo_digital_price", return_value=price):
            await bot.handle_nintendo_price_query(interaction, "ns", "70010000012345")
        interaction.response.defer.assert_awaited_once()
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("TWD 1,290", message)
        self.assertIn("TWD 1,790", message)
        self.assertIn("數位版", message)
        self.assertIn("未公開文件化介面", message)
        self.assertIn("不代表實體卡帶", message)

    async def test_probe_confirmed_ocarina_nsuid_displays_taiwan_preorder_price(self):
        interaction = AsyncMock()
        entry = {
            "name": "薩爾達傳說 時之笛",
            "product_id": "70010000130795",
            "platform": "ns2",
            "platform_verified": False,
        }
        price = {
            "available": True, "current_price": 1880.0, "regular_price": 1880.0,
            "discount_price": None, "currency": "TWD", "region": "TW",
            "provider": "Nintendo eShop price API (undocumented)",
            "sales_status": "preorder",
            "retrieved_at": "2026-10-20T00:00:00+00:00",
            "url": "https://ec.nintendo.com/TW/zh/titles/70010000130795",
        }
        with patch.object(bot, "get_nintendo_game_by_id", return_value=entry), \
             patch.object(bot.nintendo, "get_nintendo_digital_price", return_value=price):
            await bot.handle_nintendo_price_query(interaction, "ns2", "70010000130795")
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("TWD 1,880", message)
        self.assertIn("預購中", message)
        self.assertIn("台灣數位版", message)
        self.assertNotIn("目錄未標註平台世代", message)
        self.assertIn("70010000130795", message)

    async def test_nintendo_lookup_does_not_invent_price_for_missing_record(self):
        interaction = AsyncMock()
        entry = {"name": "時之笛", "product_id": "70010000012345", "platform": "ns", "platform_verified": True}
        with patch.object(bot, "get_nintendo_game_by_id", return_value=entry), \
             patch.object(bot.nintendo, "get_nintendo_digital_price", return_value=None):
            await bot.handle_nintendo_price_query(interaction, "ns", "70010000012345")
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("沒有回傳對應的台灣價格紀錄", message)
        self.assertNotIn("目前價格：", message)


class CommandRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_steam_lookup_uses_shared_price_handler(self):
        interaction = AsyncMock()
        with patch.object(bot, "handle_steam_price_query", new_callable=AsyncMock) as handler:
            await bot.lookup_command.callback(interaction, "steam", "123")
        handler.assert_awaited_once_with(interaction, "123")
        interaction.response.send_message.assert_not_awaited()

    async def test_lookup_rejects_removed_ps5_query(self):
        interaction = AsyncMock()
        await bot.lookup_command.callback(interaction, "ps5", "Final Fantasy XVI")
        interaction.response.send_message.assert_awaited_once()
        self.assertIn("不支援的平台", interaction.response.send_message.await_args.args[0])

    async def test_nintendo_lookup_routes_to_catalogue_price_handler(self):
        interaction = AsyncMock()
        with patch.object(bot, "handle_nintendo_price_query", new_callable=AsyncMock) as handler:
            await bot.lookup_command.callback(interaction, "ns", "70010000012345")
        handler.assert_awaited_once_with(interaction, "ns", "70010000012345")
        interaction.response.send_message.assert_not_awaited()

    async def test_ns2_lookup_routes_to_its_own_platform_handler(self):
        interaction = AsyncMock()
        with patch.object(bot, "handle_nintendo_price_query", new_callable=AsyncMock) as handler:
            await bot.lookup_command.callback(interaction, "ns2", "70010000012345")
        handler.assert_awaited_once_with(interaction, "ns2", "70010000012345")

    async def test_steam_lookup_always_returns_error_message_for_bad_api_payload(self):
        interaction = AsyncMock()
        with patch.object(bot, "get_steam_current_price", side_effect=ValueError("bad payload")):
            await bot.handle_steam_price_query(interaction, "123")
        interaction.response.defer.assert_awaited_once()
        interaction.followup.send.assert_awaited_once()
        self.assertIn("查價服務暫時無法使用", interaction.followup.send.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
