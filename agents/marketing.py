"""Marketing agent — plans the specific ad campaigns to run (platform, exact
targeting, format, timing, spend) and writes the ad copy plus a matching ad
image. Runs concurrently with Product/Sales/CRM.

Multimodal by design: the agent writes the copy and the image prompt in the
same pass as the campaigns, so the visual is grounded in the same positioning
and audience rather than being a generic stock picture bolted on afterwards.
Image generation itself is delegated to tools/image_gen.py.

Campaign budgets are checked in code (agents/_money.fit_to_budget): if the
model's campaigns add up to more than Marketing's allocation, they're scaled
down proportionally and the output says so.
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._brief import LAUNCH, PlanBrief
from agents._models import AGENT_MODELS
from agents._money import fit_to_budget
from agents._retry import retry_on_rate_limit
from tools.image_gen import generate_ad_image

DEFAULT_MODEL = AGENT_MODELS["marketing"]


class Campaign(BaseModel):
    channel: str = Field(
        description="Specific platform or channel, e.g. 'Instagram Reels ads', 'Google Search ads', 'housing-society WhatsApp groups'"
    )
    where: str = Field(description="Exact targeting: cities/localities, audience, keywords or placements")
    ad_format: str = Field(description="Creative format, e.g. '15-second Reel', 'carousel', 'search text ad'")
    objective: str = Field(description="What it must achieve, e.g. 'launch waitlist sign-ups'")
    duration: str = Field(description="When it runs, e.g. 'launch weeks 1-4'")
    budget: float = Field(description="Spend on this campaign, in the plan currency")


class MarketingOutputSchema(BaseModel):
    campaigns: list[Campaign] = Field(
        description="2-4 campaigns whose budgets add up to no more than the marketing budget"
    )
    ad_copy: str = Field(description="The main ad copy, 2-3 sentences")
    image_prompt: str = Field(
        description=(
            "A visual description for the ad image, for a text-to-image model. Describe "
            "the scene, subject, lighting and mood -- no text or words in the image, and "
            "no brand names. One sentence."
        )
    )


@dataclass
class MarketingOutput:
    cycle: int
    budget: float
    currency: str
    campaigns: list
    ad_copy: str
    ad_image_path: str | None
    image_prompt: str = ""
    budget_adjusted: bool = False


class MarketingAgent:
    """CrewAI agent planning campaigns plus the copy and image prompt,
    grounded in the shared PlanBrief and this plan's marketing budget."""

    def __init__(self, model: str = DEFAULT_MODEL, generate_image: bool = True):
        # generate_image is off in tests and anywhere an external image
        # service would make a run slow or flaky.
        self._generate_image = generate_image
        llm = LLM(model=model)
        self._agent = Agent(
            role="Marketing Lead",
            goal="Plan specific campaigns that reach the right customers, plus the ad they will see",
            backstory=(
                "You run marketing for a lean startup and plan like someone spending their own "
                "money: every campaign names the platform, the exact localities or audience, the "
                "format, the timing and the spend. You never give vague advice like 'use social "
                "media', and before launch you never claim results that haven't happened."
            ),
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def execute(self, brief: PlanBrief, budget: float) -> MarketingOutput:
        if brief.mode == LAUNCH:
            focus = "This is a launch: campaigns should build awareness and sign-ups for launch day."
        else:
            focus = "The business is operating: aim the campaigns at what its reported numbers say needs fixing."
        task = Task(
            description=(
                f"{brief.describe(budget, 'Marketing budget')}\n\n"
                f"{focus}\n"
                "Plan 2-4 specific campaigns, write the main ad copy, and brief the ad image. "
                "BE CONCISE: keep every campaign field under ~20 words."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=MarketingOutputSchema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed: MarketingOutputSchema = task.output.pydantic

        campaigns = [c.model_dump() for c in parsed.campaigns]
        fitted, adjusted = fit_to_budget([c["budget"] for c in campaigns], budget)
        for campaign, amount in zip(campaigns, fitted):
            campaign["budget"] = amount

        # None on failure -- an unreachable image service shouldn't fail the
        # plan, since the campaigns and copy are the substantive output.
        image_path = generate_ad_image(parsed.image_prompt, brief.cycle) if self._generate_image else None

        return MarketingOutput(
            cycle=brief.cycle,
            budget=budget,
            currency=brief.currency,
            campaigns=campaigns,
            ad_copy=parsed.ad_copy,
            ad_image_path=image_path,
            image_prompt=parsed.image_prompt,
            budget_adjusted=adjusted,
        )
