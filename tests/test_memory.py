from handy_context.context import Context
from handy_context.memory import Memory


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def ctx(before="", **kw):
    base = dict(app="notepad.exe", title="notes.txt", element_id="42", before_caret=before)
    base.update(kw)
    return Context(**base)


def remembered(text="Call Kate tomorrow.", **kw):
    clock = Clock()
    m = Memory(60, clock=clock)
    m.remember(text, ctx(**kw))
    return m, clock


def test_match_right_before_caret():
    m, _ = remembered()
    assert m.last_before_caret(ctx("Hi. Call Kate tomorrow.")) == ("Call Kate tomorrow.", 19)


def test_trailing_space_is_selected_too():
    m, _ = remembered()
    assert m.last_before_caret(ctx("Hi. Call Kate tomorrow. ")) == ("Call Kate tomorrow.", 20)


def test_crlf_counts_as_one_press():
    m, _ = remembered("one\r\ntwo")
    assert m.last_before_caret(ctx("x one\r\ntwo")) == ("one\ntwo", 7)


def test_stale_paste_is_ignored():
    m, clock = remembered()
    clock.t += 61
    assert m.last_before_caret(ctx("Call Kate tomorrow.")) is None


def test_other_element_is_ignored():
    m, _ = remembered()
    assert m.last_before_caret(ctx("Call Kate tomorrow.", element_id="7")) is None


def test_other_app_is_ignored():
    m, _ = remembered()
    assert m.last_before_caret(ctx("Call Kate tomorrow.", app="word.exe")) is None


def test_title_change_ignored_when_element_known():
    m, _ = remembered()  # Notepad marks the title dirty after a paste
    assert m.last_before_caret(ctx("Call Kate tomorrow.", title="*notes.txt")) is not None


def test_title_checked_when_no_element_id():
    m, _ = remembered(element_id="")
    assert m.last_before_caret(ctx("Call Kate tomorrow.", element_id="", title="other")) is None
    assert m.last_before_caret(ctx("Call Kate tomorrow.", element_id="")) is not None


def test_selection_present_means_no_last():
    m, _ = remembered()
    assert m.last_before_caret(ctx("Call Kate tomorrow.", selection="Kate")) is None


def test_text_typed_after_paste_breaks_match():
    m, _ = remembered()
    assert m.last_before_caret(ctx("Call Kate tomorrow. And")) is None
