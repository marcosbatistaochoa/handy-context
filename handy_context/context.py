"""Reads what is on screen where the user is typing, within a time budget.

Windows only for now (UI Automation). On any other system, or on any error,
it returns what it has so far, possibly nothing: dictation must never fail
because of context.
"""

import ctypes
import queue
import sys
import threading
import time
from dataclasses import dataclass

# Never ask for more than this from one element, before trimming.
_RAW_TEXT_LIMIT = 20000


@dataclass
class Context:
    app: str = ""
    title: str = ""
    selection: str = ""
    near_cursor: str = ""
    visible: str = ""
    ms: int = 0
    error: str = ""
    # Exact text from the start of the field up to the caret (its last part),
    # only when the caret offset is known; edit-last needs it to be exact.
    before_caret: str = ""
    selection_truncated: bool = False
    # Which element was focused (UIA RuntimeId), to re-read the same field later.
    element_id: str = ""

    def is_empty(self) -> bool:
        return not (self.app or self.title or self.selection or self.near_cursor or self.visible)


def _foreground_window() -> tuple[str, str]:
    """Title and process name of the foreground window, via plain Win32 calls."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    app = ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if handle:
        try:
            size = ctypes.c_ulong(1024)
            path = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                app = path.value.rsplit("\\", 1)[-1]
        finally:
            kernel32.CloseHandle(handle)
    return app, buf.value


def _trim_around(text: str, caret: int, limit: int) -> str:
    """Keep `limit` characters, mostly before the caret, where the user is writing."""
    if len(text) <= limit:
        return text
    caret = max(0, min(caret, len(text)))
    before = int(limit * 0.75)
    start = max(0, caret - before)
    end = min(len(text), start + limit)
    start = max(0, end - limit)
    return text[start:end]


def _focused_text(ctx: Context, max_chars: int, deadline: float, near_max: int) -> None:
    import uiautomation as auto

    focused = auto.GetFocusedControl()
    if focused is None:
        return
    try:
        ctx.element_id = ",".join(str(x) for x in focused.GetRuntimeId())
    except Exception:
        ctx.element_id = ""
    text, caret = "", -1
    pattern = focused.GetPattern(auto.PatternId.TextPattern)
    if pattern:
        selections = pattern.GetSelection()
        if selections:
            sel = selections[0].GetText(_RAW_TEXT_LIMIT)
            if sel:
                ctx.selection = sel[:max_chars]
                ctx.selection_truncated = len(sel) > max_chars
            # Text from the document start to the selection start gives the caret offset.
            try:
                doc = pattern.DocumentRange
                head = doc.Clone()
                # waitTime=0: the library otherwise sleeps 0.5 s after the move.
                head.MoveEndpointByRange(
                    auto.TextPatternRangeEndpoint.End, selections[0], auto.TextPatternRangeEndpoint.Start, waitTime=0
                )
                head_text = head.GetText(_RAW_TEXT_LIMIT)
                if len(head_text) < _RAW_TEXT_LIMIT:  # else the caret offset is unknown
                    caret = len(head_text)
                    ctx.before_caret = head_text[-max_chars:]
            except Exception:
                caret = -1
        if time.perf_counter() < deadline:
            text = pattern.DocumentRange.GetText(_RAW_TEXT_LIMIT)
    if not text:
        value = focused.GetPattern(auto.PatternId.ValuePattern)
        if value:
            text = value.Value or ""
    if not text:
        text = focused.Name or ""
    if text:
        ctx.near_cursor = _trim_around(text, caret if caret >= 0 else len(text), near_max)


def _visible_text(ctx: Context, max_chars: int, deadline: float) -> None:
    """Names of controls in the foreground window, breadth-first, until the deadline."""
    import uiautomation as auto

    window = auto.GetForegroundControl()
    if window is None:
        return
    seen, out, total = set(), [], 0
    queue = [window]
    while queue and time.perf_counter() < deadline and total < max_chars:
        node = queue.pop(0)
        try:
            name = (node.Name or "").strip()
            if name and name not in seen and name != ctx.title and len(name) < 500:
                seen.add(name)
                out.append(name)
                total += len(name) + 1
            queue.extend(node.GetChildren())
        except Exception:
            continue
    ctx.visible = "\n".join(out)[:max_chars]


def _capture_into(ctx: Context, limits: tuple[int, int, int], deadline: float) -> None:
    max_chars, near_max, visible_max = limits
    try:
        _focused_text(ctx, max_chars, deadline, near_max)
    except Exception as exc:  # an app with a broken accessibility tree
        ctx.error = f"focused: {exc!r}"[:200]
    remaining = min(visible_max, max_chars - len(ctx.near_cursor) - len(ctx.selection))
    if remaining > 200 and time.perf_counter() < deadline:
        try:
            _visible_text(ctx, remaining, deadline)
        except Exception as exc:
            ctx.error += f" visible: {exc!r}"[:200]


class _Worker:
    """One thread that sets up UI Automation once and then serves captures.

    Setting it up costs ~0.5 s (COM, plus generating comtypes wrappers on the
    very first run), far over the budget, so it must not happen per request.
    A worker stuck on a frozen app is abandoned and a fresh one started.
    """

    def __init__(self) -> None:
        self.jobs: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        self.busy = False
        self.error = ""
        threading.Thread(target=self._run, name="hc-uia", daemon=True).start()

    def _run(self) -> None:
        try:
            import uiautomation as auto

            with auto.UIAutomationInitializerInThread():
                auto.GetRootControl()  # forces the COM objects into existence now
                self.ready.set()
                while True:
                    ctx, limits, deadline, done = self.jobs.get()
                    self.busy = True
                    if callable(ctx):  # a one-off UI Automation call: (fn, box, None, done)
                        try:
                            limits["result"] = ctx()
                        except Exception as exc:
                            limits["error"] = exc
                    else:
                        _capture_into(ctx, limits, deadline)
                    self.busy = False
                    done.set()
        except ImportError:
            self.error = "uiautomation is not installed; window title only"
        except Exception as exc:
            self.error = f"uia setup: {exc!r}"[:200]
        self.ready.set()


_worker: _Worker | None = None
_worker_lock = threading.Lock()


def _select_before_caret(chars: int) -> str:
    import uiautomation as auto

    focused = auto.GetFocusedControl()
    pattern = focused.GetPattern(auto.PatternId.TextPattern) if focused else None
    selections = pattern.GetSelection() if pattern else None
    if not selections:
        return ""
    r = selections[0].Clone()
    r.MoveEndpointByUnit(auto.TextPatternRangeEndpoint.Start, auto.TextUnit.Character, -chars, waitTime=0)
    r.Select(waitTime=0)
    return r.GetText(_RAW_TEXT_LIMIT)


def select_before_caret(chars: int, timeout_s: float = 0.5) -> str | None:
    """Select the `chars` characters before the caret through UI Automation, in
    one call: Shift+Left key presses reach Notepad at ~100 per second, so a long
    dictation could not be selected in time. Returns the text the range covers,
    or None when the app has no text pattern or the call fails (use the keys)."""
    if sys.platform != "win32":
        return None
    worker = _get_worker()
    if not worker.ready.wait(timeout_s) or worker.error:
        return None
    box: dict = {}
    done = threading.Event()
    worker.jobs.put((lambda: _select_before_caret(chars), box, None, done))
    if not done.wait(timeout_s) or "error" in box:
        return None
    return box.get("result") or None


def warm_up(timeout_s: float = 10.0) -> str:
    """Start the capture worker and wait until it is ready. Returns an error, or ''."""
    if sys.platform != "win32":
        return ""
    w = _get_worker()
    w.ready.wait(timeout_s)
    return w.error


def _get_worker() -> _Worker:
    global _worker
    with _worker_lock:
        if _worker is None or _worker.busy or _worker.error:
            _worker = _Worker()
        return _worker


def capture(max_chars: int = 4000, budget_ms: int = 250, near_max: int | None = None,
            visible_max: int | None = None) -> Context:
    """Screen context for the app in the foreground. Never raises, never exceeds the budget by much.

    `max_chars` caps the selection and `before_caret`, which edits need whole;
    `near_max` and `visible_max` cap the text shown to the model, whose time
    grows with it (measured: 433 ms with none, 972 ms at 2000 + 2000)."""
    start = time.perf_counter()
    ctx = Context()
    if sys.platform != "win32":
        ctx.error = "context capture is Windows-only for now"
        return ctx
    try:
        ctx.app, ctx.title = _foreground_window()
    except Exception as exc:
        ctx.error = f"window: {exc!r}"[:200]
    # UI Automation calls can hang on a frozen app, so they run on the worker
    # thread and are abandoned at the deadline; whatever arrived by then is used.
    deadline = start + budget_ms / 1000
    partial = Context(app=ctx.app, title=ctx.title)
    worker = _get_worker()
    done = threading.Event()
    if worker.ready.wait(max(0.0, deadline - time.perf_counter())) and not worker.error:
        limits = (max_chars, near_max or max_chars, visible_max or max_chars)
        worker.jobs.put((partial, limits, deadline, done))
        finished = done.wait(max(0.0, deadline - time.perf_counter()) + 0.05)
    else:
        finished = False
        if worker.error:
            partial.error = worker.error
    ctx.selection, ctx.near_cursor, ctx.visible = partial.selection, partial.near_cursor, partial.visible
    ctx.before_caret, ctx.selection_truncated = partial.before_caret, partial.selection_truncated
    ctx.element_id = partial.element_id
    if partial.error:
        ctx.error = (ctx.error + " " + partial.error).strip()
    if not finished and not worker.error:
        ctx.error = (ctx.error + " timed out").strip()
    ctx.ms = int((time.perf_counter() - start) * 1000)
    return ctx
