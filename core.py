import importlib
import signal
import threading
from datetime import datetime

import config

# Placeholder cap on a single poll. Standardized alongside source outputs/errors
# later; for now any poll exceeding this reports a timeout and the loop continues.
POLL_TIMEOUT = 30

stop = threading.Event()
print_lock = threading.Lock()


def log(name, message):
    with print_lock:
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{name}:", message)


def load_source(name):
    """Import a source package. sources.<name> exposes get_<name>(); listener
    sources (keystrokes, app_activity) additionally expose start_<name>() /
    stop_<name>() for the core to drive their lifecycle.

    Enabled-but-unavailable (not implemented, import error) raises here and the
    caller reports it as an error for that source only.
    """
    return importlib.import_module(f"sources.{name}")


def poll_once(collect, timeout):
    """Run collect() with a timeout. Returns (data, error); error is a placeholder
    string/exception until the source error shape is standardized."""
    result = {}

    def worker():
        try:
            result["data"] = collect()
        except Exception as e:  # a failing source must not kill its thread
            result["error"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None, "timeout"  # worker is abandoned (daemon); acceptable for now
    if "error" in result:
        return None, result["error"]
    return result.get("data"), None


def poll(name, collect, interval):
    """Fixed-interval poll loop for one source. Errors are logged, never fatal."""
    while not stop.is_set():
        data, err = poll_once(collect, POLL_TIMEOUT)
        log(name, f"error: {err}" if err is not None else data)
        stop.wait(interval)


def run():
    """Read config, start one thread per enabled source, poll until interrupted.

    Listener sources (those exposing start_<name>) are started before polling and
    stopped on shutdown; the poll loop just drains their buffer each interval.
    """
    cfg = config.load()
    threads = []
    listeners = []  # (name, stop_fn) to shut down after the poll loop ends
    for name, settings in cfg["sources"].items():
        if not settings.get("enabled"):
            continue
        try:
            module = load_source(name)
            collect = getattr(module, f"get_{name}")
        except Exception as e:
            log(name, f"error: unavailable: {e}")  # enabled but no working impl
            continue

        start = getattr(module, f"start_{name}", None)
        if start is not None:  # listener source: begin buffering before polling
            try:
                start()
                listeners.append((name, getattr(module, f"stop_{name}", None)))
            except Exception as e:
                log(name, f"error: failed to start listener: {e}")
                continue

        threads.append(
            threading.Thread(
                target=poll, args=(name, collect, settings["interval"]), name=name
            )
        )

    if not threads:
        log("core", "no enabled sources")
        return

    signal.signal(signal.SIGINT, lambda *_: stop.set())
    for t in threads:
        t.start()
    while not stop.wait(0.5):
        pass
    for t in threads:
        t.join()
    for name, stop_fn in listeners:  # release OS resources (helper processes)
        if stop_fn is not None:
            try:
                stop_fn()
            except Exception as e:
                log(name, f"error: failed to stop listener: {e}")


if __name__ == "__main__":
    run()
