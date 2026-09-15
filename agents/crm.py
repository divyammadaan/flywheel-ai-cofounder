"""CRM agent — existing businesses only, working from the founder's uploaded
order history.

Code (agents/_segments.py) does the maths: who the best customers are, who is
slipping away, who is lost, and how that changed since last period. This
agent's model writes what to do about each group and a spend for each, plus
ready-to-send messages. A business that hasn't launched has no customers, so it
gets no CRM plan at all.

Deliberately runs on a local Ollama model (qwen3:4b), not a hosted API: this
agent sees real customer names and spending, so that data never leaves the
machine. Satisfies the course's local-LLM / data-privacy requirement (CO2).

Why it calls Ollama directly instead of going through CrewAI -- measured on the
dev machine's CPU (~9.5 tokens/s), same prompt and sample data:
- Through CrewAI: two model calls (6m04s + 8m45s). CrewAI wraps the task in its
  own agent prompt, then makes a second call to convert the answer into the
  schema; a 4B model on CPU pays heavily for both.
- Direct: one call to Ollama's native /api/chat with think:false and the JSON
  schema passed as `format` -- 66s, 439 output tokens, valid on the first try.
  (think:false matters: qwen3 otherwise reasons first, roughly doubling output,
  and Ollama's OpenAI-compatible endpoint ignores reasoning_effort="none".)

What the model gets wrong is fixed in code rather than trusted:
- its per-group spends are cut to fit the budget (it allocated Rs 75k of a
  Rs 60k budget in testing);
- messages always greet the customer by name, and any sentence with a
  placeholder nothing can fill (e.g. "[date]") or demeaning wording is dropped,
  rather than leaving a broken sentence.
"""

import re
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field

from agents._brief import PlanBrief
from agents._guardrails import demeaning_terms
from agents._models import OLLAMA_BASE_URL, OLLAMA_MODEL
from agents._money import fit_to_budget, fmt_money
from agents._retry import retry_on_rate_limit
from agents._segments import SEGMENT_DEFINITIONS, SEGMENT_LABELS, SEGMENTS, describe_segments, segment_changes

REQUEST_TIMEOUT_SECONDS = 300
PREVIEW_CUSTOMERS = 3

_SYSTEM = """You run customer retention for a small business. You work from real customer
groups and write specific actions the founder can do this week, each with a spend in the
plan currency. The spends together must not exceed the CRM budget. Messages are short and
warm, sound like the business rather than a marketing department, and use {name} for the
customer's first name -- no other placeholders, since nothing else can be filled in."""


class CRMPlanSchema(BaseModel):
    best_customers_action: str = Field(description="What to do for best customers, under 25 words")
    best_customers_spend: float = Field(description="Spend on that action, in the plan currency")
    regulars_action: str = Field(description="What to do for regulars, under 25 words")
    regulars_spend: float = Field(description="Spend on that action, in the plan currency")
    new_customers_action: str = Field(description="How to get new customers to a second order, under 25 words")
    new_customers_spend: float = Field(description="Spend on that action, in the plan currency")
    slipping_action: str = Field(description="How to win back customers slipping away, under 25 words")
    slipping_spend: float = Field(description="Spend on that action, in the plan currency")
    lost_action: str = Field(description="Whether and how to win back lost customers, under 25 words")
    lost_spend: float = Field(description="Spend on that action, in the plan currency")
    slipping_message: str = Field(description="WhatsApp/SMS message for slipping customers, under 40 words, using {name}")
    lost_message: str = Field(description="Win-back message for lost customers, under 40 words, using {name}")


# Schema field prefix for each segment key in agents/_segments.py.
_FIELD_FOR_SEGMENT = {
    "best": "best_customers",
    "regular": "regulars",
    "new": "new_customers",
    "slipping": "slipping",
    "lost": "lost",
}


@dataclass
class CRMOutput:
    cycle: int
    budget: float
    currency: str
    segments: dict
    changes: dict
    actions: dict
    spend: dict
    budget_adjusted: bool
    slipping_message: str
    lost_message: str
    message_previews: list


