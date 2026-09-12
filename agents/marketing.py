"""Marketing agent — generates ad copy AND the matching ad visual within its
approved budget. Runs concurrently with Product/Sales/CRM.

Multimodal by design: the agent writes both the copy and the image prompt in
one pass, so the visual is grounded in the same positioning and price point
rather than being a generic stock picture bolted on afterwards. Image
generation itself is delegated to tools/image_gen.py.
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._models import AGENT_MODELS
from agents._retry import retry_on_rate_limit
from tools.image_gen import generate_ad_image

DEFAULT_MODEL = AGENT_MODELS["marketing"]


class MarketingOutputSchema(BaseModel):
    ad_copy: str = Field(description="Ad copy for this cycle, 2-4 sentences")
    image_prompt: str = Field(
        description=(
            "A visual description for the ad image, for a text-to-image model. Describe "
            "the scene, subject, lighting and mood -- no text or words in the image, and "
            "no brand names. One sentence."
        )
    )
    quality_score: float = Field(description="Self-assessed quality/confidence 0..1")


@dataclass
class MarketingOutput:
    cycle: int
    budget_spent: float
    ad_copy: str
    ad_image_path: str | None
    quality_score: float
    image_prompt: str = ""


class MarketingAgent:
    """CrewAI agent writing ad copy plus the image prompt, grounded in
    Strategy's positioning, price point, and this cycle's budget."""

    def __init__(self, model: str = DEFAULT_MODEL, generate_image: bool = True):
        # generate_image is off in tests and anywhere an external image
        # service would make a run slow or flaky.
        self._generate_image = generate_image
        llm = LLM(model=model)
        self._agent = Agent(
            role="Marketing Lead",
            goal="Write ad copy that converts, plus the visual that should run alongside it",
            backstory=(
                "You run marketing for a lean, fast-moving startup. You write ad copy that "
                "reflects the current positioning and price point, brief the accompanying "
                "image, and are honest about your own confidence given the budget you have "
                "to work with this cycle."
            ),
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def execute(self, cycle: int, budget: float, positioning: str, pricing: float | None = None) -> MarketingOutput:
        price_context = f" at a ${pricing:.2f} price point" if pricing is not None else ""
        task = Task(
            description=(
                f"Cycle {cycle}. Marketing budget this cycle: ${budget:.2f}. "
                f"Current positioning: {positioning}{price_context}.\n"
                "Write ad copy for this cycle, brief the image that should run with it, and "
                "rate your own confidence (0..1), considering whether the budget supports "
                "the reach this copy needs."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=MarketingOutputSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed: MarketingOutputSchema = task.output.pydantic

        # None on failure -- an unreachable image service shouldn't fail the
        # cycle, since the copy is the substantive output.
        image_path = generate_ad_image(parsed.image_prompt, cycle) if self._generate_image else None

        return MarketingOutput(
            cycle=cycle,
            budget_spent=budget,
            ad_copy=parsed.ad_copy,
            ad_image_path=image_path,
            quality_score=parsed.quality_score,
            image_prompt=parsed.image_prompt,
        )
