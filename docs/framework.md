# Boku: framework

Single reference for the project. Read this file and `CLAUDE.md` and you have the
full picture. `docs/ai-guides/` holds the older planning notes; everything still
relevant from them is here, and where they disagree this file wins.

Last updated: 2026-10-06.


# what this is

Boku (working name; "Alibi" was the other candidate) collects a person's own
activity data from their devices. Small independent **sources** each gather one
kind of data; the **core** polls them, wraps each result in a standard record,
prints it, and stores it as a line in a text file. Add-on ideas built on the
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
core.py              poll loop, live config sync, record envelope, error mapping, handle() sink
config.py            read/write/edit ~/.boku/config.json
sources/             one folder per source + errors.py
storage/storage.py   store(record): one JSON line per record, filetree diffing
data/                stored records, one <source>.jsonl per source (gitignored)
ui/ui.py             tkinter UI mockup (Martin), not wired to the core
martin-temp/         Martin's Windows modules, not integrated
docs/framework.md    this file
docs/roadmap.md      Max's checklist (gitignored, local only)
docs/ai-guides/      older planning notes (superseded by this file)
```

Gitignored: both compiled Swift helpers, `data/`, `roadmap.md`, `test.py`. A fresh clone
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
- Every record goes through `core.handle(record)`, which stores it and prints it.
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
  text, which is why storage keeps only diffs for it (see "storage").

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
- It is the single source of truth every shell reads and writes.
- Edit API for shells: `set_enabled(name, enabled)` and
  `set_interval(name, seconds)`. Each loads, changes, saves, and returns the new
  config. Both raise `ValueError` for an unknown source; `set_interval` also
  rejects anything that is not a positive number.

**core.py** `run()` follows the config file while it runs:
1. Every 0.5s it checks the config file's mtime. On a change (and once at
   startup) it reloads and calls `sync()`.
2. `sync()` compares the config with the running sources: newly enabled ones
   are started, disabled ones stopped, and a source whose interval changed is
   stopped and started again.
3. `start_source()`: imports `sources.<name>`, gets `get_<name>`, calls
   `start_<name>()` if the source has one, then starts a thread running
   `poll()`: `poll_once()` -> record -> `handle()`, then waits `interval`. A
   failed import or listener start yields an `unavailable` record and the
   source is not started.
4. `stop_source()`: sets that source's stop Event, joins its thread, then calls
   `stop_<name>()` for a listener.
5. On SIGINT, every running source is stopped the same way.

Details:
- With nothing enabled the core logs "no enabled sources" and idles until a
  source is enabled; it does not exit.
- A config that fails to load (e.g. caught mid-edit) is logged and whatever is
  running keeps running.
- An enabled source that failed to start is retried on every config change, so
  its `unavailable` record repeats.
- Stopping a source waits for its current poll to finish (up to
  `POLL_TIMEOUT`); other config changes are not applied during that wait.
- `poll_once(name, collect, timeout)` runs the source in a worker thread and
  always returns a record. On timeout (`POLL_TIMEOUT = 30`) the worker is
  abandoned as a daemon thread and keeps running in the background.
- One source failing never affects the others.
- `log()` holds a print lock so lines do not interleave.
- `handle(record)` calls `storage.store(record)`, then prints. A failed write is
  logged as `storage error` and polling continues. Printed data is cut to
  `PRINT_LIMIT = 200` characters; storage always gets the full record.


# storage

`storage/storage.py` exposes `store(record)`, re-exported by
`storage/__init__.py`. The core is its only caller.

- Each record is appended as one JSON line (the full envelope) to
  `data/<source>.jsonl`. Files are append-only and never rotated.
- **Data location**: `data/` in the repo, gitignored, for now. For deployment
  this should (possibly) move to `~/.boku/data`, since a compiled app has no
  repo to write into. The path is `DATA_DIR` in `storage/storage.py`.
- **Error records are not stored**, only printed.
- One lock guards all writes. `store()` raises if a write fails; `handle()`
  catches it.

**filetree** is stored as a baseline plus diffs:
- The first record of each core run is stored whole (`data` has `root` and
  `paths`). That is the baseline.
- Later records are stored with `data` as `{"root", "added", "removed"}`,
  compared with the previous snapshot, which is held in memory.
- A poll with no changes stores nothing.
- A core restart writes a fresh baseline. Changing the interval or disabling
  and re-enabling the source does not.
- A rename shows up as one removed and one added path.
- While `data/` is inside the home directory, the walk sees the storage files
  themselves, so their creation appears once as `added` paths.


# not integrated yet

**ui/ui.py** (Martin): a tkinter window with on/off switches. It talks to the
backend through five stub methods on `LoggerUI`: `get_os()`,
`get_compatibility()`, `start_logging(kind)`, `stop_logging(kind)`,
`open_log()`. Its `kind` keys are `"Process"`, `"Key"`, `"Location"`, which do
not match the source names (`app_activity`, `keystrokes`, `location`,
`filetree`). It does not import the core or the config. Once the keys are
mapped, `start_logging` / `stop_logging` can call `config.set_enabled()`.

**martin-temp/** (Martin): `processes.py` (`ProcessLog`, foreground window
tracking) and `keystrokes.py` (`KeyLog`). Windows only, and they use `psutil`,
`pywin32`, and `pynput`, which conflicts with the stdlib-only principle. They do
not follow the source contract above.


# status

- 2026-10-06, Mac: storage was verified against a running core with a throwaway
  script (baseline, added/removed diffs, no write on unchanged polls, restart
  baseline, errors not stored, failed write survives) and by a manual run.
- 2026-10-06, Mac: live config changes (enable, disable, interval, malformed
  file, listener start/stop, SIGINT) were verified against a running core with
  a throwaway script. Not covered: disabling a source mid-poll, and a first run
  with no config file.
- 2026-10-06, Mac: envelope, every error code, skip-on-empty, and listener
  shutdown were exercised by hand and worked. Location failure was simulated
  with a stub helper, not by revoking the real permission.
- 2026-10-03, Windows: the core loop, config path, error isolation, and shutdown
  were verified. Not re-run since the envelope change.
- There are no automated tests in the repo.


# next up

From `docs/roadmap.md`, in order.

**1. Storage follow-ups** (simple storage is in; these are what it leaves open)
- Move `DATA_DIR` out of the repo before packaging (see "storage").
- Location is stored on every poll even when the position has not changed.
- Files grow without limit, and every core restart adds a ~2 MB filetree
  baseline.
- There is no way to read the data back yet (rebuilding a filetree means
  replaying diffs from the latest baseline).
- Deriving app usage sessions from `opened` / `closed` events belongs in
  storage or downstream, not in the source.

**2. To figure out**: UI (CLI vs GUI), add-ons, presentation
(Presentation II is 2026-10-07, 15:12).

**Later**: keystrokes on Mac, Windows backends per source, bringing Martin's
modules into the source contract, packaging and code signing (`.app` / `.exe`),
run at login.
