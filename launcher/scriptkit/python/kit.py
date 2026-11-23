"""Port parsing, static serving and the stop endpoint for Python apps."""

import argparse
import json
import threading
from collections.abc import Callable, Mapping, Sequence
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HOST = "127.0.0.1"
FRONTEND_DIR = Path(__file__).parents[2] / "frontend"
LAUNCHER_PREFIX = "/_launcher/"
STOP_PATH = "/_launcher/stop"

Routes = Mapping[tuple[str, str], Callable[[], object]]

_active_server: ThreadingHTTPServer | None = None


def parse_port(argv: Sequence[str]) -> int:
    """Return N from `--port N`; exits with a usage message when it is missing or not a number."""
    parser = argparse.ArgumentParser(description="App started by the launcher.")
    parser.add_argument("--port", type=int, required=True, help="TCP port on 127.0.0.1")
    return parser.parse_args(list(argv)).port


def stop() -> None:
    """Stop the server started by `run_app` from inside the app; `run_app` then returns."""
    if _active_server is not None:
        # shutdown() waits for serve_forever to end, so it must not run on the serving thread.
        threading.Thread(target=_active_server.shutdown, daemon=True).start()


def run_app(ui_dir: Path, port: int, routes: Routes | None = None) -> None:
    """Serve `ui_dir` at / and the launcher frontend at /_launcher/ until stopped.

    `routes` maps (method, path) to a function that takes no arguments and returns a JSON-able
    value. Returns after `POST /_launcher/stop` or `stop()`, so the process exits with code 0.
    """
    global _active_server
    server = ThreadingHTTPServer((HOST, port), _make_handler(Path(ui_dir), dict(routes or {})))
    _active_server = server
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _active_server = None
        server.server_close()


def _make_handler(ui_dir: Path, routes: dict) -> type[SimpleHTTPRequestHandler]:
    class Handler(SimpleHTTPRequestHandler):
        # Explicit, because on Windows the registry can map .js to a non-script type.
        extensions_map = {
            **SimpleHTTPRequestHandler.extensions_map,
            ".js": "text/javascript",
            ".mjs": "text/javascript",
            ".css": "text/css",
            ".html": "text/html",
            ".json": "application/json",
        }

        def translate_path(self, path):
            route = urlsplit(path).path
            if route.startswith(LAUNCHER_PREFIX):
                # The parent class drops ".." segments, so this cannot leave the chosen directory.
                self.directory = str(FRONTEND_DIR)
                route = route[len(LAUNCHER_PREFIX) - 1:]
            else:
                self.directory = str(ui_dir)
            return super().translate_path(route)

        def end_headers(self):
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def do_GET(self):
            if not self._run_route("GET"):
                super().do_GET()

        def do_POST(self):
            if urlsplit(self.path).path == STOP_PATH:
                self._send_json({"status": "stopping"})
                stop()
            elif not self._run_route("POST"):
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def _run_route(self, method: str) -> bool:
            handler = routes.get((method, urlsplit(self.path).path))
            if handler is None:
                return False
            try:
                self._send_json(handler())
            except Exception as error:  # report to the page instead of dropping the connection
                self._send_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return True

        def _send_json(self, body: object, status: HTTPStatus = HTTPStatus.OK):
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler
