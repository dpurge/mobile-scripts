# Android client

Slice 8 is the full client (native status screen, Termux backend start, health poll, WebView, heartbeat,
shutdown). Run once by the user on an Android 7 phone (WebView Chrome 52): backend start worked, the list
was blank; the fixes since then are only built. Everything that needs a phone is marked UNVERIFIED.

## How the app works

Code in `app/src/main/java/local/mobilescripts/`:

| File | Role |
| --- | --- |
| `MainActivity.kt` | State machine and wiring: status screen, Termux checks, start, health poll, WebView, heartbeat, shutdown on `isFinishing` |
| `TermuxLauncher.kt` | Termux installed? RUN_COMMAND permission? Builds and sends the RUN_COMMAND intent |
| `BackendClient.kt` | `HttpURLConnection` calls on `http://127.0.0.1:<port>`: health, heartbeat, shutdown (background threads only) |
| `HeartbeatLoop.kt` | `POST /api/heartbeat` every 3 s on its own thread; after 3 failures in a row (about 9 s, `MAX_FAILURES_IN_A_ROW`) it stops and reports the last error |
| `ConsecutiveFailures.kt` | Pure counter behind that rule (success resets it) |
| `MainFrameErrorClient.kt` | `WebViewClient` that keeps links in the WebView and reports main-frame load errors and main-frame HTTP status 400 or more (sub-resources ignored) |
| `NextUrl.kt` | Pure function: back to the list when no script runs and the WebView is elsewhere (mirrors the desktop client's `next_url`) |
| `StatusScreen.kt` | Native full-screen status, diagnostic (with the editable workspace path) and browser-handoff views (text 18sp, secondary 15sp, buttons 48dp, selectable text) |
| `WebViewVersion.kt` | Pure: Chrome major version from the WebView user agent; below 80 (`MIN_CHROME_MAJOR`) the WebView is too old |
| `WorkspaceSetting.kt` | The workspace path in Termux: saved in SharedPreferences, default `BuildConfig.WORKSPACE_DIR`; pure `validate` (absolute path) and `normalize` |

- No automated tests cover the Kotlin logic (no JVM test setup here); `NextUrl.kt` and `ConsecutiveFailures.kt`
  are pure so they can be unit tested later. Their behaviour is UNVERIFIED.
- WebView too old (Chrome below 80, e.g. Android 7 with Chrome 52, which showed a blank page): the
  WebView is not created. `MainActivity.showBrowserHandoff` opens the list with `ACTION_VIEW` in the
  default browser and keeps the heartbeat running; the native screen explains why and has an
  "Open in browser" button. A script that stops itself cannot navigate the browser back to the list.
  No foreground service, so Android may kill the backgrounded app (the watchdog then stops the backend
  after 15 s). UNVERIFIED on a device. Why 80: the sources and `vendor/lit.js` use `?.` and `??`.
- A page that loads but whose scripts do not run on a WebView that passed that check is detected 2 s after
  the load: the diagnostic shows the WebView user agent and the last JavaScript error. UNVERIFIED.
- A newer system WebView from F-Droid is not an option on a stock phone: only allow-listed, correctly
  signed packages can be the WebView provider (https://chromium.googlesource.com/chromium/src/+/refs/tags/111.0.5545.3/android_webview/docs/webview-providers.md).
- A backend that stops answering, or a page that fails to load, replaces the WebView with the diagnostic
  screen (Retry first sends a best-effort `POST /api/shutdown` to the previous port).
- The WebView is created only after `GET /api/health` answered, so it is never empty. The health poll
  gives up after 30 seconds (`HEALTH_TIMEOUT_MILLIS` in `MainActivity.kt`) and shows the diagnostic.
- The workspace path (where the repo is cloned in Termux) is a setting: the diagnostic screen has a
  text field for it and Retry saves it (`WorkspaceSetting`), so moving the clone needs no new APK.
  Until it is set, the build-time default `BuildConfig.WORKSPACE_DIR` applies,
  `/data/data/com.termux/files/home/mobile-scripts`; change that default with
  `task apk:build -- --workspace-dir PATH`, which passes the Gradle property `-PworkspaceDir=PATH`
  (read in `app/build.gradle.kts`).
- The manifest's `configChanges` list keeps rotation from recreating the activity: `onDestroy` shuts the
  backend down, so a recreation would stop it.

## Termux RUN_COMMAND facts (read 2026-11-23)

Sources: the wiki page https://raw.githubusercontent.com/wiki/termux/termux-app/RUN_COMMAND-Intent.md
(rendered: https://github.com/termux/termux-app/wiki/RUN_COMMAND-Intent), the Termux sources at
https://github.com/termux/termux-app/tree/master (`app/src/main/AndroidManifest.xml`,
`app/src/main/java/com/termux/app/RunCommandService.java`,
`termux-shared/src/main/java/com/termux/shared/termux/TermuxConstants.java`) and the package recipes at
https://github.com/termux/termux-packages/tree/master/packages. These were read from `master`, not from
the version of Termux installed on a phone.

| Item | Finding |
| --- | --- |
| Service component | `com.termux/com.termux.app.RunCommandService` (`intent.setClassName("com.termux", "com.termux.app.RunCommandService")`) |
| Action | `com.termux.RUN_COMMAND` |
| Extras | `com.termux.RUN_COMMAND_PATH` String (mandatory, absolute path of the executable); `com.termux.RUN_COMMAND_ARGUMENTS` String[]; `com.termux.RUN_COMMAND_WORKDIR` String (default Termux home); `com.termux.RUN_COMMAND_BACKGROUND` boolean (default false) |
| Permission | `com.termux.permission.RUN_COMMAND`; the wiki says the sender must declare it and "it should be granted by user ... through the app's App Info Permissions page ... likely under Additional Permissions" |
| Runtime grant | Termux's manifest declares it with `protectionLevel="dangerous"`, a runtime permission, so `Activity.requestPermissions` is the expected way; the wiki only mentions the Settings page. Whether a system dialog really appears for it is UNVERIFIED (device). `RUN_COMMAND_BACKGROUND` is only an extra and needs no permission of its own |
| `allow-external-apps` | Mandatory: `allow-external-apps=true` in `~/.termux/termux.properties`. `RunCommandService` checks it (`checkIfAllowExternalAppsPolicyIsViolated`) and, when it is not true, shows an error notification and runs nothing; it does NOT throw in the caller. The app can only notice by the health timeout |
| `startService` vs `startForegroundService` | The wiki example calls `startService(intent)` from an Activity. `RunCommandService` itself calls `startForeground` in `onCreate` and `onStartCommand` (API 26+) and then starts Termux's own service with `startForegroundService`. This app uses `startService` from the foreground activity. UNVERIFIED on device |
| Package visibility | targetSdk 30+ needs `<queries><package android:name="com.termux"/></queries>` (or QUERY_ALL_PACKAGES) "otherwise it will not work" (https://github.com/termux/termux-app/wiki/Termux-Libraries#target-sdk-30-package-visibility) |
| Wake lock commands | `termux-wake-lock` and `termux-wake-unlock` are scripts in the `termux-tools` repository (`scripts/termux-wake-lock.in`, `termux-wake-unlock.in`; they run `am startservice ... service_wake_lock` on `TermuxService`). The `termux-tools` package is `TERMUX_PKG_ESSENTIAL=true` (https://raw.githubusercontent.com/termux/termux-packages/master/packages/termux-tools/build.sh), so they come with Termux; the `termux-api` package ("install also the Termux:API app") is NOT needed for them |
| Termux version | Result extras need 0.109 or newer; this app uses none of them, so only the F-Droid build is assumed |

Cleartext HTTP: from API 28 it is blocked by default; the app opts in only for `127.0.0.1` and
`localhost` through `res/xml/network_security_config.xml`
(https://developer.android.com/privacy-and-security/security-config). The page says a numeric loopback
IP counts as a localhost target; that a `<domain>` entry with an IP literal is honoured by
`HttpURLConnection` and the WebView is UNVERIFIED (device).

## Build

`task apk:build` (from the repo root) runs `uv run python android/build_apk.py [--context NAME]
[--workspace-dir PATH] [--variant debug|release]`. The docker context defaults to `rancher-desktop` and is always passed
explicitly. The APK lands in `android/dist/app-release.apk`
(`--variant debug` gives `app-debug.apk`; both are signed with the debug keystore, see
`buildTypes.release.signingConfig` in `app/build.gradle.kts`).

`android/.cache/gradle` and `android/.cache/android` are mounted as the container's `~/.gradle` and
`~/.android`: Gradle downloads are cached, and the generated debug keystore persists, so the signing
key stays the same across builds and updates install over the previous APK.

## Platform and Gradle download

The image is built and run with `--platform linux/amd64`: the current command-line tools and the
AGP `aapt2` are x86_64 only, so on arm64 hosts this runs under emulation. Gradle's download redirects
to github.com, which the container does not trust on a TLS-intercepting network, so `build_apk.py`
downloads the zip on the host into `android/.cache/downloads/` and checks it against the published
SHA-256 before the build.

## Versions and sources (checked 2026-11-23)

| Component | Version | Source |
| --- | --- | --- |
| Android Gradle plugin | 9.5.2 (latest 9.x release) | https://dl.google.com/android/maven2/com/android/tools/build/gradle/maven-metadata.xml |
| Gradle | 9.9.2 (current; sha256 from https://services.gradle.org/distributions/gradle-9.9.2-bin.zip.sha256; AGP 9.5 requires at least 9.6.0) | https://services.gradle.org/versions/current ; AGP 9.5 minimums from https://developer.android.com/build/releases/gradle-plugin |
| JDK | Temurin 21 (AGP 9.5 requires at least 17) | tag `eclipse-temurin:21-jdk` checked with `docker manifest inspect` |
| Kotlin | built into AGP 9; AGP 9.5.2 depends on Kotlin Gradle plugin 2.2.10 | https://dl.google.com/android/maven2/com/android/tools/build/gradle/9.5.2/gradle-9.5.2.pom |
| Command-line tools | 16111833 | highest `commandlinetools-linux-*_latest.zip` in https://dl.google.com/android/repository/repository2-3.xml |
| Build tools | 36.0.0 (AGP 9.5 minimum and default) | same repository2-3.xml and the AGP page |
| Platform | android-34 (compileSdk and targetSdk 34, minSdk 24, Android 7) | project tech stack |
