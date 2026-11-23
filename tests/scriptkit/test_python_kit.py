import socket
import threading
import time

import pytest

from launcher.scriptkit.python import kit, parse_port, run_app, stop


def test_parse_port_reads_the_option():
    assert parse_port(["--port", "8123"]) == 8123


@pytest.mark.parametrize("argv", [[], ["--port"], ["--port", "abc"]])
def test_parse_port_exits_on_bad_input(argv, capsys):
    with pytest.raises(SystemExit) as raised:
        parse_port(argv)
    assert raised.value.code == 2
    assert "--port" in capsys.readouterr().err


def test_stop_called_from_the_app_ends_run_app(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    thread = threading.Thread(target=run_app, args=(tmp_path, port), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while kit._active_server is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert kit._active_server is not None, "run_app did not start serving within 10 s"
    stop()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert kit._active_server is None


def test_stop_without_a_running_server_does_nothing():
    stop()
