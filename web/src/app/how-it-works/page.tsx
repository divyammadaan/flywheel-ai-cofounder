/**
 * The explanation, on its own page.
 *
 * Everything here used to be somewhere it interrupted: four steps and a FAQ
 * on the home page, three panels of prose beside each form. None of it was
 * wrong -- it was in the way. A founder who has decided to describe their
 * business does not want to read about describing their business first.
 *
 * What survived is the part that answers the only question worth a page:
 * what happens after you press the button, on each of the two routes.
 *
 * It is laid out as two sequences read by scrolling rather than as two cards
 * of bullet points, because a sequence is what it is -- research, then
 * questions, then a verdict, then a plan, each depending on the one before.
 * Two side-by-side cards said all four at once and said nothing about the
 * order. See `ScrollTrack` for the mechanism, and for the reason every part
 * of it turns off under `prefers-reduced-motion`.
 *
 * Both calls to action point at the composer rather than at a form. That is
 * where a plan starts now.
 */

import { AppShell, Page } from "@/components/app-shell";
import { Reveal } from "@/components/reveal";
import { ScrollTrack } from "@/components/scroll-track";

export const metadata = {
  title: "How it works",
  description: "What Flywheel does with what you type, and what you get back.",
};

const NEW_IDEA = [
  {
    title: "Live market research",
    body: "Real web search for who else is doing this and how big the market is, cited so you can check every figure yourself rather than taking it on trust.",
  },
  {
    title: "A few questions",
    body: "Only the gaps that would change the answer. The run pauses here and waits — you can close the tab and come back to it.",
  },
  {
    title: "GO, PIVOT or NO-GO",
    body: "A straight verdict. A NO-GO stops before any money is committed, which is the entire point of asking first.",
  },
  {
    title: "The plan",
    body: "Cash reserve, break-even, campaigns, stock and lead sources — every figure sized from the capital you entered, none of it invented.",
  },
];

const EXISTING = [
  {
    title: "Your figures, read back",
    body: "Margin, runway, churn and cost per customer, computed from what you entered. Nothing is estimated on your behalf.",
  },
  {
    title: "Customer groups",
    body: "Your order history sorted into who is loyal, who is new and who is slipping away — with a message to send each. This part runs on a model on your own machine.",
  },
  {
    title: "Next period's plan",
    body: "Campaigns, stock and lead sources sized to the budget you said you could spend, not to your revenue.",
  },
  {
    title: "Funding",
    body: "Whether you are ready to raise, and the milestones to hit before you are.",
  },
];

export default function HowItWorksPage() {
  return (
    <AppShell>
      <Page className="max-w-5xl py-12 pb-40 sm:py-16 sm:pb-40">
        <Reveal>
          <h1 className="text-display font-semibold tracking-tight text-ink">How it works</h1>
          <p className="mt-3 max-w-2xl text-body leading-relaxed text-ink-muted">
            You type two or three sentences. Flywheel reads the live market for you — real
            competitors, real market size, every claim cited — returns a straight verdict,
            and turns it into a costed plan: what to spend, what to stock, who to contact,
            and in what order. Every figure in it traces back to a number you entered.
          </p>
        </Reveal>

        <div className="mt-16 space-y-24">
          <ScrollTrack
            eyebrow="If you have not launched"
            title="A new idea"
            lead="Nothing is planned until the idea has been checked against the market and given a straight answer."
            steps={NEW_IDEA}
            href="/"
            cta="Describe your idea"
          />

          <ScrollTrack
            eyebrow="If you are already trading"
            title="An operating business"
            lead="Your own numbers, read back to you, then a plan for the next period built from what they say."
            steps={EXISTING}
            href="/"
            cta="Start with your numbers"
          />
        </div>
      </Page>
    </AppShell>
  );
}
