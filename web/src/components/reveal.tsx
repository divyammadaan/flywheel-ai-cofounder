"use client";

/**
 * Content that arrives as you scroll to it.
 *
 * Built on `motion` (Framer Motion's successor). `whileInView` with
 * `viewport.once` is the whole mechanism: the element starts slightly down
 * and transparent, and animates to its resting position the first time it
 * crosses into view. Once, not every time -- a card that re-animates each
 * time it scrolls past is a page that will not sit still.
 *
 * `data-reveal` is the belt to the hook's braces, and it is not paranoia:
 * `useReducedMotion` returns false on the very first render and only settles
 * afterwards, so `initial` is captured as hidden before the hook has spoken.
 * For anything already on screen that is invisible -- `whileInView` fires
 * immediately -- but content further down stays at opacity 0 until it is
 * scrolled to, which for a reduced-motion reader is a blank page. The CSS in
 * globals.css keyed off this attribute settles it before paint, with no
 * dependence on render order.
 *
 * `useReducedMotion` is not optional either. Someone who has asked their OS to
 * stop animations has usually done so because motion makes them ill, and a
 * page of things sliding around is exactly what they turned it off for. For
 * them the content simply appears, with no transform and no delay -- the
 * information is identical either way, which is the test any decoration like
 * this has to pass.
 */

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  /** Seconds. Used to stagger siblings so they arrive in reading order. */
  delay?: number;
  className?: string;
}) {
  const still = useReducedMotion();

  return (
    <motion.div
      data-reveal
      className={className}
      initial={still ? { opacity: 1 } : { opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={
        still
          ? { duration: 0 }
          : {
              duration: 0.5,
              delay,
              // A gentle decelerating curve: things should look like they
              // settle, not like they snap into place.
              ease: [0.22, 1, 0.36, 1],
            }
      }
    >
      {children}
    </motion.div>
  );
}
