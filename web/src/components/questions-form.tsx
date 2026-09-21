"use client";

/**
 * The clarifying questions.
 *
 * Market Research decides what it still needs to know before anyone can rule
 * on the idea, so these are generated per business rather than fixed. The
 * screen says why it is asking -- a founder who thinks a form is bureaucracy
 * answers it badly, and these answers feed straight into the verdict.
 *
 * Blank answers are allowed. Some questions genuinely have no answer yet
 * ("do you have a waitlist?" -- no), and forcing a made-up one would poison
 * the plan. Skipping is shown as a real choice rather than a validation error.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button, Card } from "@/components/primitives";
import { FormError, TextArea } from "@/components/form";
import { ApiError, api } from "@/lib/api";

export function QuestionsForm({
  runId,
  questions,
}: {
  runId: number;
  questions: string[];
}) {
  const router = useRouter();
  const [answers, setAnswers] = useState<string[]>(() => questions.map(() => ""));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const answered = answers.filter((a) => a.trim()).length;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      // Keyed by the question, which is what the advisor is given -- an index
      // would lose the association entirely.
      const payload: Record<string, string> = {};
      questions.forEach((question, i) => {
        if (answers[i]?.trim()) payload[question] = answers[i].trim();
      });
      await api.submitAnswers(runId, payload);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <Card className="overflow-hidden">
      <header className="border-b border-line px-6 py-5 sm:px-8">
        <h2 className="text-title font-semibold text-ink">
          A few things before I can rule on this
        </h2>
        <p className="mt-1.5 max-w-2xl text-small text-ink-muted">
          The research turned up what it could. These are the gaps that actually change the
          answer — your costs, your head start, your edge. Skip any you don&apos;t know yet;
          a guess here becomes a guess in the plan.
        </p>
      </header>

      <form onSubmit={submit} className="space-y-6 px-6 py-6 sm:px-8">
        {questions.map((question, i) => (
          <div key={i}>
            <label
              htmlFor={`answer-${i}`}
              className="flex gap-3 text-body text-ink"
            >
              <span className="tnum mt-px shrink-0 text-small font-semibold text-ink-faint">
                {i + 1}
              </span>
              <span className="min-w-0">{question}</span>
            </label>
            <div className="mt-2.5 pl-8">
              <TextArea
                id={`answer-${i}`}
                value={answers[i]}
                rows={2}
                className="min-h-20"
                placeholder="Your answer, or leave blank"
                onChange={(e) => {
                  const next = [...answers];
                  next[i] = e.target.value;
                  setAnswers(next);
                }}
              />
            </div>
          </div>
        ))}

        {error ? <FormError message={error} /> : null}

        <div className="flex flex-wrap items-center gap-4 border-t border-line pt-6">
          <Button type="submit" disabled={submitting}>
            {submitting ? "Sending…" : "Get my verdict"}
          </Button>
          <p className="text-caption text-ink-faint">
            {answered === questions.length
              ? "All answered."
              : `${answered} of ${questions.length} answered — the rest will be treated as unknown.`}
          </p>
        </div>
      </form>
    </Card>
  );
}
