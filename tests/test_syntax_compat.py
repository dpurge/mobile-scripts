"""Best-effort check that our Python source parses as Python 3.11 syntax.

The Termux Python version is unknown, so this only catches syntax newer than 3.11 (for example
`type` statements, PEP 695 generics). It is not proof that the code runs on 3.11: it does not
check the standard library API, and `ast.parse` with `feature_version` is itself approximate.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
GLOBS = [
    "launcher/backend/*.py",
    "launcher/scriptkit/python/*.py",
    "launcher/tools/*.py",
    "apps/*/*.py",
]
FILES = sorted(path for pattern in GLOBS for path in REPO_ROOT.glob(pattern))


def test_the_globs_find_the_expected_files():
    names = {path.relative_to(REPO_ROOT).as_posix() for path in FILES}
    assert {
        "launcher/backend/server.py",
        "launcher/backend/process.py",
        "launcher/scriptkit/python/kit.py",
        "launcher/tools/run_app.py",
        "apps/hello_py/main.py",
    } <= names


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_parses_as_python_3_11(path):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 11))
