"""Turning model output into something scannable.

The shaping logic itself now lives in `agents/_text.py`, next to the agents
whose schemas it mirrors -- the API layer and the CLIs need it too, and none of
them should have to import from a dashboard package. This module stays as the
dashboard's import surface so app.py and its tests are unaffected.
"""

from agents._text import (  # noqa: F401 -- re-exported for the dashboard and its tests
    MIN_ITEM_CHARS,
    MIN_SENTENCE_CHARS,
    as_bullets,
    as_list,
    clause_items,
    headline,
    numbered_items,
    sentences,
    shorten,
)

__all__ = [
    "MIN_ITEM_CHARS",
    "MIN_SENTENCE_CHARS",
    "as_bullets",
    "as_list",
    "clause_items",
    "headline",
    "numbered_items",
    "sentences",
    "shorten",
]
