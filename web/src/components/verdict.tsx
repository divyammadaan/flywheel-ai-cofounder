/**
 * The verdict.
 *
 * This is the most consequential thing on the page and the only place three
 * colours appear together, so it gets the page's largest type and the top of
 * the document. A NO-GO is not an error state -- the product working as
 * intended is it telling a founder not to spend the money -- so it is styled
 * as a finding, not as a failure.
 */

import { Card, Judgement } from "@/components/primitives";
import { cn } from "@/lib/cn";
import { money } from "@/lib/format";
import type { AdvisorDecision, Verdict as VerdictValue } from "@/lib/types";

const COPY: Record<VerdictValue, { title: string; lead: string; tone: string; dot: string }> = {
  GO: {
    title: "Go",
    lead: "Worth building, on the terms below.",
    tone: "text-go",
    dot: "bg-go",
  },
  PIVOT: {
    title: "Pivot",
    lead: "Worth building, but not as pitched. The plan below reflects the change.",
    tone: "text-pivot",
    dot: "bg-pivot",
  },
  NO_GO: {
    title: "No go",
    lead: "Not worth your money as it stands. There is no launch plan, and that is the point.",
    tone: "text-nogo",
    dot: "bg-nogo",
  },
};

export function VerdictBlock({
  advisor,
  currency,
}: {
  advisor: AdvisorDecision;
  currency: string;
}) {
  const verdict = (advisor.verdict ?? "PIVOT") as VerdictValue;
  const copy = COPY[verdict] ?? COPY.PIVOT;

  return (
    <Card className="overflow-hidden">
      <div className="p-6 sm:p-8">
        <div className="flex items-center gap-2.5">
          <span aria-hidden className={cn("h-2 w-2 rounded-full", copy.dot)} />
          <span className="text-caption font-medium uppercase tracking-wide text-ink-faint">
            The verdict
          </span>
        </div>

        <h1 className={cn("mt-3 text-display font-semibold", copy.tone)}>{copy.title}</h1>
        <p className="mt-2 max-w-2xl text-body text-ink-muted">{copy.lead}</p>

        {advisor.seed_positioning ? (
          <div className="mt-7 border-t border-line pt-6">
            <p className="text-caption font-medium uppercase tracking-wide text-ink-faint">
              Where it should sit
            </p>
            <p className="mt-2 max-w-3xl text-heading text-ink">
              {stripQuotes(advisor.seed_positioning)}
            </p>
            {advisor.seed_price ? (
              <p className="tnum mt-3 text-small text-ink-muted">
                <span className="font-semibold text-ink">
                  {money(advisor.seed_price, currency)}
                </span>{" "}
                {advisor.seed_price_unit}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      {advisor.rationale?.length ? (
        <div className="border-t border-line bg-surface-sunken px-6 py-6 sm:px-8">
          <p className="mb-3 text-caption font-medium uppercase tracking-wide text-ink-faint">
            Why
          </p>
          <Judgement points={advisor.rationale} by="founder_advisor" />
        </div>
      ) : null}
    </Card>
  );
}

/** The model sometimes wraps positioning in quotes; the page supplies its own. */
function stripQuotes(value: string): string {
  return value.replace(/^["“”']+|["“”']+$/g, "").trim();
}
