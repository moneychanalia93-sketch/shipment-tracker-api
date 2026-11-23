"""The API logic: pick the right action for a request. No HTTP code here."""

import re
from datetime import date
from urllib.parse import parse_qs, urlsplit

from tracker import db, validation
from tracker.errors import ApiError

# Matches /shipments/7, /shipments/7/events and /shipments/7/history.
# The id is limited to 18 digits so it always fits in the database.
SHIPMENT_PATH = re.compile(r"/shipments/(\d{1,18})(/events|/history)?")


# POST /shipments: create a shipment. Returns 201, or 200 when the
# Idempotency-Key was already used (we return the first shipment again).
def create(conn, body, idem_key):
    key = validation.check_idempotency_key(idem_key)
    data = validation.check_new_shipment(body)
    shipment, was_created = db.create_shipment(conn, data, key)
    return (201 if was_created else 200), shipment


# GET /shipments?status=...&limit=...: list shipments, newest first.
def list_all(conn, query):
    status, limit = validation.check_list_params(query)
    shipments = db.list_shipments(conn, status, limit)
    return 200, {"count": len(shipments), "shipments": shipments}


# GET /shipments/{id}: one shipment, or 404.
def get_one(conn, shipment_id):
    shipment = db.get_shipment(conn, shipment_id)
    if shipment is None:
        raise ApiError(404, "shipment not found")
    return 200, shipment


# POST /shipments/{id}/events: move a shipment to a new status.
# 400 for a bad body, 404 if missing, 409 if the move is not allowed.
def add_event(conn, shipment_id, body):
    status, note = validation.check_event(body)
    return 201, db.add_event(conn, shipment_id, status, note)


# GET /shipments/{id}/history: every status change of one shipment.
def history(conn, shipment_id):
    if db.get_shipment(conn, shipment_id) is None:
        raise ApiError(404, "shipment not found")
    return 200, {"shipment_id": shipment_id, "history": db.get_history(conn, shipment_id)}


# GET /stats: counts per status and the number of late shipments.
def stats(conn):
    return 200, db.get_stats(conn, date.today().isoformat())


# Look at the method and the path, and call the matching function above.
# Anything that matches nothing is a 404.
def dispatch(conn, method, path, query, body, idem_key):
    if path == "/shipments" and method == "POST":
        return create(conn, body, idem_key)
    if path == "/shipments" and method == "GET":
        return list_all(conn, query)
    if path == "/stats" and method == "GET":
        return stats(conn)
    match = SHIPMENT_PATH.fullmatch(path)
    if match:
        shipment_id = int(match.group(1))
        extra = match.group(2)
        if extra is None and method == "GET":
            return get_one(conn, shipment_id)
        if extra == "/history" and method == "GET":
            return history(conn, shipment_id)
        if extra == "/events" and method == "POST":
            return add_event(conn, shipment_id, body)
    raise ApiError(404, "not found")


# Handle one request. Opens a database connection, runs the action, and
# always closes the connection. Returns (http_code, dict_for_json).
def handle(db_path, method, url, body, idem_key):
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    query = {name: values[0] for name, values in parse_qs(parts.query).items()}
    conn = db.connect(db_path)
    try:
        return dispatch(conn, method, path, query, body, idem_key)
    finally:
        conn.close()
