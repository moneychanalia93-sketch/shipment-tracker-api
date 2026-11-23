import unittest

from tests.helpers import GOOD, ServerTestCase


# Tests for every endpoint, through real HTTP calls to a real server.
class EndpointTests(ServerTestCase):
    def test_create_returns_201_and_the_new_shipment(self):
        code, shipment = self.call("POST", "/shipments", GOOD)
        self.assertEqual(code, 201)
        self.assertEqual(shipment["id"], 1)
        self.assertEqual(shipment["status"], "created")
        self.assertEqual(shipment["customer"], "Acme Corp")

    def test_create_with_invalid_fields_returns_400_json_error(self):
        code, body = self.call("POST", "/shipments", {**GOOD, "promised_date": "soon"})
        self.assertEqual(code, 400)
        self.assertIn("promised_date", body["error"])

    def test_create_with_broken_body_returns_400(self):
        self.assertEqual(self.call("POST", "/shipments", raw=b"{not json")[0], 400)
        self.assertEqual(self.call("POST", "/shipments", raw=b"[1, 2]")[0], 400)
        self.assertEqual(self.call("POST", "/shipments")[0], 400)
        self.assertEqual(self.call("POST", "/shipments", raw=b"x" * 10_001)[0], 400)

    def test_get_one_returns_the_shipment(self):
        made = self.make_shipment()
        code, found = self.call("GET", f"/shipments/{made['id']}")
        self.assertEqual(code, 200)
        self.assertEqual(found, made)

    def test_get_missing_or_non_numeric_id_returns_404(self):
        self.assertEqual(self.call("GET", "/shipments/999")[0], 404)
        self.assertEqual(self.call("GET", "/shipments/abc")[0], 404)

    def test_unknown_path_and_wrong_method_return_404_json(self):
        code, body = self.call("GET", "/nothing-here")
        self.assertEqual(code, 404)
        self.assertEqual(body, {"error": "not found"})
        self.assertEqual(self.call("POST", "/stats", {})[0], 404)

    def test_list_returns_newest_first_with_a_count(self):
        for name in ("A", "B", "C"):
            self.make_shipment(customer=name)
        code, body = self.call("GET", "/shipments")
        self.assertEqual(code, 200)
        self.assertEqual(body["count"], 3)
        self.assertEqual([s["customer"] for s in body["shipments"]], ["C", "B", "A"])

    def test_list_filters_by_status(self):
        first = self.make_shipment()
        self.make_shipment()
        self.move(first["id"], "packed")
        _, body = self.call("GET", "/shipments?status=packed")
        self.assertEqual([s["id"] for s in body["shipments"]], [first["id"]])

    def test_list_respects_limit(self):
        for _ in range(5):
            self.make_shipment()
        _, body = self.call("GET", "/shipments?limit=2")
        self.assertEqual(body["count"], 2)

    def test_list_with_bad_status_or_limit_returns_400(self):
        self.assertEqual(self.call("GET", "/shipments?status=lost")[0], 400)
        self.assertEqual(self.call("GET", "/shipments?limit=0")[0], 400)
        self.assertEqual(self.call("GET", "/shipments?limit=abc")[0], 400)

    def test_event_moves_the_shipment_to_the_new_status(self):
        shipment = self.make_shipment()
        code, updated = self.move(shipment["id"], "packed", "boxed at dock 3")
        self.assertEqual(code, 201)
        self.assertEqual(updated["status"], "packed")
        self.assertEqual(self.call("GET", f"/shipments/{shipment['id']}")[1]["status"], "packed")

    def test_invalid_move_returns_409_and_changes_nothing(self):
        shipment = self.make_shipment()
        code, body = self.move(shipment["id"], "delivered")
        self.assertEqual(code, 409)
        self.assertIn("cannot move from created to delivered", body["error"])
        self.assertEqual(self.call("GET", f"/shipments/{shipment['id']}")[1]["status"], "created")

    def test_cannot_cancel_after_shipping_or_move_after_delivery(self):
        shipment = self.make_shipment()
        for status in ("packed", "shipped"):
            self.move(shipment["id"], status)
        self.assertEqual(self.move(shipment["id"], "cancelled")[0], 409)
        self.assertEqual(self.move(shipment["id"], "delivered")[0], 201)
        self.assertEqual(self.move(shipment["id"], "packed")[0], 409)

    def test_event_with_unknown_status_or_missing_shipment(self):
        shipment = self.make_shipment()
        self.assertEqual(self.move(shipment["id"], "lost")[0], 400)
        self.assertEqual(self.move(999, "packed")[0], 404)

    def test_history_lists_every_change_in_order_and_skips_failed_moves(self):
        shipment = self.make_shipment()
        self.move(shipment["id"], "shipped")  # rejected: must not appear
        self.move(shipment["id"], "packed", "boxed")
        self.move(shipment["id"], "shipped")
        code, body = self.call("GET", f"/shipments/{shipment['id']}/history")
        self.assertEqual(code, 200)
        steps = [(h["from_status"], h["to_status"]) for h in body["history"]]
        self.assertEqual(steps, [(None, "created"), ("created", "packed"), ("packed", "shipped")])
        self.assertEqual(body["history"][1]["note"], "boxed")

    def test_history_of_missing_shipment_returns_404(self):
        self.assertEqual(self.call("GET", "/shipments/999/history")[0], 404)

    def test_stats_counts_each_status_and_late_shipments(self):
        self.make_shipment(promised_date="2020-01-01")          # late
        cancelled = self.make_shipment(promised_date="2020-01-01")  # past date but cancelled
        self.make_shipment()                                     # future date
        self.move(cancelled["id"], "cancelled")
        code, stats = self.call("GET", "/stats")
        self.assertEqual(code, 200)
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["by_status"]["created"], 2)
        self.assertEqual(stats["by_status"]["cancelled"], 1)
        self.assertEqual(stats["by_status"]["delivered"], 0)
        self.assertEqual(stats["late"], 1)

    def test_sql_injection_text_is_stored_as_plain_text(self):
        evil = "x'); DROP TABLE shipments; --"
        shipment = self.make_shipment(customer=evil)
        self.assertEqual(self.call("GET", f"/shipments/{shipment['id']}")[1]["customer"], evil)
        self.assertEqual(self.call("GET", "/shipments?status=%27%20OR%201%3D1%20--")[0], 400)
        self.assertEqual(self.call("GET", "/stats")[1]["total"], 1)


if __name__ == "__main__":
    unittest.main()
