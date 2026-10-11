"""The floater's look and motion, copied from Aqua Voice 0.20.16 on Windows.

Every size and colour here was measured from screenshots of the real Aqua
floater on this laptop (2026-10-04, 200% scaling), in CSS pixels:

- idle: 55x10 pill, black at 75% opacity, grey hairline border
- hover (idle): 80x20
- hold (talking while Right Alt is held): 110x37, blue dot + 12 level dots
- locked (hands-free): 160x37, adds a cancel button left and a stop button
  right, each behind a hairline divider
- finalizing (after release, until the text is pasted): hold size at 96%

Pills grow upward from a fixed bottom edge, centred above the taskbar.
"""

import math
import time
from dataclasses import dataclass

IDLE, HOVER, HOLD, LOCKED, FINALIZING = "idle", "hover", "hold", "locked", "finalizing"

SIZES = {IDLE: (55, 10), HOVER: (80, 20), HOLD: (110, 37), LOCKED: (160, 37), FINALIZING: (110, 37)}
BOTTOM_GAP = 15  # above the work area (taskbar); 30 device px measured at 200%
SIDE = 28  # width of the cancel and stop sections in the locked pill
DOT = 13  # blue dot and button diameter
BAR_W, BAR_PITCH, BAR_REST, BAR_MAX = 3, 5, 3, 17
GAP_DOT_BARS = 8

BLACK = 0x000000
IDLE_BORDER = 0x7F828B  # measured #62646b once drawn at 75% over the dark desktop
ACTIVE_BORDER = 0x27272A
DOT_LEFT, DOT_RIGHT = 0x8CC2FA, 0x6490F7
BAR_QUIET, BAR_LOUD = 0x545454, 0x8A8A8A
CANCEL_FILL, CANCEL_X = 0xC0C0C0, 0x868992
STOP_FILL, STOP_SQUARE = 0x882922, 0xDCBFBD

# Room for the largest pill plus anti-aliasing, in CSS px.
CANVAS_W, CANVAS_H = SIZES[LOCKED][0] + 10, SIZES[LOCKED][1] + 10


def _mix(a: int, b: int, t: float) -> int:
    t = max(0.0, min(1.0, t))
    out = 0
    for shift in (16, 8, 0):
        ca, cb = (a >> shift) & 255, (b >> shift) & 255
        out |= int(ca + (cb - ca) * t) << shift
    return out


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class Look:
    """Animated values, eased toward the target state each frame."""

    w: float = SIZES[IDLE][0]
    h: float = SIZES[IDLE][1]
    zoom: float = 1.0


