# Handy with Deep Context and a dictionary

Tier: 3 · Repo: handy-context · Written: 2026-10-04 · Bene Gesserit: skipped, no Bene Gesserit yet
Run: through · Risky: no
Lessons applied: 2026-09-23 [install] (the user runs each install with `!`), 2026-09-23 [facts] (hostname, GPU and model tags read live today), 2026-09-28 [hooks] (fail open: the helper never blocks dictation)

## Summary

- **You get:** Handy dictation on the Spectre that knows which app you are in and
  what is on screen around the cursor, so names, code and jargon come out spelled
  right. Plus one text file, `dictionary.txt`, for your special words and fixed
  spellings. Everything runs on the laptop for $0 a month.
- **Cost:** about two to three hours of build, moderate usage. You run three
  one-line installs and do one dictation test in three apps.
- **Risks:** a small local model may clean up worse than Aqua's cloud model;
  `HC_MODEL` in `.env` switches it in one line. Some apps (games, some Electron
  apps) expose no screen text, so those get window-title context only.
- **Your decisions:** none. Cancel Aqua only after a week you are happy with.

## Goal (frozen once approved)

- **Objective:** dictating with Handy on the Spectre pastes cleaned text whose
  spelling of on-screen names and dictionary words is right, with the helper
  adding under 300 ms before the model call.
- **Always:** fail open (raw transcript back inside the time budget on any
  error); local model by default; model ids only in `handy_context/config.py`
  and `.env`; no screen text in logs by default.
- **Never:** fork or patch Handy's binary; send screen text off the laptop by
  default; put work data anywhere here; install anything without the user's `!`.
- **Stop conditions:** context capture cannot read Notepad's text at all
  (the approach is wrong; come back); Handy stops calling the helper; the local
  model's cleanup takes over 3 s for 40 words with no faster model that works.

## Acceptance criteria

- **A1.** `python -m pytest -q` in `handy-context` passes, covering the
  dictionary parser, prompt builder, replacements, the fail-open path and a
  full request through the helper against a fake upstream.
- **A2.** With Notepad showing `Kubernetes frobnicate_widget Xylocarpa`,
  `python scripts/smoke.py --transcript "call frob nicate widget on the zylo carpa node"`
  prints text containing `frobnicate_widget` and `Xylocarpa`, using the real
  local model.
- **A3.** A `heard => written` line in `dictionary.txt` is applied: smoke with
  a dictionary line `mari gold => Marigold` turns "mari gold" into
  `Marigold` with no screen context.
- **A4.** `scripts/smoke.py --timing` reports context capture under 300 ms in
  Notepad and in a browser window.
- **A5.** The helper starts at logon: `handy-context.lnk` exists in the
  user's Startup folder (no admin needed, unlike a logon task), and
  `curl http://127.0.0.1:8765/health` answers `ok` after `scripts/install.ps1`
  restarts it.
- **A6.** Handy's settings file shows post-processing on, the Custom provider
  at `http://127.0.0.1:8765/v1`, the selected prompt's text exactly
  `${output}`, and the main shortcut on `transcribe_with_post_process`.
- **A7.** The user dictates once each into Notepad, a browser text box and VS
  Code (or the terminal) with the main shortcut, the helper's log shows one
  request per dictation, and the user says the result is good enough.

## Decided without you

- Helper in front of Handy, not a fork. Source: Handy's `llm_client.rs` posts to
  `{base_url}/chat/completions` with an editable Custom base URL; its overlay is
  `focusable(false)` (`overlay.rs`), so the target app still has focus. Cost if
  wrong: a fork, much more upkeep.
- Context from Windows UI Automation via `uiautomation` 2.0.29 (read in source)
  plus the window title and process name. Not screenshots: faster, private, no
  vision model. My choice. Cost if wrong: apps without accessible text get less
  context (screenshot is on the backburner).
- Local model through Ollama, default `qwen3:4b` (2.5 GB, tag read on
  ollama.com 2026-10-04), thinking off via `reasoning_effort: none` (Ollama
  OpenAI docs, Context7). Cost if wrong: one `.env` line.
- Speech model in Handy: Parakeet V3 (CPU-optimised, leaves the GPU to the
  cleanup model). Source: Handy README. Cost if wrong: one Handy setting.
