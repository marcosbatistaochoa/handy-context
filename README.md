# handy-context

Deep Context and a personal dictionary for [Handy](https://github.com/cjpais/Handy),
the free offline dictation app. A self-hosted replacement for what Aqua Voice
charges $10 a month for.

When you dictate, Handy turns your speech into text on your own laptop. It then
asks a language model to tidy the text. This helper sits in between. It tells
the model which app you are in, what the window is called, what text is
selected and what is written around the cursor, plus your list of special
words. The model can then spell names, code and jargon the way they appear on
your screen.

Everything runs on the laptop. Nothing is sent anywhere unless you change the
model setting to a cloud provider.

## Dictating

- **Hold Right Alt** and talk. Let go and the cleaned text is pasted.
- **Right Alt+Space** for hands-free: it keeps listening after you let go.
  Press Right Alt again to stop, or click the red stop button on the floater.
  The grey button on the left cancels.
- **Escape** cancels a recording.
- **Ctrl+Shift+Space** (hold) dictates without the cleanup step.

The small pill above the taskbar is the floater. It copies Aqua's: a thin
line when idle, a blue dot and level bars while you talk. Side-by-side
screenshots are in `docs/floater/`.

Quit Aqua Voice before using this. Both listen to Right Alt, and the helper
takes the key first, so Aqua would stop responding to it anyway.

## Setup

Windows 10 or 11 only for now: the keyboard hook, the floater and the screen
reading all use Windows APIs.

1. **Install Handy** from [its releases page](https://github.com/cjpais/Handy/releases).
   Open it once, pick a speech model, finish its setup, then quit it from the
   tray icon (right-click, Quit).
2. **Install Python 3.11 or newer** from [python.org](https://www.python.org/downloads/).
   Tick "Add python.exe to PATH" in the installer.
3. **Get the code** and its one dependency. In a terminal:

   ```
   git clone https://github.com/marcosbatistaochoa/handy-context.git
   cd handy-context
   python -m pip install -e .
   ```

4. **Pick the cleanup model.** Copy `.env.example` to `.env`. Then choose one:
   - **Groq, free and fast.** Make an account at
     [console.groq.com](https://console.groq.com), create an API key, and
     turn on Zero Data Retention in its settings. In `.env`, use the four
     commented Groq lines instead of the four `HC_UPSTREAM_BASE_URL`,
     `HC_UPSTREAM_API_KEY`, `HC_MODEL` and `HC_REASONING_EFFORT` lines above
     them, with your key after `HC_UPSTREAM_API_KEY=`. Your screen text and
     dictation then go to Groq (see Privacy below).
   - **Ollama, fully local.** Install [Ollama](https://ollama.com), then run
     `ollama pull qwen3:4b-instruct-2507-q4_K_M`. Leave `.env` as it is.
     On a laptop without a strong GPU it can take several seconds per
     dictation, and long ones fall back to the raw transcript.
5. **Point Handy at the helper**, with Handy still closed:

   ```
   python scripts/configure_handy.py
   ```

   It backs up Handy's settings file first, then sets Handy's Custom
   post-processing provider to `http://127.0.0.1:8765/v1`, puts Handy's
   main shortcut on F13 in push-to-talk mode (the helper presses F13 while
   you hold Right Alt), moves plain dictation to Ctrl+Shift+Space and turns
   Handy's own overlay off. `python scripts/configure_handy.py --check`
   prints the settings and changes nothing.
6. **Start the helper now and at every logon:**

   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install.ps1
   ```

   It adds a shortcut to your Startup folder and prints `Helper answers: ok`
   when the helper is up.
7. **Open Handy** and hold Right Alt to dictate.

Your word list is `%APPDATA%\handy-context\dictionary.txt`. One word per
line, or `heard => written` to fix a word the speech model always gets
wrong. A word you correct by hand twice the same way is added for you.

To remove it: delete `handy-context.lnk` from your Startup folder
(`shell:startup` in the Run box), end `pythonw.exe` in Task Manager, and
restore Handy's settings backup from `%APPDATA%\com.pais.handy\`.

## Privacy

The helper reads the active window's title, the selected text and up to
1,500 characters of text around the cursor at the moment you dictate, and
sends them with your dictation to the cleanup model. With Ollama that stays
on your laptop. With Groq or any other cloud URL in `.env`, it leaves your
laptop, so do not dictate into windows showing things you would not paste
into that provider's chat. Logs in `%APPDATA%\handy-context\logs` hold
timings and lengths, not screen text, unless you set `HC_LOG_CONTEXT=1`.

The helper listens only on `127.0.0.1` and refuses requests from web pages.
See `SECURITY.md` to report a problem.

## License

MIT. See `LICENSE`.
