"use client";

/**
 * How the budget is divided.
 *
 * Form: one stacked horizontal bar, because the founder's question is
 * "how is my money being cut up?" -- a part-to-whole question, not a ranking.
 * Reading an exact figure off a stacked segment is hard, so the bar carries
 * the *shape* and the figures underneath carry the *precision*. That pairing
 * is also what discharges the light-mode contrast warning on two of the hues:
 * every series is directly labelled with its own amount.
 *
 * The unallocated remainder is a real and easily-missed fact --
 * `compute_capped_allocation` caps any one area at 60% of the budget, so money
 * can be left over. It is drawn in neutral grey, not a fifth hue, because it
 * is an absence rather than an entity.
 *
 * Palette: slots 1-4 of the validated categorical set, in fixed order, stepped
 * separately for dark. Verified with the skill's validator against both
 * surfaces (worst adjacent CVD ΔE 9.1 light / 8.4 dark).
 */

import { useId, useState } from "react";

import { cn } from "@/lib/cn";
import { money, percent } from "@/lib/format";

export const AREA_ORDER = ["marketing", "product", "sales", "crm"] as const;
export type Area = (typeof AREA_ORDER)[number];

export const AREA_LABEL: Record<Area, string> = {
  marketing: "Marketing",
  product: "Product",
  sales: "Sales",
  crm: "CRM",
};

interface Slice {
  key: Area | "unallocated";
  label: string;
  amount: number;
  share: number;
}

export function BudgetSplit({
  total,
  amounts,
  currency,
  capShare,
}: {
  total: number;
  amounts: Record<string, number>;
  currency: string;
  /** The per-area cap, for explaining a remainder. 0.6 in the engine. */
  capShare?: number;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const titleId = useId();

  const allocated = AREA_ORDER.reduce((sum, area) => sum + (amounts[area] ?? 0), 0);
  const remainder = Math.max(0, total - allocated);

  const slices: Slice[] = [
    ...AREA_ORDER.map((area) => ({
      key: area,
      label: AREA_LABEL[area],
      amount: amounts[area] ?? 0,
      share: total > 0 ? (amounts[area] ?? 0) / total : 0,
    })),
    ...(remainder > 0.5
      ? [
          {
            key: "unallocated" as const,
            label: "Unallocated",
            amount: remainder,
            share: total > 0 ? remainder / total : 0,
          },
        ]
      : []),
  ].filter((slice) => slice.amount > 0);

  if (!slices.length) return null;

  return (
    <div className="viz-budget">
      <style>{`
        .viz-budget {
          --series-marketing: #2a78d6;
          --series-product:   #eb6834;
          --series-sales:     #1baf7a;
          --series-crm:       #eda100;
          --series-unallocated: oklch(0.85 0.005 85);
        }
        @media (prefers-color-scheme: dark) {
          :root:where(:not([data-theme="light"])) .viz-budget {
            --series-marketing: #3987e5;
            --series-product:   #d95926;
            --series-sales:     #199e70;
            --series-crm:       #c98500;
            --series-unallocated: oklch(0.36 0.009 75);
          }
        }
        :root[data-theme="dark"] .viz-budget {
          --series-marketing: #3987e5;
          --series-product:   #d95926;
          --series-sales:     #199e70;
          --series-crm:       #c98500;
          --series-unallocated: oklch(0.36 0.009 75);
        }
      `}</style>

      <h3 id={titleId} className="sr-only">
        How the {money(total, currency)} budget is divided
      </h3>

      {/* gap-[2px]: the surface shows between segments, so two fills never
          touch and the boundary is never mistaken for a colour change. */}
      <div
        className="flex h-11 w-full gap-[2px] overflow-hidden rounded-tile"
        role="img"
        aria-labelledby={titleId}
      >
        {slices.map((slice) => (
          <div
            key={slice.key}
            className={cn(
              "relative min-w-[3px] transition-opacity duration-150",
              hovered && hovered !== slice.key && "opacity-40",
            )}
            style={{
              width: `${Math.max(slice.share * 100, 0.6)}%`,
              backgroundColor: `var(--series-${slice.key})`,
            }}
            onMouseEnter={() => setHovered(slice.key)}
            onMouseLeave={() => setHovered(null)}
          >
            <span className="sr-only">
              {slice.label}: {money(slice.amount, currency)}, {percent(slice.share, 0)}
            </span>
          </div>
        ))}
      </div>

      {/* The legend doubles as the direct labels: identity is never colour
          alone, and every value is visible without hovering. */}
      <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-5">
        {slices.map((slice) => (
          <div
            key={slice.key}
            className={cn(
              "min-w-0 transition-opacity duration-150",
              hovered && hovered !== slice.key && "opacity-40",
            )}
            onMouseEnter={() => setHovered(slice.key)}
            onMouseLeave={() => setHovered(null)}
          >
            <dt className="flex items-center gap-2 text-caption font-medium text-ink-muted">
              <span
                aria-hidden
                className="h-2.5 w-2.5 shrink-0 rounded-[3px]"
                style={{ backgroundColor: `var(--series-${slice.key})` }}
              />
              <span className="truncate">{slice.label}</span>
            </dt>
            <dd className="tnum mt-1 text-heading font-semibold text-ink">
              {money(slice.amount, currency)}
            </dd>
            <dd className="tnum text-caption text-ink-faint">{percent(slice.share, 0)}</dd>
          </div>
        ))}
      </dl>

      {remainder > 0.5 && capShare ? (
        <p className="mt-4 text-small text-ink-muted">
          {money(remainder, currency)} is unallocated: no single area may take more than{" "}
          {percent(capShare, 0)} of the budget, so the split stops short of the total.
        </p>
      ) : null}
    </div>
  );
}
