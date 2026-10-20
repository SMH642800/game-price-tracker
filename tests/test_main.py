import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
import main


class NotificationStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.state_path = root / "notification_state.json"
        self.watchlist_path = root / "games_track_list.json"
        self.state_path.write_text("{}", encoding="utf-8")
        main.STATE_PATH = self.state_path
        main.WATCHLIST_PATH = self.watchlist_path

    def write_watchlist(self, games):
        self.watchlist_path.write_text(
            json.dumps(games, ensure_ascii=False), encoding="utf-8"
        )

    @staticmethod
    def discounted_game(name="Example Game", price=10.0, discount=50):
        return {
            "name": name,
            "currency": "TWD",
            "final_price": price,
            "initial_price": 20.0,
            "discount": discount,
            "discount_expiration": None,
            "url": "https://store.steampowered.com/app/123/",
        }

    def test_legacy_steam_state_key_is_migrated(self):
        self.state_path.write_text(
            json.dumps({"1794680": {"discount": 25, "final_price": 82.0}}),
            encoding="utf-8",
        )
        state = main.load_notification_state()
        self.assertEqual(
            state["steam:steam:TW:1794680"],
            {"discount": 25, "final_price": 82.0},
        )

    def test_corrupt_state_fails_closed(self):
        self.state_path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
            main.load_notification_state()

    def test_non_object_state_fails_closed(self):
        self.state_path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "JSON object"):
            main.load_notification_state()

    def test_state_save_writes_valid_json(self):
        state = {"steam:steam:TW:123": {"discount": 50, "final_price": 10.0}}
        main.save_notification_state(state)
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), state)

    def test_new_discount_sends_notification_and_persists_state(self):
        self.write_watchlist([{
            "platform": "steam", "store": "steam", "product_id": "123",
            "region": "TW", "name": "Example Game",
        }])
        game = self.discounted_game()
        with patch.object(main, "get_steam_price", return_value=game), \
             patch.object(main, "send_discord_message") as send:
            main.main()

        send.assert_called_once()
        self.assertIn("特價通知", send.call_args.args[0])
        self.assertIn("TWD 10.00", send.call_args.args[0])
        self.assertEqual(
            json.loads(self.state_path.read_text(encoding="utf-8")),
            {"steam:steam:TW:123": {"discount": 50, "final_price": 10.0}},
        )

    def test_unchanged_discount_does_not_send_duplicate_notification(self):
        self.write_watchlist([{
            "platform": "steam", "store": "steam", "product_id": "123",
            "region": "TW", "name": "Example Game",
        }])
        state = {"steam:steam:TW:123": {"discount": 50, "final_price": 10.0}}
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        with patch.object(main, "get_steam_price", return_value=self.discounted_game()), \
             patch.object(main, "send_discord_message") as send:
            main.main()
        send.assert_not_called()
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), state)

    def test_changed_discount_or_price_sends_a_new_notification(self):
        self.write_watchlist([{
            "platform": "steam", "store": "steam", "product_id": "123",
            "region": "TW", "name": "Example Game",
        }])
        self.state_path.write_text(json.dumps({
            "steam:steam:TW:123": {"discount": 50, "final_price": 10.0}
        }), encoding="utf-8")
        changed = self.discounted_game(price=8.0, discount=60)
        with patch.object(main, "get_steam_price", return_value=changed), \
             patch.object(main, "send_discord_message") as send:
            main.main()
        send.assert_called_once()
        self.assertEqual(
            json.loads(self.state_path.read_text(encoding="utf-8"))["steam:steam:TW:123"],
            {"discount": 60, "final_price": 8.0},
        )

    def test_ended_discount_clears_state_so_a_future_sale_can_notify(self):
        self.write_watchlist([{
            "platform": "steam", "store": "steam", "product_id": "123",
            "region": "TW", "name": "Example Game",
        }])
        self.state_path.write_text(json.dumps({
            "steam:steam:TW:123": {"discount": 50, "final_price": 10.0}
        }), encoding="utf-8")
        with patch.object(main, "get_steam_price", return_value=self.discounted_game(discount=0)), \
             patch.object(main, "send_discord_message") as send:
            main.main()
        send.assert_not_called()
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), {})

    def test_link_only_entries_are_skipped_and_nintendo_digital_sale_notifies(self):
        self.write_watchlist([
            {
                "platform": "ps5", "store": "link_only", "product_id": "game a",
                "region": "TW", "name": "Console Game", "price_mode": "links_only",
            },
            {
                "platform": "ns", "store": "link_only", "product_id": "game b",
                "region": "TW", "name": "Switch Link-only Game", "price_mode": "links_only",
            },
            {
                "platform": "ns2", "store": "nintendo_eshop", "product_id": "70010000012345",
                "region": "TW", "name": "Switch 2 Digital Game", "edition": "digital",
                "price_mode": "digital",
            },
        ])
        nintendo_game = {
            "name": "Switch 2 Digital Game",
            "available": True,
            "currency": "TWD",
            "regular_price": 1790.0,
            "current_price": 1290.0,
            "discount": 28,
            "url": "https://ec.nintendo.com/TW/zh/titles/70010000012345",
        }
        with patch.object(main, "get_steam_price") as get_steam_price, \
             patch.object(main, "get_nintendo_price", return_value=nintendo_game) as get_nintendo_price, \
             patch.object(main, "send_discord_message") as send:
            main.main()
        get_steam_price.assert_not_called()
        get_nintendo_price.assert_called_once()
        send.assert_called_once()
        message = send.call_args.args[0]
        self.assertIn("Nintendo Switch 特價通知", message)
        self.assertIn("TWD 1,290", message)
        self.assertIn("TWD 1,790", message)
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["ns2:nintendo_eshop:TW:70010000012345"],
            {"discount": 28, "final_price": 1290.0},
        )

    def test_successful_notification_state_survives_partial_failure(self):
        self.write_watchlist([
            {"platform": "steam", "store": "steam", "product_id": "123", "region": "TW", "name": "Game A"},
            {"platform": "steam", "store": "steam", "product_id": "456", "region": "TW", "name": "Game B"},
        ])

        def price_side_effect(app_id, region):
            if app_id == "123":
                return self.discounted_game(name="Game A")
            raise requests.Timeout("simulated timeout")

        with patch.object(main, "get_steam_price", side_effect=price_side_effect), \
             patch.object(main, "send_discord_message"):
            with self.assertRaises(SystemExit) as exc:
                main.main()

        self.assertEqual(exc.exception.code, 1)
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["steam:steam:TW:123"], {"discount": 50, "final_price": 10.0})

    def test_stale_state_is_removed_for_any_steam_region(self):
        self.write_watchlist([{
            "platform": "steam", "store": "steam", "product_id": "123",
            "region": "JP", "name": "Example Game",
        }])
        self.state_path.write_text(json.dumps({
            "steam:steam:TW:gone": {"discount": 10, "final_price": 1},
            "steam:steam:JP:123": {"discount": 50, "final_price": 10.0},
        }), encoding="utf-8")
        with patch.object(main, "get_steam_price", return_value=self.discounted_game()), \
             patch.object(main, "send_discord_message") as send:
            main.main()
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertNotIn("steam:steam:TW:gone", saved)
        self.assertEqual(saved["steam:steam:JP:123"], {"discount": 50, "final_price": 10.0})
        send.assert_not_called()

    def test_invalid_watchlist_shape_fails_before_network_calls(self):
        self.watchlist_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        with patch.object(main, "get_steam_price") as get_price:
            with self.assertRaisesRegex(RuntimeError, "JSON array"):
                main.main()
        get_price.assert_not_called()



