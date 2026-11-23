"""Helpers for Python apps: `--port` parsing and a tiny server (stdlib only).

The app contract is language-neutral: accept `--port N`, serve the UI on that port, stop by exiting
or by `POST /_launcher/stop`. See README.md, "Writing an app".
"""

from launcher.scriptkit.python.kit import parse_port, run_app, stop

__all__ = ["parse_port", "run_app", "stop"]
