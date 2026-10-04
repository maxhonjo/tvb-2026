# app_activity Source — Implementation Guide (2026-10-04)

A listener source that records when GUI applications open, close, and come to
the foreground — a running overview of the apps used on the Mac.

## Design decisions (settled)

- **Name:** `app_activity` (specific; sibling to `keystrokes`, `filetree`).
- **Dumb module:** records raw open/close/activate events only. Deriving usage
  sessions (open→close spans) is left to storage downstream.
- **Listener, not snapshot:** unlike `filetree`/`location` (polled snapshots),
  this source *buffers events* so it catches apps that open **and** close
  between two core polls — the blind spot a snapshot-diff would miss.
- **Self-contained:** no shared helper module. The mailbox lives inside
  `app_activity.py`. `keystrokes` will get its own copy when built.
- **Detection API:** macOS `NSWorkspace` launch/terminate/activate
  notifications — the canonical push API for GUI-app events. Gives name, bundle
  id, pid with no special permission. (EndpointSecurity rejected: wrong
  granularity — every process, not apps — and needs root + entitlement + system
  extension.)
- **Binding:** a long-running **Swift streaming helper** (mirrors the
  `location` source's compiled binary), one JSON line per event on stdout.
  Keeps `dependencies = []` (no PyObjC).

## Contract

Every listener source exposes three functions; snapshot sources expose none of
them and the core leaves them alone.

```
start_app_activity()   # idempotent: spawn helper + reader thread, begin buffering
get_app_activity()      # drain the mailbox, return events since last call
stop_app_activity()     # stop helper, release resources
```

Core lifecycle: `start()` at launch → `get()` drained every interval by the
existing poll loop → `stop()` on SIGINT.

## Mailbox (the consistency mechanism)

Fill/drain logic is identical across platforms; only detection differs.

```
emit(event)   # PRODUCER — the platform listener pushes here
drain()        # CONSUMER — core poll pulls + clears here
```

## Event schema (one JSON line from the helper)

```json
{"event": "opened", "name": "Safari", "id": "com.apple.Safari", "pid": 412, "at": "2026-10-04T14:22:01Z"}
```

`event` ∈ {`opened`, `closed`, `activated`}. `id` = bundle id on mac
(→ exe path on windows: same key, mapped concept).

## File layout

```
sources/app_activity/
  __init__.py            # exposes start_/get_/stop_
  app_activity.py        # mailbox + 3 functions + platform pick
  src/
    app-activity-mac.swift   # detection source
    app-activity-mac         # compiled binary
    mac.py                   # Listener: spawn binary, read stdout -> mailbox
    windows.py               # empty placeholder (android.py, ios.py too)
```

## Build steps (test at each)

1. **Swift streaming helper** — subscribe to NSWorkspace notifications, print one
   JSON line per event. *Test:* run it, open/quit apps, watch stdout.
2. **Compile & place** the binary beside `src/mac.py`. *Test:* run the binary
   from its final path.
3. **Mac listener (`src/mac.py`)** — `start()` spawns binary + reader thread into
   the mailbox; `stop()` kills it. *Test:* REPL — start, interact, check events,
   stop, confirm no orphan process.
4. **Dispatcher (`app_activity.py`)** — mailbox + 3 functions + platform pick.
   *Test:* start → interact → `get()` returns + empties, second `get()` empty.
5. **Platform stubs (`src/windows.py`, `android.py`, `ios.py`)** — empty
   placeholders (same convention as `location`/`filetree`); the dispatcher
   raises `NotImplementedError` for any non-darwin platform.
   *Test:* imports clean on mac; dispatcher raises if forced off darwin.
6. **Core lifecycle hooks** — `start_`/`stop_` detection in `run()`. *Test:*
   enable in config, run core, watch events logged per interval, Ctrl-C exits
   with no orphan.
7. **Config default** — add `app_activity` to `DEFAULTS`. *Test:* `python
   config.py` shows it.

Order rationale: detection proven alone (1–2) → wrapped in Python (3) →
self-contained source (4) → cross-platform parity (5) → wired to core (6–7).
A break stays localized to the current step.
