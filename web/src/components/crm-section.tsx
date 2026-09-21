"use client";

/**
 * Customers, and who is slipping away.
 *
 * The old version was a six-column table. A table answers "what are the
 * numbers"; a founder opening this is asking "who is leaving, what are they
 * worth, and what do I say to them" -- so the page leads with revenue at
 * risk, then the split, then the named people worth a phone call.
 *
 * **Why two colours and not five.** The five groups are *states* on a health
 * axis, not five identities, so painting them five categorical hues would
 * imply a distinction that isn't there -- and a five-hue set with best and
 * regular adjacent fails the colour-blindness floor outright (checked). The
 * chart therefore encodes the one split that drives action: still ordering
 * against at risk. The groups themselves are a list, where the label leads and
 * the colour is a status dot beside it.
 *
 * Everything here is computed in `agents/_segments.py` -- who is in which
 * group is arithmetic on the founder's own order history, with cut-offs
 * scaled to how often *their* customers re-order. The model only writes the
 * actions and the messages, and it runs locally so the customer list never
 * leaves the machine.
 */

import { useState } from "react";

import {
  Attribution,
  Card,
  Empty,
  Figure,
  FigureGrid,
  Section,
  Warning,
} from "@/components/primitives";
import { RefineControl } from "@/components/refine-control";
import { cn } from "@/lib/cn";
import { count, money, percent } from "@/lib/format";
import type { Crm, SegmentMeta } from "@/lib/types";

const AT_RISK = ["slipping", "lost"];
const ORDER = ["best", "regular", "new", "slipping", "lost"];

const DOT: Record<string, string> = {
  best: "bg-go",
  regular: "bg-go/60",
  new: "bg-ink-faint",
  slipping: "bg-warning",
  lost: "bg-nogo",
};

