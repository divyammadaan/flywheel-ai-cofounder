/**
 * The research and the incorporation checklist.
 *
 * Deliberately below the plan and collapsed. This is what the verdict was
 * based on rather than what the founder does next, so it earns its place on
 * the page but not the founder's first attention.
 *
 * Sources are listed in full with their [n] numbering intact, because Market
 * Research cites them inline. When there were none, that is stated rather
 * than left as a silent absence -- a market size with no source behind it is
 * a guess, and the founder should know which one they are reading.
 */

import { Attribution, Card, Empty, Judgement, Section } from "@/components/primitives";
import { asList } from "@/lib/format";
import type { FormationPlan, MarketResearch } from "@/lib/types";

function Collapsible({
  summary,
  meta,
  children,
  defaultOpen = false,
}: {
  summary: string;
  meta?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <Card as="section">
      <details open={defaultOpen} className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-5">
          <div className="min-w-0">
            <h3 className="text-heading font-semibold text-ink">{summary}</h3>
            {meta ? <p className="mt-0.5 text-caption text-ink-faint">{meta}</p> : null}
          </div>
          <svg
            aria-hidden
            viewBox="0 0 16 16"
            className="h-4 w-4 shrink-0 fill-ink-faint transition-transform group-open:rotate-180"
          >
            <path d="M8 11 3 6h10l-5 5Z" />
          </svg>
        </summary>
        <div className="border-t border-line px-6 py-6">{children}</div>
      </details>
    </Card>
  );
}

function Block({ title, points }: { title: string; points: string[] }) {
  return (
    <div>
      <h4 className="mb-3 text-caption font-medium uppercase tracking-wide text-ink-faint">
        {title}
      </h4>
      {points.length ? <Judgement points={points} /> : <Empty>None recorded.</Empty>}
    </div>
  );
}

export function BackgroundSection({
  research,
  formation,
}: {
  research?: MarketResearch;
  formation?: FormationPlan;
}) {
  if (!research && !formation) return null;

  return (
    <Section
      id="background"
      title="What this was based on"
      lead="The research behind the verdict, and how to actually incorporate."
    >
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 xl:items-start">
        {research ? <ResearchBlock research={research} /> : null}
        {formation ? <FormationBlock formation={formation} /> : null}
      </div>
    </Section>
  );
}

function ResearchBlock({ research }: { research: MarketResearch }) {
  const sources = research.sources ?? [];

  return (
    <Collapsible
      summary="Market research"
      meta={
        sources.length
          ? `Grounded in ${sources.length} live web results`
          : "No web results were available, so the figures are estimates"
      }
    >
      <div className="space-y-6">
        <div>
          <h4 className="mb-2 text-caption font-medium uppercase tracking-wide text-ink-faint">
            Market size
          </h4>
          <p className="text-body text-ink-muted">{research.market_size_estimate}</p>
        </div>

        <div className="grid gap-6 sm:grid-cols-2">
          <Block title="Who else is doing this" points={asList(research.key_competitors)} />
          <Block title="The opening" points={asList(research.opportunities)} />
        </div>

        <Block title="What could go wrong" points={asList(research.risks)} />

        {sources.length ? (
          <div className="border-t border-line pt-5">
            <h4 className="mb-3 text-caption font-medium uppercase tracking-wide text-ink-faint">
              Sources
            </h4>
            <ol className="space-y-1.5">
              {sources.map((source, i) => (
                <li key={i} className="flex gap-2 text-small">
                  <span className="tnum shrink-0 text-ink-faint">[{i + 1}]</span>
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="min-w-0 text-accent underline-offset-2 hover:underline"
                  >
                    {source.title}
                  </a>
                </li>
              ))}
            </ol>
          </div>
        ) : null}

        <Attribution agent="market_research" />
      </div>
    </Collapsible>
  );
}

function FormationBlock({ formation }: { formation: FormationPlan }) {
  return (
    <Collapsible
      summary={`Setting up — ${formation.recommended_entity}`}
      meta={`${formation.estimated_cost} · ${formation.estimated_timeline}`}
    >
      <div className="space-y-6">
        <div>
          <h4 className="mb-2 text-caption font-medium uppercase tracking-wide text-ink-faint">
            Why this entity
          </h4>
          <p className="text-body text-ink-muted">{formation.entity_rationale}</p>
        </div>

        <div>
          <h4 className="mb-3 text-caption font-medium uppercase tracking-wide text-ink-faint">
            Registration steps
          </h4>
          <ol className="space-y-2.5">
            {asList(formation.registration_steps).map((step, i) => (
              <li key={i} className="flex gap-3 text-body text-ink-muted">
                <span className="tnum mt-px w-5 shrink-0 text-small font-semibold text-ink-faint">
                  {i + 1}
                </span>
                <span className="min-w-0">{step}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="grid gap-6 sm:grid-cols-2">
          <Block title="Licences and permits" points={asList(formation.licenses_and_permits)} />
          <Block title="Tax registrations" points={asList(formation.tax_registrations)} />
        </div>

        {formation.disclaimer ? (
          <p className="border-t border-line pt-5 text-caption text-ink-faint">
            {formation.disclaimer}
          </p>
        ) : null}

        <Attribution agent="company_formation" />
      </div>
    </Collapsible>
  );
}
