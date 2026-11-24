"""Builds the Android APK inside Docker and copies it to android/dist/.

Usage: uv run python android/build_apk.py [--context NAME] [--workspace-dir PATH] [--variant debug|release]
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
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
# Both variants are signed with the Android debug keystore (see app/build.gradle.kts), so either one
# installs; the release variant is the one without the debuggable flag.
VARIANTS = ("debug", "release")
DEFAULT_VARIANT = "release"
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


def gradle_task(variant: str) -> str:
    return f"assemble{variant.capitalize()}"


def apk_name(variant: str) -> str:
    return f"app-{variant}.apk"


def run_command(context: str, android_dir: Path, workspace_dir: str = DEFAULT_WORKSPACE_DIR,
                variant: str = DEFAULT_VARIANT) -> list[str]:
    """Docker argument list that runs the Gradle build with the cache mounts.

    The workspace directory reaches app/build.gradle.kts as the Gradle property workspaceDir.
    """
    cache = android_dir / ".cache"
    return [
        "docker", "--context", context, "run", "--rm", "--platform", PLATFORM,
        "-v", f"{android_dir}:/workspace",
        "-v", f"{cache / 'gradle'}:{CONTAINER_GRADLE_HOME}",
        "-v", f"{cache / 'android'}:{CONTAINER_ANDROID_HOME}",
        IMAGE, "gradle", "--no-daemon", f"-PworkspaceDir={workspace_dir}", gradle_task(variant),
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


def curl(url: str, output: Path | None = None) -> str:
    """Fetch a URL with curl and return the body (or write it to output).

    curl rather than urllib: Python's OpenSSL rejects the certificate chain of a TLS-intercepting
    network (CA without key usage extension) that curl and the system trust store accept.
    """
    command = ["curl", "-fsSL", "--max-time", "600", url] + (["-o", str(output)] if output else [])
    result = subprocess.run(command, capture_output=output is None, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Downloading {url} failed (curl exit code {result.returncode}): {result.stderr or ''}".strip())
    return result.stdout or ""


def ensure_gradle_zip(downloads_dir: Path, version: str) -> Path:
    """Download Gradle on the host (not in Docker, where github.com is not trusted) and verify it.

    The published checksum is kept next to the zip, so a cached zip is verified without network.
    """
    zip_path = downloads_dir / gradle_zip_name(version)
    checksum_path = zip_path.with_name(zip_path.name + ".sha256")
    url = GRADLE_URL.format(version=version)
    if zip_path.is_file() and checksum_path.is_file():
        verify_sha256(zip_path, checksum_path.read_text(encoding="ascii"))
        return zip_path
    expected = curl(url + ".sha256")
    if not zip_path.is_file():
        downloads_dir.mkdir(parents=True, exist_ok=True)
        partial = zip_path.with_suffix(".part")
        curl(url, partial)
        partial.replace(zip_path)
    verify_sha256(zip_path, expected)
    checksum_path.write_text(expected, encoding="ascii")
    return zip_path


def copy_apk(android_dir: Path, variant: str = DEFAULT_VARIANT) -> Path:
    """Copy the signed APK of the variant from the Gradle output to android/dist/ and return its path."""
    source = android_dir / "app" / "build" / "outputs" / "apk" / variant / apk_name(variant)
    if not source.is_file():
        unsigned = source.with_name(f"app-{variant}-unsigned.apk")
        hint = " It is unsigned: the build type has no signing config." if unsigned.is_file() else ""
        raise FileNotFoundError(f"Gradle finished but {source} does not exist.{hint}")
    dist = android_dir / "dist"
    dist.mkdir(exist_ok=True)
    return Path(shutil.copy2(source, dist / source.name))


def inspect_command(context: str, android_dir: Path, apk: str) -> list[str]:
    """Docker argument list that verifies the signature of dist/<apk> and prints its SDK levels."""
    script = f"""
        set -eu
        APK=/workspace/dist/{apk}
        SDK=${{ANDROID_HOME}}/build-tools
        APKSIGNER=$(ls -d "$SDK"/*/apksigner | sort -V | tail -n 1)
        AAPT=$(ls -d "$SDK"/*/aapt | sort -V | tail -n 1)
        ls -l "$APK"
        "$APKSIGNER" verify --verbose --print-certs "$APK"
        "$AAPT" dump badging "$APK" | grep -E "^(package|sdkVersion|targetSdkVersion)"
    """
    return ["docker", "--context", context, "run", "--rm", "--platform", PLATFORM,
            "-v", f"{android_dir}:/workspace", IMAGE, "sh", "-c", script]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the APK in Docker.")
    parser.add_argument("--context", default=DEFAULT_CONTEXT, help="docker context name")
    parser.add_argument("--workspace-dir", default=DEFAULT_WORKSPACE_DIR,
                        help="path of the repo clone in Termux, baked into the APK (default: %(default)s)")
    parser.add_argument("--variant", choices=VARIANTS, default=DEFAULT_VARIANT,
                        help="build type; both are signed and installable (default: %(default)s)")
    args = parser.parse_args()
    for cache_name in ("gradle", "android"):
        (ANDROID_DIR / ".cache" / cache_name).mkdir(parents=True, exist_ok=True)
    ensure_gradle_zip(ANDROID_DIR / ".cache" / "downloads", GRADLE_VERSION)
    commands = (build_command(args.context, ANDROID_DIR),
                run_command(args.context, ANDROID_DIR, args.workspace_dir, args.variant))
    for command in commands:
        if subprocess.run(command).returncode != 0:
            print(f"Command failed: {' '.join(command)}", file=sys.stderr)
            return 1
    apk = copy_apk(ANDROID_DIR, args.variant)
    inspect = inspect_command(args.context, ANDROID_DIR, apk.name)
    if subprocess.run(inspect).returncode != 0:
        print(f"APK check failed: {' '.join(inspect)}", file=sys.stderr)
        return 1
    print(f"APK: {apk}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
