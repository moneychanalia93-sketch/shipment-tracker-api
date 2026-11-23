import os
import sqlite3
import tempfile
import unittest

from tracker import db, timing
from tracker.seed import add_fake_shipments


# Tests that look straight at the database (no server).
class DatabaseTests(unittest.TestCase):
    # Make a fresh database file for each test.
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.folder.name, "test.db")
        db.init_db(self.path)
        self.conn = db.connect(self.path)

    # Close the connection first, or Windows cannot delete the file.
    def tearDown(self):
        self.conn.close()
        self.folder.cleanup()

    def test_history_rows_cannot_be_changed_or_deleted(self):
        shipment, _ = db.create_shipment(
            self.conn, {"customer": "A", "destination": "B", "promised_date": "2999-01-01"})
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("UPDATE history SET note = 'edited' WHERE shipment_id = ?", (shipment["id"],))
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("DELETE FROM history WHERE shipment_id = ?", (shipment["id"],))

    def test_history_must_point_to_a_real_shipment(self):
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_history(self.conn, 999, None, "created", "orphan")

    def test_seed_creates_the_requested_number_of_rows_with_history(self):
        add_fake_shipments(self.conn, 50)
        shipments = self.conn.execute("SELECT COUNT(*) FROM shipments").fetchone()[0]
        history = self.conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        self.assertEqual(shipments, 50)
        self.assertGreaterEqual(history, 50)

    def test_query_plan_uses_the_index_only_when_it_exists(self):
        add_fake_shipments(self.conn, 200)
        with_index = timing.plan_text(self.conn, timing.COUNT_PLAN, "cancelled")
        self.assertIn("USING", with_index)
        self.assertIn("idx_shipments_status", with_index)
        self.conn.execute(timing.DROP_INDEX)
        without_index = timing.plan_text(self.conn, timing.COUNT_PLAN, "cancelled")
        self.assertIn("SCAN", without_index)
        self.assertNotIn("idx_shipments_status", without_index)

    def test_index_makes_the_status_query_faster_on_20000_rows(self):
        add_fake_shipments(self.conn, 20_000)
        self.conn.execute(timing.DROP_INDEX)
        slow = timing.measure(self.conn, timing.COUNT_QUERY, "cancelled", repeats=10)
        self.conn.execute(timing.CREATE_INDEX)
        fast = timing.measure(self.conn, timing.COUNT_QUERY, "cancelled", repeats=10)
        self.assertLess(fast, slow)


if __name__ == "__main__":
    unittest.main()
