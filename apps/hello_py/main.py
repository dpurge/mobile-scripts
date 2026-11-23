"""Example Python app: serves ui/ and reports the Python version at GET /api/info."""

import platform
import sys
from pathlib import Path

from launcher.scriptkit.python import parse_port, run_app


def info() -> dict[str, str]:
    return {"language": "Python", "runtime": platform.python_version()}


def main() -> None:
    run_app(Path(__file__).parent / "ui", parse_port(sys.argv[1:]), routes={("GET", "/api/info"): info})


if __name__ == "__main__":
    main()
