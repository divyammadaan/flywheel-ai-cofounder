"use client";

/**
 * Collapsing the rail.
 *
 * The rail is 256px of persistent navigation, which is right when you are
 * moving between plans and wrong when you are reading one: a plan is dense,
 * and on a laptop that strip is a tenth of the window spent on links you are
 * not using. Collapsed, it keeps the four things worth one click and gives
 * the width back.
 *
 * The state lives on `<html>` as `data-rail`, set before first paint by
 * `RailScript`, and the *width itself is CSS* (see globals.css) rather than
 * a React class. That ordering matters: if the width came from component
 * state read out of localStorage, the rail would paint open and snap shut a
 * frame later, on every single navigation. This is the same approach
 * `ThemeToggle` uses, and for the same reason.
 *
 * `useSyncExternalStore` then keeps only the button's own label and icon in
 * step, with a server snapshot of "open" that matches what the script has
 * already painted, so there is nothing to reconcile on hydration.
 */

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useSyncExternalStore } from "react";

const STORAGE_KEY = "flywheel-rail";

function subscribe(onChange: () => void) {
  // Fires in OTHER tabs, so two open tabs agree; this tab's own click
  // dispatches its own event below.
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

function getSnapshot(): boolean {
  return localStorage.getItem(STORAGE_KEY) === "collapsed";
}

function getServerSnapshot(): boolean {
  return false;
}

export function RailToggle({ className }: { className?: string }) {
  const collapsed = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose;

  function toggle() {
    const next = !collapsed;
    if (next) {
      document.documentElement.dataset.rail = "collapsed";
      localStorage.setItem(STORAGE_KEY, "collapsed");
    } else {
      document.documentElement.removeAttribute("data-rail");
      localStorage.removeItem(STORAGE_KEY);
    }
    window.dispatchEvent(new StorageEvent("storage"));
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      aria-expanded={!collapsed}
      className={`rounded-tile p-1.5 text-ink-faint transition-colors hover:bg-surface hover:text-ink ${className ?? ""}`}
    >
      <Icon aria-hidden className="h-4 w-4" strokeWidth={1.75} />
    </button>
  );
}

/** Applies the stored choice before the first paint. See the note above. */
export function RailScript() {
  const code = `try{if(localStorage.getItem("${STORAGE_KEY}")==="collapsed")document.documentElement.dataset.rail="collapsed"}catch(e){}`;
  return <script dangerouslySetInnerHTML={{ __html: code }} />;
}
