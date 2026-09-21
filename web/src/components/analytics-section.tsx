/**
 * What the founder's own numbers say.
 *
 * Only for an operating business. The headline is the single most important
 * finding and gets the weight; the rest are separate points, because Analytics
 * now returns them as a list rather than a paragraph.
 *
 * The four ratios are computed in `compute_kpis` -- code, not the model -- so
 * they are <Figure>s. Several are genuinely optional: a business that does not
 * track churn gets "not reported", never a zero. A zero churn rate would be a
 * claim about their business that nobody made.
 */

import { Attribution, Card, Figure, FigureGrid, Judgement, Section } from "@/components/primitives";
import { asList, money, percent } from "@/lib/format";
import type { Analytics } from "@/lib/types";

export function AnalyticsSection({ analytics }: { analytics: Analytics }) {
  const kpis = analytics.kpis ?? {};
  const file = analytics.file_metrics as Record<string, unknown> | null;
  const points = analytics.points?.length
    ? analytics.points
    : asList(analytics.summary).slice(1);
  const headline = analytics.headline ?? asList(analytics.summary)[0];

  return (
    <Section
      id="numbers"
      title="What your numbers say"
      lead={analytics.period_label ? `For ${analytics.period_label}.` : undefined}
    >
      <Card className="p-6 sm:p-8">
        {headline ? (
          <p className="mb-7 max-w-3xl text-heading text-ink">{headline}</p>
        ) : null}

        <FigureGrid>
          <Figure
            label="Net margin"
            value={percent(kpis.net_margin ?? null)}
            tone={(kpis.net_margin ?? 0) < 0 ? "caution" : "default"}
            source="Net profit ÷ revenue"
          />
          <Figure
            label="Debt to revenue"
            value={percent(kpis.debt_to_revenue ?? null, 0)}
            source="Of a year's revenue"
          />
          <Figure
            label="Cost per customer"
            value={
              kpis.cac !== null && kpis.cac !== undefined
                ? money(kpis.cac, analytics.currency)
                : "not reported"
            }
            source="Marketing spend ÷ new customers"
          />
          <Figure
            label="Churn"
            value={percent(kpis.churn_rate ?? null)}
            source="Customers lost ÷ customers at start"
          />
        </FigureGrid>

        {points.length ? (
          <div className="mt-8 border-t border-line pt-6">
            <Judgement points={points} />
            <div className="mt-3">
              <Attribution agent="analytics" />
            </div>
          </div>
        ) : null}

        {file ? <FromTheFile file={file} currency={analytics.currency} /> : null}
      </Card>
    </Section>
  );
}

function FromTheFile({ file, currency }: { file: Record<string, unknown>; currency: string }) {
  const n = (key: string) => {
    const value = file[key];
    return typeof value === "number" ? value : null;
  };
  const skipped = n("skipped_rows") ?? 0;

  return (
    <div className="mt-8 rounded-tile border border-line bg-surface-sunken p-5">
      <h3 className="mb-5 text-caption font-medium uppercase tracking-wide text-ink-faint">
        From your uploaded orders
        {file.first_order && file.last_order
          ? ` — ${file.first_order} to ${file.last_order}`
          : ""}
      </h3>
      <FigureGrid>
        <Figure
          label="Orders"
          value={(n("orders") ?? 0).toLocaleString("en-US")}
          source="Rows the file could read"
        />
        <Figure
          label="Customers"
          value={(n("customers") ?? 0).toLocaleString("en-US")}
          source="Distinct names in the file"
        />
        <Figure
          label="Average order"
          value={money(n("average_order_value"), currency)}
          source="Revenue ÷ orders"
        />
        <Figure
          label="Repeat rate"
          value={percent(n("repeat_rate"))}
          source="Customers who ordered more than once"
        />
      </FigureGrid>
      {skipped > 0 ? (
        <p className="mt-4 text-caption text-ink-faint">
          {skipped.toLocaleString("en-US")} rows could not be read and were skipped — usually a
          missing date or amount.
        </p>
      ) : null}
    </div>
  );
}
