"""Host logic of the desktop client, without pywebview: pure functions, a fake backend, a fake server."""

import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from launcher.backend import process
from launcher.desktop import host

LIST = "http://127.0.0.1:8000/"
RUNNING = {"name": "Hello", "port": 9000, "url": "http://127.0.0.1:9000/"}


class FakeBackendServer:
    """A tiny loopback server: replies to heartbeat and health, records every request in `events`."""

    def __init__(self, events, running=None, health_status=200):
        outer = self
        self.running = running
        self.events = events

        class Handler(http.server.BaseHTTPRequestHandler):
            def _reply(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                outer.events.append(f"GET {self.path}")
                self._reply(health_status, {"status": "ok"})

            def do_POST(self):
                outer.events.append(f"POST {self.path}")
                if self.path == "/api/heartbeat":
                    self._reply(200, {"running": outer.running})
                else:
                    self._reply(200, {"status": "shutting_down"})

            def log_message(self, *args):
                pass

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()


class FakeBackendProcess:
    """Popen stand-in that appends what is done to it to the shared `events` list."""

    def __init__(self, events, exits_by_itself=True, exit_code=0):
        self.events = events
        self.exits_by_itself = exits_by_itself
        self.returncode = None
        self._exit_code = exit_code

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.events.append("wait")
        if self.returncode is None and not self.exits_by_itself:
            raise subprocess.TimeoutExpired("fake", timeout)
        self.returncode = self.returncode if self.returncode is not None else self._exit_code
        return self.returncode

    def terminate(self):
        self.events.append("terminate")
        self.exits_by_itself = True

    def kill(self):
        self.events.append("kill")
        self.exits_by_itself = True


class FakeWindow:
    def __init__(self, url, on_load=None):
        self.url = url
        self.loaded = []
        self._on_load = on_load

    def get_current_url(self):
        return self.url

    def load_url(self, url):
        self.loaded.append(url)
        self.url = url
        if self._on_load:
            self._on_load()


@pytest.mark.parametrize(
    ("current", "running", "expected"),
    [
        ("http://127.0.0.1:9000/", None, LIST),  # an app stopped itself or crashed
        ("http://127.0.0.1:9000/some/page", None, LIST),
        ("http://127.0.0.1:8001/", None, LIST),  # same host, another port is not the list
        (LIST, None, None),  # already on the list
        ("http://127.0.0.1:8000", None, None),  # no trailing slash is the same page
        ("http://127.0.0.1:8000/?x=1#top", None, None),  # query and fragment do not matter
        ("http://127.0.0.1:9000/", RUNNING, None),  # an app is running: leave the window alone
        (LIST, RUNNING, None),  # the Start click is on its way
        (None, None, None),  # page not loaded yet
        (None, RUNNING, None),
    ],
)
def test_next_url(current, running, expected):
    assert host.next_url(current, running, LIST) == expected


def test_urls():
    assert host.list_url(8123) == "http://127.0.0.1:8123/"
    assert host.api_url(8123, "/api/health") == "http://127.0.0.1:8123/api/health"


def test_backend_command_is_a_list_without_a_shell():
    command = host.backend_command(8123)
    assert command == [sys.executable, "-m", "launcher.backend", "--port", "8123", "--watchdog"]


def test_free_port_is_the_backend_one():
    assert host.pick_free_port is process.pick_free_port


@pytest.mark.parametrize(
    ("running", "current", "expected"),
    [(None, "http://127.0.0.1:9000/", "list"), (None, None, None), (RUNNING, "http://127.0.0.1:9000/", None)],
)
def test_heartbeat_step_against_a_fake_server(running, current, expected):
    events = []
    with FakeBackendServer(events, running=running) as server:
        target = host.heartbeat_step(server.port, current)
    assert target == (host.list_url(server.port) if expected == "list" else None)
    assert events == ["POST /api/heartbeat"]


def test_send_heartbeat_returns_the_running_app():
    with FakeBackendServer([], running=RUNNING) as server:
        assert host.send_heartbeat(server.port) == RUNNING


def test_heartbeat_to_a_closed_port_raises_oserror(free_port):
    with pytest.raises(OSError):
        host.send_heartbeat(free_port)


def test_watch_backend_navigates_back_to_the_list_then_stops():
    stop = threading.Event()
    with FakeBackendServer([], running=None) as server:
        window = FakeWindow("http://127.0.0.1:9000/", on_load=stop.set)
        result = host.watch_backend(server.port, FakeBackendProcess([]), window, stop, period=0.01)
    assert result is None
    assert window.loaded == [host.list_url(server.port)]


def test_watch_backend_survives_a_failed_heartbeat_and_stops(free_port):
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()
    window = FakeWindow("http://127.0.0.1:9000/")
    assert host.watch_backend(free_port, FakeBackendProcess([]), window, stop, period=0.01) is None
    assert window.loaded == []


def test_watch_backend_reports_the_exit_code_of_a_dead_backend(free_port):
    dead = FakeBackendProcess([])
    dead.returncode = 7
    window = FakeWindow(LIST)
    assert host.watch_backend(free_port, dead, window, threading.Event(), period=0.01) == 7


def test_launch_backend_succeeds_when_health_answers():
    script = (
        "import http.server, sys\n"
        "class H(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200); self.send_header('Content-Length','0'); self.end_headers()\n"
        "    def log_message(self, *a): pass\n"
        "http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n"
    )
    port = host.pick_free_port()
    backend = host.launch_backend(port, [sys.executable, "-c", script, str(port)], timeout=15)
    try:
        assert backend.poll() is None
    finally:
        process.terminate(backend)


def test_launch_backend_reports_the_exit_code_of_a_child_that_dies():
    command = [sys.executable, "-c", "import sys; sys.exit(3)"]
    with pytest.raises(host.BackendError, match="exit code 3"):
        host.launch_backend(host.pick_free_port(), command, timeout=15)


def test_launch_backend_times_out_and_terminates_a_child_that_never_answers(monkeypatch):
    terminated = []
    monkeypatch.setattr(host, "terminate", lambda child: (terminated.append(child), process.terminate(child)))
    command = [sys.executable, "-c", "import time; time.sleep(60)"]
    with pytest.raises(host.BackendError, match="did not answer GET /api/health"):
        host.launch_backend(host.pick_free_port(), command, timeout=0.5)
    assert len(terminated) == 1 and terminated[0].poll() is not None


def test_launch_backend_reports_a_missing_command():
    with pytest.raises(host.BackendError, match="Could not start the backend"):
        host.launch_backend(host.pick_free_port(), ["/no/such/program-xyz"], timeout=1)


def test_wait_for_health_ignores_a_non_200_until_timeout():
    with FakeBackendServer([], health_status=503) as server:
        with pytest.raises(host.BackendError, match="did not answer"):
            host.wait_for_health(server.port, FakeBackendProcess([]), timeout=0.3)


def test_shutdown_posts_then_waits_and_does_not_terminate_a_backend_that_exits():
    events = []
    backend = FakeBackendProcess(events, exits_by_itself=True)
    with FakeBackendServer(events) as server:
        host.shutdown_backend(server.port, backend, wait_seconds=1)
    assert events == ["POST /api/shutdown", "wait"]


def test_shutdown_terminates_a_backend_that_does_not_exit():
    events = []
    backend = FakeBackendProcess(events, exits_by_itself=False)
    with FakeBackendServer(events) as server:
        host.shutdown_backend(server.port, backend, wait_seconds=0.1)
    assert events == ["POST /api/shutdown", "wait", "terminate", "wait"]


def test_shutdown_is_best_effort_when_the_post_fails(free_port):
    events = []
    host.shutdown_backend(free_port, FakeBackendProcess(events, exits_by_itself=False), wait_seconds=0.1)
    assert events == ["wait", "terminate", "wait"]


def test_app_runner_start_uses_the_requested_port(free_port):
    runner = process.AppRunner()
    script = process.REPO_ROOT / "apps" / "hello_py" / "main.py"
    try:
        info = runner.start("Hello", sys.executable, script, process.REPO_ROOT, port=free_port)
        assert info["port"] == free_port
    finally:
        runner.stop()
    assert runner.running() is None


DESKTOP_FILES = sorted((Path(__file__).parents[2] / "launcher" / "desktop").glob("*.py"))


@pytest.mark.parametrize("path", DESKTOP_FILES, ids=lambda p: p.name)
def test_desktop_sources_compile(path):
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_desktop_package_has_the_expected_modules():
    assert {p.name for p in DESKTOP_FILES} == {"__init__.py", "__main__.py", "host.py", "run_script.py", "window.py"}
