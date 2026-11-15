"""Access control for a public deployment.

Locally nothing here does anything. On a hosted deployment the app is reachable
by anyone with the URL, and every plan spends the owner's free-tier model
quota, so two protections are switched on by environment variables:

  FLYWHEEL_ACCESS_CODE        a shared code. Every request must carry it, as the
                              `X-Access-Code` header or an `access_code` query
                              parameter (a browser's EventSource and <img> cannot
                              set headers). /health and the API docs stay open.
  FLYWHEEL_RUNS_PER_HOUR      how many plans one client address may start an
                              hour (default 30). Writes that call a model
                              (speech, refining) are limited together at four
                              times that.

Written as a plain ASGI middleware rather than a BaseHTTPMiddleware: the plan
progress stream is a long-lived response, which that wrapper handles badly.
"""

import hmac
import json
import os
import threading
import time
from collections import defaultdict, deque
from urllib.parse import parse_qs

OPEN_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}
# POSTs that start a plan; the rest of the model-calling writes are limited together.
RUN_START_PATHS = {"/runs/new-idea", "/runs/existing-business"}
MODEL_WRITE_PREFIXES = ("/runs/", "/speech/")
WINDOW_SECONDS = 3600


def access_code() -> str:
    return os.environ.get("FLYWHEEL_ACCESS_CODE", "").strip()


def runs_per_hour() -> int:
    try:
        return max(1, int(os.environ.get("FLYWHEEL_RUNS_PER_HOUR", "30")))
    except ValueError:
        return 30


class RateLimiter:
    """A sliding window per (client, bucket), held in memory.

    Per process, which is fine: one server process is the supported deployment.
    """

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str, bucket: str, limit: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[(client, bucket)]
            while hits and now - hits[0] > WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


limiter = RateLimiter()


def _client(scope) -> str:
    # Behind the host's proxy the socket address is the proxy's; the original
    # client is the first entry of X-Forwarded-For.
    headers = dict(scope.get("headers") or [])
    forwarded = headers.get(b"x-forwarded-for", b"").decode().split(",")[0].strip()
    if forwarded:
        return forwarded
    client = scope.get("client")
    return client[0] if client else "unknown"


def _supplied_code(scope) -> str:
    headers = dict(scope.get("headers") or [])
    code = headers.get(b"x-access-code", b"").decode().strip()
    if code:
        return code
    query = parse_qs((scope.get("query_string") or b"").decode())
    return (query.get("access_code") or [""])[0].strip()


async def _reject(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


class AccessGate:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        method, path = scope["method"], scope["path"]
        # Preflight requests carry no credentials by design; CORS answers them.
        if method == "OPTIONS":
            return await self.app(scope, receive, send)

        code = access_code()
        if code and path not in OPEN_PATHS:
            if not hmac.compare_digest(_supplied_code(scope).encode(), code.encode()):
                return await _reject(send, 401, "An access code is required.")

        if method == "POST" and path not in OPEN_PATHS:
            limit = runs_per_hour()
            if path in RUN_START_PATHS:
                allowed = limiter.allow(_client(scope), "plans", limit)
            elif path.startswith(MODEL_WRITE_PREFIXES):
                allowed = limiter.allow(_client(scope), "model-writes", limit * 4)
            else:
                allowed = True
            if not allowed:
                return await _reject(send, 429, "Too many requests from your address. Please try again later.")

        return await self.app(scope, receive, send)


def cors_origins() -> list[str]:
    configured = os.environ.get("FLYWHEEL_CORS_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in configured.split(",") if o.strip()]
    return origins or ["http://localhost:3000", "http://127.0.0.1:3000"]


def cors_origin_regex() -> str | None:
    return os.environ.get("FLYWHEEL_CORS_ORIGIN_REGEX") or None
