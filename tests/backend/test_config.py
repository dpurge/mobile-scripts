import json
import ntpath
from pathlib import Path

import pytest

from launcher.backend import config


def write_config(tmp_path: Path, env: str | None, apps: object | str | None) -> Path:
    if env is not None:
        (tmp_path / ".env").write_text(env, encoding="utf-8")
    if apps is not None:
        text = apps if isinstance(apps, str) else json.dumps(apps)
        (tmp_path / "apps.json").write_text(text, encoding="utf-8")
    return tmp_path


def test_parse_env_skips_comments_and_blank_lines():
    text = "# comment\n\nWORKSPACE_ROOT = /w \n  # indented comment\nOTHER=a=b\n"
    assert config.parse_env(text) == {"WORKSPACE_ROOT": "/w", "OTHER": "a=b"}


def test_workspace_root_read_from_env(tmp_path):
    write_config(tmp_path, "# c\nWORKSPACE_ROOT=/some/root\n", None)
    assert config.load_workspace_root(tmp_path) == Path("/some/root")


def test_missing_env_names_example_file(tmp_path):
    with pytest.raises(config.ConfigError, match=r"config/\.env\.example"):
        config.load_workspace_root(tmp_path)


def test_missing_key_names_example_file(tmp_path):
    write_config(tmp_path, "# only a comment\nOTHER=1\n", None)
    with pytest.raises(config.ConfigError, match=r"WORKSPACE_ROOT.*config/\.env\.example"):
        config.load_workspace_root(tmp_path)


def test_empty_value_counts_as_missing(tmp_path):
    write_config(tmp_path, "WORKSPACE_ROOT=\n", None)
    with pytest.raises(config.ConfigError):
        config.load_workspace_root(tmp_path)


def test_relative_script_path_joins_workspace_root(tmp_path):
    assert config.resolve_script_path("apps/x/main.py", tmp_path) == tmp_path / "apps/x/main.py"


def test_absolute_script_path_is_used_as_is(tmp_path):
    absolute = (tmp_path / "elsewhere" / "main.py").resolve()
    assert config.resolve_script_path(str(absolute), Path("/ignored")) == absolute


def test_windows_absolute_string_is_recognised_as_pure_function():
    # Pure string check, so it runs on every OS without a Windows path flavour.
    assert ntpath.isabs("C:\\scripts\\main.py")
    assert not ntpath.isabs("apps\\x\\main.py")


def test_load_apps_returns_only_name_and_script_path(tmp_path):
    apps = {"apps": [{"name": "A", "script_path": "a.py", "port": 1}]}
    write_config(tmp_path, None, apps)
    assert config.load_apps(tmp_path) == [{"name": "A", "script_path": "a.py"}]


def test_repository_sample_config_is_valid():
    apps = config.load_apps(config.DEFAULT_CONFIG_DIR)
    assert [app["name"] for app in apps] == ["Hello (Python)", "Hello (Node)"]
    assert apps[1]["script_path"] == "apps/hello_js/main.mjs"


@pytest.mark.parametrize(
    "apps",
    [
        {"apps": [{"name": "", "script_path": "a.py"}]},
        {"apps": [{"name": "A", "script_path": "  "}]},
        {"apps": [{"name": "A"}]},
        {"apps": [{"script_path": "a.py"}]},
        {"apps": [{"name": 1, "script_path": "a.py"}]},
        {"apps": ["not an object"]},
        {"apps": "not a list"},
        {"nothing": []},
        [],
    ],
)
def test_invalid_apps_json_entries_are_rejected(tmp_path, apps):
    write_config(tmp_path, None, apps)
    with pytest.raises(config.ConfigError):
        config.load_apps(tmp_path)


def test_apps_json_that_is_not_json_is_rejected(tmp_path):
    write_config(tmp_path, None, "{not json")
    with pytest.raises(config.ConfigError, match="not valid JSON"):
        config.load_apps(tmp_path)


def test_missing_apps_json_is_rejected(tmp_path):
    with pytest.raises(config.ConfigError, match="missing"):
        config.load_apps(tmp_path)


def test_save_apps_writes_atomically_and_round_trips(tmp_path):
    write_config(tmp_path, None, {"apps": []})
    saved = config.save_apps(tmp_path, [{"name": "A", "script_path": "a.py", "extra": 1}])
    assert saved == [{"name": "A", "script_path": "a.py"}]
    assert config.load_apps(tmp_path) == saved
    assert [p.name for p in tmp_path.iterdir()] == ["apps.json"]


@pytest.mark.parametrize(
    "entries",
    [None, "x", [1], [{"name": "", "script_path": "a.py"}], [{"name": "A", "script_path": " "}]],
)
def test_save_apps_rejects_invalid_and_keeps_old_file(tmp_path, entries):
    write_config(tmp_path, None, {"apps": [{"name": "Old", "script_path": "o.py"}]})
    with pytest.raises(config.ConfigError):
        config.save_apps(tmp_path, entries)
    assert config.load_apps(tmp_path) == [{"name": "Old", "script_path": "o.py"}]


def test_save_apps_failed_replace_leaves_old_file_and_no_temp_file(tmp_path, monkeypatch):
    write_config(tmp_path, None, {"apps": [{"name": "Old", "script_path": "o.py"}]})

    def failing_replace(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(config.os, "replace", failing_replace)
    with pytest.raises(OSError):
        config.save_apps(tmp_path, [{"name": "New", "script_path": "n.py"}])
    assert [p.name for p in tmp_path.iterdir()] == ["apps.json"]
    assert config.load_apps(tmp_path)[0]["name"] == "Old"
