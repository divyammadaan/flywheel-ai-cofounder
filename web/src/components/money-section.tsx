/**
 * The cash position, and the split.
 *
 * Everything here is arithmetic. `agents/finance.py` computes the reserve,
 * break-even, runway and the capped split in code and makes no model call, so
 * every number is exact and gets the <Figure> treatment with a caption naming
 * where it came from. Finance's explanation is prose, but prose generated from
 * those same numbers -- hence <ComputedNote> rather than <Judgement>.
 *
 * The two shapes of `health` are the two kinds of business: a launch has
 * capital, a reserve and a break-even; an operating business has profit,
 * runway and debt. They are never both present.
 */

import { BudgetSplit } from "@/components/budget-split";
import { Card, ComputedNote, Figure, FigureGrid, Section, Warning } from "@/components/primitives";
import { count, money, percent } from "@/lib/format";
import type { Finance } from "@/lib/types";

/** Mirrors MAX_SHARE_PER_AGENT in agents/finance.py. */
const CAP_SHARE = 0.6;

export function MoneySection({ finance }: { finance: Finance }) {
  const { health, currency } = finance;
  const preLaunch = health?.launch_budget !== undefined;

  return (
    <Section
      id="money"
      title="The money"
      lead={
        preLaunch
          ? "What you have, what is held back, and what the plan may spend."
          : "Where the business stands, and what the plan may spend."
      }
    >
      <Card className="p-6 sm:p-8">
        <FigureGrid>
          {preLaunch ? <LaunchFigures finance={finance} /> : <OperatingFigures finance={finance} />}
        </FigureGrid>

        <div className="mt-8 border-t border-line pt-8">
          <div className="mb-6 flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-heading font-semibold text-ink">
              How the {money(finance.total_budget, currency)} is divided
            </h3>
          </div>
          <BudgetSplit
            total={finance.total_budget}
            amounts={{
              marketing: finance.marketing,
              product: finance.product,
              sales: finance.sales,
              crm: finance.crm,
            }}
            currency={currency}
            capShare={CAP_SHARE}
          />
        </div>

        {finance.rationale ? (
          <div className="mt-7">
            <ComputedNote>{finance.rationale}</ComputedNote>
          </div>
        ) : null}

        {health?.warnings?.length ? (
          <div className="mt-5 space-y-2.5">
            {health.warnings.map((warning, i) => (
              <Warning key={i}>{warning}</Warning>
            ))}
          </div>
        ) : null}
      </Card>
    </Section>
  );
}

function LaunchFigures({ finance }: { finance: Finance }) {
  const { health, currency } = finance;
  const months = health.runway_months_reserved;

  return (
    <>
      <Figure
        label="Your capital"
        value={money(health.capital, currency)}
        source="The figure you entered"
      />
      <Figure
        label="Held in reserve"
        value={money(health.reserve, currency)}
        tone="muted"
        source={
          months
            ? `${months} months of fixed costs, untouchable by the plan`
            : "No fixed costs given"
        }
      />
      <Figure
        label="Budget to deploy"
        value={money(health.launch_budget, currency)}
        source="Capital minus the reserve"
      />
      <Figure
        label="Break-even"
        value={
          health.break_even_units_per_month != null
            ? `${count(health.break_even_units_per_month)}/mo`
            : "—"
        }
        source={
          health.contribution_margin != null
            ? `Units a month at ${money(health.contribution_margin, currency)} margin each`
            : "Needs a unit cost to compute"
        }
      />
    </>
  );
}

function OperatingFigures({ finance }: { finance: Finance }) {
  const { health, currency } = finance;

  return (
    <>
      <Figure
        label="Monthly net profit"
        value={money(health.monthly_net_profit, currency)}
        tone={(health.monthly_net_profit ?? 0) >= 0 ? "positive" : "caution"}
        source="From the numbers you reported"
      />
      <Figure
        label="Runway"
        value={
          health.profitable
            ? "No burn"
            : health.runway_months != null
              ? `${health.runway_months} months`
              : "—"
        }
        source={health.profitable ? "Profitable, so cash is not the constraint" : "Cash ÷ monthly burn"}
      />
      <Figure
        label="Debt load"
        value={percent(health.debt_to_annual_revenue ?? null, 0)}
        tone={(health.debt_to_annual_revenue ?? 0) > 0.5 ? "caution" : "default"}
        source="Of a year's revenue"
      />
      <Figure
        label="Budget vs cash"
        value={percent(health.budget_share_of_cash ?? null, 0)}
        source="How much of your cash this plan spends"
      />
    </>
  );
}
