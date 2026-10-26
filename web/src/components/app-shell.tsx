"use client";

/**
 * The application frame.
 *
 * The first version centred an 896px column on the page, which left a third of
 * a desktop screen empty on each side -- a phone layout stretched onto a
 * monitor. A product occupies its window. So the shell is a persistent left
 * rail plus a content area that fills what is left, and the rail carries real
 * navigation rather than existing to soak up pixels.
 *
 * The rail now carries the founder's actual plans, not just two links to
 * places where plans might be. Two links and a button is a nav bar someone
 * put on the left; a list of the things you have made is the reason to keep a
 * rail on screen at all, and it means getting back to last week's plan is one
 * click from anywhere instead of a trip through /runs.
 *
 * The rail sits on `surface-sunken` and the content on `canvas`, so the two
 * separate tonally rather than by a hard rule. Hit targets are pill-shaped
 * and the type is small and quiet: the rail is for returning to something,
 * and nothing in it should compete with the plan being read.
 *
 * Reading measure is protected per block rather than by starving the whole
 * page: prose caps itself with `max-w-prose`, while figures, tables and
 * charts are free to use the width they were given.
 *
 * Below `lg` the rail collapses to a top bar. There is no drawer: the whole
 * navigation is two links, a button and a theme switch, and a hamburger that
 * opens a panel containing four things is ceremony.
 *
 * A client component throughout -- `usePathname` is what drives the active
 * link, and the plan list is fetched in the browser -- but every screen using
 * it still renders on the server; a server component may pass server-rendered
 * `children` into a client one.
 */

import { Search, SquarePen } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { DeletePlan } from "@/components/delete-plan";
import { RailToggle } from "@/components/rail-toggle";
import { ThemeToggle } from "@/components/theme-toggle";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { planTitle } from "@/lib/format";
import type { Run } from "@/lib/types";

/** How many plans the rail shows at rest before deferring to /runs. */
const RAIL_RUNS = 8;
/** How many it holds for searching -- filtering happens in the browser. */
const SEARCH_POOL = 100;

