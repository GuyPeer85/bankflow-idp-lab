import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PORT = int(os.getenv("PORT", "8080"))
VERSION = os.getenv("APP_VERSION", "1.0.0")


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health/live":
            self.send_json(200, {"status": "alive"})
            return

        if self.path == "/health/ready":
            self.send_json(200, {"status": "ready"})
            return

        if self.path == "/api/payments":
            self.send_json(
                200,
                {
                    "service": "payments-api",
                    "version": VERSION,
                    "hostname": socket.gethostname(),
                    "payments": [],
                },
            )
            return

        self.send_json(404, {"error": "not found"})


server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)

print(f"payments-api {VERSION} listening on port {PORT}")
server.serve_forever()