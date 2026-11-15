"use client";

/**
 * Asks for the shared access code on a hosted deployment.
 *
 * Locally there is no code, the check passes, and this renders its children
 * untouched. On a deployment the API answers 401 until the right code is sent;
 * this shows a small form, stores the code, and lets the app through. Any later
 * 401 (the code was changed, or storage was cleared) brings the form back.
 *
 * The children are rendered while the first check runs, not after it: waiting
 * would blank every page for the length of a network round trip, and a locked
 * deployment replaces them within moments anyway.
 */

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { Button } from "@/components/primitives";
import { Field, FormError, TextInput } from "@/components/form";
import { ACCESS_REQUIRED_EVENT, setAccessCode, syncAccessCookie } from "@/lib/access";
import { ApiError, api } from "@/lib/api";

export function AccessGate({ children }: { children: ReactNode }) {
  const [locked, setLocked] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const check = useCallback(async () => {
    try {
      await api.accessCheck();
      setLocked(false);
      return true;
    } catch (e) {
      // Only a 401 means "ask for the code"; any other failure is for the
      // pages themselves to report in their own words.
      if (e instanceof ApiError && e.status === 401) setLocked(true);
      return false;
    }
  }, []);

  useEffect(() => {
    // The first check is written out here, with state set in the promise's
    // callbacks, rather than calling `check`: the lint rule (rightly) forbids
    // setting state synchronously in an effect body.
    let cancelled = false;
    // A code saved before the cookie existed: write the cookie and reload once, so the
    // server can render the page with it.
    if (syncAccessCookie()) {
      window.location.reload();
      return;
    }
    api.accessCheck().catch((e) => {
      if (!cancelled && e instanceof ApiError && e.status === 401) setLocked(true);
    });
    const relock = () => setLocked(true);
    window.addEventListener(ACCESS_REQUIRED_EVENT, relock);
    return () => {
      cancelled = true;
      window.removeEventListener(ACCESS_REQUIRED_EVENT, relock);
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setChecking(true);
    setAccessCode(code);
    const ok = await check();
    setChecking(false);
    if (!ok) {
      setError("That code didn't work. Check it and try again.");
      return;
    }
    // Reload so pages rendered on the server are rendered again, now with the code.
    window.location.reload();
  }

  if (!locked) return <>{children}</>;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6">
      <h1 className="text-title font-semibold text-ink">Flywheel</h1>
      <p className="mt-2 text-body text-ink-muted">
        This demo is protected. Enter the access code you were given to continue.
      </p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <Field label="Access code" htmlFor="access-code">
          <TextInput
            id="access-code"
            type="password"
            autoComplete="off"
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value)}
            invalid={Boolean(error)}
          />
        </Field>
        {error ? <FormError message={error} /> : null}
        <Button type="submit" disabled={checking || !code.trim()}>
          {checking ? "Checking…" : "Continue"}
        </Button>
      </form>
    </main>
  );
}
