---
name: impersonate-me
description: Draft or edit an email in the user's own writing voice, learned from their Boku keystroke log. Use when the user runs /impersonate-me or asks to write/reply to an email "as me" / "in my voice" / "in my style".
---

# Impersonate me

Write emails that sound like the user by first learning their voice from real
text they have typed, captured in their own Boku keystroke log.

## Steps

1. **Pull writing samples** by running, from the repo root:

   ```
   uv run python add-ons/impersonate-me/sample.py --count 6
   ```

   This reads `~/.boku/data/keystrokes.jsonl` (read-only) and prints a handful
   of real sentences/paragraphs the user has typed in writing apps.

   - If it reports no data yet, tell the user the `keystrokes` source hasn't
     collected anything and stop — don't invent a style.
   - To bias toward email prose specifically, add `--app Mail` (or Outlook,
     Slack, etc.).

2. **Study the voice**, don't quote it. Read the samples for: sentence length
   and rhythm, greeting/sign-off habits, formality, punctuation quirks (dashes,
   ellipses, lowercase starts), contractions, hedging vs. directness, emoji
   use. Note these to yourself; the sample text is style reference, not content
   to reuse verbatim.

3. **Draft the email** the user asked for in that voice. Match the observed
   habits. Keep the user's actual intent and facts — mimic *how* they write,
   never fabricate commitments or details.

4. **Show the draft** and offer to adjust tone/length.

## Notes

- The samples are the user's own private data. Use them only to shape the
  current draft; don't store, repeat, or send them anywhere.
- If samples look sparse or off-topic, say so and ask the user to point you at
  a better app with `--app`, rather than guessing.
