import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
EXPECTED_TASKS = {"default", "setup", "backend", "test", "refresh", "apk:build", "app:run", "desktop", "app:window"}


@pytest.fixture(scope="module")
def tasks() -> list[dict]:
    # Fails, never skips: the Taskfile is the documented front door.
    if shutil.which("task") is None:
        pytest.fail("`task` is not on PATH; install it from https://taskfile.dev/installation/")
    result = subprocess.run(
        ["task", "--list-all", "--json"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=30,
    )
    return json.loads(result.stdout)["tasks"]


def test_expected_tasks_exist(tasks):
    assert {t["name"] for t in tasks} == EXPECTED_TASKS


def test_every_task_has_a_description(tasks):
    assert all(t["desc"].strip() for t in tasks), [t["name"] for t in tasks if not t["desc"].strip()]
