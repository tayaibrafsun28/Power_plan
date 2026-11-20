"""Power_plan web server.  Start it with:  python app.py

POST /api/roster   body = input JSON, response = output JSON
                   HTTP 200 for "ok" and "infeasible", 400 for "invalid_input"
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from solver import solve

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
MAX_BODY = 1_000_000          # bytes


def _reject_constant(name):
    raise ValueError(f"{name} is not allowed")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type="application/json"):
        payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _invalid(self, message):
        self._send(400, {"status": "invalid_input", "message": message})

    def do_GET(self):
        if self.path == "/api/roster":
            self._send(405, {"message": "use POST for /api/roster"})
        elif self.path == "/":
            self._send(200, b"Power_plan is running. POST an input JSON to /api/roster.",
                       "text/plain")
        else:
            self._send(404, {"message": "not found"})

    def do_POST(self):
        if self.path != "/api/roster":
            self._send(404, {"message": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._invalid("body: bad Content-Length")
        if length <= 0 or length > MAX_BODY:
            return self._invalid("body: empty or too large")
        try:
            data = json.loads(self.rfile.read(length), parse_constant=_reject_constant)
        except ValueError:
            return self._invalid("body: not valid JSON")
        try:
            result = solve(data)
        except Exception:                      # never leak a stack trace to a caller
            self._send(500, {"message": "internal error"})
            raise
        self._send(400 if result["status"] == "invalid_input" else 200, result)


def make_server(host=HOST, port=PORT):
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    server = make_server()
    print(f"Power_plan running on http://{HOST}:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")