"""Running a plan in the background, and reporting its progress.

A plan takes minutes of blocking work: web search, a dozen model calls, and a
parallel fan-out across four agents. That cannot happen inside a request, so
each plan runs on a worker thread and the request returns a run id straight
away. The client then follows `GET /runs/{id}/events`.

**Why threads and a database table, not Redis and a task queue.** Every step
already writes a row -- a Decision Record, and now a RunEvent -- so progress
and results are durable without a broker. A client that reloads re-reads the
rows; a worker that dies leaves a run whose status says so. Redis would add a
service to run without changing what the founder can recover. The seam is
`submit()`: moving this onto arq or Celery later means reimplementing that one
function, not the flows below.

**What is NOT handled here:** a process that exits mid-run leaves its run
marked `running` for ever, because nothing else is watching it. That is
acceptable while a single process serves a single machine, and is the first
thing to fix when this is deployed behind more than one worker.
"""

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Callable

from orchestration.cycle import PlanBlocked
from storage import add_event, fetch_events, start_run, update_run, using_run

# Bounded on purpose. Each job holds a Groq rate limit and, for CRM, the local
# Ollama model; running many at once makes every one of them slower rather
# than finishing any sooner.
MAX_CONCURRENT_RUNS = 4

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=MAX_CONCURRENT_RUNS, thread_name_prefix="flywheel-run"
            )
        return _executor


def shutdown(wait: bool = False) -> None:
    """Stop the pool. Called on API shutdown and between tests."""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=wait, cancel_futures=not wait)
        _executor = None


# What the founder is told when a provider fails, keyed by a marker in the
# exception text. The full exception and traceback always go to the event row;
# only this reaches the screen.
_FRIENDLY = (
    (
        ("rate limit", "ratelimit", "429"),
        "The model provider is rate-limiting this account. Waiting a minute and running "
        "it again usually clears it.",
    ),
    (
        ("tool_use_failed", "did not match schema", "validation failed"),
        "The model returned a malformed plan and the retry didn't fix it. This is a "
        "provider hiccup rather than a problem with your inputs — running it again "
        "usually works.",
    ),
    (
        ("connection", "timed out", "timeout", "getaddrinfo"),
        "Couldn't reach the model provider. Check the connection and try again.",
    ),
    (
        ("authentication", "api key", "401", "invalid_api_key"),
        "The model provider rejected the API key. Check GROQ_API_KEY in your .env.",
    ),
)


def founder_message(exc: Exception, agent: str | None = None) -> str:
    """A failure in words a founder can act on.

    `str(exc)` on a provider error is a wall of escaped JSON -- in one real run
    it was the model's entire malformed generation, which then rendered as a
    page-wide blob of raw text. That belongs in the event payload, not on the
    founder's screen.
    """
    text = str(exc).lower()
    where = f" while working on {agent.replace('_', ' ')}" if agent else ""
    for markers, message in _FRIENDLY:
        if any(marker in text for marker in markers):
            return f"{message}{(' (it stopped' + where + '.)') if where else ''}"
    return f"Something went wrong{where}: {type(exc).__name__}."


def _current_agent(run_id: int) -> str | None:
    """The agent that was in flight, for the message above."""
    started = None
    for event in fetch_events(run_id):
        if event["kind"] == "agent_started":
            started = event["agent"]
        elif event["kind"] == "agent_finished":
            started = None
    return started


def open_run(mode: str, label: str | None = None) -> int:
    run_id = start_run(mode=mode, label=label)
    add_event("started", message="Run started", run_id=run_id)
    return run_id


def submit(run_id: int, work: Callable[[], None]) -> None:
    """Run `work` on a worker thread, with the run's status kept honest.

    The worker re-binds the current run (`using_run`) because the run is held
    in a ContextVar: a pool thread does not inherit the request's.
    """

    def task() -> None:
        # Invariant, relied on by every client and by the tests: the terminal
        # EVENT is always written before the run's STATUS becomes terminal.
        # The other order is a race -- a client that polls status, sees
        # "failed" and fetches the events can arrive before the event exists.
        with using_run(run_id):
            try:
                work()
            except PlanBlocked as blocked:
                # Not a crash: a blocked plan is a correct answer the founder
                # needs to see, e.g. the reserve uses all of the capital.
                add_event("blocked", message=str(blocked), run_id=run_id)
                update_run(run_id, status="blocked", error=str(blocked))
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                readable = founder_message(exc, _current_agent(run_id))
                add_event(
                    "failed",
                    message=readable,
                    # The raw exception and traceback stay here, where a
                    # developer can find them and a founder never sees them.
                    payload={
                        "traceback": traceback.format_exc(),
                        "exception": f"{type(exc).__name__}: {exc}",
                    },
                    run_id=run_id,
                )
                update_run(run_id, status="failed", error=readable)

    executor().submit(task)


class Progress:
    """Emits an event on either side of each agent, for the run it is bound to.

    Used as a context manager so a failure inside the block still leaves the
    trail showing which agent was in flight when it happened.
    """

    def __init__(self, run_id: int):
        self.run_id = run_id

    def step(self, agent: str, message: str) -> "_Step":
        return _Step(self.run_id, agent, message)

    def event(self, kind: str, message: str | None = None, payload: dict | None = None) -> None:
        add_event(kind, message=message, payload=payload, run_id=self.run_id)


class _Step:
    def __init__(self, run_id: int, agent: str, message: str):
        self.run_id = run_id
        self.agent = agent
        self.message = message

    def __enter__(self) -> "_Step":
        add_event("agent_started", agent=self.agent, message=self.message, run_id=self.run_id)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            add_event("agent_finished", agent=self.agent, run_id=self.run_id)
        return False


def as_payload(value) -> dict:
    """A dataclass or dict as something the JSON column can hold."""
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return dict(value or {})
