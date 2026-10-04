# Core (v2)

## Note
Before implementation, discuss how this entire project will be shipped. How will we get it to a form that is easily transferrable to all devices?

## Goal

Build the simplest cross-platform core: a config file of enabled sources, and a
foreground loop that polls them and prints. No storage, no CLI, no GUI, no
background service yet. Those come later as thin shells over this core.

## Principle

The core is a plain Python package. Everything else (CLI, GUI, background
service, packaging) is an additive wrapper over it. Keep logic in the core,
never in a shell. Stay dependency-free (stdlib only) and cross-platform by
default.

**This entire thing will eventually be compiled into one app.** Every design
choice must keep that in mind: no reliance on a terminal, a shell, or a fixed
install path; config and logic must work the same when bundled inside an app.

## Target shape

```
config.py    read/write ~/.boku/config.json   {source: {enabled, interval}}
core.py      run(): read config, one thread per enabled source, poll, print
sources/     existing (location, filetree, keystrokes)
```

## Config is the interface

`enabled` sources and their intervals live in `~/.boku/config.json`. For now,
test by editing that file directly and running the core (e.g. `uv run core`) —
no CLI needed. The config is the single source of truth that every future
shell (CLI, GUI, app) reads and writes.

## Steps

1. `config.py` — read/write `~/.boku/config.json`, with defaults. Atomic writes.
2. `core.py` — `run()` driven by config (replaces the hardcoded `SOURCES` table;
   folds in today's `main.py`).
3. Verify: set a source enabled in config, run the core, confirm it polls and
   prints at the interval.

## Deferred (additive, decide later)

- CLI (`enable` / `disable` / `run`) over the config
- Storage (JSONL for location; baseline + diff for filetree)
- Background / run-at-login (service or app)
- GUI (cross-platform framework TBD)
- Packaging + code signing for sharing with testers
- Windows `src/` implementations for each source

## Rules

- Do not run or build anything without explicit permission (see `CLAUDE.md`).
- Keep each module doing one job.
