"use client";

/**
 * Form primitives.
 *
 * Two things these get right that the Streamlit version could not:
 *
 * - **Errors land on the field.** The old page collected missing fields into
 *   one sentence at the top ("Please fill in: Period, Revenue, Budget") and
 *   left the founder to find them. The API reports per-field problems, so each
 *   one is shown against its own input.
 * - **A money input knows it is money.** The currency sits inside the field,
 *   digits are tabular, and the value is grouped as you leave the field, so a
 *   mistyped 150000 vs 1500000 is visible rather than a wall of zeroes.
 */

import { useId, useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";
import { currencySymbol } from "@/lib/format";

export function Field({
  label,
  hint,
  error,
  required,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="min-w-0">
      <label
        htmlFor={htmlFor}
        className="flex items-baseline gap-1.5 text-small font-medium text-ink"
      >
        {label}
        {required ? (
          <span aria-hidden className="text-ink-faint">
            required
          </span>
        ) : (
          <span aria-hidden className="text-caption text-ink-faint">
            optional
          </span>
        )}
      </label>
      {hint ? <p className="mt-1 text-caption text-ink-faint">{hint}</p> : null}
      <div className="mt-2">{children}</div>
      {error ? (
        <p role="alert" className="mt-1.5 text-caption text-nogo">
          {error}
        </p>
      ) : null}
    </div>
  );
}

const inputBase =
  "w-full rounded-tile border bg-surface px-3 py-2.5 text-body text-ink " +
  "placeholder:text-ink-faint transition-colors " +
  "focus:border-accent focus:outline-none focus-visible:outline-none";

export function TextInput({
  invalid,
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      className={cn(inputBase, invalid ? "border-nogo" : "border-line", className)}
      aria-invalid={invalid || undefined}
      {...props}
    />
  );
}

export function TextArea({
  invalid,
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  return (
    <textarea
      className={cn(
        inputBase,
        "min-h-32 resize-y leading-relaxed",
        invalid ? "border-nogo" : "border-line",
        className,
      )}
      aria-invalid={invalid || undefined}
      {...props}
    />
  );
}

export function Select({
  invalid,
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <select
      className={cn(inputBase, "cursor-pointer", invalid ? "border-nogo" : "border-line", className)}
      {...props}
    >
      {children}
    </select>
  );
}

/**
 * A money input.
 *
 * Holds a string, not a number: a controlled numeric input fights the founder
 * mid-type, turning "1500000" into 1500000 and back on every keystroke, and
 * makes a half-typed "1." impossible. It is parsed once, on change, for the
 * caller.
 */
export function MoneyInput({
  currency,
  value,
  onValueChange,
  invalid,
  id,
  placeholder,
}: {
  currency: string;
  value: string;
  onValueChange: (raw: string) => void;
  invalid?: boolean;
  id?: string;
  placeholder?: string;
}) {
  const [focused, setFocused] = useState(false);
  const symbol = currencySymbol(currency);
  const numeric = Number(value.replace(/,/g, ""));
  const display =
    !focused && value !== "" && Number.isFinite(numeric)
      ? numeric.toLocaleString("en-US")
      : value;

  return (
    <div
      className={cn(
        "flex items-center rounded-tile border bg-surface transition-colors",
        invalid ? "border-nogo" : "border-line",
        focused && !invalid && "border-accent",
      )}
    >
      <span className="pl-3 pr-1 text-body text-ink-faint">{symbol}</span>
      <input
        id={id}
        inputMode="decimal"
        value={display}
        placeholder={placeholder}
        aria-invalid={invalid || undefined}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onChange={(e) => onValueChange(e.target.value.replace(/[^0-9.-]/g, ""))}
        className="tnum w-full bg-transparent py-2.5 pr-3 text-body text-ink placeholder:text-ink-faint focus:outline-none"
      />
    </div>
  );
}

export function Checkbox({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="flex gap-3">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-[var(--color-accent)]"
      />
      <div className="min-w-0">
        <label htmlFor={id} className="cursor-pointer text-small text-ink">
          {label}
        </label>
        {hint ? <p className="text-caption text-ink-faint">{hint}</p> : null}
      </div>
    </div>
  );
}

/** A group of fields under one heading, with a rule between groups. */
export function Fieldset({
  legend,
  hint,
  children,
  columns = 1,
}: {
  legend: string;
  hint?: string;
  children: ReactNode;
  columns?: 1 | 2 | 3;
}) {
  const cols = { 1: "", 2: "sm:grid-cols-2", 3: "sm:grid-cols-2 lg:grid-cols-3" }[columns];
  return (
    <fieldset className="border-t border-line pt-6 first:border-0 first:pt-0">
      <legend className="sr-only">{legend}</legend>
      <h2 className="text-heading font-semibold text-ink">{legend}</h2>
      {hint ? <p className="mt-1 text-small text-ink-muted">{hint}</p> : null}
      <div className={cn("mt-5 grid grid-cols-1 gap-5", cols)}>{children}</div>
    </fieldset>
  );
}

export function FormError({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-tile border border-nogo/30 bg-nogo-soft px-4 py-3 text-small text-ink"
    >
      {message}
    </div>
  );
}
