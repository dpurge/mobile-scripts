import os
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

from launcher.backend import process


def tool_env(fake_repo):
    return {**os.environ, "PYTHONPATH": str(fake_repo)}


def run_tool_command(*args):
    return [sys.executable, "-m", "launcher.tools.run_app", *args]


def run_tool(fake_repo, script: str, port: int, stop_url: str) -> None:
    child = subprocess.Popen(
        run_tool_command(script, "--port", str(port)),
        cwd=fake_repo, env=tool_env(fake_repo), stdout=subprocess.PIPE, text=True,
    )
    try:
        assert f"http://127.0.0.1:{port}/" in child.stdout.readline()
        for _ in range(100):
            try:
                urllib.request.urlopen(stop_url, data=b"", timeout=2).close()
                break
            except OSError:
                time.sleep(0.1)
        assert child.wait(timeout=10) == 0
    finally:
        if child.poll() is None:
            child.kill()
        child.stdout.close()


@pytest.mark.parametrize("script", ["apps/hello_py/main.py", "apps/hello_js/main.mjs"])
def test_tool_runs_an_app_until_it_stops(fake_repo, script):
    if script.endswith(".mjs") and shutil.which("node") is None:
        pytest.fail("`node` is not on PATH; install Node to test the .mjs app")
    port = process.pick_free_port()
    run_tool(fake_repo, script, port, f"http://127.0.0.1:{port}/_launcher/stop")


def test_tool_rejects_unknown_extension(fake_repo, tmp_path):
    script = tmp_path / "a.txt"
    script.write_text("x", encoding="utf-8")
    result = subprocess.run(
        run_tool_command(str(script)),
        cwd=fake_repo, env=tool_env(fake_repo), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1 and "Unsupported" in result.stderr


def test_app_runs_in_the_workspace_root_not_the_task_directory(fake_repo, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fake_repo / "config" / ".env").write_text(f"WORKSPACE_ROOT={workspace}\n", encoding="utf-8")
    script = fake_repo / "where.py"  # relative to the directory the task runs in, as before
    script.write_text("import os\nopen('cwd.txt', 'w').write(os.getcwd())\n", encoding="utf-8")
    result = subprocess.run(
        run_tool_command("where.py"),
        cwd=fake_repo, env=tool_env(fake_repo), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert (workspace / "cwd.txt").read_text(encoding="utf-8") == str(workspace.resolve())
    assert not (fake_repo / "cwd.txt").exists()


def test_missing_env_file_fails_fast_naming_the_example(fake_repo):
    (fake_repo / "config" / ".env").unlink()
    result = subprocess.run(
        run_tool_command("apps/hello_py/main.py"),
        cwd=fake_repo, env=tool_env(fake_repo), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert "config/.env.example" in result.stderr and "Serving on" not in result.stdout
