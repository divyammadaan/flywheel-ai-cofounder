"""The Flywheel HTTP API.

The engine is untouched: every endpoint here drives the same
`orchestration/` functions the CLIs call. What this layer adds is what a web
client needs and a terminal does not -- long work moved off the request, a
progress stream a reloaded browser can rejoin, and per-field validation.

Run it with:
    .venv/Scripts/python -m uvicorn api.main:app --reload --port 8000
"""

import asyncio
import json
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from agents.analytics import PeriodMetrics
from agents._segments import SEGMENT_DEFINITIONS, SEGMENT_LABELS, SEGMENTS
from api import flows, jobs, uploads
from api.schemas import (
    AnswersRequest,
    EventOut,
    ExistingBusinessRequest,
    NewIdeaRequest,
    OrdersPreview,
    RecordOut,
    RefineRequest,
    RunCreated,
    RunDetail,
    RunSummary,
    UsageOut,
)
from observability.usage import usage_summary
from orchestration.cycle import REFINABLE_AGENTS, RefineError, refine_execution_agent
from storage import (
    FINAL_KINDS,
    fetch_events,
    fetch_records,
    fetch_usage,
    get_run,
    list_runs,
    using_run,
)
from tools.landing_page import build_landing_page
from tools.orders_file import OrdersFileError, order_metrics
from tools.sample_data import generate_orders, to_file_bytes

load_dotenv()

# How often the SSE stream checks for new rows. The work between events takes
# seconds at minimum, so polling faster only burns database reads.
POLL_SECONDS = 0.75
# Sent while nothing is happening, to keep proxies from closing an idle stream.
HEARTBEAT_SECONDS = 15.0


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    jobs.shutdown()


app = FastAPI(
    title="Flywheel",
    description="An AI co-founder: validate a new idea, or plan an operating business's next period.",
    version="1.0.0",
    lifespan=lifespan,
)

# The Next.js front end is served from a different origin in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/meta/segments")
def segment_meta() -> dict:
    """What each customer group means.

    The rules live in `agents/_segments.py`; the UI shows them as tooltips
    rather than restating them, so the two cannot drift apart.
    """
    return {
        "order": list(SEGMENTS),
        "labels": SEGMENT_LABELS,
        "definitions": SEGMENT_DEFINITIONS,
    }


# ---------------------------------------------------------------- runs --


