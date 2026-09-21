/**
 * A run, in whatever state it is in.
 *
 * One URL covers the whole life of a plan -- working, waiting on an answer,
 * finished, stopped -- because that is what a founder bookmarks and comes back
 * to. A run still in progress shows its live sequence above whatever has
 * already landed, so the page fills in as agents finish rather than staying
 * empty for three minutes.
 *
 * The plan's own order is the order a founder reads in: is this worth doing,
 * what does it cost, what do I do on Monday, when do I raise. Not the order
 * the agents ran in.
 *
 * A finished plan is ~6,500px tall, so the rail carries a section index --
 * which is also what the empty space on a wide screen is for.
 */

import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AnalyticsSection } from "@/components/analytics-section";
import { AppShell, Page, RunIndex } from "@/components/app-shell";
import { BackgroundSection } from "@/components/background-section";
import { CrmSection } from "@/components/crm-section";
import { DoSection } from "@/components/do-section";
import { FundingSection } from "@/components/funding-section";
import { MoneySection } from "@/components/money-section";
import { PlanHeader } from "@/components/plan-header";
import { Card, Warning } from "@/components/primitives";
import { QuestionsForm } from "@/components/questions-form";
import { RunProgress } from "@/components/run-progress";
import { StrategySection } from "@/components/strategy-section";
import { UsageSection } from "@/components/usage-section";
import { VerdictBlock } from "@/components/verdict";
import { ApiError, api, toPlan, wasRevised } from "@/lib/api";
import type { Plan, RefinableAgent, RunEvent, SegmentMeta, Usage } from "@/lib/types";
import { REFINABLE_AGENTS } from "@/lib/types";

// A run changes while it is working, so this page is never cached.
export const dynamic = "force-dynamic";

/** The tab shows which plan this is -- useful the moment a founder has more
 * than one open. Falls back silently; a page that can't build a title still
 * renders, and the 404/error path below handles a genuinely missing run. */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const runId = Number(id);
  if (!Number.isFinite(runId)) return {};
  try {
    const detail = await api.getRun(runId);
    return { title: detail.run.label ?? `Plan ${runId}` };
  } catch {
    return {};
  }
}

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const runId = Number(id);
  if (!Number.isFinite(runId)) notFound();

  let detail;
  try {
    detail = await api.getRun(runId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return <ConnectionProblem message={(error as Error).message} />;
  }

  const plan = toPlan(detail);
  const { run } = plan;
  const currency = plan.intake?.currency ?? plan.strategy?.currency ?? "INR";
  const hasPlan = Boolean(plan.strategy);
  const working = run.status === "running" || run.status === "queued";
  const asking = run.status === "awaiting_answers";

  // Both are extras: the plan reads without either, so neither may break it.
  let usage: Usage | null = null;
  let segmentMeta: SegmentMeta | undefined;
  if (!working) {
    const [u, m] = await Promise.all([
      api.getUsage(runId).catch(() => null),
      api.segmentMeta().catch(() => undefined),
    ]);
    usage = u;
    segmentMeta = m;
  }

  const questions = questionsFrom(detail.events);
  // Which of this cycle's agents are already a redone version -- drives the
  // small "Revised on your feedback" note next to each "Suggest a change".
  const revisedAgents = new Set<RefinableAgent>(
    REFINABLE_AGENTS.filter((agent) => wasRevised(detail, agent, plan.cycle)),
  );

  return (
    <AppShell aside={<RunIndex sections={sectionsOf(plan)} />}>
      <PlanHeader run={run} intake={plan.intake} hasPlan={hasPlan} />

      <Page className="py-9 sm:py-12">
        <div className="space-y-12">
          {working ? <RunProgress runId={runId} status={run.status} mode={run.mode} /> : null}

          {asking && questions.length ? (
            <QuestionsForm runId={runId} questions={questions} />
          ) : null}

          {run.status === "blocked" && run.error ? (
            <Warning>
              <span className="font-medium">The plan couldn&apos;t go ahead.</span> {run.error}
            </Warning>
          ) : null}

          {run.status === "failed" ? (
            <Warning>
              <span className="font-medium">This run stopped before it finished.</span>{" "}
              {run.error ?? "Something went wrong."} Nothing was spent from your budget — you
              can start again.
            </Warning>
          ) : null}

          {plan.advisor ? <VerdictBlock advisor={plan.advisor} currency={currency} /> : null}

          {!hasPlan && plan.advisor?.verdict === "NO_GO" ? (
            <Card className="p-6 sm:p-8">
              <p className="max-w-prose text-body text-ink-muted">
                There is no launch plan, and that is the point — a NO-GO stops before any money
                is committed. What the call was based on is below.
              </p>
            </Card>
          ) : null}

          {plan.analytics ? <AnalyticsSection analytics={plan.analytics} /> : null}

          {plan.strategy ? (
            <StrategySection strategy={plan.strategy} rejections={plan.strategyRejections} />
          ) : null}

          {plan.finance ? <MoneySection finance={plan.finance} /> : null}

          <DoSection
            marketing={plan.marketing}
            sales={plan.sales}
            product={plan.product}
            currency={currency}
            runId={runId}
            cycle={plan.cycle}
            revisedAgents={revisedAgents}
          />

          {plan.crm ? (
            <CrmSection
              crm={plan.crm}
              currency={currency}
              meta={segmentMeta}
              runId={runId}
              cycle={plan.cycle}
              revised={revisedAgents.has("crm")}
            />
          ) : null}

          {plan.funding ? (
            <FundingSection
              funding={plan.funding}
              runId={runId}
              cycle={plan.cycle}
              revised={revisedAgents.has("funding")}
            />
          ) : null}

          <BackgroundSection research={plan.research} formation={plan.formation} />

          {usage ? <UsageSection usage={usage} /> : null}
        </div>
      </Page>
    </AppShell>
  );
}

