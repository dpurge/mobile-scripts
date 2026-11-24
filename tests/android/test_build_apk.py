import importlib.util
from pathlib import Path

import pytest

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


def test_run_command_runs_the_task_of_the_variant_in_the_image():
    for variant, task in (("debug", "assembleDebug"), ("release", "assembleRelease")):
        command = build_apk.run_command("c", WORK, variant=variant)
        assert command[command.index(build_apk.IMAGE):][:2] == [build_apk.IMAGE, "gradle"]
        assert command[-1] == task


def test_run_command_passes_default_workspace_dir_as_gradle_property():
    command = build_apk.run_command("c", WORK)
    assert "-PworkspaceDir=/data/data/com.termux/files/home/mobile-scripts" in command


def test_run_command_passes_custom_workspace_dir_before_the_task():
    command = build_apk.run_command("c", WORK, "/data/data/com.termux/files/home/other")
    assert command.index("-PworkspaceDir=/data/data/com.termux/files/home/other") < command.index("assembleRelease")
    assert command[-1] == "assembleRelease"


def run_main(monkeypatch, argv):
    """Runs main() with Docker, the Gradle download and the APK copy replaced; returns the commands."""
    seen = []
    monkeypatch.setattr(build_apk, "ensure_gradle_zip", lambda *args: None)
    monkeypatch.setattr(build_apk, "copy_apk", lambda android_dir, variant: Path(f"/dist/app-{variant}.apk"))
    monkeypatch.setattr(build_apk.subprocess, "run",
                        lambda command: seen.append(command) or type("R", (), {"returncode": 0})())
    monkeypatch.setattr(build_apk.sys, "argv", ["x", *argv])
    assert build_apk.main() == 0
    return seen


def test_workspace_dir_option_defaults_and_overrides(monkeypatch):
    for argv, expected in (([], build_apk.DEFAULT_WORKSPACE_DIR), (["--workspace-dir", "/w"], "/w")):
        assert f"-PworkspaceDir={expected}" in run_main(monkeypatch, argv)[1]


def test_variant_option_defaults_to_release_and_selects_the_gradle_task(monkeypatch):
    assert run_main(monkeypatch, [])[1][-1] == "assembleRelease"
    assert run_main(monkeypatch, ["--variant", "debug"])[1][-1] == "assembleDebug"


def test_main_checks_the_copied_apk_last(monkeypatch):
    commands = run_main(monkeypatch, ["--variant", "debug"])
    assert len(commands) == 3
    assert "/workspace/dist/app-debug.apk" in commands[2][-1]


def test_default_context_is_rancher_desktop():
    assert build_apk.DEFAULT_CONTEXT == "rancher-desktop"


def make_gradle_output(android_dir, name, variant="release"):
    apk = android_dir / "app" / "build" / "outputs" / "apk" / variant / name
    apk.parent.mkdir(parents=True)
    apk.write_bytes(b"apk")


def test_copy_apk_copies_the_variant_to_dist(tmp_path):
    make_gradle_output(tmp_path, "app-release.apk")
    assert build_apk.copy_apk(tmp_path, "release") == tmp_path / "dist" / "app-release.apk"
    assert (tmp_path / "dist" / "app-release.apk").read_bytes() == b"apk"


def test_copy_apk_copies_the_debug_variant(tmp_path):
    make_gradle_output(tmp_path, "app-debug.apk", "debug")
    assert build_apk.copy_apk(tmp_path, "debug") == tmp_path / "dist" / "app-debug.apk"


def test_copy_apk_fails_clearly_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="app-release.apk"):
        build_apk.copy_apk(tmp_path, "release")


def test_copy_apk_says_when_only_an_unsigned_apk_exists(tmp_path):
    make_gradle_output(tmp_path, "app-release-unsigned.apk")
    with pytest.raises(FileNotFoundError, match="unsigned"):
        build_apk.copy_apk(tmp_path, "release")


def test_inspect_command_verifies_signature_and_names_context(tmp_path):
    command = build_apk.inspect_command("my-ctx", WORK, "app-release.apk")
    assert command[:3] == ["docker", "--context", "my-ctx"]
    assert "apksigner" in command[-1] and "verify" in command[-1]
    assert "/workspace/dist/app-release.apk" in command[-1]


def test_ensure_gradle_zip_uses_the_cache_without_network(tmp_path, monkeypatch):
    zip_path = tmp_path / build_apk.gradle_zip_name("1.0")
    zip_path.write_bytes(b"abc")
    zip_path.with_name(zip_path.name + ".sha256").write_text(
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    monkeypatch.setattr(build_apk, "curl", lambda *args: pytest.fail("network used"))
    assert build_apk.ensure_gradle_zip(tmp_path, "1.0") == zip_path


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
    file = tmp_path / "f.zip"
    file.write_bytes(b"abc")
    with pytest.raises(ValueError, match="mismatch"):
        build_apk.verify_sha256(file, "0" * 64)


def test_ensure_gradle_zip_downloads_verifies_and_caches_the_checksum(tmp_path, monkeypatch):
    digest = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    def fake_curl(url, output=None):
        if output is None:
            return digest
        output.write_bytes(b"abc")
        return ""

    monkeypatch.setattr(build_apk, "curl", fake_curl)
    zip_path = build_apk.ensure_gradle_zip(tmp_path, "1.0")
    assert zip_path.read_bytes() == b"abc"
    assert zip_path.with_name(zip_path.name + ".sha256").read_text() == digest
