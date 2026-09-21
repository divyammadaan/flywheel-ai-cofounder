"use client";

/**
 * Light / dark / system, in the rail.
 *
 * The tokens in globals.css already have a complete dark palette gated on
 * `prefers-color-scheme` -- this component is the missing other half: a
 * founder working late shouldn't have to change their OS setting to get a
 * dark screen, and one who prefers light shouldn't be stuck with whatever
 * their OS happens to be set to.
 *
 * The choice is read through `useSyncExternalStore` rather than a plain
 * `useState` + effect: localStorage doesn't exist during the server render,
 * so a state initialised from it would show one value in the SSR'd HTML and
 * a different one the instant the client mounts -- a real hydration
 * mismatch, not just a lint complaint. `getServerSnapshot` always answers
 * "system", matching what `ThemeScript` below already painted before React
 * ever ran, so there is nothing to reconcile.
 */

import { Laptop, Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

const STORAGE_KEY = "flywheel-theme";
type Choice = "system" | "light" | "dark";
const ORDER: Choice[] = ["system", "light", "dark"];

const ICON = { system: Laptop, light: Sun, dark: Moon };
const LABEL = { system: "Matching your system", light: "Light", dark: "Dark" };

function subscribe(onChange: () => void) {
  // Storage events fire in OTHER tabs, not the one that wrote the value, so
  // this also keeps two open tabs in sync with each other.
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

function getSnapshot(): Choice {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

function getServerSnapshot(): Choice {
  return "system";
}

export function ThemeToggle({ className }: { className?: string }) {
  const choice = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  function cycle() {
    const next = ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length];
    apply(next);
    // useSyncExternalStore only re-renders on the "storage" event, which the
    // tab that wrote the value never receives itself -- so this tab's own
    // click needs its own nudge.
    window.dispatchEvent(new StorageEvent("storage"));
  }

  const Icon = ICON[choice];

  return (
    <button
      type="button"
      onClick={cycle}
      className={`flex w-full items-center gap-2.5 rounded-tile px-3 py-2 text-small text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink ${className ?? ""}`}
      aria-label={`Theme: ${LABEL[choice]}. Click to change.`}
    >
      <Icon aria-hidden className="h-4 w-4 shrink-0" strokeWidth={1.75} />
      <span>{LABEL[choice]}</span>
    </button>
  );
}

function apply(choice: Choice) {
  if (choice === "system") {
    document.documentElement.removeAttribute("data-theme");
    localStorage.removeItem(STORAGE_KEY);
  } else {
    document.documentElement.dataset.theme = choice;
    localStorage.setItem(STORAGE_KEY, choice);
  }
}

/**
 * Sets the theme attribute before the first paint.
 *
 * Rendered as a plain `<script>` in `layout.tsx`, ahead of `children` --
 * without this, the page paints in the wrong theme for one frame and then
 * snaps to the stored one, which reads as a flash of the wrong product.
 */
export function ThemeScript() {
  const code = `try{var t=localStorage.getItem("${STORAGE_KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;
  return <script dangerouslySetInnerHTML={{ __html: code }} />;
}
