import sys
import threading

from .src.mac import Listener


class _Mailbox:
    """Self-contained event buffer. Platform listeners fill via emit(); the core
    poll drains via get_app_activity(). Kept inside this source (no shared module)
    so each source folder is a complete, independent unit."""

    def __init__(self):
        self._events, self._lock = [], threading.Lock()

    def emit(self, event):
        with self._lock:
            self._events.append(event)

    def drain(self):
        with self._lock:
            events, self._events = self._events, []
        return events


_mailbox = _Mailbox()
_listener = None


def start_app_activity() -> None:
    global _listener
    if _listener is not None:  # idempotent
        return
    if sys.platform == "darwin":
        _listener = Listener(_mailbox)
        _listener.start()
        return
    raise NotImplementedError(f"Unsupported platform: {sys.platform}")


def get_app_activity() -> dict:
    return {"events": _mailbox.drain()}


def stop_app_activity() -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


if __name__ == "__main__":
    print(get_app_activity())
