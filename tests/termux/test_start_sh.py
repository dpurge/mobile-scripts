"""launcher/termux/start.sh under bash, with fake termux-wake-lock/unlock and a python shim.

Skipped only on Windows ('Termux-only script'): the script needs bash and POSIX signals.
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
START_SH = REPO_ROOT / "launcher" / "termux" / "start.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Termux-only script")


def test_start_sh_has_lf_line_endings_only():
    # A CRLF checkout breaks the shebang and every command in the script.
    assert b"\r" not in START_SH.read_bytes()


@pytest.fixture
def termux(tmp_path, fake_repo):
    """Env with fake Termux commands first on PATH; `.run(*args)` starts start.sh, killed in teardown."""
    assert BASH, "bash is required to test start.sh"
    shutil.copytree(REPO_ROOT / "launcher" / "termux", fake_repo / "launcher" / "termux", dirs_exist_ok=True)
    bin_dir, home = tmp_path / "bin", tmp_path / "home"
    bin_dir.mkdir()
    home.mkdir()
    wake_log = tmp_path / "wake.log"
    for name in ("termux-wake-lock", "termux-wake-unlock"):
        script = bin_dir / name
        script.write_text(f'#!/bin/sh\necho {name} >> "{wake_log}"\n', encoding="utf-8")
        script.chmod(0o755)
    shim = bin_dir / "python"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "HOME": str(home)}
    children = []

    class Termux:
        pass

    handle = Termux()
    handle.home = home
    handle.log = home / "launcher-backend.log"
    handle.start_error_log = home / "launcher-backend.start-error.log"
    handle.wake_calls = lambda: wake_log.read_text().split() if wake_log.exists() else []

    def run(*args):
        child = subprocess.Popen([BASH, str(fake_repo / "launcher" / "termux" / "start.sh"), *args], env=env)
        children.append(child)
        return child

    handle.run = run
    yield handle
    for child in children:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)


def wait_for(predicate, seconds=15.0, what="condition"):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    pytest.fail(f"{what} not met within {seconds} s")


def answers(url):
    try:
        urllib.request.urlopen(url, timeout=1).close()
        return True
    except (urllib.error.URLError, OSError):
        return False


def post(url):
    with urllib.request.urlopen(urllib.request.Request(url, data=b"", method="POST"), timeout=10) as r:
        return r.read()


def test_wake_lock_before_backend_and_unlock_after_shutdown(termux, free_port):
    child = termux.run(str(free_port))
    base = f"http://127.0.0.1:{free_port}"
    wait_for(lambda: answers(base + "/api/health"), what="/api/health")
    assert termux.wake_calls() == ["termux-wake-lock"]
    assert json.loads(post(base + "/api/shutdown")) == {"status": "shutting_down"}
    assert child.wait(timeout=15) == 0
    assert termux.wake_calls() == ["termux-wake-lock", "termux-wake-unlock"]
    log = termux.log.read_text(encoding="utf-8")
    assert f"starting backend on port {free_port}" in log and "Serving on" in log
    # The backend wrote the file itself (--log-file), including request lines.
    assert "launcher.server" in log and "wake lock released" in log


def test_sigterm_to_start_sh_unlocks_and_stops_backend_and_app(termux, free_port):
    child = termux.run(str(free_port))
    base = f"http://127.0.0.1:{free_port}"
    wait_for(lambda: answers(base + "/api/health"), what="/api/health")
    app_url = json.loads(post(base + "/api/apps/0/start"))["url"]
    child.send_signal(signal.SIGTERM)
    assert child.wait(timeout=15) == 143
    assert termux.wake_calls() == ["termux-wake-lock", "termux-wake-unlock"]
    wait_for(lambda: not answers(base + "/api/health"), what="backend port closed")
    wait_for(lambda: not answers(app_url), what="app port closed")


def test_bad_port_exits_2_and_logs_the_reason(termux):
    for argument in ("abc", "12x"):
        assert termux.run(argument).wait(timeout=15) == 2
    assert termux.run().wait(timeout=15) == 2
    log = termux.log.read_text(encoding="utf-8")
    assert "port must be a number, got 'abc'" in log and "got ''" in log
    assert termux.wake_calls() == []


def test_start_error_log_is_truncated_at_each_start(termux, free_port):
    termux.start_error_log.write_text("old failure\n" * 100, encoding="utf-8")
    child = termux.run(str(free_port))
    base = f"http://127.0.0.1:{free_port}"
    wait_for(lambda: answers(base + "/api/health"), what="/api/health")
    post(base + "/api/shutdown")
    assert child.wait(timeout=15) == 0
    assert termux.start_error_log.read_text(encoding="utf-8") == ""


def test_python_stderr_before_logging_goes_to_the_start_error_log(termux, free_port, tmp_path):
    (tmp_path / "bin" / "python").write_text("#!/bin/sh\necho 'no module named x' >&2\nexit 3\n", encoding="utf-8")
    assert termux.run(str(free_port)).wait(timeout=15) == 3
    assert "no module named x" in termux.start_error_log.read_text(encoding="utf-8")
    assert "backend exited with code 3" in termux.log.read_text(encoding="utf-8")
    assert termux.wake_calls() == ["termux-wake-lock", "termux-wake-unlock"]


def test_script_rotates_the_log_with_mv_and_drops_the_oldest(termux):
    termux.log.write_text("current " * 140_000, encoding="utf-8")  # above the 1,000,000 byte limit
    for number, marker in enumerate(["one", "two", "three"], start=1):
        Path(f"{termux.log}.{number}").write_text(marker, encoding="utf-8")
    assert termux.run("bad").wait(timeout=15) == 2
    backups = sorted(path.name for path in termux.home.glob("launcher-backend.log*"))
    assert backups == ["launcher-backend.log", "launcher-backend.log.1", "launcher-backend.log.2", "launcher-backend.log.3"]
    assert Path(f"{termux.log}.1").read_text(encoding="utf-8").startswith("current ")
    assert Path(f"{termux.log}.2").read_text(encoding="utf-8") == "one"
    assert Path(f"{termux.log}.3").read_text(encoding="utf-8") == "two"  # "three" was dropped
    assert "port must be a number" in termux.log.read_text(encoding="utf-8")
    assert termux.log.stat().st_size < 1000


def test_script_does_not_rotate_a_small_log(termux):
    termux.log.write_text("small\n", encoding="utf-8")
    assert termux.run("bad").wait(timeout=15) == 2
    assert not Path(f"{termux.log}.1").exists()
    assert termux.log.read_text(encoding="utf-8").startswith("small\n")
