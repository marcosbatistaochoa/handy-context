# Edit by voice, Aqua-grade cleanup, learning from your fixes

Tier: 2 · Repo: handy-context · Written: 2026-10-07 · Bene Gesserit: skipped, no Bene Gesserit yet
Run: through · Risky: no
Lessons applied: 2026-09-23 [facts] (model speed and Handy's model list read live today), 2026-09-28 [hooks] (every new path fails open to plain dictation), 2026-09-30 [recommend] (Aqua's Edit Mode behaviour copied from its own blog, not invented)

## Summary

- **You get:** (1) say a change instead of retyping. With text selected, it
  rewrites the selection; with nothing selected, it rewrites what you last
  dictated ("add a please at the end" gives "...please."). (2) Cleanup
  that puts in quotation marks, commas and full stops like Aqua and drops
  um, uh, filler "like" and stacked "and"s, measured on a fixed test set
  you can read. (3) When you fix a word by hand after dictating, the
  helper notices; the second time the same fix happens it adds it to your
  dictionary, so it learns how you say things.
- **Cost:** a few hours of build, moderate usage. You dictate a handful of
  times at the end to say whether it is good enough.
- **Risks:** the small local model may mistake a dictated sentence for an
  edit command; the test set measures it, and plain dictation is the
  fallback whenever it is unsure. Watching your fixes only works in apps
  whose text Windows exposes (Notepad, browsers, VS Code yes; some apps no).
- **Your decisions:** none.

## Goal (frozen once approved)

- **Objective:** with the helper in front of Handy, (a) the cleanup test
  set passes at 90% or better with a median model time under 1.5 s on mains
  power, (b) a spoken edit changes the selection or the last dictation
  instead of typing the command, and (c) a hand correction made twice ends
  up in `dictionary.txt`.
- **Always:** fail open (any error or doubt gives plain dictation inside
  the time budget); local model by default; model ids only in `config.py`
  and `.env`; no screen text in logs unless `HC_LOG_CONTEXT=1`;
  `dictionary.txt` stays the one word list.
- **Never:** fork Handy; send screen text off the laptop; delete or rewrite
  text the helper did not itself paste (the last-dictation edit selects
  only text it verified it pasted, right before the cursor).
- **Stop conditions:** the edit-versus-dictation call is wrong on more than
  1 in 10 test cases with no prompt that fixes it (come back with options);
  Handy stops pasting over a selection.

## Acceptance criteria

- **A1.** `TRIALS.md` holds trial 1's line: the cleanup test set run against
  the real local model with the current prompt, pass count and median ms.
- **A2.** `python scripts/eval_cleanup.py` prints `cleanup: N/M passed` with
  N/M >= 0.90 and `median model ms` < 1500, on `tests/eval/cleanup.jsonl`
  (at least 30 cases: quotes, question marks, filler um/uh/like/"you know",
  doubled "and", self-corrections, lists, plain sentences left alone).
- **A3.** The same script prints `edit: N/M passed` with N/M >= 0.90 on
  `tests/eval/edit.jsonl` (at least 15 edit cases, including "add a please at
  the end"), and `false edits: 0/K` on `tests/eval/not_edit.jsonl` (at least
  15 plain dictations with a last dictation present, including ones that
  sound like commands, "add a note at the end of the report"). A2's cleanup
  set is also run through the final routed path with `last` set.
- **A4.** `python -m pytest -q` passes, with new tests for edit routing,
  last-dictation selection safety (refuses when the text before the cursor
  is not what was pasted) and correction learning (diff to `heard => written`,
  added on the second sighting only).
- **A5.** Live in Notepad, `scripts/smoke.py --edit-last` pastes a dictated
  sentence, then sends "add a please at the end" with nothing selected, and
  Notepad's text reads back as the sentence ending in "please." with the
  command words absent.
- **A6.** Live in Notepad, `scripts/smoke.py --learn` pastes a sentence, edits
  one word in Notepad, repeats once, and `dictionary.txt` then holds that
  `heard => written` line; `corrections.jsonl` logs both sightings.
- **A7.** The model stays loaded: the first request after helper start
  answers under 1.5 s (Ollama `keep_alive` plus a warm-up at start).
