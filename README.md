# mobile-scripts

Runs Python (`.py`) and Node (`.mjs`, `.js`) apps that expose a small web UI. A launcher lists the
apps from `config/apps.json`, lets you add, edit, reorder and delete entries, and starts one and shows
its UI. The target is an Android phone via Termux and a native client, with a desktop client (pywebview)
for testing. Built: the backend (with heartbeat, watchdog and shutdown), the list page, the helpers for
Python and Node apps, two example apps, the Termux start script, the desktop client and the Android
client. The Android client is built but has NOT been run on a device yet; see the on-device
verification checklist below.

## Prerequisites

- [uv](https://docs.astral.sh/uv/): installs Python 3.14 if needed.
- [Task](https://taskfile.dev/installation/): the task runner used for every command below.
- Node is optional and only needed for `.js` and `.mjs` apps (and their tests). The backend needs no Node.

## Repository layout

```txt
Taskfile.yml          tasks: setup, backend, test, app:run, desktop, app:window, refresh, apk:build (run `task` to list them)
android/              Android client (Gradle/Kotlin), docker/Dockerfile, build_apk.py; see android/README.md
apps/                 example apps: hello_py/ (main.py) and hello_js/ (main.mjs), each with a ui/ page
config/               apps.json and .env.example (committed); .env (gitignored)
launcher/
  backend/            stdlib http.server: config loading, JSON API, process control, static files
  frontend/           Lit UI: index.html, styles/, src/ (components/, services/api.js, widgets/), vendor/
  scriptkit/          helpers for apps: python/ (stdlib only) and node/ (index.mjs, node:* only)
  desktop/            pywebview client (the only code that imports webview): host loop, run_script
  termux/             start.sh: starts the backend in Termux with a wake lock
  tools/              helper scripts used by the Taskfile (init_env, run_app)
tests/                pytest, mirroring launcher/
specs/                feature specs
pyproject.toml, uv.lock  Python project and lock file (uv)
README.md, CHANGELOG.md, .gitignore
```

## Setup

```sh
task setup
```

Runs `uv sync` and creates `config/.env` with `WORKSPACE_ROOT` set to this checkout, unless the file
already exists (it is never overwritten). Relative `script_path` entries in `apps.json` resolve
against `WORKSPACE_ROOT`. Edit it if the scripts live elsewhere.

## Run

```sh
task backend            # port 8765
task backend PORT=9000  # another port
```

Open http://127.0.0.1:8765/. The list shows the apps in `config/apps.json`.
Raw equivalent: `uv run python -m launcher.backend --port 8765`.

## Backend API

JSON on `127.0.0.1:<port>`; errors are `{"error": "..."}` with status 400, 404, 409 or 500 (500: a failed app start, a failed save of `apps.json`, or a config error such as an invalid `apps.json` or a missing `WORKSPACE_ROOT`).

| Method and path | Response |
| --- | --- |
| `GET /api/health` | `{"status":"ok"}` |
| `GET /api/apps` | `{"apps":[{"name","script_path"}]}` |
| `PUT /api/apps` | replaces the whole list (`Content-Type: application/json`) |
| `POST /api/apps/{index}/start` | `{"name","port","url"}`; 409 if an app runs, 404 bad index, 400 bad script, 500 if the start fails or the config is invalid |
| `GET /api/running` | `{"running": null}` or `{"running": {"name","port","url"}}` |
| `POST /api/heartbeat` | same body as `/api/running`; records the time of the call |
| `POST /api/shutdown` | `{"status":"shutting_down"}`; then the backend stops the running app and exits with code 0 |

Watchdog: `python -m launcher.backend --port N --watchdog` exits (code 0) 15 seconds after the last
`POST /api/heartbeat`, stopping the running app first; starting counts as the first heartbeat. It is
off by default, so `task backend` works in a plain browser without a host. Logging goes to stderr
unless `--log-file PATH` is given (rotated at 1,000,000 bytes, 3 backups, UTF-8); the running app's
output is logged there too. Hosts (the Termux start script and the desktop client) pass
`--watchdog` and send a heartbeat every 3 seconds. Closing the host calls `POST /api/shutdown`.

## Test

```sh
task test
task test -- -k config  # extra pytest arguments
```

Raw equivalent: `uv run pytest`. The tests need `task` and `node` on the PATH (they fail, not skip, without them).

## Refresh

```sh
task refresh
```

Runs `git pull --ff-only`. Frontend changes show on the next page load (static files are served with
`Cache-Control: no-cache`) and app changes on the next start. Restart the backend after backend changes.

## Use

1. `task backend`, then open http://127.0.0.1:8765/. The list shows the apps in `config/apps.json`.
2. Add: press Add, fill in a name and a script path (relative to `WORKSPACE_ROOT`, or absolute), Save.
3. Edit or Delete a row with its buttons; Up and Down reorder. Each change is saved to
   `config/apps.json` at once and the list is redrawn from what the server saved.
4. Start: the page opens the app's own UI (on its own port). A failure to start shows as a red
   message on the list.
5. Stop: press the app's Stop button (`<stop-button>`). The app exits; returning to the list
   automatically is done by the host clients (`task desktop`); in a plain browser go back by hand.
   Only one app runs at a time. Stopping the backend (Ctrl-C) stops the running app too.

To run one app without the launcher: `task app:run -- apps/hello_py/main.py` (the path is relative to
the directory the task runs in, the repo root; add `--port N` to choose the port). It prints the URL and runs until the app exits. The app runs with `WORKSPACE_ROOT` from `config/.env` as its working directory, like in the launcher, so `config/.env` must exist.

## Writing an app

The contract is the same for every language:

1. Accept `--port N` on the command line and listen on `127.0.0.1:N`.
2. Serve the UI at `/` on that port.
3. Stop by exiting, or when the page sends `POST /_launcher/stop` (exit code 0).

The launcher runs `.py` files with the Python that runs the backend and `.js` and `.mjs` files with
`node` from `PATH` (no `node` gives a clear error on Start). It starts the app in `WORKSPACE_ROOT`
with the repo root on `PYTHONPATH`, so nothing has to be installed. The helpers below implement the
contract and also serve `launcher/frontend/` at `/_launcher/` on the app's port (no-cache), so an
app page can import `/_launcher/vendor/lit.js` and the shared widgets, such as
`/_launcher/src/widgets/stop-button.js` (`<stop-button>`, which sends the stop request) and style the
button with `/_launcher/styles/stop-button.css`. Keep the layout rules: full width and height, text
at least 18px (15px for `.secondary`), no `max-width`, no centring margins, no px heights; buttons
get `min-height: 3rem`.

Minimal Python app, `apps/mine/main.py` (the helper is stdlib only; `stop()` stops it from code):

```python
import sys
from pathlib import Path

from launcher.scriptkit.python import parse_port, run_app

run_app(
    Path(__file__).parent / "ui",                      # served at /
    parse_port(sys.argv[1:]),
    routes={("GET", "/api/hello"): lambda: {"text": "hi"}},  # optional JSON routes
)
```

Minimal Node app, `apps/mine/main.mjs` (`node:*` modules only, no npm):

```js
import { fileURLToPath } from "node:url";
import { parsePort, runApp } from "../../launcher/scriptkit/node/index.mjs";

await runApp({
  uiDir: fileURLToPath(new URL("./ui/", import.meta.url)),   // served at /
  port: parsePort(process.argv.slice(2)),
  routes: { "GET /api/hello": () => ({ text: "hi" }) },     // optional JSON routes
});
```

Then add it in the list (Add), or put `{"name": "Mine", "script_path": "apps/mine/main.py"}` in
`config/apps.json`. Python and Node changes apply on the next start. `apps/hello_py` and
`apps/hello_js` are complete examples with a Lit page.

## Desktop client

The desktop client simulates the Android client on Linux, macOS and Windows: it reads the same
`config/` and talks to the same backend API, with a pywebview window in place of the Android WebView.

```sh
task desktop                                # the list in a window
task app:window -- apps/hello_py/main.py    # one app in a window, without the launcher
```

- `task desktop` runs the same four steps as the Android client: it picks a free port, starts
  `python -m launcher.backend --port N --watchdog`, waits for `GET /api/health`, opens a window titled
  "Mobile Scripts" on the list, sends `POST /api/heartbeat` every 3 seconds and sends
  `POST /api/shutdown` when the window closes. When an app stops itself or crashes, the heartbeat
  reports no running app and the window returns to the list within 3 seconds. The log (stderr) shows the
  chosen port, every navigation and the backend's exit code.
- `task app:window -- <script>` starts one app (the path is relative to the directory the task runs in, the repo root; add
  `--port N` to choose the port) and opens a window on it. Closing the window stops the app; the app
  exiting closes the window. The app runs with `WORKSPACE_ROOT` from `config/.env` as its working directory, like in the launcher.
- Closing the window, Ctrl-C or SIGTERM stops the backend and any running app.
- pywebview is a desktop-only dependency (uv dependency group `desktop`), so `task desktop` and
  `task app:window` run `uv run --group desktop ...`; `task test` and `task backend` do not need it.
  Only `launcher/desktop/window.py` imports `webview`; a test enforces that. Verified on macOS with
  Python 3.15.2 and pywebview 6.2.1; Linux and Windows need the pywebview system requirements
  (Linux: a GTK or Qt WebKit binding, see the pywebview installation docs) and are unverified.

## Android client

**The Android client has not been run on a device yet.** It builds (`task apk:build`), but every step
below that touches Termux or a phone is UNVERIFIED until you try it. Facts about the Termux
`RUN_COMMAND` intent come from Termux's own documentation and sources (links and what stays unverified:
`android/README.md`).

How it works: the app starts `launcher/termux/start.sh <port>` in Termux through the RUN_COMMAND intent
(background command, port chosen by the app), waits up to 30 seconds for `GET /api/health`, and only then
shows a WebView with the list. While it waits, and when something fails, it shows a native screen, never
an empty WebView. The app sends a heartbeat every 3 seconds; closing the app calls `POST /api/shutdown`,
and the backend's watchdog (15 seconds without a heartbeat) covers a killed app. If 3 heartbeats in a
row fail (about 9 seconds), or the WebView cannot load a page (main frame only), the native diagnostic
replaces the WebView; Retry first asks the previous backend to shut down, then starts a new attempt.

### Termux setup

Do this once on the phone or tablet. Package names are to be checked on the device (`pkg search`).

1. Install Termux from F-Droid (this project assumes the F-Droid build, version 0.109 or newer).
2. In Termux: `pkg install python git`. Add `nodejs` only if you want JavaScript apps. UNVERIFIED: the
   package names, and which Python version this installs (the code avoids syntax newer than Python 3.11
   on a best-effort basis, checked by a test). `termux-wake-lock` and `termux-wake-unlock` are part of
   Termux's core `termux-tools` package, so `termux-api` is not needed for them.
3. Clone this repo to `~/mobile-scripts` (`git clone <your remote> ~/mobile-scripts`). The app expects it
   at `/data/data/com.termux/files/home/mobile-scripts`; for another path build the APK with
   `uv run python android/build_apk.py --workspace-dir PATH`.
4. Create `config/.env`: `cp config/.env.example config/.env`, then edit `WORKSPACE_ROOT` if the scripts
   are not at the default path. Termux has no `uv` or `task` unless you install them, so `task setup`
   is not used here.
5. Allow external apps to run commands in Termux, then reload the settings:

   ```sh
   mkdir -p ~/.termux
   echo 'allow-external-apps=true' >> ~/.termux/termux.properties
   termux-reload-settings
   ```

   Without this, Termux refuses the command and shows a notification; the app then reports that the
   backend did not answer.

### Install on a phone or tablet

1. On the computer: `task apk:build` (see "Android build" below). The APK is `android/dist/app-debug.apk`.
2. Copy it to the device (USB, cloud drive, any file transfer) and open it in the file manager. Android
   asks you to allow installs from that app (the file manager); allow it once. Optional alternative:
   `adb install -r android/dist/app-debug.apk`. Later builds use the same signing key (the keystore in
   `android/.cache/`), so they install over the previous one.
3. First launch: the app asks for the Termux `com.termux.permission.RUN_COMMAND` permission; grant it. If the
   dialog does not appear, grant it in Android Settings, Apps, Mobile Scripts, Permissions (the Termux
   wiki says "Additional permissions"). UNVERIFIED: that the system shows this dialog for it, and its wording.

What you should see (UNVERIFIED, never observed):

1. A full-screen "Starting Termux backend..." text for a few seconds.
2. The app list. Press Start on "Hello (Python)": its page appears full screen. Its Stop button ends the
   script and the app returns to the list within about 3 seconds.
3. If it fails (health check not answered within 30 seconds, Termux missing, permission denied) a
   diagnostic screen shows the concrete failure, a checklist of likely causes and a Retry button.
   The logs are in Termux: `$HOME/launcher-backend.log` and `$HOME/launcher-backend.start-error.log`.

Refresh after changes: in Termux `cd ~/mobile-scripts && git pull --ff-only`, then close and reopen the
app (closing stops the backend, so the next start runs the new code).

### On-device verification checklist

Check these once and note what differs (all UNVERIFIED until then):

- [ ] (a) Launching the APK starts `start.sh` in Termux with the port the APK chose (the first line of
      `$HOME/launcher-backend.log` says "starting backend on port N").
- [ ] (b) The list loads in the app.
- [ ] (c) `termux-wake-lock` is active while the app runs (Termux notification shows the wake lock) and
      released after the app is closed (the log says "wake lock released").
- [ ] (d) Which Python version Termux has (`python --version`) and that the backend runs on it.
- [ ] (e) Cleartext HTTP to 127.0.0.1 works in the WebView and for the health, heartbeat and shutdown calls.
- [ ] (f) Swiping the app away from the recent apps list stops the backend within about 15 seconds
      (watchdog), or at once if `onDestroy` ran.
- [ ] (g) With the list shown, kill the backend in Termux (for example `pkill -f launcher.backend`):
      the diagnostic "The backend stopped answering" appears within about 9 seconds, and Retry
      brings the list back.

### Android build

```sh
task apk:build
```

- Needs Docker through the Rancher Desktop context `rancher-desktop` (passed explicitly; override with
  `uv run python android/build_apk.py --context NAME`).
- `--workspace-dir PATH` sets the repo path inside Termux that the APK uses (default
  `/data/data/com.termux/files/home/mobile-scripts`).
- The APK lands in `android/dist/app-debug.apk`.
- The image runs as `linux/amd64` because the Android build tools only ship x86_64 binaries. On an
  arm64 host (Apple silicon) that means emulation: measured here, the first build took about 9 minutes
  (image about 2.6 GB on disk, SDK and Gradle downloads) and a repeat run about 1 to 3 minutes.
- Gradle downloads and the debug keystore are cached in `android/.cache/` (gitignored), so updates
  keep the same signing key.
- Chosen versions and their sources: `android/README.md`.

### Termux start script

`launcher/termux/start.sh <port>` is what the app runs:

- It takes the wake lock (`termux-wake-lock`), starts `python -m launcher.backend --port <port>
  --watchdog --log-file $HOME/launcher-backend.log` from the repo root, and releases the lock (`termux-wake-unlock`) when the backend ends,
  also on SIGTERM, SIGINT or SIGHUP to the script.
- Logs, so a failure can be read later without adb:
  - `$HOME/launcher-backend.log`: the backend's lines (start, requests, watchdog, shutdown), the
    running app's output (stdout and stderr, logger `app`) and the script's own lines, including a
    start line with the date and the port. The backend rotates it at 1,000,000 bytes and keeps 3
    backups (`.1` to `.3`), so it takes about 4 MB at most; the script rotates it the same way with
    `mv` before it appends its own lines.
  - `$HOME/launcher-backend.start-error.log`: python's stderr from before logging is set up (python
    missing, import error). It is truncated at every start.
- A port that is not a number exits with code 2 and a message in that log.
- The file must keep LF line endings (CRLF breaks the shebang); a test checks it. The tests run it
  under bash with fake `termux-wake-*` commands, so they need bash and are skipped on Windows
  ("Termux-only script").
