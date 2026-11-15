# Deployment

## What runs where

| Part | Where | Notes |
|---|---|---|
| Website (Next.js) | Vercel | Static + server-rendered pages; calls the backend from the browser |
| Backend: API, the A2A agents, the agent logic | One Docker container | `Dockerfile` → `deploy/start.sh` (migrations, then uvicorn). The MCP server runs as a child process of it |
| Database | Neon (managed Postgres) | `FLYWHEEL_DATABASE_URL`; the code accepts the plain `postgresql://` address Neon gives |
| Model | Groq | `GROQ_API_KEY` |
| Tracing | Langfuse Cloud | `LANGFUSE_*`; off if the keys are absent |

Nothing runs from a laptop. The backend must be **one instance**: plans run as background
threads, uploads are held in memory, and the rate limiter is per process.

## Settings (environment variables on the backend host)

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | model provider |
| `FLYWHEEL_DATABASE_URL` | Neon connection string |
| `FLYWHEEL_ACCESS_CODE` | the shared code the website asks for. Without it the API is open |
| `FLYWHEEL_CORS_ORIGINS` | the website's address, e.g. `https://flywheel-ai-cofounder.vercel.app` |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | tracing |
| `FLYWHEEL_A2A_URL` | `http://127.0.0.1:<port>/a2a` — where the API's own A2A agents are reached |
| `PORT` | the port the container serves (8000 on Modal, 7860 on Hugging Face) |
| `FLYWHEEL_LLM_CACHE=0` | do not keep model answers on disk (they include customer data) |

## The free-hosting problem (read this first)

The plan was Hugging Face Spaces. It now refuses: *"hosting Gradio and Docker Spaces on
free cpu-basic requires a PRO subscription."* The backend needs about 300 MB idle and 480 MB
at peak (measured), which rules out the 512 MB free tiers in practice, and Koyeb, Fly.io and
Google Cloud Run need a card. What is left:

| Option | Memory | Card | Verdict |
|---|---|---|---|
| **Modal** | you choose (1.5 GB here) | not required to start, but **without one only $1 of the $30 monthly credit is unlocked** | **Recommended.** At the settings in `deploy/modal_app.py` the container costs about $0.036 an hour while running and nothing when idle, so $1 is roughly 25 hours of running time: ample for rehearsals and a demo. Cold start of up to a minute after idle |
| Render free web service | 512 MB | not stated on its docs | Risky: peak memory is about 480 MB |
| Hugging Face Space | 16 GB | — | Works, but needs PRO ($9 a month) |
| Azure for Students | generous | no (a university e-mail) | Good fallback; needs signing up |

## Backend on Modal

Use your normal Python for this (not the project's `.venv`, so Modal's packages cannot disturb the pinned ones):

```
python -m pip install modal
python -m modal token new              # logs in through the browser
```

`.env.deploy` already holds the website's address (`FLYWHEEL_CORS_ORIGINS`), so from the project folder:

```
python -m modal deploy deploy/modal_app.py
```

Modal prints the backend's address (`https://<workspace>--flywheel-backend-serve.modal.run`).
`deploy/modal_app.py` reads the keys from `.env` and `.env.deploy` and stores them as a Modal
secret; they are not written to the repository.

Check it: `https://<that address>/health` answers `{"status": "ok"}`, and
`https://<that address>/docs` lists the API.

## Backend on Hugging Face (needs PRO)

`.venv/Scripts/python deploy/deploy_backend.py` creates the Space, sets its secrets and uploads
the code. The Space's address is printed. (It uses the account name from the token, not
`HF_USERNAME`.)

## Backend on any Docker host

`docker build -t flywheel-backend .` then run it with the environment variables above and the
port exposed. `render.yaml` is a ready blueprint for Render.

## The website on Vercel

The address of the backend is baked in when the site is built, so deploy it after the backend
has an address:

```
cd web
.venv/Scripts/python deploy/deploy_frontend.py https://<backend address>
```

(it reads `VERCEL_TOKEN` from `.env.deploy`). The site asks for the access code on
first use and remembers it in the browser.

## Checking a deployment

1. `<backend>/health` is ok.
2. Open the website, enter the access code, start the demo plan (`demo/DEMO_GUIDE.md`).
3. The plan completes; "Plan (Markdown)" downloads.
4. Langfuse shows the run under *Sessions* as `run-<id>`.
5. `python evaluation/run_eval.py --base-url <backend> --access-code <code>` for the numbers.

## Demo-day checklist

- Open the site and the backend `/health` five minutes early (hosts that scale to zero need a minute to wake).
- Keep the access code and the Langfuse tab ready.
- **Mind Groq's daily allowance.** The free tier gives 200,000 tokens a day for this model, about seven full plans (each is roughly 27,000 tokens). Rehearsals count: do not spend the allowance the day before. If it runs out, plans fail with a rate-limit message until it resets.
- Run one plan at a time: Groq's free tier allows about 1,000 output tokens a minute for this model, so a plan takes two to four minutes and two plans at once both slow down.
