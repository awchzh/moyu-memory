"""
examples/http_server.py — Expose MOYU memory as a simple HTTP API.

Run:
    python3 examples/http_server.py
    curl http://localhost:8765/search?q=hello
    curl -X POST http://localhost:8765/learn -d 'text=my name is Alice'

No dependencies beyond Python stdlib + moyu-memory.
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from moyu_toolkit import agent_memory as mem


class MemoryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
        results = mem.search(q, top_k=3) if q else []
        self._json({"ok": True, "results": results})

    def do_POST(self):
        if self.path == "/learn":
            length = int(self.headers.get("Content-Length", 0))
            text = self.rfile.read(length).decode()
            mem.add_memory(text, source="user")
            self._json({"ok": True, "message": "Memory saved"})
        else:
            self._json({"ok": False}, 404)

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())


HTTPServer(("", 8765), MemoryHandler).serve_forever()
