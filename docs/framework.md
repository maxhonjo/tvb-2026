# Boku: framework

Single reference for the project. Read this file and `CLAUDE.md` and you have the
full picture. `docs/ai-guides/` holds the older planning notes; everything still
relevant from them is here, and where they disagree this file wins.

Last updated: 2026-10-06.


# what this is

Boku (working name; "Alibi" was the other candidate) collects a person's own
activity data from their devices. Small independent **sources** each gather one
kind of data; the **core** polls them, wraps each result in a standard record,
and passes it on (printing today, storage next). Add-on ideas built on the
collected data: an `/impersonate-me` skill and a data marketplace.

Built by Max (core, Mac sources) and Martin (Windows modules, UI).


# principles

- **Stdlib only.** `pyproject.toml` has `dependencies = []`, Python >= 3.14,
  managed with `uv`. Native APIs are reached through small compiled Swift
  helpers, not Python packages.
- **Everything ends up compiled into one app.** No reliance on a terminal, a
  shell, or a fixed install path.
- **Logic lives in the core.** CLI, GUI, background service, and packaging are
  thin shells over it.
- **The config file is the interface** between shells and the core.
- **Sources are dumb.** They record raw data; deriving things (sessions, diffs)
  happens downstream.
- Each module does one job.


# repo layout

```
core.py              poll loop, record envelope, error mapping, handle() sink
config.py            read/write ~/.boku/config.json
sources/             one folder per source + errors.py
ui/ui.py             tkinter UI mockup (Martin), not wired to the core
martin-temp/         Martin's Windows modules, not integrated
docs/framework.md    this file
docs/roadmap.md      Max's checklist (gitignored, local only)
docs/ai-guides/      older planning notes (superseded by this file)
```

Gitignored: both compiled Swift helpers, `roadmap.md`, `test.py`. A fresh clone
has to build the helpers before location and app_activity work.

**Run the core** from the repo root (so `sources` imports resolve):
```sh
uv run python core.py
```
There is no `[project.scripts]` entry, so `uv run core` does not work.


# sources/ module structure

```
sources/
├── errors.py                    SourceError (the one module shared by sources)
├── sourcename/
│   ├── __init__.py              re-exports get_sourcename() (+ start_/stop_ for listeners)
│   ├── sourcename.py            get_sourcename(), platform dispatch on sys.platform
│   ├── src/                     platform code, helpers, binaries
```

Core imports a source as `sources.<name>` and looks up `get_<name>`:
```py
from sources.sourcename import get_sourcename
```

**naming**
A Swift helper and its compiled binary share one kebab-case base name,
`<source>-<platform>` (e.g. `app-activity-mac.swift` -> `app-activity-mac`). If a
bundle is required (permission prompts, e.g. location), it uses the same name:
`get-location-mac.app`.


# source types

**snapshot** (filetree, location)
Only `get_sourcename()`. Each poll returns a fresh reading of current state.

**listener** (app_activity; keystrokes when built)
Records events as they happen, so nothing is missed between polls.
```
start_sourcename()   # idempotent: begin listening, buffer events into the mailbox
get_sourcename()     # drain the mailbox -> {"events": [...]}
stop_sourcename()    # stop listening, release OS resources (helper processes)
```
- The mailbox (list + lock, `emit()` / `drain()`) lives inside `sourcename.py`.
  Each listener source keeps its own copy; there is no shared mailbox module.
- Platform code in `src/` only detects events and calls `mailbox.emit(event)`.
  Fill/drain behaves the same on every platform; only detection differs.
- The core tells the two types apart by whether `start_sourcename` exists.


# output shape

Every `get_sourcename()` returns a **dict**, with the same keys regardless of
platform, so the core, storage, and display layers never need to know which OS
produced a reading. On failure it **raises**; it never returns an error value.

