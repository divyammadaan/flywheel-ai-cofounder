"use client";

/**
 * Start a launch plan.
 *
 * The form asks for the least it can: a description, and the capital. Running
 * costs are optional but visibly worth giving, because they are what turn the
 * plan from a budget into a reserve and a break-even -- so the field carries
 * that reason rather than a label.
 *
 * Capital is required and validated before submitting, because it is what the
 * entire plan is sized from. Everything else can be unknown.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell, Page } from "@/components/app-shell";
import { FormLayout, SideNote, WhatHappensNext } from "@/components/form-layout";
import {
  Checkbox,
  Field,
  Fieldset,
  FormError,
  MoneyInput,
  Select,
  TextArea,
  TextInput,
} from "@/components/form";
import { Button } from "@/components/primitives";
import { ApiError, api } from "@/lib/api";

const CURRENCIES = ["INR", "USD", "EUR", "GBP"];
const DEFAULT_RUNWAY_MONTHS = 6;

// Shown in the side panel rather than as a placeholder: inside the field it
// looks like an answer the founder has to delete before they can start.
const EXAMPLE =
  "A boutique filter-coffee subscription in Bangalore: single-origin Chikmagalur beans, roasted to order, 500g delivered monthly to young professionals.";

export default function NewIdeaPage() {
  const router = useRouter();
  const [pitch, setPitch] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [capital, setCapital] = useState("");
  const [fixedCosts, setFixedCosts] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [runway, setRunway] = useState(String(DEFAULT_RUNWAY_MONTHS));
  const [formation, setFormation] = useState(true);
  const [funding, setFunding] = useState(true);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});

  const capitalNumber = Number(capital.replace(/,/g, ""));
  const ready = pitch.trim().length >= 10 && capitalNumber > 0;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setFields({});
    try {
      const { run_id } = await api.startNewIdea({
        pitch: pitch.trim(),
        currency,
        starting_capital: capitalNumber,
        monthly_fixed_costs: numberOrNull(fixedCosts),
        unit_cost: numberOrNull(unitCost),
        runway_months: Number(runway) || DEFAULT_RUNWAY_MONTHS,
        include_formation: formation,
        include_funding: funding,
      });
      router.push(`/runs/${run_id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.message);
        setFields(e.fields);
      } else {
        setError((e as Error).message);
      }
      setSubmitting(false);
    }
  }

  return (
    <AppShell>
      <Page>
        <FormLayout
          title="A new idea"
          lead="Describe it in your own words. Flywheel will research the market, ask what it still needs to know, and rule before it plans anything."
          aside={
            <>
              <WhatHappensNext
                steps={[
                  {
                    title: "Live market research",
                    body: "Real web search for competitors and market size, cited so you can check every figure.",
                  },
                  {
                    title: "A few questions",
                    body: "Only the gaps that change the answer. The run pauses here — you can close the tab and come back.",
                  },
                  {
                    title: "GO, PIVOT or NO-GO",
                    body: "A NO-GO stops before any money is committed. That is the point of asking first.",
                  },
                  {
                    title: "The plan",
                    body: "Cash reserve, break-even, campaigns, stock and lead sources — all sized from your capital.",
                  },
                ]}
                footnote="Takes a few minutes end to end. Nothing runs in your browser; close it whenever you like."
              />
              <SideNote title="A good description looks like">
                <p className="text-ink">{EXAMPLE}</p>
                <p>
                  What you sell, who buys it, and where. That is enough for the research to
                  find the right competitors.
                </p>
              </SideNote>
              <SideNote title="Why it asks for running costs">
                <p>
                  Without them you get a budget. With them you also get a cash reserve the plan
                  cannot touch, and the number of units a month you need to break even.
                </p>
              </SideNote>
            </>
          }
        >
          <form onSubmit={submit} className="space-y-8">
            <Fieldset legend="The idea">
              <Field
                label="What do you want to build?"
                required
                htmlFor="pitch"
                hint="What you sell, to whom, and where. A couple of sentences is plenty."
                error={fields.pitch}
              >
                <TextArea
                  id="pitch"
                  value={pitch}
                  invalid={Boolean(fields.pitch)}
                  placeholder="Start the business you have in mind…"
                  onChange={(e) => setPitch(e.target.value)}
                />
              </Field>
            </Fieldset>

            <Fieldset
              legend="The money you have"
              hint="Every budget in the plan comes from this figure. Nothing is invented."
              columns={2}
            >
              <Field label="Currency" htmlFor="currency" required>
                <Select
                  id="currency"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                >
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field
                label="Capital for the launch"
                required
                htmlFor="capital"
                error={fields.starting_capital}
              >
                <MoneyInput
                  id="capital"
                  currency={currency}
                  value={capital}
                  onValueChange={setCapital}
                  invalid={Boolean(fields.starting_capital)}
                />
              </Field>
            </Fieldset>

            <Fieldset
              legend="Running costs"
              hint="Optional, but these are what produce a cash reserve and a break-even point instead of just a budget."
              columns={3}
            >
              <Field label="Monthly fixed costs" htmlFor="fixed">
                <MoneyInput
                  id="fixed"
                  currency={currency}
                  value={fixedCosts}
                  onValueChange={setFixedCosts}
                />
              </Field>
              <Field label="Cost to deliver one unit" htmlFor="unit">
                <MoneyInput
                  id="unit"
                  currency={currency}
                  value={unitCost}
                  onValueChange={setUnitCost}
                />
              </Field>
              <Field label="Months to hold in reserve" htmlFor="runway">
                <TextInput
                  id="runway"
                  type="number"
                  min={0}
                  max={36}
                  value={runway}
                  className="tnum"
                  onChange={(e) => setRunway(e.target.value)}
                />
              </Field>
            </Fieldset>

            <Fieldset legend="Also include">
              <div className="space-y-3">
                <Checkbox
                  label="How to incorporate"
                  checked={formation}
                  onChange={setFormation}
                  hint="Entity type, registrations, licences, rough cost and timeline for your region."
                />
                <Checkbox
                  label="A funding roadmap"
                  checked={funding}
                  onChange={setFunding}
                  hint="When to raise, and the milestones to hit first."
                />
              </div>
            </Fieldset>

            {error ? <FormError message={error} /> : null}

            <div className="flex flex-wrap items-center gap-4 border-t border-line pt-6">
              <Button type="submit" disabled={!ready || submitting}>
                {submitting ? "Starting…" : "Analyse my idea"}
              </Button>
              <p className="text-caption text-ink-faint">
                Takes a few minutes — real web search and model calls. You can close the tab.
              </p>
            </div>
          </form>
        </FormLayout>
      </Page>
    </AppShell>
  );
}

function numberOrNull(raw: string): number | null {
  const value = Number(raw.replace(/,/g, ""));
  return raw.trim() && Number.isFinite(value) ? value : null;
}
