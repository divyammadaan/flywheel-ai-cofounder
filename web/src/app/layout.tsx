import type { Metadata } from "next";
import localFont from "next/font/local";

import "./globals.css";

/**
 * Geist, self-hosted.
 *
 * `next/font/google` fetches from fonts.gstatic.com at build time. That
 * connection is unreliable here and the retries destabilised the dev server
 * badly enough to return 500s, so the two variable faces are committed to
 * `src/fonts/` instead. Self-hosting is the better answer regardless: the
 * build stops depending on a third party being reachable, and no founder's
 * page load is announced to Google.
 *
 * Latin subset only -- the product's copy and every currency symbol it
 * formats (₹ $ € £) are covered, and the full set is six times the weight.
 */
const geistSans = localFont({
  src: "../fonts/Geist-Variable.woff2",
  variable: "--font-geist-sans",
  weight: "100 900",
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
});

const geistMono = localFont({
  src: "../fonts/GeistMono-Variable.woff2",
  variable: "--font-geist-mono",
  weight: "100 900",
  display: "swap",
  fallback: ["ui-monospace", "Cascadia Mono", "Consolas", "monospace"],
});

export const metadata: Metadata = {
  title: "Flywheel",
  description:
    "An AI co-founder: validate a new idea, or plan an operating business's next period.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-canvas text-ink">{children}</body>
    </html>
  );
}
