# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Launcher list of Python (`.py`) and Node (`.mjs`, `.js`) apps, read from `config/apps.json`, with add, edit, delete, reorder and start; `script_path` entries resolve against `WORKSPACE_ROOT` from `config/.env`.
- Started apps turn the window into their own UI and return to the list when they stop themselves.
- Helper libraries for Python and Node apps, and two example apps (`apps/hello_py`, `apps/hello_js`).
- Backend heartbeat, watchdog (exits 15 s after the last heartbeat) and `POST /api/shutdown`, which stops the running app on exit.
- Termux start script (`launcher/termux/start.sh`) with a wake lock and rotating logs (1 MB, 3 backups).
- Desktop client with pywebview (`task desktop`, `task app:window`), which uses the same config and API as the Android client.
- Android client APK built in Docker with `task apk:build`; native-first, with a status screen, diagnostics and Retry. NOT yet run on a device: all Android behaviour is unverified.
- Taskfile as the project front door (`task setup`, `backend`, `test`, `refresh`, `app:run`, `desktop`, `app:window`, `apk:build`).
- No-build Lit frontend with a vendored Lit (`launcher/frontend/vendor/lit.js`).
- `task apk:build -- --variant debug|release` (default `release`): the release APK comes out signed and installable; the script verifies the signature.
- Android diagnostic "The page is blank" when the list page loads but its scripts do not run.
- Android: on a WebView older than Chrome 80 (Android 7 ships Chrome 52, which showed a blank page) the list opens in the default browser, with an explanatory screen and an "Open in browser" button.
- Android: the workspace path in Termux can be changed on the diagnostic screen and is kept in the app, so moving the clone needs no new APK.
