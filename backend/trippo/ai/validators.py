"""Guard rails on model output.

The product rule is that Trippo never invents a place. That has to be enforced, not
trusted: every proper noun a model produces is checked against the facts it was given, and
anything unmatched is rejected.

A rejection is never fatal. The caller falls back to the deterministic result.
"""

from __future__ import annotations

import re

#: Words that look like proper nouns but are ordinary prose.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "from",
        "by", "with", "over", "under", "along", "through", "into", "up", "down",
        "day", "morning", "afternoon", "evening", "night", "today", "tomorrow",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
        "north", "south", "east", "west", "we", "i", "our", "it", "there", "then",
    }
)

#: Capitalised in a title, but describing a kind of place rather than naming one. A group
#: called "Titanic Quarter" is grounded if "Titanic" is; "Quarter" is not an invention.
_GEOGRAPHIC = frozenset(
    {
        "quarter", "district", "centre", "center", "town", "city", "village",
        "old", "new", "upper", "lower", "great", "little",
        "harbour", "harbor", "docks", "dock", "port", "quay", "waterfront",
        "bay", "beach", "coast", "cliffs", "peninsula", "island", "isle",
        "valley", "glen", "gorge", "pass", "ridge", "summit", "peak", "hill",
        "park", "gardens", "garden", "square", "street", "road", "lane", "walk",
        "castle", "abbey", "cathedral", "church", "museum", "gallery", "market",
        "lake", "lough", "loch", "river", "falls", "forest", "woods", "trail",
        "area", "side", "end", "gate", "bridge", "point", "head", "hall",
    }
)

_WORD = re.compile(r"\b[A-Z][\w'\u00c0-\u024f-]+")


def _key(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def proper_nouns(text: str) -> set[str]:
    """Capitalised words, ignoring sentence-initial ones and common vocabulary."""
    out: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for i, match in enumerate(_WORD.finditer(sentence)):
            word = match.group(0)
            # The first word of a sentence is capitalised by grammar, not by being a name.
            if i == 0 and match.start() == 0:
                continue
            lowered = word.lower()
            if lowered in _STOPWORDS or lowered in _GEOGRAPHIC:
                continue
            out.add(word)
    return out


def invented_names(text: str, facts: list[str]) -> set[str]:
    """Proper nouns in `text` that appear nowhere in `facts`.

    Matching is loose on purpose: "Glendalough" inside "Glendalough Round Tower" counts as
    grounded. The check exists to catch wholesale invention, not paraphrase.
    """
    haystack = " ".join(_key(f) for f in facts)
    return {n for n in proper_nouns(text) if _key(n) not in haystack}


def is_grounded(text: str, facts: list[str]) -> bool:
    return not invented_names(text, facts)


def within_length(text: str, max_chars: int) -> bool:
    return len(text.strip()) <= max_chars


def choice_is_offered(chosen: str, candidates: list[str]) -> bool:
    """A disambiguation may only pick from the list it was given (ADR-0008)."""
    wanted = _key(chosen)
    return any(_key(c) == wanted for c in candidates)
