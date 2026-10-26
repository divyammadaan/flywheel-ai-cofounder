"use client";

/**
 * Read a section aloud.
 *
 * Groq first, the browser's own voice if Groq is unavailable -- not a
 * last-resort error state but an expected path. Orpheus' free tier is
 * reported at 10 requests/minute and roughly 100/day, thin enough that a
 * founder reading several sections of one plan can plausibly hit it, and
 * the model also needs a one-time terms acceptance in the Groq console
 * before the account can call it at all (the API returns 400
 * `model_terms_required` until that happens). Either way, read-aloud
 * should degrade to a flatter voice rather than go silent.
 *
 * Takes `getText: () => string` rather than a `text` prop so the caller can
 * defer reading the section's rendered content until the button is
 * actually clicked -- see `Section` in primitives.tsx, which reads its own
 * body's `innerText` at click time rather than threading a duplicate copy
 * of every section's words through props.
 */

import { Loader2, Square, Volume2 } from "lucide-react";
import { useRef, useState } from "react";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

type State = "idle" | "loading" | "playing";

export function SpeakButton({
  getText,
  className,
}: {
  getText: () => string;
  className?: string;
}) {
  const [state, setState] = useState<State>("idle");
  const audio = useRef<HTMLAudioElement | null>(null);

  function stopAll() {
    audio.current?.pause();
    audio.current = null;
    window.speechSynthesis?.cancel();
    setState("idle");
  }

  function speakWithBrowserVoice(text: string) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => setState("idle");
    utterance.onerror = () => setState("idle");
    window.speechSynthesis.speak(utterance);
    setState("playing");
  }

  async function play() {
    const text = getText().trim();
    if (!text) return;
    setState("loading");

    // Groq path first, unconditionally -- it has nothing to do with
    // whether the browser also happens to offer its own voice.
    try {
      const blob = await api.synthesize(text);
      const el = new Audio(URL.createObjectURL(blob));
      el.onended = () => setState("idle");
      el.onerror = () => setState("idle");
      audio.current = el;
      await el.play();
      setState("playing");
      return;
    } catch {
      // Falls through to the browser voice below -- this is the expected
      // path when Orpheus is rate-limited or its terms aren't accepted
      // yet, not an exceptional one, so there is no error state shown
      // here. The founder hears a flatter voice; they don't see a failure.
    }

    if ("speechSynthesis" in window) {
      speakWithBrowserVoice(text);
    } else {
      setState("idle");
    }
  }

  const label = state === "playing" ? "Stop reading" : "Read this section aloud";

  return (
    <button
      type="button"
      onClick={state === "idle" ? play : stopAll}
      disabled={state === "loading"}
      title={label}
      aria-label={label}
      className={cn(
        "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-ink-faint transition-colors hover:bg-surface-sunken hover:text-ink",
        className,
      )}
    >
      {state === "loading" ? (
        <Loader2 aria-hidden className="h-4 w-4 animate-spin" strokeWidth={2} />
      ) : state === "playing" ? (
        <Square aria-hidden className="h-3.5 w-3.5" strokeWidth={2} fill="currentColor" />
      ) : (
        <Volume2 aria-hidden className="h-4 w-4" strokeWidth={1.75} />
      )}
    </button>
  );
}
