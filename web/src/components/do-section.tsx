/**
 * What to actually do.
 *
 * Framed as the founder's questions, not as the agents' names. Nobody opens a
 * plan looking for "the Sales agent's output"; they are looking for "where do
 * my first customers come from". The agent is still named, as attribution, at
 * the bottom of each block.
 *
 * Every block is laid out the same way -- budget, then the specific items,
 * then the supporting judgement -- so the page has one rhythm rather than four
 * bespoke layouts.
 */

import { AdImage } from "@/components/ad-image";
import { AREA_LABEL } from "@/components/budget-split";
import {
  Attribution,
  Card,
  Empty,
  Judgement,
  Section,
  Warning,
} from "@/components/primitives";
import { asList, count, money } from "@/lib/format";
import type { Marketing, Product, Sales } from "@/lib/types";

function AreaCard({
  question,
  area,
  budget,
  currency,
  adjusted,
  children,
  by,
}: {
  question: string;
  area: keyof typeof AREA_LABEL;
  budget: number;
  currency: string;
  adjusted?: boolean;
  children: React.ReactNode;
  by: string;
}) {
  return (
    <Card as="section" className="overflow-hidden">
      <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-line px-6 py-5">
        <div>
          <h3 className="text-heading font-semibold text-ink">{question}</h3>
          <p className="text-caption text-ink-faint">{AREA_LABEL[area]}</p>
        </div>
        <p className="tnum text-heading font-semibold text-ink">
          {money(budget, currency)}
        </p>
      </header>

      <div className="space-y-6 px-6 py-6">
        {adjusted ? (
          <Warning>
            The spends here were scaled down to fit the {money(budget, currency)} budget.
          </Warning>
        ) : null}
        {children}
        <Attribution agent={by} />
      </div>
    </Card>
  );
}

/** One row of "thing, with its own spend" -- campaigns and lead sources share it. */
function ItemRow({
  title,
  amount,
  currency,
  detail,
  meta,
}: {
  title: string;
  amount?: number;
  currency: string;
  detail: { label: string; value: string }[];
  meta?: string[];
}) {
  return (
    <li className="border-t border-line pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h4 className="text-body font-semibold text-ink">{title}</h4>
        {amount !== undefined ? (
          <span className="tnum text-small font-medium text-ink-muted">
            {money(amount, currency)}
          </span>
        ) : null}
      </div>
      <dl className="mt-2 space-y-1.5">
        {detail.map((d) => (
          <div key={d.label} className="flex gap-2 text-small">
            <dt className="shrink-0 text-ink-faint">{d.label}</dt>
            <dd className="min-w-0 text-ink-muted">{d.value}</dd>
          </div>
        ))}
      </dl>
      {meta?.length ? (
        <p className="mt-2 text-caption text-ink-faint">{meta.filter(Boolean).join(" · ")}</p>
      ) : null}
    </li>
  );
}

