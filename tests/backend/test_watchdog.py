"""Heartbeat, watchdog and shutdown, with the server in a thread and a 0.5 s watchdog."""

import json
import threading
import time
from pathlib import Path

import pytest

from launcher.backend.server import make_server

REPO_ROOT = Path(__file__).parents[2]
APPS = {"apps": [{"name": "Hello (Python)", "script_path": "apps/hello_py/main.py"}]}
TIMEOUT = 0.5


@pytest.fixture
def start_backend(tmp_path):
    """`start_backend(watchdog_timeout=None)` -> (base_url, serving thread); all are torn down."""
    (tmp_path / ".env").write_text(f"WORKSPACE_ROOT={REPO_ROOT}\n", encoding="utf-8")
    (tmp_path / "apps.json").write_text(json.dumps(APPS), encoding="utf-8")
    started = []

    def _start(watchdog_timeout=None):
        server = make_server(0, tmp_path, watchdog_timeout=watchdog_timeout)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}", thread

    yield _start
    for server, thread in started:
        server.shutdown()  # returns at once when serving has already ended
        server.server_close()
        thread.join()


def test_heartbeat_returns_the_running_state_like_api_running(start_backend, call, spawned):
    base, _ = start_backend()
    assert call("POST", base + "/api/heartbeat") == (200, {"running": None})
    _, started = call("POST", base + "/api/apps/0/start")
    assert call("POST", base + "/api/heartbeat") == (200, {"running": started})
    assert call("GET", base + "/api/running") == (200, {"running": started})


def test_watchdog_stops_serving_and_the_child_after_the_timeout(start_backend, call, spawned):
    base, thread = start_backend(watchdog_timeout=TIMEOUT)
    assert call("POST", base + "/api/apps/0/start")[0] == 200
    assert spawned[0].poll() is None
    thread.join(timeout=10)
    assert not thread.is_alive(), "serve_forever did not return after the watchdog timeout"
    assert spawned[0].poll() is not None


def test_startup_counts_as_the_first_heartbeat(start_backend):
    began = time.monotonic()
    _, thread = start_backend(watchdog_timeout=TIMEOUT)
    thread.join(timeout=10)
    elapsed = time.monotonic() - began
    assert not thread.is_alive()
    assert TIMEOUT - 0.05 <= elapsed < 5


def test_regular_heartbeats_keep_the_backend_alive_until_they_stop(start_backend, call):
    base, thread = start_backend(watchdog_timeout=TIMEOUT)
    beats_until = time.monotonic() + 3 * TIMEOUT
    while time.monotonic() < beats_until:
        call("POST", base + "/api/heartbeat")
        assert thread.is_alive()
        time.sleep(0.1)
    thread.join(timeout=10)
    assert not thread.is_alive(), "no heartbeats for the timeout should have stopped the backend"


def test_watchdog_is_off_by_default(start_backend, call):
    base, thread = start_backend()
    thread.join(timeout=3 * TIMEOUT)
    assert thread.is_alive()
    assert call("GET", base + "/api/health") == (200, {"status": "ok"})


def test_shutdown_answers_then_stops_serving_and_the_child(start_backend, call, spawned):
    base, thread = start_backend()
    assert call("POST", base + "/api/apps/0/start")[0] == 200
    assert call("POST", base + "/api/shutdown") == (200, {"status": "shutting_down"})
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert spawned[0].poll() is not None
