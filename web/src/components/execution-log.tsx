/**
 * What happened while the plan was built, step by step.
 *
 * The monitoring callbacks on both agent frameworks (observability/callbacks.py)
 * record each intermediate step as a `monitor` event: a model request and its
 * reply, a tool call, a check that cut or refused something, an A2A hand-off, an
 * error. They are the same lines the server prints in its terminal. Shown here
 * because a plan that can be audited should be auditable from the page, not only
 * from a log file.
 *
 * Bottom of the page, collapsed, like the cost table: it is evidence, not the point.
 */

import { Card } from "@/components/primitives";
import { agentLabel } from "@/lib/format";
import type { RunEvent } from "@/lib/types";

const PHASE_LABEL: Record<string, string> = {
  step: "Step",
  task: "Task",
  model: "Model",
  agent: "Agent",
  tool: "Tool",
  guard: "Check",
  error: "Error",
  a2a: "A2A",
};

const MAX_ROWS = 400;

function phaseOf(event: RunEvent): string {
  return typeof event.payload.phase === "string" ? event.payload.phase : "step";
}

function agentOf(event: RunEvent): string {
  return typeof event.payload.agent === "string" ? event.payload.agent : "";
}

/** The event's message without the "agent: " prefix the monitor adds. */
function textOf(event: RunEvent): string {
  const message = event.message ?? "";
  const agent = agentOf(event);
  return agent && message.startsWith(`${agent}: `) ? message.slice(agent.length + 2) : message;
}

export function ExecutionLogSection({ events }: { events: RunEvent[] }) {
  const entries = events.filter((e) => e.kind === "monitor");
  if (!entries.length) return null;

  const shown = entries.slice(0, MAX_ROWS);
  const problems = entries.filter((e) => phaseOf(e) === "error" || phaseOf(e) === "guard").length;

  return (
    <Card as="section">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-5">
          <div>
            <h3 className="text-heading font-semibold text-ink">Execution log</h3>
            <p className="tnum mt-0.5 text-caption text-ink-faint">
              {entries.length} recorded steps
              {problems ? ` · ${problems} checks or errors` : ""}
            </p>
          </div>
          <svg
            aria-hidden
            viewBox="0 0 16 16"
            className="h-4 w-4 shrink-0 fill-ink-faint transition-transform group-open:rotate-180"
          >
            <path d="M8 11 3 6h10l-5 5Z" />
          </svg>
        </summary>

        <div className="border-t border-line px-6 py-6">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[32rem] border-collapse text-small">
              <thead>
                <tr className="border-b border-line text-left">
                  <th className="pb-2 pr-4 font-medium text-ink-faint">Time</th>
                  <th className="pb-2 pr-4 font-medium text-ink-faint">Kind</th>
                  <th className="pb-2 pr-4 font-medium text-ink-faint">Agent</th>
                  <th className="pb-2 font-medium text-ink-faint">What happened</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((event) => (
                  <tr key={event.seq} className="border-b border-line align-top last:border-0">
                    <td className="tnum py-2 pr-4 whitespace-nowrap text-ink-faint">
                      {event.created_at ? event.created_at.slice(11, 19) : ""}
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap text-ink-muted">
                      {PHASE_LABEL[phaseOf(event)] ?? phaseOf(event)}
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap text-ink">
                      {agentOf(event) ? agentLabel(agentOf(event)) : ""}
                    </td>
                    <td className="py-2 text-ink-muted">{textOf(event)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {entries.length > shown.length ? (
            <p className="mt-4 text-caption text-ink-faint">
              Showing the first {shown.length} of {entries.length}.
            </p>
          ) : null}
          <p className="mt-4 text-caption text-ink-faint">
            Recorded by callbacks on both CrewAI and ADK. Times are UTC.
          </p>
        </div>
      </details>
    </Card>
  );
}
