"use client";

/**
 * A sequence of steps, read by scrolling.
 *
 * The previous version put four steps in a card, which is a list of things
 * that happen presented as a list of things -- true, and flat. What actually
 * happens is a *sequence*: research, then questions, then a verdict, then a
 * plan, each one depending on the last. So the page is built to be read at
 * the speed it is scrolled, and the sequence is the thing the layout shows.
 *
 * Three pieces do that:
 *
 * - **A line that draws itself.** `useScroll` measures how far through the
 *   section the viewport is and drives the height of the accent line down
 *   the left. It is the progress bar for the story, and it is the reason
 *   four separate steps read as one process.
 * - **Steps that arrive.** Each one fades and rises into place the first
 *   time it is reached -- once, so scrolling back up does not replay it.
 * - **A marker that lights when its step is current.** `useInView` on each
 *   row, so the number you are reading is the number that is lit, and the
 *   ones behind you stay lit rather than resetting.
 *
 * The `data-reveal` and `data-progress-line` attributes are what actually
 * guarantee the last of those. `useReducedMotion` returns false on the first
 * render and settles after, so `initial` is captured hidden before the hook
 * has answered -- and anything below the fold then never un-hides, because
 * the thing that would reveal it is the scrolling the reader is avoiding.
 * The CSS in globals.css keyed off these attributes resolves it before paint.
 *
 * All of it is decoration over an ordered list, and all of it turns off:
 * under `prefers-reduced-motion` the line is simply drawn, every step is
 * simply present, and the content is identical. That is the test -- someone
 * who cannot tolerate motion should lose nothing but the motion.
 */

import { motion, useInView, useReducedMotion, useScroll, useSpring, useTransform } from "motion/react";
import Link from "next/link";
import { useRef } from "react";

export interface TrackStep {
  title: string;
  body: string;
}

export function ScrollTrack({
  eyebrow,
  title,
  lead,
  steps,
  href,
  cta,
}: {
  eyebrow: string;
  title: string;
  lead: string;
  steps: TrackStep[];
  href: string;
  cta: string;
}) {
  const section = useRef<HTMLElement>(null);
  const still = useReducedMotion();

  /*
    `offset` decides when the line is empty and when it is full.

    "end 0.85" -- the section's bottom edge reaching 85% down the viewport --
    rather than something nearer the middle, because the LAST track on the
    page can only scroll until the document ends. With a stricter target its
    line finished at around 58% and simply stopped there, which reads as the
    sequence having been abandoned. The page carries bottom padding for the
    same reason: the final step needs somewhere to scroll to.
  */
  const { scrollYProgress } = useScroll({
    target: section,
    offset: ["start 0.9", "end 0.85"],
  });
  // Springing it stops the line twitching on a trackpad's sub-pixel scrolls.
  const progress = useSpring(scrollYProgress, {
    stiffness: 120,
    damping: 30,
    restDelta: 0.001,
  });
  const height = useTransform(progress, [0, 1], ["0%", "100%"]);

  return (
    <section ref={section} className="scroll-mt-24">
      <motion.div
        data-reveal
        initial={still ? undefined : { opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.5 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <p className="text-caption font-medium uppercase tracking-wide text-accent">{eyebrow}</p>
        <h2 className="mt-2 text-title font-semibold tracking-tight text-ink">{title}</h2>
        <p className="mt-2 max-w-2xl text-small leading-relaxed text-ink-muted">{lead}</p>
      </motion.div>

      <div className="relative mt-8 pl-12">
        {/* The track the line runs in, and the line itself. */}
        <div aria-hidden className="absolute top-2 bottom-2 left-[0.9375rem] w-px bg-line">
          <motion.div
            data-progress-line
            className="w-px bg-accent"
            style={still ? { height: "100%" } : { height }}
          />
        </div>

        <ol className="space-y-9">
          {steps.map((step, i) => (
            <Step key={step.title} index={i} step={step} still={Boolean(still)} />
          ))}
        </ol>
      </div>

      <motion.div
        data-reveal
        className="mt-8 pl-12"
        initial={still ? undefined : { opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true, amount: 0.8 }}
        transition={{ duration: 0.4 }}
      >
        <Link
          href={href}
          className="group inline-flex items-center gap-1.5 text-small font-medium text-accent"
        >
          {cta}
          <span aria-hidden className="transition-transform group-hover:translate-x-0.5">
            →
          </span>
        </Link>
      </motion.div>
    </section>
  );
}

function Step({
  index,
  step,
  still,
}: {
  index: number;
  step: TrackStep;
  still: boolean;
}) {
  const row = useRef<HTMLLIElement>(null);
  // `once` matters as much here as on the animation: without it the markers
  // behind you switch back off as you scroll past, which reads as progress
  // being lost rather than made.
  const reached = useInView(row, { once: true, amount: 0.6 });
  const lit = still || reached;

  return (
    <motion.li
      ref={row}
      data-reveal
      className="relative"
      initial={still ? undefined : { opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.4 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      <span
        aria-hidden
        className={[
          "tnum absolute top-0 -left-12 flex h-8 w-8 items-center justify-center rounded-full border text-small font-semibold transition-colors duration-500",
          lit
            ? "border-accent bg-accent text-white"
            : "border-line bg-surface text-ink-faint",
        ].join(" ")}
      >
        {index + 1}
      </span>

      {/*
        Title and body side by side, not stacked.

        Widening the page on its own does nothing here: the body is capped at
        a readable measure, so a wider column just moves the same narrow
        paragraph further from the edge and leaves more empty space, not
        less. Splitting the row is what actually spends the width -- the
        title takes a fixed column, the body takes the rest, and the two
        together reach the edge of the content area while no line of prose
        gets any longer than it should be.
      */}
      <div className="grid gap-x-8 gap-y-1.5 sm:grid-cols-[13rem_minmax(0,1fr)]">
        <h3 className="text-heading font-semibold text-ink sm:pt-px">{step.title}</h3>
        <p className="text-small leading-relaxed text-ink-muted">{step.body}</p>
      </div>
    </motion.li>
  );
}
