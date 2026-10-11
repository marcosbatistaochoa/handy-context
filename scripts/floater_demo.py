"""Show the floater in one state, with fake levels, for side-by-side screenshots.

    python scripts/floater_demo.py --state hold --seconds 4
    python scripts/floater_demo.py --cycle      # idle, hold, locked, finalizing, idle

No keyboard hook, no Handy, no microphone.
"""

import argparse
import math
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from handy_context import floater as fl  # noqa: E402
from handy_context.winui import App  # noqa: E402


class FakeMic:
    def __init__(self) -> None:
        self.t0 = time.monotonic()

    @property
    def levels(self):
        t = time.monotonic() - self.t0
        return [max(0.0, 0.55 * math.sin(t * 7 + i * 0.9) * math.exp(-((i - 5.5) / 3.2) ** 2)) for i in range(12)]

    def start(self):
        pass

    def stop(self):
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="hold", choices=list(fl.SIZES))
    ap.add_argument("--seconds", type=float, default=4)
    ap.add_argument("--cycle", action="store_true")
    ap.add_argument("--dx", type=int, default=0, help="shift right by this many device px")
    args = ap.parse_args()

    app = App(handy_exe="", right_alt=False, demo=True)
    app.mic = FakeMic()
    app.dx = args.dx
    plan = [(fl.IDLE, 1.5), (fl.HOLD, 2.5), (fl.LOCKED, 2.5), (fl.FINALIZING, 2), (fl.IDLE, 1.5)] if args.cycle \
        else [(args.state, args.seconds)]

    def drive():
        time.sleep(0.3)
        for state, secs in plan:
            app.floater.set_state(state)
            app.post_done()  # wakes the loop to animate
            time.sleep(secs)
        import ctypes
        ctypes.windll.user32.PostMessageW(app.hwnd, 0x0012, 0, 0)  # WM_QUIT

    threading.Thread(target=drive, daemon=True).start()
    app.run()


if __name__ == "__main__":
    main()
