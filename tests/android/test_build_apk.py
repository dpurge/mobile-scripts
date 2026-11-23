import importlib.util
from pathlib import Path

ANDROID_DIR = Path(__file__).parents[2] / "android"

# android/ is not a package, so load the script by path.
spec = importlib.util.spec_from_file_location("build_apk", ANDROID_DIR / "build_apk.py")
build_apk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_apk)

WORK = Path("/work/android")


def test_build_command_names_context_explicitly():
    command = build_apk.build_command("my-ctx", WORK)
    assert command[:3] == ["docker", "--context", "my-ctx"]
    assert command[3] == "build"
    assert command[command.index("-t") + 1] == build_apk.IMAGE


def test_run_command_names_context_explicitly():
    command = build_apk.run_command("my-ctx", WORK)
    assert command[:5] == ["docker", "--context", "my-ctx", "run", "--rm"]


def test_run_command_mounts_workspace_and_persistent_caches():
    command = build_apk.run_command("c", WORK)
    mounts = [command[i + 1] for i, arg in enumerate(command) if arg == "-v"]
    assert f"{WORK}:/workspace" in mounts
    assert f"{WORK / '.cache' / 'gradle'}:/root/.gradle" in mounts
    assert f"{WORK / '.cache' / 'android'}:/root/.android" in mounts


def test_run_command_runs_assemble_debug_in_the_image():
    command = build_apk.run_command("c", WORK)
    assert command[command.index(build_apk.IMAGE):][:2] == [build_apk.IMAGE, "gradle"]
    assert command[-1] == "assembleDebug"


def test_run_command_passes_default_workspace_dir_as_gradle_property():
    command = build_apk.run_command("c", WORK)
    assert "-PworkspaceDir=/data/data/com.termux/files/home/mobile-scripts" in command


def test_run_command_passes_custom_workspace_dir_before_the_task():
    command = build_apk.run_command("c", WORK, "/data/data/com.termux/files/home/other")
    assert command.index("-PworkspaceDir=/data/data/com.termux/files/home/other") < command.index("assembleDebug")
    assert command[-1] == "assembleDebug"


def test_workspace_dir_option_defaults_and_overrides(monkeypatch):
    seen = []
    monkeypatch.setattr(build_apk, "ensure_gradle_zip", lambda *args: None)
    monkeypatch.setattr(build_apk, "copy_apk", lambda android_dir: "apk")
    monkeypatch.setattr(build_apk.subprocess, "run",
                        lambda command: seen.append(command) or type("R", (), {"returncode": 0})())
    for argv, expected in ((["x"], build_apk.DEFAULT_WORKSPACE_DIR),
                           (["x", "--workspace-dir", "/w"], "/w")):
        seen.clear()
        monkeypatch.setattr(build_apk.sys, "argv", argv)
        assert build_apk.main() == 0
        assert f"-PworkspaceDir={expected}" in seen[1]


def test_default_context_is_rancher_desktop():
    assert build_apk.DEFAULT_CONTEXT == "rancher-desktop"


def test_copy_apk_copies_to_dist(tmp_path):
    apk = tmp_path / build_apk.APK_RELATIVE
    apk.parent.mkdir(parents=True)
    apk.write_bytes(b"apk")
    assert build_apk.copy_apk(tmp_path) == tmp_path / "dist" / "app-debug.apk"
    assert (tmp_path / "dist" / "app-debug.apk").read_bytes() == b"apk"


def test_copy_apk_fails_clearly_when_missing(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError, match="app-debug.apk"):
        build_apk.copy_apk(tmp_path)


def test_build_and_run_pin_amd64_platform():
    for command in (build_apk.build_command("c", WORK), build_apk.run_command("c", WORK)):
        assert command[command.index("--platform") + 1] == "linux/amd64"


def test_build_context_is_the_downloads_dir():
    assert build_apk.build_command("c", WORK)[-1] == str(WORK / ".cache" / "downloads")


def test_verify_sha256_accepts_matching_checksum(tmp_path):
    file = tmp_path / "f.zip"
    file.write_bytes(b"abc")
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    build_apk.verify_sha256(file, expected + "\n")


def test_verify_sha256_rejects_mismatch(tmp_path):
    import pytest

    file = tmp_path / "f.zip"
    file.write_bytes(b"abc")
    with pytest.raises(ValueError, match="mismatch"):
        build_apk.verify_sha256(file, "0" * 64)
