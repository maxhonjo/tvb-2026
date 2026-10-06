#!/usr/bin/env python3
"""
analyze_keystrokes.py — Turn a raw keystroke/activity log into (1) a typing-error
report and (2) workflow-automation proposals.

Design notes for whoever reads this later:
- Raw keystrokes don't label typos. A typo is visible only as a BACKSPACE BURST:
  the user types a wrong form, deletes, retypes the right one. So we replay the
  stream into a text buffer, snapshot the word *just before* a deletion run
  (the "wrong" attempt) and the word as finally committed (the "right" form),
  and count recurring (wrong -> right) pairs. That is the whole trick.
- Automations come from the process/window focus stream: we sessionize by idle
  gaps, then mine app-transition n-grams and repeated typed snippets that recur
  often enough to be worth a shortcut / text-expander / launch group.
- Privacy: this is self-data, but keystrokes capture secrets. Redaction is ON by
  default and drops anything that looks like a credential, and anything typed
  while the focused window looks sensitive (password/login/bank/keychain...).
  stdlib only — runs anywhere Python 3.8+ does.
"""

import argparse, csv, json, os, re, sys, math
from collections import Counter, defaultdict
from datetime import datetime

# ---------------------------------------------------------------- key parsing

SPECIAL = {
    "space": "SPACE", "spacebar": "SPACE", " ": "SPACE",
    "enter": "ENTER", "return": "ENTER", "\n": "ENTER", "\r": "ENTER",
    "tab": "TAB", "\t": "TAB",
    "backspace": "BACKSPACE", "back_space": "BACKSPACE", "bs": "BACKSPACE",
    "\b": "BACKSPACE", "\x7f": "BACKSPACE", "delete_back": "BACKSPACE",
    "delete": "DELETE", "del": "DELETE", "forward_delete": "DELETE",
    "left": "NAV", "right": "NAV", "up": "NAV", "down": "NAV",
    "home": "NAV", "end": "NAV", "page_up": "NAV", "page_down": "NAV",
    "esc": "OTHER", "escape": "OTHER",
}
MODIFIERS = {"shift", "shift_r", "shift_l", "ctrl", "ctrl_l", "ctrl_r",
             "control", "cmd", "cmd_r", "cmd_l", "command", "alt", "alt_l",
             "alt_r", "alt_gr", "option", "caps_lock", "capslock", "fn",
             "super", "win", "meta"}

# Boku's Mac helper logs named keys as "<space>", "<delete>", ... On a Mac
# keyboard "delete" is the backspace key, so it can't share the plain-word
# mapping above.
ANGLE = {"delete": "BACKSPACE", "forward-delete": "DELETE",
         "pageup": "NAV", "pagedown": "NAV"}

def norm_key(raw):
    """Map a logged key value to a normalized token or a single printable char."""
    if raw is None:
        return None
    s = str(raw)
    # pynput style: "Key.space", "Key.backspace", or "'a'"
    if s.startswith("Key."):
        s = s[4:]
    if len(s) >= 3 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1]
    if s in SPECIAL:      # raw whitespace chars, before strip() eats them
        return SPECIAL[s]
    if len(s) >= 3 and s[0] == "<" and s[-1] == ">":
        s = s[1:-1]
        if s.lower() in ANGLE:
            return ANGLE[s.lower()]
    low = s.lower().strip()
    if low in MODIFIERS:
        return "MOD"
    if low in SPECIAL:
        return SPECIAL[low]
    if len(s) == 1:
        return s          # printable char, case preserved
    # multi-char leftovers we don't model (media keys, f-keys, mouse, etc.)
    return "OTHER"

WORD_CHARS = re.compile(r"[A-Za-z0-9''\-]")
def is_word_char(c):
    return bool(c) and len(c) == 1 and WORD_CHARS.match(c)

# ---------------------------------------------------------------- log loading

TS_FIELDS   = ["timestamp", "ts", "time", "t", "epoch", "datetime", "date"]
KEY_FIELDS  = ["key", "char", "k", "keyname", "keycode", "input", "button"]
PROC_FIELDS = ["process", "proc", "app", "application", "exe", "program", "bundle"]
WIN_FIELDS  = ["window", "title", "window_title", "wtitle", "active_window"]

def pick(d, names):
    for n in names:
        if n in d and d[n] not in ("", None):
            return d[n]
    # case-insensitive fallback
    low = {k.lower(): v for k, v in d.items()}
    for n in names:
        if n in low and low[n] not in ("", None):
            return low[n]
    return None

