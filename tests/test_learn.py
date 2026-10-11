import json

import pytest

from handy_context.context import Context
from handy_context.learn import Learner, find_swaps

PASTE = "Please send the slides to Marry Gold before the meeting."
FIXED = "Please send the slides to Marigold before the meeting."


def field(text, **kw):
    base = dict(app="notepad.exe", title="notes.txt", element_id="42", near_cursor=text)
    base.update(kw)
    return Context(**base)


@pytest.fixture
def learner(tmp_path):
    return Learner(tmp_path / "dictionary.txt", tmp_path / "logs")


def fix_once(learner, fixed=FIXED, **kw):
    learner.pasted(PASTE, field(""))
    return learner.check(field(fixed, **kw))


def test_swap_learned_only_on_second_sighting(learner):
    assert fix_once(learner) == []
    assert not learner.dictionary_path.exists()
    assert fix_once(learner) == ["marry gold => Marigold"]
    assert "marry gold => Marigold" in learner.dictionary_path.read_text(encoding="utf-8")
    rows = [json.loads(l) for l in learner.log_path.read_text(encoding="utf-8").splitlines()]
    assert [r["seen"] for r in rows] == [1, 2]
    assert set(rows[0]) == {"time", "heard", "written", "seen"}  # no surrounding text logged


def test_rule_not_added_twice(learner):
    fix_once(learner), fix_once(learner)
    assert fix_once(learner) == []


def test_one_word_fix_becomes_a_preferred_word_not_a_replacement(learner):
    paste, fixed = "I work at AIR on the data team.", "I work at AYRE on the data team."
    for _ in range(2):
        learner.pasted(paste, field(""))
        added = learner.check(field(fixed))
    assert added == ["AYRE"]
    assert "=>" not in learner.dictionary_path.read_text(encoding="utf-8").split("from your fixes")[-1]


def test_title_change_does_not_block_learning(learner):
    fix_once(learner, title="*notes.txt")
    assert fix_once(learner, title="*notes.txt") == ["marry gold => Marigold"]


@pytest.mark.parametrize("kw", [
    {"element_id": "7"},  # focus moved to another field
    {"element_id": ""},  # field cannot be identified
    {"app": "word.exe"},
])
def test_other_field_learns_nothing(learner, kw):
    fix_once(learner, **kw)
    assert fix_once(learner, **kw) == []


def test_unchanged_paste_learns_nothing(learner):
    fix_once(learner, fixed="Intro. " + PASTE)
    assert fix_once(learner, fixed="Intro. " + PASTE) == []


def test_deleted_paste_learns_nothing():
    assert find_swaps(PASTE, "Something else entirely was written here.") == []


def test_insertion_only_learns_nothing():
    assert find_swaps(PASTE, "Please send the new slides to Marry Gold before the meeting.") == []


def test_deletion_learns_nothing():
    assert find_swaps(PASTE, "Please send the slides to Marry Gold.") == []


def test_common_word_swap_learns_nothing():
    assert find_swaps("I left it over there.", "I left it over their.") == []


@pytest.mark.parametrize("pasted, fixed", [
    ("Meet on Friday at noon in room four.", "Meet on Monday at noon in room four."),
    ("Meet on Friday at 10 in room 4.", "Meet on Friday at 11 in room 4."),
    ("The launch is in October for Batty.", "The launch is in November for Batty."),
])
def test_dates_and_numbers_learn_nothing(pasted, fixed):
    assert find_swaps(pasted, fixed) == []


def test_sightings_older_than_30_days_do_not_count(tmp_path):
    clock = {"t": 1_800_000_000.0}
    learner = Learner(tmp_path / "dictionary.txt", tmp_path / "logs", clock=lambda: clock["t"])
    assert fix_once(learner) == []
    clock["t"] += 31 * 86400
    assert fix_once(learner) == []  # counts as a first sighting again
    clock["t"] += 86400
    assert fix_once(learner) == ["marry gold => Marigold"]


def test_only_one_check_per_paste(learner):
    learner.pasted(PASTE, field(""))
    learner.check(field(FIXED))
    assert learner.check(field(FIXED)) == []
    assert len(learner.log_path.read_text(encoding="utf-8").splitlines()) == 1
