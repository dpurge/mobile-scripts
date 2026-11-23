"""Creates config/.env from config/.env.example; never overwrites an existing file.

Python instead of shell `cp`/`sed` so `task setup` works on Windows too.
"""

from pathlib import Path

from launcher.backend.config import DEFAULT_CONFIG_DIR, WORKSPACE_KEY, parse_env

REPO_ROOT = Path(__file__).parents[2]


def render_env(example_text: str, workspace_root: Path) -> str:
    """Return the example text with the workspace key set to `workspace_root`."""
    lines = []
    for line in example_text.splitlines():
        if parse_env(line).get(WORKSPACE_KEY) is not None:
            line = f"{WORKSPACE_KEY}={workspace_root}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def init_env(config_dir: Path, workspace_root: Path) -> bool:
    """Create `.env` in `config_dir`; return False when it already exists."""
    env_path = config_dir / ".env"
    if env_path.exists():
        return False
    example = (config_dir / ".env.example").read_text(encoding="utf-8")
    env_path.write_text(render_env(example, workspace_root), encoding="utf-8")
    return True


def main() -> None:
    if init_env(DEFAULT_CONFIG_DIR, REPO_ROOT):
        print(f"Created config/.env with {WORKSPACE_KEY}={REPO_ROOT}")
    else:
        print("config/.env already exists; left unchanged")


if __name__ == "__main__":
    main()
