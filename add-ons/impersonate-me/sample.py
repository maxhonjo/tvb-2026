"""Pull a few writing samples from Boku's keystroke log, so Claude can draft
in your own voice. Read-only; never writes.

    uv run python add-ons/impersonate-me/sample.py            # a few samples
    uv run python add-ons/impersonate-me/sample.py --count 8  # more samples
    uv run python add-ons/impersonate-me/sample.py --app Mail # one app only

Reads ~/.boku/data/keystrokes.jsonl. The keystroke source stores records
shaped {"source", "ok", "timestamp", "data": {...}} where data carries buffers
of {"process"/"app", "keys": [...]}; keys hold typed chars plus special tokens
like "Key.space", "Key.backspace", "Key.enter" (the martin-temp prototype
shape). Parsing is defensive so it survives small schema changes.
"""

import argparse
import json
import re
from pathlib import Path

DATA_FILE = Path.home() / ".boku" / "data" / "keystrokes.jsonl"

# Apps where people write prose worth imitating. Matched case-insensitively as
# substrings of the process/app name, so "Google Chrome" matches "chrome".
WRITING_APPS = (
    "mail", "outlook", "slack", "messages", "message", "notes", "note",
    "chrome", "safari", "firefox", "arc", "code", "word", "docs",
    "notion", "obsidian", "textedit", "whatsapp", "telegram", "discord",
)

MIN_WORDS = 6      # drop fragments shorter than this (noise, not writing)
MAX_CHARS = 600    # cap a sample so one paragraph doesn't dominate


def _reconstruct(keys):
    """Turn a list of keypress tokens into the text that was typed, applying
    backspaces and mapping the common special keys. Unknown special keys
    (modifiers, arrows, etc.) are dropped.

    Understands two token vocabularies: the Boku Mac source's "<space>",
    "<return>", "<delete>" style and Martin's prototype "Key.space" style."""
    out = []
    for k in keys:
        if not isinstance(k, str):
            continue
        low = k.lower()
        if k == "Key.space" or low in ("space", "<space>"):
            out.append(" ")
        elif k in ("Key.enter", "Key.return") or low in (
            "enter", "return", "<enter>", "<return>"
        ):
            out.append("\n")
        elif k == "Key.tab" or low in ("tab", "<tab>"):
            out.append("\t")
        elif k in ("Key.backspace", "Key.delete") or low in (
            "backspace", "delete", "<delete>", "<forward-delete>"
        ):
            if out:
                out.pop()
        elif k.startswith("Key.") or (k.startswith("<") and k.endswith(">")):
            continue  # shift, cmd, arrows, etc. — no textual content
        elif len(k) == 1:
            out.append(k)
        # anything else (multi-char token) is ignored
    return "".join(out)


def _buffers(record):
    """Yield (app, keys) pairs from one record, tolerant of a few shapes."""
    data = record.get("data")
    if not isinstance(data, dict):
        return
    # data may be a single buffer, or hold a list of buffers under a few names.
    groups = None
    for key in ("buffer", "buffers", "events", "entries"):
        if isinstance(data.get(key), list):
            groups = data[key]
            break
    if groups is None:
        groups = [data]  # the record's data is itself one buffer
    # Boku Mac shape: groups is a flat stream of per-key events, each
    # {"key": ..., "app": ..., "timestamp": ...}. Coalesce consecutive events
    # with the same app into one (app, [tokens]) run.
    if groups and all(
        isinstance(g, dict) and "key" in g and "keys" not in g for g in groups
    ):
        run_app, run_keys = None, []
        for g in groups:
            app = g.get("process") or g.get("app") or g.get("name") or "unknown"
            if run_keys and app != run_app:
                yield str(run_app), run_keys
                run_keys = []
            run_app, run_keys = app, run_keys + [g.get("key")]
        if run_keys:
            yield str(run_app), run_keys
        return

    # Prototype shape: each group carries its own list of keys.
    for g in groups:
        if not isinstance(g, dict):
            continue
        app = g.get("process") or g.get("app") or g.get("name") or "unknown"
        keys = g.get("keys")
        if isinstance(keys, list):
            yield str(app), keys


def _samples(text):
    """Split reconstructed text into candidate sentences/short paragraphs and
    keep the ones long enough to show a voice."""
    out = []
    for block in re.split(r"\n{2,}", text):
        block = re.sub(r"[ \t]+", " ", block.replace("\n", " ")).strip()
        if not block:
            continue
        # Prefer sentence-sized chunks, but keep a long run-on as one sample.
        for chunk in re.split(r"(?<=[.!?])\s+", block):
            chunk = chunk.strip()
            if len(chunk.split()) >= MIN_WORDS:
                out.append(chunk[:MAX_CHARS])
    return out


def collect(count, app_filter):
    if not DATA_FILE.exists():
        return None, []
    by_app = {}
    with open(DATA_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not record.get("ok", True):
                continue
            for app, keys in _buffers(record):
                low = app.lower()
                if app_filter and app_filter.lower() not in low:
                    continue
                if not app_filter and not any(w in low for w in WRITING_APPS):
                    continue
                text = _reconstruct(keys)
                by_app.setdefault(app, []).extend(_samples(text))

    # De-duplicate, then spread picks across apps so one app can't crowd out
    # the rest. Longest samples first within each app (more voice to learn).
    picks = []
    seen = set()
    apps = sorted(by_app, key=lambda a: -len(by_app[a]))
    pools = {a: sorted(set(by_app[a]), key=lambda s: -len(s)) for a in apps}
    while len(picks) < count and any(pools.values()):
        for a in apps:
            if not pools[a]:
                continue
            s = pools[a].pop(0)
            if s not in seen:
                seen.add(s)
                picks.append((a, s))
            if len(picks) >= count:
                break
    return by_app, picks


def main():
    ap = argparse.ArgumentParser(description="Writing samples from the keystroke log.")
    ap.add_argument("--count", type=int, default=5, help="how many samples (default 5)")
    ap.add_argument("--app", default=None, help="restrict to one app (substring match)")
    args = ap.parse_args()

    by_app, picks = collect(args.count, args.app)

    if by_app is None:
        print(f"No keystroke data yet: {DATA_FILE} does not exist.")
        print("Enable the 'keystrokes' source and let it collect before using this.")
        return
    if not picks:
        print("No writing samples found in the keystroke log "
              f"({'app=' + args.app if args.app else 'writing apps only'}).")
        return

    print(f"# {len(picks)} writing sample(s) from your keystroke log\n")
    for i, (app, s) in enumerate(picks, 1):
        print(f"[{i}] ({app})\n{s}\n")


if __name__ == "__main__":
    main()
