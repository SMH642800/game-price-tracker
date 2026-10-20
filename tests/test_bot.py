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

    def test_console_store_links_are_platform_specific_and_encoded(self):
        ps5 = bot.platform_store_links("ps5", "Final Fantasy XVI")
        ns2 = bot.platform_store_links("ns2", "Mario Kart World")
        self.assertIn("store.playstation.com/zh-hant-tw/search/Final+Fantasy+XVI", ps5["store"])
        self.assertIn("google.com/search?q=", ps5["price_search"])
        self.assertEqual(ns2["store"], "https://store.nintendo.com.tw/")
        self.assertIn("Mario+Kart+World", ns2["price_search"])

    def test_link_only_product_key_is_normalized(self):
        self.assertEqual(bot.platform_product_key("  Mario   Kart World "), "mario kart world")
        with self.assertRaises(ValueError):
            bot.platform_product_key("   ")

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
        import base64
        import json
        written = json.loads(base64.b64decode(payload["content"]).decode("utf-8"))
        self.assertEqual([game["product_id"] for game in written], ["1", "2"])

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


class CommandRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_steam_lookup_uses_shared_price_handler(self):
        interaction = AsyncMock()
        with patch.object(bot, "handle_steam_price_query", new_callable=AsyncMock) as handler:
            await bot.lookup_command.callback(interaction, "steam", "123")
        handler.assert_awaited_once_with(interaction, "123")
        interaction.response.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