class Floater:
    def __init__(self) -> None:
        self.state = IDLE
        self.look = Look()
        self.levels = [0.0] * 12
        self._shown = [0.0] * 12

    def set_state(self, state: str) -> None:
        self.state = state

    def step(self, dt: float) -> bool:
        """Advance the animation; True while anything is still moving."""
        tw, th = SIZES[self.state]
        tz = 0.96 if self.state == FINALIZING else 1.0
        k = 1 - math.exp(-dt / 0.06)  # ~60 ms time constant, close to Aqua's spring
        lk = self.look
        lk.w += (tw - lk.w) * k
        lk.h += (th - lk.h) * k
        lk.zoom += (tz - lk.zoom) * k
        target = self.levels if self.state in (HOLD, LOCKED) else [0.0] * 12
        self._shown = [s + (t - s) * (1 - math.exp(-dt / 0.05)) for s, t in zip(self._shown, target)]
        moving = abs(tw - lk.w) > 0.05 or abs(th - lk.h) > 0.05 or abs(tz - lk.zoom) > 0.001
        return moving or any(v > 0.01 for v in self._shown) or self.state in (HOLD, LOCKED, FINALIZING)

    def pill_rect(self, scale: float, canvas_w: int, canvas_h: int) -> tuple[float, float, float, float]:
        lk = self.look
        w, h = lk.w * lk.zoom * scale, lk.h * lk.zoom * scale
        bottom = canvas_h - 2 * scale - (lk.h * (1 - lk.zoom) * scale) / 2
        return (canvas_w - w) / 2, bottom - h, w, h

    def paint(self, c, scale: float, canvas_w: int, canvas_h: int, now: float | None = None) -> None:
        from .gdip import argb  # Windows-only module; imported here so tests of the rest run anywhere

        now = time.monotonic() if now is None else now
        lk = self.look
        x, y, w, h = self.pill_rect(scale, canvas_w, canvas_h)
        u = scale * lk.zoom  # one CSS px at the current zoom
        active = _clamp((lk.h - SIZES[IDLE][1]) / (SIZES[HOLD][1] - SIZES[IDLE][1]))

        # Snap to whole device pixels; Aqua's border is 1 device px idle, 1 CSS px active.
        x, y = round(x), round(y)
        w, h = round(x + w) - x, round(y + h) - y
        bw = round(1 + (scale - 1) * active) if scale >= 1 else 1
        fill = argb(BLACK, 0.75 + 0.25 * active)
        border = argb(_mix(IDLE_BORDER, ACTIVE_BORDER, active), 0.75 + 0.25 * active)
        c.rounded(x + bw, y + bw, w - 2 * bw, h - 2 * bw, h / 2 - bw, fill=fill)
        c.ring(x, y, w, h, h / 2, bw, border)
        if active < 0.3:
            return
        alpha = _clamp((active - 0.3) / 0.7)
        cy = y + h / 2

        # Locked extras fade in as the pill widens from 110 to 160.
        locked = _clamp((lk.w - SIZES[HOLD][0]) / (SIZES[LOCKED][0] - SIZES[HOLD][0]))
        if locked > 0.02:
            a = alpha * locked
            side = SIDE * u
            for dx in (side, w - side):
                c.rect(x + dx - 0.5 * u, y + u, u, h - 2 * u, argb(ACTIVE_BORDER, a))
            bx = x + side / 2
            c.circle(bx, cy, DOT * u, argb(CANCEL_FILL, a))
            arm = 2.6 * u
            for sgn in (1, -1):
                c.line(bx - arm, cy - sgn * arm, bx + arm, cy + sgn * arm, argb(CANCEL_X, a), 1.1 * u)
            sx = x + w - side / 2
            c.circle(sx, cy, DOT * u, argb(STOP_FILL, a))
            sq = 6.5 * u
            c.rounded(sx - sq / 2, cy - sq / 2, sq, sq, 1.5 * u, stroke=argb(STOP_SQUARE, a), stroke_w=u)
            mid_l, mid_r = x + side, x + w - side
        else:
            mid_l, mid_r = x, x + w

        group = DOT + GAP_DOT_BARS + 12 * BAR_PITCH - (BAR_PITCH - BAR_W)
        gx = (mid_l + mid_r) / 2 - group * u / 2 - 1.5 * u
        dot_alpha = alpha
        if self.state == FINALIZING:
            dot_alpha *= 0.7 + 0.3 * (0.5 + 0.5 * math.cos(now * 2 * math.pi * 1.2))
        c.gradient_circle(gx + DOT * u / 2, cy, DOT * u, argb(DOT_LEFT, dot_alpha), argb(DOT_RIGHT, dot_alpha))
        bx0 = gx + (DOT + GAP_DOT_BARS) * u
        for i, level in enumerate(self._shown):
            bh = (BAR_REST + level * (BAR_MAX - BAR_REST)) * u
            bxc = bx0 + (i * BAR_PITCH + BAR_W / 2) * u
            color = argb(_mix(BAR_QUIET, BAR_LOUD, level), alpha)
            half = max(0.0, bh / 2 - BAR_W * u / 2)
            c.line(bxc, cy - half, bxc, cy + half + 0.01, color, BAR_W * u)

    def hit(self, px: float, scale: float, canvas_w: int, canvas_h: int) -> str | None:
        """Which locked-pill button a click at canvas x lands on."""
        if self.state != LOCKED:
            return None
        x, _, w, _ = self.pill_rect(scale, canvas_w, canvas_h)
        side = SIDE * scale
        if x <= px <= x + side:
            return "cancel"
        if x + w - side <= px <= x + w:
            return "stop"
        return None
