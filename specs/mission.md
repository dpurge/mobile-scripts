---
version: 3
status: approved
updated: 2026-11-23
---

# Mission

## Problem

Python and Node.js apps that expose a small web UI have no convenient way to be started and used from an Android phone. The user wants an icon on the Android home screen that lists the runnable apps, starts one of them, shows its UI full screen, and returns to the list when the script stops itself. The same apps must also be testable on a desktop (Linux, macOS, Windows) without a phone.

## Users

- The project owner, who runs personal Python and Node.js apps from an Android phone through Termux.
- Script authors (the same person), who write an app either as a Python `http.server` app or as a Node.js (`node:http`) app that serves its own Lit UI and API; Node is needed only for JS apps.
- Developers testing apps on a desktop with the pywebview client.

## Value proposition

One Android app that works as a launcher for Python and Node.js apps: it shows the configured list of apps (name and script path, kept in `apps.json`), lets the user add, remove, edit, reorder and start entries, and turns into a WebView of the started script's UI. Apps run directly from the workspace cloned in Termux, so there is no per-app packaging step.

The desktop pywebview client simulates the Android client's interface and uses the same configuration and the same HTTP API, so an app tested on the desktop behaves the same on Android.

## Non-goals

- Features or security hardening that the user has not asked for.
- Any backend other than a Python backend running inside Termux on Android (and locally on the desktop for testing).
- Packaging individual scripts as separate APKs.