class SteamPriceParsingTests(unittest.TestCase):
    @patch.object(main.requests, "get")
    @patch.object(main, "get_steam_discount_expiration", return_value=None)
    def test_parses_current_price_and_uses_requested_region(self, _expiration, get):
        response = get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {"123": {"success": True, "data": {
            "name": "Example Game",
            "price_overview": {
                "currency": "JPY",
                "final": 9900,
                "initial": 19900,
                "discount_percent": 50,
                "discount_expiration": 1799999999,
            },
        }}}

        result = main.get_steam_price("123", "JP")

        self.assertEqual(result["final_price"], 99.0)
        self.assertEqual(result["initial_price"], 199.0)
        self.assertEqual(result["discount"], 50)
        self.assertEqual(result["discount_expiration"], 1799999999)
        self.assertEqual(get.call_args.kwargs["params"]["cc"], "jp")
        _expiration.assert_not_called()

    @patch.object(main.requests, "get")
    def test_malformed_steam_response_shape_is_rejected(self, get):
        response = get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = []

        with self.assertRaisesRegex(ValueError, "JSON object"):
            main.get_steam_price("123")

    @patch.object(main.requests, "get")
    def test_price_record_without_currency_is_rejected(self, get):
        response = get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {"123": {"success": True, "data": {
            "name": "Example Game",
            "price_overview": {
                "final": 9900, "initial": 9900, "discount_percent": 0,
            },
        }}}
        self.assertIsNone(main.get_steam_price("123"))

    @patch.object(main.requests, "get")
    def test_missing_price_overview_returns_no_price(self, get):
        response = get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {"123": {"success": True, "data": {
            "name": "Unavailable Game",
        }}}

        self.assertIsNone(main.get_steam_price("123"))


if __name__ == "__main__":
    unittest.main()
