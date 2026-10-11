from handy_context.keys import CANCEL, HOLD, IDLE, LOCKED, PRESS, RELEASE, RightAlt


def test_hold_talks_while_held():
    k = RightAlt()
    r = k.ralt(True)
    assert r.swallow and r.actions == [PRESS] and k.state == HOLD
    assert k.ralt(True).actions == []  # auto-repeat
    r = k.ralt(False)
    assert r.swallow and r.actions == [RELEASE] and k.state == IDLE


def test_ralt_space_locks_until_next_ralt():
    k = RightAlt()
    k.ralt(True)
    r = k.space(True)
    assert r.swallow and k.state == LOCKED
    assert k.space(False).swallow
    r = k.ralt(False)
    assert r.swallow and r.actions == [] and k.state == LOCKED
    assert k.space(True).swallow is False  # normal typing passes while locked
    r = k.ralt(True)
    assert r.swallow and r.actions == [RELEASE] and k.state == IDLE
    r = k.ralt(False)
    assert r.swallow and r.actions == [] and k.state == IDLE


def test_escape_cancels_and_passes_through():
    for lock in (False, True):
        k = RightAlt()
        k.ralt(True)
        if lock:
            k.space(True)
            k.space(False)
            k.ralt(False)
        r = k.escape(True)
        assert r.actions == [CANCEL] and not r.swallow and k.state == IDLE


def test_combo_with_other_key_cancels():
    k = RightAlt()
    k.ralt(True)
    r = k.other(True)
    assert r.actions == [CANCEL] and not r.swallow and k.state == IDLE
    assert k.ralt(False).actions == []  # the release after a cancel does nothing


def test_space_outside_recording_is_untouched():
    k = RightAlt()
    assert not k.space(True).swallow and not k.space(False).swallow
    assert k.ralt(False).swallow is False  # an up we never saw go down


def test_floater_buttons():
    k = RightAlt()
    assert k.click_stop() == []
    k.ralt(True)
    k.space(True)
    k.space(False)
    k.ralt(False)
    assert k.click_stop() == [RELEASE] and k.state == IDLE
    k.ralt(True)
    k.space(True)
    assert k.click_cancel() == [CANCEL] and k.state == IDLE
