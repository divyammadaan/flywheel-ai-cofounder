/**
 * A form, with a companion panel.
 *
 * A form column alone leaves most of a desktop window empty, and widening the
 * inputs to fill it would be worse -- a 1,200px text field is unusable. The
 * width goes to something that earns it instead: what happens after the
 * founder submits, and what each answer is actually used for. On a laptop it
 * stacks under the form and reads as an intro.
 */

import type { ReactNode } from "react";

import { Card } from "@/components/primitives";

export function FormLayout({
  title,
  lead,
  children,
  aside,
}: {
  title: string;
  lead: string;
  children: ReactNode;
  aside: ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 gap-8 py-12 sm:py-16 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-12 xl:grid-cols-[minmax(0,1fr)_24rem]">
      <div className="min-w-0 max-w-3xl">
        <h1 className="text-display font-semibold tracking-tight text-ink">{title}</h1>
        <p className="mt-2 max-w-prose text-body text-ink-muted">{lead}</p>
        <Card className="mt-8 p-6 sm:p-8">{children}</Card>
      </div>

      <aside className="min-w-0 lg:pt-20">
        <div className="lg:sticky lg:top-8 space-y-6">{aside}</div>
      </aside>
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
              <p className="text-small font-medium text-ink">{step.title}</p>
              <p className="mt-0.5 text-caption leading-relaxed text-ink-muted">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>
      {footnote ? (
        <p className="mt-5 border-t border-line pt-4 text-caption text-ink-faint">{footnote}</p>
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
      <div className="mt-3 space-y-2.5 text-caption leading-relaxed text-ink-muted">
        {children}
      </div>
    </div>
  );
}
