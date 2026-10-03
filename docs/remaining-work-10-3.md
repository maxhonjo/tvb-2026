# Remaining Work (2026-10-03)

## Done
- `config.py` — read/write `~/.boku/config.json`, defaults + merge, atomic writes.
- `core.py` — config-driven loop, one thread per enabled source, per-poll
  timeout, per-source error isolation, clean SIGINT shutdown.
- Cross-platform core verified on Mac (polling, error channel, empty case).

## Docs cleanup (quick)
- `framework.md` `# main.py` section (lines 67–72) is stale — `core.py` replaced
  the hardcoded `SOURCES` table with the config-driven loop. Rewrite to describe
  `core.py` + `config.py`.

## Core-adjacent (small, additive)
- Standardize source **output + error shape** (note added in `framework.md`) —
  unblocks storage.
- `[project.scripts]` entry in `pyproject.toml` so `uv run core` works as the
  doc assumes.

## Features (deferred list from core-planning-2.md)
- CLI over the config (`enable` / `disable` / `run`).
- Storage (JSONL for location; baseline + diff for filetree).
- GUI with the on/off toggle (writes `enabled`).
- `keystrokes` implementation (Mac first).
- Windows `src/` backends per source + dispatch branches.
- Packaging / code signing → `.app` / `.exe` build, run-at-login.

## Recommended next: storage
The core currently polls and discards the data (prints only). Storage is the
first thing that makes the tool do something, it's pure core (no platform code,
no GUI framework, no signing), and it's the natural consumer of the
output-shape standardization.

Sequence:
1. Standardize the output shape (short decision; dependency for clean storage).
2. Storage layer — append each reading to `~/.boku/<source>.jsonl`, wired into
   `core.poll()` where it currently logs.
3. Then choose CLI (fastest path to usable-by-us) or packaging (fastest path to
   installable-by-testers), depending on the next milestone.
