"""Deploy the website to Vercel, pointed at a backend address.

    .venv/Scripts/python deploy/deploy_frontend.py https://<backend address>

The backend address is baked into the site when it is built (Next.js inlines
NEXT_PUBLIC_* values), so run this after the backend has an address, and again
if that address ever changes. Reads VERCEL_TOKEN from `.env.deploy`.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from deploy_backend import read_env  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("http"):
        print(__doc__)
        return 2
    backend = sys.argv[1].rstrip("/")
    token = read_env(ROOT / ".env.deploy").get("VERCEL_TOKEN")
    if not token:
        print("missing VERCEL_TOKEN in .env.deploy")
        return 1

    env = dict(os.environ, VERCEL_TOKEN=token)
    command = f"npx --yes vercel@latest deploy --prod --yes --build-env NEXT_PUBLIC_API_BASE={backend}"
    result = subprocess.run(command, shell=True, cwd=ROOT / "web", env=env, capture_output=True, text=True, timeout=1200)
    output = (result.stdout + result.stderr).replace(token, "<token>")
    print(output[-1500:])
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
