---
title: "Android old-WebView handoff, workspace setting and signed APK build"
kind: bugfix
status: validating
version: 1
updated: 2026-11-24
branch: main
---

## Problem / Motivation

On the user's Android 7 phone the APK installed and started the Termux backend (the app log showed requests and heartbeats), but the WebView showed a blank page. The app log showed `GET /src/main.js`, then only `/favicon.ico` (404, harmless: `http.server` logs "code 404" before the access line of the failing request, reproduced locally). There was no request for `/src/components/app-list.js`, `/vendor/lit.js` or `/api/apps`. The user's Chrome app on the same phone shows the list; a WebView test app on the phone reports the user agent `Chrome/52.0.2743.100` and shows the same blank page.

Cause: the system WebView is Chrome 52, which cannot run the frontend (ES modules, custom elements v1, class fields, `?.` and `??` in `launcher/frontend/src` and `launcher/frontend/vendor/lit.js`). The browser-version numbers are from memory and UNVERIFIED against a compatibility table. A server MIME-type theory was tried, disproved by the user's Chrome result, and its code was reverted.

Other findings made on the way:
- The user had to change `minSdk` 26 to 24 (Android 7 is API 24; the earlier install failure was probably `minSdk`, the user's own statement) and added APK signing by hand.
- The workspace path could not be changed through `task apk:build` because the Taskfile did not forward arguments.
- `tests/android` had 5 red tests after the user's edits.
- Python 3.15's OpenSSL rejected the TLS-intercepting network's certificate for the Gradle download.

## Acceptance Criteria

1. The release APK builds signed and installable at `minSdk` 24 (`android/dist/app-release.apk`; `apksigner verify` passes; the build prints package and SDK levels).
2. `--variant debug|release` selects the build type (default `release`) and the output name `android/dist/app-<variant>.apk`; an unsigned-only result fails with an explanation.
3. `task apk:build -- <args>` forwards the arguments to `android/build_apk.py` (e.g. `--variant debug --workspace-dir PATH`).
4. A cached Gradle zip needs no network; the download uses `curl`, not Python TLS.
5. A WebView below Chrome 80 does not load the list; the list opens in the default browser, the heartbeat keeps running, and a native screen offers an "Open in browser" button. UNVERIFIED on a device.
6. The workspace path in Termux can be changed on the diagnostic screen without rebuilding the APK, is kept in the app, and defaults to `BuildConfig.WORKSPACE_DIR`. UNVERIFIED on a device.
7. When the list page loads but its scripts do not run, the diagnostic "The page is blank" is shown. UNVERIFIED on a device.
8. `tests/android` is green and covers the changed build script.
9. `README.md`, `android/README.md` and `CHANGELOG.md` describe the changes.

## Approach

Memory consulted: apk|WebView|TLS|curl|build — 2 relevant entries (APK build image runs as linux/amd64; the TLS-intercepting proxy breaks Gradle downloads inside containers)

Fix the build and diagnose the old WebView; do not make the frontend run on Chrome 52.

- Build script: `--variant`, `copy_apk` that finds and copies the signed APK, `inspect_command` that runs `apksigner verify` and prints package and SDK levels after every build, a `curl()` download with a cached `.sha256` file, removal of dead code and of the separate apksigner step.
- Gradle: the `release` build type uses the debug signing config; the debug keystore is persisted in `android/.cache/android`, so updates over earlier builds keep the same key. `minSdk` 24 (the user's edit) is kept.
- Taskfile: `apk:build` appends `{{.CLI_ARGS}}`.
- Kotlin: a pure `WebViewVersion` (`MIN_CHROME_MAJOR = 80`) decides whether the WebView is too old; if so the browser handoff replaces the WebView. A blank-page check reports `The page is blank` with the last console error. `WorkspaceSetting` stores the workspace path in SharedPreferences.
- Rejected: a server MIME-type fix (disproved by the user's Chrome result, reverted).

## Affected Areas

- `android/build_apk.py`
- `android/app/build.gradle.kts`
- `Taskfile.yml`
- `android/app/src/main/java/local/mobilescripts/`: `WebViewVersion.kt` (new), `WorkspaceSetting.kt` (new), `MainActivity.kt`, `MainFrameErrorClient.kt`, `StatusScreen.kt`, `TermuxLauncher.kt`
- `tests/android/test_build_apk.py`
- `README.md`, `android/README.md`, `CHANGELOG.md`

## Out of Scope

- A legacy Chrome-52 bundle of the frontend (needs polyfills and cannot be tested without such a device).
- A foreground service.
- JVM unit tests for the Kotlin code.

## Implementation Notes

All changes are in the working tree on `main`; nothing is committed by the agent (the user commits manually). Each new symbol has a non-test call site:

1. `android/build_apk.py`: `--variant` parser argument (line 156); `copy_apk` defined at line 123, called at line 168; `inspect_command` defined at line 135, called at line 169; `curl` defined at line 88, called at lines 112 and 116 (the Gradle download and its `.sha256`).
2. `android/app/build.gradle.kts`: `buildTypes.release.signingConfig = signingConfigs.getByName("debug")` (line 28); `minSdk = 24` (line 17).
3. `Taskfile.yml`: `apk:build` runs `uv run python android/build_apk.py --context=default {{.CLI_ARGS}}` (line 51).
4. Kotlin:
   - `WebViewVersion.kt`: `MIN_CHROME_MAJOR = 80`, `chromeMajor`, `isTooOld`; used at `MainActivity.kt:135`.
   - `MainActivity.showBrowserHandoff` (called at line 136), `openInBrowser` (lines 199 and 202), `startHeartbeat` (lines 171 and 201), `StatusScreen.browserHandoff` (called at `MainActivity.kt:195`).
   - Blank-page check: `MainFrameErrorClient` `onPageLoaded` (wired at `MainActivity.kt:150`), `WebChromeClient.onConsoleMessage` capture (line 155), `checkListRendered` (line 153), `PAGE_BLANK = "The page is blank"` (line 277).
   - `WorkspaceSetting.kt`: constructed at `MainActivity.kt:44`, `get` passed to `StatusScreen` at line 46, `retryWith` (line 51) saves the path; `TermuxLauncher` takes a `workspaceDir: () -> String` provider (`TermuxLauncher.kt:8`, used at line 34).
5. Tests: `tests/android/test_build_apk.py` updated and extended.
6. Docs: see Documentation Updates.

Deviation from the first idea: the server MIME-type change was reverted after the user's Chrome result disproved it.

## Validation

Offline only. Nothing was run on a device after the fixes.

- `uv run pytest -q` from the repo root (run 2026-11-24 while writing this spec): `213 passed in 48.62s`, 0 failed. The 5 red `tests/android` tests from before are green.
- Three Docker builds equivalent to `task apk:build` were run; the last (`uv run python android/build_apk.py`, release) printed BUILD SUCCESSFUL, `apksigner` "Verifies" (v2 scheme, certificate "Android Debug"), `sdkVersion` 24, `targetSdkVersion` 34. Log: `.agent/tmp/apk-build.log` (scratch, not committed; reported by the coordinator, not re-run for this spec).
- Kotlin has no JVM unit tests. `WebViewVersion` and `WorkspaceSetting.validate` are pure but untested.

UNVERIFIED:
- All device behaviour: browser handoff, workspace field, "The page is blank" check.
- Installing over an older APK signed with another key (Android refuses a different signature; the old app must then be uninstalled).
- That Android does not kill the backgrounded app so that the watchdog stops the backend after 15 s (no foreground service exists).
- Whether a newer WebView can be installed on stock Android 7 through F-Droid. A web search found Chromium's WebView Providers document saying only allow-listed, correctly signed packages can be the provider; nothing was found about F-Droid itself.
- The Chrome version numbers in the Problem section (from memory, not checked against a compatibility table).

## Documentation Review

Checked against this change: `README.md` (sections "Old WebView (Android 7)" at line 204 and "Where the workspace is (moving the clone)" at line 227, plus the install and build sections), `android/README.md` (file table lines 13-22 and the old-WebView paragraph from line 26), `CHANGELOG.md` (`## [Unreleased]`, `### Added`). The three exist and describe the handoff, `--variant`, argument forwarding and the workspace field. Constitution files (`specs/mission.md`, `specs/tech-stack.md`, `specs/roadmap.md`) were not read for this spec and no constitution change is proposed.

CI review: not applicable (no CI config in this repo: `ls -a` shows no `.github`, and `find` for `.github/workflows` files found none).

## Documentation Updates

Done, in the working tree (uncommitted):
- `README.md`: new sections "Old WebView (Android 7)" and "Where the workspace is (moving the clone)"; install and build sections updated.
- `android/README.md`: file table lists `WebViewVersion.kt` and `WorkspaceSetting.kt`; old-WebView behaviour described.
- `CHANGELOG.md`: `## [Unreleased]` / `### Added` lines for `task apk:build -- --variant`, the "The page is blank" diagnostic, the browser handoff and the workspace path setting.

No constitution change.
