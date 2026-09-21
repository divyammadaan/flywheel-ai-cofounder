"""Request and response shapes.

Validation that belongs to the product, not to a form widget, lives here: a
budget of zero cannot be planned with, and capital is what the whole launch
plan is sized from. The Streamlit version checked these by assembling a list
of missing field labels in the page; stating them on the schema means the
front end gets a precise, per-field error for free and cannot forget one.
"""

from pydantic import BaseModel, Field, field_validator

from agents._money import SUPPORTED_CURRENCIES
from agents._cash import DEFAULT_RUNWAY_MONTHS

Currency = Field(default="INR", description="One of " + ", ".join(SUPPORTED_CURRENCIES))


class NewIdeaRequest(BaseModel):
    pitch: str = Field(min_length=10, description="What the founder wants to build")
    currency: str = Currency
    starting_capital: float = Field(gt=0, description="Capital available for the launch")
    monthly_fixed_costs: float | None = Field(default=None, ge=0)
    unit_cost: float | None = Field(default=None, ge=0)
    runway_months: int = Field(default=DEFAULT_RUNWAY_MONTHS, ge=0, le=36)
    include_formation: bool = True
    include_funding: bool = True

    @field_validator("currency")
    @classmethod
    def known_currency(cls, value: str) -> str:
        if value not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {', '.join(SUPPORTED_CURRENCIES)}")
        return value

    @field_validator("pitch")
    @classmethod
    def not_just_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("describe the idea in a sentence or two")
        return value.strip()


class AnswersRequest(BaseModel):
    """The founder's replies, keyed by the question they answer."""

    answers: dict[str, str] = Field(default_factory=dict)


class PeriodMetricsIn(BaseModel):
    period_label: str = Field(min_length=1, description='e.g. "FY2025-26"')
    revenue: float = Field(ge=0)
    net_profit: float = Field(description="Negative for a loss")
    total_debt: float = Field(ge=0)
    period_months: int = Field(default=12, ge=1, le=12)
    ebitda: float | None = None
    cash_in_bank: float | None = Field(default=None, ge=0)
    marketing_spend: float | None = Field(default=None, ge=0)
    new_customers: int | None = Field(default=None, ge=0)
    customers_at_start: int | None = Field(default=None, ge=0)
    customers_lost: int | None = Field(default=None, ge=0)


class ExistingBusinessRequest(BaseModel):
    description: str = Field(min_length=10)
    currency: str = Currency
    metrics: PeriodMetricsIn
    budget: float = Field(gt=0, description="What the founder can deploy next period")
    include_funding: bool = True
    # Set by the upload endpoint, which parses the file and hands back a token.
    orders_token: str | None = None

    @field_validator("currency")
    @classmethod
    def known_currency(cls, value: str) -> str:
        if value not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {', '.join(SUPPORTED_CURRENCIES)}")
        return value


class RunSummary(BaseModel):
    id: int
    workspace_id: int
    mode: str | None
    label: str | None
    status: str
    error: str | None
    created_at: str | None
    updated_at: str | None


class RunCreated(BaseModel):
    run_id: int
    status: str


class EventOut(BaseModel):
    seq: int
    run_id: int
    kind: str
    agent: str | None
    message: str | None
    payload: dict
    created_at: str | None


class RecordOut(BaseModel):
    id: int
    cycle: int
    agent: str
    input_snapshot: dict
    decision: dict
    timestamp: str


class UsageAgent(BaseModel):
    agent: str
    calls: int
    cache_hits: int
    prompt_tokens: int
    completion_tokens: int
    seconds: float


class UsageOut(BaseModel):
    agents: list[UsageAgent]
    totals: dict


class OrdersPreview(BaseModel):
    """What the founder sees before committing to an upload.

    A parsed preview rather than a bare "file accepted": order files are messy
    exports, and the number of rows that had to be skipped is the founder's
    signal that the wrong column was picked up.
    """

    token: str
    rows: int
    skipped_rows: int
    customers: int
    first_order: str | None
    last_order: str | None
    columns: list[str]


class RunDetail(BaseModel):
    run: RunSummary
    records: list[RecordOut]
    events: list[EventOut]