@app.get("/runs", response_model=list[RunSummary])
def get_runs(limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    return list_runs(limit=limit)


@app.post("/runs/new-idea", response_model=RunCreated, status_code=202)
def create_new_idea_run(payload: NewIdeaRequest) -> dict:
    """Start a launch plan. Returns immediately; follow /events for progress."""
    run_id = jobs.open_run(mode="new_idea")
    jobs.submit(
        run_id,
        lambda: flows.start_new_idea(
            run_id,
            pitch=payload.pitch,
            currency=payload.currency,
            starting_capital=payload.starting_capital,
            monthly_fixed_costs=payload.monthly_fixed_costs,
            unit_cost=payload.unit_cost,
            runway_months=payload.runway_months,
        ),
    )
    return {"run_id": run_id, "status": "running"}


@app.post("/runs/{run_id}/answers", response_model=RunCreated, status_code=202)
def answer_clarifying_questions(run_id: int, payload: AnswersRequest) -> dict:
    run = _require_run(run_id)
    if run["status"] != "awaiting_answers":
        raise HTTPException(
            status_code=409,
            detail=f"This run is {run['status']}, so it is not waiting for answers.",
        )
    jobs.submit(run_id, lambda: flows.resume_new_idea(run_id, payload.answers))
    return {"run_id": run_id, "status": "running"}


@app.post("/runs/existing-business", response_model=RunCreated, status_code=202)
def create_business_review_run(payload: ExistingBusinessRequest) -> dict:
    orders = None
    if payload.orders_token:
        try:
            orders = uploads.load(payload.orders_token)
        except uploads.UploadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OrdersFileError as exc:
            raise HTTPException(status_code=400, detail=f"Order file: {exc}") from exc

    metrics = PeriodMetrics(**payload.metrics.model_dump())
    run_id = jobs.open_run(mode="existing_business")
    jobs.submit(
        run_id,
        lambda: flows.start_business_review(
            run_id,
            description=payload.description,
            currency=payload.currency,
            metrics=metrics,
            budget=payload.budget,
            orders=orders,
            include_funding=payload.include_funding,
        ),
    )
    if payload.orders_token:
        uploads.discard(payload.orders_token)
    return {"run_id": run_id, "status": "running"}


@app.post("/runs/{run_id}/refine", response_model=RecordOut)
def refine_run(run_id: int, payload: RefineRequest) -> dict:
    """Redo one agent's output on the founder's own instruction.

    Synchronous, not a background job: unlike a full plan this is a single
    agent call (a few seconds on Groq, up to ~20s for CRM's local model), so
    there is nothing here worth a progress stream for. Defined as a plain
    `def`, which FastAPI runs in its threadpool -- the event loop stays free
    while the call is out to Groq or Ollama.

    Only a finished plan can be refined: refining mid-run would race the
    plan that is still being built, and a blocked or failed run has nothing
    yet to refine.
    """
    run = _require_run(run_id)
    if run["status"] != "done":
        raise HTTPException(
            status_code=409,
            detail=f"This run is {run['status']}, so there's no finished plan yet to refine.",
        )
    with using_run(run_id):
        try:
            refine_execution_agent(payload.cycle, payload.agent, payload.feedback)
        except RefineError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        records = fetch_records(cycle=payload.cycle, agent=payload.agent, run_id=run_id, as_json_text=False)
    if not records:  # pragma: no cover -- refine_execution_agent always logs one on success
        raise HTTPException(status_code=500, detail="The refined plan wasn't recorded.")
    return _record_out(records[-1])


@app.get("/meta/refinable-agents")
def refinable_agents() -> list[str]:
    """Which agents `/runs/{id}/refine` accepts -- the UI reads this rather
    than hardcoding the list a second time."""
    return list(REFINABLE_AGENTS)


@app.get("/runs/{run_id}", response_model=RunDetail)
def get_run_detail(run_id: int, after_seq: int = Query(default=0, ge=0)) -> dict:
    """Everything the UI needs to render a run, in one request."""
    run = _require_run(run_id)
    return {
        "run": run,
        "records": [_record_out(r) for r in fetch_records(run_id=run_id, as_json_text=False)],
        "events": fetch_events(run_id, after_seq=after_seq),
    }


@app.get("/runs/{run_id}/events", response_model=list[EventOut])
def get_run_events(run_id: int, after_seq: int = Query(default=0, ge=0)) -> list[dict]:
    """Plain polling, for clients that would rather not hold a stream open."""
    _require_run(run_id)
    return fetch_events(run_id, after_seq=after_seq)


@app.get("/runs/{run_id}/stream")
async def stream_run_events(run_id: int, request: Request, after_seq: int = Query(default=0, ge=0)) -> Response:
    """Server-sent events, resumable from `after_seq`.

    The client sends the last sequence number it saw, so a reload replays
    what it missed rather than restarting the run's progress from nothing.
    """
    _require_run(run_id)

    async def publish():
        seq = after_seq
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return

            events = await asyncio.to_thread(fetch_events, run_id, seq)
            for event in events:
                seq = event["seq"]
                idle = 0.0
                yield f"id: {seq}\nevent: {event['kind']}\ndata: {json.dumps(event)}\n\n"
                if event["kind"] in FINAL_KINDS:
                    return

            if not events:
                idle += POLL_SECONDS
                if idle >= HEARTBEAT_SECONDS:
                    idle = 0.0
                    yield ": keep-alive\n\n"
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(
        publish(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Without this, nginx buffers the stream and the founder sees
            # nothing until the whole run finishes.
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/runs/{run_id}/usage", response_model=UsageOut)
def get_run_usage(run_id: int, settle: bool = False) -> dict:
    """Tokens, calls and cache hits for this run.

    `settle=true` waits for litellm's background thread to finish reporting;
    only worth it right after a run ends.
    """
    run = _require_run(run_id)
    with using_run(run["id"]):
        if settle:
            return usage_summary()
    agents = fetch_usage(run_id=run_id)
    totals = {
        key: sum(a[key] for a in agents)
        for key in ("calls", "cache_hits", "prompt_tokens", "completion_tokens")
    }
    totals["seconds"] = round(sum(a["seconds"] for a in agents), 1)
    return {"agents": agents, "totals": totals}


@app.get("/runs/{run_id}/ad-image")
def get_ad_image(run_id: int) -> Response:
    """The generated ad image for this run's marketing plan.

    Marketing records an absolute path on the server (`data/ads/cycle_N.jpg`),
    which a browser obviously cannot open, so it is served here. The path is
    checked to be inside the ads directory before anything is read: it comes
    from a Decision Record, and a record is data, not a capability to read any
    file on disk.
    """
    _require_run(run_id)
    records = {r["agent"]: r["decision"] for r in fetch_records(run_id=run_id, as_json_text=False)}
    raw = (records.get("marketing") or {}).get("ad_image_path")
    if not raw:
        raise HTTPException(status_code=404, detail="This run has no ad image.")

    path = Path(str(raw)).resolve()
    ads_dir = (Path(__file__).resolve().parent.parent / "data" / "ads").resolve()
    if not path.is_relative_to(ads_dir) or not path.is_file():
        raise HTTPException(status_code=404, detail="The ad image is no longer on disk.")

    return Response(
        content=path.read_bytes(),
        media_type="image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/runs/{run_id}/landing-page", response_class=HTMLResponse)
def get_landing_page(run_id: int) -> Response:
    """The one-page launch site built from this run's plan."""
    _require_run(run_id)
    records = {r["agent"]: r["decision"] for r in fetch_records(run_id=run_id, as_json_text=False)}
    if "strategy" not in records:
        raise HTTPException(status_code=404, detail="This run has no plan to build a page from yet.")
    # Built on demand rather than written to disk. tools/landing_page.py
    # writes to one shared data/site/index.html, so two founders planning at
    # the same time would overwrite each other's page.
    html = build_landing_page(records.get("intake", {}), records["strategy"], records.get("marketing"))
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f'attachment; filename="launch-page-{run_id}.html"'},
    )


# -------------------------------------------------------------- orders --


@app.post("/orders/preview", response_model=OrdersPreview)
async def preview_orders(file: UploadFile) -> dict:
    """Parse an uploaded order history and report what was found.

    The founder sees the result before committing, including how many rows had
    to be skipped -- which is their signal that the wrong column was matched.
    """
    content = await file.read()
    try:
        token = uploads.save(content, file.filename or "")
        orders = uploads.load(token)
    except uploads.UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OrdersFileError as exc:
        raise HTTPException(status_code=400, detail=f"Order file: {exc}") from exc

    metrics = order_metrics(orders)
    return {
        "token": token,
        "rows": int(len(orders)),
        "skipped_rows": int(metrics.get("skipped_rows", 0)),
        "customers": int(orders["customer"].nunique()),
        "first_order": metrics.get("first_order"),
        "last_order": metrics.get("last_order"),
        "columns": [str(c) for c in orders.columns],
    }


@app.get("/orders/sample.{extension}")
def sample_orders(extension: str) -> Response:
    """A realistic order file, for a founder who wants to try the flow."""
    if extension not in {"csv", "xlsx"}:
        raise HTTPException(status_code=404, detail="Choose sample.csv or sample.xlsx.")
    media = {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }[extension]
    return Response(
        content=to_file_bytes(generate_orders(), extension),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="sample_orders.{extension}"'},
    )


# ------------------------------------------------------------- helpers --


def _require_run(run_id: int) -> dict:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No run with id {run_id}.")
    return run


def _record_out(record: dict) -> dict:
    return {
        "id": record["id"],
        "cycle": record["cycle"],
        "agent": record["agent"],
        "input_snapshot": record["input_snapshot"],
        "decision": record["decision"],
        "timestamp": record["timestamp"],
    }


__all__ = ["app"]
