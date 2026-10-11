"""Print what the helper would read from the screen.

    python scripts/show_context.py --delay 3    # then click into any window within 3 seconds
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from handy_context.config import load_config  # noqa: E402
from handy_context.context import capture, warm_up  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--delay", type=float, default=3)
ap.add_argument("--repeat", type=int, default=1, help="captures to print, to see warm timings")
args = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8")  # app icons are private-use characters a cp1252 console cannot print
cfg = load_config()
error = warm_up()
if error:
    print(f"warm-up: {error}", file=sys.stderr)
time.sleep(args.delay)
for _ in range(args.repeat):
    print(json.dumps(capture(6000, cfg.context_budget_ms, cfg.context_max_chars, cfg.visible_max_chars).__dict__, indent=2, ensure_ascii=False))
