/**
 * What this plan cost in model calls.
 *
 * Kept because it is a genuine claim the project makes -- work is moved into
 * code where code will do, and identical inputs reuse a saved answer -- and a
 * claim with no number behind it is marketing. Cache hits are counted
 * separately from calls because they are the evidence for that claim.
 *
 * Bottom of the page, collapsed: interesting, not the point.
 */

import { Card } from "@/components/primitives";
import { agentLabel, count, seconds, tokens } from "@/lib/format";
import type { Usage } from "@/lib/types";

export function UsageSection({ usage }: { usage: Usage }) {
  if (!usage.agents?.length) return null;

  const { totals } = usage;
  const allTokens = (totals.prompt_tokens ?? 0) + (totals.completion_tokens ?? 0);

  return (
    <Card as="section">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-5">
          <div>
            <h3 className="text-heading font-semibold text-ink">What this cost</h3>
            <p className="tnum mt-0.5 text-caption text-ink-faint">
              {count(totals.calls)} model calls · {tokens(allTokens)} tokens
              {totals.cache_hits ? ` · ${count(totals.cache_hits)} reused from cache` : ""}
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
                  <th className="pb-2 pr-4 font-medium text-ink-faint">Agent</th>
                  <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Calls</th>
                  <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Reused</th>
                  <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Tokens in</th>
                  <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Tokens out</th>
                  <th className="pb-2 text-right font-medium text-ink-faint">Time</th>
                </tr>
              </thead>
              <tbody>
                {usage.agents.map((agent) => (
                  <tr key={agent.agent} className="border-b border-line last:border-0">
                    <td className="py-2.5 pr-4 text-ink">{agentLabel(agent.agent)}</td>
                    <td className="tnum py-2.5 pr-4 text-right text-ink-muted">{agent.calls}</td>
                    <td className="tnum py-2.5 pr-4 text-right text-ink-muted">
                      {agent.cache_hits || "—"}
                    </td>
                    <td className="tnum py-2.5 pr-4 text-right text-ink-muted">
                      {tokens(agent.prompt_tokens)}
                    </td>
                    <td className="tnum py-2.5 pr-4 text-right text-ink-muted">
                      {tokens(agent.completion_tokens)}
                    </td>
                    <td className="tnum py-2.5 text-right text-ink-muted">
                      {seconds(agent.seconds)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-caption text-ink-faint">
            Finance makes no model call at all: its arithmetic and its explanation are both code.
          </p>
        </div>
      </details>
    </Card>
  );
}
