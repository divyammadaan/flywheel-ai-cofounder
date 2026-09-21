/**
 * The application frame.
 *
 * The first version centred an 896px column on the page, which left a third of
 * a desktop screen empty on each side -- a phone layout stretched onto a
 * monitor. A product occupies its window. So the shell is a persistent left
 * rail plus a content area that fills what is left, and the rail carries real
 * navigation rather than existing to soak up pixels.
 *
 * Reading measure is still protected, but per block rather than by starving
 * the whole page: prose caps itself with `max-w-prose`, while figures, tables
 * and charts are free to use the width they were given.
 *
 * Below `lg` the rail collapses to a top bar. There is no drawer: the whole
 * navigation is two links and a button, and a hamburger that opens a panel
 * containing two links is ceremony.
 */

import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function AppShell({
  children,
  aside,
}: {
  children: ReactNode;
  /** Page-specific rail content, e.g. a run's section index. */
  aside?: ReactNode;
}) {
  return (
    <div className="flex min-h-full flex-1">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-surface lg:flex xl:w-72">
        <div className="px-5 py-5">
          <Wordmark />
        </div>

        <div className="px-3">
          <Link
            href="/new"
            className="flex w-full items-center justify-center gap-2 rounded-tile bg-accent px-3 py-2 text-small font-medium text-white transition-colors hover:bg-accent-hover"
          >
            New plan
          </Link>
        </div>

        <nav className="mt-6 px-3">
          <RailLink href="/">Home</RailLink>
          <RailLink href="/runs">Your plans</RailLink>
        </nav>

        {aside ? (
          <div className="mt-8 min-h-0 flex-1 overflow-y-auto px-3 pb-6">{aside}</div>
        ) : (
          <div className="flex-1" />
        )}

        <div className="border-t border-line px-5 py-4">
          <p className="text-caption text-ink-faint">
            Plans are built from your own figures. No revenue is invented.
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-line bg-surface px-4 py-3 lg:hidden">
          <Wordmark />
          <nav className="flex items-center gap-1">
            <Link
              href="/runs"
              className="rounded-tile px-3 py-1.5 text-small text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink"
            >
              Your plans
            </Link>
            <Link
              href="/new"
              className="rounded-tile bg-accent px-3 py-1.5 text-small font-medium text-white transition-colors hover:bg-accent-hover"
            >
              New plan
            </Link>
          </nav>
        </div>

        {children}
      </div>
    </div>
  );
}

/**
 * The content column.
 *
 * `wide` is the default and is what most screens want: it fills the frame and
 * caps only far out, so a 1080p window has no dead margin. `reading` is for a
 * form, where a 1200px-wide input would be absurd.
 */
export function Page({
  children,
  width = "wide",
  className,
}: {
  children: ReactNode;
  width?: "wide" | "reading";
  className?: string;
}) {
  return (
    <main
      className={cn(
        "w-full flex-1 px-4 sm:px-8 xl:px-12",
        width === "wide" ? "mx-auto max-w-[96rem]" : "mx-auto max-w-5xl",
        className,
      )}
    >
      {children}
    </main>
  );
}

/** Prose that should not run to a 1200px measure. */
export function Prose({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("max-w-prose", className)}>{children}</div>;
}

function RailLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="block rounded-tile px-3 py-2 text-small text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink"
    >
      {children}
    </Link>
  );
}

export function Wordmark() {
  return (
    <Link
      href="/"
      className="flex items-center gap-2 text-small font-semibold tracking-tight text-ink"
    >
      <Flywheel />
      Flywheel
    </Link>
  );
}

/** The mark: a wheel mid-turn. Two arcs, not a literal flywheel. */
function Flywheel() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
    >
      <path d="M8 2.2a5.8 5.8 0 0 1 5.32 3.5" />
      <path d="M13.8 3.2v2.8h-2.8" />
      <path d="M8 13.8A5.8 5.8 0 0 1 2.68 10.3" />
      <path d="M2.2 12.8V10h2.8" />
      <circle cx="8" cy="8" r="1.6" />
    </svg>
  );
}

/**
 * The section index for a run, in the rail.
 *
 * A plan is 6,500px tall. Without this the only way to reach the funding
 * roadmap is to scroll past everything, and the rail is exactly the space that
 * was empty before.
 */
export function RunIndex({
  sections,
}: {
  sections: { id: string; label: string }[];
}) {
  if (!sections.length) return null;
  return (
    <nav aria-label="Sections of this plan">
      <p className="px-3 pb-2 text-caption font-medium uppercase tracking-wide text-ink-faint">
        This plan
      </p>
      {sections.map((section) => (
        <a
          key={section.id}
          href={`#${section.id}`}
          className="block rounded-tile px-3 py-1.5 text-small text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink"
        >
          {section.label}
        </a>
      ))}
    </nav>
  );
}
