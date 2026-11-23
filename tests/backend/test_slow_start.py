"""While an app is still starting, the backend keeps answering and a stop leaves nothing behind."""

import json
import threading
import time

import pytest

from launcher.backend.server import make_server

SLOW_APP = (
    "import socket, sys, time\n"
    "port = int(sys.argv[sys.argv.index('--port') + 1])\n"
    "time.sleep(2)\n"
    "server = socket.socket()\n"
    "server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
    "server.bind(('127.0.0.1', port))\n"
    "server.listen()\n"
    "time.sleep(60)\n"
)
ANSWER_WITHIN_SECONDS = 0.5


@pytest.fixture
def backend(tmp_path):
    script = tmp_path / "slow.py"
    script.write_text(SLOW_APP, encoding="utf-8")
    (tmp_path / ".env").write_text(f"WORKSPACE_ROOT={tmp_path}\n", encoding="utf-8")
    apps = {"apps": [{"name": "Slow", "script_path": str(script)}]}
    (tmp_path / "apps.json").write_text(json.dumps(apps), encoding="utf-8")
    server = make_server(0, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", server
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def starting_request(backend, call, wait_until, spawned):
    """Begin `POST /api/apps/0/start` on a thread once the child is spawned; yield `answer()`.

    `answer()` waits for that request to finish and returns its (status, body).
    """
    base, _ = backend
    result = []
    thread = threading.Thread(target=lambda: result.append(call("POST", base + "/api/apps/0/start")))
    thread.start()
    wait_until(lambda: len(spawned) == 1)

    def answer():
        thread.join(timeout=20)
        assert result, "the start request did not finish within 20 s"
        return result[0]

    yield answer
    thread.join(timeout=20)


def timed_call(call, method, url):
    began = time.monotonic()
    status, body = call(method, url, None if method == "GET" else {})
    return status, body, time.monotonic() - began


def test_heartbeat_and_running_answer_while_an_app_is_starting(backend, call, starting_request):
    base, _ = backend
    status, body, seconds = timed_call(call, "POST", base + "/api/heartbeat")
    assert (status, body["running"]) == (200, None) and seconds < ANSWER_WITHIN_SECONDS
    status, body, seconds = timed_call(call, "GET", base + "/api/running")
    assert (status, body["running"]) == (200, None) and seconds < ANSWER_WITHIN_SECONDS
    starting_request()  # waits for the start to finish, so the child is listening and registered
    assert call("GET", base + "/api/running")[1]["running"]["name"] == "Slow"


def test_second_start_while_starting_is_409(backend, call, starting_request):
    base, _ = backend
    status, body = call("POST", base + "/api/apps/0/start")
    assert status == 409 and "already starting" in body["error"]
    assert starting_request()[0] == 200


def test_stop_during_starting_leaves_no_process(backend, call, starting_request, spawned):
    base, server = backend
    server.runner.stop()
    assert spawned[0].poll() is not None
    status, body = starting_request()
    assert status == 500 and "stopped during startup" in body["error"]
    assert server.runner.running() is None
    assert call("POST", base + "/api/heartbeat", {})[1]["running"] is None
