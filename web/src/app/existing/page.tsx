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
import { OrdersUpload } from "@/components/orders-upload";
import { Button } from "@/components/primitives";
import { ApiError, api } from "@/lib/api";

const CURRENCIES = ["INR", "USD", "EUR", "GBP"];

export default function ExistingBusinessPage() {
  const router = useRouter();
  const [description, setDescription] = useState("");
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
  const ready =
    description.trim().length >= 10 &&
    period.trim() !== "" &&
    revenue !== "" &&
    netProfit !== "" &&
    debt !== "" &&
    num(budget) > 0;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
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
          lead="Your real numbers, and your order history if you have it. Flywheel plans the next period from those — nothing is estimated or invented."
          aside={
            <>
              <WhatHappensNext
                steps={[
                  {
                    title: "Your numbers, read back",
                    body: "Margin, debt load, cost per customer and churn — computed in code, then explained.",
                  },
                  {
                    title: "Your customers, grouped",
                    body: "Best, regular, new, slipping away and lost, with cut-offs scaled to how often yours re-order.",
                  },
                  {
                    title: "Next period's plan",
                    body: "Campaigns, lead sources, stock and retention, all inside the budget you set.",
                  },
                  {
                    title: "Funding",
                    body: "Whether to raise now, and the milestones to hit first.",
                  },
                ]}
                footnote="Takes a few minutes. You can close the tab and come back to it."
              />
              <SideNote title="What the optional fields buy">
                <p>
                  <span className="text-ink">Cash in bank</span> gives you a runway figure.
                </p>
                <p>
                  <span className="text-ink">Marketing spend</span> with{" "}
                  <span className="text-ink">new customers</span> gives a cost per customer.
                </p>
                <p>
                  <span className="text-ink">Customers at start</span> with{" "}
                  <span className="text-ink">customers lost</span> gives a churn rate.
                </p>
                <p>
                  Leave any blank and it reads as &ldquo;not reported&rdquo; — never as zero,
                  which would be a claim about your business that nobody made.
                </p>
              </SideNote>
              <SideNote title="Your customer data stays here">
                <p>
                  The retention plan runs on a model on this machine, so the names and amounts
                  in your order file never leave it.
                </p>
              </SideNote>
            </>
          }
        >
          <form onSubmit={submit} className="space-y-8">
            <Fieldset legend="The business">
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
                  className="min-h-24"
                  placeholder="Describe the business you run…"
                  onChange={(e) => setDescription(e.target.value)}
                />
              </Field>
            </Fieldset>

            <Fieldset legend="The period" columns={3}>
              <Field
                label="Period"
                required
                htmlFor="period"
                hint="However you refer to it, e.g. FY2025-26 or Aug 2026."
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
                <Select id="currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </Select>
              </Field>
            </Fieldset>

            <Fieldset
              legend="The numbers that drive the plan"
              hint="These five decide the cash position and what you can safely deploy."
              columns={2}
            >
              <Field label="Revenue" required htmlFor="revenue" error={fields["metrics.revenue"]}>
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
              <Field label="Total debt" required htmlFor="debt" error={fields["metrics.total_debt"]}>
                <MoneyInput
                  id="debt"
                  currency={currency}
                  value={debt}
                  onValueChange={setDebt}
                  invalid={Boolean(fields["metrics.total_debt"])}
                />
              </Field>
              <Field
                label="Budget for next period"
                required
                htmlFor="budget"
                hint="What the plan is allowed to spend."
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
            </Fieldset>

            <Fieldset
              legend="If you track them"
              hint="Each one buys a specific figure. Leave any blank and it reads as 'not reported' rather than zero."
              columns={2}
            >
              <Field label="Cash in bank" htmlFor="cash" hint="Gives you a runway figure.">
                <MoneyInput id="cash" currency={currency} value={cash} onValueChange={setCash} />
              </Field>
              <Field label="EBITDA" htmlFor="ebitda">
                <MoneyInput id="ebitda" currency={currency} value={ebitda} onValueChange={setEbitda} />
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
            </Fieldset>

            <Fieldset
              legend="Your order history"
              hint="Optional. With it you also get customer groups, who is slipping away, and messages to send them — without it there are no customers to retain, so that part is skipped."
            >
              <OrdersUpload onChange={setOrdersToken} />
            </Fieldset>

            <Fieldset legend="Also include">
              <Checkbox
                label="A funding roadmap"
                checked={funding}
                onChange={setFunding}
                hint="When to raise, and the milestones to hit first."
              />
            </Fieldset>

            {error ? <FormError message={error} /> : null}

            <div className="flex flex-wrap items-center gap-4 border-t border-line pt-6">
              <Button type="submit" disabled={!ready || submitting}>
                {submitting ? "Starting…" : "Plan my next period"}
              </Button>
              <p className="text-caption text-ink-faint">
                Takes a few minutes. You can close the tab.
              </p>
            </div>
          </form>
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