- Python 3 stdlib HTTP server, port 8765, bound to 127.0.0.1 only. My choice.
- Dictionary format: one entry per line; `Word` (a spelling to prefer) or
  `heard => Written` (always replaced after the model answers, whole words,
  case-insensitive); `#` comments. My choice.
- Autostart with a Task Scheduler logon task running `pythonw`. My choice.

## Review Focus (tier 3)

1. Context read after focus moved (Handy window, overlay): U3 check reads
   Notepad from a script started elsewhere, U6 confirms in real use.
2. A slow or dead model leaves the user waiting: U4 test with a hanging fake
   upstream must return the raw transcript inside the budget.
3. The model answers the dictated text instead of cleaning it, or obeys
   instructions in screen text: U2 prompt fences context and transcript; U4
   test with an instruction in the context.
4. Handy's structured-output request (`response_format`, `transcription`
   field) breaks through the helper: U4 test uses Handy's exact request shape.
5. Long screen text blows the prompt: U3 caps context at 4,000 characters
   around the cursor.

## Units

### U1. Project skeleton

- **Does:** AGENTS.md, CLAUDE.md, README.md, STATE.md, BACKBURNER.md, git repo.
- **Files:** those five, `.gitignore`, this plan.
- **Depends on:** none.
- **Check:** `git log --oneline` shows the commit.
- **Model:** inline. **Risk:** routine. **Owner:** inline.

### U2. Config, dictionary and prompt

- **Does:** `config.py` (env with defaults), `dictionary.py` (parse, apply
  replacements), `prompt.py` (system prompt from context and dictionary).
- **Files:** `handy_context/__init__.py`, `config.py`, `dictionary.py`,
  `prompt.py`, `.env.example`, `tests/test_dictionary.py`, `tests/test_prompt.py`.
- **Depends on:** U1.
- **Interfaces:** Produces `load_config()`, `Dictionary.load(path)`,
  `Dictionary.apply(text)`, `build_messages(transcript, context, dictionary)`.
- **Check:** `python -m pytest -q tests/test_dictionary.py tests/test_prompt.py`.
- **Model:** inline. **Risk:** routine. **Owner:** inline.

### U2b. The user's installs

- **Does:** the user runs, each with `!`: `winget install cjpais.Handy`,
  `winget install Ollama.Ollama`, `python -m pip install uiautomation==2.0.29`,
  then `ollama pull qwen3:4b`.
- **Files:** none.
- **Depends on:** U1.
- **Check:** `python -c "import uiautomation"` exits 0; `ollama list` shows `qwen3:4b`.
- **Owner:** the user.

### U3. Context capture (Windows)

- **Does:** `context.py`: foreground process and title, focused element's
  selection and text around the caret, nearby visible text, capped at 4,000
  characters and a 250 ms budget; returns empty context on any error.
- **Files:** `handy_context/context.py`, `tests/test_context.py`,
  `scripts/show_context.py`.
- **Depends on:** U1, U2b.
- **Interfaces:** Produces `capture() -> Context` (fields `app`, `title`,
  `selection`, `near_cursor`, `visible`, `ms`).
- **Check:** open Notepad with known text, run `scripts/show_context.py --delay 3`
  after focusing Notepad; output contains the text and `ms` < 300.
- **Model:** inline. **Risk:** routine. **Owner:** inline.

### U4. The helper server

- **Does:** `server.py`: `POST /v1/chat/completions` (Handy's request, both
  structured and plain), `GET /v1/models`, `GET /health`; captures context,
  builds messages, forwards to upstream, applies replacements, fails open.
- **Files:** `handy_context/server.py`, `handy_context/__main__.py`,
  `tests/test_server.py`.
- **Depends on:** U2, U3.
- **Check:** `python -m pytest -q` (A1).
- **Model:** inline. **Risk:** routine. **Owner:** inline.

### U5. Install and wire up

- **Does:** writes the autostart task and `scripts/smoke.py`; with Handy
  closed, `configure_handy.py` sets its settings (A6). Installs are U2b.
- **Files:** `scripts/smoke.py`, `scripts/install.ps1`, `scripts/configure_handy.py`, README.
- **Depends on:** U4.
- **Check:** A2 to A6.
- **Model:** inline. **Risk:** routine. **Owner:** inline.

### U7. Aqua-style floater (the user, 2026-10-04: "look at Aqua's UI and do that, don't invent")

- **Does:** our own always-on-top, click-through pill at bottom centre just
  above the taskbar; Handy's overlay set to `overlay_style: none`.
