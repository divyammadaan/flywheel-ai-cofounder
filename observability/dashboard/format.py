"""Turning model prose into something scannable.

The agents write paragraphs; a founder reading a plan wants its shape at a
glance -- a headline, then bullets. These helpers split model text only where
the structure is unambiguous (numbered lists, semicolon-separated clauses,
sentences) and leave it alone otherwise, so nothing is mangled into looking
tidy. Kept out of app.py, and free of Streamlit, so it can be unit tested.
"""

import re

# "1. " / "2) " -- at the start, or after a space following sentence punctuation.
_NUMBERED = re.compile(r"(?:^|(?<=[\s]))(\d{1,2})[.)]\s+")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")

# Below this, a fragment is too short to be worth its own bullet.
MIN_ITEM_CHARS = 25
MIN_SENTENCE_CHARS = 40


def _clean(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def numbered_items(text) -> list[str]:
    """['Title slide -- name', 'Problem -- ...'] from '1. Title slide -- name 2. Problem ...'."""
    body = _clean(text)
    marks = list(_NUMBERED.finditer(body))
    if len(marks) < 2:
        return []
    items = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        item = body[mark.end() : end].strip(" ;,.")
        if item:
            items.append(item)
    return items if len(items) >= 2 else []


def clause_items(text) -> list[str]:
    """Semicolon-separated clauses, when each is substantial enough to stand alone."""
    parts = [p.strip(" ;,") for p in _clean(text).split(";")]
    parts = [p for p in parts if p]
    if len(parts) < 2 or any(len(p) < MIN_ITEM_CHARS for p in parts):
        return []
    return parts


def sentences(text) -> list[str]:
    parts = [s.strip() for s in _SENTENCE_BREAK.split(_clean(text)) if s.strip()]
    return parts


def as_bullets(text) -> list[str]:
    """The text as bullets, or [] when it has no structure worth splitting."""
    body = _clean(text)
    if not body:
        return []
    for split in (numbered_items, clause_items):
        items = split(body)
        if items:
            return items
    parts = sentences(body)
    if len(parts) >= 2 and all(len(p) >= MIN_SENTENCE_CHARS for p in parts[:-1]):
        return parts
    return []


def headline(text) -> tuple[str, list[str]]:
    """(first sentence, the rest as bullets) -- the shape most sections render in."""
    parts = sentences(text)
    if not parts:
        return "", []
    rest = " ".join(parts[1:])
    return parts[0], as_bullets(rest) or ([rest] if rest else [])


def shorten(text, limit: int = 140) -> str:
    body = _clean(text)
    return body if len(body) <= limit else body[: limit - 1].rstrip(" ,;.") + "…"
