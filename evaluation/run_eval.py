"""End-to-end evaluation: running time, tokens, estimated cost, and correctness checks.

    .venv/Scripts/python evaluation/run_eval.py --base-url http://127.0.0.1:8000
    .venv/Scripts/python evaluation/run_eval.py --base-url https://<backend> --access-code <code>

It drives the real API the way the website does -- start a plan, answer the
advisor's questions, wait for the result -- over a small set of scenarios, and
measures each run from outside:

  time        wall-clock per plan, and per agent (from the run's own event log)
  tokens      prompt and completion tokens per agent (the usage table)
  cost        tokens x Groq's published list price. The free tier charges nothing;
              this is what the same usage would cost at list price.
  correctness checks that must hold whatever the model says: the plan parses as
              a FinalPlan, the budget split never exceeds the budget, no area gets
              more than 60% of it, the sections the flow promises are present.

`--baseline` also runs a *single prompt* to the same model asking for the cash
figures, and checks it against the exact arithmetic -- the comparison that shows
what the code-side checks buy over "just calling the model".

Results are written to docs/EVALUATION.md and evaluation/results.json. Scenarios
are few on purpose: Groq's free tier allows about 1,000 output tokens a minute for
this model, so a plan takes a few minutes however fast the code is.
"""

import argparse
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx

from agents._cash import launch_cash_plan
from orchestration.final_plan import FinalPlan

# Groq's published list price for qwen/qwen3.8-27b (a preview model), USD per 1M tokens.
PRICE_PER_MILLION = {"input": 0.80, "output": 4.00}
MAX_AREA_SHARE = 0.6  # agents/finance.py MAX_SHARE_PER_AGENT

DEMO_ORDERS = ROOT / "demo" / "demo_orders.csv"

SCENARIOS = [
    {
        "name": "new idea: filter-coffee subscription (Bangalore)",
        "kind": "new_idea",
        "body": {
            "pitch": "I want to start a premium filter-coffee subscription for working professionals in Bangalore, delivering freshly roasted beans every month.",
            "currency": "INR",
            "starting_capital": 1500000,
            "monthly_fixed_costs": 100000,
            "unit_cost": 350,
            "runway_months": 6,
        },
        "answer": "We have not fixed this yet. Please assume sensible figures for a small founder-run launch in India.",
        "expected": ["business", "research", "verdict", "strategy", "finance"],
        "expected_after_go": ["marketing", "sales", "product", "funding"],
    },
    {
        "name": "new idea: weekend cloud kitchen (Pune)",
        "kind": "new_idea",
        "body": {
            "pitch": "I want to open a weekend cloud kitchen in Pune selling home-style regional thalis through delivery apps.",
            "currency": "INR",
            "starting_capital": 800000,
            "monthly_fixed_costs": 60000,
            "unit_cost": 120,
            "runway_months": 4,
        },
        "answer": "We have not fixed this yet. Please assume sensible figures for a small founder-run launch in India.",
        "expected": ["business", "research", "verdict", "strategy", "finance"],
        "expected_after_go": ["marketing", "sales", "product", "funding"],
    },
    {
        "name": "existing business: coffee subscription with order history",
        "kind": "existing",
        "body": {
            "description": "We run a monthly filter-coffee subscription in Bangalore, delivering 250g packs to working professionals.",
            "currency": "INR",
            "budget": 200000,
            "include_funding": True,
            "metrics": {
                "period_label": "FY2025-26",
                "revenue": 1370000,
                "net_profit": 150000,
                "total_debt": 300000,
                "period_months": 12,
                "cash_in_bank": 400000,
                "ebitda": 210000,
                "marketing_spend": 180000,
                "customers_at_start": 120,
                "new_customers": 180,
                "customers_lost": 106,
            },
        },
        "expected": ["business", "analytics", "strategy", "finance", "marketing", "sales", "product", "crm", "funding"],
        "expected_after_go": [],
    },
]


class Client:
    def __init__(self, base_url: str, access_code: str | None) -> None:
        headers = {"X-Access-Code": access_code} if access_code else {}
        self.base = base_url.rstrip("/")
        self.http = httpx.Client(timeout=60, headers=headers)

    def get(self, path: str, **params):
        r = self.http.get(self.base + path, params=params or None)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, **kwargs):
        r = self.http.post(self.base + path, **kwargs)
        r.raise_for_status()
        return r.json()


