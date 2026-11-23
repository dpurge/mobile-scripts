"""Start and stop the real example apps as subprocesses, through the backend's HTTP API."""

import http.client
import json
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from launcher.backend import process
from launcher.backend.server import make_server

REPO_ROOT = Path(__file__).parents[2]
APPS = {
    "apps": [
        {"name": "Hello (Python)", "script_path": "apps/hello_py/main.py"},
        {"name": "Hello (Node)", "script_path": "apps/hello_js/main.mjs"},
    ]
}


@pytest.fixture
def backend(tmp_path):
    """Yield (base_url, server, config_dir); the workspace is the real repo."""
    (tmp_path / ".env").write_text(f"WORKSPACE_ROOT={REPO_ROOT}\n", encoding="utf-8")
    (tmp_path / "apps.json").write_text(json.dumps(APPS), encoding="utf-8")
    server = make_server(0, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", server, tmp_path
    server.shutdown()
    server.server_close()
    thread.join()


def require_node():
    # Fails, never skips: the Node helper and hello_js are part of the contract.
    if shutil.which("node") is None:
        pytest.fail("`node` is not on PATH; install Node to test the .mjs app (hello_js)")


def raw_get(url, path):
    """GET without client-side path normalisation, to probe traversal."""
    parts = urllib.parse.urlsplit(url)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


@pytest.mark.parametrize(
    ("index", "language"), [(0, "Python"), (1, "JavaScript")], ids=["hello_py", "hello_js"]
)
def test_start_serve_and_stop_from_the_page(backend, call, wait_until, spawned, index, language):
    if index == 1:
        require_node()
    base, _, _ = backend
    status, started = call("POST", f"{base}/api/apps/{index}/start")
    assert status == 200, started
    app_url = started["url"]
    assert started["name"] == APPS["apps"][index]["name"]
    assert app_url == f"http://127.0.0.1:{started['port']}/"
    assert call("GET", base + "/api/running") == (200, {"running": started})

    with urllib.request.urlopen(app_url, timeout=10) as page:
        assert page.status == 200 and b"<hello-page>" in page.read()
    status, info = call("GET", app_url + "api/info")
    assert status == 200 and info["language"] == language and info["runtime"]
    for path, content_type in [
        ("_launcher/vendor/lit.js", "text/javascript"),
        ("_launcher/src/widgets/stop-button.js", "text/javascript"),
        ("_launcher/styles/stop-button.css", "text/css"),
        ("ui-missing.html", None),
    ]:
        try:
            with urllib.request.urlopen(app_url + path, timeout=10) as response:
                assert response.headers["Content-Type"].startswith(content_type)
                assert response.headers["Cache-Control"] == "no-cache"
        except urllib.error.HTTPError as error:
            assert content_type is None and error.code == 404

    assert call("POST", f"{base}/api/apps/{index}/start")[0] == 409
    assert call("POST", f"{base}/api/apps/{1 - index}/start")[0] == 409

    assert call("POST", app_url + "_launcher/stop") == (200, {"status": "stopping"})
    wait_until(lambda: call("GET", base + "/api/running")[1] == {"running": None})
    assert [child.wait(timeout=10) for child in spawned] == [0]


@pytest.mark.parametrize("script", ["main.py", "main.mjs"])
def test_app_pages_cannot_read_outside_their_directories(backend, call, spawned, script):
    if script.endswith(".mjs"):
        require_node()
    base, _, _ = backend
    _, started = call("POST", f"{base}/api/apps/{0 if script == 'main.py' else 1}/start")
    for path in [
        "/_launcher/..%2f..%2fpyproject.toml",
        "/_launcher/%2e%2e/%2e%2e/pyproject.toml",
        "/..%2f..%2f..%2fpyproject.toml",
        "/%2e%2e/%2e%2e/%2e%2e/pyproject.toml",
    ]:
        status, body = raw_get(started["url"], path)
        assert status in (400, 403, 404) and b"[project]" not in body, path


def test_start_with_bad_index_is_404(backend, call):
    base, _, _ = backend
    assert call("POST", base + "/api/apps/9/start")[0] == 404
    assert call("POST", base + "/api/apps/x/start")[0] == 404


def test_start_with_unknown_extension_or_missing_file_is_400(backend, call):
    base, _, config_dir = backend
    (config_dir / "notes.txt").write_text("x", encoding="utf-8")
    apps = {"apps": [
        {"name": "T", "script_path": str(config_dir / "notes.txt")},
        {"name": "M", "script_path": str(config_dir / "missing.py")},
    ]}
    assert call("PUT", base + "/api/apps", apps)[0] == 200
    status, payload = call("POST", base + "/api/apps/0/start")
    assert status == 400 and "Unsupported" in payload["error"]
    status, payload = call("POST", base + "/api/apps/1/start")
    assert status == 400 and "not found" in payload["error"]


def test_start_js_without_node_is_400(backend, call, monkeypatch):
    base, _, config_dir = backend
    monkeypatch.setattr(process.shutil, "which", lambda command: None)
    status, payload = call("POST", base + "/api/apps/1/start")
    assert status == 400 and "node was not found on PATH" in payload["error"]


def test_early_exit_gives_500_and_no_orphan(backend, call, spawned):
    base, _, config_dir = backend
    script = config_dir / "boom.py"
    script.write_text("import sys\nsys.exit(4)\n", encoding="utf-8")
    call("PUT", base + "/api/apps", {"apps": [{"name": "Boom", "script_path": str(script)}]})
    status, payload = call("POST", base + "/api/apps/0/start")
    assert status == 500 and "exit code 4" in payload["error"]
    assert call("GET", base + "/api/running") == (200, {"running": None})
    assert [child.poll() for child in spawned] == [4]


def test_crashed_app_is_reported_as_not_running(backend, call, wait_until, spawned):
    base, _, config_dir = backend
    script = config_dir / "crash.py"
    script.write_text(
        "import os, sys, threading\n"
        "from pathlib import Path\n"
        "from launcher.scriptkit.python import parse_port, run_app\n"
        "threading.Timer(0.5, lambda: os._exit(7)).start()\n"
        "run_app(Path('.'), parse_port(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    call("PUT", base + "/api/apps", {"apps": [{"name": "Crash", "script_path": str(script)}]})
    assert call("POST", base + "/api/apps/0/start")[0] == 200
    wait_until(lambda: call("GET", base + "/api/running")[1] == {"running": None})
    assert spawned[0].returncode == 7


def test_backend_stop_terminates_the_child(backend, call, spawned):
    base, server, _ = backend
    assert call("POST", base + "/api/apps/0/start")[0] == 200
    assert spawned[0].poll() is None
    server.shutdown()
    server.server_close()
    assert spawned[0].poll() is not None
