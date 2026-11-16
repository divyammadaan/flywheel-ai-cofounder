"""Deploy the Flywheel backend to Modal (modal.com), which has a free monthly credit.

    python -m pip install modal          # your normal Python, not the project's .venv
    python -m modal token new            # one time: log in through the browser
    python -m modal deploy deploy/modal_app.py

Why Modal: the backend needs about 0.5 GB while planning (CrewAI + ADK + LiteLLM
are heavy) and the free hosts that need no card give 512 MB or less. Modal lets
us choose the memory (1.5 GB here) and bills against a free monthly credit.

How it runs: one container, one process -- the same `deploy/start.sh` the Docker
image uses (migrations, then uvicorn on port 8000). The container scales to zero
when idle and takes a short while to start on the first request, so open the site
a few minutes before a demo. `max_containers=1` matters: plans run as background
threads and uploads are held in memory, so every request must reach the same
process.

Settings are read when you deploy, from `.env` (GROQ_API_KEY) and `.env.deploy`
(everything else), and stored as a Modal secret -- never in this file or in git.
`.env.deploy` holds the website's address as FLYWHEEL_CORS_ORIGINS, next to the keys.
"""

import os
import subprocess
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
CODE_DIRS = ["agents", "api", "orchestration", "observability", "storage", "tools", "migrations"]
CODE_FILES = ["alembic.ini"]
PORT = 8000


def _read_env(path: Path) -> dict:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _secret() -> modal.Secret:
    # This file is imported twice: on your machine when deploying, and again inside the
    # container, where .env and .env.deploy do not exist. Modal requires the same objects
    # to be defined in both places, so the container gets a placeholder secret (the real
    # one is already attached to it, as environment variables).
    if not modal.is_local():
        return modal.Secret.from_dict({"PLACEHOLDER": "unused"})
    model = _read_env(ROOT / ".env")
    deploy = _read_env(ROOT / ".env.deploy")
    region = (deploy.get("LANGFUSE_REGION") or "").upper()
    values = {
        "GROQ_API_KEY": model.get("GROQ_API_KEY", ""),
        "FLYWHEEL_DATABASE_URL": deploy.get("NEON_DATABASE_URL", ""),
        # No access code: the demo is open, so examiners can use it without one. Left empty,
        # the gate in api/security.py stays off and the website never shows its code form.
        # The per-address rate limit (FLYWHEEL_RUNS_PER_HOUR) still applies. To lock the
        # demo again, put ACCESS_CODE in .env.deploy and use deploy.get("ACCESS_CODE", "").
        "FLYWHEEL_ACCESS_CODE": "",
        "FLYWHEEL_CORS_ORIGINS": deploy.get("FLYWHEEL_CORS_ORIGINS", ""),
        "LANGFUSE_PUBLIC_KEY": deploy.get("LANGFUSE_PUBLIC_KEY", ""),
        "LANGFUSE_SECRET_KEY": deploy.get("LANGFUSE_SECRET_KEY", ""),
        "LANGFUSE_HOST": {"EU": "https://cloud.langfuse.com", "US": "https://us.cloud.langfuse.com"}.get(region, ""),
        # The API serves the A2A agents on itself; the plan's ADK coordinator calls them here.
        "PORT": str(PORT),
        "FLYWHEEL_A2A_URL": f"http://127.0.0.1:{PORT}/a2a",
        "FLYWHEEL_LLM_CACHE": "0",
        # Run numbers restart in every database, so a local test and the deployment both have a "run-3";
        # this keeps their traces apart in Langfuse (filter by environment).
        "LANGFUSE_TRACING_ENVIRONMENT": "production",
    }
    missing = [k for k in ("GROQ_API_KEY", "FLYWHEEL_DATABASE_URL") if not values[k]]
    if missing:
        raise SystemExit(f"missing in .env / .env.deploy: {', '.join(missing)}")
    return modal.Secret.from_dict({k: v for k, v in values.items() if v})


image = modal.Image.debian_slim(python_version="3.12").pip_install_from_requirements(
    str(ROOT / "requirements.deploy.txt"),
    # A complete freeze of the tested environment, installed exactly (see the Dockerfile).
    extra_options="--no-deps",
)
for _name in CODE_DIRS:
    image = image.add_local_dir(ROOT / _name, f"/root/app/{_name}", ignore=["__pycache__", "*.pyc", "*.db", "*.db-wal", "*.db-shm"])
for _name in CODE_FILES:
    image = image.add_local_file(ROOT / _name, f"/root/app/{_name}")
image = image.add_local_file(ROOT / "deploy" / "start.sh", "/root/app/deploy/start.sh")

app = modal.App("flywheel-backend", image=image)


@app.function(
    secrets=[_secret()],
    # Sized to stretch Modal's $1 of credit (no payment method): about $0.036 an hour while
    # running (0.5 core at $0.0000131/s + 1.5 GiB at $0.00000222/s per GiB), nothing when
    # scaled to zero. The backend peaks near 0.5 GiB; the rest is headroom for the MCP process.
    memory=1536,
    cpu=0.5,
    timeout=60 * 60,
    min_containers=0,
    max_containers=1,
    scaledown_window=10 * 60,  # long enough for a plan to finish after the browser tab closes
)
@modal.concurrent(max_inputs=100)
@modal.web_server(port=PORT, startup_timeout=240)
def serve() -> None:
    # Runs the same entry point as the Docker image: alembic, then uvicorn.
    subprocess.Popen("cd /root/app && sh deploy/start.sh", shell=True, env={**os.environ, "PORT": str(PORT)})
