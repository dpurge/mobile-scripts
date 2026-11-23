"""Loads launcher configuration from the config directory (stdlib only)."""

import json
import os
import tempfile
from pathlib import Path

DEFAULT_CONFIG_DIR = Path(__file__).parents[2] / "config"
ENV_FILE = "config/.env"
ENV_EXAMPLE = "config/.env.example"
WORKSPACE_KEY = "WORKSPACE_ROOT"


class ConfigError(Exception):
    """Raised when configuration is missing or invalid; the message says how to fix it."""


def parse_env(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines, ignoring blank lines and `#` comments."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def load_workspace_root(config_dir: Path) -> Path:
    """Return WORKSPACE_ROOT from `.env`, failing fast with a pointer to the example file."""
    env_path = config_dir / ".env"
    if not env_path.is_file():
        raise ConfigError(f"{ENV_FILE} is missing; copy {ENV_EXAMPLE} to {ENV_FILE} and edit it.")
    root = parse_env(env_path.read_text(encoding="utf-8")).get(WORKSPACE_KEY)
    if not root:
        raise ConfigError(f"{WORKSPACE_KEY} is not set in {ENV_FILE}; see {ENV_EXAMPLE}.")
    return Path(root)


def resolve_script_path(script_path: str, workspace_root: Path) -> Path:
    """Use an absolute path as is, otherwise resolve it against the workspace root."""
    path = Path(script_path)
    return path if path.is_absolute() else workspace_root / path


def _validate_app(index: int, entry: object) -> dict[str, str]:
    if not isinstance(entry, dict):
        raise ConfigError(f"apps.json entry {index} must be an object.")
    app = {}
    for key in ("name", "script_path"):
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"apps.json entry {index}: '{key}' must be a non-empty string.")
        app[key] = value
    return app


def _validate_apps(entries: object) -> list[dict[str, str]]:
    if not isinstance(entries, list):
        raise ConfigError("'apps' must be a list.")
    return [_validate_app(index, entry) for index, entry in enumerate(entries)]


def load_apps(config_dir: Path) -> list[dict[str, str]]:
    """Return the validated app list, keeping only `name` and `script_path`."""
    apps_path = config_dir / "apps.json"
    try:
        data = json.loads(apps_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{apps_path} is missing.") from None
    except json.JSONDecodeError as error:
        raise ConfigError(f"{apps_path} is not valid JSON: {error}.") from None
    entries = data.get("apps") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ConfigError(f"{apps_path} must contain an 'apps' list.")
    return _validate_apps(entries)


def save_apps(config_dir: Path, entries: object) -> list[dict[str, str]]:
    """Validate and replace the whole app list; the write is atomic.

    The temp file lives in the same directory so `os.replace` never crosses a filesystem and a
    reader sees either the old or the new file, never a partial one.
    """
    apps = _validate_apps(entries)
    payload = json.dumps({"apps": apps}, indent=2) + "\n"
    handle, temp_name = tempfile.mkstemp(dir=config_dir, prefix="apps.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as temp_file:
            temp_file.write(payload)
        os.replace(temp_name, config_dir / "apps.json")
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return apps