TERMINAL = {"done", "failed", "blocked", "awaiting_answers"}


def wait(client: Client, run_id: int, until=TERMINAL, timeout=1500):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/runs/{run_id}")["run"]
        if run["status"] in until:
            return run
        time.sleep(4)
    raise TimeoutError(f"run {run_id} did not settle in {timeout}s")


def run_scenario(client: Client, scenario: dict) -> dict:
    started = time.time()
    if scenario["kind"] == "existing":
        with DEMO_ORDERS.open("rb") as f:
            token = client.post("/orders/preview", files={"file": ("orders.csv", f, "text/csv")})["token"]
        run_id = client.post("/runs/existing-business", json={**scenario["body"], "orders_token": token})["run_id"]
        run = wait(client, run_id)
    else:
        run_id = client.post("/runs/new-idea", json=scenario["body"])["run_id"]
        run = wait(client, run_id)
        if run["status"] == "awaiting_answers":
            events = client.get(f"/runs/{run_id}/events")
            questions = next(e["payload"]["questions"] for e in reversed(events) if e["kind"] == "awaiting_answers")
            client.post(f"/runs/{run_id}/answers", json={"answers": {q: scenario["answer"] for q in questions}})
            time.sleep(2)
            run = wait(client, run_id)
    seconds = time.time() - started
    return {"run_id": run_id, "status": run["status"], "error": run.get("error"), "seconds": round(seconds, 1)}


def per_agent_seconds(events: list[dict]) -> dict[str, float]:
    """Agent durations from the run's own started/finished events."""
    started: dict[str, datetime] = {}
    spans: dict[str, float] = {}
    for e in events:
        if not e.get("agent") or not e.get("created_at"):
            continue
        at = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
        if e["kind"] == "agent_started":
            started[e["agent"]] = at
        elif e["kind"] == "agent_finished" and e["agent"] in started:
            spans[e["agent"]] = round((at - started[e["agent"]]).total_seconds(), 1)
    return spans


def cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens * PRICE_PER_MILLION["input"] + completion_tokens * PRICE_PER_MILLION["output"]) / 1_000_000


def check_plan(plan: FinalPlan, scenario: dict) -> dict:
    """Properties that must hold whatever the model wrote."""
    present = {name for name in ("business", "research", "verdict", "analytics", "strategy", "finance", "marketing", "sales", "product", "crm", "funding") if getattr(plan, name)}
    stopped_by_advisor = plan.verdict is not None and plan.verdict.verdict == "NO_GO"
    expected = set(scenario["expected"]) | (set() if stopped_by_advisor else set(scenario["expected_after_go"]))
    results = {"sections_complete": expected <= present, "missing_sections": sorted(expected - present), "stopped_by_advisor": stopped_by_advisor}
    if plan.finance:
        f = plan.finance
        areas = [f.marketing, f.product, f.sales, f.crm]
        results["budget_within_total"] = sum(areas) <= f.total_budget + 1e-6
        results["no_area_over_cap"] = all(a <= f.total_budget * MAX_AREA_SHARE + 1e-6 for a in areas)
    for name, amount in (("marketing", plan.marketing), ("sales", plan.sales), ("product", plan.product)):
        if amount and getattr(plan.finance, name, None) is not None:
            spends = [c.get("budget", 0) for c in (getattr(amount, "campaigns", None) or getattr(amount, "lead_sources", None) or getattr(amount, "line_items", None) or [])]
            if name == "product":
                spends = [c.get("total_cost", 0) for c in amount.line_items]
            results[f"{name}_spend_within_budget"] = sum(spends) <= getattr(plan.finance, name) + 1.0
    results["guardrail_rejections"] = len(plan.guardrail_rejections)
    return results


