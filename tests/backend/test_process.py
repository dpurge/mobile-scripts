import sys
from pathlib import Path

import pytest

from launcher.backend import process


def test_python_script_uses_current_interpreter():
    assert process.select_interpreter(Path("a/b.py")) == sys.executable


@pytest.mark.parametrize("name", ["a.js", "a.mjs", "A.MJS"])
def test_node_scripts_use_node_from_path(monkeypatch, name):
    monkeypatch.setattr(process.shutil, "which", lambda command: f"/bin/{command}")
    assert process.select_interpreter(Path(name)) == "/bin/node"


def test_missing_node_gives_clear_error(monkeypatch):
    monkeypatch.setattr(process.shutil, "which", lambda command: None)
    with pytest.raises(process.LaunchError, match="node was not found on PATH"):
        process.select_interpreter(Path("a.js"))


@pytest.mark.parametrize("name", ["a.txt", "a", "a.pyc"])
def test_unknown_extension_is_rejected(name):
    with pytest.raises(process.LaunchError, match="Unsupported"):
        process.select_interpreter(Path(name))


def test_missing_script_file_is_rejected(tmp_path):
    with pytest.raises(process.LaunchError, match="not found"):
        process.require_script_file(tmp_path / "nope.py")


def test_free_port_is_usable():
    assert 0 < process.pick_free_port() < 65536


def test_env_puts_repo_root_first_on_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/other")
    parts = process.app_env()["PYTHONPATH"].split(process.os.pathsep)
    assert parts == [str(process.REPO_ROOT), "/other"]
    monkeypatch.delenv("PYTHONPATH")
    assert process.app_env()["PYTHONPATH"] == str(process.REPO_ROOT)


def test_early_exit_is_reported_and_leaves_no_child(tmp_path, spawned):
    script = tmp_path / "boom.py"
    script.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    runner = process.AppRunner()
    with pytest.raises(process.StartError, match="exit code 3"):
        runner.start("Boom", sys.executable, script, tmp_path)
    assert runner.running() is None
    assert [child.poll() for child in spawned] == [3]


def test_start_timeout_kills_child(tmp_path, spawned):
    script = tmp_path / "idle.py"
    script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    runner = process.AppRunner(start_timeout=0.5)
    with pytest.raises(process.StartError, match="did not accept connections.*exit code"):
        runner.start("Idle", sys.executable, script, tmp_path)
    assert runner.running() is None
    assert all(child.poll() is not None for child in spawned) and spawned


def test_unlaunchable_interpreter_is_a_start_error(tmp_path):
    with pytest.raises(process.StartError, match="Could not start"):
        process.AppRunner().start("X", str(tmp_path / "no-such-program"), tmp_path / "a.py", tmp_path)
