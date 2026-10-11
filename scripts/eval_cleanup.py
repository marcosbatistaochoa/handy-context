"""Score the cleanup prompt against the real model on the fixed test sets.

    python scripts/eval_cleanup.py                 # every set
    python scripts/eval_cleanup.py --set cleanup   # one set
    python scripts/eval_cleanup.py --show          # print every answer, not only failures

Each line of tests/eval/<set>.jsonl is one case:
  in        what Handy heard
  has       strings the answer must contain (case-sensitive unless "ci": true)
  not       words or phrases that must be absent (whole words, case-insensitive)
  min_sentences, max_len   optional shape checks
  visible   optional screen text (the Spanish bug came with an English screen)
Edit cases also carry "target" (the text being edited), "selected" (bool)
and "mode" (the expected "edit" or "dictate").
Prints `<set>: N/M passed`, the failures, and the median model time.
"""

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from handy_context.config import load_config  # noqa: E402
from handy_context.context import Context  # noqa: E402
from handy_context.dictionary import Dictionary  # noqa: E402
from handy_context import modes, prompt  # noqa: E402
from handy_context.server import call_upstream  # noqa: E402

SETS = ["cleanup", "edit", "not_edit"]
ROUTED_LAST = "Thanks for the update yesterday."  # --routed: cleanup cases with a last dictation present


def check(case: dict, answer: str, mode: str | None = None) -> list[str]:
    problems = []
    if "mode" in case and mode != case["mode"]:
        problems.append(f"mode {mode!r}, expected {case['mode']!r}")
    hay = answer.lower() if case.get("ci") else answer
    for s in case.get("has", []):
        if (s.lower() if case.get("ci") else s) not in hay:
            problems.append(f"missing {s!r}")
    for s in case.get("not", []):
        if re.search(r"(?<!\w)" + re.escape(s.lower()) + r"(?!\w)", answer.lower()):
            problems.append(f"still has {s!r}")
    if "min_sentences" in case:
        n = len(re.findall(r"[.!?](\s|$)", answer))
        if n < case["min_sentences"]:
            problems.append(f"{n} sentences, wanted {case['min_sentences']}+")
    if "max_len" in case and len(answer) > case["max_len"]:
        problems.append(f"{len(answer)} chars, max {case['max_len']}")
    return problems


ROUTED = False


def run_case(cfg, case: dict, empty: Dictionary) -> tuple[str, str | None, float]:
    """Returns (answer, mode, model ms) the way the helper would produce them."""
    if "target" in case:  # an edit-set case
        ctx = Context(selection=case["target"] if case.get("selected") else "")
        last = None if case.get("selected") else case["target"]
    else:
        ctx, last = Context(visible=case.get("visible", "")), (ROUTED_LAST if ROUTED else None)
    t = time.perf_counter()
    out = modes.decide(case["in"], ctx, empty, last, lambda m: call_upstream(cfg, m, 60))
    ms = (time.perf_counter() - t) * 1000
    mode = "dictate" if out.mode == "dictate" else "edit"
    return out.text, mode, ms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=SETS)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--routed", action="store_true", help="run cleanup cases with a last dictation present")
    ap.add_argument("--pace", type=float, default=0.0,
                    help="seconds between cases; a cloud free plan rate-limits back-to-back requests")
    args = ap.parse_args()
    global ROUTED
    ROUTED = args.routed
    cfg = load_config()
    empty = Dictionary([], {})
    print(f"model: {cfg.model}")
    call_upstream(cfg, prompt.build_messages("warm up", Context(), empty), 120)  # load the model first

    times, ok_all = [], True
    for name in [args.set] if args.set else SETS:
        path = ROOT / "tests" / "eval" / f"{name}.jsonl"
        if not path.exists():
            continue
        cases = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        passed = 0
        for case in cases:
            time.sleep(args.pace)
            try:
                answer, mode, ms = run_case(cfg, case, empty)
            except Exception as exc:  # a crash is a failure, not the end of the run
                answer, mode, ms = f"<error {exc!r}>", None, 0.0
            times.append(ms)
            case["_mode"] = mode
            problems = check(case, answer, mode)
            passed += not problems
            if problems or args.show:
                mark = "FAIL" if problems else "ok  "
                print(f"  {mark} {case['id']}: {answer!r}" + (f"  <- {'; '.join(problems)}" if problems else ""))
        print(f"{name}{' (routed)' if ROUTED and name == 'cleanup' else ''}: {passed}/{len(cases)} passed")
        if name == "not_edit":
            false_edits = sum(1 for c in cases if c.get("_mode") == "edit")
            print(f"false edits: {false_edits}/{len(cases)}")
            ok_all = ok_all and false_edits == 0
        else:
            ok_all = ok_all and passed >= 0.9 * len(cases)
    if times:
        print(f"median model ms: {statistics.median(times):.0f}  (max {max(times):.0f})")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
