# shipment-tracker-api

A small REST API that tracks shipments through five states: `created`, `packed`, `shipped`, `delivered`, `cancelled`.

It uses only the Python standard library (`http.server`, `sqlite3`, `json`, `unittest`). There is nothing to install. Python 3.13 was used; any recent Python 3 should work.

> Built with AI assistance (Kiro). I designed the rules, reviewed the code, and ran the tests.
> This is a learning project. It has not been used in production.

## What it does

- Create a shipment, read it, list and filter shipments.
- Move a shipment to a new status. A small state machine decides which moves are allowed. A bad move returns `409`.
- Keep an append-only history of every status change. Database triggers refuse any edit or delete of history rows.
- Report counts per status and how many shipments are late (promised date passed and not yet delivered or cancelled).
- Accept an `Idempotency-Key` header on `POST /shipments`, so a retried request does not create a second shipment.

The allowed moves:

```
created --> packed --> shipped --> delivered
   |          |
   +----------+--> cancelled
```

`delivered` and `cancelled` are final. A shipment cannot be cancelled once it has shipped.

## Run it (3 commands)

Run these from the project folder. If `python` is not on your PATH, use `py` or the full path to `python.exe`.

```powershell
python -m tracker.seed        # creates shipments.db with 1,000 fake shipments
python -m tracker.server      # starts the API on http://127.0.0.1:8000 (Ctrl+C to stop)
python -m unittest discover -s tests -t .   # runs the tests
```

Real output of the first command:

```
Added 1000 shipments to shipments.db
Totals now: 1000 shipments, 232 late
By status: {'created': 277, 'packed': 250, 'shipped': 268, 'delivered': 184, 'cancelled': 21}
```

