/**
 * One run, as a row in a list.
 *
 * Split out of app/page.tsx once the home page stopped showing runs at all
 * (they moved entirely to /runs) -- this is the one piece of that file
 * `/runs` still needed.
 *
 * The delete control sits beside the link rather than inside it: a button
 * nested in an anchor is invalid HTML, and clicking it would follow the link
 * instead of deleting anything.
 */

import Link from "next/link";

import { DeletePlan } from "@/components/delete-plan";
import { Pill } from "@/components/primitives";
import { planTitle, relativeTime } from "@/lib/format";
import type { Run } from "@/lib/types";

const STATUS: Record<string, { label: string; tone: "neutral" | "go" | "pivot" | "nogo" }> = {
  running: { label: "Working", tone: "neutral" },
  queued: { label: "Queued", tone: "neutral" },
  awaiting_answers: { label: "Needs you", tone: "pivot" },
  done: { label: "Ready", tone: "go" },
  blocked: { label: "Stopped", tone: "pivot" },
  failed: { label: "Failed", tone: "nogo" },
};

export function RunLink({ run }: { run: Run }) {
  const status = STATUS[run.status] ?? { label: run.status, tone: "neutral" as const };
  // The short name leads; the founder's own sentence sits under it as the
  // thing that actually tells two coffee subscriptions apart.
  const label = planTitle(run.label, run.id);
  const pitch = (run.label ?? "").trim();
  // The API refuses to delete a plan mid-build, so the control is not offered
  // for one -- a bin that always answers "no" is worse than no bin.
  const deletable = run.status !== "running" && run.status !== "queued";

  return (
    <div className="group/run flex items-center gap-4 pr-3 transition-colors hover:bg-surface-sunken">
      <Link href={`/runs/${run.id}`} className="flex min-w-0 flex-1 items-center gap-6 px-5 py-4">
        <div className="min-w-0 flex-1">
          <p className="truncate text-body font-medium text-ink">{label}</p>
          {pitch && pitch !== label ? (
            <p className="mt-0.5 truncate text-small text-ink-muted">{pitch}</p>
          ) : null}
          <p className="mt-0.5 text-caption text-ink-faint">
            {run.mode === "existing_business" ? "Operating business" : "New idea"} ·{" "}
            {relativeTime(run.updated_at)}
          </p>
        </div>
        <Pill tone={status.tone}>{status.label}</Pill>
      </Link>

      {deletable ? (
        <DeletePlan
          runId={run.id}
          label={label}
          variant="row"
          className="opacity-0 transition-opacity group-hover/run:opacity-100 focus-within:opacity-100"
        />
      ) : null}
    </div>
  );
}