The core wraps every poll in one envelope (`core.make_record`):
```py
# success
{"source": "location", "ok": True,  "timestamp": "2026-10-06T18:02:11Z", "data": {...}}
# failure
{"source": "location", "ok": False, "timestamp": "...", "error": {"code": "...", "message": "..."}}
```
- `timestamp` on the envelope is the poll time, set by the core.
- `data` is whatever the source returned. Source-specific times live inside it.
- Every record goes through `core.handle(record)` (prints now, storage later).
- A listener poll with no events (`{"events": []}`) produces no record.

**timestamps**: always UTC ISO-8601 with `Z`, always under the key `timestamp`
(envelope, readings, and individual events). Only the display layer converts to
local time (`core.log` prefixes printed lines with local time).

**errors**: sources raise `SourceError(code, message)` from `sources/errors.py`.
The core maps exceptions to codes (`core.to_error`):

| code                   | when                                                    |
|------------------------|---------------------------------------------------------|
| `permission_denied`    | source knows the OS denied access (no source uses it yet) |
| `unavailable`          | helper missing/exited, import or listener start failed  |
| `unsupported_platform` | no backend for this OS (also any `NotImplementedError`) |
| `timeout`              | poll exceeded `POLL_TIMEOUT` (set by the core)          |
| `internal`             | any other exception, or a non-dict return               |


# current sources

Mac backends only. Every `windows.py` / `android.py` / `ios.py` under `src/` is
an empty placeholder, and the dispatcher raises `unsupported_platform` off
darwin.

## location (snapshot)

```py
{"latitude": 40.42, "longitude": -3.70, "accuracy": 35, "altitude": 0,
 "timestamp": "2026-10-06T03:21:59Z"}
```
- `src/mac.py` runs the Swift helper inside `get-location-mac.app` (a bundle,
  because CoreLocation needs one to prompt for permission) and parses its JSON.
- The helper waits up to 10s for a fix, then exits 1 with a message on stderr.
  Any helper failure becomes `unavailable` with that stderr text. A denied
  permission is not distinguished from a missing fix.
- Location permission is granted to the launching app (terminal or IDE), so
  behaviour differs depending on where the core is started.
- Build command for the bundle's binary is not recorded anywhere in the repo.

## filetree (snapshot)

```py
{"root": "/Users/maxhonjo", "paths": ["Developer/", "Developer/a/main.py", ...]}
```
- Names only; file contents are never read. Paths are relative to `root`,
  sorted, and directories end in `/`.
- Walks the home directory with `os.walk` (symlinks not followed). Skips
  anything starting with `.` and `SKIP_DIRS = Library, node_modules,
  __pycache__, venv, Pods, DerivedData`. Generic names (`build`, `dist`, `out`,
  `target`, `env`) are deliberately not skipped, to avoid dropping user folders.
- Unreadable directories are left out silently. Reading Desktop, Documents,
  Downloads, or iCloud Drive can trigger macOS permission prompts for the
  launching app.
- On Max's Mac one walk takes under a second and the record is about 2 MB of
  text, which matters for storage (see "next up").

## app_activity (listener)

```py
{"events": [{"event": "opened", "name": "Safari", "id": "com.apple.Safari",
             "pid": 412, "timestamp": "2026-10-04T14:22:01Z"}]}
```
- `event` is `opened`, `closed`, or `activated`. `id` is the bundle id on Mac
  (the same key would hold the exe path on Windows).
- Detection is a long-running Swift helper subscribed to `NSWorkspace`
  launch/terminate/activate notifications, one JSON line per event on stdout.
  No special permission needed. `src/mac.py` (`Listener`) spawns it and forwards
  lines to the mailbox.
- If the helper has exited and the mailbox is empty, `get_app_activity()` raises
  `unavailable`.
- Rebuild after editing the Swift file:
  ```sh
  swiftc sources/app_activity/src/app-activity-mac.swift -o sources/app_activity/src/app-activity-mac
  ```

## keystrokes (not implemented)

`keystrokes.py` and `__init__.py` are empty. Enabling it in the config produces
one `unavailable` record and the other sources keep running. It will be a
listener source. Martin has a Windows version in `martin-temp/`.


