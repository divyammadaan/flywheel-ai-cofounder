import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Your business today" };

export default function ExistingBusinessLayout({ children }: { children: ReactNode }) {
  return children;
}
