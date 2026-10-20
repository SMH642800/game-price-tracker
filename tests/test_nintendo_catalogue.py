import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nintendo_catalogue as catalogue


class NintendoCatalogueSearchTests(unittest.TestCase):
    def test_search_matches_normalized_traditional_chinese_title(self):
        rows = [
            {"title": "薩爾達傳說 時之笛", "nsuid": "70010000000001", "platform": "Nintendo Switch"},
            {"title": "時之笛 特別版", "nsuid": "70010000000002", "platform": "Nintendo Switch"},
        ]
        result = catalogue.search_nintendo_games(" 時之笛 ", "ns", rows=rows)
        self.assertEqual([item["product_id"] for item in result], ["70010000000001", "70010000000002"])

    def test_switch_and_switch_2_are_not_mixed(self):
        rows = [
            {"title": "Example", "nsuid": "70010000000001", "platform": "Nintendo Switch"},
            {"title": "Example", "nsuid": "70010000000002", "platform": "Nintendo Switch 2"},
        ]
        self.assertEqual(
            [item["product_id"] for item in catalogue.search_nintendo_games("Example", "ns", rows=rows)],
            ["70010000000001"],
        )
        self.assertEqual(
            [item["product_id"] for item in catalogue.search_nintendo_games("Example", "ns2", rows=rows)],
            ["70010000000002"],
        )

    def test_search_deduplicates_nsuid_and_caps_at_25(self):
        rows = [
            {"title": f"Game {index:02}", "nsuid": str(70010000000000 + index), "platform": "Nintendo Switch"}
            for index in range(40)
        ]
        rows.append(rows[0].copy())
        result = catalogue.search_nintendo_games("Game", "ns", rows=rows, limit=100)
        self.assertEqual(len(result), 25)
        self.assertEqual(len({item["product_id"] for item in result}), 25)

    def test_invalid_platform_is_rejected(self):
        with self.assertRaises(ValueError):
            catalogue.search_nintendo_games("Example", "ps5", rows=[])

    def test_lookup_by_id_requires_exact_platform_and_numeric_id(self):
        rows = [
            {"title": "Switch 2 edition", "nsuid": "70010000000002", "platform": "Nintendo Switch 2"},
        ]
        self.assertIsNone(catalogue.get_nintendo_game_by_id("70010000000002", "ns", rows=rows))
        self.assertEqual(
            catalogue.get_nintendo_game_by_id("70010000000002", "ns2", rows=rows)["name"],
            "Switch 2 edition",
        )
        self.assertIsNone(catalogue.get_nintendo_game_by_id("title", "ns2", rows=rows))

    def test_expired_cache_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            cache_path = Path(temp) / "cache.json"
            cache_path.write_text(json.dumps({
                "fetched_at": 100,
                "rows": [],
            }), encoding="utf-8")
            with patch.object(catalogue, "CACHE_PATH", cache_path):
                with self.assertRaisesRegex(catalogue.NintendoCatalogueError, "過期"):
                    catalogue.load_cached_catalogue(now=100 + catalogue.CACHE_TTL_SECONDS + 1)


if __name__ == "__main__":
    unittest.main()