_NAME_PLACEHOLDER = re.compile(r"[\[{<]\s*(?:customer[\s_]*|first[\s_]*)?name\s*[\]}>]", re.IGNORECASE)
_OTHER_PLACEHOLDER = re.compile(r"[\[{<](?!name[}])[^\]}>]{1,40}[\]}>]")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
GREETING = "Hi {name}, "
FALLBACK_MESSAGE = "Hi {name}, it's been a while and we'd love to have you back."


def normalise_message(text: str) -> str:
    """Make a model-written message safe to send.

    Name placeholders in any style become {name}. A sentence containing any
    other placeholder (e.g. "[date]", which nothing can truthfully fill) or
    demeaning wording is dropped whole, so no broken sentence is left behind.
    If the result doesn't greet the customer by name, a greeting is added.
    """
    text = _NAME_PLACEHOLDER.sub("{name}", text or "").strip()
    kept = [
        s for s in _SENTENCE_BREAK.split(text) if s and not _OTHER_PLACEHOLDER.search(s) and not demeaning_terms(s)
    ]
    message = re.sub(r"\s{2,}", " ", " ".join(kept)).strip()
    if not message:
        return FALLBACK_MESSAGE
    if "{name}" not in message:
        # Lower-case the old first letter after "Hi {name}, " -- unless it
        # starts an acronym or "I".
        first = message[0].lower() if len(message) > 1 and message[1].islower() else message[0]
        message = GREETING + first + message[1:]
    return message


def personalise(message: str, customer: str) -> str:
    first_name = str(customer).split()[0] if str(customer).strip() else "there"
    return message.replace("{name}", first_name)


class CRMAgent:
    """Direct call to a local Ollama model -- customer data never leaves this
    machine, by design."""

    def __init__(self, model: str = OLLAMA_MODEL, base_url: str = OLLAMA_BASE_URL):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _ask(self, prompt: str) -> CRMPlanSchema:
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "format": CRMPlanSchema.model_json_schema(),
                "options": {"temperature": 0.4},
                # Unload right after this one call. Ollama otherwise keeps the
                # model in RAM for 5 minutes (~3.9 GB), and on a 16 GB machine
                # that got the rest of the pipeline killed for low memory.
                "keep_alive": 0,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return CRMPlanSchema.model_validate_json(response.json()["message"]["content"])

    @retry_on_rate_limit()
    def execute(self, brief: PlanBrief, budget: float, segments: dict, previous: dict | None = None) -> CRMOutput:
        changes = segment_changes(segments, previous)
        change_text = (
            "Change since last period: " + ", ".join(f"{SEGMENT_LABELS[k]} {v:+d}" for k, v in changes.items())
            if changes
            else "No earlier period to compare with."
        )
        top = segments["top_slipping"]
        top_text = (
            "Highest-spending customers slipping away: "
            + "; ".join(
                f"{c['customer']} ({c['orders']} orders, {fmt_money(c['spent'], brief.currency)}, "
                f"{c['days_since_last_order']} days since last order)"
                for c in top
            )
            if top
            else "No high-value customers are slipping away right now."
        )
        definitions = "\n".join(f"- {SEGMENT_LABELS[k]}: {SEGMENT_DEFINITIONS[k]}" for k in SEGMENTS)
        prompt = (
            f"{brief.describe(budget, 'CRM budget')}\n\n"
            f"What each customer group means:\n{definitions}\n\n"
            f"Customer groups from the uploaded order history: {describe_segments(segments)}\n"
            f"{change_text}\n{top_text}\n\n"
            "Write one specific action and spend per group, and the two messages."
        )
        parsed = self._ask(prompt)

        spends, adjusted = fit_to_budget([getattr(parsed, f"{_FIELD_FOR_SEGMENT[k]}_spend") for k in SEGMENTS], budget)
        slipping_message = normalise_message(parsed.slipping_message)

        return CRMOutput(
            cycle=brief.cycle,
            budget=budget,
            currency=brief.currency,
            segments=segments,
            changes=changes,
            actions={k: getattr(parsed, f"{_FIELD_FOR_SEGMENT[k]}_action") for k in SEGMENTS},
            spend=dict(zip(SEGMENTS, spends)),
            budget_adjusted=adjusted,
            slipping_message=slipping_message,
            lost_message=normalise_message(parsed.lost_message),
            message_previews=[
                {"customer": c["customer"], "message": personalise(slipping_message, c["customer"])}
                for c in top[:PREVIEW_CUSTOMERS]
            ],
        )
