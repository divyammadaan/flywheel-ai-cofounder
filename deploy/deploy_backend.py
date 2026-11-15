"""Deploy the Flywheel backend to a Hugging Face Space (Docker).

    .venv/Scripts/python deploy/deploy_backend.py [--no-wait]

Reads its settings from `.env.deploy` and the model key from `.env`; nothing
secret is ever printed or written to the uploaded files. It

  1. stages only what the container needs (code, migrations, Dockerfile),
  2. creates the Space if it does not exist,
  3. sets the Space's secrets and variables,
  4. uploads the staged files, which makes the Space build and start, and
  5. waits until it reports RUNNING (or fails, and prints the build log tail).

Run it again after any code change: it is idempotent.
"""

import argparse
import os
import secrets
import shutil
import sys
import tempfile
import time
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
SPACE_NAME = "flywheel-backend"
CODE_DIRS = ["agents", "api", "orchestration", "observability", "storage", "tools", "migrations"]
CODE_FILES = ["alembic.ini", "requirements.deploy.txt", "Dockerfile"]

README = """---
title: Flywheel Backend
emoji: 🔁
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Flywheel backend

FastAPI service for Flywheel, an AI co-founder built with CrewAI and Google ADK.
It serves the website's API; the website is deployed separately.
Interactive API docs are at `/docs`.
"""


def read_env(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def ensure_access_code(env_deploy: Path, current: dict) -> str:
    """The shared access code: kept in .env.deploy so every deploy reuses it."""
    if current.get("ACCESS_CODE"):
        return current["ACCESS_CODE"]
    code = secrets.token_urlsafe(9)
    with env_deploy.open("a", encoding="utf-8") as f:
        f.write(f"\n# Shared access code for the deployed demo (generated).\nACCESS_CODE={code}\n")
    return code


def stage(target: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.db", "*.db-wal", "*.db-shm")
    for name in CODE_DIRS:
        shutil.copytree(ROOT / name, target / name, ignore=ignore)
    for name in CODE_FILES:
        shutil.copy2(ROOT / name, target / name)
    (target / "deploy").mkdir()
    shutil.copy2(ROOT / "deploy" / "start.sh", target / "deploy" / "start.sh")
    (target / "README.md").write_text(README, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-wait", action="store_true", help="upload and return without waiting for the build")
    args = parser.parse_args()

    env_deploy = ROOT / ".env.deploy"
    deploy = read_env(env_deploy)
    model = read_env(ROOT / ".env")
    for needed in ("HF_USERNAME", "HF_TOKEN", "NEON_DATABASE_URL"):
        if not deploy.get(needed):
            print(f"missing {needed} in .env.deploy")
            return 1
    if not model.get("GROQ_API_KEY"):
        print("missing GROQ_API_KEY in .env")
        return 1

    token = deploy["HF_TOKEN"]
    api = HfApi(token=token)
    # The account name comes from the token itself: a typo (or a project name)
    # in .env.deploy would otherwise try to create the Space in someone else's namespace.
    user = api.whoami()["name"]
    if user != deploy["HF_USERNAME"]:
        print(f"note: HF_USERNAME says {deploy['HF_USERNAME']!r} but the token belongs to {user!r}; using {user!r}")
    repo_id = f"{user}/{SPACE_NAME}"

    code = ensure_access_code(env_deploy, deploy)
    deploy = read_env(env_deploy)

    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=False, exist_ok=True)

    secrets_to_set = {
        "GROQ_API_KEY": model["GROQ_API_KEY"],
        "FLYWHEEL_DATABASE_URL": deploy["NEON_DATABASE_URL"],
        "FLYWHEEL_ACCESS_CODE": code,
    }
    for optional in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        if deploy.get(optional):
            secrets_to_set[optional] = deploy[optional]
    for key, value in secrets_to_set.items():
        api.add_space_secret(repo_id, key, value)

    host = {"EU": "https://cloud.langfuse.com", "US": "https://us.cloud.langfuse.com"}.get(
        (deploy.get("LANGFUSE_REGION") or "").upper()
    )
    variables = {"FLYWHEEL_LLM_CACHE": "0"}
    if deploy.get("FLYWHEEL_CORS_ORIGINS"):
        variables["FLYWHEEL_CORS_ORIGINS"] = deploy["FLYWHEEL_CORS_ORIGINS"]
    if deploy.get("FLYWHEEL_CORS_ORIGIN_REGEX"):
        variables["FLYWHEEL_CORS_ORIGIN_REGEX"] = deploy["FLYWHEEL_CORS_ORIGIN_REGEX"]
    if host:
        variables["LANGFUSE_HOST"] = host
    for key, value in variables.items():
        api.add_space_variable(repo_id, key, value)

    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "space"
        staged.mkdir()
        stage(staged)
        api.upload_folder(
            folder_path=str(staged),
            repo_id=repo_id,
            repo_type="space",
            commit_message="Deploy backend",
            delete_patterns="*",
        )

    url = f"https://{user.lower().replace('_', '-')}-{SPACE_NAME}.hf.space"
    print(f"uploaded; space: https://huggingface.co/spaces/{repo_id}\nbackend url: {url}")
    if args.no_wait:
        return 0

    deadline = time.time() + 40 * 60
    last = None
    while time.time() < deadline:
        runtime = api.get_space_runtime(repo_id)
        stage_name = str(runtime.stage)
        if stage_name != last:
            print(time.strftime("%H:%M:%S"), "space stage:", stage_name)
            last = stage_name
        if stage_name == "RUNNING":
            print("space is running")
            return 0
        if stage_name in {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"}:
            print("space failed:", stage_name)
            return 2
        time.sleep(20)
    print("timed out waiting for the space")
    return 3


if __name__ == "__main__":
    sys.exit(main())
