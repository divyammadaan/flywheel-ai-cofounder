/**
 * The one link out of a form to the explanation.
 *
 * Deliberately small and unemphasised. The founder on a form has already
 * decided to fill it in; this is for the one who stops halfway and wants to
 * know what happens to what they typed, and it should cost them one click
 * without costing everyone else a column of prose.
 */

import { HelpCircle } from "lucide-react";
import Link from "next/link";

export function HowItWorksLink() {
  return (
    <Link
      href="/how-it-works"
      className="inline-flex items-center gap-1.5 text-small text-ink-muted transition-colors hover:text-ink"
    >
      <HelpCircle aria-hidden className="h-4 w-4" strokeWidth={1.75} />
      How it works
    </Link>
  );
}
