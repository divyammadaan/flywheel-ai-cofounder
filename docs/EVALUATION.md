# End-to-end evaluation

Performance, cost and correctness of the deployed system, measured by `evaluation/run_eval.py`
(which drives the real API the way the website does) and by reading back plans started from the
website. **Cost is an estimate at Groq's published list price** ($0.80 per 1M input tokens,
$4.00 per 1M output tokens for `qwen/qwen3.8-27b`); the free tier charges nothing.

## 1. Plans completed on the live deployment (Modal + Neon + Groq)

Both were started by hand from the website at https://flywheel-ai-cofounder.vercel.app and read
back from the backend afterwards.

| | New idea (millet breakfast, Pune) | Existing business (coffee subscription) |
|---|---|---|
| Status | done | done |
| Verdict | PIVOT (plan continued on the advisor's changed direction) | not applicable |
| Time spent in agents | 218.7 s (the founder's answering time is not counted) | 101.5 s |
| Model calls | 10 | 8 |
| Tokens in / out | 23,743 / 5,234 | 15,162 / 3,345 |
| Estimated cost (USD) | 0.0399 | 0.0255 |
| Execution agents ran over | A2A | A2A |
| Callback events recorded | 25 | 22 |
| Plan parses as `FinalPlan` | pass | pass |
| All promised sections present | pass | pass |
| Budget split within the total | pass | pass |
| No area over 60% of the budget | pass | pass |
| Marketing, sales and product spends within their budgets | pass | pass |
| Drafts sent back by a check | 0 | 0 |

Customer groups found in the order file (existing business): Best 66, Regular 32, New 45, Slipping 51, Lost 106 (300 customers).

### Where the time went (seconds per step, from the run's event log)

| Step | New idea (s) | Existing business (s) |
|---|---|---|
| company_formation | 5.5 | - |
| founder_advisor | 72.4 | - |
| funding | 5.6 | 21.3 |
| intake | 6.6 | 4.5 |
| market_research | 15.3 | - |
| planning | 113.3 | 75.7 |

"planning" is the whole planning engine: Strategy, Finance and the four execution agents over A2A.

### Tokens and model time per agent

| Agent | New idea (tokens in / out · model s) | Existing business (tokens in / out · model s) |
|---|---|---|
| analytics | - | 737 / 175 · 4.2 |
| company_formation | 1,772 / 478 · 2.6 | - |
| crm | - | 2,621 / 404 · 2.1 |
| founder_advisor | 2,895 / 442 · 1.5 | - |
| funding | 2,403 / 813 · 2.7 | 2,548 / 814 · 2.7 |
| intake | 1,746 / 259 · 1.2 | 1,714 / 300 · 1.3 |
| market_research | 1,760 / 855 · 2.7 | - |
| marketing | 2,875 / 450 · 1.6 | 2,280 / 516 · 1.6 |
| product | 2,250 / 652 · 2.9 | 2,135 / 567 · 1.6 |
| sales | 5,967 / 990 · 3.6 | 1,858 / 348 · 0.9 |
| strategy | 2,075 / 295 · 4.2 | 1,269 / 221 · 2.9 |

Finance makes no model call, so it does not appear.

## 2. An earlier completed run (local backend, 13 Nov)

Before deployment the harness completed one scenario against a local backend:

| Scenario | Status | Verdict | Time | Model calls | Tokens in / out | Est. cost |
|---|---|---|---|---|---|---|
| new idea: filter-coffee subscription (Bangalore) | done | PIVOT | 330.9 s | 9 | 23,171 / 4,494 | $0.0365 |

All correctness checks passed on it (plan parses, sections complete, budget within total, no area
over 60%, spends within budgets). Its per-step times: planning 197.5 s, funding 33.4 s, founder
advisor 38.5 s, company formation 28.0 s, market research 26.8 s, intake 2.0 s. That is about 5.5
minutes of wall-clock time including the rate-limit waits.

## 3. Harness runs that did not complete, and why

The harness was run twice. Only the first run completed anything; both were stopped by Groq's
free-tier limits, **not** by the application:

| Session | Result | Cause |
|---|---|---|
| Local backend, 13 Nov | 1 of 3 scenarios completed | one request exceeded the per-minute input limit (see below), and then the daily allowance ran out |
| Live backend, 14 Nov | 0 of 3 completed | the daily allowance ran out part-way: every run ended with "rate-limiting this account" |

Groq's free tier allows about **1,000 output tokens and 7,000 input tokens a minute and 200,000
tokens a day** for this model. A full plan uses roughly 18,000 to 27,000 tokens, so the day's
allowance covers about seven plans and development testing consumes most of it.

One failure in the first session exposed a **real bug**, now fixed: when a call was rate-limited,
the retry re-sent the same message into the same ADK session, so each retry's request was larger
than the last until one exceeded the 7,000-token input limit and could never succeed. Each failed
attempt now starts in a clean session. `tests/test_adk_sessions.py` shows 1, 1, 1, 1 messages per
request with the fix and 1, 2, 3, 4 without it.

The raw output of the latest harness run is kept in `evaluation/last_run_report.md` and
`evaluation/results.json`.

## 4. Baseline: one prompt to the same model, no code-side checks

The model was asked, in a single prompt, for the cash figures of the new-idea scenario (capital
1,500,000; fixed costs 100,000 a month; unit cost 350; price 899; 6 months of reserve). The exact
answers are: reserve 600,000, launch budget 900,000, break-even 183 units a month. Seven replies
parsed as JSON across two baseline runs (five in the first run, two in the second, where the rest
were rate-limited):

| Check | Single prompt | Flywheel |
|---|---|---|
| Reserve correct | 7 of 7 | exact (computed in code, covered by unit tests) |
| Launch budget correct | 7 of 7 | exact |
| Break-even correct | **0 of 7** | exact (rounded up in code, `agents/_cash.py`) |
| Budget split within the launch budget | 7 of 7 | exact |
| No area over 60% | 7 of 7 | exact |

The model does the subtractions correctly but reports the unrounded 182 units for break-even, which
does not cover the fixed costs; 183 does. (The second baseline run shows lower "correct" counts in
its raw output only because three of its five replies were rate-limited rather than wrong.)

## 5. Reading the results

- **Time.** A plan takes roughly two to six minutes. The model calls themselves add up to well under
  a minute; the rest is the agents waiting out Groq's per-minute limits (the retry layer,
  `agents/_retry.py`, waits for the interval the provider reports).
- **Cost.** About $0.03 to $0.04 per plan at list price, and nothing on the free tier.
- **Correctness.** Every completed plan passed the checks that must hold whatever the model writes.
- **Memory.** Measured on a Windows laptop while a full plan ran: about 300 MB idle and 480 MB at
  peak (the reason a 512 MB free host is too small).
- **Provider limits are the real constraint** for a demo: do not spend the daily allowance on
  rehearsals the day before.

## 6. Reproduce

```
.venv\Scripts\python evaluation\run_eval.py --base-url https://<backend> --access-code <code> --baseline 5
```

Run it when the day's Groq allowance has recovered, one scenario at a time (`--only`) if needed.
`--from-results` rebuilds the report from the saved results without running anything.
