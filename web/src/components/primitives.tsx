/**
 * The primitives every screen is built from.
 *
 * Two of them carry the idea the whole design rests on:
 *
 *   <Figure>    an exact number. Finance computes the reserve, break-even and
 *               budget split in code and makes no model call at all, so these
 *               are arithmetic the founder can bank on. Tabular, heavy, dark,
 *               with a caption naming where the number came from.
 *
 *   <Judgement> a model's opinion. Positioning, campaigns, milestones. Set as
 *               prose, lighter, and always attributed to the agent that wrote
 *               it.
 *
 * The two must never look alike. A founder has to be able to tell at a glance
 * which parts of this plan are arithmetic and which are an argument.
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { NONE_GIVEN, agentLabel } from "@/lib/format";

// --------------------------------------------------------------- layout --

export function Card({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article" | "li";
}) {
  return (
    <Tag
      className={cn(
        "rounded-card border border-line bg-surface shadow-card",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export function Section({
  title,
  lead,
  children,
  action,
  id,
}: {
  title: string;
  lead?: string;
  children: ReactNode;
  action?: ReactNode;
  id?: string;
}) {
  return (
    <section id={id} className="scroll-mt-24">
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-title font-semibold text-ink">{title}</h2>
          {lead ? <p className="mt-1 text-small text-ink-muted">{lead}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Divider({ className }: { className?: string }) {
  return <hr className={cn("border-0 border-t border-line", className)} />;
}

// ----------------------------------------------------- exact vs opinion --

export function Figure({
  label,
  value,
  source,
  tone = "default",
  className,
}: {
  label: string;
  value: ReactNode;
  /** Where the number came from. Omit only when the label already says. */
  source?: string;
  tone?: "default" | "positive" | "caution" | "muted";
  className?: string;
}) {
  const toneClass = {
    default: "text-ink",
    positive: "text-go",
    caution: "text-warning",
    muted: "text-ink-muted",
  }[tone];

  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-caption font-medium uppercase tracking-wide text-ink-faint">
        {label}
      </dt>
      <dd
        className={cn(
          "tnum mt-1.5 text-title font-semibold tracking-tight break-words",
          toneClass,
        )}
      >
        {value}
      </dd>
      {source ? (
        <p className="mt-1 text-caption leading-snug text-ink-faint">{source}</p>
      ) : null}
    </div>
  );
}

export function FigureGrid({
  children,
  columns = 4,
}: {
  children: ReactNode;
  columns?: 2 | 3 | 4;
}) {
  const cols = {
    2: "sm:grid-cols-2",
    3: "sm:grid-cols-2 lg:grid-cols-3",
    4: "sm:grid-cols-2 lg:grid-cols-4",
  }[columns];
  return <dl className={cn("grid grid-cols-1 gap-x-6 gap-y-7", cols)}>{children}</dl>;
}

export function Judgement({
  points,
  by,
  className,
}: {
  points: string[];
  /** The agent that wrote this. Attribution is how provenance is shown. */
  by?: string;
  className?: string;
}) {
  if (!points.length) return <Empty>Nothing recorded.</Empty>;

  return (
    <div className={cn("space-y-3", className)}>
      <ul className="space-y-2.5">
        {points.map((point, i) => (
          <li key={i} className="flex gap-3 text-body text-ink-muted">
            <span
              aria-hidden
              className="mt-[0.6em] h-1 w-1 shrink-0 rounded-full bg-ink-faint"
            />
            <span className="min-w-0">{point}</span>
          </li>
        ))}
      </ul>
      {by ? <Attribution agent={by} /> : null}
    </div>
  );
}

export function Attribution({ agent }: { agent: string }) {
  return (
    <p className="text-caption text-ink-faint">
      Written by the {agentLabel(agent)} agent
    </p>
  );
}

/** Finance's explanation: prose, but computed from its own arithmetic. */
export function ComputedNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-tile border-l-2 border-line-strong bg-surface-sunken px-4 py-3">
      <p className="text-small text-ink-muted">{children}</p>
      <p className="mt-2 text-caption text-ink-faint">
        Computed in code — Finance makes no model call.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- state --

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-small italic text-ink-faint">{children}</p>;
}

export function NotReported({ what }: { what?: string }) {
  return (
    <span className="text-ink-faint">
      {NONE_GIVEN}
      {what ? <span className="sr-only"> {what} not reported</span> : null}
    </span>
  );
}

export function Warning({ children }: { children: ReactNode }) {
  return (
    // min-w-0 + break-words: a provider exception can be one unbroken string
    // thousands of characters long, and without these it pushed the whole page
    // into horizontal scroll.
    <div className="flex min-w-0 gap-2.5 rounded-tile bg-warning-soft px-3.5 py-3 text-small text-ink">
      <svg
        aria-hidden
        viewBox="0 0 16 16"
        className="mt-0.5 h-4 w-4 shrink-0 fill-warning"
      >
        <path d="M8 1.5 15 14H1L8 1.5Zm0 4a.75.75 0 0 0-.75.75v3a.75.75 0 0 0 1.5 0v-3A.75.75 0 0 0 8 5.5Zm0 6.75a.9.9 0 1 0 0-1.8.9.9 0 0 0 0 1.8Z" />
      </svg>
      <span className="min-w-0 break-words">{children}</span>
    </div>
  );
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "go" | "pivot" | "nogo" | "accent";
}) {
  const tones = {
    neutral: "bg-surface-sunken text-ink-muted border-line",
    go: "bg-go-soft text-go border-transparent",
    pivot: "bg-pivot-soft text-pivot border-transparent",
    nogo: "bg-nogo-soft text-nogo border-transparent",
    accent: "bg-accent-soft text-accent border-transparent",
  }[tone];

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-caption font-medium",
        tones,
      )}
    >
      {children}
    </span>
  );
}

// -------------------------------------------------------------- actions --

export function Button({
  children,
  variant = "primary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
}) {
  const variants = {
    primary: "bg-accent text-white hover:bg-accent-hover border-transparent",
    secondary: "bg-surface text-ink hover:bg-surface-sunken border-line",
    ghost: "bg-transparent text-ink-muted hover:text-ink hover:bg-surface-sunken border-transparent",
  }[variant];

  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-tile border px-4 py-2",
        "text-small font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variants,
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function LinkButton({
  children,
  className,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-tile border border-line bg-surface",
        "px-4 py-2 text-small font-medium text-ink transition-colors hover:bg-surface-sunken",
        className,
      )}
      {...props}
    >
      {children}
    </a>
  );
}
