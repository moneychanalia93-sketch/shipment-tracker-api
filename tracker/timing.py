"""Measure the status query with and without the index: python -m tracker.timing"""

import os
import tempfile
import time

from tracker import db
from tracker.seed import add_fake_shipments

# The two queries we time. The first is the one GET /shipments?status= runs.
# The second is a count, like the one behind GET /stats.
LIST_QUERY = "SELECT * FROM shipments WHERE status = ? ORDER BY id DESC LIMIT 20"
COUNT_QUERY = "SELECT COUNT(*) FROM shipments WHERE status = ?"
LIST_PLAN = "EXPLAIN QUERY PLAN SELECT * FROM shipments WHERE status = ? ORDER BY id DESC LIMIT 20"
COUNT_PLAN = "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM shipments WHERE status = ?"

DROP_INDEX = "DROP INDEX IF EXISTS idx_shipments_status"
CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status)"


# Average milliseconds for one run of `sql`. We run it `repeats` times in a
# row and take the best of `rounds` rounds, so a random slow moment
# (another program waking up) does not spoil the number.
def measure(conn, sql, status, repeats=20, rounds=5):
    best = None
    for _ in range(rounds):
        start = time.perf_counter()
        for _ in range(repeats):
            conn.execute(sql, (status,)).fetchall()
        elapsed = (time.perf_counter() - start) / repeats * 1000
        best = elapsed if best is None else min(best, elapsed)
    return best


# What SQLite says it will do for a query: scan every row, or use an index.
def plan_text(conn, plan_sql, status):
    rows = conn.execute(plan_sql, (status,)).fetchall()
    return rows[0]["detail"]


# Time both queries for one status, once without and once with the index.
def compare(conn, label, status):
    print(f"  status = {status} ({label})")
    for name, sql, plan_sql in [("list  ", LIST_QUERY, LIST_PLAN),
                                ("count ", COUNT_QUERY, COUNT_PLAN)]:
        conn.execute(DROP_INDEX)
        slow = measure(conn, sql, status)
        slow_plan = plan_text(conn, plan_sql, status)
        conn.execute(CREATE_INDEX)
        fast = measure(conn, sql, status)
        fast_plan = plan_text(conn, plan_sql, status)
        print(f"    {name} without index: {slow:8.4f} ms   ({slow_plan})")
        print(f"    {name} with index:    {fast:8.4f} ms   ({fast_plan})")
        print(f"    {name} speed-up: {slow / fast:.1f}x")


# Build a fresh temporary database with `rows` shipments and compare.
def run(rows):
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "timing.db")
        db.init_db(path)
        conn = db.connect(path)
        add_fake_shipments(conn, rows)
        print(f"{rows} shipments")
        compare(conn, "rare, about 2% of rows", "cancelled")
        compare(conn, "common, about 30% of rows", "created")
        conn.close()


# Run the comparison for a small table (the size of the seed) and a bigger one.
def main():
    for rows in (1000, 100_000):
        run(rows)


if __name__ == "__main__":
    main()
