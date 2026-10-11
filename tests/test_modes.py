from handy_context import modes
from handy_context.context import Context
from handy_context.dictionary import Dictionary

LAST = "Send the report to Kate on Friday."


def test_gate_accepts_orders_that_point_at_the_last_text():
    assert modes.could_be_edit("change that to Monday", LAST)
    assert modes.could_be_edit("please replace Kate with Kat", LAST)  # shared word
    assert modes.could_be_edit("k a t", LAST)  # spelled out


def test_gate_rejects_plain_dictation():
    assert not modes.could_be_edit("and then we went home", LAST)
    assert not modes.could_be_edit("change is hard", LAST)  # a statement, not an order
    assert not modes.could_be_edit("add milk to the list", LAST)  # an order, but not about LAST


def asker(*answers):
    queue = list(answers)

    def ask(messages):
        a = queue.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    return ask


def test_edit_selection_failure_pastes_nothing():
    out = modes.decide("make it shorter", Context(selection="Long text."), Dictionary(), None, asker(TimeoutError()))
    assert (out.mode, out.text) == ("edit_selection", "")
    assert out.fallback


def test_edit_selection_empty_answer_pastes_nothing():
    out = modes.decide("make it shorter", Context(selection="Long text."), Dictionary(), None, asker("  "))
    assert (out.mode, out.text) == ("edit_selection", "")


def test_truncated_selection_pastes_nothing_without_asking():
    ctx = Context(selection="x" * 100, selection_truncated=True)
    out = modes.decide("fix it", ctx, Dictionary(), None, asker())
    assert (out.mode, out.text) == ("edit_selection", "")


def test_edit_last_when_classifier_says_edit():
    out = modes.decide("change Friday to Monday", Context(), Dictionary(), LAST,
                       asker("EDIT", "Send the report to Kate on Monday."))
    assert (out.mode, out.text, out.target) == ("edit_last", "Send the report to Kate on Monday.", LAST)


def test_words_after_the_period_move_inside_it():
    assert modes.fix_tail("Apples. please", "Apples.") == "Apples, please."
    assert modes.fix_tail("Send the report to Kate on Friday. please.", LAST) == "Send the report to Kate on Friday, please."
    assert modes.fix_tail("Is it done? thank you", "Is it done?") == "Is it done, thank you?"
    assert modes.fix_tail("Apples. and pears too", "Apples.") == "Apples and pears too."
    assert modes.fix_tail("Can you send me the deck, please.", "Can you send me the deck?") == "Can you send me the deck, please?"
    assert modes.fix_tail("Can you send me the deck.", "Can you send me the deck?") == "Can you send me the deck."  # asked for


def test_fix_tail_leaves_real_edits_alone():
    assert modes.fix_tail("Apples. Pears are next.", "Apples.") == "Apples. Pears are next."  # a new sentence
    assert modes.fix_tail("Apples, please.", "Apples.") == "Apples, please."  # already right
    assert modes.fix_tail("Send it on Monday.", LAST) == "Send it on Monday."  # not an append
    assert modes.fix_tail("Apples please", "Apples") == "Apples please"  # no period to move


def test_edit_last_moves_please_inside_the_period():
    out = modes.decide("add please at the end", Context(), Dictionary(), LAST,
                       asker("EDIT", "Send the report to Kate on Friday. please"))
    assert out.text == "Send the report to Kate on Friday, please."


def test_edit_last_failure_pastes_nothing():
    out = modes.decide("change Friday to Monday", Context(), Dictionary(), LAST, asker("EDIT", RuntimeError("down")))
    assert (out.mode, out.text) == ("edit_last", "")


def test_unsure_classifier_means_dictation():
    out = modes.decide("change Friday to Monday", Context(), Dictionary(), LAST,
                       asker("maybe", "Change Friday to Monday."))
    assert (out.mode, out.text) == ("dictate", "Change Friday to Monday.")


def test_failed_capture_with_an_order_pastes_nothing():
    # A selection may be there unseen; the spoken order must not replace it.
    out = modes.decide("make this more formal", Context(error="focused: timed out"), Dictionary(), None, asker())
    assert out.text == ""


def test_failed_capture_still_dictates_plain_speech():
    out = modes.decide("we went home early", Context(error="timed out"), Dictionary(), None, asker("We went home early."))
    assert (out.mode, out.text) == ("dictate", "We went home early.")


def test_edit_answer_far_too_long_pastes_nothing():
    out = modes.decide("fix it", Context(selection="Hi."), Dictionary(), None, asker("x" * 500))
    assert (out.mode, out.text) == ("edit_selection", "")


def test_dictation_failure_keeps_raw_transcript():
    out = modes.decide("hello there", Context(), Dictionary(), None, asker(TimeoutError()))
    assert (out.mode, out.text) == ("dictate", "hello there")


SPANISH = "¿Por qué me estás traduciendo en inglés que es extraño?"  # the user's dictation, 2026-10-07


def test_translated_answer_falls_back_to_what_was_said():
    en = "Why are you translating this into English? It's strange."
    out = modes.decide(SPANISH, Context(), Dictionary(), None, asker(en, en))
    assert out.text == SPANISH
    assert out.fallback == "model: translated es to en; retry: model: translated es to en"


def test_translated_answer_is_retried_in_the_spoken_language():
    heard = "eh bueno mañana tengo que llamar a mi mamá y y después ir al supermercado"
    es = "Bueno, mañana tengo que llamar a mi mamá y después ir al supermercado."
    out = modes.decide(heard, Context(), Dictionary(), None,
                       asker("Eh, bueno. Tomorrow I have to call my mom and then go to the supermarket.", es))
    assert (out.text, out.fallback) == (es, "")


def test_cleanup_in_the_same_language_goes_through():
    es = "Por qué me estás traduciendo al inglés? Es extraño."
    assert modes.decide(SPANISH, Context(), Dictionary(), None, asker(es)).text == es
    en = "Okay, it's now translating my Spanish into English. I don't want that."
    heard = "okay well now it's started to translate my spanish into english which i don't want"
    assert modes.decide(heard, Context(), Dictionary(), None, asker(en)).text == en


def test_language_is_unsure_on_short_or_mixed_text():
    assert modes.language("Grace Hopper") == ""
    assert modes.language("ok") == ""
    assert modes.language(SPANISH) == "es"
