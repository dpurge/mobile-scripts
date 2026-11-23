"""Host logic of the desktop client, without any window code (stdlib only, no `webview` import).

The desktop client simulates the Android client with the same four steps: pick a free port, start
the backend and poll `GET /api/health`, send `POST /api/heartbeat` every HEARTBEAT_SECONDS, and send
`POST /api/shutdown` on close. The window itself lives in `window.py`, so tests never need pywebview.
"""

import json
import logging
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from launcher.backend.process import HOST, REPO_ROOT, pick_free_port, terminate

HEARTBEAT_SECONDS = 3.0  # H, the approved heartbeat period
HEALTH_TIMEOUT_SECONDS = 15.0
HEALTH_POLL_SECONDS = 0.1
REQUEST_TIMEOUT_SECONDS = 2.0
SHUTDOWN_WAIT_SECONDS = 5.0
LOG = logging.getLogger("launcher.desktop")

# Talk to loopback directly: a proxy from the environment must not intercept it.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

__all__ = [
    "BackendError", "HEARTBEAT_SECONDS", "HEALTH_TIMEOUT_SECONDS", "api_url", "backend_command", "heartbeat_step",
    "install_stop_signals", "launch_backend", "list_url", "next_url", "pick_free_port", "send_heartbeat",
    "shutdown_backend", "wait_for_health", "watch_backend",
]


class BackendError(Exception):
    """The backend did not come up or died; the message says why."""


def list_url(port: int) -> str:
    return f"http://{HOST}:{port}/"


def api_url(port: int, path: str) -> str:
    return f"http://{HOST}:{port}{path}"


def _is_list_page(url: str, expected: str) -> bool:
    """True when `url` is the list page itself (query and fragment do not matter)."""
    left, right = urlsplit(url), urlsplit(expected)
    return (left.scheme, left.netloc, left.path or "/") == (right.scheme, right.netloc, right.path or "/")


def next_url(current_url: str | None, running: dict | None, list_url: str) -> str | None:
    """The URL the window must go to, or None to leave it alone.

    No app is running and the window is somewhere else (the app stopped itself, or crashed): go
    back to the list. An unknown current URL (page not loaded yet) is left alone.
    """
    if running is not None or current_url is None:
        return None
    return None if _is_list_page(current_url, list_url) else list_url


def backend_command(port: int) -> list[str]:
    return [sys.executable, "-m", "launcher.backend", "--port", str(port), "--watchdog"]


def launch_backend(
    port: int, command: list[str] | None = None, timeout: float = HEALTH_TIMEOUT_SECONDS
) -> subprocess.Popen:
    """Start the backend (no shell, from the repo root) and return it once `/api/health` answers."""
    command = command if command is not None else backend_command(port)
    try:
        backend = subprocess.Popen(command, cwd=REPO_ROOT)
    except OSError as error:
        raise BackendError(f"Could not start the backend ({command[0]}): {error}") from None
    LOG.info("Started backend (pid %d) on port %d", backend.pid, port)
    try:
        wait_for_health(port, backend, timeout)
    except BackendError:
        terminate(backend)
        raise
    return backend


def wait_for_health(port: int, backend: subprocess.Popen, timeout: float) -> None:
    """Poll `GET /api/health` until it answers 200; fail on timeout or when the backend exits."""
    deadline = time.monotonic() + timeout
    while True:
        exit_code = backend.poll()
        if exit_code is not None:
            raise BackendError(f"The backend exited during startup with exit code {exit_code}.")
        try:
            with _OPENER.open(api_url(port, "/api/health"), timeout=REQUEST_TIMEOUT_SECONDS) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass  # not listening yet
        if time.monotonic() >= deadline:
            raise BackendError(
                f"The backend did not answer GET /api/health on port {port} within {timeout:g} s."
            )
        time.sleep(HEALTH_POLL_SECONDS)


def send_heartbeat(port: int) -> dict | None:
    """POST /api/heartbeat and return the `running` value of the reply (None or `{name, port, url}`)."""
    request = urllib.request.Request(api_url(port, "/api/heartbeat"), data=b"", method="POST")
    with _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.load(response)["running"]


def heartbeat_step(port: int, current_url: str | None) -> str | None:
    """One heartbeat; returns the URL to navigate to, or None. Raises OSError if the backend is unreachable."""
    return next_url(current_url, send_heartbeat(port), list_url(port))


def watch_backend(port: int, backend: subprocess.Popen, window, stop: threading.Event,
                  period: float = HEARTBEAT_SECONDS) -> int | None:
    """Heartbeat loop of the host. `window` needs `get_current_url()` and `load_url(url)`.

    Runs until `stop` is set. Returns the backend's exit code if it died, else None.
    """
    while True:
        exit_code = backend.poll()
        if exit_code is not None:
            LOG.error("The backend exited unexpectedly with exit code %s", exit_code)
            return exit_code
        try:
            target = heartbeat_step(port, window.get_current_url())
        except (OSError, ValueError, KeyError) as error:
            LOG.warning("Heartbeat failed: %s", error)
        else:
            if target is not None:
                LOG.info("Navigating to %s (no app is running)", target)
                window.load_url(target)
        if stop.wait(period):
            return None


def shutdown_backend(port: int, backend: subprocess.Popen, wait_seconds: float = SHUTDOWN_WAIT_SECONDS) -> None:
    """Ask the backend to exit (best effort), wait for it, and terminate it if it does not."""
    request = urllib.request.Request(api_url(port, "/api/shutdown"), data=b"", method="POST")
    try:
        _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS).close()
    except (OSError, urllib.error.URLError) as error:
        LOG.warning("POST /api/shutdown failed: %s", error)
    try:
        backend.wait(timeout=wait_seconds)
    except subprocess.TimeoutExpired:
        LOG.warning("The backend did not exit within %g s; terminating it", wait_seconds)
        terminate(backend)
    LOG.info("Backend exited with code %s", backend.returncode)


def install_stop_signals(stop: threading.Event) -> None:
    """SIGINT and SIGTERM set `stop`, so the client closes the window and cleans up. Main thread only."""
    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), lambda signum, frame: stop.set())
