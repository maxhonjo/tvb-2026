# filetree source: implementation handoff

## Goal

Add a third source, `filetree`, that records the names of the directories and files under the user's home directory. It never reads file contents.

## Scope

In:
- A new source module `sources/filetree/`, laid out the same way as `sources/location/` (see `docs/framework.md`).
- `get_filetree()`, which returns a full snapshot of the paths as a plain `dict`.

Out (for now):
- Changes to `main.py` (wiring `filetree` into the loop comes later).
- Storing snapshots or reconciling them against earlier ones (that belongs to the core, see "Later").
- Changes to `sources/location/` or `sources/keystrokes/` (keystrokes is owned by Max's partner).
- Windows, Android and iOS implementations.

## Current state

- `sources/location/`: the reference implementation. `location.py` picks a platform function based on `sys.platform`; `src/mac.py` does the work and returns a `dict`.
- `main.py`: calls `get_location()` every `INTERVAL` seconds and prints each reading.
- No `sources/filetree/` yet.

## Target layout

```
sources/filetree/
├── __init__.py          >> from .filetree import get_filetree
├── filetree.py          >> get_filetree(): calls get_filetree_mac() on darwin
├── src/
│   ├── mac.py           >> get_filetree_mac(): walks the home directory
│   ├── windows.py       (todo)
│   ├── android.py       (todo)
│   ├── ios.py           (todo)
```

## Output shape

A flat list of paths relative to `root`. Directories end in `/`.

```python
{
    "root": "/Users/maxhonjo",
    "paths": [
        "Developer/",
        "Developer/ProjectA/",
        "Developer/ProjectA/main.py",
    ],
}
```

A flat list makes reconciliation in the core a set difference (`new - old`, `old - new`).

## Rules for whoever implements this

- Do not run or build anything without explicit permission from Max (see `CLAUDE.md`).
- Stop after each step and check in.

---

## Phase 1: filetree source

1. **Scaffold**
   - Create `sources/filetree/` with `__init__.py`, `filetree.py`, and `src/` holding `mac.py`, `windows.py`, `android.py` and `ios.py`.
   - `__init__.py`: `from .filetree import get_filetree`.
   - `filetree.py`: mirror `location.py`, so `darwin` calls `get_filetree_mac()` and any other platform raises `NotImplementedError`. Include the `if __name__ == "__main__":` block.
   - `windows.py`, `android.py`, `ios.py`: empty files.
2. **Walk the home directory** (`src/mac.py`)
   - Set `root = Path.home()`.
   - Walk it with `os.walk(root)`, which does not follow symlinks by default.
   - Before descending, remove skipped entries from `dirnames` in place:
     - anything starting with `.`
     - `SKIP_DIRS = {"Library", "node_modules", "__pycache__", "venv", "Pods", "DerivedData"}` (a constant at the top of the file)
   - Skip files that start with `.`.
   - Add each directory as `relative/path/` and each file as `relative/path/name`, both relative to `root`.
   - Return `{"root": str(root), "paths": sorted(paths)}`.
3. **Survive unreadable directories**
   - `os.walk` skips unreadable directories silently by default (no `onerror`). Keep it that way, so a denied directory is left out and the walk continues.
4. **Docs**
   - Add `filetree/` under "current sources" in `docs/framework.md`.

Done when `uv run python -m sources.filetree.filetree` (run from the repo root) prints a dict whose `paths` list matches the home directory, without hidden or skipped directories.

---

## Open decisions for Max

- ~~`SKIP_DIRS`: the list above is a starting point.~~ Decided: skip only
  unambiguous non-user dirs — `Library`, `node_modules`, `__pycache__`, `venv`,
  `Pods`, `DerivedData`. Generic names (`build`/`dist`/`out`/`target`/`env`)
  deliberately left out to avoid dropping real user folders.
- ~~How often `main.py` should call `get_filetree()`.~~ Decided: hourly
  (`FILETREE_INTERVAL = 3600`). filetree is now wired into `main.py`, running in
  its own thread alongside location (see `docs/framework.md`).

## Known risks

- **Speed**: walking the whole home directory can take seconds or more, so this source should run far less often than location.
- **macOS privacy**: reading Desktop, Documents, Downloads or iCloud Drive can trigger permission prompts for the launching app (terminal or IDE). Denied directories are left out silently.
- **Size**: one snapshot can hold tens of thousands of paths. This is why the core should store changes rather than full snapshots (see "Later").

## Later (not part of this handoff)

Reconciliation, done in the core once storage exists:

1. Store the first snapshot in full as a baseline.
2. On each call, compare the new `paths` with the last known set: `added = new - old`, `removed = old - new`.
3. Store only `{time, added, removed}`. Skip storing when both are empty.
4. Rebuild the tree at any time by replaying the changes on top of the baseline. Save a fresh full baseline now and then (for example weekly) to keep replays short.

A rename or move shows up as one path removed and one path added.
