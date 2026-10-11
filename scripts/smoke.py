"""End-to-end check against the real screen and the real model.

    python scripts/smoke.py --transcript "call frob nicate widget" --notepad "Kubernetes frobnicate_widget Xylocarpa"
    python scripts/smoke.py --transcript "..." --browser "text to show in a browser page"
    python scripts/smoke.py --transcript "..."          # no window, no screen context
    add --timing to print how long context capture took

Stand-ins for Handy (paste through the clipboard, then read Notepad back):
    python scripts/smoke.py --notepad "" --transcript "send the report to kate on friday" --edit-last "add a please at the end"
    python scripts/smoke.py --notepad "" --transcript "send the slides to marry gold" --learn "marry gold=>Marigold"
"""

import argparse
import ctypes
import json
import re
import subprocess
import sys
import tempfile
import time
import webbrowser
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from handy_context.config import load_config  # noqa: E402
from handy_context.context import Context, warm_up  # noqa: E402
from handy_context.learn import Learner  # noqa: E402
from handy_context.server import Helper  # noqa: E402


def paste(text: str) -> None:
    """What Handy does with the answer: clipboard, Ctrl+V. Empty means paste nothing."""
    import uiautomation as auto

    if text:
        auto.SetClipboardText(text)
        auto.SendKeys("{Ctrl}v", waitTime=0.3)


def field_text() -> str:
    """The focused field's whole text, read through UI Automation."""
    import uiautomation as auto

    control = auto.GetFocusedControl()
    pattern = control.GetPattern(auto.PatternId.TextPattern)
    if pattern:
        return pattern.DocumentRange.GetText(-1).replace("\r\n", "\n").replace("\r", "\n")
    return control.GetPattern(auto.PatternId.ValuePattern).Value


def wait_for_field(done, wait_s: float = 3.0) -> str:
    """Poll the field until `done(text)`; a paste lands asynchronously. Returns the last read."""
    end = time.time() + wait_s
    text = field_text()
    while not done(text) and time.time() < end:
        time.sleep(0.1)
        text = field_text()
    return text


def ask(helper: Helper, transcript: str) -> str:
    resp = helper.handle({"messages": [{"role": "user", "content": transcript}]})
    return resp["choices"][0]["message"]["content"]


