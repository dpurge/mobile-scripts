"""Starting, watching and stopping the one running app (stdlib only, Windows-safe).

No `preexec_fn` and no process groups: `Popen.terminate()` and `kill()` work on every platform.
"""

import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

HOST = "127.0.0.1"
START_TIMEOUT_SECONDS = 10.0
TERMINATE_GRACE_SECONDS = 5.0
REPO_ROOT = Path(__file__).parents[2]
PYTHON_EXTENSIONS = {".py"}
NODE_EXTENSIONS = {".js", ".mjs"}
LOG = logging.getLogger("launcher.process")
APP_LOG = logging.getLogger("app")
READER_JOIN_SECONDS = 2.0


class LaunchError(ValueError):
    """The app cannot be launched because of its path or the machine; the caller maps it to 400."""


class AlreadyRunning(Exception):
    """Another app is running; only one runs at a time (409)."""


class StartError(Exception):
    """The child failed to come up; it has been killed (500)."""


def select_interpreter(script: Path) -> str:
    """Pick the program that runs `script`, by file extension only."""
    extension = script.suffix.lower()
    if extension in PYTHON_EXTENSIONS:
        return sys.executable
    if extension in NODE_EXTENSIONS:
        node = shutil.which("node")
        if node is None:
            raise LaunchError("node was not found on PATH; install Node to run .js/.mjs apps")
        return node
    raise LaunchError(
        f"Unsupported script type '{script.suffix}' for {script.name}; use .py, .js or .mjs."
    )


def require_script_file(script: Path) -> None:
    if not script.is_file():
        raise LaunchError(f"Script not found: {script}")


def pick_free_port() -> int:
    """Ask the OS for a free loopback port. Another process could grab it before the app binds."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def app_env() -> dict[str, str]:
    """Environment for an app: the repo root on PYTHONPATH so `launcher.scriptkit` imports."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT)] + ([existing] if existing else []))
    return env


def terminate(process: subprocess.Popen) -> None:
    """Stop a child politely, then forcefully; a no-op when it has already exited."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _drain_output(process: subprocess.Popen, label: str) -> None:
    """Log each output line of the child under 'app' until it closes its output, then its exit."""
    try:
        for raw in iter(process.stdout.readline, b""):
            APP_LOG.info("%s: %s", label, raw.decode("utf-8", errors="replace").rstrip("\r\n"))
    finally:
        process.stdout.close()
    LOG.info("%s (pid %d) exited with code %s", label, process.pid, process.wait())


def _app_url(port: int) -> str:
    return f"http://{HOST}:{port}/"


class _Starting:
    """An app that has been spawned but is not known to listen yet."""

    def __init__(self, name: str, process: subprocess.Popen, reader: threading.Thread):
        self.name = name
        self.process = process
        self.reader = reader
        self.cancelled = threading.Event()


class AppRunner:
    """Owns at most one child process. Thread-safe: the server handles requests on threads.

    The lock only guards short state changes. The readiness wait and the terminate grace period run
    outside it, so `running()` (and with it `/api/heartbeat`) never waits for a slow start or stop.
    """

    def __init__(self, start_timeout: float = START_TIMEOUT_SECONDS):
        self._start_timeout = start_timeout
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._info: dict | None = None
        self._reader: threading.Thread | None = None
        self._starting: _Starting | None = None

    def start(
        self, name: str, interpreter: str, script: Path, workspace_root: Path, port: int | None = None
    ) -> dict:
        """Spawn the app and return `{name, port, url}` once its port accepts connections.

        The port is chosen by the OS unless the caller (the desktop `run_script`) names one.
        A `stop()` while this waits ends the child and makes this raise `StartError`.
        """
        starting, port = self._spawn(name, interpreter, script, workspace_root, port)
        try:
            self._wait_until_listening(starting, port, script.name)
        except StartError:
            terminate(starting.process)
            self._finish_starting(starting)
            raise
        with self._lock:
            if starting.cancelled.is_set():
                outcome = StartError(f"{script.name} was stopped during startup.")
            else:
                self._process = starting.process
                self._reader = starting.reader
                self._info = {"name": name, "port": port, "url": _app_url(port)}
                outcome = None
            self._starting = None
        if outcome is not None:
            terminate(starting.process)
            raise outcome
        return dict(self._info)

    def running(self) -> dict | None:
        """The running app, or None (also while an app is only starting); an exited app is forgotten."""
        with self._lock:
            return dict(self._info) if self._alive() else None

    def stop(self) -> None:
        """Stop the running or starting app; returns once it is gone."""
        with self._lock:
            processes = [self._process]
            readers = [self._reader]
            if self._starting is not None:
                self._starting.cancelled.set()
                processes.append(self._starting.process)
                readers.append(self._starting.reader)
            self._process = None
            self._reader = None
            self._info = None
        for child in processes:
            if child is not None:
                terminate(child)
        for reader in readers:
            if reader is not None:
                # The pipe closes with the child; a grandchild holding it open is not waited for.
                reader.join(READER_JOIN_SECONDS)

    def _spawn(
        self, name: str, interpreter: str, script: Path, workspace_root: Path, port: int | None
    ) -> tuple[_Starting, int]:
        """Check that nothing runs or starts, spawn the child and register it as starting."""
        with self._lock:
            if self._starting is not None:
                raise AlreadyRunning(f"'{self._starting.name}' is already starting.")
            if self._alive():
                raise AlreadyRunning(f"'{self._info['name']}' is already running.")
            port = port if port is not None else pick_free_port()
            try:
                child = subprocess.Popen(
                    [interpreter, str(script), "--port", str(port)],
                    cwd=workspace_root,
                    env={**app_env(), "PYTHONUNBUFFERED": "1"},
                    # Output goes through logging, so it is rotated like everything else.
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            except OSError as error:
                raise StartError(f"Could not start {script.name}: {error}") from None
            LOG.info("Started %s (pid %d) on port %d", script.name, child.pid, port)
            reader = threading.Thread(target=_drain_output, args=(child, script.name), daemon=True)
            reader.start()
            self._starting = _Starting(name, child, reader)
            return self._starting, port

    def _finish_starting(self, starting: _Starting) -> None:
        with self._lock:
            if self._starting is starting:
                self._starting = None

    def _alive(self) -> bool:
        """Whether the registered app still runs; call with the lock held."""
        if self._process is not None and self._process.poll() is None:
            return True
        self._process = None
        self._info = None
        return False

    def _wait_until_listening(self, starting: _Starting, port: int, label: str) -> None:
        process = starting.process
        deadline = time.monotonic() + self._start_timeout
        while time.monotonic() < deadline:
            if starting.cancelled.is_set():
                raise StartError(f"{label} was stopped during startup.")
            exit_code = process.poll()
            if exit_code is not None:
                raise StartError(f"{label} exited during startup with exit code {exit_code}.")
            try:
                socket.create_connection((HOST, port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        terminate(process)
        raise StartError(
            f"{label} did not accept connections on port {port} within "
            f"{self._start_timeout:g} s; it was killed (exit code {process.returncode})."
        )
