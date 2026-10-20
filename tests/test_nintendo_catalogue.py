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

    def test_switch_and_switch_2_are_included_in_all_nintendo_search_modes(self):
        rows = [
            {"title": "Example Original", "nsuid": "70010000000001", "platform": "Nintendo Switch"},
            {"title": "Example Nintendo Switch 2 Edition", "nsuid": "70010000000002", "platform": "Nintendo Switch 2"},
        ]
        expected = ["70010000000001", "70010000000002"]
        for platform in ("nintendo", "ns", "ns2"):
            with self.subTest(platform=platform):
                self.assertEqual(
                    [item["product_id"] for item in catalogue.search_nintendo_games("Example", platform, rows=rows)],
                    expected,
                )

    def test_missing_platform_metadata_is_returned_but_marked_unverified(self):
        rows = [
            {"title": "薩爾達傳說 時之笛", "nsuid": "70010000130795", "platform": None},
            {"title": "Kyoto Xanadu NS2 Edition", "nsuid": "70010000130796", "platform": None},
        ]
        ns_results = catalogue.search_nintendo_games("時之笛", "ns", rows=rows)
        ns2_results = catalogue.search_nintendo_games("時之笛", "ns2", rows=rows)
        self.assertEqual(ns_results[0]["product_id"], "70010000130795")
        self.assertFalse(ns_results[0]["platform_verified"])
        self.assertEqual(ns2_results[0]["product_id"], "70010000130795")
        self.assertFalse(ns2_results[0]["platform_verified"])
        for platform in ("nintendo", "ns", "ns2"):
            with self.subTest(platform=platform):
                self.assertEqual(
                    catalogue.search_nintendo_games("Kyoto", platform, rows=rows)[0]["product_id"],
                    "70010000130796",
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

    def test_unified_nintendo_search_returns_both_generations_and_unknown_platform(self):
        rows = [
            {"title": "Example Original", "nsuid": "70010000000001", "platform": "Nintendo Switch"},
            {"title": "Example Switch 2 Edition", "nsuid": "70010000000002", "platform": "Nintendo Switch 2"},
            {"title": "Example Unverified", "nsuid": "70010000000003", "platform": None},
        ]
        result = catalogue.search_nintendo_games("Example", "nintendo", rows=rows)
        self.assertEqual([item["product_id"] for item in result], [
            "70010000000001", "70010000000002", "70010000000003",
        ])
        self.assertEqual([item["platform"] for item in result], ["nintendo", "nintendo", "nintendo"])
        self.assertFalse(result[2]["platform_verified"])

    def test_curated_fallback_finds_missing_trails_in_the_sky_ordinary_switch_edition(self):
        results = catalogue.search_nintendo_games("空之軌跡 the 2nd", "nintendo", rows=[])
        self.assertEqual(
            results,
            [{
                "product_id": "70010000128495",
                "name": "空之軌跡 the 2nd",
                "platform": "nintendo",
                "platform_verified": True,
            }],
        )
        self.assertEqual(
            catalogue.search_nintendo_games("空之軌跡 the 2nd", "ns", rows=[])[0]["product_id"],
            "70010000128495",
        )
        self.assertEqual(
            catalogue.search_nintendo_games("空之軌跡 the 2nd", "ns2", rows=[])[0]["product_id"],
            "70010000128495",
        )

    def test_curated_fallback_lookup_by_id_works_without_bulk_catalogue_row(self):
        entry = catalogue.get_nintendo_game_by_id("70010000128495", "ns", rows=[])
        self.assertIsNotNone(entry)
        self.assertEqual(entry["name"], "空之軌跡 the 2nd")
        self.assertEqual(entry["platform"], "nintendo")
        self.assertEqual(catalogue.get_nintendo_game_by_id("70010000128495", "ns2", rows=[])["product_id"], "70010000128495")

    def test_hk_catalogue_supplements_search_after_tw_and_tw_wins_duplicate_ids(self):
        tw_rows = [
            {"title": "Example Taiwan title", "nsuid": "70010000000011", "platform": "Nintendo Switch"},
        ]
        hk_rows = [
            {"title": "Example conflicting HK title", "nsuid": "70010000000011", "platform": "Nintendo Switch", "catalogue_source": "HK"},
            {"title": "Example HK-only edition", "nsuid": "70010000000012", "platform": "Nintendo Switch 2", "catalogue_source": "HK"},
        ]
        result = catalogue.search_nintendo_games(
            "Example", "nintendo", rows=tw_rows, hk_rows=hk_rows,
        )
        self.assertEqual([item["product_id"] for item in result], [
            "70010000000011", "70010000000012",
        ])
        self.assertEqual(result[0]["name"], "Example Taiwan title")
        self.assertEqual(result[1]["name"], "Example HK-only edition")

    def test_lookup_by_id_falls_back_to_hk_when_tw_has_no_match(self):
        hk_rows = [
            {"title": "HK-only edition", "nsuid": "70010000000013", "platform": "Nintendo Switch", "catalogue_source": "HK"},
        ]
        entry = catalogue.get_nintendo_game_by_id(
            "70010000000013", "nintendo", rows=[], hk_rows=hk_rows,
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["name"], "HK-only edition")
        self.assertEqual(entry["product_id"], "70010000000013")

    def test_lookup_by_id_prefers_tw_over_hk_for_duplicate_id(self):
        tw_rows = [
            {"title": "Taiwan title", "nsuid": "70010000000014", "platform": "Nintendo Switch"},
        ]
        hk_rows = [
            {"title": "Hong Kong title", "nsuid": "70010000000014", "platform": "Nintendo Switch", "catalogue_source": "HK"},
        ]
        entry = catalogue.get_nintendo_game_by_id(
            "70010000000014", "nintendo", rows=tw_rows, hk_rows=hk_rows,
        )
        self.assertEqual(entry["name"], "Taiwan title")

    def test_curated_entry_deduplicates_if_bulk_catalogue_later_adds_same_id(self):
        rows = [{
            "title": "空之軌跡 the 2nd",
            "nsuid": "70010000128495",
            "platform": "Nintendo Switch",
        }]
        result = catalogue.search_nintendo_games("空之軌跡 the 2nd", "nintendo", rows=rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["product_id"], "70010000128495")

    def test_invalid_platform_is_rejected(self):
        with self.assertRaises(ValueError):
            catalogue.search_nintendo_games("Example", "ps5", rows=[])

    def test_lookup_by_id_accepts_any_nintendo_selector_but_requires_numeric_id(self):
        rows = [
            {"title": "Switch 2 edition", "nsuid": "70010000000002", "platform": "Nintendo Switch 2"},
        ]
        for platform in ("nintendo", "ns", "ns2"):
            with self.subTest(platform=platform):
                self.assertEqual(
                    catalogue.get_nintendo_game_by_id("70010000000002", platform, rows=rows)["name"],
                    "Switch 2 edition",
                )
        self.assertIsNone(catalogue.get_nintendo_game_by_id("title", "ns2", rows=rows))

    def test_catalogue_cache_lifetime_covers_weekly_refresh_interval(self):
        self.assertEqual(catalogue.CACHE_TTL_SECONDS, 8 * 24 * 60 * 60)

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
