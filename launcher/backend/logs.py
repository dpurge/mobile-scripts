"""Logging setup: stderr by default, a size-rotated file with `--log-file` (stdlib only)."""

import logging
import logging.handlers
import sys
import threading
from pathlib import Path

LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3  # the file plus 3 backups: about 4 MB at most
LOGGER_NAMES = ("launcher", "app")  # "app" carries the output of the running script
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_installed: list[tuple[logging.Logger, logging.Handler]] = []
_original_hooks: tuple | None = None


def configure(
    log_file: Path | None = None,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> logging.Handler:
    """Send the launcher's and the apps' log lines to `log_file` (rotating) or to stderr.

    Also routes uncaught exceptions, on any thread, through logging. Replaces an earlier setup.
    """
    global _original_hooks
    reset()
    if log_file is None:
        handler: logging.Handler = logging.StreamHandler(sys.stderr)
    else:
        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
    handler.setFormatter(logging.Formatter(FORMAT))
    for name in LOGGER_NAMES:
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _installed.append((logger, handler))
    _original_hooks = (sys.excepthook, threading.excepthook)
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_uncaught_in_thread
    return handler


def reset() -> None:
    """Undo `configure` (used by tests and before a new `configure`)."""
    global _original_hooks
    for logger, handler in _installed:
        logger.removeHandler(handler)
        handler.close()
    _installed.clear()
    if _original_hooks is not None:
        sys.excepthook, threading.excepthook = _original_hooks
        _original_hooks = None


def _log_uncaught(exc_type, exc, traceback) -> None:
    logging.getLogger("launcher").critical("Uncaught exception", exc_info=(exc_type, exc, traceback))


def _log_uncaught_in_thread(args) -> None:
    _log_uncaught(args.exc_type, args.exc_value, args.exc_traceback)
