import threading
import unittest

from tests.helpers import GOOD, ServerTestCase

KEY = {"Idempotency-Key": "order-1001"}


# Tests for the Idempotency-Key header on POST /shipments.
class IdempotencyTests(ServerTestCase):
    def test_retry_with_same_key_returns_the_first_shipment(self):
        first_code, first = self.call("POST", "/shipments", GOOD, KEY)
        retry_code, retry = self.call("POST", "/shipments", GOOD, KEY)
        self.assertEqual((first_code, retry_code), (201, 200))
        self.assertEqual(first, retry)
        self.assertEqual(self.call("GET", "/stats")[1]["total"], 1)

    def test_retry_does_not_add_a_second_history_line(self):
        self.call("POST", "/shipments", GOOD, KEY)
        self.call("POST", "/shipments", GOOD, KEY)
        history = self.call("GET", "/shipments/1/history")[1]["history"]
        self.assertEqual(len(history), 1)

    def test_different_keys_or_no_key_create_separate_shipments(self):
        self.call("POST", "/shipments", GOOD, {"Idempotency-Key": "a"})
        self.call("POST", "/shipments", GOOD, {"Idempotency-Key": "b"})
        self.call("POST", "/shipments", GOOD)
        self.call("POST", "/shipments", GOOD)
        self.assertEqual(self.call("GET", "/stats")[1]["total"], 4)

    def test_empty_key_is_rejected(self):
        code, _ = self.call("POST", "/shipments", GOOD, {"Idempotency-Key": "   "})
        self.assertEqual(code, 400)

    def test_five_requests_at_once_with_the_same_key_make_one_shipment(self):
        ids = []
        def send():
            ids.append(self.call("POST", "/shipments", GOOD, KEY)[1]["id"])
        threads = [threading.Thread(target=send) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(ids, [1] * 5)
        self.assertEqual(self.call("GET", "/stats")[1]["total"], 1)


if __name__ == "__main__":
    unittest.main()
