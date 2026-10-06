"""Boku desktop UI: a pywebview window over the in-process core.

Run from anywhere:  uv run python ui/ui2.py
The page (ui2.html) calls the Api methods below; all logic stays in core/config.
"""

import math
import os
import subprocess
import sys
import threading
from pathlib import Path

# core.py, config.py and the sources package live in the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import webview

import config
import core
from storage.storage import DATA_DIR

PAGE = Path(__file__).with_name("ui2.html")


class Api:
    """Methods the page can call as window.pywebview.api.<name>(). Each call
    runs on its own thread and returns the full state for the page to render."""

    def __init__(self):
        self._window = None
        self._lock = threading.Lock()  # held while the core starts or stops
        self._config_lock = threading.Lock()  # config.py is not safe to call concurrently
        self._stopping = False
        self._closing = False
        self._config = config.DEFAULTS  # last config that loaded cleanly

    def get_state(self):
        config_error = None
        try:
            with self._config_lock:  # load() writes the file on first run
                self._config = config.load()
        except Exception as e:  # e.g. caught mid-edit; show the last good one
            config_error = f"{type(e).__name__}: {e}"

        if self._stopping:
            core_state = "stopping"
        elif core.is_running():
            core_state = "running"
        else:
            core_state = "stopped"

        status = core.status()["sources"]
        sources = []
        for name, settings in self._config["sources"].items():
            entry = status.get(name, {})
            sources.append({
                "name": name,
                "enabled": bool(settings.get("enabled")),
                "interval": settings["interval"],
                "running": bool(entry.get("running")),
                "last_ok": entry.get("last_ok"),
                "last_error": entry.get("last_error"),
            })
        return {
            "core": core_state,
            "closing": self._closing,
            "config_error": config_error,
            "sources": sources,
        }

    def start(self):
        # Skipped while a stop (or another start) is in flight.
        if self._lock.acquire(blocking=False):
            try:
                core.start()
            finally:
                self._lock.release()
        return self.get_state()

    def stop(self):
        """Blocks until the core has stopped (up to core.POLL_TIMEOUT); the page
        keeps polling get_state() meanwhile and shows "stopping"."""
        with self._lock:
            self._stopping = True
            try:
                core.stop()
            finally:
                self._stopping = False
        return self.get_state()

    def set_enabled(self, name, enabled):
        return self._edit(config.set_enabled, name, enabled)

    def set_interval(self, name, seconds):
        # config.set_interval lets nan and inf through.
        if isinstance(seconds, float) and not math.isfinite(seconds):
            return {**self.get_state(), "error": f"interval must be a positive number, got {seconds!r}"}
        return self._edit(config.set_interval, name, seconds)

    def open_data_folder(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.run(["open", str(DATA_DIR)])
        elif sys.platform == "win32":
            os.startfile(DATA_DIR)
        else:
            subprocess.run(["xdg-open", str(DATA_DIR)])

    def _edit(self, change, name, value):
        try:
            with self._config_lock:
                change(name, value)
        except Exception as e:
            return {**self.get_state(), "error": str(e)}
        return self.get_state()

    def _on_closing(self):
        """Window close or Cmd-Q. The core must be stopped before the process
        exits (its threads are not daemons, and listeners hold helper
        processes), so hold the window open until it has."""
        if not core.is_running():
            return True
        if not self._closing:
            self._closing = True
            threading.Thread(target=self._stop_and_close, name="ui-close").start()
        return False

    def _stop_and_close(self):
        try:
            # Poll now, so the page shows "Stopping…" without waiting for its timer.
            self._window.evaluate_js("call('get_state')")
        except Exception:
            pass
        try:
            self.stop()
        finally:
            self._window.destroy()


def main():
    api = Api()
    window = webview.create_window(
        "Boku",
        html=PAGE.read_text(encoding="utf-8"),
        js_api=api,
        width=480,
        height=680,
        min_size=(400, 480),
        background_color="#F6F6F4",
    )
    api._window = window
    window.events.closing += api._on_closing
    webview.start()
    core.stop()  # no-op unless the window went away without the closing event


if __name__ == "__main__":
    main()
