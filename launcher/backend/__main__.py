"""Entry point: `python -m launcher.backend --port N [--watchdog]`."""

import argparse
import logging
import signal
import sys
from pathlib import Path

from launcher.backend import logs
from launcher.backend.config import ConfigError
from launcher.backend.server import HOST, WATCHDOG_TIMEOUT_SECONDS, make_server


def main() -> int:
    parser = argparse.ArgumentParser(prog="launcher.backend", description="Launcher backend.")
    parser.add_argument("--port", type=int, required=True, help="TCP port on 127.0.0.1")
    parser.add_argument(
        "--watchdog",
        action="store_true",
        help=f"exit {WATCHDOG_TIMEOUT_SECONDS:g} s after the last POST /api/heartbeat "
        "(used by hosts: the Termux start script and the desktop client)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help=f"append log lines here, rotated at {logs.LOG_MAX_BYTES} bytes with "
        f"{logs.LOG_BACKUP_COUNT} backups (default: log to stderr)",
    )
    args = parser.parse_args()
    logs.configure(args.log_file)
    log = logging.getLogger("launcher")
    try:
        server = make_server(args.port, watchdog_timeout=WATCHDOG_TIMEOUT_SECONDS if args.watchdog else None)
    except ConfigError as error:
        log.error("Configuration error: %s", error)
        return 1
    # Termination (start.sh stopping us) must take the same clean path as /api/shutdown,
    # otherwise the running app would be left behind.
    signal.signal(signal.SIGTERM, lambda signum, frame: server.request_shutdown())
    log.info("Serving on http://%s:%d/ (watchdog %s)", HOST, server.server_port, "on" if args.watchdog else "off")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    log.info("Backend stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
