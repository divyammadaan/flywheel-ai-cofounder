# Existing-business demo: filter-coffee subscription (Bangalore)

Upload file: `demo/demo_orders.csv` (1,427 orders, 300 customers, 2025-09-01 to 2026-08-31). The same data is already consistent with the numbers below.

## Before you start
1. Ollama running, with `qwen3:4b` pulled (the CRM step needs it).
2. `GROQ_API_KEY` set in `.env`.
3. API: `.venv/Scripts/python -m uvicorn api.main:app --port 8000`
4. Web: `cd web && npm run dev`, then open http://localhost:3000/existing
5. A full run takes a few minutes (CRM on the local model is the slowest part). Do one dry run tonight so the answers are cached and tomorrow's run is much faster.

## Form values to enter

| Field | Value |
|---|---|
| Description | We run a monthly filter-coffee subscription in Bangalore. We roast beans from Chikmagalur and deliver 250g packs to working professionals in Indiranagar, Koramangala and HSR Layout. Customers mostly find us through Instagram, WhatsApp groups and referrals. |
| Currency | INR |
| Period label | FY2025-26 |
| Period length | 12 months |
| Revenue | 1370000 |
| Net profit | 150000 |
| Total debt | 300000 |
| Cash in bank | 400000 |
| EBITDA (optional) | 210000 |
| Marketing spend (optional) | 180000 |
| Customers at start (optional) | 120 |
| New customers (optional) | 180 |
| Customers lost (optional) | 106 |
| Budget to deploy next period | 200000 |
| Order history | upload `demo/demo_orders.csv` (check the preview says 1,427 rows, 300 customers, 0 skipped) |

## What the data shows (computed from the file)
- Order revenue: about 13.7 lakh, matching the revenue above.
- Average order: about 960. Repeat-customer rate: 71%.
- Revenue in the last 3 months is 17% lower than the 3 months before, a good story for "why plan now".
- Typical re-order gap: 29 days (measured, not assumed).
- Customer groups: Best 66 (44% of revenue), Slipping 51 (27%), Lost 106 (21%), New 45 (3%), Regulars 32 (5%).
- Top slipping customers appear by name in the CRM section (for example Rohan Mehta, Kavya Das).

## Suggested demo script (5 minutes)
1. Show the form and the upload preview: "Messy exports are fine; it reports skipped rows."
2. Start the run and point at the live progress list (Intake, Analytics, Strategy, Finance, then Marketing/Sales/Product/CRM together).
3. Open the plan: Analytics headline, the budget split (note no area exceeds 60%), customer groups with tooltips explaining each rule.
4. Open the CRM section: "This ran on the local model, so customer names stay on this laptop."
5. Use "Suggest a change" on Sales, for example "Only free channels for now", to show human-in-the-loop.
6. Optional: download the launch page.

## Likely questions and safe answers
- Why is Finance not an AI? Money maths must be exact, so plain code does it and tests cover it.
- Is customer data private? Customer names go only to the local model. Do not click the read-aloud button on the customer-groups section; that one sends text online.
- Is the improvement loop automatic? No. Each period the founder enters new numbers; comparing periods works in the command line and dashboard, not yet in the web app.

## If something goes wrong
- "Can't reach Flywheel": the API is not running on port 8000.
- Rate-limit message: wait a minute and rerun (Groq free tier).
- CRM says "no CRM plan this run": the small local model returned placeholder text twice; rerun.
- Regenerate the file anytime: `.venv/Scripts/python tools/sample_data.py --out demo/demo_orders.csv`
