# handy-context

A small local helper that gives Handy (the open-source dictation app,
github.com/cjpais/Handy) two things Aqua Voice has and Handy lacks:
**Deep Context** (the cleanup model sees the active app, window title,
selected text and the text around the cursor) and a **personal dictionary**
of uncommon words and spellings.

Status: being built, 2026-10-04. Plan: `plans/2026-10-04-handy-context.md`.
Runs on the HP Spectre (Windows 11 now, Fedora later).
Repo: public, github.com/marcosbatistaochoa/handy-context (since
2026-10-11; private before), cloned on the HP Spectre, the Framework and dabox. `git pull`
at the start of every session; another machine may have pushed.

## How it works

Handy's post-processing step sends an OpenAI-style chat request to any
base URL. Handy's "Custom" provider points at this helper on
`127.0.0.1`. The helper reads the screen context at that moment (focus is
still on the target app, because Handy's overlay is not focusable), builds
the cleanup prompt with the context and the dictionary, forwards it to the
configured model, applies the dictionary's fixed replacements to the answer,
and returns it. Handy pastes the result. No fork of Handy.

On Windows the same process also runs the **floater** (an Aqua-style pill,
`floater.py` for look, `winui.py` for the window) and a **Right Alt keyboard
hook** (`keys.py` state machine, `winui.py` hook). The hook holds F13 down
while you talk; Handy listens on F13 in push-to-talk mode, so Handy's
recording state follows the key. The floater's sizes and colours are
measured from Aqua's real floater; change them only against a new
screenshot, never by taste (`scripts/floater_demo.py` draws any state).

## Rules

- **Fail open.** If context capture or the model fails or is slow, return
  the raw transcript within the time budget. Dictation must never be lost or
  stuck because of this helper.
- **Local by default.** The default upstream is Ollama on this laptop.
  Screen text is private: switching the upstream to a cloud provider sends
  it off the machine, and the README says so where the setting lives.
- **Models are configuration** (`Projects/AGENTS.md` section 3): the
  upstream base URL and model id come from `.env`, resolved only in
  `handy_context/config.py`; `.env.example` lists each with its default.
- **One dictionary file**, `dictionary.txt` in the user's data folder (path in
  README). Nothing else holds the word list.
- **Logs stay small and local.** No screen text in logs unless
  `HC_LOG_CONTEXT=1`.
- **A fix is done when it survives a restart.** Before calling a Handy or
  helper fix done: list every running Handy and helper process (a second
  Handy once rewrote the always-on mic setting), restart them, re-read the
  setting from disk, and run `scripts/eval_cleanup.py`, which holds short,
  long (200+ word) and Spanish cases. On Groq's free plan use `--pace 8`;
  faster, the rate limit returns raw text and reads as failures. All of it
  headless: never open windows or paste on the user's screen; the live
  check with the mic is the user's.
- Commit and push after each piece of work; stage files by name.
- Never put work data in this repo. It is public: no names, emails or
  employer details in code, tests, docs or commit metadata.
