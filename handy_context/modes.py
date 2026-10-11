"""Decides what one dictation does: type new text, edit the selection, or edit the last dictation.

Pure logic: the model is reached through `ask(messages) -> str`, which may
raise. The server wraps it with the time budget; the eval script calls it
directly.

Safety: an edit that fails answers with empty text. Handy pastes nothing for
an empty answer (`actions.rs`, `final_text.is_empty()`), so the selected or
previous text is left exactly as it was, never replaced by the spoken command.
"""

import re
from dataclasses import dataclass
from typing import Callable

from .context import Context
from .dictionary import Dictionary
from . import prompt

EDIT_MAX_CHARS = 6000  # Aqua's Edit Mode limit; a longer selection is left alone

# Words that point back at the text just written. An edit of the last
# dictation must use one of these, or name a word that is in that text;
# otherwise it is dictation and the model is not even asked.
_POINTER = re.compile(
    r"\b(that|it|this|these|those|instead|everything|the whole thing|the (end|beginning|start)"
    r"|the (last|first|previous|next|second) (word|words|sentence|sentences|line|lines|part|bit|paragraph)"
    r"|the (word|name|comma|period|full stop|spelling))\b",
    re.IGNORECASE,
)
_STOPWORDS = set(
    "a an and are as at be but by for from has have i in is of on or so the to was we were with you your my our".split()
)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in _STOPWORDS}


# An edit command is an order: it starts with one of these verbs, after an
# optional lead-in ("please", "can you", "now").
_EDIT_VERBS = set(
    "add append insert put remove delete drop cut scratch erase change replace swap switch use make "
    "capitalize uppercase lowercase spell fix correct rewrite rephrase reword shorten expand end start "
    "begin turn translate move undo bold".split()
)
_LEAD_IN = re.compile(r"^(?:(?:um|uh|okay|ok|so|now|please|actually|wait|oh|can you|could you|would you)[\s,]+)+")
_NOT_IMPERATIVE = set("is was are were will would can could has had did does should might".split())
_SPELLED = re.compile(r"\b(?:[a-z]\s+){2,}[a-z]\b", re.IGNORECASE)  # "k a t e"


def _is_order(instruction: str) -> bool:
    text = _LEAD_IN.sub("", instruction.strip().lower())
    words = re.findall(r"[a-z']+", text)
    if not words or words[0] not in _EDIT_VERBS:
        return False
    return len(words) < 2 or words[1] not in _NOT_IMPERATIVE  # "change is hard" is a statement


def could_be_edit(instruction: str, last: str) -> bool:
    """Cheap gate before the model is asked: an order that points at the last
    dictation (a pointer word, or a word that is in it), or a spelled-out word."""
    if _SPELLED.search(instruction):
        return True
    if not _is_order(instruction):
        return False
    return bool(_POINTER.search(instruction)) or bool(_words(instruction) & _words(last))


@dataclass
class Outcome:
    mode: str  # "dictate" | "edit_selection" | "edit_last"
    text: str  # what Handy should paste ("" = paste nothing)
    target: str = ""  # the text an edit replaces
    fallback: str = ""  # why the safe answer was used, if it was
    route: str = ""  # with a last dictation present: why this was or was not an edit (for the log)


def _valid_edit(answer: str, target: str, instruction: str) -> str:
    """The reason an edit answer is unusable, or ''."""
    if not answer.strip():
        return "empty answer"
    if len(answer) > 3 * len(target) + len(instruction) + 200:
        return "answer too long"
    return ""


def fix_tail(answer: str, target: str) -> str:
    """The model appends words after the target's closing period ("Apples. please").
    Move the period to the end: "Apples, please." for a 1-2 word tail, else a space."""
    t = target.rstrip()
    if not t or t[-1] not in ".!?":
        return answer
    if t[-1] in "!?" and answer.endswith(".") and answer.startswith(t[:-1]) and answer[len(t) - 1:len(t)] in (",", " "):
        return answer[:-1] + t[-1]  # "Can you send it?" + please -> "..., please." loses the question mark
    if not answer.startswith(t):
        return answer
    tail = answer[len(t):].strip()
    if not tail or not tail[0].islower() or re.search(r"[.!?]\s", tail):
        return answer
    tail = tail.rstrip(".!? ")
    join = ", " if len(tail.split()) <= 2 else " "
    return t[:-1].rstrip(",;: ") + join + tail + t[-1]


