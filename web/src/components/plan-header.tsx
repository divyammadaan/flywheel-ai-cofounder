/**
 * Who this plan is for, and how to leave with it.
 *
 * The business summary is the page's real title -- the run id is a database
 * detail the founder should never have to care about.
 *
 * The header spans the content frame rather than a narrow column, but the
 * title itself still caps its measure: a summary that runs 1,200px wide is
 * unreadable even though the space exists.
 */

import { Page } from "@/components/app-shell";
import { LinkButton, Pill } from "@/components/primitives";
import { api } from "@/lib/api";
import { money, relativeTime } from "@/lib/format";
import type { Intake, Run } from "@/lib/types";

export function PlanHeader({
  run,
  intake,
  hasPlan,
}: {
  run: Run;
  intake?: Intake;
  hasPlan: boolean;
}) {
  const operating = intake?.mode === "existing_business";

  return (
    <header className="border-b border-line bg-surface">
      <Page className="py-7 sm:py-9">
        <div className="flex flex-wrap items-start justify-between gap-x-10 gap-y-5">
          <div className="min-w-0 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone="accent">{operating ? "Operating business" : "Pre-launch"}</Pill>
              {intake?.industry ? <Pill>{intake.industry}</Pill> : null}
              {intake?.target_region ? <Pill>{intake.target_region}</Pill> : null}
            </div>

            <h1 className="mt-3.5 text-title font-semibold tracking-tight text-ink">
              {intake?.business_summary ?? run.label ?? `Plan ${run.id}`}
            </h1>

            <p className="mt-2.5 text-small text-ink-muted">
              {!operating && intake?.starting_capital ? (
                <>
                  Planned from{" "}
                  <span className="tnum font-semibold text-ink">
                    {money(intake.starting_capital, intake.currency)}
                  </span>{" "}
                  of capital
                </>
              ) : null}
              {run.updated_at ? (
                <span className="text-ink-faint">
                  {!operating && intake?.starting_capital ? " · " : ""}
                  {relativeTime(run.updated_at)}
                </span>
              ) : null}
            </p>
          </div>

          {hasPlan ? (
            <LinkButton href={api.landingPageUrl(run.id)} download className="shrink-0">
              Download launch page
            </LinkButton>
          ) : null}
        </div>
      </Page>
    </header>
  );
}
