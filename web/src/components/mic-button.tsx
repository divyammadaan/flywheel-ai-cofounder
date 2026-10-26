"use client";

/**
 * Dictate instead of type.
 *
 * One component used in two places -- the composer's first sentence and a
 * refine box's objection -- both of which are exactly the kind of text
 * someone would rather say than type, especially from a phone. It owns the
 * whole record -> upload -> transcribe round trip and hands the caller only
 * the text, via `onTranscript`; the caller decides whether that replaces or
 * appends to what's already there.
 *
 * Three states, one icon each: idle (Mic), recording (Square, pulsing,
 * click to stop), transcribing (Loader2, spinning). There is no separate
 * "stop and discard" -- stopping always sends what was recorded, because a
 * false start is rare enough that re-recording is less friction than a
 * second control for it.
 *
 * Permission and hardware failures are shown inline rather than thrown:
 * the composer and the refine box are small surfaces, and a toast or a
 * console error is easy to miss on either.
 */

import { Loader2, Mic, Square } from "lucide-react";
import { useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/cn";

type State = "idle" | "recording" | "transcribing";

export function MicButton({
  onTranscript,
  className,
}: {
  onTranscript: (text: string) => void;
  className?: string;
}) {
  const [state, setState] = useState<State>("idle");
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const stream = useRef<MediaStream | null>(null);

  async function start() {
    setError(null);
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      // Covers both "denied" and "no microphone" -- the browser doesn't
      // distinguish them in a way worth telling the founder apart, and
      // either way the fix on their end is the same: check mic access.
      setError("Couldn't reach the microphone. Check your browser's permission for this site.");
      return;
    }

    // MediaRecorder picks its own container; Groq's transcription endpoint
    // reads the extension to know the format, so the filename sent later
    // has to match whatever mimeType actually got negotiated here rather
    // than being hardcoded.
    const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
    const rec = new MediaRecorder(stream.current, mime ? { mimeType: mime } : undefined);
    chunks.current = [];
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.current.push(e.data);
    };
    rec.onstop = () => void finish(rec.mimeType || "audio/webm");
    recorder.current = rec;
    rec.start();
    setState("recording");
  }

  function stop() {
    recorder.current?.stop();
    stream.current?.getTracks().forEach((t) => t.stop());
    setState("transcribing");
  }

  async function finish(mimeType: string) {
    const blob = new Blob(chunks.current, { type: mimeType });
    const ext = mimeType.includes("webm") ? "webm" : mimeType.includes("mp4") ? "mp4" : "wav";
    try {
      const { text } = await api.transcribe(blob, `audio.${ext}`);
      onTranscript(text);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't transcribe that. Try again.");
    } finally {
      setState("idle");
    }
  }

  const label =
    state === "recording" ? "Stop recording" : state === "transcribing" ? "Transcribing…" : "Dictate";

  return (
    <span className="inline-flex items-center gap-1.5">
      <button
        type="button"
        onClick={state === "recording" ? stop : state === "idle" ? start : undefined}
        disabled={state === "transcribing"}
        title={label}
        aria-label={label}
        aria-pressed={state === "recording"}
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-colors",
          state === "recording"
            ? "animate-pulse bg-nogo text-white"
            : "text-ink-faint hover:bg-surface-sunken hover:text-ink",
          className,
        )}
      >
        {state === "recording" ? (
          <Square aria-hidden className="h-3.5 w-3.5" strokeWidth={2} fill="currentColor" />
        ) : state === "transcribing" ? (
          <Loader2 aria-hidden className="h-4 w-4 animate-spin" strokeWidth={2} />
        ) : (
          <Mic aria-hidden className="h-4 w-4" strokeWidth={1.75} />
        )}
      </button>
      {error ? (
        <span role="alert" className="text-caption text-nogo">
          {error}
        </span>
      ) : null}
    </span>
  );
}
