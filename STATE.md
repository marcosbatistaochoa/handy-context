# handy-context: where this is

Last updated 2026-10-09.

Working daily on the HP Spectre since 2026-10-07: Handy (Right Alt) plus
this helper, with Deep Context, the dictionary, learning from hand fixes,
and spoken edits of a selection or the last dictation. The user: "works".

Installed on the Framework 2026-10-08. Its local model was too slow (6
tokens/s, long dictations timed out), so its `.env` sends cleanup to
Groq's free plan, `openai/gpt-oss-120b`, Zero Data Retention on: eval
28/34, median 444 ms; live 1.0 s with screen context. The user chose
cloud ("as long as it's quick and doesn't cost money"). Its
`dictionary.txt` and learn log stay on the Framework (`ai-system`
AGENTS.md, "The wall").

The Spectre went to Groq too on 2026-10-08: its own key (`spectre`, made
by the user), same `.env` lines as the Framework, local Ollama as fallback.
Check over HTTP: 410 ms, no fallback. Before that its local model timed
out on 28 of 141 dictations. Its dictionary has a capitals-only acronym
fix (`AIR => ...`, `A I R => ...`).

Small fixes 2026-10-09 (Framework, `983bf04`). The local fallback model
is loaded in the background once Groq's rate-limit headers show under a
quarter of the minute's 8000 tokens or under 20 of the day's 1000
requests left, at most every 5 minutes (`server.py` `saw_headers`; log
field `warm_local`). A cold load took 10.2 s and pushed the fallback past
its 15 s limit; warm, the fallback answered in 1.8-5.4 s (2026-10-08).
`install.ps1` now waits up to 20 s for the helper (it took 3.1 s; the old
fixed wait was 2 s). Ollama keeps starting at logon: it is the fallback,
so it is no longer unused. Not covered: going offline gives no warning,
so the first offline dictation still loads the model cold. The Spectre
gets the code at its next `git pull` and `scripts/install.ps1`.

## Next, in order

1. **One dictionary on dabox**, waiting until dabox is built (the user
   chose to wait, 2026-10-08; `ai-system` STATE item 1). Until then, a
   new entry goes on both laptops by hand. (The user: "only the things
   that NEED to live locally there, and everything that can be
   centralized lives in dabox"). Today each laptop has its own
   `dictionary.txt` and they drift (one acronym was only on the Spectre). Plan:
   the personal dictionary and learn log live on the personal side of
   dabox; the helper reads it from there with a local cached copy for
   offline, and the learner writes new entries back. Work-only entries
   (anything learned from work, which may name people) stay in a
   local layer on the Framework, per the wall. Local stays: Handy and its
   model, the helper (it reads the screen and pastes), `.env` keys.
2. **dabox for voice memos**: tracked in `ai-system` `BACKBURNER.md`,
   "Voice recordings transcribed and filed" (trip-wire: dabox built and
   Alexandria exists). It reuses this repo's prompt, dictionary and model
   config in a batch form, not the live helper.
3. Before cancelling Aqua: a good week of daily use (`ai-system` STATE 2.2).

## Blocked

None.

## Open questions

Loose ends carried over from the closed `ai-system` thread `handy-context`
(2026-10-14):

- The learner wrote 0 rows to `corrections.jsonl` after 90 dictations
  (2026-10-07). It only sees a hand fix at the next dictation in the same
  field; why it saw none was never investigated.
- The README does not describe spoken edits (Edit Mode), learning or the
  context caps.
- The first dictation in a freshly opened browser may miss context.

## Dead ends and mistakes

- Shift+Left to select the last dictation (2026-10-07): Notepad takes
  ~100 key presses a second, so any last dictation over ~80 chars failed
  the check. Instead: UI Automation `Select()` on the range (e5342d2).
- Turning the always-on mic off by editing `settings_store.json` after a
  plain `taskkill` (2026-10-07): two `handy.exe` were running later and the
  setting was back on 3 minutes after the edit (cause not proven; likely a
  surviving copy saving its old settings on quit). Instead: `taskkill //F
  //IM handy.exe`, confirm none left with `tasklist`, then
  `configure_handy.py`.
- A background `shift.py` run in a fresh worktree (2026-10-07): "Workspace
  not trusted", never started. Instead: check `shift.py status` at once.

- Smaller models for the Framework (2026-10-08, `eval_cleanup.py --set
  cleanup`, integrated GPU on): qwen3 4b 32/34 at 3.1 s median; qwen2.5 3b
  26/34 at 1.7 s; llama3.2 3b 25/34 at 1.8 s; gemma3 1b 21/34 at 0.8 s.
  Too inaccurate. Instead: qwen3 4b with `HC_TIMEOUT_S=8` in the
  Framework's `.env`.
- Integrated GPU on the Framework (`OLLAMA_IGPU_ENABLE=1`, 2026-10-08):
  21% of the model on Intel UHD made writing slower, 4.8 tokens/s against
  6.6 on the CPU alone. Removed. Long dictations (150+ chars) still time
  out at 8 s here: writing speed, not reading the context (368 prompt
  tokens read in 0.2 s once warm).
- Restarting Ollama's tray app from a shell (2026-10-08): its server never
  came up ("ollama server not ready", empty `server.log`). Cause not found.
  Instead: `ollama serve` with `OLLAMA_IGPU_ENABLE=1`, or a reboot.
- `smoke.py --notepad` on a laptop the user is working on (2026-10-08): it
  opens Notepad and pastes, which takes over the screen. The user: "stop
  taking over my computer". Instead: `eval_cleanup.py`, which only calls
  the model; the user's own dictation is the live check.

Decided: `docs/decisions/` (none yet). Shelved: `BACKBURNER.md`.
