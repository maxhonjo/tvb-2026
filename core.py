import copy
import importlib
import json
import os
import signal
import threading
import time
from datetime import datetime, timezone

import config
import storage
from sources.errors import SourceError

# Cap on a single poll; a poll exceeding this yields a timeout error record and
# the loop continues.
POLL_TIMEOUT = 30

# Status file rewritten by the running core; shells read it (see docs/framework.md).
STATUS_PATH = config.CONFIG_DIR / "status.json"
# The status file is rewritten at least this often (seconds) while the core
# runs, so a reader can tell a live core from one that died.
HEARTBEAT = 5

stopping = threading.Event()
print_lock = threading.Lock()
status_lock = threading.Lock()
state = {"running": False, "updated": None, "sources": {}}
written = None  # (status as last written to disk, monotonic time of that write)
core_thread = None  # set by start()


def log(name, message):
    with print_lock:
        print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{name}:", message)


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_record(name, data=None, error=None):
    """Wrap one poll result in the standard envelope (see docs/framework.md).
    timestamp is the poll time in UTC; source-specific times stay inside data."""
    record = {
        "source": name,
        "ok": error is None,
        "timestamp": utc_now(),
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


def source_status(name):
    """Status entry for one source. Call with status_lock held."""
    return state["sources"].setdefault(
        name, {"running": False, "last_ok": None, "last_error": None}
    )


def track(record):
    """Note a poll result in the status. Any success clears last_error; last_ok
    only moves on a record with data (not an empty listener poll)."""
    with status_lock:
        entry = source_status(record["source"])
        if not record["ok"]:
            entry["last_error"] = {**record["error"], "timestamp": record["timestamp"]}
            return
        entry["last_error"] = None
        if record["data"] != {"events": []}:
            entry["last_ok"] = record["timestamp"]


def publish(running, alive=True):
    """Write the status file if the status changed or the heartbeat is due."""
    global written
    with status_lock:
        state["running"] = alive
        for name in config.DEFAULTS["sources"]:
            source_status(name)["running"] = name in running
        current = (alive, json.dumps(state["sources"]))
        if written and written[0] == current and time.monotonic() - written[1] < HEARTBEAT:
            return
        state["updated"] = utc_now()
        text = json.dumps(state, indent=2)
    try:
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATUS_PATH.with_suffix(".json.tmp")
        tmp.write_text(text)
        os.replace(tmp, STATUS_PATH)
        written = (current, time.monotonic())
    except OSError as e:  # a failed status write must not stop the core
        log("core", f"status error: {type(e).__name__}: {e}")


def status():
    """Copy of the current status, same shape as the status file."""
    with status_lock:
        return copy.deepcopy(state)


def summarize(data):
    """One-line description of a successful poll, for the console."""
    for key in ("events", "paths"):
        if isinstance(data.get(key), list):
            return f"{len(data[key])} {key} collected"
    return "data collected"


def handle(record):
    """Single sink for every record: store it, then print a summary line."""
    track(record)
    try:
        storage.store(record)
    except Exception as e:  # a failed write must not kill the poll thread
        log(record["source"], f"storage error: {type(e).__name__}: {e}")
        return
    if record["ok"]:
        log(record["source"], summarize(record["data"]))
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
        if record["ok"] and record["data"] == {"events": []}:
            track(record)
        else:
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
    global written
    with status_lock:  # each run starts with a clean status
        state["sources"] = {}
    written = None
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
        publish(running)
        if stopping.wait(0.5):
            break

    for entry in running.values():  # signal all first so they wind down together
        entry["stopped"].set()
    for name, entry in running.items():
        stop_source(name, entry)
    publish({}, alive=False)


def is_running():
    """True while a core started with start() is running in this process."""
    return core_thread is not None and core_thread.is_alive()


def start():
    """Run the core on a background thread. No-op if it is already running."""
    global core_thread
    if is_running():
        return
    stopping.clear()
    core_thread = threading.Thread(target=run, name="core")
    core_thread.start()


def stop():
    """Stop a core started with start(). Returns once every source is stopped
    and its listener released (up to POLL_TIMEOUT if a poll is in flight)."""
    stopping.set()
    if core_thread is not None:
        core_thread.join()


if __name__ == "__main__":
    # Signal handlers can only be installed on the main thread, so this stays
    # out of run().
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    run()
