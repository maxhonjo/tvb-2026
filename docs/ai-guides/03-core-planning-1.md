# Core application: implementation handoff

## Goal

Build the smallest possible core: call `get_location()` on an interval and print each reading. Everything else is built on top of this later.

## Scope

In:
- One file, `main.py`, that imports `get_location()` and prints what it returns.

Out (for now):
- Storing or writing readings anywhere.
- Keystrokes or any other source.
- Changes to `sources/`.

## Current state

- `sources/location/location.py`: `get_location()` works on macOS and returns a plain `dict` (the JSON from the Swift binary). It stays exactly as it is.
- `sources/keystrokes/`: empty scaffolding. Not touched.
- `pyproject.toml`: Python >= 3.14, no dependencies, managed with `uv`.
- No `main.py` yet.

## Target layout

```
main.py              >> entry point: loop, call get_location(), print
sources/             >> unchanged
```

## Rules for whoever implements this

- Do not run or build anything without explicit permission from Max (see `CLAUDE.md`).
- Stop after each step and check in.

---

## Phase 1: Print location readings

1. **Call once** (`main.py`)
   - `from sources.location import get_location`.
   - Call it once and print the returned dict.
   - Run from the repo root so the `sources` import resolves.
2. **Loop on an interval**
   - `INTERVAL = 60` (seconds) as a constant at the top of the file.
   - `while True:` call `get_location()`, print the reading, `time.sleep(INTERVAL)`.
   - Prefix each printed line with the local time of the reading so consecutive readings can be told apart.
3. **Survive a failed reading**
   - Wrap the call in `try/except Exception`: print the error and carry on to the next interval. A denied permission or a missing binary must not end the loop.
4. **Clean exit**
   - Catch `KeyboardInterrupt` around the loop so Ctrl+C exits without a traceback.

Done when `main.py` prints a location reading every `INTERVAL` seconds until Ctrl+C, and keeps going after a failed reading.

---

## Open decisions for Max

- Interval: 60s is a placeholder.
- Print format: the raw dict (assumed above) or selected fields such as latitude and longitude.

## Known risks

- **Blocking call**: the location binary can take seconds, and a hung binary would stall the loop. A subprocess `timeout` in `sources/location/src/mac.py` would fix it, but that is a change to `sources/` and is out of scope here.
- **Permissions**: Location permission is granted to the launching app (terminal or IDE), so behaviour can differ depending on where `main.py` is started.

## Later (not part of this handoff)

In rough order, each built on the loop above:

1. A list of sources, each with its own interval, in place of the single hard-coded call.
2. A shared reading shape with a timestamp.
3. Writing readings to a file.
4. One thread per source, so a slow source does not delay the others.
5. Streaming sources (keystrokes) with `start` / `stop`.
