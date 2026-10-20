import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import probe_nintendo_sources as probe


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class NintendoCatalogueRefreshTests(unittest.TestCase):
    def test_incomplete_pagination_does_not_write_or_replace_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            cache_path = Path(temp) / "catalogue.json"
            session = Mock()
            session.get.side_effect = [
                FakeResponse({
                    "total": 25,
                    "items": [
                        {"title": f"Game {index}", "nsuid": str(70010000000000 + index)}
                        for index in range(24)
                    ],
                }),
                FakeResponse({"items": []}),
            ]
            with patch.object(probe.time, "sleep"):
                with self.assertRaisesRegex(ValueError, "Incomplete catalogue"):
                    probe.load_catalogue(
                        session,
                        cache_path=cache_path,
                        refresh_cache=True,
                        catalogue_url="https://example.invalid/catalogue",
                    )
            self.assertFalse(cache_path.exists())

    def test_complete_catalogue_is_written_to_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            cache_path = Path(temp) / "catalogue.json"
            session = Mock()
            session.get.return_value = FakeResponse({
                "total": 1,
                "items": [{"title": "Example", "nsuid": "70010000000001"}],
            })
            rows, summary = probe.load_catalogue(
                session,
                cache_path=cache_path,
                refresh_cache=True,
                catalogue_url="https://example.invalid/catalogue",
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(summary["rows_received"], 1)
            self.assertTrue(cache_path.exists())


if __name__ == "__main__":
    unittest.main()
