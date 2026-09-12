"""Ad image generation for the Marketing agent.

Uses Pollinations (keyless, free) rather than a hosted provider because the
obvious options don't work on a free tier:

  Gemini image models  quota is literally 0 on the free tier -- not
                       "exhausted", zero. Requires billing, so it would
                       block anyone cloning this repo.
  NVIDIA NIM           its catalogue has no image generation model reachable
                       from the chat-completions endpoint.
  Local diffusion      far too slow on a CPU-only machine.

Failure here is deliberately non-fatal. The ad copy is Marketing's actual
output; the image is supplementary, so a flaky image service must not take
down a whole business cycle. Callers get None and carry on.
"""

import urllib.parse
from pathlib import Path

import httpx

AD_DIR = Path(__file__).resolve().parent.parent / "data" / "ads"
ENDPOINT = "https://image.pollinations.ai/prompt/"
WIDTH, HEIGHT = 1024, 576  # landscape, roughly ad-banner shaped
TIMEOUT = 90.0


def generate_ad_image(prompt: str, cycle: int, out_dir: Path | None = None) -> str | None:
    """Generate an ad image and return its path, or None if generation failed.

    Returns a path rather than bytes so the image survives the run and can be
    shown in the dashboard afterwards.
    """
    target_dir = out_dir or AD_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"cycle_{cycle}.jpg"

    url = f"{ENDPOINT}{urllib.parse.quote(prompt)}?width={WIDTH}&height={HEIGHT}&nologo=true"
    try:
        response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        if "image" not in response.headers.get("content-type", ""):
            # The service answers 200 with an HTML error page under load, so
            # status alone isn't enough to trust the body.
            return None
        path.write_bytes(response.content)
        return str(path)
    except Exception:
        return None