- **A9.** Through Handy itself (not smoke.py), in Notepad: one dictation,
  then "add a please at the end" with nothing selected; Notepad reads back
  the edited sentence, and the matching `requests.jsonl` line shows
  `mode: edit_last` and `select_check: ok`; Handy's `paste_method` and
  `append_trailing_space` are recorded in Progress.
- **A8.** The user dictates and edits for real in Notepad, a browser and VS
  Code with Nemotron Streaming 3.5 as Handy's speech model, and says it is
  good enough (folds into the first plan's A7).

## Decided without you

- Edit Mode copies Aqua: selected text plus speech means edit, no command
  words. Source: aquavoice.com/blog/introducing-edit-mode (research file
  `ai-system/docs/research/2026-10-04-aqua-voice.md`). Cost if wrong: a prompt change.
- With nothing selected, one model call returns JSON `{"mode": "edit" |
  "dictate", "text": ...}`, and "edit" is honoured only when the last
  dictation was in the same window and is the text right before the cursor.
  Otherwise it is dictation. My choice (a separate key would be safer but
  you asked to just say it). Cost if wrong: a third Right Alt gesture.
- The last dictation is selected with Shift+Left key presses for its exact
  length, then Handy pastes over the selection (Handy pastes with Ctrl+V,
  `clipboard.rs`, which replaces a selection). My choice. Cost if wrong:
  apps that treat Shift+Left oddly; the read-back check refuses then.
- Learning: the helper remembers what it pasted and where; at the next
  dictation (and 30 s after a paste) it re-reads that text, diffs it word by
  word, and logs changed words to `corrections.jsonl`. The same change seen
  twice is added to `dictionary.txt` as `heard => written` and noted in the
  log; you can delete the line any time. Routine call made by a written
  test, per your rule that the agent files without asking. Recent
  corrections are also shown to the model as examples, which covers
  meaning and style, not only spelling. My choice.
- Rule `prompt.py:22` ("never add quotes") is replaced: quotation marks go
  in when the speaker is quoting someone. Source: your request.
- Speech model: Nemotron Streaming 3.5 (you are installing it; in Handy's
  catalog as `nemotron-3.5-asr-streaming-0.6b`, 28 languages, streaming).
  Replaces Parakeet V3 in the first plan. The cleanup step works the same
  on either. Whether Nemotron punctuates by itself: unverified, irrelevant
  because the cleanup does it.
- Pass checks in the eval are exact-match after normalising whitespace,
  with a list of accepted answers per case where wording can vary. My choice.

## Units

### T1. Trial 1: cleanup test set against today's prompt

- **Does:** `tests/eval/cleanup.jsonl` (30+ cases, input and accepted
  outputs), `scripts/eval_cleanup.py` (runs each through `build_messages`
  and the real model, prints pass count, failures and median ms), one line
  in `TRIALS.md`.
- **Files:** `tests/eval/cleanup.jsonl`, `scripts/eval_cleanup.py`, `TRIALS.md`.
- **Depends on:** none.
- **Check:** the script prints its result line; `TRIALS.md` has it (A1).
- **Model:** inline. **Risk:** routine. **Owner:** inline.

### T2. Trial 2: prompt for quotes and fillers

- **Does:** rewrite `RULES` for quotation marks, filler "like", "you know",
  "I mean" used as filler, stacked "and"s, and sentence splitting; rerun.
- **Files:** `handy_context/prompt.py`, `tests/test_prompt.py`, `TRIALS.md`.
- **Depends on:** T1.
- **Check:** A2.
- **Model:** inline. **Risk:** routine. **Owner:** inline.

### T3. Trial 3: Edit Mode on a selection

- **Does:** when the captured context has a selection, build an edit
  prompt (selection, spoken instruction, return the rewritten selection
  only); eval cases in `tests/eval/edit.jsonl`.
- **Files:** `handy_context/prompt.py`, `handy_context/server.py`,
  `scripts/eval_cleanup.py`, `tests/eval/edit.jsonl`, `tests/test_server.py`, `TRIALS.md`.
- **Depends on:** T2.
- **Interfaces:** Produces `build_edit_messages(instruction, target, ctx, dictionary)`
  and `build_messages(..., last=None)` returning the JSON-mode prompt.
- **Check:** A3 (selection cases), A4.
- **Model:** inline. **Risk:** routine. **Owner:** inline.

### T4. Trial 4: edit the last dictation

- **Does:** `memory.py` keeps the last paste (text, app, window title,
  time); with no selection the model decides edit or dictate; on edit the
  helper checks the text before the cursor ends with the last paste, sends
  Shift+Left for its length, re-reads the selection, and only then returns
  the edited text; any mismatch returns plain dictation.
- **Files:** `handy_context/memory.py`, `handy_context/server.py`,
  `handy_context/winui.py` (key sends), `tests/test_memory.py`,
  `tests/test_server.py`, `tests/eval/edit.jsonl`, `scripts/smoke.py`, `TRIALS.md`.
- **Depends on:** T3.
- **Check:** A3 (no-selection and must-not-edit cases), A4, A5.
- **Safety (critic 1, 2):** keys are sent only after the model answered
  "edit" and the answer passed validation; every failure after that point
  answers with the original last paste, never the transcript; exact
  `before_caret` text required (unknown caret offset: no edit); presses
  counted with CRLF as one; one trailing space allowed; read-back polled up
  to 150 ms and must equal the paste exactly, else Right arrow collapses the
  selection and the original paste is returned; arrow keys sent with
  KEYEVENTF_EXTENDEDKEY; only within 60 s of the paste, same window.
  Behind `HC_EDIT_LAST` (default off until A9 passes, then on).
- **Model:** inline. **Risk:** high (injects keys that overwrite text). **Owner:** inline.

### T5. Trial 5: learn from hand corrections

- **Does:** `learn.py`: re-read the last paste's text, word diff,
  `corrections.jsonl`, second sighting appends to `dictionary.txt`; recent
  corrections fed to the prompt as examples.
- **Files:** `handy_context/learn.py`, `handy_context/server.py`,
  `handy_context/prompt.py`, `handy_context/config.py`, `.env.example`,
  `tests/test_learn.py`, `scripts/smoke.py`, README, `TRIALS.md`.
- **Depends on:** T4.
- **Safety (critic 4):** re-read only the same element (UIA RuntimeId and
  window), else skip; skip unless half the paste's words still align; learn
  only one-for-one swaps of one to three words, never deletions or
  insertions; the helper's own edits replace its memory and are never
  learned; a common English word swap goes to the preferred-words list, not
  a `=>` replacement; `corrections.jsonl` holds only the heard and written
  words, no surrounding text.
- **Check:** A4 (including deleted-whole-paste, element-gone, focus-moved
  cases that must log nothing), A6.
- **Model:** inline. **Risk:** routine. **Owner:** inline.

### I1. Keep the model loaded

- **Does:** `keep_alive` on each upstream call when the upstream is Ollama,
  plus one warm-up request at helper start.
- **Files:** `handy_context/server.py`, `handy_context/__main__.py`,
  `handy_context/config.py`, `.env.example`.
- **Pulled by:** T1, because the first call after load took 9.9 s against
  a 4 s budget (measured 2026-10-07).
- **Check:** A7.
- **Model:** inline. **Risk:** routine. **Owner:** inline.

## Critic

Pass one, 2026-10-07, five findings, all accepted:

1. A failed edit would paste the spoken command over the selection (Handy
   pastes the raw transcript on error, `actions.rs:338`; the length guard at
   `server.py:120` is sized to the transcript; selection cut at 4,000
   chars) — fixed: edit fallback is the target text unchanged; guard sized
   to the target; a truncated selection is never edited; A4 tests every
   failure path.
2. "Right before the cursor" is not checkable with `near_cursor`; CRLF,
   trailing space and async SendInput — fixed: T4 Safety line.
3. A3 pooled false edits with true ones — fixed: separate `not_edit` set at
   0 false edits; 60 s recency; A2 rerun through the routed path.
4. Learning would learn wrong rules and log screen text — fixed: T5 Safety line.
5. T4 is destructive and nothing checks the real Handy path — fixed: T4
   high risk behind `HC_EDIT_LAST`; new A9 runs through Handy.

## Progress

Now: T1-T5 and I1 done; A1-A7 pass. Open: A9 (needs Handy and a voice;
the user's), then `HC_EDIT_LAST` default to 1; A8 (the user's verdict);
critic pass two.

- 2026-10-07 Base commit 3bd9f2e.
- 2026-10-07 Probe on mains power (GPU P4, 1605 MHz): first call 9935 ms
  (model loading), second 617 ms; output already quoted correctly.
- 2026-10-07 T1 done: 34 cases, baseline 22/34, median 239 ms (`TRIALS.md`).
- 2026-10-07 T2 done: cleanup 32/34, median 281 ms; pytest 29 passed.
- 2026-10-07 Ruling (taste): eval checks are required substrings and
  forbidden words, not exact matches, so harmless wording differences pass.
  Cost if wrong: a loose case lets a bad answer through; tighten that case.
- 2026-10-07 T3/T4 in cfcd7a4: edit 17/17, false edits 0/22.
- 2026-10-07 T5 + I1 in 382e238: memory matches by field id (title only
  without one), learner and model warm-up wired in `__main__`. pytest 63
  passed (A4). Eval: cleanup 32/34, edit 16/17, false edits 0/22, median
  257 ms (A2, A3).
- 2026-10-07 A5 pass 3/3: `smoke.py --edit-last`, Notepad reads "Send the
  report to Kate on Friday, please."
- 2026-10-07 A6 pass 4/4 after the smoke script polls for the paste (one
  earlier miss read the field before the paste landed). `--learn` uses a
  pass-through model: the real one read the first fix off the screen and
  spelled it right the second time, leaving nothing to learn.
- 2026-10-07 A7 pass: cold load 3.6 s paid by the warm-up at start, first
  request 0.51 s. Gap: after 30 min idle (`HC_KEEP_ALIVE`) the next
  dictation pays the load inside the 4 s budget and likely falls back to
  raw text.
- 2026-10-07 Critic pass two: nothing blocks A1-A7. Fixed: (1) the learner
  refuses numbers, days and months and counts sightings only within 30
  days; (2) a failed capture plus a spoken order pastes nothing (a hidden
  selection would otherwise get the order pasted over it); an app that has
  no TextPattern but sets no error is still not covered; (3) A5 now requires
  the field to equal the edit exactly (rerun: pass), A9 says `edit_last`;
  (4) tests for the key-failure and too-long-answer paths. pytest 71 passed.
  Routed cleanup (`--set cleanup --routed`): 32/34.
- 2026-10-07 Deviations from the units, accepted: T5 does not show recent
  corrections to the model and does not re-read 30 s after a paste
  (learning happens at the next dictation); README not yet updated for Edit
  Mode and learning; read-back polls 400 ms (plan said 150); a failed edit
  pastes "" rather than the original. `context.py` and `modes.py` changed
  outside the units' file lists. Open risk: a selection stays on the last
  dictation if Handy's paste is cancelled in that 400 ms window.
- 2026-10-07 Eval max model time hit 4909 ms and 7537 ms once each (helper
  budget 4 s; the eval allows 60 s), so an occasional real dictation falls
  back to raw text. Cause not found.
- 2026-10-07 Aqua Voice was still running during those runs; the user quit
  it. Three full evals after: max 711, 666, 696 ms, median ~320 ms, scores
  unchanged. Likely the cause (not proven). `HC_KEEP_ALIVE` default now
  `-1m` (the user's choice: always loaded); `ollama ps` shows "Forever".
  A bare `-1` is rejected by Ollama's OpenAI endpoint.
- 2026-10-07 Run `runs/speed-and-edit` steps 1-4 done inline (the
  background session never started: workspace not trusted). "Apples.
  please" now "Apples, please."; context capped 1000 + 500; screen read at
  key release (`Helper.prefetch`, `App.on_release`); select-last read-back
  window 0.4 -> 0.8 s after one live mismatch in 4. pytest 76 passed; eval
  and smoke numbers in `TRIALS.md` T6 (433276b, b8aa5a5).