def parse_ts(v):
    if v is None:
        return None
    try:
        f = float(v)
        if f > 1e12:   # milliseconds
            f /= 1000.0
        return f
    except (ValueError, TypeError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(str(v), fmt).timestamp()
        except ValueError:
            continue
    try:                   # ISO-8601 with "Z" and/or fractional seconds
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

def flatten(rows):
    """Expand Boku records ({"source", "ok", "timestamp", "data": {"events": [...]}})
    into their per-key events; rows that are already flat pass through."""
    for r in rows:
        if not isinstance(r, dict):
            continue
        data = r.get("data")
        if isinstance(data, dict) and isinstance(data.get("events"), list):
            if r.get("ok", True):
                yield from data["events"]
        else:
            yield r

def load_events(path):
    """Return a list of dicts: {t, key, proc, win}. Tolerant of jsonl/json/csv."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        head = fh.read(4096); fh.seek(0)
        rows = []
        stripped = head.lstrip()
        if stripped.startswith("["):                         # JSON array
            rows = json.load(fh)
        elif stripped.startswith("{"):                       # JSONL
            for line in fh:
                line = line.strip()
                if line:
                    try: rows.append(json.loads(line))
                    except json.JSONDecodeError: pass
        else:                                                # CSV/TSV
            delim = "\t" if "\t" in head.split("\n")[0] else ","
            rows = list(csv.DictReader(fh, delimiter=delim))

    events = []
    for r in flatten(rows):
        if not isinstance(r, dict):
            continue
        # key-up events, if labelled, are dropped to avoid double counting
        et = pick(r, ["event", "event_type", "type", "action"])
        if et and str(et).lower() in ("up", "keyup", "release", "released"):
            continue
        k = norm_key(pick(r, KEY_FIELDS))
        if k is None:
            continue
        events.append({
            "t":    parse_ts(pick(r, TS_FIELDS)),
            "key":  k,
            "proc": pick(r, PROC_FIELDS),
            "win":  pick(r, WIN_FIELDS),
        })
    return events

# ---------------------------------------------------------------- redaction

SECRETY = re.compile(r"""^(?=.*[A-Za-z])(?=.*\d)(?=.*[^\w\s]).{6,}$""")  # mixed classes
SENSITIVE_WIN = re.compile(r"(password|passwd|login|sign.?in|keychain|bank|"
                           r"wallet|1password|lastpass|bitwarden|secret|token|otp)",
                           re.I)
def looks_secret(tok):
    if not tok: return False
    if len(tok) > 40: return True
    if SECRETY.match(tok): return True
    if re.fullmatch(r"[A-Fa-f0-9]{16,}", tok): return True   # hex token/hash
    return False

# ---------------------------------------------------------------- typing model

def analyze_typing(events, min_count, redact):
    """Replay the stream; collect (wrong, right) correction pairs per word."""
    cur = []                 # chars of the word being typed
    first_peak = None        # buffer snapshot at the first backspace of this word
    in_bs = False            # currently inside a backspace run
    invalid = False          # cursor jumped mid-word -> can't trust reconstruction
    sensitive = False        # focused window looks like a secret field

    corrections = []         # (wrong, right)
    committed_words = []      # all finalized words (for snippet mining, non-sensitive)
    committed_lines = []      # text between ENTERs
    line_buf = []
    deleted_chars = Counter()
    n_keys = n_bs = n_words = n_corrected_words = 0

    def finalize():
        nonlocal cur, first_peak, in_bs, invalid, n_words, n_corrected_words
        right = "".join(cur)
        if right:
            n_words += 1
            if not (redact and (sensitive or looks_secret(right))):
                committed_words.append(right)
                line_buf.append(right)
            if first_peak is not None and not invalid:
                wrong = first_peak
                if wrong and right and wrong != right:
                    n_corrected_words += 1
                    if not (redact and (sensitive or looks_secret(wrong) or looks_secret(right))):
                        corrections.append((wrong, right))
        cur = []; first_peak = None; in_bs = False; invalid = False

    for ev in events:
        k = ev["key"]
        # no window titles in a Boku log, so the app name has to carry this too
        ctx = " ".join(str(x) for x in (ev.get("win"), ev.get("proc")) if x)
        if ctx:
            sensitive = bool(SENSITIVE_WIN.search(ctx))
        n_keys += 1

        if k == "MOD" or k == "OTHER":
            continue
        if is_word_char(k):
            if in_bs:        # a deletion run just ended; retyping begins
                in_bs = False
            cur.append(k)
        elif k == "BACKSPACE":
            n_bs += 1
            if not in_bs:
                first_peak = first_peak if first_peak is not None else "".join(cur)
                in_bs = True
            if cur:
                deleted_chars["".join(cur)[-1]] += 1
                cur.pop()
            else:
                invalid = True   # deleted into previous word; stop trusting this word
        elif k in ("SPACE", "ENTER", "TAB"):
            finalize()
            if k == "ENTER":
                if line_buf and not (redact and sensitive):
                    committed_lines.append(" ".join(line_buf))
                line_buf.clear()
        elif k in ("NAV", "DELETE"):
            invalid = True      # non-linear editing; commit text but skip typo inference
            finalize()
        else:                   # punctuation / symbol = word boundary
            finalize()
    finalize()
    if line_buf:
        committed_lines.append(" ".join(line_buf))

    # group recurring typos by the corrected ("right") form
    by_right = defaultdict(Counter)
    for wrong, right in corrections:
        by_right[right][wrong] += 1

    recurring = []
    for right, wrongs in by_right.items():
        for wrong, c in wrongs.items():
            if c >= min_count:
                recurring.append({
                    "intended": right, "mistyped": wrong, "count": c,
                    "kind": classify(wrong, right),
                })
    recurring.sort(key=lambda x: (-x["count"], x["intended"]))

    return {
        "stats": {
            "events": n_keys, "backspaces": n_bs, "words_committed": n_words,
            "words_with_correction": n_corrected_words,
            "correction_rate": round(n_corrected_words / n_words, 3) if n_words else 0,
        },
        "recurring_typos": recurring,
        "most_deleted_chars": deleted_chars.most_common(8),
        "_committed_words": committed_words,
        "_committed_lines": committed_lines,
    }

QWERTY = {"q":"wa","w":"qes","e":"wrd","r":"etf","t":"ryg","y":"tuh","u":"yij",
          "i":"uok","o":"ipl","p":"ol","a":"qsz","s":"awdz","d":"sefc","f":"drgv",
          "g":"fthb","h":"gyjn","j":"hukm","k":"jil","l":"kop","z":"asx","x":"zsdc",
          "c":"xdfv","v":"cfgb","b":"vghn","n":"bhjm","m":"njk"}

def classify(wrong, right):
    lw, lr = len(wrong), len(right)
    if lw == lr + 1:
        # one extra inserted char? (hellop -> hello)
        for i in range(lw):
            if wrong[:i] + wrong[i+1:] == right:
                return f"extra '{wrong[i]}'"
        if lr and wrong[:-1] == right and wrong[-1] == wrong[-2]:
            return f"doubled '{wrong[-1]}'"
        return "insertion"
    if lw + 1 == lr:
        return "missed a letter"
    if lw == lr and lw >= 2:
        diffs = [i for i in range(lw) if wrong[i] != right[i]]
        if len(diffs) == 2 and diffs[1] == diffs[0] + 1 \
           and wrong[diffs[0]] == right[diffs[1]] and wrong[diffs[1]] == right[diffs[0]]:
            return "transposed letters"
        if len(diffs) == 1:
            i = diffs[0]; w, r = wrong[i].lower(), right[i].lower()
            if w in QWERTY.get(r, ""):
                return f"hit '{wrong[i]}' next to '{right[i]}'"
            return f"'{wrong[i]}' instead of '{right[i]}'"
    return "other"

# ---------------------------------------------------------------- automations

def app_name(ev):
    p = ev.get("proc") or ev.get("win")
    if not p: return None
    name = str(p).split("/")[-1].split("\\")[-1]
    return re.sub(r"\.(exe|app)$", "", name, flags=re.I).strip() or None

def analyze_automations(events, idle_gap, min_count, redact, typing):
    # focus timeline, collapsing consecutive same-app events
    timeline = []
    for ev in events:
        a = app_name(ev)
        if a and (not timeline or timeline[-1][1] != a):
            timeline.append((ev.get("t"), a))

    # sessionize by idle gap
    sessions, cur = [], []
    last_t = None
    for t, a in timeline:
        if last_t is not None and t is not None and (t - last_t) > idle_gap and cur:
            sessions.append(cur); cur = []
        cur.append(a); last_t = t if t is not None else last_t
    if cur: sessions.append(cur)

    # mine recurring app-transition n-grams (2..3) across sessions
    seq_counts = Counter()
    for s in sessions:
        dedup = [s[0]] + [s[i] for i in range(1, len(s)) if s[i] != s[i-1]]
        for n in (2, 3):
            for i in range(len(dedup) - n + 1):
                seq_counts[tuple(dedup[i:i+n])] += 1
    sequences = [{"apps": list(seq), "count": c}
                 for seq, c in seq_counts.most_common() if c >= min_count][:10]

    app_usage = Counter(a for _, a in timeline)

    # repeated typed snippets -> text-expander candidates
    line_counts = Counter(l for l in typing["_committed_lines"] if len(l) >= 12)
    snippets = [{"text": l, "count": c} for l, c in line_counts.most_common()
                if c >= min_count and not (redact and looks_secret(l))][:8]

    # build concrete proposals
    proposals = []
    for s in sequences[:5]:
        apps = s["apps"]
        proposals.append({
            "type": "launch-group",
            "evidence": f"opened in sequence {s['count']}x",
            "suggestion": f"One-click launch group / startup script for: {' -> '.join(apps)}",
            "apps": apps, "count": s["count"],
        })
    for sn in snippets[:5]:
        preview = sn["text"][:60] + ("..." if len(sn["text"]) > 60 else "")
        proposals.append({
            "type": "text-expansion",
            "evidence": f"typed verbatim {sn['count']}x",
            "suggestion": f"Create a text-expander snippet for: \"{preview}\"",
            "count": sn["count"],
        })
    proposals.sort(key=lambda p: -p["count"])

    return {
        "sessions": len(sessions),
        "top_apps": app_usage.most_common(10),
        "recurring_app_sequences": sequences,
        "repeated_snippets": snippets,
        "proposals": proposals,
    }

# ---------------------------------------------------------------- report

def to_markdown(typing, auto):
    s = typing["stats"]
    out = ["# Keystroke analysis\n"]
    out.append("## Typing")
    out.append(f"- {s['events']} events, {s['words_committed']} words, "
               f"{s['backspaces']} backspaces")
    out.append(f"- Correction rate: {s['correction_rate']*100:.1f}% of words were fixed mid-typing\n")

    if typing["recurring_typos"]:
        out.append("### Recurring typos")
        for t in typing["recurring_typos"]:
            out.append(f"- **{t['intended']}** — mistyped as `{t['mistyped']}` "
                       f"{t['count']}x ({t['kind']})")
    else:
        out.append("### Recurring typos\n- None above the threshold.")
    if typing["most_deleted_chars"]:
        chars = ", ".join(f"`{c}` ({n})" for c, n in typing["most_deleted_chars"])
        out.append(f"\nMost-deleted characters: {chars}")

    out.append("\n## Workflow / automation")
    out.append(f"- {auto['sessions']} work sessions detected")
    if auto["top_apps"]:
        out.append("- Top apps: " + ", ".join(f"{a} ({n})" for a, n in auto["top_apps"][:6]))
    if auto["proposals"]:
        out.append("\n### Proposed automations")
        for p in auto["proposals"]:
            out.append(f"- [{p['type']}] {p['suggestion']}  _({p['evidence']})_")
    else:
        out.append("\n### Proposed automations\n- Nothing recurred often enough yet.")
    return "\n".join(out)

# ---------------------------------------------------------------- main

LOG = os.path.join(os.path.expanduser("~"), ".boku", "data", "keystrokes.jsonl")

def main():
    ap = argparse.ArgumentParser(
        description="Analyze Boku's keystroke log (~/.boku/data/keystrokes.jsonl).")
    ap.add_argument("--min-count", type=int, default=2,
                    help="Minimum repetitions to report a pattern (default 2)")
    ap.add_argument("--idle-gap", type=float, default=300.0,
                    help="Seconds of inactivity that split work sessions (default 300)")
    ap.add_argument("--no-redact", action="store_true",
                    help="Disable secret/sensitive-field redaction (NOT recommended)")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    args = ap.parse_args()

    redact = not args.no_redact
    if not os.path.exists(LOG):
        print(f"No keystroke log at {LOG}. Enable Boku's 'keystrokes' "
              "source and let it collect first.", file=sys.stderr)
        sys.exit(1)
    try:
        events = load_events(LOG)
    except Exception as e:
        print(f"Could not read log: {e}", file=sys.stderr); sys.exit(1)
    if not events:
        print("No usable key events found. Check the log format.", file=sys.stderr); sys.exit(2)

    typing = analyze_typing(events, args.min_count, redact)
    auto = analyze_automations(events, args.idle_gap, args.min_count, redact, typing)

    if args.json:
        typing = {k: v for k, v in typing.items() if not k.startswith("_")}
        print(json.dumps({"typing": typing, "automation": auto}, indent=2, ensure_ascii=False))
    else:
        print(to_markdown(typing, auto))

if __name__ == "__main__":
    main()
