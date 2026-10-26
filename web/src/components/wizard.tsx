"use client";

/**
 * A form in steps.
 *
 * The business-review form asks for fourteen figures. As one column in one
 * card that is roughly two and a half screens of scrolling before the founder
 * reaches the button, with the whole right half of a laptop window empty
 * beside it -- a long form and a wide gap at the same time, which is the
 * worst of both.
 *
 * Splitting it fixes both at once. Each step is short enough to sit on one
 * screen, and the width that was empty goes to the progress rail: which steps
 * there are, which one you are on, and which are done. That is navigation, not
 * prose -- the explaining lives at /how-it-works and deliberately did not come
 * back here.
 *
 * Nothing is hidden or dropped. Every field the form asked for is still
 * asked for, on the step it belongs to.
 *
 * Three details that matter more than they look:
 *
 * - **Enter does not submit early.** A single `<form>` wraps every step, so
 *   Enter in a text field fires submit -- which on step one would post a form
 *   missing most of its answers. `onSubmit` advances instead, and only
 *   actually submits on the last step.
 * - **State lives in the parent.** Steps that are not showing are not
 *   rendered, so the inputs unmount; the values have to outlive them.
 * - **You can go back, but not skip ahead.** A visited step is a link; an
 *   unreached one is not, because the steps after it depend on answers it
 *   has not collected yet.
 */

import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Card } from "@/components/primitives";
import { cn } from "@/lib/cn";

export interface WizardStep {
  /** Short enough for the rail: two or three words. */
  label: string;
  /** False while this step's required fields are unanswered. */
  complete: boolean;
  content: ReactNode;
}

export function Wizard({
  steps,
  onSubmit,
  submitting,
  submitLabel,
  submittingLabel = "Starting…",
  error,
  initialStep = 0,
}: {
  steps: WizardStep[];
  onSubmit: () => void;
  submitting?: boolean;
  submitLabel: string;
  submittingLabel?: string;
  error?: ReactNode;
  /**
   * Start past the steps the founder has already answered elsewhere.
   *
   * The composer on the home page collects the description, so landing on
   * step one and being asked for it again reads as the product having
   * forgotten. The step is still there and still in the rail -- it opens
   * already answered, one click back -- it just is not what greets them.
   */
  initialStep?: number;
}) {
  const [index, setIndex] = useState(initialStep);
  // The furthest step reached, so going back does not re-lock the ones after,
  // and so a skipped-but-answered step is navigable rather than dead.
  const [furthest, setFurthest] = useState(initialStep);

  const step = steps[index];
  const last = index === steps.length - 1;
  const canAdvance = step.complete;

  function goTo(next: number) {
    setIndex(next);
    setFurthest((f) => Math.max(f, next));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!last) {
      if (canAdvance) goTo(index + 1);
      return;
    }
    onSubmit();
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-10"
    >
      <StepRail
        steps={steps}
        index={index}
        furthest={furthest}
        onPick={(i) => setIndex(i)}
      />

      <Card className="min-w-0 p-6 sm:p-8">
        <div className="min-h-[19rem]">
          <h2 className="text-heading font-semibold text-ink">{step.label}</h2>
          <div className="mt-5">{step.content}</div>
        </div>

        {error ? <div className="mt-6">{error}</div> : null}

        <div className="mt-7 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6">
          <button
            type="button"
            onClick={() => goTo(index - 1)}
            disabled={index === 0}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-small font-medium transition-colors",
              index === 0
                ? "invisible"
                : "text-ink-muted hover:bg-surface-sunken hover:text-ink",
            )}
          >
            <ArrowLeft aria-hidden className="h-4 w-4" strokeWidth={2} />
            Back
          </button>

          <div className="flex items-center gap-4">
            <button
              type="submit"
              disabled={submitting || !canAdvance}
              className={cn(
                "group inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-small font-medium transition-colors",
                submitting || !canAdvance
                  ? "cursor-not-allowed bg-surface-sunken text-ink-faint"
                  : "bg-accent text-white hover:bg-accent-hover",
              )}
            >
              {last ? (submitting ? submittingLabel : submitLabel) : "Continue"}
              {!submitting ? (
                <ArrowRight
                  aria-hidden
                  className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
                  strokeWidth={2}
                />
              ) : null}
            </button>
          </div>
        </div>
      </Card>
    </form>
  );
}

/**
 * The steps, down the left.
 *
 * On a phone there is no left, so the same information collapses to a row of
 * bars and a "Step 2 of 3" -- the labels would not fit, and the one thing
 * worth keeping at that width is how much is left.
 */
function StepRail({
  steps,
  index,
  furthest,
  onPick,
}: {
  steps: WizardStep[];
  index: number;
  furthest: number;
  onPick: (i: number) => void;
}) {
  return (
    <nav aria-label="Progress" className="lg:sticky lg:top-8">
      {/* Phone and tablet */}
      <div className="lg:hidden">
        <div className="flex items-center gap-1.5">
          {steps.map((s, i) => (
            <span
              key={s.label}
              className={cn(
                "h-1 flex-1 rounded-full transition-colors",
                i <= index ? "bg-accent" : "bg-line",
              )}
            />
          ))}
        </div>
        <p className="mt-2.5 text-small text-ink-muted">
          Step {index + 1} of {steps.length}
          <span className="text-ink-faint"> · {steps[index].label}</span>
        </p>
      </div>

      {/* Laptop and up */}
      <ol className="hidden lg:block">
        {steps.map((s, i) => {
          const current = i === index;
          const done = s.complete && i < furthest;
          const reachable = i <= furthest;
          const isLast = i === steps.length - 1;

          return (
            <li key={s.label} className="relative flex gap-3 pb-6 last:pb-0">
              {/* The connector, drawn behind the markers. */}
              {!isLast ? (
                <span
                  aria-hidden
                  className={cn(
                    "absolute top-7 left-[0.6875rem] h-[calc(100%-1.75rem)] w-px",
                    done ? "bg-accent/40" : "bg-line",
                  )}
                />
              ) : null}

              <span
                className={cn(
                  "tnum relative z-10 flex h-[1.375rem] w-[1.375rem] shrink-0 items-center justify-center rounded-full border text-caption font-semibold transition-colors",
                  current
                    ? "border-accent bg-accent text-white"
                    : done
                      ? "border-accent/40 bg-accent-soft text-accent"
                      : "border-line bg-surface text-ink-faint",
                )}
              >
                {done ? <Check aria-hidden className="h-3 w-3" strokeWidth={3} /> : i + 1}
              </span>

              {reachable && !current ? (
                <button
                  type="button"
                  onClick={() => onPick(i)}
                  className="-mt-0.5 text-left text-small text-ink-muted transition-colors hover:text-ink"
                >
                  {s.label}
                </button>
              ) : (
                <span
                  aria-current={current ? "step" : undefined}
                  className={cn(
                    "-mt-0.5 text-small",
                    current ? "font-medium text-ink" : "text-ink-faint",
                  )}
                >
                  {s.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
