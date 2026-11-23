"""Check what the caller sent. Anything wrong raises ApiError(400, ...)."""

from datetime import datetime

from tracker.errors import ApiError
from tracker.states import STATES

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


# The body must be a JSON object like {"a": 1}. A list or a number is not ok.
def require_object(body):
    if not isinstance(body, dict):
        raise ApiError(400, "body must be a JSON object")
    return body


# Get a required text field. It must be text, not blank, and not too long.
# We cap the length so nobody can store a huge string.
def require_text(body, field, max_length):
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, f"{field} is required and must be non-empty text")
    value = value.strip()
    if len(value) > max_length:
        raise ApiError(400, f"{field} must be at most {max_length} characters")
    return value


# True only for real dates written exactly like 2026-12-31.
# We check the length too, because Python also accepts looser spellings.
def is_real_date(value):
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


# Check the body of POST /shipments and return only the fields we keep.
def check_new_shipment(body):
    body = require_object(body)
    promised_date = body.get("promised_date")
    if not is_real_date(promised_date):
        raise ApiError(400, "promised_date must be a real date like 2026-12-31")
    return {
        "customer": require_text(body, "customer", 100),
        "destination": require_text(body, "destination", 200),
        "promised_date": promised_date,
    }


# Check the body of POST /shipments/{id}/events.
# Returns (new_status, note). The note is optional.
def check_event(body):
    body = require_object(body)
    status = body.get("status")
    if status not in STATES:
        raise ApiError(400, "status must be one of: " + ", ".join(STATES))
    note = body.get("note", "")
    if not isinstance(note, str) or len(note) > 200:
        raise ApiError(400, "note must be text of at most 200 characters")
    return status, note.strip()


# Check the query string of GET /shipments (?status=...&limit=...).
# Returns (status or None, limit). The limit has a default and a maximum.
def check_list_params(query):
    status = query.get("status")
    if status is not None and status not in STATES:
        raise ApiError(400, "status must be one of: " + ", ".join(STATES))
    try:
        limit = int(query.get("limit", DEFAULT_LIMIT))
    except ValueError:
        limit = 0
    if not 1 <= limit <= MAX_LIMIT:
        raise ApiError(400, f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return status, limit


# Check the Idempotency-Key header. No header is fine (returns None).
# A header that is empty or very long is rejected.
def check_idempotency_key(key):
    if key is None:
        return None
    key = key.strip()
    if not key or len(key) > 100:
        raise ApiError(400, "Idempotency-Key must be 1 to 100 characters")
    return key
