import importlib
import signal
import threading
from datetime import datetime, timezone

import config
from sources.errors import SourceError

# Cap on a single poll; a poll exceeding this yields a timeout error record and
# the loop continues.
POLL_TIMEOUT = 30

stop = threading.Event()
print_lock = threading.Lock()


def log(name, message):
    with print_lock:
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{name}:", message)


def make_record(name, data=None, error=None):
    """Wrap one poll result in the standard envelope (see docs/framework.md).
    timestamp is the poll time in UTC; source-specific times stay inside data."""
    record = {
        "source": name,
        "ok": error is None,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if error is None:
        record["data"] = data
    else:
        record["error"] = error
    return record


def to_error(exc):
    """Map an exception raised by a source to the standard error shape."""
    if isinstance(exc, SourceError):
        return {"code": exc.code, "message": exc.message}
    if isinstance(exc, NotImplementedError):
        return {"code": "unsupported_platform", "message": str(exc)}
    return {"code": "internal", "message": f"{type(exc).__name__}: {exc}"}


def handle(record):
    """Single sink for every record. Prints for now; storage hooks in here."""
    if record["ok"]:
        log(record["source"], record["data"])
    else:
        error = record["error"]
        log(record["source"], f"error [{error['code']}]: {error['message']}")


def load_source(name):
    """Import a source package. sources.<name> exposes get_<name>(); listener
    sources (keystrokes, app_activity) additionally expose start_<name>() /
    stop_<name>() for the core to drive their lifecycle.

    Enabled-but-unavailable (not implemented, import error) raises here and the
    caller reports it as an error for that source only.
    """
    return importlib.import_module(f"sources.{name}")


def poll_once(name, collect, timeout):
    """Run collect() with a timeout and return the resulting record."""
    result = {}

    def worker():
        try:
            result["data"] = collect()
        except Exception as e:  # a failing source must not kill its thread
            result["error"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():  # worker is abandoned (daemon); acceptable for now
        return make_record(
            name, error={"code": "timeout", "message": f"poll exceeded {timeout}s"}
        )
    if "error" in result:
        return make_record(name, error=to_error(result["error"]))
    data = result.get("data")
    if not isinstance(data, dict):
        return make_record(
            name,
            error={
                "code": "internal",
                "message": f"expected dict, got {type(data).__name__}",
            },
        )
    return make_record(name, data=data)


def poll(name, collect, interval):
    """Fixed-interval poll loop for one source. Errors are recorded, never fatal."""
    while not stop.is_set():
        record = poll_once(name, collect, POLL_TIMEOUT)
        # A listener with nothing buffered since the last poll produces no record.
        if not (record["ok"] and record["data"] == {"events": []}):
            handle(record)
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
        except Exception as e:  # enabled but no working impl
            handle(make_record(name, error={"code": "unavailable", "message": str(e)}))
            continue

        start = getattr(module, f"start_{name}", None)
        if start is not None:  # listener source: begin buffering before polling
            try:
                start()
                listeners.append((name, getattr(module, f"stop_{name}", None)))
            except Exception as e:
                error = to_error(e)
                if error["code"] == "internal":
                    error["code"] = "unavailable"
                error["message"] = f"failed to start listener: {error['message']}"
                handle(make_record(name, error=error))
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
