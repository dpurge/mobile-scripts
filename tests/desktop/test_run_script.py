"""`run_script.main` with a fake window module, so no pywebview and no GUI are needed."""

import sys
import types

import pytest

from launcher.backend import config
from launcher.desktop import run_script

LISTENING_APP = (
    "import os, socket, sys, time\n"
    "port = int(sys.argv[sys.argv.index('--port') + 1])\n"
    "open('cwd.txt', 'w').write(os.getcwd())\n"
    "server = socket.socket()\n"
    "server.bind(('127.0.0.1', port))\n"
    "server.listen()\n"
    "time.sleep(60)\n"
)


@pytest.fixture
def window_returns_at_once(monkeypatch):
    window = types.ModuleType("launcher.desktop.window")
    window.run_window = lambda url, watch: None
    monkeypatch.setitem(sys.modules, "launcher.desktop.window", window)


def use_config(monkeypatch, tmp_path, workspace):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    if workspace is not None:
        (config_dir / ".env").write_text(f"WORKSPACE_ROOT={workspace}\n", encoding="utf-8")
    monkeypatch.setattr(config, "DEFAULT_CONFIG_DIR", config_dir)


def test_app_runs_in_the_workspace_root(monkeypatch, tmp_path, window_returns_at_once, spawned):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    use_config(monkeypatch, tmp_path, workspace)
    script = tmp_path / "listening.py"
    script.write_text(LISTENING_APP, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["run_script", str(script)])
    assert run_script.main() == 0
    assert (workspace / "cwd.txt").read_text(encoding="utf-8") == str(workspace.resolve())
    assert [child.poll() is not None for child in spawned] == [True]  # the window closed, so the app stopped


def test_missing_env_file_fails_fast_naming_the_example(
    monkeypatch, tmp_path, window_returns_at_once, spawned, caplog
):
    use_config(monkeypatch, tmp_path, None)
    monkeypatch.setattr(sys, "argv", ["run_script", str(tmp_path / "any.py")])
    assert run_script.main() == 1
    assert "config/.env.example" in caplog.text and spawned == []
