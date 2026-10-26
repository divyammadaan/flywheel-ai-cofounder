"use client";

/**
 * Deleting a plan.
 *
 * This is the only irreversible thing a founder can do in the product, and a
 * plan is several minutes of model calls plus whatever they typed, so it asks
 * first. The confirmation is inline -- the row turns into "Delete this plan?
 * / Delete / Cancel" -- rather than a modal over the page: a dialog for one
 * yes/no question about the row you are already pointing at is ceremony, and
 * it loses the context of *which* plan you were about to remove.
 *
 * It is deliberately not a browser `confirm()`, which cannot be styled, reads
 * as a site-wide error, and blocks the whole tab.
 *
 * The API refuses to delete a run that is still building, so a failure here
 * is shown against the row rather than swallowed: the plan is still there,
 * and the founder needs to know why.
 */

import { Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

export function DeletePlan({
  runId,
  label,
  onDeleted,
  className,
  /** `rail` is the small icon that appears on hover; `row` is a labelled button. */
  variant = "rail",
}: {
  runId: number;
  label: string;
  onDeleted?: () => void;
  className?: string;
  variant?: "rail" | "row";
}) {
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirmDelete() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteRun(runId);
      onDeleted?.();
      // `refresh` rather than a local splice: /runs is server-rendered, and
      // the rail's list is keyed off the pathname, so one refresh updates
      // both without either having to know about the other.
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
      setAsking(false);
    }
  }

  if (asking) {
    return (
      <span className={cn("flex items-center gap-1.5", className)}>
        <button
          type="button"
          onClick={confirmDelete}
          disabled={busy}
          className="rounded-full bg-nogo px-2.5 py-1 text-caption font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {busy ? "Deleting…" : "Delete"}
        </button>
        <button
          type="button"
          onClick={() => setAsking(false)}
          disabled={busy}
          className="rounded-full px-2.5 py-1 text-caption text-ink-muted transition-colors hover:text-ink"
        >
          Cancel
        </button>
      </span>
    );
  }

  return (
    <span className={cn("flex items-center gap-2", className)}>
      {error ? (
        <span role="alert" className="text-caption text-nogo">
          {error}
        </span>
      ) : null}
      <button
        type="button"
        onClick={() => setAsking(true)}
        aria-label={`Delete ${label}`}
        title="Delete plan"
        className={cn(
          "rounded-full text-ink-faint transition-colors hover:text-nogo",
          variant === "rail" ? "p-1" : "p-1.5 hover:bg-nogo-soft",
        )}
      >
        <Trash2 aria-hidden className="h-4 w-4" strokeWidth={1.75} />
      </button>
    </span>
  );
}