export function CrmSection({
  crm,
  currency,
  meta,
  runId,
  cycle,
  revised,
}: {
  crm: Crm;
  currency: string;
  meta?: SegmentMeta;
  runId: number;
  cycle: number;
  revised: boolean;
}) {
  const segments = crm.segments;
  if (!segments?.segments) return null;

  const order = meta?.order?.length ? meta.order : ORDER;
  const labels = meta?.labels ?? {};
  const definitions = meta?.definitions ?? {};

  const totalRevenue = order.reduce((sum, key) => sum + (segments.segments[key]?.revenue ?? 0), 0);
  const atRiskRevenue = AT_RISK.reduce(
    (sum, key) => sum + (segments.segments[key]?.revenue ?? 0),
    0,
  );
  const atRiskCustomers = AT_RISK.reduce(
    (sum, key) => sum + (segments.segments[key]?.customers ?? 0),
    0,
  );
  const healthyCustomers = segments.customers - atRiskCustomers;

  return (
    <Section
      id="crm"
      title="Your customers"
      lead="Who is still ordering, who has gone quiet, and what to send them."
    >
      <Card className="overflow-hidden">
        <div className="px-6 py-6 sm:px-8">
          {crm.warnings?.length ? (
            <div className="mb-6 space-y-2.5">
              {crm.warnings.map((w, i) => (
                <Warning key={i}>{w}</Warning>
              ))}
            </div>
          ) : null}

          <FigureGrid columns={3}>
            <Figure
              label="Revenue at risk"
              value={money(atRiskRevenue, currency)}
              tone={atRiskRevenue > totalRevenue * 0.25 ? "caution" : "default"}
              source={
                totalRevenue
                  ? `${percent(atRiskRevenue / totalRevenue, 0)} of everything these customers have spent`
                  : "From your uploaded orders"
              }
            />
            <Figure
              label="Customers at risk"
              value={count(atRiskCustomers)}
              source={`Of ${count(segments.customers)} in your order history`}
            />
            <Figure
              label="They re-order every"
              value={`${segments.typical_gap_days} days`}
              source={
                segments.gap_measured
                  ? "Measured from your own repeat customers"
                  : "Assumed — too few repeat customers to measure"
              }
            />
          </FigureGrid>

          <HealthBar
            healthy={healthyCustomers}
            atRisk={atRiskCustomers}
            currency={currency}
            healthyRevenue={totalRevenue - atRiskRevenue}
            atRiskRevenue={atRiskRevenue}
          />

          <ul className="mt-8 border-t border-line">
            {order.map((key) => {
              const stat = segments.segments[key];
              if (!stat) return null;
              return (
                <SegmentRow
                  key={key}
                  segmentKey={key}
                  label={labels[key] ?? stat.label}
                  definition={definitions[key]}
                  customers={stat.customers}
                  change={crm.changes?.[key]}
                  revenueShare={stat.revenue_share}
                  action={crm.actions?.[key]}
                  spend={crm.spend?.[key]}
                  currency={currency}
                />
              );
            })}
          </ul>

          <p className="mt-4 text-caption text-ink-faint">
            As of {segments.as_of}. Groups are computed from your order file; the actions and
            messages are written by a model running locally, so your customer list never
            leaves this machine.
          </p>
        </div>

        {segments.top_slipping?.length ? (
          <div className="border-t border-line bg-surface-sunken px-6 py-6 sm:px-8">
            <h3 className="text-heading font-semibold text-ink">
              Worth a personal call
            </h3>
            <p className="mt-1 text-small text-ink-muted">
              Your biggest spenders who have gone quiet. A message from a template will not
              hold these.
            </p>
            <ul className="mt-5 space-y-3">
              {segments.top_slipping.map((person) => (
                <li
                  key={person.customer}
                  className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-line pb-3 last:border-0 last:pb-0"
                >
                  <span className="text-body font-medium text-ink">{person.customer}</span>
                  <span className="tnum text-small text-ink-muted">
                    {money(person.spent, currency)} over {count(person.orders)} orders ·{" "}
                    <span className="text-warning">{person.days_since_last_order} days quiet</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="grid gap-5 border-t border-line px-6 py-6 sm:grid-cols-2 sm:px-8">
          <CopyBlock
            title="To customers slipping away"
            message={crm.slipping_message}
          />
          <CopyBlock title="To win back lost customers" message={crm.lost_message} />
        </div>

        <div className="space-y-3 border-t border-line px-6 py-4 sm:px-8">
          <Attribution agent="crm" />
          <RefineControl runId={runId} agent="crm" cycle={cycle} revised={revised} />
        </div>
      </Card>
    </Section>
  );
}

/**
 * Still ordering against at risk.
 *
 * Two colours, both directly labelled with their own count and revenue --
 * required, because green/red sits in the 6-8 colour-blindness band where
 * colour alone is not allowed to carry the meaning.
 */
function HealthBar({
  healthy,
  atRisk,
  healthyRevenue,
  atRiskRevenue,
  currency,
}: {
  healthy: number;
  atRisk: number;
  healthyRevenue: number;
  atRiskRevenue: number;
  currency: string;
}) {
  const total = healthy + atRisk;
  if (!total) return null;

  return (
    <div className="viz-health mt-8">
      <style>{`
        .viz-health { --healthy: #1baf7a; --at-risk: #e34948; }
        @media (prefers-color-scheme: dark) {
          :root:where(:not([data-theme="light"])) .viz-health {
            --healthy: #199e70; --at-risk: #e66767;
          }
        }
        :root[data-theme="dark"] .viz-health { --healthy: #199e70; --at-risk: #e66767; }
      `}</style>

      <div className="flex h-2.5 w-full gap-[2px] overflow-hidden rounded-full" role="img"
        aria-label={`${healthy} customers still ordering, ${atRisk} at risk`}>
        <div style={{ width: `${(healthy / total) * 100}%`, backgroundColor: "var(--healthy)" }} />
        <div style={{ width: `${(atRisk / total) * 100}%`, backgroundColor: "var(--at-risk)" }} />
      </div>

      <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-2">
        <Legend
          swatch="var(--healthy)"
          label="Still ordering"
          value={`${count(healthy)} · ${money(healthyRevenue, currency)}`}
        />
        <Legend
          swatch="var(--at-risk)"
          label="Slipping or lost"
          value={`${count(atRisk)} · ${money(atRiskRevenue, currency)}`}
        />
      </dl>
    </div>
  );
}

function Legend({ swatch, label, value }: { swatch: string; label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-2 text-caption text-ink-muted">
        <span
          aria-hidden
          className="h-2.5 w-2.5 shrink-0 rounded-[3px]"
          style={{ backgroundColor: swatch }}
        />
        {label}
      </dt>
      <dd className="tnum mt-0.5 pl-[1.125rem] text-small font-medium text-ink">{value}</dd>
    </div>
  );
}

function SegmentRow({
  segmentKey,
  label,
  definition,
  customers,
  change,
  revenueShare,
  action,
  spend,
  currency,
}: {
  segmentKey: string;
  label: string;
  definition?: string;
  customers: number;
  change?: number;
  revenueShare: number | null;
  action?: string;
  spend?: number;
  currency: string;
}) {
  return (
    <li className="border-b border-line py-4 last:border-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="flex items-center gap-2">
          <span aria-hidden className={cn("h-2 w-2 shrink-0 rounded-full", DOT[segmentKey])} />
          <span className="text-body font-medium text-ink" title={definition}>
            {label}
          </span>
        </span>
        <span className="tnum text-small text-ink-muted">{count(customers)}</span>
        {change !== undefined && change !== 0 ? (
          <span
            className={cn(
              "tnum text-caption font-medium",
              change > 0 ? "text-go" : "text-warning",
            )}
          >
            {change > 0 ? "+" : ""}
            {change} since last period
          </span>
        ) : null}
        {revenueShare !== null ? (
          <span className="tnum text-caption text-ink-faint">
            {percent(revenueShare, 0)} of revenue
          </span>
        ) : null}
        {spend ? (
          <span className="tnum ml-auto text-small text-ink-muted">
            {money(spend, currency)} budgeted
          </span>
        ) : null}
      </div>
      {action ? <p className="mt-1.5 pl-4 text-small text-ink-muted">{action}</p> : null}
      {definition ? (
        <p className="mt-1 pl-4 text-caption text-ink-faint">{definition}</p>
      ) : null}
    </li>
  );
}

/** A ready-to-send message, with copying as the primary action. */
function CopyBlock({ title, message }: { title: string; message?: string }) {
  const [copied, setCopied] = useState(false);

  if (!message) return <Empty>No message written.</Empty>;

  async function copy() {
    try {
      await navigator.clipboard.writeText(message!);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard is blocked outside a secure context; the text is selectable
      // anyway, so this fails quietly rather than shouting at the founder.
    }
  }

  return (
    <div className="min-w-0">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h4 className="text-caption font-medium uppercase tracking-wide text-ink-faint">
          {title}
        </h4>
        <button
          type="button"
          onClick={copy}
          className="text-caption font-medium text-accent transition-colors hover:text-accent-hover"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <p className="rounded-tile border border-line bg-surface-sunken px-4 py-3 text-small leading-relaxed text-ink">
        {message}
      </p>
    </div>
  );
}