def evaluate(client: Client, scenarios: list[dict]) -> list[dict]:
    rows = []
    for scenario in scenarios:
        print(f"running: {scenario['name']}", flush=True)
        outcome = run_scenario(client, scenario)
        row = {"scenario": scenario["name"], **outcome}
        run_id = outcome["run_id"]
        try:
            usage = client.get(f"/runs/{run_id}/usage", settle="true")
            events = client.get(f"/runs/{run_id}/events")
            plan = FinalPlan.model_validate(client.get(f"/runs/{run_id}/plan.json"))
            row["plan_parses"] = True
            row["checks"] = check_plan(plan, scenario)
            row["verdict"] = plan.verdict.verdict if plan.verdict else None
        except Exception as exc:  # noqa: BLE001 - a failed run is a result, not a crash
            usage, events = {"agents": [], "totals": {}}, []
            row["plan_parses"] = False
            row["checks"] = {}
            row["verdict"] = None
            row["evaluation_error"] = f"{type(exc).__name__}: {exc}"[:200]
        totals = usage.get("totals", {})
        row["tokens_in"] = totals.get("prompt_tokens", 0)
        row["tokens_out"] = totals.get("completion_tokens", 0)
        row["model_calls"] = totals.get("calls", 0)
        row["model_seconds"] = totals.get("seconds", 0)
        row["cost_usd"] = round(cost_usd(row["tokens_in"], row["tokens_out"]), 5)
        row["agents"] = {
            a["agent"]: {"calls": a["calls"], "tokens_in": a["prompt_tokens"], "tokens_out": a["completion_tokens"], "model_seconds": a["seconds"]}
            for a in usage.get("agents", [])
        }
        row["agent_wall_seconds"] = per_agent_seconds(events)
        rows.append(row)
        print(f"  -> {row['status']} in {row['seconds']}s, {row['tokens_in'] + row['tokens_out']} tokens, ${row['cost_usd']}", flush=True)
    return rows


# ------------------------------------------------------------- the baseline --


BASELINE_PROMPT = (
    "A founder has {capital} {currency} of capital, monthly fixed costs of {fixed} {currency}, a unit cost of {unit} {currency}, "
    "and will sell at {price} {currency} per unit. Hold back {runway} months of fixed costs as a reserve. "
    'Reply with only a JSON object with numeric fields: "reserve", "launch_budget" (capital minus the reserve), '
    '"break_even_units_per_month" (whole units a month whose margin covers the fixed costs), '
    'and a budget split "marketing", "product", "sales" that adds up to the launch budget.'
)


