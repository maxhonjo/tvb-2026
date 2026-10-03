



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

[src/]
everything else the source needs (platform-specific code, helpers, binaries)

**usage**
Core application imports get_sourcename():
```py
    from sources.sourcename import get_sourcename
```





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
│   │   ├── GetLocationMac.app/
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
