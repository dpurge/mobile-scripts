"""`python -m launcher.backend` as a real process: exit code after /api/shutdown and the watchdog."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def run_backend(fake_repo, free_port):
    """`run_backend(*extra_args)` -> (Popen, base_url) once /api/health answers; killed in teardown."""
    children = []

    def _run(*extra_args):
        child = subprocess.Popen(
            [sys.executable, "-m", "launcher.backend", "--port", str(free_port), *extra_args],
            cwd=fake_repo,
            env={"PYTHONPATH": str(fake_repo), "PATH": ""},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        children.append(child)
        base = f"http://127.0.0.1:{free_port}"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1).close()
                return child, base
            except (urllib.error.URLError, OSError):
                time.sleep(0.05)
        pytest.fail("backend did not answer /api/health within 15 s")

    yield _run
    for child in children:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        child.stderr.close()


def post(url):
    request = urllib.request.Request(url, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read()


def test_shutdown_exits_with_code_0_and_with_the_app_stopped(run_backend):
    child, base = run_backend("--watchdog")
    status, body = post(base + "/api/apps/0/start")
    assert status == 200
    app_url = json.loads(body)["url"]
    assert post(base + "/api/shutdown") == (200, b'{"status": "shutting_down"}')
    assert child.wait(timeout=15) == 0
    with pytest.raises(OSError):
        urllib.request.urlopen(app_url, timeout=2)


def test_without_the_flag_there_is_no_watchdog_exit(run_backend):
    child, base = run_backend()
    with pytest.raises(subprocess.TimeoutExpired):
        child.wait(timeout=1)
    post(base + "/api/shutdown")
    assert child.wait(timeout=15) == 0


def test_without_log_file_nothing_is_written_and_lines_go_to_stderr(run_backend, fake_repo):
    child, base = run_backend()
    post(base + "/api/shutdown")
    assert child.wait(timeout=15) == 0
    stderr = child.stderr.read().decode("utf-8")
    child.stderr.close()
    assert "Serving on" in stderr and "Backend stopped" in stderr
    assert not list(fake_repo.rglob("*.log*"))


def test_with_log_file_the_lines_go_to_the_file_not_stderr(run_backend, fake_repo):
    log_file = fake_repo / "backend.log"
    child, base = run_backend("--log-file", str(log_file))
    post(base + "/api/shutdown")
    assert child.wait(timeout=15) == 0
    assert child.stderr.read() == b""
    child.stderr.close()
    text = log_file.read_text(encoding="utf-8")
    assert "Serving on" in text and "Shutdown requested" in text and "Backend stopped" in text
