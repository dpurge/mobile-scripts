"""Desktop client: `python -m launcher.desktop`. Simulates the Android client with the same config and API."""

import logging
import sys

from launcher.desktop import host

LOG = logging.getLogger("launcher.desktop")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Imported here so a missing pywebview gives a clear message instead of a traceback.
    try:
        from launcher.desktop.window import run_window
    except ImportError as error:
        LOG.error("pywebview is not installed (%s); run it through `task desktop`", error)
        return 1
    port = host.pick_free_port()
    LOG.info("Using port %d (%s)", port, host.list_url(port))
    try:
        backend = host.launch_backend(port)
    except host.BackendError as error:
        LOG.error("%s", error)
        return 1
    failure: list[int] = []

    def watch(window, stop):
        exit_code = host.watch_backend(port, backend, window, stop)
        if exit_code is not None:
            failure.append(exit_code)

    try:
        run_window(host.list_url(port), watch)
    finally:
        host.shutdown_backend(port, backend)
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
