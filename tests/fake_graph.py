"""A stand-in Meta Graph API, good enough to run the real publisher against.

It implements the endpoints the Ship layer uses, records every request, and
returns plausible ids. Point the client at it with GRAPH_BASE_URL and the whole
publish path runs for real — real HTTP, real form encoding, real error handling
— without touching an account or needing a token.

    with FakeGraph() as fake:
        os.environ["GRAPH_BASE_URL"] = fake.url
        ...
        fake.calls   # every request, in order
"""
from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer


class FakeGraph:
    def __init__(self, fail_on: str | None = None):
        self.calls: list[dict] = []
        self.fail_on = fail_on          # substring of a path that should 400
        self._n = 0
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ---- lifecycle ----
    def __enter__(self) -> "FakeGraph":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):        # keep pytest output clean
                pass

            def _reply(self, code: int, body: dict):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                params = {k: v[0] for k, v in
                          urllib.parse.parse_qs(parsed.query).items()}
                self._reply(*outer._handle(parsed.path, params, "GET"))

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                params = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
                self._reply(*outer._handle(urllib.parse.urlparse(self.path).path,
                                           params, "POST"))

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    @property
    def url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v23.0"

    # ---- routing ----
    def _handle(self, path: str, params: dict, method: str) -> tuple[int, dict]:
        route = path.split("/v23.0/", 1)[-1]
        token = params.pop("access_token", None)
        self.calls.append({"method": method, "path": route, "params": params})

        if not token:
            return 400, {"error": {"message": "An access token is required",
                                   "code": 190, "fbtrace_id": "fake"}}
        if self.fail_on and self.fail_on in route:
            return 400, {"error": {"message": f"simulated failure on {route}",
                                   "code": 100, "error_subcode": 2207003,
                                   "fbtrace_id": "fake"}}

        self._n += 1
        n = self._n

        if route == "me":
            return 200, {"id": "1", "name": "Fake User"}
        if route == "me/accounts":
            return 200, {"data": [{"id": "FB_PAGE", "name": "Fake Page",
                                   "access_token": "PAGE_TOKEN"}]}
        if route.endswith("/media_publish"):
            return 200, {"id": f"media_{n}"}
        if route.endswith("/media"):
            kind = "parent" if params.get("media_type") == "CAROUSEL" else "child"
            return 200, {"id": f"{kind}_{n}"}
        if route.endswith("/photos"):
            return 200, {"id": f"photo_{n}"}
        if route.endswith("/feed"):
            return 200, {"id": f"FB_PAGE_post_{n}"}
        if route.endswith("/comments"):
            return 200, {"id": f"comment_{n}"}
        # a container status poll: /{container-id}?fields=status_code
        if params.get("fields", "").startswith("status_code"):
            return 200, {"status_code": "FINISHED", "id": route}

        return 404, {"error": {"message": f"unrouted: {route}", "code": 803}}

    # ---- assertions helpers ----
    def paths(self, suffix: str) -> list[dict]:
        return [c for c in self.calls if c["path"].endswith(suffix)]
