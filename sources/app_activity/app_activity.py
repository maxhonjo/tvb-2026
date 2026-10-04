import sys
import threading


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


def _make_listener():
    if sys.platform == "darwin":
        from .src.mac import Listener
        return Listener(_mailbox)
    raise NotImplementedError(f"Unsupported platform: {sys.platform}")


def start_app_activity() -> None:
    global _listener
    if _listener is None:  # idempotent
        _listener = _make_listener()
        _listener.start()


def get_app_activity() -> dict:
    return {"events": _mailbox.drain()}


def stop_app_activity() -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


if __name__ == "__main__":
    print(get_app_activity())
