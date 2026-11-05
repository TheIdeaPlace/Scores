"""What happens to an exception nothing caught.

Without a hook, PyQt6 ends the process on any exception that escapes a slot. A bug in
one dialog shouldn't take the app away from someone following a game, but it mustn't
vanish either: the windowed build has no console. So it's written to a log next to the
settings, and the screen reader says something went wrong.
"""

import os
import sys
import time
import traceback

ANNOUNCE_EVERY_SECONDS = 30
_last_announced = 0.0


def log_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Scores", "errors.log")


def _write(text):
    try:
        if sys.stderr:
            sys.stderr.write(text)
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')}\n{text}\n")
    except Exception:
        pass


def log_handled():
    """Log the exception being handled, for a screen that has already said in its own words that
    something failed. Without this, the windowed build would keep no trace of it."""
    _write(traceback.format_exc())


def report_uncaught(exc_type, exc, tb, announce=None, now=time.monotonic):
    """Log it and say so. Never raises: this runs when something has already gone wrong."""
    global _last_announced
    _write("".join(traceback.format_exception(exc_type, exc, tb)))
    try:
        if announce is None:
            from windows_notifications import announce
        moment = now()
        # A repeating failure shouldn't talk over everything.
        if not _last_announced or moment - _last_announced >= ANNOUNCE_EVERY_SECONDS:
            _last_announced = moment
            announce("Something went wrong. Details are in the error log.")
    except Exception:
        pass


def install():
    sys.excepthook = report_uncaught
