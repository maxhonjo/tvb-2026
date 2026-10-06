---
name: keystroke-analysis
description: Analyze the user's own Boku keystroke log to surface (1) recurring typing errors — e.g. "you type 'hellop' when you mean 'hello'" — and (2) concrete workflow-automation proposals (text-expander snippets, app launch-groups). Use when the user runs /keystroke-analysis or asks about their typos, typing mistakes, typing accuracy or typing habits, or wants suggestions for automating repetitive app/typing routines. No file is needed — it always reads the Boku log at ~/.boku/data/keystrokes.jsonl.
---

# Keystroke analysis

This skill turns the user's Boku keystroke log into two useful outputs: a
report of the typos they keep making, and a short list of automations worth
setting up. The analysis runs entirely locally via one stdlib-only Python
script — nothing is uploaded.

## How to run it

The log is always `~/.boku/data/keystrokes.jsonl`, written by Boku's
`keystrokes` source — never ask the user for a file. From the repo root:

```bash
python3 add-ons/keystroke-analysis/scripts/analyze_keystrokes.py [--json] [--min-count N] [--idle-gap SECONDS] [--no-redact]
```

- If the script reports no log, tell the user the `keystrokes` source hasn't
  collected anything yet and stop.
- Don't open or print the raw log yourself — it holds everything the user
  typed. Only run the script, which redacts before it reports.
- Default output is a readable markdown report. Pass `--json` when you want the
  structured data to reshape it yourself (e.g. to build a chart or a nicer
  summary for the user).
- `--min-count` is how many repetitions a pattern needs before it's reported
  (default 2). On a small sample use 2; on a large multi-week log, raise it to
  5–10 so only genuine habits surface.
- `--idle-gap` sets how many seconds of inactivity splits one "work session"
  from the next (default 300), which drives the app-sequence detection.

Read the script's output, then present it to the user in your own words. Don't
just paste the raw report — interpret it (see below).

## How the typo detection actually works

Raw keystrokes don't come labelled with "this was a mistake." A typo is only
visible as a **backspace burst**: the user types a wrong form, deletes it, and
retypes. The script replays the whole stream into a text buffer, snapshots the
word *right before* a deletion run (the "mistyped" attempt) against the word as
finally committed (the "intended" form), and counts how often each
(mistyped → intended) pair recurs. Each pair is classified: extra letter,
doubled letter, missed letter, transposition, or an adjacent-key slip (it knows
the QWERTY neighbour map, so it can say "you hit 'p' reaching for 'o'").

Because the signal is the correction itself, the report only catches typos the
user *noticed and fixed*. Mistakes they left in the text are invisible to this
method — worth saying to the user so they don't over-trust the accuracy number.

## How the automation detection works

From the process/window focus stream, the script sessionizes activity by idle
gaps, then mines:
- **Recurring app sequences** — the same ordered app switches across many
  sessions (e.g. open Terminal → Chrome → Slack every morning) → suggest a
  one-click launch group or startup script.
- **Repeated typed snippets** — whole lines typed verbatim again and again (a
  signature, a boilerplate reply, a command) → suggest a text-expander snippet.

## Interpreting and presenting results

Lead with the single most actionable finding (usually the top recurring typo or
the top automation), then give the rest as a short list. Good framing:

- Typos: "You corrected 'hello' to the typo 'hellop' 8 times — your pinky is
  adding a trailing 'p'. A text replacement rule 'hellop → hello' would fix it
  silently."
- Automations: "Terminal → Chrome → Slack opened in that order on 8 of your
  sessions. Want a one-tap launcher for that set?"

When the user wants it, go one step further and actually draft the automation —
e.g. the macOS `espanso`/`aText`/`Text Replacement` entry, a Windows AutoHotkey
line, or a small launch script — using the detected pattern as the input.

## Privacy — this matters, keep it on by default

Keystroke logs contain passwords, messages, card numbers. Redaction is **on by
default**: the script drops any token that looks like a credential (mixed
letters+digits+symbols, long hex tokens, anything over 40 chars) and anything
typed while the focused window or app looks sensitive (password / login / bank /
keychain / password-manager names). Boku logs carry the app name only, no
window title, so a password typed into a browser is caught only by the
credential-shape check. Only pass `--no-redact` if the user
explicitly asks and understands the risk. Never echo a raw secret back to the
user even if one slips through — if you notice one in the output, flag it and
suggest re-running with redaction rather than repeating it.

## Log shape

One record per poll, each holding that poll's key events:
```
{"source": "keystrokes", "ok": true, "timestamp": "...", "data": {"events": [
  {"key": "h", "app": "Code", "timestamp": "2026-10-06T10:15:02Z"},
  {"key": "<delete>", "app": "Code", "timestamp": "2026-10-06T10:15:03Z"}]}}
```
Named keys are `<space>`, `<return>`, `<tab>`, `<delete>` (the Mac backspace
key), `<forward-delete>`, arrows, etc. The helper doesn't log modifier state,
so a shortcut like Cmd+C shows up as a typed `c` — expect a little noise in
the word counts.
