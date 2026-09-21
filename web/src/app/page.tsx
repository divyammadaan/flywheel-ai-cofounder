/**
 * The front door.
 *
 * One decision to make, and it is a real fork rather than a preference: a
 * business that has not launched has no results, so it gets research and a
 * verdict before any plan; one that is trading has real numbers, so it gets
 * analysed instead. The two cards say what each path actually does, because
 * picking the wrong one wastes several minutes of model calls.
 */

import Link from "next/link";

import { AppShell, Page } from "@/components/app-shell";
import { Card, Pill } from "@/components/primitives";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { Run } from "@/lib/types";

export const dynamic = "force-dynamic";
// A title.template on the root layout never applies to app/page.tsx: they
// are the SAME route segment, not parent and child, so this is written out
// in full rather than relying on the "— Flywheel" suffix.
export const metadata = { title: "Flywheel — an AI co-founder" };

export default async function HomePage() {
  let recent: Run[] = [];
  try {
    recent = (await api.listRuns(3)) ?? [];
  } catch {
    // The front door should still open with the API down; the entry cards
    // work, and the failure is reported when a plan is actually started.
    recent = [];
  }

  return (
    <AppShell>
      <Page className="py-14 sm:py-20">
        <h1 className="max-w-3xl text-display font-semibold tracking-tight text-ink">
          An AI co-founder that works from your actual numbers
        </h1>
        <p className="mt-3 max-w-prose text-body text-ink-muted">
          It researches the market, tells you plainly whether the idea is worth your money,
          and turns what is left into campaigns, stock and a week-by-week plan. No revenue is
          invented.
        </p>

        <div className="mt-10 grid gap-5 lg:grid-cols-2">
          <EntryCard
            href="/new"
            eyebrow="Not launched yet"
            title="I have an idea"
            body="Live market research, the questions it still needs answered, then a GO, PIVOT or NO-GO — before you commit anything."
            steps={["Research", "Verdict", "How to incorporate", "Launch plan"]}
          />
          <EntryCard
            href="/existing"
            eyebrow="Already trading"
            title="I'm running a business"
            body="Your real figures and your order history, analysed — then a plan for the next period built from what they say."
            steps={["Your numbers", "Customer groups", "Next-period plan", "Funding"]}
          />
        </div>

        {recent.length ? (
          <section className="mt-14">
            <div className="mb-4 flex items-baseline justify-between gap-4">
              <h2 className="text-heading font-semibold text-ink">Recent plans</h2>
              <Link
                href="/runs"
                className="text-small text-accent underline-offset-2 hover:underline"
              >
                See all
              </Link>
            </div>
            <ul className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
              {recent.map((run) => (
                <li key={run.id}>
                  <RunLink run={run} />
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </Page>
    </AppShell>
  );
}

function EntryCard({
  href,
  eyebrow,
  title,
  body,
  steps,
}: {
  href: string;
  eyebrow: string;
  title: string;
  body: string;
  steps: string[];
}) {
  return (
    <Link href={href} className="group block">
      <Card className="h-full p-6 transition-colors group-hover:border-line-strong">
        <p className="text-caption font-medium uppercase tracking-wide text-ink-faint">
          {eyebrow}
        </p>
        <h2 className="mt-2 text-title font-semibold text-ink">{title}</h2>
        <p className="mt-2 max-w-prose text-small text-ink-muted">{body}</p>
        <ol className="mt-5 flex flex-wrap gap-x-2 gap-y-1.5 text-caption text-ink-faint">
          {steps.map((step, i) => (
            <li key={step} className="flex items-center gap-2">
              {i > 0 ? <span aria-hidden>→</span> : null}
              {step}
            </li>
          ))}
        </ol>
        <p className="mt-6 text-small font-medium text-accent">
          Start <span aria-hidden>→</span>
        </p>
      </Card>
    </Link>
  );
}

export function RunLink({ run }: { run: Run }) {
  const status = STATUS[run.status] ?? { label: run.status, tone: "neutral" as const };
  return (
    <Link
      href={`/runs/${run.id}`}
      className="block rounded-card border border-line bg-surface px-5 py-4 shadow-card transition-colors hover:border-line-strong"
    >
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <p className="min-w-0 flex-1 text-body font-medium text-ink">
          {run.label ?? `Plan ${run.id}`}
        </p>
        <Pill tone={status.tone}>{status.label}</Pill>
      </div>
      <p className="mt-1 text-caption text-ink-faint">
        {run.mode === "existing_business" ? "Operating business" : "New idea"} ·{" "}
        {relativeTime(run.updated_at)}
      </p>
    </Link>
  );
}

const STATUS: Record<string, { label: string; tone: "neutral" | "go" | "pivot" | "nogo" }> = {
  running: { label: "Working", tone: "neutral" },
  queued: { label: "Queued", tone: "neutral" },
  awaiting_answers: { label: "Needs you", tone: "pivot" },
  done: { label: "Ready", tone: "go" },
  blocked: { label: "Stopped", tone: "pivot" },
  failed: { label: "Failed", tone: "nogo" },
};
