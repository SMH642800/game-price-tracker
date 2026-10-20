import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class NintendoScheduledNotificationTests(unittest.TestCase):
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
    def config(region="TW"):
        return {
            "platform": "nintendo",
            "store": "nintendo_eshop",
            "product_id": "70010000012345",
            "region": region,
            "name": "Example Switch Game",
            "edition": "digital",
            "price_mode": "digital",
        }

    @staticmethod
    def sale():
        return {
            "provider": "Nintendo eShop price API (undocumented)",
            "title_id": "70010000012345",
            "region": "TW",
            "currency": "TWD",
            "sales_status": "onsale",
            "available": True,
            "regular_price": 1790.0,
            "discount_price": 1290.0,
            "current_price": 1290.0,
            "url": "https://ec.nintendo.com/TW/zh/titles/70010000012345",
        }

    def test_price_adapter_is_always_queried_for_taiwan_and_calculates_discount(self):
        with patch.object(main.nintendo, "get_nintendo_digital_price", return_value=self.sale()) as get_price:
            result = main.get_nintendo_price(self.config())

        get_price.assert_called_once_with(
            "70010000012345", country="TW", lang="zh"
        )
        self.assertEqual(result["currency"], "TWD")
        self.assertEqual(result["discount"], 28)
        self.assertEqual(result["current_price"], 1290.0)

    def test_non_taiwan_region_is_rejected_instead_of_using_unverified_currency(self):
        with patch.object(main.nintendo, "get_nintendo_digital_price") as get_price:
            with self.assertRaisesRegex(ValueError, "require region TW"):
                main.get_nintendo_price(self.config(region="HK"))
        get_price.assert_not_called()

    def test_unchanged_nintendo_sale_does_not_send_duplicate(self):
        config = self.config()
        self.write_watchlist([config])
        state = {
            "nintendo:nintendo_eshop:TW:70010000012345": {
                "discount": 28,
                "final_price": 1290.0,
            }
        }
        self.state_path.write_text(json.dumps(state), encoding="utf-8")

        with patch.object(main, "get_nintendo_price", return_value={
            "name": config["name"],
            "available": True,
            "currency": "TWD",
            "regular_price": 1790.0,
            "current_price": 1290.0,
            "discount": 28,
            "url": "https://ec.nintendo.com/TW/zh/titles/70010000012345",
        }), patch.object(main, "send_discord_message") as send:
            main.main()

        send.assert_not_called()
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), state)

    def test_confirmed_no_discount_clears_state(self):
        config = self.config()
        self.write_watchlist([config])
        state_key = "nintendo:nintendo_eshop:TW:70010000012345"
        self.state_path.write_text(json.dumps({
            state_key: {"discount": 28, "final_price": 1290.0}
        }), encoding="utf-8")
        regular_price = {
            "name": config["name"],
            "available": True,
            "currency": "TWD",
            "regular_price": 1790.0,
            "current_price": 1790.0,
            "discount": 0,
            "url": "https://ec.nintendo.com/TW/zh/titles/70010000012345",
        }

        with patch.object(main, "get_nintendo_price", return_value=regular_price), \
             patch.object(main, "send_discord_message") as send:
            main.main()

        send.assert_not_called()
        self.assertNotIn(state_key, json.loads(self.state_path.read_text(encoding="utf-8")))

    def test_unverified_currency_fails_closed_and_preserves_previous_state(self):
        config = self.config()
        self.write_watchlist([config])
        state_key = "nintendo:nintendo_eshop:TW:70010000012345"
        state = {state_key: {"discount": 28, "final_price": 1290.0}}
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        wrong_currency = {
            "name": config["name"],
            "available": True,
            "currency": "HKD",
            "regular_price": 1790.0,
            "current_price": 1290.0,
            "discount": 28,
            "url": "https://ec.nintendo.com/TW/zh/titles/70010000012345",
        }

        with patch.object(main, "get_nintendo_price", return_value=wrong_currency), \
             patch.object(main, "send_discord_message") as send:
            with self.assertRaises(SystemExit) as exc:
                main.main()

        self.assertEqual(exc.exception.code, 1)
        send.assert_not_called()
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), state)

    def test_missing_price_record_fails_and_preserves_previous_state(self):
        config = self.config()
        self.write_watchlist([config])
        state_key = "nintendo:nintendo_eshop:TW:70010000012345"
        state = {state_key: {"discount": 28, "final_price": 1290.0}}
        self.state_path.write_text(json.dumps(state), encoding="utf-8")

        with patch.object(main, "get_nintendo_price", return_value=None), \
             patch.object(main, "send_discord_message") as send:
            with self.assertRaises(SystemExit) as exc:
                main.main()

        self.assertEqual(exc.exception.code, 1)
        send.assert_not_called()
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), state)


if __name__ == "__main__":
    unittest.main()