/** Only sections that actually rendered, so the index can't point at nothing. */
function sectionsOf(plan: Plan): { id: string; label: string }[] {
  const sections: { id: string; label: string }[] = [];
  if (plan.analytics) sections.push({ id: "numbers", label: "Your numbers" });
  if (plan.strategy) sections.push({ id: "strategy", label: "The strategy" });
  if (plan.finance) sections.push({ id: "money", label: "The money" });
  if (plan.marketing || plan.sales || plan.product)
    sections.push({ id: "do", label: "What to actually do" });
  if (plan.crm) sections.push({ id: "crm", label: "Your customers" });
  if (plan.funding) sections.push({ id: "funding", label: "Raising money" });
  if (plan.research || plan.formation)
    sections.push({ id: "background", label: "What this was based on" });
  return sections;
}

/**
 * The clarifying questions, read back off the run's own events.
 *
 * Not held in memory between the two requests: this is what lets a founder
 * close the tab, come back tomorrow and still be asked the same questions.
 */
function questionsFrom(events: RunEvent[]): string[] {
  const event = [...events].reverse().find((e) => e.kind === "awaiting_answers");
  const questions = event?.payload?.questions;
  return Array.isArray(questions) ? questions.map(String) : [];
}

function ConnectionProblem({ message }: { message: string }) {
  return (
    <AppShell>
      <Page width="reading" className="flex flex-1 items-center py-20">
        <Card className="w-full max-w-lg p-8">
          <h1 className="text-title font-semibold text-ink">Can&apos;t load this plan</h1>
          <p className="mt-2 text-body text-ink-muted">{message}</p>
          <p className="mt-4 text-small text-ink-faint">
            Start the API with{" "}
            <code className="rounded bg-surface-sunken px-1.5 py-0.5 font-mono text-caption">
              python -m uvicorn api.main:app --port 8000
            </code>
          </p>
        </Card>
      </Page>
    </AppShell>
  );
}