def edit_last_check(cfg, transcript: str, command: str) -> int:
    """A5: dictate, then speak an edit with nothing selected; the field must show the edit only."""
    helper = Helper(replace(cfg, edit_last=True))
    first = ask(helper, transcript)
    paste(first)
    wait_for_field(lambda t: first in t)
    second = ask(helper, command)
    print(f"dictated: {first!r}\nedit answer: {second!r}")
    paste(second)
    ends_please = lambda t: t.rstrip().lower()[:-1].endswith("please") and t.rstrip()[-1:] in ".?!"  # noqa: E731
    text = wait_for_field(ends_please)
    print(f"field now: {text!r}")
    # Notepad started empty, so it must hold the edit and nothing else: the
    # first sentence replaced, not left in front of a second copy.
    ok = text.strip() == second.strip() and ends_please(text)
    print("A5", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def learn_check(cfg, transcript: str, rule: str) -> int:
    """A6: dictate, fix one phrase by hand, twice; the rule must land in a scratch dictionary on the 2nd sighting."""
    import uiautomation as auto

    heard, written = (s.strip() for s in rule.split("=>", 1))
    scratch = Path(tempfile.mkdtemp(prefix="hc-learn-"))
    cfg = replace(cfg, dictionary_path=scratch / "dictionary.txt", log_dir=scratch / "logs")
    # Pass-through model: a real one reads the first fix off the screen and spells it right
    # the second time, leaving nothing to fix. This checks the learning loop, not the model.
    helper = Helper(cfg, learner=Learner(cfg.dictionary_path, cfg.log_dir), upstream=lambda c, m, t: transcript)
    pattern = re.compile(re.escape(heard), re.IGNORECASE)
    for round_ in (1, 2):
        out = ask(helper, transcript)
        paste(out + " ")
        text = wait_for_field(lambda t: out in t)
        found = list(pattern.finditer(text))
        if not found:
            print(f"round {round_}: {heard!r} not in the field {text!r} after pasting {out!r}")
            return 1
        m = found[-1]
        fixed = text[:m.start()] + written + text[m.end():]
        auto.SendKeys("{Ctrl}a", waitTime=0.2)  # the hand fix: retype the field with the phrase corrected
        paste(fixed)
        wait_for_field(lambda t: t == fixed)
    ask(helper, transcript)  # the next dictation is when the second fix is noticed
    dict_path, log_path = cfg.dictionary_path, cfg.log_dir / "corrections.jsonl"
    dictionary = dict_path.read_text(encoding="utf-8") if dict_path.exists() else ""
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    print(f"corrections.jsonl:\n{log}dictionary.txt:\n{dictionary}")
    ok = f"{heard.lower()} => {written}" in dictionary and len(log.splitlines()) == 2
    print("A6", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def focus_window(title_part: str, wait_s: float = 8.0) -> bool:
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if title_part.lower() in buf.value.lower() and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    deadline = time.time() + wait_s
    while time.time() < deadline:
        found.clear()
        user32.EnumWindows(enum, 0)
        if found:
            hwnd = found[0]
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            # Windows lets a process take focus after a simulated Alt press.
            user32.keybd_event(0x12, 0, 0, 0)
            user32.keybd_event(0x12, 0, 2, 0)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.3)
            # That Alt press puts menu bars (Notepad's) in keyboard mode, focus on "File"; Escape leaves it.
            user32.keybd_event(0x1B, 0, 0, 0)
            user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.2)
            return True
        time.sleep(0.3)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--notepad")
    ap.add_argument("--browser")
    ap.add_argument("--timing", action="store_true")
    ap.add_argument("--no-model", action="store_true", help="capture only, skip the model")
    ap.add_argument("--edit-last", metavar="COMMAND", help="paste the transcript, then speak COMMAND as an edit (A5)")
    ap.add_argument("--learn", metavar="HEARD=>WRITTEN", help="paste, fix HEARD to WRITTEN by hand, twice (A6)")
    args = ap.parse_args()
    if (args.edit_last or args.learn) and args.notepad is None:
        ap.error("--edit-last and --learn need --notepad")

    cfg = load_config()
    error = warm_up()  # as the helper does at start; setup would otherwise eat the budget
    if error:
        print(f"warm-up: {error}")
    tag = f"hc-smoke-{int(time.time())}"
    if args.notepad is not None:
        path = Path(tempfile.gettempdir()) / f"{tag}.txt"
        path.write_text(args.notepad, encoding="utf-8")
        subprocess.Popen(["notepad.exe", str(path)])
        if not focus_window(tag):
            print("could not focus Notepad")
            return 1
    elif args.browser:
        path = Path(tempfile.gettempdir()) / f"{tag}.html"
        path.write_text(f"<title>{tag}</title><textarea autofocus cols=80 rows=10>{args.browser}</textarea>", encoding="utf-8")
        webbrowser.open(path.as_uri())
        time.sleep(3)
        if not focus_window(tag, 10):
            print("could not focus the browser")
            return 1

    if args.edit_last:
        return edit_last_check(cfg, args.transcript, args.edit_last)
    if args.learn:
        return learn_check(cfg, args.transcript, args.learn)

    captured: dict = {}
    helper = Helper(cfg)
    real_capture = helper.capture

    def capture() -> Context:
        ctx = real_capture()
        captured["ctx"] = ctx
        return ctx

    helper.capture = capture
    if args.no_model:
        helper.upstream = lambda c, m, t: args.transcript
    t0 = time.perf_counter()
    resp = helper.handle({"messages": [{"role": "user", "content": args.transcript}]})
    total = time.perf_counter() - t0
    ctx = captured.get("ctx") or Context()
    if args.timing:
        print(f"context: {ctx.ms} ms, app={ctx.app!r}, title={ctx.title!r}, chars={len(ctx.near_cursor)}+{len(ctx.visible)}, error={ctx.error!r}")
        print(f"total: {total * 1000:.0f} ms")
    print(resp["choices"][0]["message"]["content"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
