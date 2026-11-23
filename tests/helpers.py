"""Shared test setup: start the real server on a free port in a thread."""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from tracker.server import make_server

# A shipment body that passes validation. The date is far in the future,
# so this shipment is never "late".
GOOD = {"customer": "Acme Corp", "destination": "Austin", "promised_date": "2999-01-01"}


# Base class for tests that talk to the server over HTTP.
# Every test gets its own empty database and its own server.
class ServerTestCase(unittest.TestCase):
    # Start a server on a free port (port 0) in a background thread.
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.folder.name, "test.db")
        self.server = make_server(self.db_path, port=0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        # poll_interval=0.05 makes shutdown() quick (the default waits 0.5 s).
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    # Stop the server and delete the temporary database.
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.folder.cleanup()

    # Send one HTTP request. Returns (status_code, parsed_json).
    # `raw` lets a test send bytes that are not valid JSON.
    def call(self, method, path, body=None, headers=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(self.base + path, data=data, method=method)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    # Create a valid shipment (changing any fields given) and return it.
    def make_shipment(self, **changes):
        code, shipment = self.call("POST", "/shipments", {**GOOD, **changes})
        self.assertEqual(code, 201)
        return shipment

    # Move a shipment to a new status and return (code, body).
    def move(self, shipment_id, status, note=None):
        body = {"status": status}
        if note is not None:
            body["note"] = note
        return self.call("POST", f"/shipments/{shipment_id}/events", body)
