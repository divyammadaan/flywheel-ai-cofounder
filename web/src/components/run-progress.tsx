"use client";

/**
 * Watching a plan being built.
 *
 * A plan takes minutes. A spinner for three minutes is a lie about how much
 * the product knows, so this shows the actual sequence: which agent is working
 * now, which have finished, and how long each took. The founder can tell the
 * difference between "thinking" and "stuck", which a progress bar cannot
 * express.
 *
 * **Resumable by construction.** Events are rows in the database with a
 * sequence number, so this reconnects with `?after_seq=` and replays only what
 * it missed. Reloading the page mid-plan rejoins the run in progress rather
 * than starting the animation over -- and if the stream drops, it falls back
 * to polling rather than silently freezing.
 */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/primitives";
import { API_BASE, api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { agentLabel } from "@/lib/format";
import type { RunEvent, RunStatus } from "@/lib/types";

const FINAL = new Set(["finished", "failed", "blocked", "awaiting_answers"]);

/** The order agents run in, so steps not yet reached can be shown greyed. */
const EXPECTED: Record<string, string[]> = {
  new_idea_start: ["intake", "market_research"],
  new_idea_resume: ["founder_advisor", "company_formation", "planning", "funding"],
  existing_business: ["intake", "planning", "funding"],
};

const STEP_COPY: Record<string, string> = {
  intake: "Reading your description",
  market_research: "Searching the web for competitors and market size",
  founder_advisor: "Weighing it up",
  company_formation: "Working out how to incorporate",
  planning: "Strategy, cash, campaigns, stock and leads",
  funding: "Mapping the road to funding",
};

interface Step {
  agent: string;
  message: string | null;
  startedAt: number | null;
  finishedAt: number | null;
}

export function RunProgress({
  runId,
  status,
  mode,
}: {
  runId: number;
  status: RunStatus;
  mode: string | null;
}) {
  const router = useRouter();
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [disconnected, setDisconnected] = useState(false);
  const lastSeq = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let source: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;

    const absorb = (incoming: RunEvent[]) => {
      if (!incoming.length || cancelled) return;
      lastSeq.current = Math.max(lastSeq.current, ...incoming.map((e) => e.seq));
      setEvents((previous) => {
        const seen = new Set(previous.map((e) => e.seq));
        return [...previous, ...incoming.filter((e) => !seen.has(e.seq))].sort(
          (a, b) => a.seq - b.seq,
        );
      });
      // A terminal event means the page's server-rendered content is now
      // stale -- the plan exists. Refresh rather than re-fetch by hand.
      if (incoming.some((e) => FINAL.has(e.kind))) {
        setTimeout(() => router.refresh(), 400);
      }
    };

    // Catch up on everything that happened before this component mounted.
    api
      .getEvents(runId, 0)
      .then(absorb)
      .catch(() => setDisconnected(true));

    const startPolling = () => {
      if (poll) return;
      setDisconnected(true);
      poll = setInterval(() => {
        api.getEvents(runId, lastSeq.current).then(absorb).catch(() => {});
      }, 2500);
    };

    try {
      source = new EventSource(`${API_BASE}/runs/${runId}/stream?after_seq=0`);
      source.onmessage = (e) => absorb([JSON.parse(e.data)]);
      // Named events (the server sets `event:` to the kind) don't reach
      // onmessage, so each kind is subscribed explicitly.
      for (const kind of [
        "started",
        "agent_started",
        "agent_finished",
        "awaiting_answers",
        "finished",
        "blocked",
        "failed",
      ]) {
        source.addEventListener(kind, (e) => absorb([JSON.parse((e as MessageEvent).data)]));
      }
      source.onopen = () => setDisconnected(false);
      source.onerror = () => {
        source?.close();
        startPolling();
      };
    } catch {
      startPolling();
    }

    return () => {
      cancelled = true;
      source?.close();
      if (poll) clearInterval(poll);
    };
  }, [runId, router]);

  const steps = toSteps(events);
  const expected = expectedFor(mode, status, steps);
  const failure = events.find((e) => e.kind === "failed" || e.kind === "blocked");

  return (
    <Card className="overflow-hidden">
      <header className="flex items-center justify-between gap-4 border-b border-line px-6 py-5">
        <div className="flex items-center gap-3">
          {!failure ? <Pulse /> : null}
          <div>
            <h2 className="text-heading font-semibold text-ink">
              {failure ? "The run stopped" : "Building your plan"}
            </h2>
            <p className="text-caption text-ink-faint">
              {failure
                ? failure.message
                : "This takes a few minutes. You can close the tab and come back."}
            </p>
          </div>
        </div>
      </header>

      <ol className="px-6 py-5">
        {expected.map((agent, i) => {
          const step = steps.get(agent);
          const state = !step
            ? "pending"
            : step.finishedAt
              ? "done"
              : failure
                ? "stopped"
                : "active";
          return (
            <li key={agent} className="flex gap-4 py-2.5">
              <Marker state={state} last={i === expected.length - 1} />
              <div className="min-w-0 flex-1 pb-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                  <p
                    className={cn(
                      "text-body",
                      state === "pending" ? "text-ink-faint" : "text-ink",
                      state === "active" && "font-medium",
                    )}
                  >
                    {agentLabel(agent)}
                  </p>
                  {step?.startedAt && step.finishedAt ? (
                    <span className="tnum text-caption text-ink-faint">
                      {((step.finishedAt - step.startedAt) / 1000).toFixed(1)}s
                    </span>
                  ) : null}
                </div>
                <p className="text-caption text-ink-faint">
                  {step?.message ?? STEP_COPY[agent] ?? ""}
                </p>
              </div>
            </li>
          );
        })}
      </ol>

      {disconnected && !failure ? (
        <p className="border-t border-line px-6 py-3 text-caption text-ink-faint">
          Live updates dropped out — checking every few seconds instead. The run itself is
          unaffected; it is running on the server.
        </p>
      ) : null}
    </Card>
  );
}

