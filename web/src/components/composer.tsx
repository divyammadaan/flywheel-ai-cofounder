"use client";

/**
 * The composer.
 *
 * The entry to this product used to be a form: seven fields, two of them
 * required, before anything happened. That is the right shape for the numbers
 * a plan is sized from, but it is the wrong thing to meet someone with. The
 * only thing they can answer without thinking is "what is the business", and
 * that is a sentence, not a field.
 *
 * So the first screen asks for the sentence and nothing else, and the form
 * comes after, already carrying the answer. Nothing was removed -- `/new` and
 * `/existing` still collect exactly what they did -- the order changed.
 *
 * Enter submits and Shift+Enter breaks the line, which is the convention
 * anyone arriving here already has in their hands. The textarea grows with
 * the text rather than scrolling inside a fixed box, capped before it can
 * push the suggestions off screen.
 */

import { ArrowUp } from "lucide-react";

import { MicButton } from "@/components/mic-button";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

type Mode = "new" | "existing";

/*
  Named for what the business IS, not for what the founder is thinking.

  "I have an idea" and "I'm already trading" were the founder's inner
  monologue, which made two buttons that have to be told apart at a glance
  read as two similar-length sentences. A noun is what a choice like this
  wants: two words, obviously exclusive, and the same shape as each other.
*/
const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "new", label: "New business", hint: "Not launched yet — researched and given a verdict first" },
  { id: "existing", label: "Existing business", hint: "Already trading — analysed from your real figures" },
];

/** Enough to be worth researching. The forms enforce the same floor. */
const MIN_LENGTH = 10;
const MAX_HEIGHT = 220;

export function Composer({
  suggestions = [],
}: {
  suggestions?: { label: string; text: string; mode: Mode }[];
}) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [mode, setMode] = useState<Mode>("new");
  const [handedOff, setHandedOff] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);

  const ready = text.trim().length >= MIN_LENGTH;

  // Grow to fit. Reset to `auto` first or the box can only ever get taller:
  // scrollHeight is measured against the height already set.
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [text]);

  function submit(withText = text, withMode = mode) {
    if (withText.trim().length < MIN_LENGTH) return;
    setHandedOff(true);
    const field = withMode === "new" ? "pitch" : "description";
    router.push(`/${withMode}?${field}=${encodeURIComponent(withText.trim())}`);
  }

  return (
    <div>
      <div
        className={cn(
          "rounded-3xl border bg-surface shadow-card transition-colors",
          ready ? "border-line-strong" : "border-line",
          "focus-within:border-line-strong",
        )}
      >
        <label htmlFor="composer" className="sr-only">
          Describe your business
        </label>
        <textarea
          id="composer"
          ref={box}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Describe your business in a sentence or two"
          className="block w-full resize-none bg-transparent px-5 pt-4 pb-2 text-body leading-relaxed text-ink placeholder:text-ink-faint focus:outline-none"
        />

        <div className="flex items-end justify-between gap-3 px-3 pt-1 pb-3">
          <div
            role="radiogroup"
            aria-label="What kind of business is this?"
            className="flex flex-wrap gap-1"
          >
            {MODES.map((option) => {
              const active = option.id === mode;
              return (
                <button
                  key={option.id}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  title={option.hint}
                  onClick={() => setMode(option.id)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-small transition-colors",
                    active
                      ? "border-accent bg-accent-soft font-medium text-accent"
                      : "border-line text-ink-muted hover:bg-surface-sunken hover:text-ink",
                  )}
                >
                  {option.label}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-1.5">
            <MicButton
              onTranscript={(spoken) =>
                setText((current) => (current.trim() ? `${current.trim()} ${spoken}` : spoken))
              }
            />
            <button
              type="button"
              onClick={() => submit()}
              disabled={!ready || handedOff}
              aria-label="Start"
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors",
                ready && !handedOff
                  ? "bg-ink text-canvas hover:opacity-90"
                  : "bg-surface-sunken text-ink-faint",
              )}
            >
              <ArrowUp aria-hidden className="h-4 w-4" strokeWidth={2.25} />
            </button>
          </div>
        </div>
      </div>

      {/* The next screen asks for money, and saying so here is what stops it
          reading as a bait-and-switch when it appears. */}
      <p className="mt-2.5 text-center text-caption text-ink-faint">
        {mode === "new"
          ? "Next: how much capital you're starting with."
          : "Next: your revenue, costs and order history for the period."}
      </p>

      {suggestions.length ? (
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {suggestions.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => {
                setText(s.text);
                setMode(s.mode);
                box.current?.focus();
              }}
              className="rounded-full border border-line px-3.5 py-1.5 text-small text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink"
            >
              {s.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
