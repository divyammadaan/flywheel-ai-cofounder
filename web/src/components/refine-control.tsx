"use client";

/**
 * "Suggest a change" -- the founder talking back to one agent.
 *
 * Scoped to the five agents nothing else depends on (marketing, sales,
 * product, crm, funding). Strategy and Finance decide what every other agent
 * is given, so refining either would leave the rest of the plan stale until
 * it was redone too -- out of scope here on purpose; see
 * `orchestration/cycle.py:REFINABLE_AGENTS`.
 *
 * The card's own footer, not a separate panel: a founder reading "How people
 * hear about you" should be able to react to it right there, not go hunting
 * for a global feedback box and pick the right section from a dropdown.
 *
 * On success this calls `router.refresh()` rather than touching any local
 * state. The backend already logs the redone output as a NEW Decision
 * Record and keeps the old one -- `toPlan()` already treats the newest
 * record for an agent as current -- so a server refetch is the entire
 * update. No client-side merge logic to keep in sync with the backend.
 */

import { RefreshCw, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/primitives";
import { ApiError, api } from "@/lib/api";
import type { RefinableAgent } from "@/lib/types";

const PLACEHOLDER: Record<RefinableAgent, string> = {
  marketing: "e.g. “Drop the Facebook ad, put that budget into Instagram instead”",
  sales: "e.g. “Only free channels for now — nothing with an upfront cost”",
  product: "e.g. “Source locally even if it costs a little more”",
  crm: "e.g. “Be warmer in tone — this reads a bit corporate”",
  funding: "e.g. “We already have two years of runway, push the raise later”",
};

export function RefineControl({
  runId,
  agent,
  cycle,
  revised,
}: {
  runId: number;
  agent: RefinableAgent;
  cycle: number;
  /** Whether this is already a redone version, for the small note below. */
  revised: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!feedback.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.refine(runId, agent, cycle, feedback.trim());
      setOpen(false);
      setFeedback("");
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That didn't go through. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="flex items-center justify-between gap-3">
        {revised ? (
          <p className="text-caption text-ink-faint">Revised on your feedback.</p>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex items-center gap-1.5 text-caption font-medium text-accent transition-colors hover:text-accent-hover"
        >
          <Sparkles aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
          Suggest a change
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="rounded-tile border border-line bg-surface-sunken p-4">
      <label htmlFor={`refine-${agent}`} className="text-small font-medium text-ink">
        What would you change here?
      </label>
      <textarea
        id={`refine-${agent}`}
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder={PLACEHOLDER[agent]}
        rows={2}
        autoFocus
        disabled={busy}
        className="mt-2 w-full rounded-tile border border-line bg-surface px-3 py-2 text-small text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none disabled:opacity-60"
      />
      {error ? <p className="mt-1.5 text-caption text-nogo">{error}</p> : null}
      <div className="mt-3 flex items-center gap-2.5">
        <Button type="submit" disabled={busy || !feedback.trim()} className="px-3 py-1.5 text-caption">
          {busy ? (
            <>
              <RefreshCw aria-hidden className="h-3.5 w-3.5 animate-spin" strokeWidth={2} />
              Redoing it{"…"}
            </>
          ) : (
            "Redo with this"
          )}
        </Button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setError(null);
          }}
          disabled={busy}
          className="text-caption text-ink-faint transition-colors hover:text-ink disabled:opacity-60"
        >
          Cancel
        </button>
      </div>
      {busy ? (
        <p className="mt-2 text-caption text-ink-faint">
          {agent === "crm"
            ? "This runs on the local model, so it can take up to 20 seconds."
            : "Usually just a few seconds."}
        </p>
      ) : null}
    </form>
  );
}
