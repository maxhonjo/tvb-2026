"""Boku reader add-on: a window for browsing the data Boku has stored.

Run from anywhere:  uv run python add-ons/reader/reader.py
Reads ~/.boku/data/<source>.jsonl and never writes. The page (reader.html)
calls the Api methods below, which parse the files and hand back one page of
display rows at a time.
"""

import json
import threading
from pathlib import Path

import webview

DATA_DIR = Path.home() / ".boku" / "data"
PAGE = Path(__file__).with_name("reader.html")

PAGE_SIZE = 100    # rows per request
MAX_PATHS = 50     # paths listed per filetree row
MAX_TEXT = 4000    # characters of JSON shown per generic row


def _strings(value):
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _match(paths, query):
    return [p for p in paths if query in p.lower()] if query else paths


def location_rows(records, query):
    """One row per position. Consecutive polls at the same spot (to about 10 m)
    are folded into one row spanning first to last reading."""
    rows = []
    for record in records:
        data = record["data"]
        lat, lon = data.get("latitude"), data.get("longitude")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        spot = [round(lat, 4), round(lon, 4)]
        if rows and rows[-1]["spot"] == spot:
            rows[-1]["until"] = record.get("timestamp")
            rows[-1]["count"] += 1
            continue
        rows.append({
            "spot": spot,
            "time": record.get("timestamp"),
            "until": None,
            "count": 1,
            "accuracy": data.get("accuracy"),
            "altitude": data.get("altitude"),
        })
    if query:
        rows = [r for r in rows if query in f"{r['spot'][0]}, {r['spot'][1]}"]
    return rows


def app_activity_rows(records, query):
    """One row per event."""
    rows = []
    for record in records:
        events = record["data"].get("events")
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            row = {
                "time": event.get("timestamp") or record.get("timestamp"),
                "event": str(event.get("event") or ""),
                "name": str(event.get("name") or ""),
                "id": str(event.get("id") or ""),
            }
            if query in f"{row['name']} {row['id']} {row['event']}".lower():
                rows.append(row)
    return rows


def filetree_rows(records, query):
    """One row per stored record: a snapshot (the baseline) or a change. With a
    query, only matching paths are kept, and snapshots list their matches."""
    rows = []
    for record in records:
        data = record["data"]
        row = {"time": record.get("timestamp"), "root": data.get("root")}
        if "paths" in data:
            paths = _strings(data["paths"])
            matched = _match(paths, query) if query else []
            if query and not matched:
                continue
            row.update(snapshot=True, total=len(paths), matched=len(matched),
                       paths=matched[:MAX_PATHS])
        else:
            added = _match(_strings(data.get("added")), query)
            removed = _match(_strings(data.get("removed")), query)
            if not added and not removed:
                continue
            row.update(snapshot=False,
                       added=added[:MAX_PATHS], added_total=len(added),
                       removed=removed[:MAX_PATHS], removed_total=len(removed))
        rows.append(row)
    return rows


def generic_rows(records, query):
    """Any source without a view of its own: the data as indented JSON."""
    rows = []
    for record in records:
        text = json.dumps(record["data"], indent=2, ensure_ascii=False)
        if query in text.lower():
            rows.append({
                "time": record.get("timestamp"),
                "text": text[:MAX_TEXT],
                "cut": len(text) > MAX_TEXT,
            })
    return rows


# source name -> (view the page draws, row builder). Builders take the records
# oldest first and return rows oldest first.
VIEWS = {
    "location": ("location", location_rows),
    "app_activity": ("app_activity", app_activity_rows),
    "filetree": ("filetree", filetree_rows),
}


class Api:
    """Methods the page can call as window.pywebview.api.<name>(). Each call
    runs on its own thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache = {}  # source name -> ((mtime, size), records)

    def _names(self):
        return sorted(p.stem for p in DATA_DIR.glob("*.jsonl"))

    def _load(self, name):
        """Parsed records of one source, re-read only when its file changed."""
        if name not in self._names():
            raise FileNotFoundError(f"no data for {name}")
        path = DATA_DIR / f"{name}.jsonl"
        with self._lock:
            stat = path.stat()
            key = (stat.st_mtime_ns, stat.st_size)
            cached = self._cache.get(name)
            if cached and cached[0] == key:
                return cached[1]
            records = []
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue  # e.g. a line the core is still writing
                    if isinstance(record, dict) and isinstance(record.get("data"), dict):
                        records.append(record)
            self._cache[name] = (key, records)
            return records

    def sources(self):
        """Every source that has a data file, with its record count."""
        found = []
        for name in self._names():
            try:
                records = self._load(name)
            except OSError:
                continue
            found.append({
                "name": name,
                "records": len(records),
                "last": records[-1].get("timestamp") if records else None,
            })
        return found

    def rows(self, name, query="", offset=0):
        """One page of display rows for a source, newest first."""
        kind, build = VIEWS.get(name, ("generic", generic_rows))
        try:
            rows = build(self._load(name), str(query or "").strip().lower())
        except OSError as e:
            return {"kind": kind, "total": 0, "rows": [], "error": str(e)}
        rows.reverse()
        offset = max(0, int(offset or 0))
        return {"kind": kind, "total": len(rows), "rows": rows[offset:offset + PAGE_SIZE]}


def main():
    webview.create_window(
        "Boku Reader",
        html=PAGE.read_text(encoding="utf-8"),
        js_api=Api(),
        width=720,
        height=760,
        min_size=(480, 480),
        background_color="#F6F6F4",
        text_select=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
