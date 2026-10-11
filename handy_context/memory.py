"""Remembers the last text the helper had Handy paste, and where.

"Edit the last dictation" may only touch text this helper itself pasted, so
the memory is honoured only when the same field is focused, the paste was
recent, and the text right before the caret is exactly that paste.
"""

import threading
import time
from dataclasses import dataclass

from .context import Context


def normalize(text: str) -> str:
    """Line breaks as one character each, the way a caret steps over them."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


@dataclass
class Paste:
    text: str
    app: str
    title: str
    element_id: str
    at: float


class Memory:
    def __init__(self, window_s: float = 60.0, clock=time.monotonic):
        self.window_s = window_s
        self.clock = clock
        self._last: Paste | None = None
        self._lock = threading.Lock()

    def remember(self, text: str, ctx: Context) -> None:
        with self._lock:
            self._last = Paste(normalize(text), ctx.app, ctx.title, ctx.element_id, self.clock()) if text else None

    def forget(self) -> None:
        with self._lock:
            self._last = None

    def peek(self) -> Paste | None:
        with self._lock:
            return self._last

    def why_not(self, ctx: Context) -> str:
        """Which check of `last_before_caret` failed, for the log (no text in it)."""
        p = self.peek()
        if p is None:
            return "nothing pasted yet"
        checks = [
            (not ctx.before_caret, "text before the caret unreadable"),
            (bool(ctx.selection), "text selected"),
            (self.clock() - p.at > self.window_s, "last paste too old"),
            (p.app != ctx.app, "another app"),
            (bool(p.element_id or ctx.element_id) and p.element_id != ctx.element_id, "another field"),
        ]
        for failed, reason in checks:
            if failed:
                return reason
        return "text before the caret is not the last paste"

    def last_before_caret(self, ctx: Context) -> tuple[str, int] | None:
        """(text, presses to select it) when the last paste sits right before the caret, else None.

        Handy may add one trailing space after a paste; it is selected too, and
        Handy adds it again after the new paste.
        """
        p = self.peek()
        if p is None or not ctx.before_caret or ctx.selection:
            return None
        if self.clock() - p.at > self.window_s:
            return None
        if p.app != ctx.app:
            return None
        if p.element_id or ctx.element_id:
            if p.element_id != ctx.element_id:
                return None
        elif p.title != ctx.title:  # title only when no field id; Notepad adds "*" after a paste
            return None
        before = normalize(ctx.before_caret)
        for tail in ("", " "):
            if before.endswith(p.text + tail):
                return p.text, len(p.text) + len(tail)
        return None
