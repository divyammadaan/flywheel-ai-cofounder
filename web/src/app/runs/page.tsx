/**
 * Every plan, newest first.
 *
 * This screen could not exist before: the engine kept one global table and
 * starting a plan wiped it, so a founder had exactly one plan at a time and no
 * way back to the previous one. Runs made history possible, and this is where
 * it shows.
 */

import Link from "next/link";

import { AppShell, Page } from "@/components/app-shell";
import { RunLink } from "@/app/page";
import { Card } from "@/components/primitives";
import { api } from "@/lib/api";
import type { Run } from "@/lib/types";

export const dynamic = "force-dynamic";

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

  return (
    <AppShell>
      <Page className="py-12 sm:py-16">
        <h1 className="text-display font-semibold tracking-tight text-ink">Your plans</h1>

        {error ? (
          <Card className="mt-8 max-w-2xl p-6">
            <p className="text-body text-ink">{error}</p>
            <p className="mt-3 text-small text-ink-faint">
              Start the API with{" "}
              <code className="rounded bg-surface-sunken px-1.5 py-0.5 font-mono text-caption">
                python -m uvicorn api.main:app --port 8000
              </code>
            </p>
          </Card>
        ) : runs.length === 0 ? (
          <Card className="mt-8 max-w-2xl p-8">
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
          <div className="mt-8 space-y-10">
            {/* Runs paused on a question are surfaced first: they are stuck
                until the founder does something, and nothing else tells them. */}
            {needsYou.length ? (
              <section>
                <h2 className="mb-3 text-heading font-semibold text-ink">Waiting on you</h2>
                <ul className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
                  {needsYou.map((run) => (
                    <li key={run.id}>
                      <RunLink run={run} />
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section>
              {needsYou.length ? (
                <h2 className="mb-3 text-heading font-semibold text-ink">Everything else</h2>
              ) : null}
              <ul className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
                {rest.map((run) => (
                  <li key={run.id}>
                    <RunLink run={run} />
                  </li>
                ))}
              </ul>
            </section>
          </div>
        )}
      </Page>
    </AppShell>
  );
}
