"""Builds the Android APK inside Docker and copies it to android/dist/.

Usage: uv run python android/build_apk.py [--context NAME] [--workspace-dir PATH]
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ANDROID_DIR = Path(__file__).resolve().parent
DEFAULT_CONTEXT = "rancher-desktop"
IMAGE = "mobile-scripts-android-build"
# The Android build tools only ship x86_64 binaries (aapt2, the SDK manager), so the image runs
# under emulation on arm64 hosts.
PLATFORM = "linux/amd64"
GRADLE_VERSION = "9.9.2"
# Where the repo is cloned in Termux; baked into the APK (BuildConfig.WORKSPACE_DIR). Same default
# as WORKSPACE_ROOT in config/.env.example.
DEFAULT_WORKSPACE_DIR = "/data/data/com.termux/files/home/mobile-scripts"
GRADLE_URL = "https://services.gradle.org/distributions/gradle-{version}-bin.zip"
APK_RELATIVE = Path("app/build/outputs/apk/debug/app-debug.apk")
# Gradle and the debug keystore live in the container user's home; mounting host
# directories there caches downloads and keeps the signing key stable across builds.
CONTAINER_GRADLE_HOME = "/root/.gradle"
CONTAINER_ANDROID_HOME = "/root/.android"


def gradle_zip_name(version: str) -> str:
    return f"gradle-{version}-bin.zip"


def build_command(context: str, android_dir: Path) -> list[str]:
    """Docker argument list that builds the image; the context is always explicit.

    The build context is the downloads directory so that it holds only the Gradle zip.
    """
    return ["docker", "--context", context, "build", "--platform", PLATFORM,
            "--build-arg", f"GRADLE={GRADLE_VERSION}",
            "-f", str(android_dir / "docker" / "Dockerfile"), "-t", IMAGE,
            str(android_dir / ".cache" / "downloads")]


def run_command(context: str, android_dir: Path, workspace_dir: str = DEFAULT_WORKSPACE_DIR) -> list[str]:
    """Docker argument list that runs the Gradle build with the cache mounts.

    The workspace directory reaches app/build.gradle.kts as the Gradle property workspaceDir.
    """
    cache = android_dir / ".cache"
    return [
        "docker", "--context", context, "run", "--rm", "--platform", PLATFORM,
        "-v", f"{android_dir}:/workspace",
        "-v", f"{cache / 'gradle'}:{CONTAINER_GRADLE_HOME}",
        "-v", f"{cache / 'android'}:{CONTAINER_ANDROID_HOME}",
        IMAGE, "gradle", "--no-daemon", f"-PworkspaceDir={workspace_dir}", "assembleDebug",
    ]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    """Raise if the file's SHA-256 differs from the published value."""
    actual = sha256_of(path)
    if actual != expected.strip().lower():
        raise ValueError(f"SHA-256 mismatch for {path}: expected {expected.strip()}, got {actual}.")


def ensure_gradle_zip(downloads_dir: Path, version: str) -> Path:
    """Download Gradle on the host (not in Docker, where github.com is not trusted) and verify it."""
    zip_path = downloads_dir / gradle_zip_name(version)
    url = GRADLE_URL.format(version=version)
    with urllib.request.urlopen(url + ".sha256", timeout=60) as response:
        expected = response.read().decode("ascii")
    if not zip_path.is_file():
        downloads_dir.mkdir(parents=True, exist_ok=True)
        partial = zip_path.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as file:
            shutil.copyfileobj(response, file)
        partial.replace(zip_path)
    verify_sha256(zip_path, expected)
    return zip_path


def copy_apk(android_dir: Path) -> Path:
    """Copy the built APK to android/dist/ and return its path."""
    source = android_dir / APK_RELATIVE
    if not source.is_file():
        raise FileNotFoundError(f"Gradle finished but {source} does not exist.")
    dist = android_dir / "dist"
    dist.mkdir(exist_ok=True)
    return Path(shutil.copy2(source, dist / source.name))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the APK in Docker.")
    parser.add_argument("--context", default=DEFAULT_CONTEXT, help="docker context name")
    parser.add_argument("--workspace-dir", default=DEFAULT_WORKSPACE_DIR,
                        help="path of the repo clone in Termux, baked into the APK (default: %(default)s)")
    args = parser.parse_args()
    for cache_name in ("gradle", "android"):
        (ANDROID_DIR / ".cache" / cache_name).mkdir(parents=True, exist_ok=True)
    ensure_gradle_zip(ANDROID_DIR / ".cache" / "downloads", GRADLE_VERSION)
    for command in (build_command(args.context, ANDROID_DIR), run_command(args.context, ANDROID_DIR, args.workspace_dir)):
        if subprocess.run(command).returncode != 0:
            print(f"Command failed: {' '.join(command)}", file=sys.stderr)
            return 1
    print(f"APK: {copy_apk(ANDROID_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
