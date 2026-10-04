



# sources/ module structure (naming/outputs)

sources/
├── sourcename/
│   ├── __init__.py
│   ├── sourcename.py
│   ├── src/
│   │   ├── 
│   │   ├── 

[sourcename.py]
contains the get_sourcename() function to collect data

[__init__.py]
re-exports get_sourcename() so the main application can import it directly
(listener sources also re-export start_sourcename() / stop_sourcename())

[src/]
everything else the source needs (platform-specific code, helpers, binaries)

**usage**
Core application imports get_sourcename():
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

**listener** (app_activity, keystrokes)
Records events as they happen, so nothing is missed between polls.
```
start_sourcename()   # idempotent: begin listening, buffer events into the mailbox
get_sourcename()     # drain the mailbox -> {"events": [...]}
stop_sourcename()    # stop listening, release OS resources (helper processes)
```
- The mailbox (list + lock, `emit()` / `drain()`) lives inside `sourcename.py`.
  Nothing is shared between sources; each source folder is self-contained.
- Platform code in `src/` only detects events and calls `mailbox.emit(event)`.
  Fill/drain behaves the same on every platform; only detection differs.
- The module stays dumb: it records raw events, and deriving things like
  sessions happens downstream.
- The core tells the two types apart by whether `start_sourcename` exists.





# output shape (TODO: standardize)

Every `get_sourcename()` must return the **same dict shape regardless of
platform** — same keys, same conventions — so the core, storage, and display
layers never need to know which OS produced a reading. The platform dispatch
picks the backend; the output contract stays identical across mac / windows /
etc.

Decide the concrete shape later. When we do, also standardize:
- **timestamps**: sources record UTC (ISO-8601, `Z`); only the display layer
  converts to local. (location already does this; the core logger currently
  prints local time — that split lives in the display layer, not the source.)
- **errors**: a shared error shape alongside the data shape.

Until then the core treats readings as opaque and prints them as-is.


# current sources

sources/
├── location/
│   ├── __init__.py
│   ├── location.py              >> get_location()
│   ├── src/
│   │   ├── mac.py
│   │   ├── windows.py           (todo)
│   │   ├── android.py           (todo)
│   │   ├── ios.py               (todo)
│   │   ├── get-location-mac.swift
│   │   ├── get-location-mac.app/
├── app_activity/                (listener)
│   ├── __init__.py
│   ├── app_activity.py          >> start_/get_/stop_app_activity()
│   ├── src/
│   │   ├── mac.py               Listener: spawns helper, stdout -> mailbox
│   │   ├── windows.py           (todo)
│   │   ├── android.py           (todo)
│   │   ├── ios.py               (todo)
│   │   ├── app-activity-mac.swift
│   │   ├── app-activity-mac
├── keystrokes/                  (scaffolding only, not implemented)
│   ├── __init__.py
│   ├── keystrokes.py            >> get_keystrokes()
│   ├── src/
│   │   ├── mac.py               (todo)
│   │   ├── windows.py           (todo)
│   │   ├── android.py           (todo)
│   │   ├── ios.py               (todo)
├── filetree/
│   ├── __init__.py
│   ├── filetree.py              >> get_filetree()
│   ├── src/
│   │   ├── mac.py
│   │   ├── windows.py           (todo)
│   │   ├── android.py           (todo)
│   │   ├── ios.py               (todo)




# core.py / config.py

config.py reads/writes ~/.boku/config.json (per-source {enabled, interval},
defaults + merge on load, atomic writes). It is the single source of truth
every shell (CLI, GUI, app) reads and writes.

core.py runs one thread per *enabled* source, resolving each via
sources.<name> -> get_<name>(). Each poll has a timeout; a failing or
unavailable source logs an error and the other sources keep running. A stop
Event + SIGINT handler give clean shutdown; a print lock keeps log lines from
interleaving.

Listener lifecycle: if a source exposes start_<name>(), core calls it before
polling starts (a failed start skips that source). The normal poll loop then
drains the buffer each interval via get_<name>(). On SIGINT, after the poll
threads join, core calls stop_<name>() for every started listener.
