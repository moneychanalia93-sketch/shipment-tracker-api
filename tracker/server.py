"""The web server: reads HTTP requests, calls api.handle, sends JSON back."""

import argparse
import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tracker import api, db
from tracker.errors import ApiError

MAX_BODY_BYTES = 10_000


class Handler(BaseHTTPRequestHandler):
    # Browsers and curl call this for every GET request.
    def do_GET(self):
        self.respond_to("GET")

    # ...and this for every POST request.
    def do_POST(self):
        self.respond_to("POST")

    # Silence the default one-line-per-request log so test output stays clean.
    def log_message(self, format, *args):
        pass

    # Read the JSON body of a POST. Returns None when there is no body.
    # Bad length or bad JSON raises a 400 error.
    def read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(400, "bad Content-Length header")
        if length < 0 or length > MAX_BODY_BYTES:
            raise ApiError(400, f"body must be at most {MAX_BODY_BYTES} bytes")
        raw = self.rfile.read(length)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            raise ApiError(400, "body is not valid JSON")

    # Run the request through api.handle and send the answer.
    # Errors we expect (ApiError) become JSON errors. Anything else is
    # a bug: we print it for the developer and send a plain 500.
    def respond_to(self, method):
        try:
            body = self.read_json_body() if method == "POST" else None
            idem_key = self.headers.get("Idempotency-Key")
            code, payload = api.handle(self.server.db_path, method, self.path, body, idem_key)
        except ApiError as error:
            code, payload = error.code, {"error": error.message}
        except Exception:
            traceback.print_exc()
            code, payload = 500, {"error": "internal server error"}
        self.send_json(code, payload)

    # Write the HTTP status line, the headers, and the JSON text.
    def send_json(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


# Create the database if needed and build a server (not started yet).
# Port 0 means "pick any free port" - the tests use that.
def make_server(db_path, port=0, host="127.0.0.1"):
    db.init_db(db_path)
    server = ThreadingHTTPServer((host, port), Handler)
    server.db_path = db_path
    return server


# Start the server from the command line: python -m tracker.server
def main():
    parser = argparse.ArgumentParser(description="Shipment tracker API")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default="shipments.db")
    args = parser.parse_args()
    server = make_server(args.db, args.port)
    print(f"Listening on http://127.0.0.1:{args.port}  (database: {args.db}). Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