def _edit(instruction: str, target: str, ctx: Context, dictionary: Dictionary, ask: Callable, mode: str) -> Outcome:
    try:
        answer = prompt.clean_output(ask(prompt.build_edit_messages(instruction, target, ctx, dictionary)))
    except Exception as exc:
        return Outcome(mode, "", target, f"model: {exc!r}"[:200])
    bad = _valid_edit(answer, target, instruction)
    if bad:
        return Outcome(mode, "", target, f"model: {bad}")
    return Outcome(mode, fix_tail(answer, target), target)


# Short function words that only one of these languages uses a lot. Enough to
# tell which language a dictation is in, not to translate anything.
_LANG_WORDS = {
    "en": set("the and is are was you that this with have for not what why it's i'm don't of to i my we will".split()),
    "es": set("el la los las que es por qué una uno del con para pero como está estás muy yo tú me se lo"
              " y mi mis al tengo tiene hay pues bueno también ya cuando después hoy mañana".split()),
    "pt": set("o os as que é não uma um do da dos com para mas como você está muito eu e meu minha".split()),
    "fr": set("le les et est que une un des du avec pour mais comme vous je pas très c'est mon ma".split()),
}
_LANG_NAMES = {"en": "English", "es": "Spanish", "pt": "Portuguese", "fr": "French"}


def language(text: str) -> str:
    """The language most of `text`'s function words belong to, or '' when unsure."""
    words = re.findall(r"[\w'’]+", text.lower())
    hits = {lang: sum(w in s for w in words) for lang, s in _LANG_WORDS.items()}
    best = max(hits, key=hits.get)
    ranked = sorted(hits.values(), reverse=True)
    if ranked[0] < 2 or ranked[0] < 2 * ranked[1]:
        return ""
    return best


def _clean(transcript: str, messages: list[dict], ask: Callable) -> tuple[str, str]:
    """(answer, why it is unusable or '')."""
    try:
        answer = prompt.clean_output(ask(messages))
    except Exception as exc:
        return "", f"model: {exc!r}"[:200]
    if not answer:
        return "", "model: empty answer"
    if len(answer) > 3 * len(transcript) + 200:
        # Far longer than what was said: the model answered instead of cleaning.
        return "", "model: answer too long"
    heard, wrote = language(transcript), language(answer)
    if heard and wrote and heard != wrote:
        return "", f"model: translated {heard} to {wrote}"
    return answer, ""


def _dictate(transcript: str, ctx: Context, dictionary: Dictionary, ask: Callable) -> Outcome:
    messages = prompt.build_messages(transcript, ctx, dictionary)
    answer, bad = _clean(transcript, messages, ask)
    if bad.startswith("model: translated"):
        # The model translated (Spanish speech, English screen). Never wanted:
        # ask once more, naming the language, before giving up on the cleanup.
        name = _LANG_NAMES[language(transcript)]
        messages[0] = {**messages[0], "content": messages[0]["content"] + f"\n\nThe speaker spoke {name}. Write in {name}."}
        answer, bad2 = _clean(transcript, messages, ask)
        bad = f"{bad}; retry: {bad2}" if bad2 else ""
    if bad:
        return Outcome("dictate", transcript, fallback=bad)
    return Outcome("dictate", answer)


def decide(transcript: str, ctx: Context, dictionary: Dictionary, last: str | None, ask: Callable) -> Outcome:
    """`last` is the previous dictation when it is still right before the cursor, else None."""
    if ctx.selection:
        if ctx.selection_truncated or len(ctx.selection) > EDIT_MAX_CHARS:
            return Outcome("edit_selection", "", ctx.selection, "selection too long to edit")
        return _edit(transcript, ctx.selection, ctx, dictionary, ask, "edit_selection")
    if ctx.error and _is_order(transcript):
        # The capture failed, so a selection may be there unseen; pasting the
        # spoken order would replace it. Paste nothing instead.
        return Outcome("edit_selection", "", "", "capture failed on an order")
    route = ""
    if last and could_be_edit(transcript, last):
        try:
            kind = prompt.parse_classify(ask(prompt.build_classify_messages(transcript, last)))
        except Exception as exc:
            kind, route = None, f"classify failed: {exc!r}"[:120]  # unsure means dictation
        if kind == "edit":
            return _edit(transcript, last, ctx, dictionary, ask, "edit_last")
        route = route or f"classified {kind or 'unsure'}"
    elif last:
        route = "gate: not an order about the last text"
    out = _dictate(transcript, ctx, dictionary, ask)
    out.route = route
    return out
