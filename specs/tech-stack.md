---
version: 3
status: approved
updated: 2026-11-23
---

# Tech Stack

## Languages & runtimes

- Python for the backend, the Python helper library and the desktop client. Backend uses the standard library `http.server`. Python 3.14. pywebview 6.2.1 installs and imports on Python 3.15.2 (checked 2026-11-23); Python 3.14 itself and Termux's Python version remain unverified.
- Apps launched by the launcher are Python or Node.js apps (Node 26; Node is optional and needed only for JS apps). `.py` files run with Python, `.js` and `.mjs` files run with `node`.
- Native Android client: Kotlin + Gradle.
- Frontend: Lit (web components), shared by the Android and desktop clients.
- Android: minSdk 26, targetSdk 34.

## Frameworks & libraries

- Lit for the shared frontend, including each app's own UI. Lit is no-build: vendored once as `launcher/frontend/vendor/lit.js` through a one-off esbuild bundle in a scratch directory; widgets are plain ES modules served as-is; npm is needed only to upgrade Lit.
- Android WebView hosts the UI in the APK.
- pywebview for the desktop client (Linux, macOS, Windows); it simulates the Android client's interface.
- Small shared helper libraries, one for Python and one for Node (`node:http` only), that handle the port and stop-self for apps. The backend's `/api/shutdown` is called by the clients.
- Termux (from F-Droid) runs the backend on Android; the APK starts it through the Termux `RUN_COMMAND` intent.

## Infrastructure & tooling

- Project front door is Taskfile (go-task, 3.54.0 verified installed locally): `Taskfile.yml` at the repo root wraps uv (Python environment), docker (APK build) and node, with a task for every important operation (setup, backend, test, app:run, desktop, app:window, refresh, apk:build). uv stays the Python environment manager and tasks call it. Installing task on other platforms is not recorded here (unverified); see https://taskfile.dev/installation/.
- Git: repository initialised with `git init -b main`, no remote yet; the user commits manually.
- The APK is built in Docker. Verified locally: uv, task and docker are installed; docker is provided by Rancher Desktop. No cluster, cloud account or database is involved.
- Repo layout lets scripts run directly from the workspace cloned in Termux.
- Termux setup: `allow-external-apps=true` in `~/.termux/termux.properties`; the APK needs the `com.termux.permission.RUN_COMMAND` permission.
- Startup command in Termux runs `termux-wake-lock` and releases it with `termux-wake-unlock` on server exit via a trap.
- Shutdown: the APK sends `/api/shutdown` when closed, and the backend has a heartbeat watchdog that exits after N seconds without a heartbeat. Decided values: heartbeat period H = 3 s, watchdog N = 15 s. The watchdog is enabled with `--watchdog` (off by default; `start.sh` and the desktop client pass it).
- Local testing on Linux, macOS and Windows with the pywebview desktop client.

## Key conventions

- App contract: each app is a Python `http.server` app or a Node.js app (`.py` run with Python, `.js` and `.mjs` run with `node`) serving its own Lit UI and API on a port passed in as `--port N` (see the port flow in the Config bullet). The Android WebView and the desktop pywebview window load `http://127.0.0.1:<port>/`.
- Config: `apps.json` in the repo workspace, shared by the Android and desktop clients, edited only through the HTTP API. Each entry has only `name` and `script_path`; there is no `port` key in `apps.json`. Port flow (user decision): the APK picks a port for the Termux backend and passes it as an argument in the `RUN_COMMAND` intent; the backend picks a free port per script and passes it to the script. `apps.json` is committed to git and maintained by the user.
- Launcher configuration (user decision): a `.env` file configures the launcher, and `script_path` entries are resolved relative to a workspace root taken from `.env`. `WORKSPACE_ROOT` is the approved key name. `.env` is gitignored; a committed `.env.example` lets the user start from scratch. No other `.env` keys are defined. The Windows rule below still applies: resolve with `pathlib`, check with `os.path.isabs`, and an absolute `script_path` is allowed.
- Naming conventions: JSON and config keys are snake_case (for example `name`, `script_path`).
- GUI layout: full browser width and full viewport height; base text at least 18px and secondary text at least 15px; no narrow centred columns (no `max-w-*`, no `mx-auto`); no fixed-height message boxes.
- Windows: the app must run on Windows. Use `pathlib` and `os.path.isabs` for paths. Treat POSIX-only APIs as unavailable unless guarded by a platform check with a test of that branch.
- No unrequested features and no unrequested security hardening.
- Environment targets: the only dev target for builds is the local Docker context (Rancher Desktop). There are no production targets. Address docker explicitly with `--context rancher-desktop` (verified with `docker context ls`).
