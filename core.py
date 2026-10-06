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


def poll(name, collect, interval, stopped):
    """Fixed-interval poll loop for one source. Errors are recorded, never fatal."""
    while not stopped.is_set():
        record = poll_once(name, collect, POLL_TIMEOUT)
        # A listener with nothing buffered since the last poll produces no record.
        if not (record["ok"] and record["data"] == {"events": []}):
            handle(record)
        stopped.wait(interval)


def start_source(name, settings):
    """Start one source: import it, start its listener if it has one, and begin
    polling. Returns its running entry, or None if it could not be started (an
    error record is emitted)."""
    try:
        module = load_source(name)
        collect = getattr(module, f"get_{name}")
    except Exception as e:  # enabled but no working impl
        handle(make_record(name, error={"code": "unavailable", "message": str(e)}))
        return None

    stop_fn = None
    start = getattr(module, f"start_{name}", None)
    if start is not None:  # listener source: begin buffering before polling
        try:
            start()
            stop_fn = getattr(module, f"stop_{name}", None)
        except Exception as e:
            error = to_error(e)
            if error["code"] == "internal":
                error["code"] = "unavailable"
            error["message"] = f"failed to start listener: {error['message']}"
            handle(make_record(name, error=error))
            return None

    stopped = threading.Event()
    interval = settings["interval"]
    thread = threading.Thread(
        target=poll, args=(name, collect, interval, stopped), name=name
    )
    thread.start()
    return {"thread": thread, "stopped": stopped, "stop_fn": stop_fn, "interval": interval}


def stop_source(name, entry):
    """Stop one source's poll thread, then release its listener (helper processes)."""
    entry["stopped"].set()
    entry["thread"].join()
    if entry["stop_fn"] is not None:
        try:
            entry["stop_fn"]()
        except Exception as e:
            log(name, f"error: failed to stop listener: {e}")


def sync(running, cfg):
    """Bring the running sources in line with cfg: start newly enabled ones, stop
    disabled ones, restart those whose interval changed."""
    for name, settings in cfg["sources"].items():
        enabled = settings.get("enabled")
        entry = running.get(name)
        if entry and (not enabled or entry["interval"] != settings["interval"]):
            stop_source(name, running.pop(name))
            entry = None
        if enabled and entry is None:
            entry = start_source(name, settings)
            if entry is not None:
                running[name] = entry


def config_mtime():
    try:
        return config.CONFIG_PATH.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def run():
    """Run one poll thread per enabled source until interrupted, following the
    config file: whenever it changes, sources are started, stopped, or restarted
    to match. With nothing enabled the core idles until a source is enabled.

    Listener sources (those exposing start_<name>) are started before polling and
    stopped when disabled or on shutdown; the poll loop just drains their buffer
    each interval.
    """
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    running = {}  # name -> entry from start_source
    seen = -1  # config mtime last acted on; -1 forces the initial load
    while True:
        mtime = config_mtime()
        if mtime != seen:
            seen = mtime
            try:
                cfg = config.load()
            except Exception as e:  # e.g. caught mid-edit; keep what is running
                log("core", f"error: config not loaded, keeping previous: {e}")
            else:
                sync(running, cfg)
                if not running:
                    log("core", "no enabled sources")
        if stop.wait(0.5):
            break

    for entry in running.values():  # signal all first so they wind down together
        entry["stopped"].set()
    for name, entry in running.items():
        stop_source(name, entry)


if __name__ == "__main__":
    run()
