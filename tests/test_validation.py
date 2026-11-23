import unittest

from tracker.errors import ApiError
from tracker.validation import (check_event, check_idempotency_key, check_list_params,
                                check_new_shipment, is_real_date)

GOOD = {"customer": "Acme", "destination": "Austin", "promised_date": "2026-12-31"}


# Tests for the input checks (no server, no database).
class ValidationTests(unittest.TestCase):
    # Helper: the call must fail with a 400 error.
    def assert_400(self, function, *args):
        with self.assertRaises(ApiError) as context:
            function(*args)
        self.assertEqual(context.exception.code, 400)

    def test_good_shipment_passes_and_text_is_trimmed(self):
        data = check_new_shipment({**GOOD, "customer": "  Acme  ", "extra": "ignored"})
        self.assertEqual(data, {**GOOD, "customer": "Acme"})

    def test_missing_blank_or_non_text_customer_is_rejected(self):
        self.assert_400(check_new_shipment, {"destination": "A", "promised_date": "2026-12-31"})
        self.assert_400(check_new_shipment, {**GOOD, "customer": "   "})
        self.assert_400(check_new_shipment, {**GOOD, "customer": 42})

    def test_too_long_destination_is_rejected(self):
        self.assert_400(check_new_shipment, {**GOOD, "destination": "x" * 201})

    def test_body_that_is_not_an_object_is_rejected(self):
        for body in (None, [], "text", 5):
            self.assert_400(check_new_shipment, body)

    def test_dates_must_be_real_and_written_yyyy_mm_dd(self):
        self.assertTrue(is_real_date("2026-02-28"))
        for bad in ("2026-02-30", "2026-1-5", "20261231", "31-12-2026", "", None, 20261231):
            self.assertFalse(is_real_date(bad), bad)

    def test_bad_date_in_a_shipment_is_rejected(self):
        self.assert_400(check_new_shipment, {**GOOD, "promised_date": "tomorrow"})

    def test_event_needs_a_known_status_and_a_short_note(self):
        self.assertEqual(check_event({"status": "packed", "note": " ok "}), ("packed", "ok"))
        self.assertEqual(check_event({"status": "packed"}), ("packed", ""))
        self.assert_400(check_event, {"status": "lost"})
        self.assert_400(check_event, {})
        self.assert_400(check_event, {"status": "packed", "note": "x" * 201})

    def test_list_params_have_defaults_and_limits(self):
        self.assertEqual(check_list_params({}), (None, 20))
        self.assertEqual(check_list_params({"status": "packed", "limit": "5"}), ("packed", 5))
        for bad_limit in ("0", "101", "-1", "abc", "2.5"):
            self.assert_400(check_list_params, {"limit": bad_limit})
        self.assert_400(check_list_params, {"status": "lost"})

    def test_idempotency_key_rules(self):
        self.assertIsNone(check_idempotency_key(None))
        self.assertEqual(check_idempotency_key(" abc "), "abc")
        self.assert_400(check_idempotency_key, "   ")
        self.assert_400(check_idempotency_key, "k" * 101)
