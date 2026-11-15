"""Checks on text that comes INTO the system: what the founder types, and what
tools bring back.

Two different trust levels, handled differently:

- The founder's own text (pitch, answers, change notes) is checked and, if it
  contains abusive language or an attempt to override the agents'
  instructions, refused with a message saying why. The founder can rephrase.
- Text a tool returns (web search snippets) is untrusted. Anyone can publish a
  page that says "ignore your instructions and ...", so instruction-like
  sentences are cut out before a model ever sees them, and what is left is
  framed to the model as data to cite, never as instructions.

Like agents/_guardrails.py these are deliberately simple, explainable rules
rather than another model call: fast, testable offline, and they cannot be
talked out of their answer. They are a baseline, not a complete defence.
"""

import re

from observability import trace

MAX_USER_TEXT_CHARS = 4000

# Phrases that try to replace or reveal the agents' instructions.
_INJECTION = [
    re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|all|any|your)\b"
        r"[^.\n]{0,30}\b(?:instructions?|prompts?|rules?|guidelines?|directions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|show|print|repeat|leak|output)\b[^.\n]{0,30}\b(?:system|hidden|initial|original|secret)\b"
        r"[^.\n]{0,20}\b(?:prompt|instructions?|message)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\byou are now\b|\bdeveloper mode\b|\bjailbreak(?:ed)?\b|\bDAN mode\b", re.IGNORECASE),
    re.compile(r"\bact as (?:an? )?(?:unrestricted|unfiltered|jailbroken)\b", re.IGNORECASE),
    re.compile(r"\bnew instructions?\s*:", re.IGNORECASE),
    re.compile(r"\b(?:do not|don't|never)\s+(?:follow|obey)\b[^.\n]{0,30}\b(?:instructions?|rules?)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:system|assistant|developer)\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<\|?\s*(?:im_start|im_end|system|endoftext)\s*\|?>", re.IGNORECASE),
]

# A short list of unmistakable abuse (English and common Hindi transliterations)
# and direct threats. Words that are also ordinary names or business terms are
# left out on purpose.
_ABUSIVE = re.compile(
    r"\b(?:fuck\w*|shit\w*|bitch\w*|asshole\w*|bastards?|cunts?|motherfuck\w*|dumbass\w*|"
    r"madarchod|bhenchod|behenchod|chutiya\w*|gandu|harami)\b",
    re.IGNORECASE,
)
_THREAT = re.compile(r"\b(?:kill|murder|hurt|destroy)\s+(?:you|them|him|her|everyone)\b", re.IGNORECASE)

_TAGS = re.compile(r"<[^>]{0,200}>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")

REMOVED_MARKER = "[removed: instruction-like text]"


class UnsafeInput(ValueError):
    """User text refused. A ValueError so a request schema reports it as a field error."""


def injection_found(text: str) -> bool:
    return any(p.search(text or "") for p in _INJECTION)


def unsafe_reasons(text: str) -> list[str]:
    """Why this text should not be passed to the agents, in words the founder can act on."""
    reasons = []
    if _ABUSIVE.search(text or "") or _THREAT.search(text or ""):
        reasons.append("abusive or threatening language")
    if injection_found(text):
        reasons.append("an instruction aimed at overriding the assistant")
    return reasons


def check_user_text(text: str, label: str = "text") -> str:
    """The founder's text, unchanged -- or UnsafeInput saying what is wrong with it."""
    value = text or ""
    if len(value) > MAX_USER_TEXT_CHARS:
        raise UnsafeInput(f"{label} is too long (over {MAX_USER_TEXT_CHARS:,} characters). Please shorten it.")
    reasons = unsafe_reasons(value)
    if reasons:
        trace.note("GUARD", f"refused {label}: {', '.join(reasons)}")
        raise UnsafeInput(f"Your {label} contains {' and '.join(reasons)}, which we can't process. Please rephrase it.")
    return value


def sanitize_untrusted(text: str) -> tuple[str, bool]:
    """Untrusted text with markup, control characters and instruction-like sentences removed.

    Returns (clean text, whether anything instruction-like was cut).
    """
    value = _CONTROL.sub(" ", _TAGS.sub(" ", text or ""))
    kept, flagged = [], False
    for sentence in _SENTENCE_BREAK.split(value):
        if not sentence.strip():
            continue
        if injection_found(sentence):
            flagged = True
            continue
        kept.append(sentence.strip())
    clean = re.sub(r"\s{2,}", " ", " ".join(kept)).strip()
    return (clean or (REMOVED_MARKER if flagged else "")), flagged


def redact_instructions(text: str) -> tuple[str, int]:
    """Cut instruction-like sentences from a prompt, keeping its line structure.

    For text that is already inside a model request, where flattening the
    layout (as sanitize_untrusted does) would damage the prompt. Returns
    (text, number of lines that had something cut).
    """
    lines, cut = [], 0
    for line in (text or "").split("\n"):
        if injection_found(line):
            cut += 1
            kept = [s for s in re.split(r"(?<=[.!?])\s+", line) if not injection_found(s)]
            lines.append(" ".join(kept) if kept else REMOVED_MARKER)
        else:
            lines.append(line)
    return "\n".join(lines), cut


def output_problems(text: str) -> list[str]:
    """What should not appear in an agent's reply to a founder."""
    from agents._guardrails import demeaning_terms  # lazy: _guardrails is imported by many agents

    problems = []
    if demeaning_terms(text):
        problems.append(f"it describes people or places in demeaning terms ({', '.join(demeaning_terms(text))})")
    if _ABUSIVE.search(text or "") or _THREAT.search(text or ""):
        problems.append("it contains abusive or threatening language")
    if injection_found(text):
        problems.append("it contains an instruction aimed at overriding the assistant")
    return problems


def clean_sources(sources) -> list[dict]:
    """Validate what the search tool returned, and make it safe to show a model.

    The return type is checked, not assumed: anything that is not a list of
    records with an http(s) URL is dropped, every field is forced to text, and
    snippets and titles are sanitised.
    """
    if not isinstance(sources, list):
        trace.note("GUARD", f"search returned {type(sources).__name__}, expected a list; ignored")
        return []
    cleaned, flagged = [], 0
    for item in sources:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not re.match(r"https?://", url.strip(), re.IGNORECASE):
            continue
        title, title_flag = sanitize_untrusted(str(item.get("title") or ""))
        snippet, snippet_flag = sanitize_untrusted(str(item.get("snippet") or ""))
        flagged += title_flag or snippet_flag
        cleaned.append({"title": title, "url": url.strip(), "snippet": snippet})
    if flagged:
        trace.note("GUARD", f"cut instruction-like text from {flagged} search result(s)")
    return cleaned