- **Evidence read (Aqua 0.20.16 installed, `%LOCALAPPDATA%/aqua-voice/app-0.20.16/resources/app.asar`,
  renderer `.webpack/renderer/main_window/index.js`, minified):** Windows uses the
  "legacy" layout (confirmed by screenshot: idle pill 109x19 physical px at 200%
  scale = 55x10). Sizes in CSS px: idle 55x10, opacity 0.75; hover 80x20;
  active (recording) 110x37; active locked (hands-free) 160x37; edit-unclear
  110x37; finalizing scales to 0.96. Idle look: black fill, thin grey border,
  fully rounded. Recording shows 5 bars, width 3.8 px, gap 2 px, from 12
  frequency bands grouped `[10,11],[2,3],[4,5,6,7],[0,1],[8,9]` with floor/gain
  `.06/1.45, .06/1.45, .2/.9, .06/1.45, .06/1.45` (function `rd()`, constants
  `nd`, `ad`). Glass-mode sizes (`ed`, macOS) not used on Windows.
  Assets `floater-bloom-ptt.png` (one soft blue glow) and
  `floater-bloom-locked.png` (two glows) exist; not copied, redraw only.
- **Still to verify by live screenshot:** active colours, bar colour, what
  the 160-wide locked pill shows besides bars (stop button?), sounds on/off
  (Aqua ships `sounds/default/on.wav`, `off.wav`). Method: focus a Notepad,
  hold Right Alt via `keybd_event` 1 s, screenshot with
  `scratchpad/crop.ps1`-style capture (DPI aware), release; close Notepad unsaved.
- **Check:** screenshots of our floater in idle, hold and locked states put
  side by side with Aqua's.

### U8. Right Alt shortcuts (the user, 2026-10-04)

- **Does:** hold Right Alt = talk while held; Right Alt+Space = hands-free,
  stays on until Right Alt is pressed again. Handy cannot do both (one global
  `shortcut_activation`), so a low-level keyboard hook (WH_KEYBOARD_LL, ctypes)
  in the helper drives `handy --toggle-post-process` (Handy CLI, README) and
  swallows the Space and the lone-Alt menu activation. Handy's own
  post-process binding moves to an unused key. Measure CLI start latency;
  if the first word gets cut, fall back to Handy's native `ralt` binding in
  `hold_or_toggle` mode (handy-keys 0.3.4 accepts `ralt`, source read) and tell the user.
- **Check:** hook unit test of the state machine (hold, latch, stop); live: the floater changes state.

### U6. The user's test

- **Does:** the user dictates into three apps; fixes from what they report.
- **Depends on:** U5.
- **Check:** A7.
- **Owner:** the user, then inline.

## Critic

Pass one, 2026-10-04, five findings, all checked against Handy and uiautomation source:

1. Custom provider never sends structured output; one user message = selected
   prompt with `${output}` replaced — fixed: Handy's prompt is set to exactly
   `${output}` (never blank, `actions.rs:172` skips blank), the helper owns the
   rules, U4 tests Handy's legacy body `{model, messages:[user], stream:false,
   reasoning_effort:"none"}`, A6 checks the prompt text.
2. U3 needs uiautomation before U5 installs it — fixed: new U2b (user installs)
   before U3; `context.py` imports uiautomation lazily so A1 runs without it.
3. Handy's HTTP client has no timeout; UIA can hang — fixed: context runs in a
   worker thread joined at `HC_CONTEXT_BUDGET_MS` (250), the model call is
   capped by `HC_TIMEOUT_S` (4); U4 tests both a hanging capture and a hanging
   upstream returning the raw transcript inside budget plus 0.5 s.
4. Only the "Transcribe with Post-Processing" shortcut calls the helper, and
   Handy rewrites its settings file while running — fixed: `configure_handy.py`
   refuses to run while Handy is open, moves the main shortcut to the
   post-processing action and the plain one to `ctrl+shift+space`; A7 requires
   the helper log to show one request per test dictation.
5. Handy's own `custom_words` would be a second word list; model pull is an
   install; shared `__init__.py` — fixed: `custom_words` stays empty and the
   README says `dictionary.txt` is the only list; `ollama pull` is one of the
   user's commands; U2 owns `__init__.py` and `pyproject.toml`.

## Progress

Now: waiting on the user for what is left of U2b. Handy 0.9.8 and Ollama
are installed (checked 2026-10-05: `winget list`, `ollama.exe` present).
Still to do: `python -m pip install uiautomation==2.0.29`, then
`ollama pull qwen3:4b`, then open Handy once, pick Parakeet V3, quit it.
Then: U3 check (`scripts/show_context.py` on Notepad), quit Aqua,
`scripts/install.ps1`, `scripts/configure_handy.py`, A2 to A6, and a live
Right Alt dictation (U8 live check with Handy).

- 2026-10-04 U1 done, commit c2cc8db.
- 2026-10-04 Critic pass one: five findings, all fixed (see Critic).
- 2026-10-04 U2 and U4 done, commit 819d437, `python -m pytest -q` 23 passed.
  U3 code written; its live check waits on uiautomation (U2b).
- 2026-10-04 U5 scripts written: configure_handy.py, smoke.py, show_context.py, install.ps1.
  A5 changed from a logon task to a Startup shortcut (no admin).
- 2026-10-05 U7 done. Live Aqua screenshots taken by driving its Right Alt
  into a throwaway text box. Corrections to the minified-code reading: the
  Windows pill shows **12** level dots (3 px wide, 5 px pitch, rest #545454),
  not 5 bars; locked is 160x37 with a #c0c0c0 cancel circle left and a
  #882922 stop circle with a #dcbfbd rounded square right, each behind a
  #27272a hairline divider; the blue dot is 13 px, gradient #8cc2fa to #6490f7;
  idle border is 1 device px, active 1 CSS px; pill bottom 15 px above the
  taskbar. Our floater (`floater.py`, `gdip.py`, `winui.py`) matches the idle
  pill pixel for pixel (rows 214-233, #62646b border, #030303 fill); pairs in
  `docs/floater/`. Not copied: Aqua's sounds (not checkable from a screenshot)
  and its glow PNGs.
- 2026-10-05 U8 done except the live check with Handy. Design changed from
  `handy --toggle-post-process` to holding F13 (Handy push-to-talk on F13):
  no process start per press, and Handy's state cannot drift from ours.
  Evidence: handy-keys 0.3.4 `windows/listener.rs` has no injected-event
  filter, `keycode.rs` maps F13. `tests/test_keys.py` 6 tests; full suite 29
  passed. Live hook run (test keys marked with dwExtraInfo, helper on port
  8799): F13 down on hold, stays down when locked, up on stop, up on Escape;
  the target text box stayed empty (nothing leaked). `configure_handy.py` now
  sets the cleanup binding `f13`, `shortcut_activation: push_to_talk`,
  `overlay_style: none`; dry run on a fake store passed `--check`.
- 2026-10-05 U3 live check passed on Notepad: three warm captures 163, 111,
  129 ms (budget 250), `near_cursor` holds the file's text, no error. Two
  causes of the earlier 650-840 ms: UIA set up per call (now one worker
  thread, warmed at start, ed6084d) and uiautomation's `MoveEndpointByRange`
  sleeping 0.5 s by default (`waitTime=0`, 5d337de). qwen3:4b pulled.
- 2026-10-05 A2 smoke: capture fine (Notepad text read, 208 ms) once
  smoke.py warms up and presses Escape after its focus trick (the simulated
  Alt had put focus on Notepad's "File" menu). The model timed out at 4 s
  every time, two causes. (1) `qwen3:4b` is now the 2507 build, which always
  thinks: `think:false` still gave "Okay, the user said...". Default changed
  to `qwen3:4b-instruct-2507-q4_K_M` (pulled; 26 tokens, no thinking).
  (2) On battery the RTX 4050 sits at P8, 210 MHz, 100% busy: 2.6 tokens/s,
  ~10 s per answer. Retest A2 on mains power.
- 2026-10-07 On mains, Aqua quit: A2 pass (Notepad, 227 ms, "Call the
  frobnicate_widget on the Xylocarpa node."), A3 pass ("Please send it to
  Marigold."), A4 pass in Brave on reruns (251, 262 ms, 31 chars of the
  text box read, "Xylocarpa" corrected). The first Brave run read none of
  the text box (0 chars); every later read worked. Likely Brave's
  accessibility switching on at the first UI Automation query (unverified);
  the first dictation in a fresh browser may miss context. A1 is covered
  by the 71-test suite. Left: A5, A6 (wire Handy), A7 (the user).
