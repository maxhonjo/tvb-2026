import sys
import threading

from ..errors import SourceError
from .src.mac import Listener


class _Mailbox:
    """Self-contained event buffer. Platform listeners fill via emit(); the core
    poll drains via get_keystrokes(). Kept inside this source (no shared module)
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


def start_keystrokes() -> None:
    global _listener
    if _listener is not None:  # idempotent
        return
    if sys.platform == "darwin":
        _listener = Listener(_mailbox)
        _listener.start()
        return
    raise SourceError("unsupported_platform", f"Unsupported platform: {sys.platform}")


def get_keystrokes() -> dict:
    events = _mailbox.drain()
    # A dead helper would otherwise look like "no typing" forever. Keys it
    # buffered before dying are still returned; the next poll reports the error.
    # The helper exits 2 when the OS denied key access, anything else otherwise.
    if not events and _listener is not None and not _listener.alive():
        if _listener.denied():
            raise SourceError(
                "permission_denied",
                "keystroke access denied; grant Input Monitoring / Accessibility "
                "to the app running the core",
            )
        raise SourceError("unavailable", "keystroke helper is not running")
    return {"events": events}


def stop_keystrokes() -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


if __name__ == "__main__":
    print(get_keystrokes())
