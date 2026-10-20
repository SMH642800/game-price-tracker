import unittest
from unittest.mock import Mock, patch

from scripts import probe_nintendo_sources as probe


class NintendoSourceProbeTests(unittest.TestCase):
    def test_normalizes_fullwidth_and_punctuation_for_search(self):
        rows = [
            {"title": "薩爾達傳說 時之笛", "nsuid": "70010000000001"},
            {"title": "亰都幻都－櫻花幻舞－", "nsuid": "70010000000002"},
            {"title": "Mario Kart World", "nsuid": "70010000000003"},
        ]
        self.assertEqual(len(probe.matching_rows(rows, "時之笛")), 1)
        self.assertEqual(len(probe.matching_rows(rows, "亰都幻都")), 1)
        self.assertEqual(len(probe.matching_rows(rows, "Kyoto Xanadu")), 0)

    def test_empty_query_never_matches_everything(self):
        self.assertEqual(probe.matching_rows([{"title": "Example"}], "  "), [])

    @patch.object(probe.time, "sleep")
    def test_catalogue_pages_are_loaded_sequentially_and_schema_checked(self, _sleep):
        session = Mock()
        first = session.get.return_value
        first.raise_for_status.return_value = None
        first.json.return_value = {
            "total": 25,
            "items": [{"title": "Game A", "nsuid": "70010000000001"}],
        }
        second_response = Mock()
        second_response.raise_for_status.return_value = None
        second_response.json.return_value = {
            "total": 25,
            "items": [{"title": "Game B", "nsuid": "70010000000002"}],
        }
        session.get.side_effect = [first, second_response]

        rows, summary = probe.load_catalogue(session, cache_path=None)

        self.assertEqual([row["title"] for row in rows], ["Game A", "Game B"])
        self.assertEqual(summary["pages_requested"], 2)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(session.get.call_args_list[0].kwargs["params"]["spage"], 1)
        self.assertEqual(session.get.call_args_list[1].kwargs["params"]["spage"], 2)

    def test_price_request_only_uses_numeric_nsuid_and_expected_region(self):
        session = Mock()
        response = session.get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {"prices": [{
            "title_id": "70010000000001",
            "sales_status": "onsale",
        }]}

        result = probe.get_prices(session, [
            {"title": "Game A", "nsuid": "70010000000001"},
            {"title": "Bad ID", "nsuid": "not-an-id"},
            {"title": "Duplicate", "nsuid": "70010000000001"},
        ])

        self.assertEqual(result["requested_ids"], ["70010000000001"])
        self.assertEqual(
            session.get.call_args.kwargs["params"],
            {"country": "TW", "lang": "zh", "ids": "70010000000001"},
        )

    def test_price_schema_mismatch_fails_closed(self):
        session = Mock()
        session.get.return_value.raise_for_status.return_value = None
        session.get.return_value.json.return_value = {"unexpected": []}
        with self.assertRaises(ValueError):
            probe.get_prices(session, [{"nsuid": "70010000000001"}])


if __name__ == "__main__":
    unittest.main()
