import json
import threading
from pathlib import Path

# Data is kept inside the repo (gitignored) for now, one <source>.jsonl per source.
# NOTE: for deployment this should (possibly) move to ~/.boku/data, next to the
# config; a compiled app has no repo to write into.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

lock = threading.Lock()
# Paths from the last stored filetree snapshot; None until this run's baseline.
filetree_paths = None


def _append(record):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / f"{record['source']}.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


def _store_filetree(record):
    """Store the first snapshot of a run whole (the baseline), then only what
    changed since the previous one. An unchanged tree stores nothing."""
    global filetree_paths
    data = record["data"]
    paths = set(data["paths"])
    if filetree_paths is None:
        _append(record)
    else:
        added = sorted(paths - filetree_paths)
        removed = sorted(filetree_paths - paths)
        if added or removed:
            diff = {"root": data["root"], "added": added, "removed": removed}
            _append({**record, "data": diff})
    filetree_paths = paths  # only after a successful write, so no change is lost


def store(record):
    """Append one record to its source's file. Error records are not stored.
    Raises if the write fails; the caller decides what to do about it."""
    if not record["ok"]:
        return
    with lock:
        if record["source"] == "filetree":
            _store_filetree(record)
        else:
            _append(record)
