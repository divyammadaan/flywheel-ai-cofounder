"use client";

/**
 * The order history upload.
 *
 * Uploading is not the interesting part -- knowing the file was *understood*
 * is. Real exports have loose column names, "₹1,599.00" amounts and day-first
 * dates, and `tools/orders_file.py` silently skips rows it cannot read. So the
 * file is parsed on the server the moment it is chosen and the result shown
 * back: how many orders, how many customers, the date range, and how many rows
 * were skipped. A founder seeing "312 rows skipped" knows to check their
 * export; the old version told them nothing.
 */

import { useRef, useState } from "react";

import { Button } from "@/components/primitives";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { count } from "@/lib/format";
import type { OrdersPreview } from "@/lib/types";

export function OrdersUpload({
  onChange,
}: {
  onChange: (token: string | null) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<OrdersPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  async function accept(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.previewOrders(file);
      setPreview(result);
      onChange(result.token);
    } catch (e) {
      setPreview(null);
      onChange(null);
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function clear() {
    setPreview(null);
    setError(null);
    onChange(null);
    if (input.current) input.current.value = "";
  }

  if (preview) {
    return (
      <div className="rounded-tile border border-line bg-surface-sunken p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-small font-medium text-ink">Order history read</p>
            <p className="tnum mt-1 text-small text-ink-muted">
              {count(preview.rows)} orders from {count(preview.customers)} customers
              {preview.first_order && preview.last_order
                ? `, ${preview.first_order} to ${preview.last_order}`
                : ""}
            </p>
            {preview.skipped_rows > 0 ? (
              <p className="mt-2 text-caption text-warning">
                {count(preview.skipped_rows)} rows could not be read and were skipped — usually
                a missing date or amount. Worth checking your export if that seems high.
              </p>
            ) : null}
            <p className="mt-2 text-caption text-ink-faint">
              Columns used: {preview.columns.join(", ")}
            </p>
          </div>
          <Button type="button" variant="ghost" onClick={clear}>
            Remove
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void accept(e.dataTransfer.files?.[0]);
        }}
        className={cn(
          "rounded-tile border border-dashed px-5 py-8 text-center transition-colors",
          dragging ? "border-accent bg-accent-soft" : "border-line-strong bg-surface-sunken",
        )}
      >
        <p className="text-small text-ink">
          Drop a .csv or .xlsx export here, or{" "}
          <button
            type="button"
            onClick={() => input.current?.click()}
            className="font-medium text-accent underline-offset-2 hover:underline"
          >
            choose a file
          </button>
        </p>
        <p className="mt-1.5 text-caption text-ink-faint">
          {busy
            ? "Reading it…"
            : "Needs a customer, a date and an amount per row. Column names can be messy."}
        </p>
        <p className="mt-3 text-caption text-ink-faint">
          No file handy?{" "}
          <a
            href={api.sampleOrdersUrl("csv")}
            className="text-accent underline-offset-2 hover:underline"
          >
            Download a sample
          </a>
        </p>
        <input
          ref={input}
          type="file"
          accept=".csv,.xlsx"
          className="sr-only"
          onChange={(e) => void accept(e.target.files?.[0])}
        />
      </div>
      {error ? (
        <p role="alert" className="mt-2 text-caption text-nogo">
          {error}
        </p>
      ) : null}
    </div>
  );
}
