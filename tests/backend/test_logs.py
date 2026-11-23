"""Rotating log wiring and draining of the child's output through logging."""

import json
import logging
import sys
import threading
import time
from pathlib import Path

import pytest

from launcher.backend import logs, process
from launcher.backend.server import make_server

NOISY_APP = (
    "import sys\n"
    "from pathlib import Path\n"
    "from launcher.scriptkit.python import parse_port, run_app\n"
    "for i in range(2000):\n"
    "    print(f'noise line {i} ' + 'x' * 100)\n"
    "print('caf\\u00e9 done', flush=True)\n"
    "sys.stdout.buffer.write(b'bad \\xff byte\\n'); sys.stdout.flush()\n"
    "print('to stderr', file=sys.stderr, flush=True)\n"
    "run_app(Path('.'), parse_port(sys.argv[1:]))\n"
)


@pytest.fixture
def log_file(tmp_path):
    path = tmp_path / "launcher.log"
    yield path
    logs.reset()


@pytest.fixture
def backend(tmp_path):
    repo_root = Path(__file__).parents[2]
    script = tmp_path / "noisy.py"
    script.write_text(NOISY_APP, encoding="utf-8")
    (tmp_path / ".env").write_text(f"WORKSPACE_ROOT={repo_root}\n", encoding="utf-8")
    apps = {"apps": [{"name": "Noisy", "script_path": str(script)}]}
    (tmp_path / "apps.json").write_text(json.dumps(apps), encoding="utf-8")
    server = make_server(0, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", server
    server.shutdown()
    server.server_close()
    thread.join()


def test_rotation_never_keeps_more_than_the_backup_count(log_file):
    logs.configure(log_file, max_bytes=500, backup_count=3)
    for number in range(200):
        logging.getLogger("launcher.test").info("line %d %s", number, "y" * 40)
    names = sorted(path.name for path in log_file.parent.glob("launcher.log*"))
    assert names == ["launcher.log", "launcher.log.1", "launcher.log.2", "launcher.log.3"]
    assert all(path.stat().st_size <= 600 for path in log_file.parent.glob("launcher.log*"))


def test_child_output_and_request_lines_reach_the_log_file(log_file, backend, call, wait_until):
    logs.configure(log_file, max_bytes=1_000_000, backup_count=3)
    base, server = backend
    started = call("POST", base + "/api/apps/0/start")[1]
    wait_until(lambda: "to stderr" in log_file.read_text(encoding="utf-8"))
    server.runner.stop()
    text = log_file.read_text(encoding="utf-8")
    assert "app: noisy.py: noise line 1999" in text  # drained, so the child never blocked on a full pipe
    assert "café done" in text and "bad � byte" in text  # decode errors are replaced
    assert "POST /api/apps/0/start" in text and "launcher.server" in text
    assert f"on port {started['port']}" in text and "exited with code" in text


def _read_log_files(directory):
    """Contents of every launcher.log* file; a file renamed away by a rotation mid-read is skipped."""
    texts = []
    for path in directory.glob("launcher.log*"):
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
    return texts


def test_child_output_is_rotated_with_the_rest(log_file, backend, call, wait_until):
    logs.configure(log_file, max_bytes=20_000, backup_count=3)
    base, server = backend
    call("POST", base + "/api/apps/0/start")
    wait_until(lambda: any("to stderr" in text for text in _read_log_files(log_file.parent)))
    server.runner.stop()
    # The drain thread may still be writing after stop(); wait for its last line so the files are stable.
    wait_until(lambda: any("exited with code" in text for text in _read_log_files(log_file.parent)))
    files = list(log_file.parent.glob("launcher.log*"))
    assert 1 < len(files) <= 4
    assert max(path.stat().st_size for path in files) <= 21_000


def test_reader_thread_ends_with_the_child_and_the_pipe_is_closed(log_file, backend, call, spawned):
    logs.configure(log_file)
    base, server = backend
    call("POST", base + "/api/apps/0/start")
    child = spawned[0]
    reader = server.runner._reader
    server.runner.stop()  # terminate() still works with a piped child
    assert child.poll() is not None
    assert not reader.is_alive()
    assert child.stdout.closed


def test_early_exit_child_leaves_no_reader_or_open_pipe(backend, call, spawned, tmp_path):
    base, server = backend
    boom = tmp_path / "boom.py"
    boom.write_text("print('about to fail')\nraise SystemExit(4)\n", encoding="utf-8")
    call("PUT", base + "/api/apps", {"apps": [{"name": "Boom", "script_path": str(boom)}]})
    assert call("POST", base + "/api/apps/0/start")[0] == 500
    deadline = time.monotonic() + 5
    while spawned[0].stdout is not None and not spawned[0].stdout.closed and time.monotonic() < deadline:
        time.sleep(0.05)
    assert spawned[0].stdout.closed


def test_uncaught_thread_exception_is_logged_and_the_hook_restored(log_file):
    original = threading.excepthook
    logs.configure(log_file)

    def explode():
        raise RuntimeError("kaboom")

    thread = threading.Thread(target=explode)
    thread.start()
    thread.join()
    logs.reset()
    assert threading.excepthook is original and sys.excepthook is sys.__excepthook__
    assert "kaboom" in log_file.read_text(encoding="utf-8") and "Traceback" in log_file.read_text(encoding="utf-8")
