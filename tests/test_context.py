import time

from handy_context.context import _trim_around, capture


def test_trim_keeps_text_before_caret():
    text = "a" * 100 + "CARET" + "b" * 100
    out = _trim_around(text, 105, 40)
    assert len(out) == 40 and "a" in out and out.index("b") >= 25


def test_trim_short_text_unchanged():
    assert _trim_around("short", 2, 100) == "short"


def test_capture_never_raises_and_respects_budget():
    t0 = time.perf_counter()
    ctx = capture(max_chars=500, budget_ms=150)
    assert time.perf_counter() - t0 < 0.5
    assert len(ctx.near_cursor) <= 500 and len(ctx.visible) <= 500
