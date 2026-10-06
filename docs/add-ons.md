# Boku: add-ons

An add-on is a standalone app that uses the data Boku has collected. The core
collects and stores; everything that reads the data back is an add-on. See
`docs/framework.md` for the core, the record envelope, and storage.

Last updated: 2026-10-06.


# layout

```
add-ons/
├── <name>/
│   ├── <name>.py        entry point, runnable on its own
│   └── ...              everything else the add-on needs (pages, assets, helpers)
```

- One directory per add-on. The directory and the entry point share one
  kebab-case name (`reader/reader.py`).
- Run from anywhere:
  ```sh
  uv run python add-ons/<name>/<name>.py
  ```
- The entry point starts with a docstring saying what the add-on does and how to
  run it.


# rules

- **Self-contained.** No imports from `core`, `config`, `storage`, `sources`,
  `ui`, or another add-on. Deleting any other add-on, or moving this one out of
  the repo, must not break it. Files the add-on ships are found relative to
  `__file__`, never the working directory.
- **The files are the interface.** An add-on reads `~/.boku/data/<source>.jsonl`
  (one record envelope per line) and, if it needs to know what the core is
  doing, `~/.boku/status.json`. It builds the path itself:
  `Path.home() / ".boku" / "data"`.
- **Read-only.** Never write, rename, or delete anything under `~/.boku`. An
  add-on that produces output writes it somewhere else and says where.
- **Never start, stop, or configure the core.** That is a shell's job.
- **Dependencies.** Stdlib, plus `pywebview` for an add-on with a window (it is
  already in `pyproject.toml`). Anything else needs a reason.


# reading the data

The core may be running and appending while an add-on reads. An add-on must
cope with:

- `~/.boku/data` or a source's file not existing yet.
- A last line that is only partly written: skip any line that does not parse.
- Files that grow between reads. Re-read when the size or mtime changes.
- Sources it has never heard of. Either ignore them or show them generically;
  never crash on one.
- Records whose `data` is missing a key it expects.

Things to know about the stored data (details in `docs/framework.md`):

- Only successful records are stored, so every line has `ok: true` and a `data`
  dict.
- All timestamps are UTC ISO-8601 with `Z`. Convert to local time only when
  displaying.
- **filetree** is a baseline (`data.paths`) followed by diffs (`data.added`,
  `data.removed`). Each new core process writes a new baseline. The current
  tree is the latest baseline with every later diff applied.
- **app_activity** records hold a list of events, each with its own
  `timestamp`; the envelope's `timestamp` is only when they were collected.
- Files are never rotated, so they can be large (each filetree baseline is
  about 2 MB). Do not hand a whole file to a UI.


# look

An add-on with a window should look like part of Boku: copy the colour
variables, type, cards, and dark-mode block from `ui/ui2.html` into its own
page. Copy, do not import, so the add-on stays self-contained.


# current add-ons

| add-on   | what it does                                              |
|----------|-----------------------------------------------------------|
| `reader` | Window for browsing the stored data, one tab per source.  |

Ideas not started: an `/impersonate-me` skill and a data marketplace.


# reader

```sh
uv run python add-ons/reader/reader.py
```

```
add-ons/reader/
├── reader.py      pywebview window + Api: parses the files, builds display rows
└── reader.html    the page: tabs, filter, tables; styled from ui/ui2.html
```

**What it shows**: one tab per `.jsonl` file found in `~/.boku/data`, newest
rows first, times in local time.

| tab          | one row is                  | notes                                             |
|--------------|-----------------------------|---------------------------------------------------|
| Location     | a position                  | consecutive polls at the same spot are folded into one row ("N readings here", first to last time). Same spot = latitude and longitude equal to 4 decimals (about 10 m). |
| App activity | an event                    | opened / closed / switched to, with app name and bundle id. Uses the event's own timestamp. |
| Files        | a stored filetree record    | a baseline shows as "Snapshot · N paths" with no list; a diff lists added (`+`) and removed (`−`) paths. |
| anything else| a record                    | `data` as indented JSON, cut at `MAX_TEXT` characters. |

- **Filter** (per tab) matches coordinates, app name / id / event, or path. It
  does not match dates. In Files, filtering also searches inside snapshots and
  lists their matching paths.
- **Limits** (constants at the top of `reader.py`): `PAGE_SIZE = 100` rows per
  request ("Load more" fetches the next page), `MAX_PATHS = 50` paths listed
  per Files row, then "and N more".
- **Refresh** is manual. Nothing updates on its own while the core records.
- The Files tab shows the stored records as they are. It does not rebuild the
  current tree from baseline + diffs.

**How it works**
- The page calls two methods on `window.pywebview.api`:
  - `sources()` -> `[{"name", "records", "last"}]`, one per data file.
  - `rows(name, query, offset)` -> `{"kind", "total", "rows"}` (plus `"error"`
    if the file could not be read). `kind` picks the view the page draws.
- Python does the parsing, filtering and paging, so a large file is never sent
  to the page whole. Parsed records are cached per source and re-read only
  when the file's mtime or size changes.
- Lines that do not parse, and records without a `data` dict, are skipped.
- `text_select=True` is passed to the window so rows can be selected and
  copied; the page turns selection off everywhere except the list.

**Adding a view for a new source**
1. `reader.py`: write `<source>_rows(records, query)` (records oldest first in,
   rows oldest first out; `query` is already lowercased) and add it to `VIEWS`.
2. `reader.html`: add a `draw<Source>(rows)` function and an entry in the
   page's `VIEWS` (singular, plural, filter placeholder, draw function). Add a
   tab title to `LABELS`.

Without these, a new source still appears, using the generic JSON view.

**Status**
- 2026-10-06: written, **not run or tested yet**. Checklist for the first run:
  1. The window opens with a tab per data file.
  2. Location: local times, repeated positions folded.
  3. Files: snapshots and diffs as described; the filter lists matching paths
     inside snapshots.
  4. App activity: one row per event; filter by app name.
  5. With the main UI collecting, Refresh shows new records.
  6. Dark mode follows the system setting.
- Known gaps: no auto-refresh, no date filter, no map for locations, no rebuilt
  file tree, no app usage sessions derived from opened / closed events.
- `docs/framework.md` still says "stdlib only" with `dependencies = []`;
  `pyproject.toml` now has `pywebview`, which `ui/ui2.py` and this add-on use.
