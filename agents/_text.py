"""Model output as points, whatever shape it arrived in.

Agents now ask for real lists (`rationale: list[str]`), so most of this is a
pass-through. Two cases still need the splitting heuristics below:

- **Older records.** Decision Records written before the schema change hold
  those fields as one paragraph, and the dashboard reads them straight back
  out of SQLite. They must keep rendering.
- **A model that ignores the schema.** Groq's free tier occasionally returns a
  single string where the schema asked for an array. Falling back to a split
  beats showing a founder a wall of text.

The splitters only break text where the structure is unambiguous -- numbered
marks, then semicolon clauses, then sentences -- and leave it alone otherwise,
so nothing is mangled into merely looking tidy.
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
    return body if len(body) <= limit else body[: limit - 1].rstrip(" ,;.") + "\u2026"


def as_list(value) -> list[str]:
    """A schema field that should be points, as points.

    A real list passes through (blank entries dropped). A string is split where
    it has structure, and otherwise kept whole as a single point -- never
    dropped, and never chopped mid-thought.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [item for item in (_clean(v) for v in value) if item]
    body = _clean(value)
    if not body:
        return []
    return as_bullets(body) or [body]


def as_text(value, joiner: str = " ") -> str:
    """The inverse: points as one string, for prompt context and the CLIs.

    Numbered so a model reading it back sees the same separations the founder
    sees, rather than one run-on paragraph.
    """
    if isinstance(value, (list, tuple)):
        items = as_list(value)
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return joiner.join(f"{i}. {item}" for i, item in enumerate(items, 1))
    return _clean(value)
