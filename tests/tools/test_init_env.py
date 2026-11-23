from pathlib import Path

from launcher.backend import config
from launcher.tools.init_env import init_env, render_env

EXAMPLE = "# comment\nWORKSPACE_ROOT=/data/example\n"


def test_render_env_replaces_only_the_workspace_line():
    assert render_env(EXAMPLE, Path("/repo")) == "# comment\nWORKSPACE_ROOT=/repo\n"


def test_init_env_creates_env_readable_by_config(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    assert init_env(tmp_path, tmp_path / "repo") is True
    assert config.load_workspace_root(tmp_path) == tmp_path / "repo"


def test_init_env_never_overwrites(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    (tmp_path / ".env").write_text("WORKSPACE_ROOT=/mine\n", encoding="utf-8")
    assert init_env(tmp_path, Path("/repo")) is False
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "WORKSPACE_ROOT=/mine\n"
