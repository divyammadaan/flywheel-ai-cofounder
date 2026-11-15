# End-to-end evaluation

_Generated 2026-11-14 06:28 UTC against `https://divyammadaan--flywheel-backend-serve.us-east.modal.run` by `evaluation/run_eval.py`._

Each scenario is run through the live API exactly as the website does it. Time is wall-clock; tokens are the usage the system recorded; **cost is an estimate at Groq's published list price** ($0.80 per 1M input tokens, $4.00 per 1M output tokens for `qwen/qwen3.8-27b`) -- the free tier charges nothing.

## Runs

| Scenario | Status | Verdict | Time | Model calls | Tokens in / out | Est. cost (USD) |
|---|---|---|---|---|---|---|
| new idea: filter-coffee subscription (Bangalore) | failed | PIVOT | 336.5 s | 8 | 18,915 / 3,463 | 0.0290 |
| new idea: weekend cloud kitchen (Pune) | failed | - | 157.8 s | 0 | 0 / 0 | 0.0000 |
| existing business: coffee subscription with order history | failed | - | 154.5 s | 1 | 1,680 / 185 | 0.0021 |

## Runs that did not complete

- **new idea: filter-coffee subscription (Bangalore)** (failed): The model provider is rate-limiting this account. Waiting a minute and running it again usually clears it. (it stopped while working on funding.)
- **new idea: weekend cloud kitchen (Pune)** (failed): The model provider is rate-limiting this account. Waiting a minute and running it again usually clears it. (it stopped while working on intake.)
- **existing business: coffee subscription with order history** (failed): The model provider is rate-limiting this account. Waiting a minute and running it again usually clears it. (it stopped while working on planning.)

On Groq's free tier these are most often its limits, not the application: about 1,000 output tokens and 7,000 input tokens per minute, and **200,000 tokens per day** for this model (roughly seven full plans). A run that starts after the daily allowance is spent fails however correct the code is. Re-run this script once the allowance has reset.

## Where the time goes (seconds per agent, from the run's event log)

| Agent | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| company_formation | 12.8 | - | - |
| founder_advisor | 3.0 | - | - |
| intake | 3.2 | - | 3.0 |
| market_research | 9.0 | - | - |
| planning | 155.6 | - | - |

## Tokens per agent (prompt / completion)

| Agent | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| company_formation | 1,703 / 538 | - | - |
| founder_advisor | 2,360 / 375 | - | - |
| intake | 1,681 / 125 | - | 1,680 / 185 |
| market_research | 4,995 / 546 | - | - |
| marketing | 2,455 / 537 | - | - |
| product | 1,975 / 502 | - | - |
| sales | 2,320 / 560 | - | - |
| strategy | 1,426 / 280 | - | - |

## Correctness checks

| Scenario | Plan parses as FinalPlan | Sections complete | Budget within total | No area over 60% | Spends within budgets | Draft sent back by a check |
|---|---|---|---|---|---|---|
| new idea: filter-coffee subscription (Bangalore) | pass | FAIL | pass | pass | pass | 0 |
| new idea: weekend cloud kitchen (Pune) | pass | FAIL | - | - | - | 0 |
| existing business: coffee subscription with order history | pass | FAIL | - | - | - | 0 |

## Baseline: one prompt, no checks

The same model was asked, in a single prompt, for the cash figures of the first scenario (5 samples). The exact answers are reserve 600,000, launch budget 900,000, break-even 183 units a month.

| Check | Single prompt | Flywheel |
|---|---|---|
| Reserve correct | 2 / 5 | exact by construction (computed in code, covered by unit tests) |
| Launch budget correct | 2 / 5 | exact by construction (computed in code, covered by unit tests) |
| Break-even correct | 0 / 5 | exact by construction (computed in code, covered by unit tests) |
| Budget split within the launch budget | 2 / 5 | exact by construction (computed in code, covered by unit tests) |
| No area over 60% of the budget | 2 / 5 | exact by construction (computed in code, covered by unit tests) |

Single-prompt replies that parsed as JSON: 2 / 5.

The model does the simple subtractions correctly but gets break-even wrong: it reports the unrounded 182 units, which does not cover the fixed costs; 183 does. Flywheel rounds up in code (`agents/_cash.py`).

## Reading these numbers

- A plan takes minutes mainly because Groq's free tier allows about 1,000 output tokens a minute for this model: agents wait out the limit (the retry layer, `agents/_retry.py`), so wall-clock is dominated by waiting, not by computation.
- Model time (the sum of the model calls themselves) is a small fraction of wall-clock time; the difference is queueing and retries.
- Cost is tiny because each plan is only a few thousand tokens. On the free tier it is zero.
- Server memory, measured on a Windows laptop while a full plan ran: about 300 MB idle and 480 MB at peak.