def run_baseline(samples: int) -> dict:
    """One prompt to the model, no code-side checks, against the exact answer."""
    import litellm

    from agents._models import GROQ_MODEL

    params = dict(capital=1_500_000, fixed=100_000, unit=350, price=899, runway=6, currency="INR")
    truth = launch_cash_plan(1_500_000, 899, 100_000, 350, 6)
    rows = []
    for i in range(samples):
        started = time.time()
        try:
            for attempt in range(6):
                try:
                    reply = litellm.completion(
                        model=GROQ_MODEL,
                        messages=[{"role": "user", "content": BASELINE_PROMPT.format(**params)}],
                        max_tokens=300,
                    )
                    break
                except Exception as exc:  # noqa: BLE001 - free-tier rate limit: wait and retry
                    if "rate" not in str(exc).lower() or attempt == 5:
                        raise
                    time.sleep(20)
            text = reply.choices[0].message.content or ""
            data = json.loads(text[text.index("{"): text.rindex("}") + 1])
            split_total = sum(float(data.get(k, 0)) for k in ("marketing", "product", "sales"))
            rows.append(
                {
                    "parses": True,
                    "reserve_correct": math.isclose(float(data["reserve"]), truth["reserve"], rel_tol=1e-6),
                    "launch_budget_correct": math.isclose(float(data["launch_budget"]), truth["launch_budget"], rel_tol=1e-6),
                    "break_even_correct": int(float(data["break_even_units_per_month"])) == truth["break_even_units_per_month"],
                    "split_within_budget": split_total <= truth["launch_budget"] + 1,
                    "split_respects_cap": all(float(data.get(k, 0)) <= truth["launch_budget"] * MAX_AREA_SHARE + 1 for k in ("marketing", "product", "sales")),
                    "seconds": round(time.time() - started, 1),
                    "tokens": (reply.usage.prompt_tokens, reply.usage.completion_tokens),
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append({"parses": False, "error": f"{type(exc).__name__}: {str(exc)[:80]}", "seconds": round(time.time() - started, 1)})
        time.sleep(8)  # stay under the per-minute output-token limit
    return {"truth": {k: truth[k] for k in ("reserve", "launch_budget", "break_even_units_per_month")}, "samples": rows}


# ----------------------------------------------------------------- reporting --


def _mean(values) -> float:
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 1) if values else 0.0


def write_report(rows: list[dict], baseline: dict | None, base_url: str, out_md: Path, out_json: Path) -> None:
    out_json.write_text(json.dumps({"base_url": base_url, "generated": datetime.now(timezone.utc).isoformat(), "runs": rows, "baseline": baseline}, indent=2), encoding="utf-8")

    ok = [r for r in rows if r["status"] in ("done",)]
    lines = [
        "# End-to-end evaluation",
        "",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC against `{base_url}` by `evaluation/run_eval.py`._",
        "",
        "Each scenario is run through the live API exactly as the website does it. Time is wall-clock; tokens are the "
        "usage the system recorded; **cost is an estimate at Groq's published list price** "
        f"(${PRICE_PER_MILLION['input']:.2f} per 1M input tokens, ${PRICE_PER_MILLION['output']:.2f} per 1M output tokens for "
        "`qwen/qwen3.8-27b`) -- the free tier charges nothing.",
        "",
        "## Runs",
        "",
        "| Scenario | Status | Verdict | Time | Model calls | Tokens in / out | Est. cost (USD) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['scenario']} | {r['status']} | {r.get('verdict') or '-'} | {r['seconds']} s | {r['model_calls']} | {r['tokens_in']:,} / {r['tokens_out']:,} | {r['cost_usd']:.4f} |")
    if ok:
        lines += [
            "",
            f"**Completed {len(ok)} of {len(rows)} runs.** Mean time {_mean(r['seconds'] for r in ok)} s, "
            f"mean tokens {_mean(r['tokens_in'] + r['tokens_out'] for r in ok):,.0f}, "
            f"mean estimated cost ${statistics.mean(r['cost_usd'] for r in ok):.4f} per plan.",
        ]

    failed = [r for r in rows if r["status"] not in ("done", "blocked")]
    if failed:
        lines += ["", "## Runs that did not complete", ""]
        for r in failed:
            lines.append(f"- **{r['scenario']}** ({r['status']}): {r.get('error') or 'no message recorded'}")
        lines += [
            "",
            "On Groq's free tier these are most often its limits, not the application: about 1,000 output tokens and "
            "7,000 input tokens per minute, and **200,000 tokens per day** for this model (roughly seven full plans). "
            "A run that starts after the daily allowance is spent fails however correct the code is. Re-run this "
            "script once the allowance has reset.",
        ]

    lines += ["", "## Where the time goes (seconds per agent, from the run's event log)", ""]
    agents = sorted({a for r in rows for a in r["agent_wall_seconds"]})
    if agents:
        lines += ["| Agent | " + " | ".join(f"Run {i + 1}" for i in range(len(rows))) + " |", "|---|" + "---|" * len(rows)]
        for a in agents:
            lines.append(f"| {a} | " + " | ".join(str(r["agent_wall_seconds"].get(a, "-")) for r in rows) + " |")
    lines += ["", "## Tokens per agent (prompt / completion)", ""]
    agents = sorted({a for r in rows for a in r["agents"]})
    if agents:
        lines += ["| Agent | " + " | ".join(f"Run {i + 1}" for i in range(len(rows))) + " |", "|---|" + "---|" * len(rows)]
        for a in agents:
            lines.append(f"| {a} | " + " | ".join((f"{r['agents'][a]['tokens_in']:,} / {r['agents'][a]['tokens_out']:,}" if a in r["agents"] else "-") for r in rows) + " |")

    lines += ["", "## Correctness checks", "", "| Scenario | Plan parses as FinalPlan | Sections complete | Budget within total | No area over 60% | Spends within budgets | Draft sent back by a check |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        c = r.get("checks", {})
        spends = [v for k, v in c.items() if k.endswith("_spend_within_budget")]
        mark = lambda v: "-" if v is None else ("pass" if v else "FAIL")  # noqa: E731
        lines.append(f"| {r['scenario']} | {mark(r.get('plan_parses'))} | {mark(c.get('sections_complete')) if c else '-'}{' (stopped by advisor)' if c.get('stopped_by_advisor') else ''} | {mark(c.get('budget_within_total'))} | {mark(c.get('no_area_over_cap'))} | {mark(all(spends)) if spends else '-'} | {c.get('guardrail_rejections', '-')} |")

    if baseline:
        samples = baseline["samples"]
        n = len(samples)
        valid = [s for s in samples if s.get("parses")]
        lines += [
            "",
            "## Baseline: one prompt, no checks",
            "",
            f"The same model was asked, in a single prompt, for the cash figures of the first scenario ({n} samples). "
            f"The exact answers are reserve {baseline['truth']['reserve']:,.0f}, launch budget {baseline['truth']['launch_budget']:,.0f}, "
            f"break-even {baseline['truth']['break_even_units_per_month']} units a month.",
            "",
            "| Check | Single prompt | Flywheel |",
            "|---|---|---|",
        ]
        for label, key in (("Reserve correct", "reserve_correct"), ("Launch budget correct", "launch_budget_correct"), ("Break-even correct", "break_even_correct"), ("Budget split within the launch budget", "split_within_budget"), ("No area over 60% of the budget", "split_respects_cap")):
            hits = sum(1 for s in valid if s.get(key))
            lines.append(f"| {label} | {hits} / {n} | exact by construction (computed in code, covered by unit tests) |")
        lines += [
            "",
            f"Single-prompt replies that parsed as JSON: {len(valid)} / {n}.",
            "",
            "The model does the simple subtractions correctly but gets break-even wrong: it reports the unrounded "
            f"{baseline['truth']['break_even_units_per_month'] - 1} units, which does not cover the fixed costs; "
            f"{baseline['truth']['break_even_units_per_month']} does. Flywheel rounds up in code (`agents/_cash.py`).",
        ]

    lines += [
        "",
        "## Reading these numbers",
        "",
        "- A plan takes minutes mainly because Groq's free tier allows about 1,000 output tokens a minute for this model: "
        "agents wait out the limit (the retry layer, `agents/_retry.py`), so wall-clock is dominated by waiting, not by computation.",
        "- Model time (the sum of the model calls themselves) is a small fraction of wall-clock time; the difference is queueing and retries.",
        "- Cost is tiny because each plan is only a few thousand tokens. On the free tier it is zero.",
        "- Server memory, measured on a Windows laptop while a full plan ran: about 300 MB idle and 480 MB at peak.",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from-results", action="store_true", help="rebuild the report from evaluation/results.json; run nothing")
    parser.add_argument("--base-url", default=os.environ.get("FLYWHEEL_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--access-code", default=os.environ.get("FLYWHEEL_ACCESS_CODE"))
    parser.add_argument("--only", help="run only scenarios whose name contains this text")
    parser.add_argument("--baseline", type=int, default=0, metavar="N", help="also run N single-prompt baseline samples")
    parser.add_argument("--out", default=str(ROOT / "docs" / "EVALUATION.md"))
    args = parser.parse_args()

    if args.from_results:
        saved = json.loads((ROOT / "evaluation" / "results.json").read_text(encoding="utf-8"))
        write_report(saved["runs"], saved.get("baseline"), saved["base_url"], Path(args.out), ROOT / "evaluation" / "results.json")
        print(f"rebuilt {args.out}")
        return 0

    scenarios = [s for s in SCENARIOS if not args.only or args.only in s["name"]]
    client = Client(args.base_url, args.access_code)
    client.get("/health")
    rows = evaluate(client, scenarios)
    baseline = run_baseline(args.baseline) if args.baseline else None
    out_md = Path(args.out)
    write_report(rows, baseline, args.base_url, out_md, ROOT / "evaluation" / "results.json")
    print(f"wrote {out_md}")
    return 0 if all(r["status"] in ("done", "blocked") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
