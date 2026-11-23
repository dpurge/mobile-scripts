"""The pywebview window: the only module in the repository that imports `webview`."""

import threading
from collections.abc import Callable

import webview

from launcher.desktop.host import install_stop_signals

WINDOW_TITLE = "Mobile Scripts"
WAKE_SECONDS = 0.5


def run_window(url: str, watch: Callable[[object, threading.Event], None]) -> None:
    """Open a window on `url` and block until it is closed.

    `watch(window, stop)` runs on a worker thread and must return once `stop` is set (the window
    was closed, or a signal asked to quit) or when it has its own reason to end. After it returns
    the window is closed if it is still open, so ending the watcher ends the client.
    """
    stop = threading.Event()
    closed = threading.Event()
    # Resizable and maximized: the window fills the screen like the Android WebView does.
    window = webview.create_window(WINDOW_TITLE, url, resizable=True, maximized=True)
    window.events.closed += closed.set
    window.events.closed += stop.set

    def wake_main_thread() -> None:
        # The main thread sits in the native GUI loop and runs Python signal handlers only when a
        # call reaches it; reading the URL is such a call, so SIGTERM and SIGINT are noticed within
        # WAKE_SECONDS even when `watch` never touches the window (observed on macOS).
        while not stop.wait(WAKE_SECONDS):
            window.get_current_url()

    def worker() -> None:
        threading.Thread(target=wake_main_thread, daemon=True).start()
        try:
            watch(window, stop)
        finally:
            if not closed.is_set():
                window.destroy()

    install_stop_signals(stop)
    webview.start(worker)
