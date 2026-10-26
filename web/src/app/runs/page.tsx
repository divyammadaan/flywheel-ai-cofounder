/**
 * Every plan, grouped by when it happened.
 *
 * This screen could not exist before: the engine kept one global table and
 * starting a plan wiped it, so a founder had exactly one plan at a time and
 * no way back to the previous one. Runs made history possible.
 *
 * A grid of same-size cards is what "history" looked like at first, and it
 * read as clutter the moment titles varied in length and a few old test runs
 * sat beside a real one, with no way to tell which was which at a glance. A
 * single list with date headers -- Today, Yesterday, This week -- gives the
 * eye something to anchor on regardless of how many runs pile up, and reads
 * as an actual history rather than a wall of boxes.
 */

import Link from "next/link";

import { AppShell, Page } from "@/components/app-shell";
import { Card } from "@/components/primitives";
import { RunLink } from "@/components/run-link";
import { api } from "@/lib/api";
import { bucketByDay } from "@/lib/format";
import type { Run } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Your plans" };

export default async function RunsPage() {
  let runs: Run[] = [];
  let error: string | null = null;

  try {
    runs = await api.listRuns(100);
  } catch (e) {
    error = (e as Error).message;
  }

  const needsYou = runs.filter((r) => r.status === "awaiting_answers");
  const rest = runs.filter((r) => r.status !== "awaiting_answers");
  const groups = bucketByDay(rest, (r) => r.updated_at);

  return (
    <AppShell>
      <Page width="reading" className="py-12 sm:py-16">
        <h1 className="text-display font-semibold tracking-tight text-ink">Your plans</h1>

        {error ? (
          <Card className="mt-8 p-6">
            <p className="text-body text-ink">{error}</p>
            <p className="mt-3 text-small text-ink-faint">
              Start the API with{" "}
              <code className="rounded bg-surface-sunken px-1.5 py-0.5 font-mono text-caption">
                python -m uvicorn api.main:app --port 8000
              </code>
            </p>
          </Card>
        ) : runs.length === 0 ? (
          <Card className="mt-8 p-8">
            <p className="text-body text-ink">No plans yet.</p>
            <p className="mt-2 text-small text-ink-muted">
              Start with{" "}
              <Link href="/new" className="text-accent underline-offset-2 hover:underline">
                a new idea
              </Link>{" "}
              or{" "}
              <Link href="/existing" className="text-accent underline-offset-2 hover:underline">
                a business you already run
              </Link>
              .
            </p>
          </Card>
        ) : (
          <div className="mt-8 space-y-8">
            {/* Runs paused on a question are surfaced first, out of date
                order: they are stuck until the founder does something, and
                nothing else on the page tells them that. */}
            {needsYou.length ? <RunGroup label="Waiting on you" runs={needsYou} /> : null}

            {groups.map((group) => (
              <RunGroup key={group.label} label={group.label} runs={group.items} />
            ))}
          </div>
        )}
      </Page>
    </AppShell>
  );
}

function RunGroup({ label, runs }: { label: string; runs: Run[] }) {
  return (
    <section>
      <h2 className="mb-3 text-caption font-medium uppercase tracking-wide text-ink-faint">
        {label}
      </h2>
      <Card className="divide-y divide-line overflow-hidden">
        {runs.map((run) => (
          <RunLink key={run.id} run={run} />
        ))}
      </Card>
    </section>
  );
}
