import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import scripts.probe_nintendo_sources as probe


class NintendoSourceProbeTests(unittest.TestCase):
    def make_response(self, payload):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    def test_matching_rows_deduplicates_by_nsuid_but_keeps_editions(self):
        rows = [
            {"title": "亰都幻都 -櫻花幻舞-", "nsuid": "70010000123318"},
            {"title": "亰都幻都 -櫻花幻舞-", "nsuid": "70010000123318"},
            {"title": "亰都幻都 -櫻花幻舞- Nintendo Switch 2 Edition", "nsuid": "70010000130930"},
        ]

        matches = probe.matching_rows(rows, "亰都幻都")

        self.assertEqual(len(matches), 2)
        self.assertEqual({row["nsuid"] for row in matches}, {
            "70010000123318", "70010000130930",
        })

    def test_catalogue_fetch_writes_cache_and_next_run_uses_it(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "catalogue.json"
            session = Mock()
            session.get.side_effect = [
                self.make_response({
                    "total": 25,
                    "items": [
                        {"title": "Game A", "nsuid": "70010000000001"},
                        *[{"title": f"Filler {index}", "nsuid": str(70010000001000 + index)} for index in range(23)],
                    ],
                }),
                self.make_response({
                    "items": [
                        {"title": "Game B", "nsuid": "70010000000002"},
                        {"title": "Game B duplicate", "nsuid": "70010000000002"},
                    ],
                }),
            ]

            with patch.object(probe.time, "sleep"):
                rows, summary = probe.load_catalogue(session, cache_path=cache_path)

            self.assertEqual(len(rows), 26)
            self.assertEqual(summary["pages_requested"], 2)
            self.assertEqual(summary["unique_nsuid_count"], 25)
            self.assertEqual(summary["duplicate_nsuid_rows"], 1)
            self.assertFalse(summary["cache_hit"])
            self.assertTrue(cache_path.exists())
            self.assertEqual(session.get.call_count, 2)

            cached_rows, cached_summary = probe.load_catalogue(
                Mock(), cache_path=cache_path
            )
            self.assertEqual(cached_rows, rows)
            self.assertTrue(cached_summary["cache_hit"])
            self.assertEqual(cached_summary["rows_received"], 26)

    def test_hk_catalogue_probe_uses_hk_catalogue_url_but_keeps_taiwan_price_region(self):
        session = Mock()
        response = self.make_response({
            "total": 0,
            "items": [],
        })
        session.get.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "hk.json"
            rows, summary = probe.load_catalogue(
                session,
                cache_path=cache_path,
                refresh_cache=True,
                catalogue_url=probe.CATALOG_URLS["HK"],
            )
        self.assertEqual(rows, [])
        self.assertEqual(session.get.call_args.args[0], "https://www.nintendo.com/hk/api/software")
        self.assertEqual(probe.get_prices(Mock(), []), {"requested_ids": [], "prices": []})

    def test_refresh_cache_bypasses_existing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "catalogue.json"
            cache_path.write_text(json.dumps({
                "schema_version": probe.CACHE_SCHEMA_VERSION,
                "fetched_at": probe.time.time(),
                "summary": {"reported_total": 0, "pages_requested": 1, "rows_received": 0},
                "rows": [],
            }), encoding="utf-8")
            session = Mock()
            session.get.return_value = self.make_response({
                "total": 0,
                "items": [{"title": "Fresh result", "nsuid": "70010000000003"}],
            })

            rows, summary = probe.load_catalogue(
                session, cache_path=cache_path, refresh_cache=True
            )

            self.assertEqual(rows[0]["title"], "Fresh result")
            self.assertFalse(summary["cache_hit"])
            session.get.assert_called_once()

    def test_no_cache_option_does_not_read_or_write_cache(self):
        session = Mock()
        session.get.return_value = self.make_response({
            "total": 0, "items": [],
        })
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "should-not-exist.json"
            rows, summary = probe.load_catalogue(session, cache_path=None)
            self.assertEqual(rows, [])
            self.assertFalse(cache_path.exists())
            self.assertFalse(summary["cache_hit"])

    def test_catalogue_page_safety_cap_still_rejects_extreme_page_count(self):
        session = Mock()
        session.get.return_value = self.make_response({
            "total": probe.PAGE_SIZE * (probe.MAX_PAGES + 1),
            "items": [],
        })
        with self.assertRaisesRegex(ValueError, "safety cap is 1000"):
            probe.load_catalogue(session, cache_path=None)
        session.get.assert_called_once()

    def test_catalogue_above_warning_threshold_warns_but_continues(self):
        session = Mock()
        total = probe.PAGE_SIZE * (probe.WARNING_PAGES + 1)
        def response_for_page(*args, **kwargs):
            page = kwargs["params"]["spage"]
            start = (page - 1) * probe.PAGE_SIZE
            return self.make_response({
                "total": total,
                "items": [
                    {"title": f"Game {index}", "nsuid": str(70010000000000 + index)}
                    for index in range(start, min(start + probe.PAGE_SIZE, total))
                ],
            })
        session.get.side_effect = response_for_page
        with patch.object(probe.time, "sleep"):
            with self.assertWarnsRegex(RuntimeWarning, "warning threshold of 800"):
                rows, summary = probe.load_catalogue(session, cache_path=None)
        self.assertEqual(summary["pages_requested"], probe.WARNING_PAGES + 1)
        self.assertEqual(len(rows), total)
        self.assertEqual(session.get.call_count, probe.WARNING_PAGES + 1)

    def test_malformed_page_schema_fails_closed(self):
        session = Mock()
        session.get.side_effect = [
            self.make_response({"total": 25, "items": []}),
            self.make_response({"unexpected": []}),
        ]
        with patch.object(probe.time, "sleep"):
            with self.assertRaisesRegex(ValueError, "page 2"):
                probe.load_catalogue(session, cache_path=None)


if __name__ == "__main__":
    unittest.main()
