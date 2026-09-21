/**
 * Positioning, customer and price.
 *
 * The price is the one exact number here and sits apart from the prose,
 * because it is the figure the founder will actually quote to a customer.
 *
 * `strategyRejections` is worth surfacing rather than hiding: the code checks
 * in `agents/_guardrails.py` caught a plan that described the wrong business,
 * priced in the wrong units or used demeaning wording, and sent it back. A
 * founder seeing that the plan was checked trusts the one they got more.
 */

import { Attribution, Card, Figure, Judgement, Section } from "@/components/primitives";
import { money } from "@/lib/format";
import type { Strategy } from "@/lib/types";

export function StrategySection({
  strategy,
  rejections,
}: {
  strategy: Strategy;
  rejections: { problems: string[] }[];
}) {
  return (
    <Section id="strategy" title="The strategy" lead="Who this is for, and what they pay.">
      <Card className="p-6 sm:p-8">
        <div className="grid gap-8 lg:grid-cols-[1fr_auto] lg:gap-12">
          <div className="min-w-0 space-y-6">
            <div>
              <p className="text-caption font-medium uppercase tracking-wide text-ink-faint">
                Positioning
              </p>
              <p className="mt-2 text-heading text-ink">{strategy.positioning}</p>
            </div>
            <div>
              <p className="text-caption font-medium uppercase tracking-wide text-ink-faint">
                Who buys
              </p>
              <p className="mt-2 text-body text-ink-muted">{strategy.target_customer}</p>
            </div>
          </div>

          <div className="lg:border-l lg:border-line lg:pl-12">
            <Figure
              label="Price"
              value={money(strategy.price, strategy.currency)}
              source={strategy.price_unit}
            />
          </div>
        </div>

        {strategy.rationale?.length ? (
          <div className="mt-8 border-t border-line pt-6">
            <p className="mb-3 text-caption font-medium uppercase tracking-wide text-ink-faint">
              Why this, and not something else
            </p>
            <Judgement points={strategy.rationale} by="strategy" />
          </div>
        ) : null}

        {rejections.length ? (
          <p className="mt-6 text-caption text-ink-faint">
            {rejections.length === 1 ? "An earlier draft was" : `${rejections.length} earlier drafts were`}{" "}
            sent back by the plan checks before this one passed
            {rejections[0]?.problems?.length ? ` (${rejections[0].problems[0].toLowerCase()})` : ""}.
          </p>
        ) : null}
      </Card>
    </Section>
  );
}

export function StrategyAttribution() {
  return <Attribution agent="strategy" />;
}