# core.py / config.py

**config.py** reads/writes `~/.boku/config.json`:
```json
{"sources": {"location": {"enabled": true, "interval": 5}, ...}}
```
- `interval` is seconds between polls. All sources default to disabled.
- `load()` merges the file over `DEFAULTS`, so a new source added to `DEFAULTS`
  appears without a migration; it writes the defaults on first run.
- `save()` is atomic (temp file + `os.replace`).
- It is the single source of truth every shell reads and writes. Today the only
  way to change it is editing the file or calling `config.load()` / `save()`.

**core.py** `run()`:
1. Loads the config **once at startup**. Changes made while it runs are not
   picked up until restart.
2. For each enabled source: imports `sources.<name>`, gets `get_<name>`. A
   failure here yields an `unavailable` record and that source is skipped.
3. If the source exposes `start_<name>()`, calls it before polling (a failed
   start skips the source).
4. Starts one thread per source running `poll()`: `poll_once()` -> record ->
   `handle()`, then waits `interval`.
5. On SIGINT, sets the stop Event, joins the poll threads, then calls
   `stop_<name>()` for every started listener.

Details:
- `poll_once(name, collect, timeout)` runs the source in a worker thread and
  always returns a record. On timeout (`POLL_TIMEOUT = 30`) the worker is
  abandoned as a daemon thread and keeps running in the background.
- One source failing never affects the others.
- `log()` holds a print lock so lines do not interleave.


# not integrated yet

**ui/ui.py** (Martin): a tkinter window with on/off switches. It talks to the
backend through five stub methods on `LoggerUI`: `get_os()`,
`get_compatibility()`, `start_logging(kind)`, `stop_logging(kind)`,
`open_log()`. Its `kind` keys are `"Process"`, `"Key"`, `"Location"`, which do
not match the source names (`app_activity`, `keystrokes`, `location`,
`filetree`). It does not import the core or the config.

**martin-temp/** (Martin): `processes.py` (`ProcessLog`, foreground window
tracking) and `keystrokes.py` (`KeyLog`). Windows only, and they use `psutil`,
`pywin32`, and `pynput`, which conflicts with the stdlib-only principle. They do
not follow the source contract above.


# status

- 2026-10-06, Mac: envelope, every error code, skip-on-empty, and listener
  shutdown were exercised by hand and worked. Location failure was simulated
  with a stub helper, not by revoking the real permission.
- 2026-10-03, Windows: the core loop, config path, error isolation, and shutdown
  were verified. Not re-run since the envelope change.
- There are no automated tests in the repo.


# next up

From `docs/roadmap.md`, in order.

**1. Core can edit config (enable/disable sources, edit interval)**
- `config.load()` / `save()` already exist; what is missing is a small API
  (enable, disable, set interval) for shells to call.
- Open question: whether a running core should pick up changes live. Today it
  needs a restart, and starting or stopping a listener mid-run is not supported.
- The UI's `start_logging` / `stop_logging` stubs are the natural callers, once
  its keys are mapped to source names.

**2. Storage (simple text file for now)**
- Hook point is `core.handle(record)`; every record already passes through it.
- Earlier plan: append each record as one line to `~/.boku/<source>.jsonl`.
- Decide whether error records are stored or only printed.
- filetree needs different treatment because of its size. Plan: store the first
  snapshot as a baseline, then per poll store only
  `{timestamp, added, removed}` (`new - old`, `old - new` on the path sets),
  skip when both are empty, and write a fresh baseline now and then. A rename
  shows up as one removed and one added path.
- Deriving app usage sessions from `opened` / `closed` events belongs here too,
  not in the source.

**3. To figure out**: UI (CLI vs GUI), add-ons, presentation
(Presentation II is 2026-10-07, 15:12).

**Later**: keystrokes on Mac, Windows backends per source, bringing Martin's
modules into the source contract, packaging and code signing (`.app` / `.exe`),
run at login.
