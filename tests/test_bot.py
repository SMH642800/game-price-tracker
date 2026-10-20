import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
