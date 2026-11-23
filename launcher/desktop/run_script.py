"""Run one app in a desktop window: `python -m launcher.desktop.run_script <script> [--port N]`.

The window closing stops the app; the app exiting closes the window. The app runs with
WORKSPACE_ROOT from config/.env as its working directory, like in the launcher.
"""

import argparse
import logging
import sys
from pathlib import Path

from launcher.backend import config, process
from launcher.desktop import host

LOG = logging.getLogger("launcher.desktop")
POLL_SECONDS = 0.5


def main() -> int:
    parser = argparse.ArgumentParser(prog="launcher.desktop.run_script", description=__doc__)
    parser.add_argument("script", type=Path, help="a .py, .js or .mjs app (relative to the current directory)")
    parser.add_argument("--port", type=int, help="TCP port; a free one is chosen when omitted")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        from launcher.desktop.window import run_window
    except ImportError as error:
        LOG.error("pywebview is not installed (%s); run it through `task app:window`", error)
        return 1
    script = args.script.resolve()
    runner = process.AppRunner()
    try:
        workspace_root = config.load_workspace_root(config.DEFAULT_CONFIG_DIR)
        process.require_script_file(script)
        interpreter = process.select_interpreter(script)
        port = args.port if args.port is not None else process.pick_free_port()
        info = runner.start(script.name, interpreter, script, workspace_root, port=port)
    except (config.ConfigError, process.LaunchError, process.StartError) as error:
        LOG.error("Cannot run: %s", error)
        return 1
    LOG.info("Serving %s on %s", script.name, info["url"])

    def watch(window, stop):
        while not stop.wait(POLL_SECONDS):
            if runner.running() is None:
                LOG.info("%s exited; closing the window", script.name)
                return

    try:
        run_window(info["url"], watch)
    finally:
        runner.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
