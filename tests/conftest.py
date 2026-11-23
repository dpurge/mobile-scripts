import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]


@pytest.fixture
def fake_repo(tmp_path):
    """A throwaway checkout (launcher, example apps, own config) so process-level tests are hermetic."""
    root = tmp_path / "repo"
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(REPO_ROOT / "launcher", root / "launcher", ignore=ignore)
    for app in ("hello_py", "hello_js"):
        shutil.copytree(REPO_ROOT / "apps" / app, root / "apps" / app, ignore=ignore)
    (root / "config").mkdir()
    (root / "config" / ".env").write_text(f"WORKSPACE_ROOT={root}\n", encoding="utf-8")
    apps = {"apps": [{"name": "Hello (Python)", "script_path": "apps/hello_py/main.py"}]}
    (root / "config" / "apps.json").write_text(json.dumps(apps), encoding="utf-8")
    return root


@pytest.fixture
def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def spawned(monkeypatch):
    """Records every child process the backend starts, so tests can prove none is left running."""
    real_popen = subprocess.Popen
    created = []

    class RecordingPopen(real_popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    return created
