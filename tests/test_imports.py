import ast
import sys
from pathlib import Path

LAUNCHER_DIR = Path(__file__).parents[1] / "launcher"
# Only these packages must stay stdlib-only (the desktop client alone may import webview).
STDLIB_ONLY_DIRS = [LAUNCHER_DIR / "backend", LAUNCHER_DIR / "scriptkit" / "python"]
ALLOWED = set(sys.stdlib_module_names) | {"launcher"}


def imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            modules.add(node.module.split(".")[0])
    return modules


def python_files() -> list[Path]:
    files = [path for directory in STDLIB_ONLY_DIRS for path in directory.glob("*.py")]
    assert len(files) >= 7, files
    return files


def test_stdlib_only_packages_import_only_stdlib_or_launcher():
    for path in python_files():
        assert imported_modules(path) <= ALLOWED, path


def test_stdlib_only_packages_never_import_webview():
    for path in python_files():
        assert "webview" not in imported_modules(path), path


def test_only_the_desktop_window_module_imports_webview():
    root = LAUNCHER_DIR.parent
    importers = {
        path.relative_to(root).as_posix()
        for directory in (LAUNCHER_DIR, root / "apps", root / "tests")
        for path in directory.rglob("*.py")
        if "webview" in imported_modules(path)
    }
    # window.py is the one place; the rest of launcher/desktop (host.py, tests) stays importable without it.
    assert importers == {"launcher/desktop/window.py"}
