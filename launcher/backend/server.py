"""HTTP server: JSON API under /api, everything else is the static frontend."""

import json
import logging
import re
import threading
import time
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from launcher.backend import config, process

FRONTEND_DIR = Path(__file__).parents[1] / "frontend"
HOST = "127.0.0.1"
START_ROUTE = re.compile(r"/api/apps/(\d+)/start")
WATCHDOG_TIMEOUT_SECONDS = 15.0
LOG = logging.getLogger("launcher.server")


class Handler(SimpleHTTPRequestHandler):
    """Serves the API and static files; `config_dir` is bound by `make_server`."""

    def __init__(self, *args, config_dir: Path, **kwargs):
        self.config_dir = config_dir
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def end_headers(self):
        # Frontend edits must show on the next page load, so nothing is cached.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        route = self._route()
        if not route.startswith("/api/"):
            super().do_GET()
        elif route == "/api/health":
            self._send_json({"status": "ok"})
        elif route == "/api/apps":
            self._send_apps()
        elif route == "/api/running":
            self._send_json({"running": self.server.runner.running()})
        else:
            self._send_unknown(route)

    def do_PUT(self):
        route = self._route()
        if route == "/api/apps":
            self._replace_apps()
        else:
            self._send_unknown(route)

    def do_POST(self):
        route = self._route()
        match = START_ROUTE.fullmatch(route)
        if match:
            self._start_app(int(match.group(1)))
        elif route == "/api/heartbeat":
            self.server.record_heartbeat()
            self._send_json({"running": self.server.runner.running()})
        elif route == "/api/shutdown":
            LOG.info("Shutdown requested through the API")
            self._send_json({"status": "shutting_down"})
            # After the response, so the client receives it before the socket goes away.
            self.server.request_shutdown()
        else:
            self._send_unknown(route)

    def log_message(self, format, *args):
        # Request lines go through logging (rotated), not straight to stderr.
        LOG.info("%s %s", self.address_string(), format % args)

    def _route(self) -> str:
        return self.path.split("?", 1)[0]

    def _send_unknown(self, route: str):
        self._send_error(HTTPStatus.NOT_FOUND, f"Unknown API path {route}")

    def _send_apps(self):
        try:
            self._send_json({"apps": config.load_apps(self.config_dir)})
        except config.ConfigError as error:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def _replace_apps(self):
        # Rejects bodies that are not declared as JSON, before they are parsed. It is not a cross-site
        # defence: HTML forms cannot send PUT, and a cross-origin PUT is preflighted by the browser.
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            self._send_error(HTTPStatus.BAD_REQUEST, "Content-Type must be application/json.")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            body = json.loads(self.rfile.read(length))
        except ValueError:
            self._send_error(HTTPStatus.BAD_REQUEST, "Body must be valid JSON with a Content-Length.")
            return
        entries = body.get("apps") if isinstance(body, dict) else None
        try:
            apps = config.save_apps(self.config_dir, entries)
        except config.ConfigError as error:
            self._send_error(HTTPStatus.BAD_REQUEST, str(error))
        except OSError as error:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Could not write apps.json: {error}")
        else:
            self._send_json({"apps": apps})

    def _start_app(self, index: int):
        try:
            apps = config.load_apps(self.config_dir)
            workspace_root = config.load_workspace_root(self.config_dir)
        except config.ConfigError as error:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
            return
        if index >= len(apps):
            self._send_error(HTTPStatus.NOT_FOUND, f"No app at index {index}.")
            return
        app = apps[index]
        script = config.resolve_script_path(app["script_path"], workspace_root)
        try:
            running = self.server.runner.running()
            if running:
                raise process.AlreadyRunning(f"'{running['name']}' is already running.")
            process.require_script_file(script)
            interpreter = process.select_interpreter(script)
            started = self.server.runner.start(app["name"], interpreter, script, workspace_root)
        except process.AlreadyRunning as error:
            self._send_error(HTTPStatus.CONFLICT, str(error))
        except process.LaunchError as error:
            self._send_error(HTTPStatus.BAD_REQUEST, str(error))
        except process.StartError as error:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
        else:
            self._send_json(started)

    def _send_error(self, status: HTTPStatus, message: str):
        self._send_json({"error": message}, status)

    def _send_json(self, body: dict, status: HTTPStatus = HTTPStatus.OK):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class LauncherServer(ThreadingHTTPServer):
    """Carries the app runner; stops the running app when the server shuts down or closes.

    With `watchdog_timeout` set, the server shuts itself down when no heartbeat arrived for that
    many seconds; serving start counts as the first heartbeat.
    """

    def __init__(
        self,
        address,
        handler,
        runner: process.AppRunner,
        watchdog_timeout: float | None = None,
    ):
        super().__init__(address, handler)
        self.runner = runner
        self._watchdog_timeout = watchdog_timeout
        self._heartbeat_lock = threading.Lock()
        self._last_heartbeat = time.monotonic()
        self._serving_done = threading.Event()

    def record_heartbeat(self) -> None:
        with self._heartbeat_lock:
            self._last_heartbeat = time.monotonic()

    def request_shutdown(self) -> None:
        """Stop the app and end `serve_forever`, from any thread, without blocking the caller."""
        # shutdown() waits for serve_forever to return, so it cannot run on a request thread.
        threading.Thread(target=self._stop_serving, daemon=True).start()

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        self._serving_done.clear()
        if self._watchdog_timeout is not None:
            self.record_heartbeat()
            threading.Thread(target=self._watch, daemon=True).start()
        try:
            super().serve_forever(poll_interval)
        finally:
            self._serving_done.set()

    def server_close(self):
        # No orphan: a normal stop (including Ctrl-C) takes the child down too.
        self.runner.stop()
        super().server_close()

    def handle_error(self, request, client_address) -> None:
        # Called inside the except block, so the traceback is attached.
        LOG.exception("Request from %s failed", client_address)

    def _stop_serving(self) -> None:
        self.runner.stop()
        self.shutdown()

    def _watch(self) -> None:
        """Sleep until the heartbeat deadline; shut down if it passed without a new heartbeat."""
        while True:
            with self._heartbeat_lock:
                remaining = self._last_heartbeat + self._watchdog_timeout - time.monotonic()
            if remaining <= 0:
                LOG.warning("No heartbeat for %g s; shutting down", self._watchdog_timeout)
                self._stop_serving()
                return
            if self._serving_done.wait(remaining):
                return


def make_server(
    port: int,
    config_dir: Path = config.DEFAULT_CONFIG_DIR,
    runner: process.AppRunner | None = None,
    watchdog_timeout: float | None = None,
) -> LauncherServer:
    """Validate the config (fail fast), then bind to loopback only."""
    config.load_workspace_root(config_dir)
    config.load_apps(config_dir)
    return LauncherServer(
        (HOST, port),
        partial(Handler, config_dir=config_dir),
        runner or process.AppRunner(),
        watchdog_timeout,
    )