function toSteps(events: RunEvent[]): Map<string, Step> {
  const steps = new Map<string, Step>();
  for (const event of events) {
    if (!event.agent) continue;
    const at = event.created_at ? new Date(event.created_at).getTime() : null;
    const existing = steps.get(event.agent) ?? {
      agent: event.agent,
      message: null,
      startedAt: null,
      finishedAt: null,
    };
    if (event.kind === "agent_started") {
      existing.startedAt = at;
      existing.message = event.message;
    }
    if (event.kind === "agent_finished") existing.finishedAt = at;
    steps.set(event.agent, existing);
  }
  return steps;
}

/**
 * Which steps to show, including ones not yet reached.
 *
 * Showing what is coming is the point: it tells the founder how much is left,
 * which a list that grows one row at a time cannot. Any agent that actually
 * ran but was not expected is appended, so the list can never contradict what
 * happened.
 */
function expectedFor(mode: string | null, status: RunStatus, steps: Map<string, Step>): string[] {
  const seen = [...steps.keys()];
  let base: string[];
  if (mode === "existing_business") {
    base = EXPECTED.existing_business;
  } else if (status === "awaiting_answers" || seen.includes("founder_advisor")) {
    base = seen.includes("founder_advisor")
      ? EXPECTED.new_idea_resume
      : EXPECTED.new_idea_start;
  } else {
    base = EXPECTED.new_idea_start;
  }
  return [...base, ...seen.filter((agent) => !base.includes(agent))];
}

function Marker({ state, last }: { state: string; last: boolean }) {
  return (
    <div className="relative flex w-4 shrink-0 justify-center">
      {!last ? (
        <span
          aria-hidden
          className="absolute top-5 bottom-[-0.75rem] w-px bg-line"
        />
      ) : null}
      <span
        aria-hidden
        className={cn(
          "relative mt-1.5 h-3 w-3 rounded-full border-2 bg-surface",
          state === "done" && "border-go bg-go",
          state === "active" && "border-accent",
          state === "pending" && "border-line",
          state === "stopped" && "border-nogo",
        )}
      >
        {state === "active" ? (
          <span className="absolute inset-[-3px] animate-ping rounded-full border border-accent" />
        ) : null}
      </span>
      <span className="sr-only">{state}</span>
    </div>
  );
}

function Pulse() {
  return (
    <span aria-hidden className="relative flex h-2.5 w-2.5">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
      <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-accent" />
    </span>
  );
}