export function AppShell({
  children,
  aside,
}: {
  children: ReactNode;
  /** Page-specific rail content, e.g. a run's section index. */
  aside?: ReactNode;
}) {
  const pathname = usePathname();
  /*
    Search is a button until it is needed.

    A permanent text field in a 256px rail spends a whole row, every screen,
    on something used occasionally -- and it reads as the rail's primary
    action, which it is not. As an icon beside the collapse control it costs
    nothing until clicked, and the row it would have occupied goes to the
    plans themselves.

    The state lives here rather than in `RecentPlans` because the control and
    the list it filters are in different parts of the rail.
  */
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState("");

  function closeSearch() {
    setSearching(false);
    setQuery("");
  }

  return (
    <div className="flex min-h-full flex-1">
      <aside
        data-rail
        className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col overflow-hidden border-r border-line bg-surface-sunken lg:flex xl:w-72"
      >
        <div data-rail-center className="flex items-center justify-between gap-2 px-4 py-4">
          <span data-rail-hide>
            <Wordmark />
          </span>
          <span className="flex items-center gap-0.5">
            <button
              type="button"
              data-rail-hide
              onClick={() => (searching ? closeSearch() : setSearching(true))}
              title="Search plans"
              aria-label="Search plans"
              aria-expanded={searching}
              className={cn(
                "rounded-tile p-1.5 transition-colors hover:bg-surface hover:text-ink",
                searching ? "bg-surface text-ink" : "text-ink-faint",
              )}
            >
              <Search aria-hidden className="h-4 w-4" strokeWidth={1.75} />
            </button>
            <RailToggle />
          </span>
        </div>

        {/* "New plan" is the rail's one action, so it reads as a row rather
            than as an icon tucked beside the collapse control where it was
            competing with two things that only change the view.

            "All plans" used to sit under it -- a second route to the list
            already in this rail. /runs still exists, and the plan list links
            to it when there are more plans than the rail shows. */}
        <nav className="space-y-0.5 px-2">
          {/* Both lead to the composer: it IS the start of a plan, and a
              separate "New plan" route that opened a form asking the same
              question the composer asks was a second front door to the same
              room. Home keeps its own row because that is the name people
              look for when they want to get back. */}
          <RailLink href="/" icon={SquarePen} active={pathname === "/"}>
            New plan
          </RailLink>
        </nav>

        {searching ? <SearchField value={query} onChange={setQuery} onClose={closeSearch} /> : null}

        {aside ? (
          <div data-rail-hide className="mt-6 px-2">
            {aside}
          </div>
        ) : null}

        <RecentPlans query={query} className="mt-6 min-h-0 flex-1" />

        <div className="mt-auto border-t border-line px-2 py-2">
          <ThemeToggle />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-line bg-canvas px-4 py-3 lg:hidden">
          <Wordmark />
          <nav className="flex items-center gap-1">
            <Link
              href="/runs"
              aria-current={pathname.startsWith("/runs") ? "page" : undefined}
              className={cn(
                "rounded-full px-3 py-1.5 text-small transition-colors",
                pathname.startsWith("/runs")
                  ? "bg-surface-sunken text-ink"
                  : "text-ink-muted hover:bg-surface-sunken hover:text-ink",
              )}
            >
              Your plans
            </Link>
            <Link
              href="/new"
              className="rounded-full bg-accent px-3 py-1.5 text-small font-medium text-white transition-colors hover:bg-accent-hover"
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
 * The founder's plans, in the rail.
 *
 * Fetched in the browser rather than passed down from each page: the rail is
 * on every screen, and threading a runs list through every server component
 * that renders an AppShell would make six pages care about something only the
 * frame uses. A failure here is silent on purpose -- if the API is down, the
 * page itself will say so far more usefully than a broken list in the rail.
 */
function RecentPlans({ query, className }: { query: string; className?: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [runs, setRuns] = useState<Run[] | null>(null);

  useEffect(() => {
    let live = true;
    api
      .listRuns(SEARCH_POOL)
      .then((list) => live && setRuns(list))
      .catch(() => live && setRuns([]));
    return () => {
      live = false;
    };
    // Refetched on navigation so a plan started this session appears without
    // a reload -- starting one is the single most likely reason this list is
    // now out of date.
  }, [pathname]);

  /*
    Search runs over the whole pitch, not the shortened title.

    The title is deliberately the first few words, so searching it would miss
    "Chikmagalur" or "sourdough" -- exactly the words a founder reaches for
    when they are looking for one plan among several that all start the same
    way. Filtering happens here rather than at the API because the pool is
    small enough to hold and a keystroke should not be a round trip.
  */
  const matches = useMemo(() => {
    const all = runs ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return all.slice(0, RAIL_RUNS);
    return all.filter((r) => (r.label ?? `Plan ${r.id}`).toLowerCase().includes(q));
  }, [runs, query]);

  // Nothing to search and nothing to show: keep the rail's spacing, say
  // nothing. A search box over an empty list is furniture.
  if (!runs?.length) return <div className={cn("flex-1", className)} />;

  const hiddenByLimit = !query.trim() && runs.length > RAIL_RUNS;

  return (
    <div data-rail-hide className={cn("flex min-h-0 flex-col px-2", className)}>
      {matches.length === 0 ? (
        <p className="px-3 py-2 text-small text-ink-faint">No plan matches that.</p>
      ) : null}

      <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        {matches.map((run) => {
          const active = pathname === `/runs/${run.id}`;
          return (
            <li key={run.id} className="group/plan relative">
              <Link
                href={`/runs/${run.id}`}
                aria-current={active ? "page" : undefined}
                title={run.label ?? `Plan ${run.id}`}
                className={cn(
                  // The right padding leaves room for the delete control, so
                  // the title truncates before it reaches the bin rather
                  // than sliding under it on hover.
                  // `text-ink`, not `text-ink-muted`. The rail is a list of
                  // things you are choosing between, so its items are content
                  // rather than chrome; at muted weight they read as disabled
                  // next to the page they link to.
                  "flex items-center gap-2 rounded-full py-1.5 pr-9 pl-3 text-small transition-colors",
                  active
                    ? "bg-surface font-medium text-ink"
                    : "text-ink hover:bg-surface",
                )}
              >
                {/* A run that is still working or is stuck on a question is
                    the one thing in this list worth interrupting for. */}
                {run.status === "awaiting_answers" || run.status === "running" ? (
                  <span
                    aria-hidden
                    className={cn(
                      "h-1.5 w-1.5 shrink-0 rounded-full",
                      run.status === "running" ? "bg-accent" : "bg-pivot",
                    )}
                  />
                ) : null}
                <span className="truncate">{planTitle(run.label, run.id)}</span>
              </Link>

              {/* Outside the Link, not inside it: a button nested in an
                  anchor is invalid HTML and clicking it would navigate. It
                  is hidden until the row is hovered or the button itself is
                  focused, so the rail stays quiet, but it is always in the
                  tab order for anyone not using a mouse. */}
              <DeletePlan
                runId={run.id}
                label={planTitle(run.label, run.id)}
                variant="rail"
                onDeleted={() => {
                  setRuns((current) => (current ?? []).filter((r) => r.id !== run.id));
                  // Standing on the plan that just vanished: go somewhere
                  // that still exists rather than leaving a 404 on screen.
                  if (active) router.push("/");
                }}
                className="absolute top-1/2 right-1 -translate-y-1/2 opacity-0 transition-opacity group-hover/plan:opacity-100 focus-within:opacity-100"
              />
            </li>
          );
        })}
      </ul>

      {hiddenByLimit ? (
        <Link
          href="/runs"
          className="mt-1 rounded-full px-3 py-1.5 text-small text-ink-faint transition-colors hover:bg-surface hover:text-ink"
        >
          All {runs.length} plans
        </Link>
      ) : null}
    </div>
  );
}

/**
 * The search field, shown only while searching.
 *
 * Focused on mount, because the founder clicked a magnifier and expects a
 * cursor. Escape closes it and clears the query -- without that the list
 * stays filtered by text nobody can see, which looks like plans have gone
 * missing.
 */
function SearchField({
  value,
  onChange,
  onClose,
}: {
  value: string;
  onChange: (next: string) => void;
  onClose: () => void;
}) {
  const box = useRef<HTMLInputElement>(null);

  useEffect(() => {
    box.current?.focus();
  }, []);

  return (
    <div data-rail-hide className="relative mt-2 px-3">
      <Search
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-6 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint"
        strokeWidth={1.75}
      />
      <input
        ref={box}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
        }}
        placeholder="Search plans"
        aria-label="Search your plans"
        className="w-full rounded-full border border-line bg-surface py-1.5 pr-3 pl-8 text-small text-ink transition-colors placeholder:text-ink-faint focus:border-line-strong focus:outline-none"
      />
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

function RailLink({
  href,
  icon: Icon,
  active,
  children,
}: {
  href: string;
  icon: typeof SquarePen;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      data-rail-center
      title={typeof children === "string" ? children : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-full px-3 py-1.5 text-small transition-colors",
        active ? "bg-surface font-medium text-ink" : "text-ink hover:bg-surface",
      )}
    >
      <Icon aria-hidden className="h-4 w-4 shrink-0" strokeWidth={active ? 2 : 1.75} />
      <span data-rail-hide>{children}</span>
    </Link>
  );
}

/** The name, set as the name. No mark -- a 16px glyph next to it was doing
 *  no work that the word was not already doing better. */
export function Wordmark() {
  return (
    <Link href="/" className="text-body font-semibold tracking-tight text-ink-strong">
      Flywheel
    </Link>
  );
}

/**
 * The section index for a run, in the rail.
 *
 * A plan is 6,500px tall. Without this the only way to reach the funding
 * roadmap is to scroll past everything, and the rail is exactly the space that
 * was empty before.
 *
 * `useActiveSection` tracks which one is on screen via IntersectionObserver,
 * so the index doubles as a reading position indicator on the way down.
 */
export function RunIndex({
  sections,
}: {
  sections: { id: string; label: string }[];
}) {
  const activeId = useActiveSection(sections.map((s) => s.id));
  if (!sections.length) return null;

  return (
    <nav aria-label="Sections of this plan">
      <p className="px-3 pb-1.5 text-caption font-medium text-ink-faint">This plan</p>
      {sections.map((section) => {
        const active = section.id === activeId;
        return (
          <a
            key={section.id}
            href={`#${section.id}`}
            aria-current={active ? "location" : undefined}
            className={cn(
              "relative block rounded-full py-1.5 pr-3 pl-3.5 text-small transition-colors",
              active ? "font-medium text-ink" : "text-ink hover:bg-surface",
            )}
          >
            {active ? (
              <span
                aria-hidden
                className="absolute top-1/2 left-0 h-4 w-0.5 -translate-y-1/2 rounded-full bg-accent"
              />
            ) : null}
            {section.label}
          </a>
        );
      })}
    </nav>
  );
}

function useActiveSection(ids: string[]): string | null {
  const [active, setActive] = useState<string | null>(ids[0] ?? null);
  // The effect keys off this, not `ids` itself: `sectionsOf()` builds a new
  // array on every render, which would otherwise tear the observer down and
  // rebuild it every render instead of once per actual change in sections.
  const key = ids.join(",");

  useEffect(() => {
    if (!ids.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        // The entry closest to the top of the viewport among those
        // currently visible -- a plain "is it intersecting" flags every
        // section on a tall page at once.
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-15% 0px -70% 0px" },
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
    // Intentionally keyed on the stable string `key`, not the array identity
    // of `ids` (see the comment on `key` above).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return active;
}