export function DoSection({
  marketing,
  sales,
  product,
  currency,
  runId,
}: {
  marketing?: Marketing;
  sales?: Sales;
  product?: Product;
  currency: string;
  runId: number;
}) {
  if (!marketing && !sales && !product) return null;

  return (
    <Section
      id="do"
      title="What to actually do"
      lead="The specific moves this budget buys, and who they are aimed at."
    >
      {/* Two up from xl. Marketing spans both columns because it carries the
          ad image and copy, which need the width; sales and product are lists
          and read better in a narrower measure beside each other. */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2 xl:items-start">
        {marketing ? (
          <div className="xl:col-span-2">
            <MarketingCard marketing={marketing} currency={currency} runId={runId} />
          </div>
        ) : null}
        {sales ? <SalesCard sales={sales} currency={currency} /> : null}
        {product ? <ProductCard product={product} currency={currency} /> : null}
      </div>
    </Section>
  );
}

function MarketingCard({
  marketing,
  currency,
  runId,
}: {
  marketing: Marketing;
  currency: string;
  runId: number;
}) {
  return (
    <AreaCard
      question="How people hear about you"
      area="marketing"
      budget={marketing.budget}
      currency={currency}
      adjusted={marketing.budget_adjusted}
      by="marketing"
    >
      {marketing.campaigns?.length ? (
        <ul className="grid grid-cols-1 gap-x-10 gap-y-4 lg:grid-cols-2">
          {marketing.campaigns.map((campaign, i) => (
            <ItemRow
              key={i}
              title={campaign.channel}
              amount={campaign.budget}
              currency={currency}
              detail={[{ label: "Where", value: campaign.where }]}
              meta={[campaign.ad_format, campaign.objective, campaign.duration]}
            />
          ))}
        </ul>
      ) : (
        <Empty>No campaigns recorded.</Empty>
      )}

      {marketing.ad_copy ? (
        <figure className="rounded-tile border border-line bg-surface-sunken p-5">
          <figcaption className="mb-2.5 text-caption font-medium uppercase tracking-wide text-ink-faint">
            The ad
          </figcaption>
          <div className="flex flex-col gap-5 sm:flex-row">
            {marketing.ad_image_path ? <AdImage runId={runId} /> : null}
            <blockquote className="min-w-0 text-body text-ink">
              {marketing.ad_copy}
            </blockquote>
          </div>
        </figure>
      ) : null}
    </AreaCard>
  );
}

function SalesCard({ sales, currency }: { sales: Sales; currency: string }) {
  return (
    <AreaCard
      question="Where your first customers come from"
      area="sales"
      budget={sales.budget}
      currency={currency}
      adjusted={sales.budget_adjusted}
      by="sales"
    >
      {sales.lead_sources?.length ? (
        <ul className="space-y-4">
          {sales.lead_sources.map((source, i) => (
            <ItemRow
              key={i}
              title={source.where}
              amount={source.budget}
              currency={currency}
              detail={[
                { label: "How", value: source.how },
                { label: "Weekly", value: source.weekly_actions },
              ]}
            />
          ))}
        </ul>
      ) : (
        <Empty>No lead sources recorded.</Empty>
      )}

      {asList(sales.conversion_process).length ? (
        <div>
          <h4 className="mb-3 text-caption font-medium uppercase tracking-wide text-ink-faint">
            From lead to paying customer
          </h4>
          <ol className="space-y-2.5">
            {asList(sales.conversion_process).map((step, i) => (
              <li key={i} className="flex gap-3 text-body text-ink-muted">
                <span className="tnum mt-px w-5 shrink-0 text-small font-semibold text-ink-faint">
                  {i + 1}
                </span>
                <span className="min-w-0">{step}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </AreaCard>
  );
}

function ProductCard({ product, currency }: { product: Product; currency: string }) {
  const isInventory = product.plan_type === "inventory";

  return (
    <AreaCard
      question={isInventory ? "What to buy before you open" : "What you need to deliver"}
      area="product"
      budget={product.budget}
      currency={currency}
      adjusted={product.budget_adjusted}
      by="product"
    >
      {product.line_items?.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] border-collapse text-small">
            <thead>
              <tr className="border-b border-line text-left">
                <th className="pb-2 pr-4 font-medium text-ink-faint">Item</th>
                <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Quantity</th>
                <th className="pb-2 pr-4 text-right font-medium text-ink-faint">Unit cost</th>
                <th className="pb-2 text-right font-medium text-ink-faint">Total</th>
              </tr>
            </thead>
            <tbody>
              {product.line_items.map((item, i) => (
                <tr key={i} className="border-b border-line last:border-0">
                  <td className="py-3 pr-4 text-ink">{item.item}</td>
                  <td className="tnum py-3 pr-4 text-right whitespace-nowrap text-ink-muted">
                    {count(item.units)} × {item.unit}
                  </td>
                  <td className="tnum py-3 pr-4 text-right whitespace-nowrap text-ink-muted">
                    {money(item.unit_cost, currency)}
                  </td>
                  <td className="tnum py-3 text-right whitespace-nowrap font-medium text-ink">
                    {money(item.total_cost, currency)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={3} className="pt-3 pr-4 text-right font-medium text-ink-muted">
                  Total
                </td>
                <td className="tnum pt-3 text-right font-semibold text-ink">
                  {money(product.line_items_total, currency)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      ) : (
        <Empty>No line items recorded.</Empty>
      )}

      {product.cost_basis ? (
        <p className="text-caption text-ink-faint">Cost basis: {product.cost_basis}</p>
      ) : null}

      <div className="grid gap-6 sm:grid-cols-2">
        <div>
          <h4 className="mb-3 text-caption font-medium uppercase tracking-wide text-ink-faint">
            Sourcing
          </h4>
          <Judgement points={asList(product.sourcing_plan)} />
        </div>
        <div>
          <h4 className="mb-3 text-caption font-medium uppercase tracking-wide text-ink-faint">
            {isInventory ? "When to reorder" : "When to add capacity"}
          </h4>
          <Judgement points={asList(product.replenish_policy)} />
        </div>
      </div>
    </AreaCard>
  );
}

