"""The personal dictionary: words to prefer, and fixed heard => written replacements."""

import re
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATE = """\
# Your dictionary for Handy dictation. One entry per line.
#
#   Kubernetes                 a word or name to spell exactly like this
#   mari gold => Marigold    whenever you hear the left side, write the right side
#
# Lines starting with # are ignored. Changes apply on the next dictation.
"""


@dataclass
class Dictionary:
    words: list[str] = field(default_factory=list)
    replacements: list[tuple[str, str]] = field(default_factory=list)

    @classmethod
    def parse(cls, text: str) -> "Dictionary":
        d = cls()
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=>" in line:
                heard, written = (part.strip() for part in line.split("=>", 1))
                if heard and written:
                    d.replacements.append((heard, written))
                    if written not in d.words:
                        d.words.append(written)
            elif line not in d.words:
                d.words.append(line)
        return d

    @classmethod
    def load(cls, path: Path) -> "Dictionary":
        """Read the file, creating it from the template the first time."""
        try:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(TEMPLATE, encoding="utf-8", newline="\n")
            return cls.parse(path.read_text(encoding="utf-8-sig"))
        except OSError:
            return cls()

    def apply(self, text: str) -> str:
        """Apply heard => written replacements as whole words, ignoring case.

        A heard side in capitals ("AIR => AYRE") matches capitals only, so the
        acronym is fixed and the everyday word "air" is left alone."""
        # Longest first, so "new york city" wins over "new york".
        for heard, written in sorted(self.replacements, key=lambda r: -len(r[0])):
            words = [re.escape(w) for w in heard.split()]
            pattern = r"(?<!\w)" + r"[\s\-]+".join(words) + r"(?!\w)"
            flags = 0 if heard.isupper() else re.IGNORECASE
            text = re.sub(pattern, lambda _m, w=written: w, text, flags=flags)
        return text
