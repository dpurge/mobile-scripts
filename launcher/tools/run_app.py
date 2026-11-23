"""Run one app on its own, without the launcher.

Usage: uv run python -m launcher.tools.run_app <script> [--port N]
The script path is relative to the current directory (the repo root when run through `task`).
The app runs with WORKSPACE_ROOT from config/.env as its working directory, like in the launcher.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from launcher.backend import config, process


def main() -> int:
    parser = argparse.ArgumentParser(prog="launcher.tools.run_app", description=__doc__)
    parser.add_argument("script", type=Path, help="a .py, .js or .mjs app")
    parser.add_argument("--port", type=int, help="TCP port; a free one is chosen when omitted")
    args = parser.parse_args()
    script = args.script.resolve()
    try:
        workspace_root = config.load_workspace_root(config.DEFAULT_CONFIG_DIR)
        process.require_script_file(script)
        interpreter = process.select_interpreter(script)
    except (config.ConfigError, process.LaunchError) as error:
        print(f"Cannot run: {error}", file=sys.stderr)
        return 1
    port = args.port if args.port is not None else process.pick_free_port()
    print(f"Serving on http://{process.HOST}:{port}/ (Ctrl-C to stop)", flush=True)
    child = subprocess.Popen(
        [interpreter, str(script), "--port", str(port)], cwd=workspace_root, env=process.app_env()
    )
    try:
        return child.wait()
    except KeyboardInterrupt:
        process.terminate(child)
        return 0


if __name__ == "__main__":
    sys.exit(main())
