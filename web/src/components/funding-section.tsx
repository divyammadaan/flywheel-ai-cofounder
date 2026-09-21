/**
 * When to raise, and what to hit first.
 *
 * NOT_READY is the common and correct answer for a business that has not
 * launched, so it is presented as a plain finding rather than dressed up as a
 * problem. The milestones are the actionable part and get the visual weight.
 *
 * `warnings` are the funding checker's remaining objections after one retry --
 * a round too big for its stage, or traction and revenue milestones that
 * contradict each other. They are shown because an unflagged contradiction is
 * how a founder walks into a pitch with numbers that do not add up.
 */

import {
  Attribution,
  Card,
  Judgement,
  Pill,
  Section,
  Warning,
} from "@/components/primitives";
import { asList } from "@/lib/format";
import type { Funding } from "@/lib/types";

const READINESS_COPY: Record<string, string> = {
  NOT_READY: "Not yet",
  READY_PRE_SEED: "Ready — pre-seed",
  READY_SEED: "Ready — seed",
  READY_SERIES_A: "Ready — Series A",
};

export function FundingSection({ funding }: { funding: Funding }) {
  const readiness = READINESS_COPY[funding.readiness] ?? funding.readiness;
  const ready = funding.readiness !== "NOT_READY";

  return (
    <Section
      id="funding"
      title="Raising money"
      lead="Whether to raise now, and what to prove before you do."
    >
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-3 border-b border-line px-6 py-5 sm:px-8">
          <div className="flex items-baseline gap-3">
            <span className="text-caption font-medium uppercase tracking-wide text-ink-faint">
              Ready to raise?
            </span>
            <Pill tone={ready ? "go" : "neutral"}>{readiness}</Pill>
          </div>
          <p className="text-small text-ink-muted">
            Target <span className="font-semibold text-ink">{funding.target_raise_date}</span> ·{" "}
            {funding.target_stage}
          </p>
        </div>

        <div className="space-y-7 px-6 py-6 sm:px-8">
          {funding.warnings?.length ? (
            <div className="space-y-2.5">
              {funding.warnings.map((warning, i) => (
                <Warning key={i}>{warning}</Warning>
              ))}
            </div>
          ) : null}

          <div>
            <h3 className="mb-4 text-caption font-medium uppercase tracking-wide text-ink-faint">
              Hit these first
            </h3>
            <div className="grid gap-4 sm:grid-cols-3">
              <Milestone label="Revenue" value={funding.revenue_milestone} />
              <Milestone label="Profit" value={funding.profit_milestone} />
              <Milestone
                label="Traction"
                items={asList(funding.traction_milestones)}
              />
            </div>
          </div>

          <div className="grid gap-6 border-t border-line pt-6 sm:grid-cols-2">
            <div>
              <h3 className="mb-2 text-caption font-medium uppercase tracking-wide text-ink-faint">
                Who to talk to
              </h3>
              <p className="text-small text-ink-muted">{funding.investor_profile}</p>
            </div>
            <div>
              <h3 className="mb-2 text-caption font-medium uppercase tracking-wide text-ink-faint">
                Instead of equity
              </h3>
              <p className="text-small text-ink-muted">{funding.alternative_funding}</p>
            </div>
          </div>

          {funding.readiness_rationale?.length ? (
            <details className="group border-t border-line pt-6">
              <summary className="cursor-pointer list-none text-small font-medium text-ink-muted transition-colors hover:text-ink">
                <span className="group-open:hidden">Why this call →</span>
                <span className="hidden group-open:inline">Why this call ↓</span>
              </summary>
              <div className="mt-4">
                <Judgement points={funding.readiness_rationale} />
              </div>
            </details>
          ) : null}

          {asList(funding.pitch_deck_outline).length ? (
            <details className="group border-t border-line pt-6">
              <summary className="cursor-pointer list-none text-small font-medium text-ink-muted transition-colors hover:text-ink">
                <span className="group-open:hidden">Pitch deck outline →</span>
                <span className="hidden group-open:inline">Pitch deck outline ↓</span>
              </summary>
              <ol className="mt-4 space-y-2.5">
                {asList(funding.pitch_deck_outline).map((slide, i) => (
                  <li key={i} className="flex gap-3 text-body text-ink-muted">
                    <span className="tnum mt-px w-5 shrink-0 text-small font-semibold text-ink-faint">
                      {i + 1}
                    </span>
                    <span className="min-w-0">{slide}</span>
                  </li>
                ))}
              </ol>
            </details>
          ) : null}

          <Attribution agent="funding" />
        </div>
      </Card>
    </Section>
  );
}

function Milestone({
  label,
  value,
  items,
}: {
  label: string;
  value?: string;
  items?: string[];
}) {
  return (
    <div className="rounded-tile border border-line bg-surface-sunken p-4">
      <p className="text-caption font-medium uppercase tracking-wide text-ink-faint">{label}</p>
      {items?.length ? (
        <ul className="mt-2 space-y-2">
          {items.map((item, i) => (
            <li key={i} className="text-small text-ink">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-small text-ink">{value}</p>
      )}
    </div>
  );
}
