"""All the SQL lives here. Every query uses ? placeholders (parameterized)."""

import sqlite3
import threading
from datetime import datetime, timezone

from tracker.errors import ApiError
from tracker.states import FINISHED, STATES, can_move

SCHEMA = """
CREATE TABLE IF NOT EXISTS shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT NOT NULL,
    destination TEXT NOT NULL,
    promised_date TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shipment_id INTEGER NOT NULL REFERENCES shipments(id),
    from_status TEXT,
    to_status TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS history_no_update BEFORE UPDATE ON history
BEGIN SELECT RAISE(ABORT, 'history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS history_no_delete BEFORE DELETE ON history
BEGIN SELECT RAISE(ABORT, 'history is append-only'); END;

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    shipment_id INTEGER NOT NULL REFERENCES shipments(id)
);
"""

# Only one write may run at a time inside this server process.
# This stops two requests from changing the same shipment at the same moment.
# shortcut: this lock only works inside one process; with several server
# processes, move to a real database and use its transactions and constraints.
write_lock = threading.Lock()


# The current time as text, like 2026-11-23T20:15:00Z (UTC).
def now_text():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Open the database file. Rows come back as dict-like objects, and
# foreign keys are checked. We open one connection per request and close it,
# so the statement cache (cached_statements=0) would never help. Turning it
# off also keeps EXPLAIN output honest after DROP INDEX in timing.py.
def connect(path):
    conn = sqlite3.connect(path, timeout=5, cached_statements=0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Create the tables, the index and the append-only triggers if missing.
# Safe to run every time the server starts.
def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.close()


# Turn a database row into a plain dict (so it can become JSON).
# Returns None when there is no row.
def row_to_dict(row):
    return dict(row) if row is not None else None


# Add one line to the history table. History is only ever added to,
# never changed (the triggers in SCHEMA enforce that).
def add_history(conn, shipment_id, from_status, to_status, note):
    conn.execute(
        "INSERT INTO history (shipment_id, from_status, to_status, note, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (shipment_id, from_status, to_status, note, now_text()),
    )


# Find one shipment by id. Returns a dict, or None if it does not exist.
def get_shipment(conn, shipment_id):
    row = conn.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,)).fetchone()
    return row_to_dict(row)


# List shipments, newest first. Optionally keep only one status.
# The status filter is the query that the index on `status` speeds up.
def list_shipments(conn, status, limit):
    if status is None:
        rows = conn.execute("SELECT * FROM shipments ORDER BY id DESC LIMIT ?", (limit,))
    else:
        rows = conn.execute(
            "SELECT * FROM shipments WHERE status = ? ORDER BY id DESC LIMIT ?",
            (status, limit),
        )
    return [dict(row) for row in rows]


# Create a shipment with status "created" and its first history line.
# Idempotency: if the caller sends a key we have already seen, we do NOT
# create a second shipment. We return the first one again. This makes a
# retry after a network failure safe. Returns (shipment, was_created).
def create_shipment(conn, data, idem_key=None):
    with write_lock:
        if idem_key is not None:
            row = conn.execute(
                "SELECT shipment_id FROM idempotency_keys WHERE key = ?", (idem_key,)
            ).fetchone()
            if row is not None:
                return get_shipment(conn, row["shipment_id"]), False
        now = now_text()
        # "with conn" is one transaction: all three inserts happen, or none do.
        with conn:
            cursor = conn.execute(
                "INSERT INTO shipments"
                " (customer, destination, promised_date, status, created_at, updated_at)"
                " VALUES (?, ?, ?, 'created', ?, ?)",
                (data["customer"], data["destination"], data["promised_date"], now, now),
            )
            shipment_id = cursor.lastrowid
            add_history(conn, shipment_id, None, "created", "shipment created")
            if idem_key is not None:
                conn.execute(
                    "INSERT INTO idempotency_keys (key, shipment_id) VALUES (?, ?)",
                    (idem_key, shipment_id),
                )
        return get_shipment(conn, shipment_id), True


# Move a shipment to a new status, if the state machine allows it.
# Raises 404 if the shipment is missing and 409 if the move is not allowed.
# The status update and the history line are saved together (one transaction).
def add_event(conn, shipment_id, new_status, note):
    with write_lock:
        shipment = get_shipment(conn, shipment_id)
        if shipment is None:
            raise ApiError(404, "shipment not found")
        old_status = shipment["status"]
        if not can_move(old_status, new_status):
            raise ApiError(409, f"cannot move from {old_status} to {new_status}")
        with conn:
            conn.execute(
                "UPDATE shipments SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now_text(), shipment_id),
            )
            add_history(conn, shipment_id, old_status, new_status, note)
        return get_shipment(conn, shipment_id)


# All history lines of one shipment, oldest first.
def get_history(conn, shipment_id):
    rows = conn.execute(
        "SELECT from_status, to_status, note, created_at FROM history"
        " WHERE shipment_id = ? ORDER BY id",
        (shipment_id,),
    )
    return [dict(row) for row in rows]


# Numbers for GET /stats: how many shipments per status, and how many are
# late. Late = promised date is before `today` and the shipment is not
# finished yet. The two ? marks below match the two FINISHED statuses.
def get_stats(conn, today):
    by_status = {status: 0 for status in STATES}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM shipments GROUP BY status"):
        by_status[row["status"]] = row["n"]
    late = conn.execute(
        "SELECT COUNT(*) FROM shipments WHERE promised_date < ? AND status NOT IN (?, ?)",
        (today, *FINISHED),
    ).fetchone()[0]
    return {"total": sum(by_status.values()), "by_status": by_status, "late": late}
