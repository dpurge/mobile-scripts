---
title: "Android launcher for Python and Node apps: APK + Termux backend + desktop pywebview client"
kind: feature
status: done
branch: main
version: 1
updated: 2026-11-23
---

## Problem / Motivation

Python and Node.js apps that expose a small web UI have no convenient way to be started and used from an Android phone. The user wants a home-screen icon that lists the runnable apps, starts one, shows its UI full screen, and returns to the list when the app stops itself. The same apps must be testable on Linux, macOS and Windows without a phone, using the same configuration and the same HTTP API.

Request in short: a native thin Kotlin client APK hosting a WebView; a Python `http.server` JSON API backend inside Termux, started by the APK through the Termux `RUN_COMMAND` intent; a shared Lit frontend; a start screen listing apps from config; a view to add, remove, edit (name, script path) and reorder; start turns the app into the script's WebView; a script can stop itself and the WebView returns to the list; `termux-wake-lock` in the startup command, released when the server shuts down; the backend stops when the APK closes; the APK is built in Docker; scripts run from the workspace cloned in Termux; a pywebview desktop client simulates the Android client; uv manages the project and provides the commands that build the APK and run any script.

## Acceptance Criteria

1. On start, the client shows the list of apps read from `config/apps.json` (each entry has only `name` and `script_path`).
2. Add, remove, edit (name, script path) and reorder are available in the UI and persisted to `config/apps.json` through `PUT /api/apps`.
3. Starting an app navigates the WebView (or desktop window) to the started script's UI at `http://127.0.0.1:<port>/`.
4. When a script stops itself, the client returns to the list within H seconds (H = 3 s, approved decision); this also holds when the script crashes.
5. Closing the APK or the desktop window shuts the backend down (`POST /api/shutdown`); when heartbeats stop, the watchdog shuts the backend down after N seconds (N = 15 s, approved decision) and terminates the running script.
6. `launcher/termux/start.sh` acquires `termux-wake-lock` and releases it with `termux-wake-unlock` when the server exits.
7. The APK builds inside Docker through the apk build task in `Taskfile.yml` (which calls `uv run python android/build_apk.py`), and the APK is copied to `android/dist/`.
8. Scripts run from the workspace cloned in Termux without installing anything (no uv, no pip install in Termux).
9. The desktop client (started by its task in `Taskfile.yml`, which calls `uv run python -m launcher.desktop`) runs on Linux, macOS and Windows with the same `config/` and the same API; paths are Windows-safe (`pathlib`, `os.path.isabs`, no POSIX-only APIs).
10. The layout rules hold for `launcher/frontend/styles/` and the CSS of every `apps/*/ui`: no `max-width`, no `margin: auto` centring, no fixed px heights, base font at least 18px, secondary font at least 15px. This covers both example apps (`apps/hello_py/ui`, `apps/hello_js/ui`).
11. `README.md` explains build, installation (Termux setup, RUN_COMMAND permission, `allow-external-apps=true`) and use.
12. The repo root contains only `CHANGELOG.md`, `Taskfile.yml`, `pyproject.toml`, `uv.lock`, `README.md` and `.gitignore` (plus `.git`). (Updated 2026-11-23: `CHANGELOG.md` added at the user's request; it was 5 files.)
13. The source is separated into `android/` (client), `launcher/` (local frontend and backend) and `apps/` (scripts).
14. A JavaScript app (`.js` or `.mjs`) runs through `node`; `apps/hello_js/main.mjs` starts, shows its UI and stops from its Stop button.
15. The app contract is language-neutral and documented in `README.md`: accept `--port N`, serve the UI on that port, stop by exiting or via `POST /_launcher/stop`.
16. The GUI source is readable: `launcher/frontend/` is laid out as `index.html`, `styles/`, `src/main.js`, `src/components/` (one component per small file), `src/services/api.js` (all `fetch` calls live there) and `vendor/`; public pieces have JSDoc; comments explain why; no decorators.
17. After `git pull --ff-only` (documented in `README.md`), frontend changes appear on the next page load and Python or Node changes on the next app start.
18. A `Taskfile.yml` exists whose tasks all have a description (`task --list` shows them) and covers setup, backend run, test, refresh, and (when built) apk build, desktop client and running any app.
19. The Android client never shows an empty WebView: it shows a native status screen while the backend starts, loads the WebView only after `GET /api/health` succeeds, and on timeout shows a native diagnostic listing likely causes with a Retry button (verified on device by the user later; UNVERIFIED until then).

## Approach

Memory consulted: specs/memory.md does not exist yet — none relevant

Layout (repo root has 6 files: `CHANGELOG.md`, `Taskfile.yml`, `pyproject.toml`, `uv.lock`, `README.md`, `.gitignore`):

- `android/`: Gradle/Kotlin project (`app/src/main/` with Manifest, MainActivity, `res/`); `docker/Dockerfile`; `build_apk.py` drives docker and copies the APK to `android/dist/` (gitignored).
- `launcher/backend/`: stdlib `http.server`; config, JSON API, process control, watchdog.
- `launcher/scriptkit/python/` (stdlib only) and `launcher/scriptkit/node/` (`node:http` only, no npm dependencies): helpers for apps; `--port` parsing, `/_launcher/stop`, and serving `launcher/frontend/` at `/_launcher/`.
- `launcher/desktop/`: pywebview client, the only place that imports `webview`, plus `run_script`.
- `launcher/frontend/`: list UI: `index.html`, `styles/`, `src/main.js`, `src/components/` (one component per small file), `src/services/api.js` (all `fetch` calls live here), `vendor/` (`lit.js`, LICENSE, `README.md`). JSDoc on public pieces; comments explain why; no decorators.
- `launcher/termux/`: `start.sh`.
- `apps/`: example apps, one directory each: `hello_py/` (`main.py`) and `hello_js/` (`main.mjs`), each with a Lit `ui/` page and a Stop button.
- `config/`: `apps.json` and `.env.example` committed, `.env` gitignored.
- `tests/`: pytest, mirroring `launcher/`.

Frontend sharing: the backend serves `launcher/frontend/` at `http://127.0.0.1:<port>/`; both WebViews load the same URL, so no assets are packaged in the APK.

Lit, no build step: jsdelivr has no standalone Lit bundle (verified: `lit-core.min.js` returns 404; `index.min.js` and `+esm` are import stubs). Lit is vendored once as `launcher/frontend/vendor/lit.js`, produced by a one-off `npx esbuild` bundle of lit 3.3.3 (BSD-3-Clause, LICENSE committed) run in a scratch directory. There is no `package.json` in the repo. The exact command is documented in `vendor/README.md`; npm is needed only to upgrade Lit. Widgets are plain ES modules that import Lit by relative or absolute URL (no import maps, no bundler, no decorators, no TypeScript) and are served as-is. Static responses send `Cache-Control: no-cache` so a WebView does not keep old modules after a pull. Both scriptkit helpers serve `launcher/frontend/` at `/_launcher/` on each app's port, so app UIs import Lit and the shared widgets by absolute `/_launcher/...` URLs (the example apps import `/_launcher/vendor/lit.js`, `/_launcher/src/widgets/stop-button.js` and `/_launcher/styles/stop-button.css`).

Refresh: the command is `git pull --ff-only` (documented in `README.md`). Frontend changes appear on the next page load; Python or Node changes on the next app start (closing the APK stops the backend). No wrapper script. A git repo and remote are the user's job; `git init` has not been run and the user has not answered.

Host interface (no JS bridge). Each host (Android client, desktop client):

1. picks a free port;
2. starts the backend with `--port N`, polls `GET /api/health`, then loads the list URL;
3. runs a native heartbeat loop, `POST /api/heartbeat` every H seconds;
4. sends `POST /api/shutdown` on close.

Start: the list page calls `POST /api/apps/{index}/start` and sets `location.href` to the returned `url`. Stop-self: the script calls `scriptkit.stop()` or its page POSTs `/_launcher/stop`, and the process exits; the next heartbeat returns `running: null` and the host navigates to the list (latency at most H seconds; this also covers crashes).

Watchdog: the backend exits N seconds after the last heartbeat (startup counts as the first) and terminates the child. One script at a time (409 otherwise). H=3 s and N=15 s (see Decisions).

App launch: the backend picks the interpreter by file extension: `.py` uses `sys.executable`; `.js` and `.mjs` use `node` found with `shutil.which`. An unknown extension returns 400; a missing `node` returns 400 with a clear message. Node is needed only for JS apps (Node 26 in Termux is stated by the user, unverified by us). It spawns `[interpreter, script, "--port", P]` with `PYTHONPATH=<repo root>` built with `os.pathsep` and `pathlib`, no shell. Nothing is installed, so Python apps work on Termux without uv. The app contract is language-neutral and documented in `README.md`: accept `--port N`, serve the UI on that port, stop by exiting or via `POST /_launcher/stop`.

Decision made 2026-11-23 for Termux compatibility: the code in `launcher/backend`, `launcher/scriptkit/python`, `launcher/tools` and `apps` must not use syntax newer than Python 3.11 (checked best-effort by `test_syntax_compat`).

Wake lock: `launcher/termux/start.sh` sets its traps first and then runs `termux-wake-lock`. It starts `python -m launcher.backend --port "$1" --watchdog --log-file "$HOME/launcher-backend.log"` as a background job and waits on it (no `exec`). A signal only runs a trap after the foreground command ends, hence the wait. The INT, TERM and HUP traps exit (130, 143, 129) and fire the EXIT trap, which kills the backend and then runs `termux-wake-unlock`. The desktop client starts Python directly (Windows-safe).

pywebview isolation: an AST test (Python side only) allows only stdlib modules in `launcher/backend` and `launcher/scriptkit/python`.

Config: `apps.json` and `.env.example` live in `config/`; the backend reads them via `Path(__file__).parents[2]/"config"`. `.env` is parsed by our own stdlib code (no python-dotenv). Path resolution: the code (`launcher/backend/config.py`, `resolve_script_path`) uses `Path(script_path).is_absolute()`: an absolute path is used as is, otherwise it is `Path(WORKSPACE_ROOT)/p`. The reviewer judged `Path.is_absolute()` equivalent to `os.path.isabs` for the supported Python versions; I did not verify that myself. A missing `.env` or key fails fast with a message naming `config/.env.example`. Sample `apps.json`: `{"apps":[{"name":"Hello (Python)","script_path":"apps/hello_py/main.py"},{"name":"Hello (Node)","script_path":"apps/hello_js/main.mjs"}]}`. Sample `.env.example`: a comment line plus `WORKSPACE_ROOT=/data/data/com.termux/files/home/mobile-scripts`.

API (JSON on `127.0.0.1:<port>`; errors are `{"error": "..."}` with 400, 404, 409 or 500):

| Method and path | Response |
| --- | --- |
| `GET /` | static frontend |
| `GET /api/health` | `{"status":"ok"}` |
| `GET /api/apps` | `{"apps":[{"name","script_path"}]}` |
| `PUT /api/apps` | replaces the whole list (covers add, remove, edit, reorder); `name` and `script_path` non-empty strings; atomic write (temp file, then `os.replace`) |
| `POST /api/apps/{index}/start` | `{"name","port","url"}`; 409 if running, 404 bad index, 400 missing file, unknown extension or missing `node` |
| `GET /api/running` | `{"running": null or {"name","port","url"}}` |
| `POST /api/heartbeat` | same body as `/api/running` |
| `POST /api/shutdown` | `{"status":"shutting_down"}` |

Taskfile: `Taskfile.yml` is the front door; every task has a description. A task is added in the slice that creates the thing it runs, so there are no dead tasks. Taskfile is cross-platform, so no POSIX-only commands in it. Task names are defined in slice 1b. The underlying commands are:

Commands: `uv run pytest`; `uv run python -m launcher.backend --port 8765`; `uv run python -m launcher.desktop`; `uv run python -m launcher.desktop.run_script apps/hello_py/main.py`; `uv run python android/build_apk.py` (runs docker with `--context rancher-desktop`).

Ordered slices (status: 1, 1b, 2, 4, 5, 6 and 7 done, 8 built but not run on a device, 3 deferred, the rest not started), each runnable and each ending with a README section and a spec update:

1. (done) Backend read-only list on macOS: config loading, `/api/health`, `GET /api/apps`, static list page with vendored `vendor/lit.js` (one-off esbuild bundle, see above), `Cache-Control: no-cache` on static responses, full-width CSS.
1b. (done) Taskfile (setup, backend, test, refresh): `Taskfile.yml` with described tasks for environment setup, running the backend, running the tests and refreshing (`git pull --ff-only`); README section on installing task (https://taskfile.dev/installation/; non-mac install steps unverified).
2. (done) Docker APK build of a stub Activity showing a fixed page. Verifies JDK, Gradle, AGP, Kotlin, SDK 34, build-tools and base image (verified, see Implementation Notes). The debug keystore persists in the gitignored, bind-mounted `android/.cache` (settled in this slice).
3. (deferred by the user 2026-11-23: no phone available now; its checks move to the end of slice 8 as an on-device verification list; everything phone-related stays UNVERIFIED until the user tests) Termux `RUN_COMMAND` spike, bounded to ONE phone session (about 15 minutes of the user's time; agent work is only writing the stub). Success, all observed on the phone: (a) launching the APK starts `start.sh` in Termux with the APK-chosen port; (b) the APK shows the JSON body of `/api/health` from that port; (c) `termux-wake-lock` is active and released after Ctrl-C. The user does by hand: install F-Droid Termux (0.109 or newer), `pkg install python termux-api` (whether termux-api is needed is UNVERIFIED), clone the repo to `~/mobile-scripts`, create `config/.env`, set `allow-external-apps=true` in `~/.termux/termux.properties` and run `termux-reload-settings`, install the APK, grant the RUN_COMMAND permission. Also checked, all UNVERIFIED: Termux Python version versus 3.14; manifest `<queries>` for `com.termux`; cleartext HTTP to 127.0.0.1 under targetSdk 34 (network security config); `startService` versus `startForegroundService`; Termux home and `$PREFIX/bin/bash` paths. If it fails: stop and report alternatives; do not work around.
4. (done) CRUD and reorder: `PUT /api/apps`, add, remove, edit, up and down controls. Also, together with slice 5: the Taskfile task `app:run`, the shared widget `launcher/frontend/src/widgets/stop-button.js` and the `test_syntax_compat` check (see slice 5).
5. (done) Both scriptkit helpers (Python and Node), `apps/hello_py` and `apps/hello_js`, interpreter selection, start and stop. `run_script` picks a port and opens pywebview; `--port N` is optional. Slices 4 and 5 also add the Taskfile task `app:run` (run any app directly: `task app:run -- apps/hello_py/main.py`, via `launcher/tools/run_app.py`), the shared widget `launcher/frontend/src/widgets/stop-button.js`, and the `test_syntax_compat` check (`ast.parse` with `feature_version=(3, 11)` over `launcher/backend`, `launcher/scriptkit/python`, `launcher/tools` and `apps`; best-effort only, because the Termux Python version is unverified and may be older than 3.14).
6. (done) Heartbeat, watchdog, shutdown, finish `start.sh` (verified with curl).
7. (done) Desktop client `launcher.desktop`: spawns the backend, host loop, returns to the list on stop-self, shutdown on close. pywebview `create_window`, `events.closed`, `load_url`, `get_current_url` and Python 3.14 support are UNVERIFIED and checked with `inspect` in this slice. Verified on macOS; Linux and Windows are left to the user.
8. (done at build level; UNVERIFIED on a device) Full Android client: WebView, health poll, heartbeat loop, return to the list, shutdown when `isFinishing`. `onDestroy` reliability on swipe-away is UNVERIFIED; the watchdog covers it. The activity is native-first and never shows an empty WebView: it shows a native status screen ("Starting Termux backend..."), loads the WebView only after `GET /api/health` succeeds, and on timeout (bounded; the number of seconds is stated when chosen) shows a native diagnostic listing likely causes (Termux not installed, `allow-external-apps` not true, RUN_COMMAND permission not granted, repo not at the workspace path, python missing) with a Retry button. The manifest needs the permissions `com.termux.permission.RUN_COMMAND` and `INTERNET`, a `<queries>` entry for `com.termux`, and a network-security config allowing cleartext HTTP to 127.0.0.1 (each UNVERIFIED on device). The workspace directory the APK passes to Termux is a build-time constant defaulting to `/data/data/com.termux/files/home/mobile-scripts` (the `.env.example` path), overridable by a `build_apk.py` option. The slice 3 checks move to the end of slice 8 as an on-device verification list for the user.

Testing (offline, fast, scripted): pytest with the server in a thread on port 0 and a temporary config dir. Cases: config path resolution including a Windows-style absolute string via `ntpath.isabs`, and a missing `.env`; API CRUD, validation and atomic write; start and stop of `apps/hello_py` as a subprocess, 409 on a second start; interpreter selection as a pure function (extension to interpreter, unknown extension, node missing); the Node helper is checked by running `apps/hello_js` in a test only if `node` is on PATH, otherwise the test FAILS with a message rather than skipping; watchdog timeout injected as 0.5 s; shutdown kills the child; AST import-boundary test (Python side only); layout test over `launcher/frontend/styles/` and `apps/*/ui` CSS (both example apps); desktop host logic as pure functions `next_url(current_url, running, list_url)` and a port picker, tested without importing pywebview. Android: `gradle assembleDebug` succeeds in Docker; behaviour is verified by hand on the phone per slice 3's checks; no emulator, no live probes. JS unit tests with the built-in `node --test` for pure modules are proposed; decision at slice 4. Not covered by automated tests: Lit components, pywebview windows, Android WebView behaviour (checked by hand at their slice).

Risks (reported; no features added for them):

- High: any local app can reach the loopback API and, via `PUT /api/apps` then start, run arbitrary Python as the Termux user.
- Medium-High: CSRF or DNS rebinding from a browser on the phone if Content-Type is not required to be `application/json`.
- Medium: `allow-external-apps=true` lets any app with the RUN_COMMAND permission run commands in Termux.
- Low: `/api/shutdown` is callable by any local app; free-port race.
- `script_path` runs whatever file is named, including absolute paths, by design.
- The debug keystore would regenerate per container; settled by bind-mounting the gitignored `android/.cache` (slice 2).
- `apps.json` is committed but edited on the phone through the API, which can cause git merge conflicts.
- Termux Python may not be 3.14.

Decisions (approved by the user 2026-11-23):

- Heartbeat period H=3 s and watchdog timeout N=15 s.
- `apps.json` and `.env.example` live in `config/` (moved from the repo top level).
- Name of the workspace key: `WORKSPACE_ROOT`.
- Android back button while a script runs: nothing added (not specified).
- Location of the debug keystore: settled in slice 2 (bind-mounted, gitignored `android/.cache`).
- JS unit tests with `node --test` (decision at slice 4).
- App renamed to mobile-scripts (2026-11-23): project name, default workspace path `/data/data/com.termux/files/home/mobile-scripts`, Android applicationId `local.mobilescripts`, home-screen label Mobile Scripts, build image tag; the feature slug `android-launcher` is unchanged; the user renames their local clone directory themselves.

## Affected Areas

- New: `android/` (Gradle/Kotlin project, `docker/Dockerfile`, `build_apk.py`, `dist/`).
- New: `launcher/backend/`, `launcher/scriptkit/python/`, `launcher/scriptkit/node/`, `launcher/desktop/`, `launcher/frontend/` (including `vendor/lit.js`, its LICENSE and `vendor/README.md`), `launcher/termux/start.sh`.
- New: `apps/hello_py/` (`main.py`, `ui/`) and `apps/hello_js/` (`main.mjs`, `ui/`).
- New: `config/apps.json`, `config/.env.example`; `config/.env` is gitignored.
- New: `tests/` mirroring `launcher/`.
- Root files: `CHANGELOG.md`, `Taskfile.yml`, `pyproject.toml`, `uv.lock`, `README.md`, `.gitignore`.
- Constitution files, updated to version 2 (applied, approved 2026-11-23): `specs/mission.md` and `specs/tech-stack.md` (Python or Node apps, no-build Lit, `/api/shutdown`, Docker context `rancher-desktop`, Taskfile), and `specs/roadmap.md` (item title).

## Out of Scope

- Running several scripts at once.
- Authentication or hardening of the loopback API.
- Per-script APK packaging.
- An npm or vite toolchain.
- Emulator tests.
- Features not listed above.

## Implementation Notes

Slice 1 (backend read-only list on macOS): done. All facts below were checked by the coordinator with live commands.

Files created:

- Root: `pyproject.toml`, `uv.lock`, `.gitignore`, `README.md`.
- `config/apps.json` (two sample entries), `config/.env.example`, `config/.env` (local, gitignored).
- `launcher/__init__.py`, `launcher/backend/{__init__,__main__,config,server}.py`.
- `launcher/frontend/`: `index.html`, `styles/global.css`, `src/main.js`, `src/components/app-list.js`, `src/services/api.js`, `vendor/{lit.js,LICENSE,README.md}`.
- `tests/backend/{test_config,test_server}.py`, `tests/test_layout.py`, `tests/test_imports.py`.

Results:

- `uv run pytest -q -rs`: 37 passed, 0 skipped, 0 failed.
- Real run `uv run python -m launcher.backend --port 8765`: `/api/apps` returned both entries with `Cache-Control: no-cache`; `/vendor/lit.js` returned 200 with 15850 bytes; the port was free after the process was killed.
- Lit 3.3.3 was bundled once with esbuild 0.28.2 in a scratch directory. No `package.json`, `node_modules` or `package-lock.json` in the repo (verified with `find`).

Decisions made in slice 1:

- `app-list` renders into the light DOM (`createRenderRoot` returns `this`) so `styles/global.css`, linked from `index.html`, applies and the layout test can read it.
- "Secondary" text means elements with the `.secondary` class (15px); base text is 18px on `body`.
- `Cache-Control: no-cache` is set in `end_headers`, so it also applies to JSON API responses.
- `GET /api/apps` returns a 500 JSON error if `apps.json` becomes invalid after startup. This is a small addition beyond the 400/404/409 list in the Approach.
- `uv run python --version` reports 3.15.2 on this machine (satisfies >=3.14); the Termux Python version is still unverified.

Unverified:

- The Lit component in a real browser (no automated coverage; the user will open it).
- `resolve_script_path` in `launcher/backend/config.py` has no non-test caller yet. This is intentional: slice 5 (starting scripts) uses it.

Resolved 2026-11-23: the user approved the constitution wording changes (applied, constitution version 2) and `git init` (run: `git init -b main`, no commits, no remote).

Next (as of the end of slice 1): slice 1b, then slice 2; see the slice 1b notes below for the current next step.

Slice 1b (Taskfile): done. All facts below were checked by the coordinator with live commands.

New files: `Taskfile.yml`, `launcher/tools/{__init__,init_env}.py`, `tests/test_taskfile.py`, `tests/tools/test_init_env.py`. `README.md` was rewritten (Prerequisites, Repository layout tree, Setup, Run, Test, Refresh; task is the front door).

Tasks:

- `default`: runs `task --list`.
- `setup`: `uv sync` plus `uv run python -m launcher.tools.init_env`. It creates `config/.env` with `WORKSPACE_ROOT` set to the repo root only if the file is absent, and never overwrites it. It is a stdlib module because `cp` and `sed` are not available in task's builtin shell on Windows.
- `backend`: `PORT` defaults to 8765; `task backend PORT=9000` overrides it.
- `test`: `task test -- -k name` passes arguments to pytest.
- `refresh`: `git pull --ff-only`.

Results:

- `task test`: 42 passed, 0 skipped, 0 failed (was 37; +2 `test_taskfile`, +3 `test_init_env`).
- `tests/test_taskfile.py` fails (never skips) when `task` is not on PATH and pins the task set to {default, setup, backend, test, refresh}. Later slices must update `EXPECTED_TASKS` when they add tasks.
- `task backend PORT=8767` served `/api/health` with 200, and the port was free after the process was killed.
- `task setup` run twice on a scratch copy: the second run left `config/.env` unchanged (identical sha1).
- Call sites: `launcher.tools.init_env` at `Taskfile.yml:14`; `init_env()` at `launcher/tools/init_env.py:34`.

Unverified: Windows runs of `task setup` and `init_env`; `task refresh` was not executed (the repo has no commits).

Next: slice 2 (Docker APK build of a stub).

Slice 2 (Docker APK build of a stub): done. All facts below were checked by the coordinator with live commands.

Result: `task apk:build` builds `android/dist/app-debug.apk` (868614 bytes, 15 files; `unzip -l` lists `AndroidManifest.xml` and `classes.dex`). First run 532 s wall (BUILD SUCCESSFUL in 6m 59s, includes the image build); repeat run 77 s (warm: build directories from run 1 still present). The image `pylauncher-android-build` takes 2.58 GB on disk (933 MB content).

Docker target: context `rancher-desktop`, Lima VM aarch64. The image runs as `linux/amd64` under qemu emulation. Why: the first try as arm64 failed, because the current cmdline-tools `sdkmanager` needs an x86_64 binary and Google publishes only an x86_64 `aapt2` for AGP 9.5.2 (the aarch_64 jar returns 404, verified by the coordinator). The user chose the amd64-emulation spike (30 min cap) and it succeeded; the current cmdline-tools needed no older pin.

Versions (sources in `android/README.md`): AGP 9.5.2, Gradle 9.9.2, JDK Temurin 21, cmdline-tools 16111833, build-tools 36.0.0, platform android-34, Kotlin built into AGP 9; minSdk 26, targetSdk 34, applicationId `local.pylauncher`.

Decision (slice 2 keystore): `android/.cache/{gradle,android}` are bind-mounted as the container's `~/.gradle` and `~/.android` and are gitignored. The debug keystore sha1 `23508e210a896ee5bdf90b1193d31cd427672ac8` was unchanged across runs. Files written by the container are owned by the host user (no root-owned files; checked on Rancher Desktop and macOS only).

Finding: inside the container, github.com presents a Netskope-issued corporate CA chain (issuer `CN=ca.homedepot.goskope.com`) that the host trusts and the container does not ("self-signed certificate in chain"), which broke Gradle's download redirect. Resolved without disabling verification: `build_apk.py` downloads `gradle-9.9.2-bin.zip` on the host into the gitignored `android/.cache/downloads` and verifies the published SHA-256 before the build, and the Dockerfile COPYs it; no CA is installed. Other downloads from github.com inside the container would hit the same TLS problem.

New files: under `android/`: `docker/Dockerfile`, `settings.gradle.kts`, `build.gradle.kts`, `app/build.gradle.kts`, `AndroidManifest.xml`, `MainActivity.kt` (WebView with a fixed inline page), `build_apk.py`, `README.md`; the Taskfile task `apk:build`; `tests/android/test_build_apk.py` (11 offline tests: `--context` and `--platform` pinned, mounts, checksum accept and reject). `task test`: 53 passed, 0 skipped, 0 failed.

Call sites in `android/build_apk.py`: `ensure_gradle_zip` (main), `verify_sha256` (`ensure_gradle_zip`), `sha256_of` (`verify_sha256`), `gradle_zip_name`, `PLATFORM` and `GRADLE_VERSION` (`build_command` and `run_command`).

Unverified: the APK has not been installed or run on a phone; AGP 9.5.2 with Gradle 9.9.2 built here but the AGP page gives only minimums; Linux and Windows hosts; a true cold-cache second run; the network path of `ensure_gradle_zip` (only exercised by the real build); Windows paths in `build_apk.py`.

Next: slice 3 (Termux RUN_COMMAND spike, needs the user's phone).

Plan change 2026-11-23: slice 3 deferred, slices 4-8 proceed without a phone; user will test on device later.

Slices 4 and 5 (CRUD/reorder, start/stop, example apps): done. All facts below were checked by the coordinator with live commands, or are the engineer's report verified by those and by the test run.

Results:

- `task test`: 132 passed, 0 skipped, 0 failed (was 53).
- Real run with the real repo config: starting "Hello (Python)" returned a free port and URL; its `/` gave 200, `/api/info` gave `{"language":"Python","runtime":"3.15.2"}`, and `/_launcher/vendor/lit.js` gave 200. `POST /_launcher/stop` returned `{"status":"stopping"}` and `/api/running` became `{"running": null}`. The same held for "Hello (Node)" (runtime 26.13.1). After SIGINT to the backend the port was free and no `apps/hello_*` process remained. `config/apps.json` was unchanged.

Backend (engineer's report):

- New module `launcher/backend/process.py`: `select_interpreter`, `require_script_file`, `pick_free_port`, `app_env`, `terminate`, `AppRunner`, and `LaunchError`, `AlreadyRunning`, `StartError`.
- `config.save_apps` writes atomically (`mkstemp` in the same directory, then `os.replace`).
- Server routes: `PUT /api/apps` (Content-Type must be `application/json`, else 400), `POST /api/apps/{i}/start`, `GET /api/running`. The child is terminated when the server closes.
- Check order is 404, 409, 400, 500. Start waits at most 10 s for the port and kills a child that exits early or times out.

Helpers and tools:

- `launcher/scriptkit/python/{__init__,kit}.py`: `parse_port`, `run_app`, `stop`, routes keyed `(method, path)`.
- `launcher/scriptkit/node/index.mjs`: `parsePort`, `runApp`, routes keyed `"METHOD /path"`; path-traversal-safe.
- `launcher/tools/run_app.py` and the Taskfile task `app:run`.

Frontend:

- `api.js` (all fetches, including `requestStop`).
- Components `app-list` and `app-form` (Up/Down reorder, Start/Edit/Delete/Add, error banner).
- Widget `src/widgets/stop-button.js`.
- `styles/global.css` and `styles/stop-button.css`.
- All components render in the light DOM, so the CSS the layout test reads applies.

Example apps: `apps/hello_py` and `apps/hello_js` (Lit page, `/api/info`, stop button).

Decisions:

- Buttons use `min-height: 3rem`; the layout test still bans px heights.
- The layout test runs per CSS set.
- The first PUT reformats the committed one-line `apps.json` as indented JSON.
- The `task app:run` script path is relative to the repo root.

Tests: node-dependent tests FAIL (not skip) with a clear message when node is missing (the engineer checked with node removed from PATH: 3 failed). `test_syntax_compat.py` is best-effort only. The engineer's first run caught a real bug in the Node helper (trailing-slash prefix check) and fixed it.

Unverified: the Lit pages in a browser (no screenshots); Windows and Linux; Termux and Python 3.11 (the syntax check is best-effort only); behaviour was only checked on Python 3.15.2 and Node 26.13.1.

Not yet called from outside at the end of slice 5: frontend `fetchRunning` (removed later in the validation review) and Python `stop()` (used inside `kit.py` and by the `/_launcher/stop` handler).

Open: `node --test` JS unit tests (decision still open; not added). Until the host loop exists (slices 7-8), the user returns to the list by hand in a plain browser.

Next (as of the end of slice 5): slice 6; see the slice 6 notes below for the current next step.

Slice 6 (heartbeat, watchdog, shutdown, start.sh, rotating logs): done. All facts below were checked by the coordinator with live commands, or are the engineer's report.

Results:

- `task test`: 157 passed, 0 skipped, 0 failed. The only possible skip is the `start.sh` tests on win32 (reason "Termux-only script"), not triggered here.
- Real run `python -m launcher.backend --port 8774 --watchdog --log-file <scratch>`: `POST /api/heartbeat` returned `{"running": null}`; `hello_py` was started; `POST /api/shutdown` returned `{"status":"shutting_down"}`. Afterwards the `hello_py` process was gone and the port was free. The log shows "Shutdown requested through the API", "main.py (pid N) exited with code -15" and "Backend stopped".
- `bash -n launcher/termux/start.sh` is ok and the file has LF endings; shellcheck is not installed.
- Engineer's measurement from the log timestamps: the watchdog exited 15.0 s after the last heartbeat.
- Rotation run with an injected 20000-byte limit: `launcher.log` plus `.1`, `.2`, `.3`, no `.4`.

Built:

- `POST /api/heartbeat` (same body as `/api/running`; records a monotonic timestamp).
- Watchdog: OFF by default and enabled with `--watchdog` (decision 2026-11-23: so plain `task backend` in a browser does not exit after 15 s; `start.sh` and the desktop client pass it). N = 15 s, startup counts as the first heartbeat, the timeout is injectable for tests.
- `POST /api/shutdown` responds first, then stops the app and exits 0.
- A SIGTERM handler in `__main__` calls `request_shutdown` (added so `start.sh` killing the backend also stops the app).

Logging (user requirement 2026-11-23: logs must rotate):

- `--log-file PATH` uses `RotatingFileHandler` with `LOG_MAX_BYTES` 1,000,000 and `LOG_BACKUP_COUNT` 3 (about 4 MB total); the constants are in `launcher/backend/logs.py` and mirrored in `start.sh`.
- Without `--log-file`, logs go to stderr and no file is created.
- Logged: request lines, uncaught exceptions, start, watchdog and shutdown events, and child start and exit.
- Child app output is captured via `stdout=PIPE, stderr=STDOUT` and a daemon reader thread logging under logger `app` (`PYTHONUNBUFFERED=1` for children).

`start.sh`:

- LF endings are required. The argument is the port; a non-numeric port exits 2 and logs it.
- Traps are set before `termux-wake-lock`, and there is no `exec`.
- The backend runs in the background and is waited on, so INT, TERM and HUP traps (exit 130, 143, 129) fire the EXIT trap, which kills the backend and then runs `termux-wake-unlock`.
- Python is invoked with `--watchdog` and `--log-file "$HOME/launcher-backend.log"`. Its pre-logging stderr goes to `"$HOME/launcher-backend.start-error.log"`, truncated at every start. The script's own lines rotate with `mv` (`.1` to `.3`) when over 1,000,000 bytes.
- The README has a Backend API section and the Termux notes.

New files: `launcher/backend/logs.py`, `launcher/termux/start.sh`, `tests/conftest.py`, `tests/backend/{test_watchdog,test_main_process,test_logs}.py`, `tests/termux/test_start_sh.py` (fake `termux-wake-lock` and `termux-wake-unlock` on PATH).

Call sites: `record_heartbeat` at `server.py:60` and `:181`; `request_shutdown` at `server.py:66` and `__main__.py:39`; `logs.configure` at `__main__.py:30`; `_drain_output` at `process.py:86` (definition; I did not re-grep its callers).

Unverified: the real `termux-wake-lock` and `termux-wake-unlock`; Termux Python and bash (only macOS bash 3.2 and Python 3.15.2 were run); the `$HOME` path on Termux; Windows for the Python side; no mutation run of the new tests.

Next: slice 7 (desktop client) and slice 8 (Android client), in parallel.

Slice 7 (pywebview desktop client): done. All facts below were checked by the coordinator with live commands, or are the engineer's report consistent with them.

Results:

- `task test`: 197 passed, 0 skipped, 0 failed.
- Real run of `task desktop`: the log shows "Using port N"; the backend started with `--watchdog`; heartbeats every 3 s; `GET /api/health` ok; `POST /api/apps/1/start` started Hello (Node) (`/api/info` gave `{"language":"JavaScript","runtime":"26.13.1"}`); `POST /_launcher/stop` made `/api/running` null. SIGTERM led to `POST /api/shutdown`, "Backend stopped" and "Backend exited with code 0". No leftover processes, ports free.
- Return to the list: the engineer's scratch driver (not in the repo) replaces the Start click with `window.load_url`; everything else is real (window, `watch_backend`, backend). The coordinator re-ran it: the window was at the app URL, then about 3.4 s after the app's stop the log showed "Navigating to <list url> (no app is running)" and the window URL was the list again. SIGTERM was clean (exit 0, no leftovers).

Built (engineer's report):

- pywebview 6.2.1 installs and imports on Python 3.15.2 (pyobjc 13.0 wheels). It is added as the uv dependency group `desktop` (run with `uv run --group desktop ...`). Signatures confirmed with `inspect`: `webview.create_window`, `webview.start`, `Window.load_url`, `Window.get_current_url`, `Window.destroy`, `window.events.closed`.
- `launcher/desktop/host.py`: pure logic plus the backend subprocess, with no `webview` import (`next_url`, `list_url`, `api_url`, `backend_command`, `launch_backend`, `wait_for_health`, `send_heartbeat`, `heartbeat_step`, `watch_backend`, `shutdown_backend`, `install_stop_signals`).
- `launcher/desktop/window.py`: the only file importing `webview`. `launcher/desktop/__main__.py`: the host loop. `launcher/desktop/run_script.py`.
- Taskfile tasks `desktop` and `app:window` (`task app:window -- <script>`).
- `AppRunner.start` in `launcher/backend/process.py` gained an optional `port=` argument, reused by `run_script`, which also reuses `select_interpreter`, `pick_free_port` and `app_env`.
- Tests: `tests/desktop/test_host.py` (`next_url` 10 cases, heartbeat against a fake server, backend start failures, shutdown order, `watch_backend` with a fake window) and an AST test that only `launcher/desktop/window.py` imports `webview`.

Bug found and fixed in the real run: SIGTERM was ignored by `app:window` because the GUI main loop only runs Python signal handlers when a call reaches it. `window.py` now has a wake-up thread reading `get_current_url` every 0.5 s.

Decisions: the window opens maximized and resizable; the HTTP client bypasses environment proxies; heartbeat H = 3 s.

Risk (not changed): the first window start after a fresh install took about 12 s (later about 1 s) and the watchdog is 15 s, so a very slow first start could trip it.

Unverified: Linux and Windows runs; `signal.SIGTERM` on Windows; a real Start click and the rendering of the window (no screenshots); the Python 3.11 syntax of `launcher/desktop` is not covered by the compat test; no mutation run.

Next: the slice 8 follow-up (diagnostics for heartbeat failures and WebView load errors) is in progress, then validation.

Slice 8 (Android client, native-first): built, not run on a device. Facts below were checked by the coordinator with live commands on the final APK, or are the engineer's report (build-level facts; behaviour unverified).

Checked on `android/dist/app-debug.apk` (901575 bytes):

- The manifest (decoded with `iconv` UTF-16LE) contains `com.termux.permission.RUN_COMMAND`, `android.permission.INTERNET`, package `com.termux` (queries), `networkSecurityConfig`, `configChanges` and the label "Mobile Scripts".
- `res/xml/network_security_config.xml` is present (552 bytes).
- `classes3.dex` (37272 bytes) holds the `local/mobilescripts` classes `BackendClient`, `BuildConfig`, `ConsecutiveFailures`, `HeartbeatLoop`, `MainActivity`, `MainFrameErrorClient`, and the strings "Starting Termux backend...", "The backend stopped answering", "The page could not be loaded" and `onReceivedHttpError`.
- The debug keystore sha1 is unchanged (`23508e210a896ee5bdf90b1193d31cd427672ac8`).
- `task test` passed 197 (0 skipped, 0 failed) in 4 of 5 coordinator runs. One run failed with exit 1 and its output was lost; it was not reproduced in 4 reruns. A flaky test is suspected and the tester is hunting it. OPEN ISSUE: the suite is not confirmed clean.

Termux findings (engineer's report; sources: https://raw.githubusercontent.com/wiki/termux/termux-app/RUN_COMMAND-Intent.md, Termux sources on master, termux-tools `build.sh`):

- Service `com.termux/com.termux.app.RunCommandService`, action `com.termux.RUN_COMMAND`, extras `RUN_COMMAND_PATH` (String), `_ARGUMENTS` (String[]), `_WORKDIR` (String), `_BACKGROUND` (boolean).
- The permission `com.termux.permission.RUN_COMMAND` is protectionLevel dangerous in Termux's manifest (the wiki documents only the Settings route).
- `allow-external-apps=true` is mandatory. When missing, Termux shows an error notification and runs nothing, without raising an exception to the caller; the app can only notice through the 30 s health timeout.
- The wiki example uses `startService` from an activity (used here).
- `<queries>` for `com.termux` is needed at targetSdk 30 and above.
- `termux-wake-lock` and `termux-wake-unlock` ship in `termux-tools`, which is essential, so `termux-api` is not needed.
- The cleartext config uses 127.0.0.1 and localhost; whether IP-literal domain entries are honoured by `HttpURLConnection` and WebView is UNCLEAR in the docs.

Design (engineer's report): a native-first state machine. Classes in `android/app/src/main/java/local/mobilescripts/`:

- `MainActivity` (state and wiring), `TermuxLauncher` (installed check, permission request, intent), `BackendClient` (health, heartbeat, shutdown over `HttpURLConnection`, `pickFreePort`).
- `HeartbeatLoop` (3 s; gives up after 3 consecutive failures via `ConsecutiveFailures`, constant `MAX_FAILURES_IN_A_ROW`), `NextUrl` (pure `nextUrl`).
- `MainFrameErrorClient` (main-frame WebView errors and HTTP 400 or above are replaced by the native diagnostic with URL and error), `StatusScreen` (status and diagnostic views with Retry).
- Health timeout 30 s polled every 0.5 s. Retry first POSTs `/api/shutdown` to the previous attempt's port in the background.
- The workspace directory is `BuildConfig.WORKSPACE_DIR`, defaulting to `/data/data/com.termux/files/home/mobile-scripts`, overridable with `build_apk.py --workspace-dir` (`-PworkspaceDir`).
- `configChanges` so rotation does not recreate the activity; the back button is unchanged.

Known gaps (not done):

- No JVM unit tests for the Kotlin logic.
- A Retry does not stop a half-started backend except by its watchdog (15 s) and the shutdown POST.
- The `workspaceDir` value is not escaped.
- A legitimate main-frame HTTP 4xx from an app page shows the diagnostic, by design.

UNVERIFIED on a device:

- The RUN_COMMAND permission dialog and the "don't ask again" behaviour.
- `startService` from the activity on API 26 and above, and Termux accepting `bash start.sh <port>` with workdir and `background=true`.
- That a Termux refusal appears only as the 30 s timeout.
- Cleartext to 127.0.0.1 for `HttpURLConnection` and WebView.
- The `<queries>` entry being enough for `getPackageInfo`.
- The WebView showing the list and an app page.
- Stop returning to the list within about 3 s.
- `onDestroy` on swipe-away, and the watchdog stopping the backend within about 15 s.
- Rotation not recreating the activity.
- The 9 s give-up diagnostic, and that the browser error page never shows.
- Wake-lock behaviour.
- Termux Python version and package names (`python`, `git`, `nodejs`).
- Termux home and bash paths.
- A custom `-PworkspaceDir` end to end.
- Screen layouts.

`README.md` has an "Android client" section with the on-device checklist (a)-(g).

Next: validation (tester: flaky hunt, criteria walk; reviewer: security), documentation review, closeout.

Validation review 2026-11-23 (reviewer; read-only security and code review, no Critical or High findings). F2, F3, F4, F7, F15 and F16 are FIXED (2026-11-23); the rest are OPEN-DECISION for the user, because the standing rule is that no unrequested hardening is added.

- F1 (Med) OPEN-DECISION: `start.sh` cleanup releases the wake lock while a newer backend may still run (Retry or reopening within 15 s). It is unverified whether Termux's wake lock is shared.
- F2 (Med, bug) FIXED (2026-11-23): `AppRunner.start` no longer holds its lock during the readiness wait. The lock covers only short state changes, a "starting" state exists, `running()` returns None while starting, and `stop()` during start raises `StartError` ("was stopped during startup"), which the API returns as 500. New tests: `tests/backend/test_slow_start.py` with a 2 s slow-start app (heartbeat and running answer under 0.5 s, a second start gives 409, a stop during start leaves no process).
- F3 (bug) FIXED (2026-11-23): the heartbeat result of a previous attempt is ignored; `HeartbeatLoop` checks `isStopped` before callbacks.
- F4 (bug) FIXED (2026-11-23): `NextUrl.kt` now mirrors the desktop `next_url` (null URL or running script means no navigation; comparison by scheme, host, port and path).
- F5 (Med security) OPEN-DECISION: POST routes accept requests without Content-Type or Origin checks.
- F6 (Med security) OPEN-DECISION: no Host header check, so DNS rebinding is possible; the risk is higher with the fixed port 8765 of `task backend`.
- F7 (Low) FIXED (2026-11-23): the misleading comment on the Content-Type check.
- F8 (Low) OPEN-DECISION: a negative Content-Length is accepted.
- F9 (Low) OPEN-DECISION: directory listings are on in the backend and the Python helper; the Node helper returns 404.
- F10 (Low) OPEN-DECISION: the `apps.json` write is not fsynced.
- F11 (Low) OPEN-DECISION (known): port race in the readiness probe.
- F12 (Low) OPEN-DECISION: `workspaceDir` is not escaped.
- F13 (Low) OPEN-DECISION: the cmdline-tools zip is downloaded without a checksum, and apt is not pinned.
- F14 (Low security) OPEN-DECISION: all links stay inside the WebView.
- F15 (Low) FIXED (2026-11-23): `_kill_code` was removed.
- F16 (Low) FIXED (2026-11-23): `run_app` and `run_script` now use `WORKSPACE_ROOT` via `config.load_workspace_root` as the child's cwd; a missing `config/.env` fails fast naming `config/.env.example`.
- Also done after the review: dead code `fetchRunning` removed; Python `stop()` now has direct tests.
- The Kotlin changes (F3, F4) have no automated tests (no JVM test setup), and the tests for F2 to F4, F15 and F16 were not run against the old code (no baseline).
- Rebuilt APK: 903032 bytes, BUILD SUCCESSFUL, manifest unchanged (checked), keystore unchanged.

Documentation drift fixed on 2026-11-23: `README.md` intro, the desktop client section moved out of "Coming in later slices", the 500 status in the API error list, the working directory of `task app:run`; in this spec, the Lit import paths, the `start.sh` description, the path-resolution wording, the 500 status and the call-site line number for `_drain_output`. The other call-site line numbers in the slice 1b and 6 notes (`Taskfile.yml:14`, `init_env.py:34`, `server.py:60`, `:66`, `:181`, `__main__.py:30`, `:39`) were re-grepped and are correct; the slice 2 notes name functions without line numbers.

## Validation

Final results (observed by the coordinator with live commands; I ran none of them):

- `task test -- -q -rs` run twice: 206 passed, 0 skipped, 0 failed (47.5 s); no stray processes after.
- History: 197 passed earlier. One unexplained failure was traced by the tester to a race inside `tests/backend/test_logs.py::test_child_output_is_rotated_with_the_rest` (glob, then read, while `RotatingFileHandler` renamed files; it failed 5 of 60 runs under 10 background `yes` processes and 0 of 40 when idle). The test was fixed and then passed 60 of 60 under the same load and the whole suite 3 times. The earlier "open issue" about a flaky test is therefore resolved.
- Tester's acceptance walk (all run locally, no device): criteria 1 to 18 PASS. Evidence: `curl` of `/api/apps`, start and stop of both example apps through `task backend` and `task app:run`, shutdown, the `start.sh` tests with fake termux-wake commands, the layout test, `task --list` showing described tasks, `uv lock --check`, and the root file check (`Taskfile.yml`, `pyproject.toml`, `uv.lock`, `README.md`, `.gitignore` plus directories). Criterion 19 and every Android runtime behaviour are UNVERIFIED-ON-DEVICE.
- Reviewer: no Critical or High findings; see the "Validation review" block in Implementation Notes for what was fixed and what stays an open decision.
- Coverage gaps: the Kotlin logic (no JVM test setup); the Lit components and pywebview windows in a real browser or window; Windows and Linux runs; Termux Python (best-effort syntax check for 3.11 only); the F2 to F4, F15 and F16 tests were not run against the old code.

## Documentation Review

Audit of `README.md` and `android/README.md` against the code, the Taskfile and `find` of the tree (the `doc` skill method). Documentation only; no code, test, Taskfile or config edits.

Checked and found correct: the task names (`setup`, `backend`, `test`, `app:run`, `desktop`, `app:window`, `refresh`, `apk:build`, `default`) against `Taskfile.yml`; default port 8765; `requires-python = ">=3.14"` in `pyproject.toml` against "installs Python 3.14"; timeouts (`HEALTH_TIMEOUT_MILLIS = 30_000L` and `HEALTH_POLL_MILLIS = 500L` in `MainActivity.kt`, `PERIOD_MILLIS = 3000L` and `MAX_FAILURES_IN_A_ROW = 3` in `HeartbeatLoop.kt`, `WATCHDOG_TIMEOUT_SECONDS = 15.0` in `server.py`, `START_TIMEOUT_SECONDS = 10.0` in `process.py`); log rotation (`LOG_MAX_BYTES = 1_000_000`, `LOG_BACKUP_COUNT = 3` in `logs.py`, mirrored in `start.sh`); the 48dp Retry button (`MIN_TOUCH_DP = 48`); the log paths in `start.sh`; the manifest claims (`RUN_COMMAND`, `INTERNET`, `<queries>` for `com.termux`, `networkSecurityConfig`, `configChanges`, label "Mobile Scripts"); `build_apk.py` defaults (context `rancher-desktop`, `--workspace-dir`, platform `linux/amd64`, cache directories); `app:run` and `app:window` use `WORKSPACE_ROOT` as the child's cwd (`run_app.py:32`, `run_script.py:33-37`).

Findings fixed in `README.md`:

1. Repository layout tree omitted the root files `pyproject.toml`, `uv.lock`, `README.md`, `.gitignore` (the `find` shows them). Added.
2. "Termux start script" said `start.sh` runs the backend with `--watchdog` only; `start.sh` also passes `--log-file "$HOME/launcher-backend.log"`. Fixed.
3. The Backend API paragraph had a hard-wrapped fragment ("Hosts (the Termux start / script ...) pass the flag"); reworded to name `--watchdog` explicitly.
4. `task app:run` text said the path is relative to the repo root; `run_app.py:20` resolves it against the current directory, which for a task is the repo root. Reworded to "the directory the task runs in, the repo root". That go-task runs tasks in the Taskfile's directory is not verified by me.
5. The Android install section quoted a permission dialog title ("Run commands in Termux environment") that no file I read contains. Replaced by the permission name `com.termux.permission.RUN_COMMAND`, and noted that the dialog and its wording are UNVERIFIED.

`android/README.md`: no drift found against the files above; no edit. It does not name the Docker image tag (`mobile-scripts-android-build` in `build_apk.py`); not a drift.

Acceptance criterion 11: confirmed. `README.md` has "Android build" (build), "Termux setup" and "Install on a phone or tablet" (installation, including the RUN_COMMAND permission and `allow-external-apps=true`), and "Use". The Android sections state in bold that the client has not run on a device and describe the native diagnostic with Retry and the 30 s health timeout.

Constitution check (`specs/mission.md`, `specs/tech-stack.md`). In line: Python or Node apps, no-build Lit, Taskfile front door, `--context rancher-desktop` (re-checked with `docker --context rancher-desktop context ls`), `/api/shutdown`. Drift, listed as PROPOSED edits for the user (NOT applied):

- `specs/tech-stack.md`, Infrastructure bullet "Shutdown": "N not yet chosen"; the code uses N = 15 s with the heartbeat period 3 s, and the watchdog is enabled by the `--watchdog` flag (off by default).
- `specs/tech-stack.md`, Key conventions bullet "Launcher configuration": says `WORKSPACE_ROOT` "is Proposed (needs approval)"; the spec's Decisions list records it as approved.
- `specs/tech-stack.md`, Languages bullet: "Termux and pywebview availability for 3.14 not yet verified"; pywebview 6.2.1 was verified on this machine with Python 3.15.2 (not 3.14), and Termux's Python is still unverified.
- `specs/tech-stack.md`, Taskfile bullet: says "later apk build"; `apk:build` exists.
- `specs/mission.md`, Users bullet: "testing scripts on a desktop" (the rest of the file says apps). Cosmetic.

Changelog: `CHANGELOG.md` created at the user's request (decision changed 2026-11-23; the earlier plan was none until the first release). It has a Keep a Changelog 1.1.0 header and a filled `## [Unreleased]` with `### Added` entries taken from the Acceptance Criteria and Implementation Notes; the Android entry says it is NOT yet run on a device. The repo root now has 6 files. The root-file check in criterion 12 was updated.

CI, build and release review (no `.github/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci` or `azure-pipelines.yml` exist: a `find` at depth 2 returned nothing; the Dockerfile and `build_apk.py` are the build config):

- {android/docker/Dockerfile, needs change: yes (open decision F13, not applied), reason: the cmdline-tools zip is downloaded with `curl` without a checksum and `apt-get install` is not pinned, so a clean rebuild is not reproducible; the amd64 emulation cost (about 9 min first build) comes from x86-only Android tools and is not avoidable here}
- {android/build_apk.py, needs change: no, reason: it passes `--context` and `--platform` explicitly, verifies the Gradle zip's SHA-256 on the host (the workaround for the TLS-intercepting proxy), mounts the gradle and keystore caches and copies the APK to `android/dist/`; Windows paths are unverified}
- {Taskfile.yml, needs change: no, reason: every task has a `desc`, `apk:build` calls `build_apk.py`, no POSIX-only commands, and `test_taskfile.py` pins the task set}
- {.gitignore, needs change: no, reason: it covers `config/.env`, `android/dist/`, `.venv/`, `.agent/`, `__pycache__/`, `.pytest_cache/`, `.gradle/`, `android/**/build/` and `android/.cache/`; consequence: a clean checkout rebuilds from scratch and downloads Gradle on the host}
- CI review: no CI workflows exist (none of `.github/`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci`, `azure-pipelines.yml` found), so there is no release wiring to check; there is no tag-creating workflow and no changelog.

## Documentation Updates

Changed in this closeout (documentation only; the user commits manually, and I drafted no commit message or PR text):

- `README.md`: the five fixes listed in Documentation Review (layout tree root files, `start.sh` flags, Backend API wording, `app:run` path wording, permission wording); earlier in the work the intro and the desktop client section were fixed too.
- `specs/features/android-launcher.md`: Validation, Documentation Review, Documentation Updates, the "Validation review" block (FIXED or OPEN-DECISION per finding), the stale `fetchRunning` line, `status: done`.
- `specs/roadmap.md`: the `## Now` line for this feature was removed and replaced by "None." (not added anywhere else).
- `specs/memory.md`: created per the `memory-format` skill with 7 entries (build, gotcha, convention).
- `CHANGELOG.md` created at the repo root (Keep a Changelog 1.1.0, `## [Unreleased]` with `### Added`, one line per user-facing capability); `README.md` layout tree now lists it; criterion 12 and the Layout and Affected Areas root-file lists in this spec say 6 files.

Constitution: the five proposed edits were approved by the user and applied on 2026-11-23: `specs/tech-stack.md` (now version 3: shutdown values H = 3 s and N = 15 s with `--watchdog`, `WORKSPACE_ROOT` approved, pywebview 6.2.1 verified on Python 3.15.2, Taskfile task list) and `specs/mission.md` (now version 3: "apps" in the Users bullet). Before that, no edit had been made. The proposed edits for `specs/tech-stack.md` and `specs/mission.md` are listed in Documentation Review and wait for the user's approval.

Closeout checklist evidence:

- Every new non-test function, class and constant in `launcher/` and `android/build_apk.py` has a use outside its definition and outside tests: a scripted word-count over `launcher/**` (py, mjs, js, yml, sh, html) and `build_apk.py` flagged only `do_PUT`, `handle_error` and `log_message` in `launcher/backend/server.py`, which are `http.server` framework hooks. `fetchRunning` and `_kill_code` are removed (grep over `launcher` and `tests` finds neither). Python `stop()` is used at `launcher/scriptkit/python/kit.py:87` and is exported in `__all__` as the documented public helper.
- Config key `WORKSPACE_ROOT` is read by `config.load_workspace_root` and used by `run_app.py` and `run_script.py`.
- `specs/roadmap.md` `## Now` is "None.".
- `validate-specs` passes (output in the closeout report).

Pending: the user's final delivery approval, the proposed constitution edits, the OPEN-DECISION findings (F1, F5, F6, F8 to F14), and every on-device check (criterion 19 and the Android runtime behaviour stay UNVERIFIED until the user tests). The repo has no commits; `git status --short` shows the files as untracked (checked for `.gitignore`, `README.md` and `Taskfile.yml` in the first three lines of its output).
