import type { Metadata } from "next";
import type { ReactNode } from "react";

// The page itself is a client component (form state), and Next.js only reads
// `metadata` from a server module -- this layout is that server module.
export const metadata: Metadata = { title: "A new idea" };

export default function NewIdeaLayout({ children }: { children: ReactNode }) {
  return children;
}
