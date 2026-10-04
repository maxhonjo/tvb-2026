import json
import subprocess
import threading
from pathlib import Path

BINARY = Path(__file__).parent / "app-activity-mac"


class Listener:
    """Pipes GUI-app events from the Swift helper into a mailbox.

    The mailbox is any object exposing emit(event: dict). Detection lives in the
    helper binary; this class only spawns it and forwards its stdout lines.
    """

    def __init__(self, mailbox):
        self._mailbox = mailbox
        self._proc = None
        self._reader = None

    def start(self):
        if self._proc is not None:  # idempotent
            return
        self._proc = subprocess.Popen(
            [str(BINARY)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self):
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._mailbox.emit(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip a malformed line rather than kill the reader

    def stop(self):
        if self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        if self._reader is not None:
            self._reader.join(timeout=5)
        self._proc = None
        self._reader = None
