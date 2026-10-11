"""Learns from the user's hand fixes to what the helper pasted.

At each dictation the helper re-reads the field it pasted into last time. If
the user changed a word or two of that paste by hand, the change is logged to
`corrections.jsonl`; the second time the same change is seen, it goes into
`dictionary.txt`, so the next dictation gets it right. Only the heard and
written words are logged, never the text around them.

Strict on purpose, because a wrong rule would change every later dictation:
same field only; at least half the paste still recognisable; one-for-one
swaps of one to three words that look alike, seen twice within 30 days;
never deletions, insertions, rewrites, swaps of everyday words (there/their,
to/too), or of numbers, days and months (a changed plan, not a mishearing).
"""

import difflib
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .context import Context
from .memory import normalize

# Everyday words: a swap involving one of these is grammar or style, not a
# name or a pronunciation, and must never become a global replacement.
COMMON = set(
    """a an the and or but if so to too two for of in on at by with from as is are was were be been am
    i you he she it we they me him her us them my your his its our their there they're it's you're
    this that these those then than here where when what who how why which not no yes do does did
    have has had can could will would should may might must one won new knew know no now our are
    hour right write rite see sea be bee by buy bye week weak hear here""".split()
)
# Dates, times and numbers change because plans change, not because a word
# was misheard: "Friday" to "Monday" twice must never rewrite every Friday.
_FACTS = re.compile(
    r"\d|\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow|yesterday|tonight"
    r"|january|february|march|april|may|june|july|august|september|october|november|december"
    r"|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty"
    r"|hundred|thousand|million|am|pm|noon|midnight)\b",
    re.IGNORECASE,
)
MAX_SWAP_WORDS = 3
MIN_SIMILARITY = 0.4
SIGHTING_MAX_AGE_S = 30 * 86400  # two fixes count together only within 30 days


@dataclass
class _Pending:
    text: str
    app: str
    title: str
    element_id: str
    at: float


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w'’-]+", text)


def find_swaps(pasted: str, field: str) -> list[tuple[str, str]]:
    """(heard, written) pairs: words of `pasted` the user replaced in `field`.

    Empty when the paste cannot be found in the field (deleted, rewritten,
    another field), or when the changes are not clean one-for-one swaps.
    """
    p, f = _tokens(pasted), _tokens(field)
    if not p or not f:
        return []
    sm = difflib.SequenceMatcher(None, [w.lower() for w in p], [w.lower() for w in f], autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    if not blocks or sum(b.size for b in blocks) * 2 < len(p):
        return []  # less than half the paste is still there
    start, end = blocks[0].b - blocks[0].a, blocks[-1].b + blocks[-1].size + (len(p) - blocks[-1].a - blocks[-1].size)
    region = f[max(0, start):max(0, end)]
    swaps = []
    for op, a0, a1, b0, b1 in difflib.SequenceMatcher(None, p, region, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        if op != "replace":
            return []  # a deletion or insertion: an edit of meaning, not a mishearing
        heard, written = " ".join(p[a0:a1]), " ".join(region[b0:b1])
        if not (1 <= a1 - a0 <= MAX_SWAP_WORDS and 1 <= b1 - b0 <= MAX_SWAP_WORDS):
            return []
        if heard.lower() in COMMON or written.lower() in COMMON or _FACTS.search(heard) or _FACTS.search(written):
            continue
        if heard != written and difflib.SequenceMatcher(None, heard.lower(), written.lower()).ratio() >= MIN_SIMILARITY:
            swaps.append((heard, written))
    return swaps


class Learner:
    def __init__(self, dictionary_path: Path, log_dir: Path, clock=time.time):
        self.dictionary_path = Path(dictionary_path)
        self.log_path = Path(log_dir) / "corrections.jsonl"
        self.clock = clock
        self._pending: _Pending | None = None
        self._lock = threading.Lock()

    def pasted(self, text: str, ctx: Context) -> None:
        """The helper just had `text` pasted into the focused field (its own edits included)."""
        with self._lock:
            self._pending = _Pending(normalize(text), ctx.app, ctx.title, ctx.element_id, self.clock())

    def check(self, ctx: Context) -> list[str]:
        """Compare the last paste with the field now. Returns dictionary lines added."""
        with self._lock:
            pending, self._pending = self._pending, None
        if pending is None or not pending.element_id or pending.element_id != ctx.element_id:
            return []  # another field, or one we cannot identify: learn nothing
        if pending.app != ctx.app:
            return []
        field = normalize(ctx.near_cursor)
        if not field or pending.text in field:
            return []
        added = []
        for heard, written in find_swaps(pending.text, field):
            if self._log_and_count(heard, written) == 2:
                line = self._add_to_dictionary(heard, written)
                if line:
                    added.append(line)
        return added

    def _log_and_count(self, heard: str, written: str) -> int:
        count = 1
        now = self.clock()
        if self.log_path.exists():
            for raw in self.log_path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(raw)
                    at = time.mktime(time.strptime(row["time"], "%Y-%m-%dT%H:%M:%S"))
                except (ValueError, KeyError, TypeError):
                    continue
                if now - at > SIGHTING_MAX_AGE_S:
                    continue  # an old sighting: the second fix must come within the window
                if row.get("heard", "").lower() == heard.lower() and row.get("written") == written:
                    count += 1
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as f:
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
            row = {"time": stamp, "heard": heard, "written": written, "seen": count}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return count

    def _add_to_dictionary(self, heard: str, written: str) -> str:
        """Append the rule unless the dictionary already has it.

        Case-only fixes and one-word fixes become a preferred word, never a
        hard replacement: "air => AYRE" would rewrite every "air" (replacements
        ignore case and context); the model sees the word and uses context."""
        if heard.lower() == written.lower() or len(heard.split()) == 1:
            line = written
        else:
            line = f"{heard.lower()} => {written}"
        existing = self.dictionary_path.read_text(encoding="utf-8") if self.dictionary_path.exists() else ""
        if any(l.strip().lower() == line.lower() for l in existing.splitlines()):
            return ""
        stamp = time.strftime("%Y-%m-%d")
        with self.dictionary_path.open("a", encoding="utf-8", newline="\n") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"# learned {stamp} from your fixes\n{line}\n")
        return line
