"""One normalisation for Spider-value checks, shared by the hash-list generator and the
scan, so a value and its mention in text always normalise to the same string.

normalise("'Mercedes-Benz'") == "mercedes benz": lowercase, every run of characters
that is not a letter or digit becomes one space (quotes, backticks, brackets, hyphens,
dots), and the ends are trimmed.
"""

from __future__ import annotations

import hashlib
import re

_SEPARATORS = re.compile(r"[\W_]+", re.UNICODE)


def normalise(text: str) -> str:
    return _SEPARATORS.sub(" ", text.lower()).strip()


def digest(text: str) -> str:
    return hashlib.sha256(normalise(text).encode()).hexdigest()


def is_checkable(value: str) -> bool:
    """Very short values and plain numbers would match ordinary text; they are skipped."""
    norm = normalise(value)
    return len(norm) >= 3 and not norm.replace(" ", "").isdigit()


def ngrams(text: str, longest: int) -> set[str]:
    words = normalise(text).split()
    grams: set[str] = set()
    for n in range(1, longest + 1):
        for i in range(len(words) - n + 1):
            grams.add(" ".join(words[i : i + n]))
    return grams
