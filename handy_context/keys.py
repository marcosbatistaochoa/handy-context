"""Right Alt shortcuts as a pure state machine, so it can be tested anywhere.

Hold Right Alt: talk while it is held. Right Alt+Space: hands-free, until
Right Alt is pressed again. Escape while recording: cancel.

Handy itself listens on F13 in push-to-talk mode; the Windows hook turns
`press`/`release` into F13 down/up. Holding F13 down for the whole recording
means Handy's own state follows the key and cannot drift from ours.
"""

from dataclasses import dataclass, field

IDLE, HOLD, LOCKED = "idle", "hold", "locked"

# Actions for the platform layer.
PRESS, RELEASE, CANCEL = "press", "release", "cancel"


@dataclass
class Result:
    swallow: bool = False
    actions: list[str] = field(default_factory=list)


class RightAlt:
    def __init__(self) -> None:
        self.state = IDLE
        self.ralt_down = False
        self.space_swallowed = False  # swallow the Space key-up that matches a swallowed down
        self.stop_pending = False  # the Right Alt press that stopped a locked recording

    def ralt(self, down: bool) -> Result:
        if down:
            if self.ralt_down:  # auto-repeat
                return Result(swallow=True)
            self.ralt_down = True
            if self.state == IDLE:
                self.state = HOLD
                return Result(True, [PRESS])
            if self.state == LOCKED:
                self.state = IDLE
                self.stop_pending = True
                return Result(True, [RELEASE])
            return Result(swallow=True)
        if not self.ralt_down:  # an up we never saw go down: not ours
            return Result()
        self.ralt_down = False
        if self.stop_pending:
            self.stop_pending = False
            return Result(swallow=True)
        if self.state == HOLD:
            self.state = IDLE
            return Result(True, [RELEASE])
        return Result(swallow=True)  # LOCKED: the latch press ends; keep recording

    def space(self, down: bool) -> Result:
        if down and self.state == HOLD and self.ralt_down:
            self.state = LOCKED
            self.space_swallowed = True
            return Result(swallow=True)
        if not down and self.space_swallowed:
            self.space_swallowed = False
            return Result(swallow=True)
        if down and self.state == LOCKED and self.ralt_down:
            return Result(swallow=True)  # Space auto-repeat while still holding Right Alt
        return Result()

    def escape(self, down: bool) -> Result:
        if down and self.state in (HOLD, LOCKED):
            self.state = IDLE
            return Result(False, [CANCEL])  # Escape passes on; Handy cancels on it too
        return Result()

    def other(self, down: bool) -> Result:
        """Any other key while Right Alt is held means it was a key combination, not dictation."""
        if down and self.state == HOLD and self.ralt_down:
            self.state = IDLE
            return Result(False, [CANCEL])
        return Result()

    def click_stop(self) -> list[str]:
        if self.state == LOCKED:
            self.state = IDLE
            return [RELEASE]
        return []

    def click_cancel(self) -> list[str]:
        if self.state in (HOLD, LOCKED):
            self.state = IDLE
            return [CANCEL]
        return []
