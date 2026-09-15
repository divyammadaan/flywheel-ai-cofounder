"""Reuse a model's answer when an agent gets exactly the same inputs again.

Same inputs to the same agent code and model give an answer we already paid
for, so it is read from disk instead of spending another call. This matters
most for repeated runs of the same business (demos, iterating on the
dashboard) -- a fully repeated run costs zero model calls.

The key covers everything that could change the answer:
  - the agent's name and model,
  - a hash of the agent's own source file, so editing an agent's prompt or
    schema invalidates only that agent's saved answers,
  - every input argument,
  - anything else the prompt depends on (e.g. today's date for Funding).

Answers live in data/llm_cache/ on this machine only (gitignored) -- CRM
answers include real customer names. Turn caching off with
FLYWHEEL_LLM_CACHE=0.
"""

import dataclasses
import functools
import hashlib
import inspect
import json
import os
from pathlib import Path

from observability.usage import record_usage

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "llm_cache"


def _enabled() -> bool:
    return os.getenv("FLYWHEEL_LLM_CACHE", "1") != "0"


def _jsonable(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"__type__": type(value).__name__, **{k: _jsonable(v) for k, v in dataclasses.asdict(value).items()}}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _source_file(method) -> str:
    """The file that defines the agent method itself, looking through
    decorators such as retry_on_rate_limit whose wrapper lives in
    agents/_retry.py. Without unwrapping, every agent hashed _retry.py, so
    editing an agent's prompt didn't invalidate its saved answers -- caught in
    a live run, where Funding replayed an answer written before its prompt
    changed."""
    return inspect.getfile(inspect.unwrap(method))


def cached(agent_name: str, result_type: type, extra_key=None, should_cache=None):
    """Decorate an agent method whose return value is a dataclass of plain data.

    `extra_key` is an optional zero-argument callable for inputs that aren't
    arguments, such as the current date. `should_cache` optionally decides
    whether a result is worth keeping -- a failed answer shouldn't be replayed
    on the next run.
    """

    def decorator(method):
        source_hash = hashlib.sha256(Path(_source_file(method)).read_bytes()).hexdigest()[:16]

        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            if not _enabled():
                return method(self, *args, **kwargs)

            model = getattr(self, "model_name", None)
            payload = {
                "agent": agent_name,
                "model": model,
                "source": source_hash,
                "args": _jsonable(args),
                "kwargs": _jsonable(kwargs),
                "extra": extra_key() if extra_key else None,
            }
            key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            path = CACHE_DIR / f"{agent_name}-{key[:32]}.json"

            if path.exists():
                record_usage(agent_name, model, 0, 0, 0.0, calls=0, cached=True)
                return result_type(**json.loads(path.read_text(encoding="utf-8")))

            result = method(self, *args, **kwargs)
            if should_cache is not None and not should_cache(result):
                return result
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            # Write-then-rename, so a crash mid-write can't leave a half file
            # that later reads as a valid cached answer.
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(dataclasses.asdict(result), default=str), encoding="utf-8")
            tmp.replace(path)
            return result

        return wrapper

    return decorator
