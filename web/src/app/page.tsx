/**
 * The front door.
 *
 * One question, centred, and nothing else. Earlier versions carried a
 * headline, two route cards, a "how it works" walkthrough and a FAQ, on the
 * reasoning that someone new needs to understand the product before they will
 * trust it with their figures. In practice all of it was instruction, and it
 * arrived before the founder had done anything -- reading four steps about a
 * plan you have not asked for is not understanding, it is homework.
 *
 * So the page asks the one thing only the founder can answer and gets out of
 * the way. The explaining now happens where it is actually load-bearing: the
 * suggestion chips show what a good answer looks like by filling the box with
 * one, the line under the composer says what the next screen will ask for,
 * and the form itself explains each figure at the moment it is wanted.
 *
 * The fork between the two paths lives in the composer as a pair of chips,
 * defaulted to "I have an idea". It is a real fork rather than a preference:
 * a business that has not launched has no results, so it gets research and a
 * verdict before any plan, while one that is trading has real numbers and is
 * analysed instead.
 *
 * Run history is not here either -- a first visit has none, and the rail
 * carries it once there is any.
 */

import { AppShell, Page } from "@/components/app-shell";
import { Composer } from "@/components/composer";

export const dynamic = "force-dynamic";
// A title.template on the root layout never applies to app/page.tsx: they
// are the SAME route segment, not parent and child, so this is written out
// in full rather than relying on the "— Flywheel" suffix.
export const metadata = { title: "Flywheel — an AI co-founder" };

/**
 * Concrete enough to run as-is.
 *
 * These are the page's only instruction, and they teach by being an answer
 * rather than by describing one: clicking a chip fills the box with a
 * description at the length and specificity the research agents actually
 * want, which is a thing no amount of placeholder text conveys.
 */
const SUGGESTIONS = [
  {
    label: "Coffee subscription",
    mode: "new" as const,
    text: "A filter-coffee subscription in Bangalore: single-origin Chikmagalur beans roasted to order, 500g delivered monthly to young professionals.",
  },
  {
    label: "Weekend tour operator",
    mode: "new" as const,
    text: "Guided weekend cycling tours around Coorg for city professionals, including bikes, homestay and meals.",
  },
  {
    label: "A shop I already run",
    mode: "existing" as const,
    text: "A neighbourhood bakery in Pune selling sourdough and pastries, walk-in plus a small online order book.",
  },
];

export default function HomePage() {
  return (
    <AppShell>
      {/* Centred in the viewport rather than sitting at the top of it: with
          the page down to one question, anything else leaves the composer
          stranded under a band of empty space. */}
      <Page className="relative flex max-w-3xl flex-1 flex-col justify-center pb-24">
        {/* Fixed to the viewport and never clipped -- see the note in
            globals.css. `fixed inset-0` cannot widen the page, so this needs
            no wrapper to contain it. */}
        <div aria-hidden className="ambient pointer-events-none fixed inset-0 -z-10" />

        <h1 className="text-center text-display font-semibold tracking-tight text-balance text-ink">
          What are you building?
        </h1>
        <div className="mt-8">
          <Composer suggestions={SUGGESTIONS} />
        </div>
      </Page>
    </AppShell>
  );
}
