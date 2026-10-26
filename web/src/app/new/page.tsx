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

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AppShell, Page } from "@/components/app-shell";
import { FormLayout } from "@/components/form-layout";
import { Wizard } from "@/components/wizard";
import { HowItWorksLink } from "@/components/how-it-works-link";
import {
  Checkbox,
  Field,
  FormError,
  MoneyInput,
  Select,
  TextArea,
  TextInput,
} from "@/components/form";
import { ApiError, api } from "@/lib/api";

const CURRENCIES = ["INR", "USD", "EUR", "GBP"];
const DEFAULT_RUNWAY_MONTHS = 6;

/*
 * The composer on the home page hands its sentence over as `?pitch=`, so the
 * founder never retypes what they already wrote. `useSearchParams` forces a
 * Suspense boundary -- without one, Next cannot prerender this route at all,
 * because the params are not known until the request.
 */
export default function NewIdeaPage() {
  return (
    <Suspense fallback={null}>
      <NewIdeaForm />
    </Suspense>
  );
}

function NewIdeaForm() {
  const router = useRouter();
  const fromComposer = useSearchParams().get("pitch") ?? "";
  const [pitch, setPitch] = useState(fromComposer);
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

  async function submit() {
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
        <FormLayout title="A new idea" action={<HowItWorksLink />} variant="bare">
          <Wizard
            // Arriving from the composer, the idea is already answered, so
            // open on the first thing still to ask for.
            initialStep={fromComposer.trim().length >= 10 ? 1 : 0}
            submitLabel="Analyse my idea"
            submitting={submitting}
            onSubmit={submit}
            error={error ? <FormError message={error} /> : null}
            steps={[
              {
                label: "The idea",
                complete: pitch.trim().length >= 10,
                content: (
                  <Field
                    label="What do you want to build?"
                    required
                    htmlFor="pitch"
                    error={fields.pitch}
                  >
                    <TextArea
                      id="pitch"
                      value={pitch}
                      invalid={Boolean(fields.pitch)}
                      className="min-h-40"
                      placeholder="Start the business you have in mind…"
                      onChange={(e) => setPitch(e.target.value)}
                    />
                  </Field>
                ),
              },
              {
                label: "The money you have",
                complete: capitalNumber > 0,
                content: (
                  <div className="space-y-6">
                    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
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
                    </div>

                    <div className="border-t border-line pt-6">
                      <h3 className="text-small font-medium text-ink-muted">
                        Running costs (optional)
                      </h3>
                      <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-3">
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
                      </div>
                    </div>
                  </div>
                ),
              },
              {
                label: "Also include",
                complete: true,
                content: (
                  <div className="space-y-4">
                    <Checkbox
                      label="How to incorporate"
                      checked={formation}
                      onChange={setFormation}
                    />
                    <Checkbox
                      label="A funding roadmap"
                      checked={funding}
                      onChange={setFunding}
                    />
                  </div>
                ),
              },
            ]}
          />
        </FormLayout>
      </Page>
    </AppShell>
  );
}

function numberOrNull(raw: string): number | null {
  const value = Number(raw.replace(/,/g, ""));
  return raw.trim() && Number.isFinite(value) ? value : null;
}
