import unittest
from unittest.mock import Mock

import requests

import steam


class SteamProviderTests(unittest.TestCase):
    def make_session(self, payload):
        session = Mock()
        response = session.get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return session

    def test_normalizes_price_and_preserves_requested_region(self):
        session = self.make_session({"123": {"success": True, "data": {
            "name": "Example",
            "price_overview": {
                "currency": "TWD", "final": 9900, "initial": 19900,
                "discount_percent": 50, "discount_expiration": 1799999999,
            },
        }}})
        result = steam.get_price("123", session=session)
        self.assertEqual(result["final_price"], 99.0)
        self.assertEqual(result["currency"], "TWD")
        self.assertEqual(result["discount"], 50)
        self.assertEqual(
            session.get.call_args.kwargs["params"],
            {"appids": "123", "cc": "tw", "l": "tchinese"},
        )

    def test_missing_or_wrong_taiwan_currency_never_produces_numeric_price(self):
        for currency in (None, "JPY"):
            with self.subTest(currency=currency):
                price = {"final": 9900, "initial": 9900, "discount_percent": 0}
                if currency is not None:
                    price["currency"] = currency
                session = self.make_session({"123": {"success": True, "data": {
                    "name": "Example", "price_overview": price,
                }}})
                result = steam.get_price("123", session=session)
                self.assertFalse(result["price_available"])
                self.assertNotIn("final_price", result)

    def test_currency_must_match_known_requested_region(self):
        session = self.make_session({"123": {"success": True, "data": {
            "name": "Example",
            "price_overview": {
                "currency": "TWD", "final": 9900, "initial": 9900,
                "discount_percent": 0,
            },
        }}})
        result = steam.get_price("123", region="JP", session=session)
        self.assertFalse(result["price_available"])
        self.assertNotIn("final_price", result)

    def test_malformed_price_fields_fail_closed(self):
        session = self.make_session({"123": {"success": True, "data": {
            "name": "Example",
            "price_overview": {
                "currency": "TWD", "final": True, "initial": 1000,
                "discount_percent": 0,
            },
        }}})
        with self.assertRaisesRegex(ValueError, "malformed price fields"):
            steam.get_price("123", session=session)

    def test_bad_response_shape_is_rejected(self):
        session = self.make_session([])
        with self.assertRaisesRegex(ValueError, "JSON object"):
            steam.get_price("123", session=session)

    def test_invalid_app_id_is_rejected_before_network_call(self):
        session = Mock()
        with self.assertRaisesRegex(ValueError, "digits only"):
            steam.get_price("abc", session=session)
        session.get.assert_not_called()

    def test_search_returns_only_records_with_valid_ids_and_names(self):
        session = self.make_session({"items": [
            {"id": 123, "name": "Example"},
            {"id": "456", "name": "Another"},
            {"id": "bad", "name": "Invalid ID"},
            {"id": "789", "name": ""},
            "malformed",
        ]})
        result = steam.search_games("Example", session=session)
        self.assertEqual(result, [
            {"product_id": "123", "name": "Example"},
            {"product_id": "456", "name": "Another"},
        ])

    def test_http_errors_propagate(self):
        session = Mock()
        session.get.return_value.raise_for_status.side_effect = requests.Timeout("timeout")
        with self.assertRaises(requests.Timeout):
            steam.get_price("123", session=session)


if __name__ == "__main__":
    unittest.main()
