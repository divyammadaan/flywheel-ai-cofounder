/**
 * A form, optionally with a companion panel.
 *
 * The panel used to be mandatory and carried the explaining -- what happens
 * after you submit, what a good description looks like, why it wants running
 * costs. That was three boxes of prose next to a form the founder had already
 * decided to fill in, and it made the screen look like documentation with an
 * input in it. The explaining now lives at /how-it-works, where someone who
 * wants it can read it and everyone else never sees it.
 *
 * Without a panel the form centres in a single column. A form column alone
 * would otherwise leave most of a desktop window empty, and widening the
 * inputs to fill it is worse -- a 1,200px text field is unusable -- so the
 * column is capped and centred rather than stretched.
 *
 * The title and lead sit ABOVE the grid, full width, rather than inside the
 * left column above the card. That is what makes the card and the panel align
 * when there is one: they are then true grid siblings starting at the same
 * row, instead of the panel guessing a top offset (`padding-top: 5rem`, in an
 * earlier version) to match wherever the title happened to push the card down
 * to. A guess like that breaks the moment either side's content changes
 * height -- which is exactly what happened.
 */

import type { ReactNode } from "react";

import { Card } from "@/components/primitives";
import { cn } from "@/lib/cn";

export function FormLayout({
  title,
  lead,
  children,
  aside,
  action,
  /** `bare` hands layout to the child (the stepped form brings its own card). */
  variant = "card",
}: {
  title: string;
  lead?: string;
  children: ReactNode;
  aside?: ReactNode;
  /** A single quiet link beside the title, e.g. to /how-it-works. */
  action?: ReactNode;
  variant?: "card" | "bare";
}) {
  const bare = variant === "bare";
  return (
    <div
      className={cn(
        "py-12 sm:py-16",
        bare ? "mx-auto max-w-5xl" : aside ? undefined : "mx-auto max-w-2xl",
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h1 className="text-display font-semibold tracking-tight text-ink">{title}</h1>
        {action}
      </div>
      {lead ? <p className="mt-2 max-w-prose text-body text-ink-muted">{lead}</p> : null}

      {bare ? (
        <div className="mt-8">{children}</div>
      ) : aside ? (
        <div className="mt-8 grid grid-cols-1 items-start gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-12 xl:grid-cols-[minmax(0,1fr)_24rem]">
          <Card className="min-w-0 p-6 sm:p-8">{children}</Card>

          <aside className="min-w-0">
            <div className="space-y-6 lg:sticky lg:top-8">{aside}</div>
          </aside>
        </div>
      ) : (
        <Card className="mt-8 min-w-0 p-6 sm:p-8">{children}</Card>
      )}
    </div>
  );
}

/** A numbered account of what the run will actually do, in order. */
export function WhatHappensNext({
  steps,
  footnote,
}: {
  steps: { title: string; body: string }[];
  footnote?: string;
}) {
  return (
    <div className="rounded-card border border-line bg-surface-sunken p-5">
      <h2 className="text-caption font-medium uppercase tracking-wide text-ink-faint">
        What happens next
      </h2>
      <ol className="mt-4 space-y-4">
        {steps.map((step, i) => (
          <li key={step.title} className="flex gap-3">
            <span className="tnum mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line text-caption font-semibold text-ink-faint">
              {i + 1}
            </span>
            <div className="min-w-0">
              <p className="text-body font-medium text-ink">{step.title}</p>
              <p className="mt-0.5 text-small leading-relaxed text-ink-muted">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>
      {footnote ? (
        <p className="mt-5 border-t border-line pt-4 text-small text-ink-faint">{footnote}</p>
      ) : null}
    </div>
  );
}

export function SideNote({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-card border border-line p-5">
      <h2 className="text-caption font-medium uppercase tracking-wide text-ink-faint">
        {title}
      </h2>
      <div className="mt-3 space-y-2.5 text-small leading-relaxed text-ink-muted">
        {children}
      </div>
    </div>
  );
}
