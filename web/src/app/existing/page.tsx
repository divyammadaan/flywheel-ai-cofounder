"use client";

/**
 * Plan an operating business's next period.
 *
 * The required set is deliberately small -- period, revenue, net profit, debt,
 * budget -- because those five are what the cash maths actually needs. The
 * optional ones are grouped separately and labelled with what each unlocks, so
 * a founder can see that leaving churn blank costs them a churn figure and
 * nothing else.
 *
 * The order-history upload is optional but is what turns a plan into a *CRM*
 * plan: without real customers there is nobody to retain, and the engine skips
 * that agent entirely.
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
import { OrdersUpload } from "@/components/orders-upload";
import { ApiError, api } from "@/lib/api";

const CURRENCIES = ["INR", "USD", "EUR", "GBP"];

/*
 * The composer on the home page hands its sentence over as `?description=`,
 * so the founder never retypes what they already wrote. `useSearchParams`
 * forces a Suspense boundary -- without one, Next cannot prerender this route
 * at all, because the params are not known until the request.
 */
export default function ExistingBusinessPage() {
  return (
    <Suspense fallback={null}>
      <ExistingBusinessForm />
    </Suspense>
  );
}

function ExistingBusinessForm() {
  const router = useRouter();
  const fromComposer = useSearchParams().get("description") ?? "";
  const [description, setDescription] = useState(fromComposer);
  const [currency, setCurrency] = useState("INR");
  const [period, setPeriod] = useState("");
  const [months, setMonths] = useState("12");
  const [revenue, setRevenue] = useState("");
  const [netProfit, setNetProfit] = useState("");
  const [debt, setDebt] = useState("");
  const [budget, setBudget] = useState("");
  const [cash, setCash] = useState("");
  const [ebitda, setEbitda] = useState("");
  const [marketingSpend, setMarketingSpend] = useState("");
  const [newCustomers, setNewCustomers] = useState("");
  const [customersAtStart, setCustomersAtStart] = useState("");
  const [customersLost, setCustomersLost] = useState("");
  const [ordersToken, setOrdersToken] = useState<string | null>(null);
  const [funding, setFunding] = useState(true);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});

  const num = (raw: string) => Number(raw.replace(/,/g, ""));

  async function submit() {
    setSubmitting(true);
    setError(null);
    setFields({});
    try {
      const { run_id } = await api.startBusinessReview({
        description: description.trim(),
        currency,
        budget: num(budget),
        include_funding: funding,
        orders_token: ordersToken,
        metrics: {
          period_label: period.trim(),
          period_months: Number(months) || 12,
          revenue: num(revenue),
          net_profit: num(netProfit),
          total_debt: num(debt),
          cash_in_bank: optional(cash),
          ebitda: optional(ebitda),
          marketing_spend: optional(marketingSpend),
          new_customers: optionalInt(newCustomers),
          customers_at_start: optionalInt(customersAtStart),
          customers_lost: optionalInt(customersLost),
        },
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
          title="Your business today"
          action={<HowItWorksLink />}
          variant="bare"
        >
          <Wizard
            // Arriving from the composer, the business is already described,
            // so open on the figures instead of asking for it again.
            initialStep={fromComposer.trim().length >= 10 ? 1 : 0}
            submitLabel="Build my plan"
            submitting={submitting}
            onSubmit={submit}
            error={error ? <FormError message={error} /> : null}
            steps={[
              {
                label: "The business",
                complete: description.trim().length >= 10,
                content: (
                  <Field
                    label="What do you sell, to whom, and where?"
                    required
                    htmlFor="description"
                    error={fields.description}
                  >
                    <TextArea
                      id="description"
                      value={description}
                      invalid={Boolean(fields.description)}
                      className="min-h-40"
                      placeholder="Describe the business you run…"
                      onChange={(e) => setDescription(e.target.value)}
                    />
                  </Field>
                ),
              },
              {
                label: "The numbers",
                complete:
                  period.trim() !== "" &&
                  months !== "" &&
                  revenue !== "" &&
                  netProfit !== "" &&
                  debt !== "" &&
                  num(budget) > 0,
                content: (
                  <div className="space-y-6">
                    {/* What the figures below are figures *for*, so it leads
                        rather than sitting a step away from them. */}
                    <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
                      <Field
                        label="Period"
                        required
                        htmlFor="period"
                        hint="However you refer to it, e.g. FY2025-26."
                        error={fields["metrics.period_label"]}
                      >
                        <TextInput
                          id="period"
                          value={period}
                          invalid={Boolean(fields["metrics.period_label"])}
                          onChange={(e) => setPeriod(e.target.value)}
                        />
                      </Field>
                      <Field label="Months it covers" required htmlFor="months">
                        <TextInput
                          id="months"
                          type="number"
                          min={1}
                          max={12}
                          value={months}
                          className="tnum"
                          onChange={(e) => setMonths(e.target.value)}
                        />
                      </Field>
                      <Field label="Currency" required htmlFor="currency">
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
                    </div>

                    {/* Four across rather than two: these are short numeric
                        fields, and at two columns this step alone ran to a
                        screen and a half. */}
                    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
                      <Field
                        label="Revenue"
                        required
                        htmlFor="revenue"
                        error={fields["metrics.revenue"]}
                      >
                        <MoneyInput
                          id="revenue"
                          currency={currency}
                          value={revenue}
                          onValueChange={setRevenue}
                          invalid={Boolean(fields["metrics.revenue"])}
                        />
                      </Field>
                      <Field
                        label="Net profit"
                        required
                        htmlFor="net-profit"
                        hint="Negative for a loss."
                        error={fields["metrics.net_profit"]}
                      >
                        <MoneyInput
                          id="net-profit"
                          currency={currency}
                          value={netProfit}
                          onValueChange={setNetProfit}
                          invalid={Boolean(fields["metrics.net_profit"])}
                        />
                      </Field>
                      <Field
                        label="Total debt"
                        required
                        htmlFor="debt"
                        error={fields["metrics.total_debt"]}
                      >
                        <MoneyInput
                          id="debt"
                          currency={currency}
                          value={debt}
                          onValueChange={setDebt}
                          invalid={Boolean(fields["metrics.total_debt"])}
                        />
                      </Field>
                      <Field
                        label="Budget"
                        required
                        htmlFor="budget"
                        hint="What the plan may spend next period."
                        error={fields.budget}
                      >
                        <MoneyInput
                          id="budget"
                          currency={currency}
                          value={budget}
                          onValueChange={setBudget}
                          invalid={Boolean(fields.budget)}
                        />
                      </Field>
                    </div>
                  </div>
                ),
              },
              {
                label: "If you track them",
                // Nothing here is required; the step exists so the founder
                // can walk past it in one click rather than scroll past it.
                complete: true,
                content: (
                  <div>
                    <p className="text-small text-ink-muted">
                      Optional. Each one buys a specific figure — leave any blank and it reads
                      as &ldquo;not reported&rdquo; rather than as zero.
                    </p>
                    <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">
                        <Field label="Cash in bank" htmlFor="cash" hint="Gives you a runway figure.">
                          <MoneyInput
                            id="cash"
                            currency={currency}
                            value={cash}
                            onValueChange={setCash}
                          />
                        </Field>
                        <Field label="EBITDA" htmlFor="ebitda">
                          <MoneyInput
                            id="ebitda"
                            currency={currency}
                            value={ebitda}
                            onValueChange={setEbitda}
                          />
                        </Field>
                        <Field
                          label="Marketing spend"
                          htmlFor="marketing-spend"
                          hint="With new customers, gives a cost per customer."
                        >
                          <MoneyInput
                            id="marketing-spend"
                            currency={currency}
                            value={marketingSpend}
                            onValueChange={setMarketingSpend}
                          />
                        </Field>
                        <Field label="New customers" htmlFor="new-customers">
                          <TextInput
                            id="new-customers"
                            type="number"
                            min={0}
                            value={newCustomers}
                            className="tnum"
                            onChange={(e) => setNewCustomers(e.target.value)}
                          />
                        </Field>
                        <Field
                          label="Customers at start"
                          htmlFor="customers-start"
                          hint="With customers lost, gives a churn rate."
                        >
                          <TextInput
                            id="customers-start"
                            type="number"
                            min={0}
                            value={customersAtStart}
                            className="tnum"
                            onChange={(e) => setCustomersAtStart(e.target.value)}
                          />
                        </Field>
                        <Field label="Customers lost" htmlFor="customers-lost">
                          <TextInput
                            id="customers-lost"
                            type="number"
                            min={0}
                            value={customersLost}
                            className="tnum"
                            onChange={(e) => setCustomersLost(e.target.value)}
                          />
                        </Field>
                      </div>
                    </div>
                ),
              },
              {
                label: "Order history",
                complete: true,
                content: (
                  <div className="space-y-6">
                    <OrdersUpload onChange={setOrdersToken} />
                    <div className="border-t border-line pt-6">
                      <Checkbox
                        label="A funding roadmap"
                        checked={funding}
                        onChange={setFunding}
                      />
                    </div>
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

function optional(raw: string): number | null {
  const value = Number(raw.replace(/,/g, ""));
  return raw.trim() && Number.isFinite(value) ? value : null;
}

function optionalInt(raw: string): number | null {
  const value = optional(raw);
  return value === null ? null : Math.round(value);
}
