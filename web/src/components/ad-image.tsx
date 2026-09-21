"use client";

/**
 * The generated ad image.
 *
 * Served by the API rather than read from the recorded path: Marketing stores
 * an absolute server path, which a browser cannot open.
 *
 * A client component purely for the error handler. The image is a bonus --
 * `tools/image_gen.py` fails soft, and the file can be cleaned up later -- so
 * a missing one removes itself rather than leaving a broken frame in the
 * middle of the plan.
 */

import { useState } from "react";

import { API_BASE } from "@/lib/api";

export function AdImage({ runId }: { runId: number }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;

  return (
    // eslint-disable-next-line @next/next/no-img-element -- served by the API, outside Next's loader
    <img
      src={`${API_BASE}/runs/${runId}/ad-image`}
      alt="The generated ad image for this campaign"
      width={128}
      height={128}
      loading="lazy"
      decoding="async"
      className="h-32 w-32 shrink-0 rounded-tile border border-line object-cover"
      onError={() => setFailed(true)}
    />
  );
}
