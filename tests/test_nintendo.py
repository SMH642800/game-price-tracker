import unittest
from unittest.mock import Mock

import requests

import nintendo


class NintendoDigitalPriceTests(unittest.TestCase):
    def make_session(self, payload):
        session = Mock()
        response = session.get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return session

    def test_parses_taiwan_discount_price_and_uses_stable_id(self):
        session = self.make_session({
            "prices": [{
                "title_id": "70010000012345",
                "sales_status": "onsale",
                "regular_price": {
                    "currency": "TWD", "raw_value": 1790, "formatted_value": "NT$1,790",
                },
                "discount_price": {
                    "currency": "TWD", "raw_value": 1290, "formatted_value": "NT$1,290",
                },
            }]
        })

        result = nintendo.get_nintendo_digital_price(
            "70010000012345", session=session
        )

        self.assertEqual(result["current_price"], 1290.0)
        self.assertEqual(result["regular_price"], 1790.0)
        self.assertEqual(result["discount_price"], 1290.0)
        self.assertEqual(result["currency"], "TWD")
        self.assertEqual(result["region"], "TW")
        self.assertEqual(result["title_id"], "70010000012345")
        self.assertIn("/TW/zh/titles/70010000012345", result["url"])
        self.assertEqual(session.get.call_args.kwargs["params"], {
            "country": "TW", "lang": "zh", "ids": "70010000012345",
        })


    def test_missing_currency_does_not_infer_twd_from_region(self):
        session = self.make_session({"prices": [{
            "title_id": "70010000012345",
            "sales_status": "onsale",
            "regular_price": {"raw_value": 1290},
        }]})
        result = nintendo.get_nintendo_digital_price(
            "70010000012345", country="TW", session=session
        )
        self.assertTrue(result["available"])
        self.assertIsNone(result["currency"])
        self.assertIsNone(result["regular_price"])
        self.assertIsNone(result["current_price"])

    def test_currency_must_match_requested_region(self):
        session = self.make_session({"prices": [{
            "title_id": "70010000012345",
            "sales_status": "onsale",
            "regular_price": {"currency": "JPY", "raw_value": 1290},
        }]})
        result = nintendo.get_nintendo_digital_price(
            "70010000012345", country="TW", session=session
        )
        self.assertEqual(result["currency"], "JPY")
        self.assertIsNone(result["discount_price"])
        self.assertIsNone(result["current_price"])

    def test_invalid_negative_or_non_finite_amounts_are_not_used(self):
        for raw_value in (-1, float("inf"), float("nan"), True):
            with self.subTest(raw_value=raw_value):
                session = self.make_session({"prices": [{
                    "title_id": "70010000012345",
                    "sales_status": "onsale",
                    "regular_price": {"currency": "TWD", "raw_value": raw_value},
                }]})
                result = nintendo.get_nintendo_digital_price(
                    "70010000012345", country="TW", session=session
                )
                self.assertIsNone(result["regular_price"])
                self.assertIsNone(result["current_price"])

    def test_conflicting_regular_and_discount_currencies_fail_closed(self):
        session = self.make_session({"prices": [{
            "title_id": "70010000012345",
            "sales_status": "onsale",
            "regular_price": {"currency": "TWD", "raw_value": 1790},
            "discount_price": {"currency": "JPY", "raw_value": 1290},
        }]})
        result = nintendo.get_nintendo_digital_price(
            "70010000012345", country="TW", session=session
        )
        self.assertIsNone(result["current_price"])

    def test_does_not_match_a_different_title_id(self):
        session = self.make_session({"prices": [{
            "title_id": "70010000099999",
            "sales_status": "onsale",
            "regular_price": {"currency": "TWD", "raw_value": 500},
        }]})
        self.assertIsNone(nintendo.get_nintendo_digital_price(
            "70010000012345", session=session
        ))

    def test_explicit_not_for_sale_status_has_no_numeric_current_price(self):
        session = self.make_session({"prices": [{
            "title_id": "70010000012345",
            "sales_status": "not_for_sale",
            "regular_price": {"currency": "JPY", "raw_value": 6500},
        }]})
        result = nintendo.get_nintendo_digital_price(
            "70010000012345", country="JP", lang="ja", session=session
        )
        self.assertFalse(result["available"])
        self.assertIsNone(result["current_price"])
        self.assertEqual(result["currency"], "JPY")
        self.assertIn("/JP/ja/titles/", result["url"])

    def test_does_not_fall_back_to_japan_implicitly(self):
        session = self.make_session({"prices": []})
        result = nintendo.get_nintendo_digital_price(
            "70010000012345", country="TW", session=session
        )
        self.assertIsNone(result)
        self.assertEqual(session.get.call_count, 1)
        self.assertEqual(session.get.call_args.kwargs["params"]["country"], "TW")

    def test_invalid_ids_regions_and_languages_are_rejected_before_request(self):
        session = Mock()
        for args, kwargs in [
            (("not-an-id",), {}),
            (("123",), {"country": "US"}),
            (("123",), {"lang": "zh-TW"}),
        ]:
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    nintendo.get_nintendo_digital_price(*args, session=session, **kwargs)
        session.get.assert_not_called()

    def test_http_errors_propagate(self):
        session = Mock()
        session.get.return_value.raise_for_status.side_effect = requests.Timeout("timeout")
        with self.assertRaises(requests.Timeout):
            nintendo.get_nintendo_digital_price("70010000012345", session=session)

    def test_malformed_json_and_schema_fail_closed(self):
        session = Mock()
        session.get.return_value.raise_for_status.return_value = None
        session.get.return_value.json.side_effect = ValueError("bad json")
        with self.assertRaises(nintendo.NintendoPriceError):
            nintendo.get_nintendo_digital_price("70010000012345", session=session)

        session.get.return_value.json.side_effect = None
        session.get.return_value.json.return_value = {"items": []}
        with self.assertRaises(nintendo.NintendoPriceError):
            nintendo.get_nintendo_digital_price("70010000012345", session=session)


if __name__ == "__main__":
    unittest.main()
