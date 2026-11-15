#!/bin/sh
# Container entry point: bring the database schema up to date, then serve.
# Settings come from the environment (a host's secrets): FLYWHEEL_DATABASE_URL,
# GROQ_API_KEY, FLYWHEEL_ACCESS_CODE, FLYWHEEL_CORS_ORIGINS, LANGFUSE_*.

PORT="${PORT:-7860}"
export PORT
# The API serves the CrewAI agents over A2A on itself; the plan's ADK coordinator
# reaches them here. A host that sets this explicitly wins.
export FLYWHEEL_A2A_URL="${FLYWHEEL_A2A_URL:-http://127.0.0.1:${PORT}/a2a}"

# Migrations are run on every start; they are no-ops once applied. If they fail
# the app still starts and creates its tables itself on first use.
python -m alembic upgrade head || echo "alembic upgrade failed; the app will create tables on first use"

exec python -m uvicorn api.main:app --host 0.0.0.0 --port "${PORT}" --proxy-headers --forwarded-allow-ips="*"