(The late count depends on today's date, because the fake promised dates are spread around today.)

Options: `python -m tracker.server --port 9000 --db other.db` and `python -m tracker.seed --count 50`. Delete `shipments.db` to start fresh.

## Endpoints

| Method and path | What it does | Success | Errors |
|---|---|---|---|
| `POST /shipments` | Create a shipment | `201` (`200` on an idempotent retry) | `400` |
| `GET /shipments/{id}` | Read one shipment | `200` | `404` |
| `GET /shipments?status=packed&limit=20` | List, newest first. `limit` is 1 to 100, default 20 | `200` | `400` |
| `POST /shipments/{id}/events` | Move to a new status | `201` | `400`, `404`, `409` |
| `GET /shipments/{id}/history` | Every status change, oldest first | `200` | `404` |
| `GET /stats` | Counts per status and late shipments | `200` | none |

Errors are always JSON: `{"error": "message"}`. An unknown path, or a known path with the wrong method (for example `POST /stats`), returns `404`.

## Examples (Windows PowerShell)

Start the server in one window, then paste these in another. In PowerShell, write `curl.exe` (plain `curl` is a different command there). The `\"` escapes keep the quotes inside the JSON. On macOS or Linux, use normal single-quoted JSON without the backslashes. Output below is real, from a run right after the seed command.

**Create a shipment** (the seed already made ids 1 to 1000, so this one is 1001):

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/shipments -H "Content-Type: application/json" -d '{\"customer\": \"Acme Corp\", \"destination\": \"Austin\", \"promised_date\": \"2026-12-31\"}' -w '\nHTTP %{http_code}\n'
```
```
{"id": 1001, "customer": "Acme Corp", "destination": "Austin", "promised_date": "2026-12-31", "status": "created", "created_at": "2026-11-23T20:25:31Z", "updated_at": "2026-11-23T20:25:31Z"}
HTTP 201
```

**Read it:**

```powershell
curl.exe -s http://127.0.0.1:8000/shipments/1001 -w '\nHTTP %{http_code}\n'
```
```
{"id": 1001, "customer": "Acme Corp", "destination": "Austin", "promised_date": "2026-12-31", "status": "created", "created_at": "2026-11-23T20:25:31Z", "updated_at": "2026-11-23T20:25:31Z"}
HTTP 200
```

**List cancelled shipments (two at most):**

```powershell
curl.exe -s "http://127.0.0.1:8000/shipments?status=cancelled&limit=2" -w '\nHTTP %{http_code}\n'
```
```
{"count": 2, "shipments": [{"id": 980, "customer": "Eagle Tools", "destination": "Dallas", "promised_date": "2026-11-26", "status": "cancelled", "created_at": "2026-11-23T20:24:44Z", "updated_at": "2026-11-23T20:24:44Z"}, {"id": 959, "customer": "Fern Books", "destination": "Denver", "promised_date": "2026-12-09", "status": "cancelled", "created_at": "2026-11-23T20:24:44Z", "updated_at": "2026-11-23T20:24:44Z"}]}
HTTP 200
```

**Move it to `packed`:**

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/shipments/1001/events -H "Content-Type: application/json" -d '{\"status\": \"packed\", \"note\": \"boxed at dock 3\"}' -w '\nHTTP %{http_code}\n'
```
```
{"id": 1001, "customer": "Acme Corp", "destination": "Austin", "promised_date": "2026-12-31", "status": "packed", "created_at": "2026-11-23T20:25:31Z", "updated_at": "2026-11-23T20:25:31Z"}
HTTP 201
```

**See its history:**

```powershell
curl.exe -s http://127.0.0.1:8000/shipments/1001/history -w '\nHTTP %{http_code}\n'
```
```
{"shipment_id": 1001, "history": [{"from_status": null, "to_status": "created", "note": "shipment created", "created_at": "2026-11-23T20:25:31Z"}, {"from_status": "created", "to_status": "packed", "note": "boxed at dock 3", "created_at": "2026-11-23T20:25:31Z"}]}
HTTP 200
```

**Stats:**

```powershell
curl.exe -s http://127.0.0.1:8000/stats -w '\nHTTP %{http_code}\n'
```
```
{"total": 1001, "by_status": {"created": 277, "packed": 251, "shipped": 268, "delivered": 184, "cancelled": 21}, "late": 232}
HTTP 200
```

**A move the rules do not allow (`packed` straight to `delivered`) returns 409:**

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/shipments/1001/events -H "Content-Type: application/json" -d '{\"status\": \"delivered\"}' -w '\nHTTP %{http_code}\n'
```
```
{"error": "cannot move from packed to delivered"}
HTTP 409
```

**Bad input returns 400:**

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/shipments -H "Content-Type: application/json" -d '{\"customer\": \"\", \"destination\": \"Austin\", \"promised_date\": \"2026-12-31\"}' -w '\nHTTP %{http_code}\n'
```
```
{"error": "customer is required and must be non-empty text"}
HTTP 400
```

**An unknown id returns 404:**

```powershell
curl.exe -s http://127.0.0.1:8000/shipments/999999 -w '\nHTTP %{http_code}\n'
```
```
{"error": "shipment not found"}
HTTP 404
```

**Idempotency.** Send the same request twice with the same `Idempotency-Key`. The first call creates the shipment (`201`). The retry creates nothing and returns the first shipment again (`200`, same id):

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/shipments -H "Content-Type: application/json" -H "Idempotency-Key: order-5001" -d '{\"customer\": \"Birch Foods\", \"destination\": \"Denver\", \"promised_date\": \"2026-12-31\"}' -w '\nHTTP %{http_code}\n'
```
```
{"id": 1002, "customer": "Birch Foods", "destination": "Denver", "promised_date": "2026-12-31", "status": "created", "created_at": "2026-11-23T20:25:31Z", "updated_at": "2026-11-23T20:25:31Z"}
HTTP 201
```
Run the same command again:
```
{"id": 1002, "customer": "Birch Foods", "destination": "Denver", "promised_date": "2026-12-31", "status": "created", "created_at": "2026-11-23T20:25:31Z", "updated_at": "2026-11-23T20:25:31Z"}
HTTP 200
```

**An invalid `limit` returns 400:**

```powershell
curl.exe -s "http://127.0.0.1:8000/shipments?limit=500" -w '\nHTTP %{http_code}\n'
```
```
{"error": "limit must be a whole number from 1 to 100"}
HTTP 400
```

## Does the index help? (real numbers)

`shipments.status` has an index. `python -m tracker.timing` builds a temporary database, then times two queries with the index dropped and with it created. It also prints what SQLite says it will do (`SCAN` = read every row, `SEARCH ... USING INDEX` = jump straight to the matching rows).

One run on a Windows laptop (Python 3.13, SQLite, times are milliseconds per query, best of 5 rounds of 20). Your numbers will differ.

| Rows | Status | Query | Without index | With index | Speed-up |
|---|---|---|---|---|---|
| 1,000 | cancelled (about 2%) | list (20 newest) | 0.0968 | 0.0633 | 1.5x |
| 1,000 | cancelled (about 2%) | count | 0.0865 | 0.0380 | 2.3x |
| 100,000 | cancelled (about 2%) | list (20 newest) | 0.1628 | 0.0445 | 3.7x |
| 100,000 | cancelled (about 2%) | count | 9.7678 | 0.0919 | 106.3x |
| 100,000 | created (about 30%) | list (20 newest) | 0.0545 | 0.0619 | 0.9x |
| 100,000 | created (about 30%) | count | 10.1347 | 0.9146 | 11.1x |

What this shows, honestly:

- At 1,000 rows (the size of the seed) everything is already fast. The index barely matters.
- Counting is where the index wins big, because SQLite can count inside the index without reading the table rows.
- The "list 20 newest" query is already quick without an index, because it scans from the newest row and stops after 20 matches. For a common status the index gives no gain (0.9x is within noise).

## What it does not do

- No authentication or authorization. Anyone who can reach the port can read and change data.
- No HTTPS. The server listens on `127.0.0.1` (your own machine) only.
- SQLite and `http.server` are for learning and small demos, not for heavy traffic. Writes are serialized with one lock inside one process, so running several server processes against one database file is not supported.
- Idempotency is basic: the key maps to the first shipment. It does not compare the body, so reusing a key with a different body returns the first shipment. Keys are never expired.
- No pagination beyond `limit` (no offset or cursor), no sorting options, no update or delete of shipments.
- No rate limiting, no request logging, no metrics.
- Only `GET` and `POST` are handled. `PUT`, `PATCH` and `DELETE` get Python's default "not implemented" reply, which is not JSON.
- Dates are plain `YYYY-MM-DD` text. "Late" uses the server's local date, with no time zones.
- Tests cover the behavior listed above. There is no load testing.

## Run the tests

```powershell
python -m unittest discover -s tests -t .
```

Real result: `Ran 45 tests ... OK`. The tests start the real server on a free port in a background thread and call it over HTTP. They cover the state machine, input validation, every endpoint, idempotency (including five simultaneous requests with one key), the append-only history, and the index.

## Files

```
tracker/errors.py      one error type that carries an HTTP code
tracker/states.py      the states and the allowed moves
tracker/validation.py  checks on everything the caller sends
tracker/db.py          all the SQL (parameterized) and the schema
tracker/api.py         picks the right action for each URL
tracker/server.py      the HTTP server (reads requests, sends JSON)
tracker/seed.py        adds fake shipments
tracker/timing.py      the with/without index measurement
tests/                 unittest tests
```

## License

MIT. See `LICENSE`.
