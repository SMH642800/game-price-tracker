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
        with self.assertRaises(RuntimeError):
            main.load_notification_state()

    def test_state_save_writes_valid_json(self):
        state = {"steam:steam:TW:123": {"discount": 50, "final_price": 10.0}}
        main.save_notification_state(state)
        self.assertEqual(json.loads(self.state_path.read_text(encoding="utf-8")), state)

    def test_successful_notification_state_survives_partial_failure(self):
        self.watchlist_path.write_text(json.dumps([
            {"platform": "steam", "store": "steam", "product_id": "123", "region": "TW", "name": "Game A"},
            {"platform": "steam", "store": "steam", "product_id": "456", "region": "TW", "name": "Game B"},
        ]), encoding="utf-8")

        good_price = {
            "name": "Game A",
            "currency": "TWD",
            "final_price": 10.0,
            "initial_price": 20.0,
            "discount": 50,
            "discount_expiration": None,
            "url": "https://store.steampowered.com/app/123/",
        }

        def price_side_effect(app_id, region):
            if app_id == "123":
                return good_price
            raise requests.Timeout("simulated timeout")

        with patch.object(main, "get_steam_price", side_effect=price_side_effect), \
             patch.object(main, "send_discord_message"):
            with self.assertRaises(SystemExit) as exc:
                main.main()

        self.assertEqual(exc.exception.code, 1)
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["steam:steam:TW:123"], {"discount": 50, "final_price": 10.0})


if __name__ == "__main__":
    unittest.main()
