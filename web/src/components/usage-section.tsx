/**
 * What this plan cost, and which agents did the work.
 *
 * A genuine claim the project makes -- work is moved into code where code will
 * do, and identical inputs reuse a saved answer -- and a claim with no number
 * behind it is marketing. So the page shows the numbers: model calls, tokens,
 * time and an estimated dollar cost, in total and per agent.
 *
 * The cost is an estimate at the provider's published list price. The free tier
 * charges nothing; the estimate is what the same tokens would cost on a paid plan.
 *
 * Open by default: for a marked project the cost is part of what is shown.
 */

import { Card } from "@/components/primitives";
import { agentLabel, count, seconds, tokens } from "@/lib/format";
import type { Usage } from "@/lib/types";

// Groq's published list price for qwen/qwen3.8-27b, in US dollars per million tokens.
// The same figures docs/EVALUATION.md uses.
const USD_PER_M_INPUT = 0.8;
const USD_PER_M_OUTPUT = 4.0;

function dollars(promptTokens: number, completionTokens: number): number {
  return (promptTokens * USD_PER_M_INPUT + completionTokens * USD_PER_M_OUTPUT) / 1_000_000;
}

function usd(value: number): string {
  if (value === 0) return "$0";
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(3)}`;
}

export function UsageSection({ usage }: { usage: Usage }) {
  if (!usage.agents?.length) return null;

  const { totals } = usage;
  const tokensIn = usage.agents.reduce((sum, a) => sum + (a.prompt_tokens ?? 0), 0);
  const tokensOut = usage.agents.reduce((sum, a) => sum + (a.completion_tokens ?? 0), 0);
  const modelTime = usage.agents.reduce((sum, a) => sum + (a.seconds ?? 0), 0);
  const totalCost = dollars(tokensIn, tokensOut);

  const tiles = [
    { label: "Estimated cost", value: usd(totalCost), note: "at list price; free tier $0" },
    { label: "Model calls", value: count(totals.calls), note: `${usage.agents.length} agents used a model` },
    { label: "Tokens", value: tokens(tokensIn + tokensOut), note: `${tokens(tokensIn)} in · ${tokens(tokensOut)} out` },
    { label: "Model time", value: seconds(modelTime), note: "time spent in model calls" },
  ];

  return (
    <Card as="section">
      <details className="group" open>
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-5">
          <div>
            <h3 className="text-heading font-semibold text-ink">Run metrics</h3>
            <p className="tnum mt-0.5 text-caption text-ink-faint">
              Cost, tokens, time and which agents ran
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
          <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
            {tiles.map((tile) => (
              <div key={tile.label}>
                <dt className="text-caption text-ink-faint">{tile.label}</dt>
                <dd className="tnum mt-1 text-title font-semibold text-ink">{tile.value}</dd>
                <dd className="mt-0.5 text-caption text-ink-faint">{tile.note}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-6 overflow-x-auto">
            <table className="w-full min-w-[36rem] border-collapse text-small">
              <thead>
                <tr className="border-b border-line text-left">
                  <th className="pb-2 pr-4 font-medium text-ink-faint">Agent</th>
                  <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Calls</th>
                  <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Reused</th>
                  <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Tokens in</th>
                  <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Tokens out</th>
                  <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Time</th>
                  <th className="pb-2 text-right font-medium text-ink-faint">Est. cost</th>
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
                    <td className="tnum py-2.5 pr-4 text-right text-ink-muted">
                      {seconds(agent.seconds)}
                    </td>
                    <td className="tnum py-2.5 text-right text-ink-muted">
                      {usd(dollars(agent.prompt_tokens ?? 0, agent.completion_tokens ?? 0))}
                    </td>
                  </tr>
                ))}
                <tr className="border-t border-line">
                  <td className="py-2.5 pr-4 font-medium text-ink">Finance</td>
                  <td className="tnum py-2.5 pr-4 text-right text-ink-muted">0</td>
                  <td className="py-2.5 pr-4 text-right text-ink-muted">—</td>
                  <td className="py-2.5 pr-4 text-right text-ink-muted">—</td>
                  <td className="py-2.5 pr-4 text-right text-ink-muted">—</td>
                  <td className="py-2.5 pr-4 text-right text-ink-muted">—</td>
                  <td className="tnum py-2.5 text-right text-ink-muted">$0</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-caption text-ink-faint">
            Finance makes no model call: its arithmetic and its explanation are both code, so it costs
            nothing. Cost is an estimate at Groq&apos;s list price ($0.80 per million input tokens,
            $4.00 per million output tokens).
          </p>
        </div>
      </details>
    </Card>
  );
}
