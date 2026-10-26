"use client";

/**
 * The header-and-body layout for `Section`, pulled into its own client
 * component for one reason: it needs a ref, and `primitives.tsx` -- where
 * `Section` lives -- is imported by a server component
 * (`app/runs/[id]/page.tsx`). A hook anywhere in that file's import graph
 * would force Next to render the whole module, including every other
 * primitive in it, client-side. This component is the one piece that
 * actually needs the client runtime; everything else in primitives.tsx
 * stays server-renderable by not importing it directly.
 *
 * The ref is what lets the speak button read a section's own rendered text
 * at click time (`innerText`), rather than threading a second copy of
 * every section's words through props just so something could read them
 * aloud.
 */

import { useRef } from "react";
import type { ReactNode } from "react";

import { SpeakButton } from "@/components/speak-button";

export function SpeakableSection({
  title,
  lead,
  action,
  children,
}: {
  title: string;
  lead?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  const body = useRef<HTMLDivElement>(null);

  return (
    <>
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-title font-semibold text-ink">{title}</h2>
          {lead ? <p className="mt-1 text-small text-ink-muted">{lead}</p> : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {action}
          <SpeakButton getText={() => body.current?.innerText ?? ""} />
        </div>
      </div>
      <div ref={body}>{children}</div>
    </>
  );
}
