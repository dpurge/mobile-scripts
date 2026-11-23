# Project Memory

<!-- Append-only, one entry per line: `YYYY-MM-DDTHH:MM:SSZ [tag] text`. See the `memory-format` skill. Do not read this file in full — grep it. -->

2026-11-23T20:38:07Z [build] Android build tools (cmdline-tools sdkmanager, aapt2 for AGP 9.x) exist only for x86_64 Linux, so the APK build image in android/docker/Dockerfile runs as linux/amd64, under emulation on arm64 Docker hosts; first build took about 9 min, a warm repeat 1 to 3 min.
2026-11-23T20:38:07Z [gotcha] A TLS-intercepting corporate proxy makes github.com certificates untrusted inside containers, which breaks Gradle's download redirect; android/build_apk.py downloads gradle-9.9.2-bin.zip on the host, verifies the published SHA-256 and the Dockerfile COPYs it.
2026-11-23T20:38:07Z [gotcha] AndroidManifest.xml inside an APK is binary UTF-16; inspect it with `iconv -f UTF-16LE -t UTF-8 | strings`.
2026-11-23T20:38:07Z [gotcha] jsdelivr has no standalone Lit bundle (lit-core.min.js is 404, index.min.js and +esm are import stubs); launcher/frontend/vendor/lit.js is a one-off esbuild bundle, steps in launcher/frontend/vendor/README.md.
2026-11-23T20:38:07Z [gotcha] Tests that glob and read rotated log files race with RotatingFileHandler renames; tolerate FileNotFoundError and wait for the writer to finish (tests/backend/test_logs.py failed 5 of 60 runs under CPU load before the fix).
2026-11-23T20:38:07Z [gotcha] The pywebview GUI main loop only runs Python signal handlers when a call reaches it, so launcher/desktop/window.py runs a wake-up thread polling get_current_url, otherwise SIGTERM is ignored.
2026-11-23T20:38:07Z [convention] Agents make no git commits in this repo: the user commits manually.
