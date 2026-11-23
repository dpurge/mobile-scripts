import json
import threading
import urllib.error
import urllib.request

import pytest

from launcher.backend.server import make_server

APPS = {"apps": [{"name": "Hello", "script_path": "apps/hello/main.py"}]}


@pytest.fixture
def base_url(tmp_path):
    (tmp_path / ".env").write_text("WORKSPACE_ROOT=/w\n", encoding="utf-8")
    (tmp_path / "apps.json").write_text(json.dumps(APPS), encoding="utf-8")
    server = make_server(0, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def get(url):
    try:
        return urllib.request.urlopen(url, timeout=5)
    except urllib.error.HTTPError as error:
        return error


def test_health(base_url):
    with get(base_url + "/api/health") as response:
        assert response.status == 200
        assert json.load(response) == {"status": "ok"}


def test_apps(base_url):
    with get(base_url + "/api/apps") as response:
        assert json.load(response) == APPS


def test_unknown_api_path_is_json_404(base_url):
    with get(base_url + "/api/nope") as response:
        assert response.status == 404
        assert response.headers["Content-Type"] == "application/json"
        assert "error" in json.load(response)


def test_static_index_is_served(base_url):
    with get(base_url + "/") as response:
        assert response.status == 200
        assert b"<app-list>" in response.read()


def test_static_files_are_not_cached(base_url):
    with get(base_url + "/styles/global.css") as response:
        assert response.headers["Cache-Control"] == "no-cache"


def test_vendored_lit_is_served(base_url):
    with get(base_url + "/vendor/lit.js") as response:
        assert response.status == 200
        assert b"LitElement" in response.read()


def test_invalid_config_fails_fast(tmp_path):
    from launcher.backend.config import ConfigError

    with pytest.raises(ConfigError):
        make_server(0, tmp_path)


def test_put_replaces_list_and_persists(base_url, tmp_path, call):
    new = {"apps": [{"name": "B", "script_path": "b.py"}, {"name": "A", "script_path": "a.py"}]}
    assert call("PUT", base_url + "/api/apps", new) == (200, new)
    assert call("GET", base_url + "/api/apps") == (200, new)
    assert json.loads((tmp_path / "apps.json").read_text(encoding="utf-8")) == new
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []


def test_put_accepts_empty_list(base_url, call):
    assert call("PUT", base_url + "/api/apps", {"apps": []}) == (200, {"apps": []})


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"apps": "x"},
        {"apps": [{"name": "", "script_path": "a.py"}]},
        {"apps": [{"name": "A", "script_path": "  "}]},
        {"apps": [{"name": "A"}]},
        {"apps": [{"name": 1, "script_path": "a.py"}]},
        [],
    ],
)
def test_put_rejects_invalid_body_and_keeps_file(base_url, tmp_path, call, body):
    before = (tmp_path / "apps.json").read_text(encoding="utf-8")
    status, payload = call("PUT", base_url + "/api/apps", body)
    assert status == 400 and payload["error"]
    assert (tmp_path / "apps.json").read_text(encoding="utf-8") == before


def test_put_requires_json_content_type(base_url, call):
    status, payload = call("PUT", base_url + "/api/apps", raw=b'{"apps": []}', content_type="text/plain")
    assert status == 400 and "application/json" in payload["error"]


def test_put_rejects_malformed_json(base_url, call):
    status, payload = call("PUT", base_url + "/api/apps", raw=b"{nope")
    assert status == 400 and payload["error"]


def test_put_to_unknown_path_is_404(base_url, call):
    assert call("PUT", base_url + "/api/nope", {"apps": []})[0] == 404
