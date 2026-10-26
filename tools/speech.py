"""Voice in, voice out -- both over Groq, both on the account's existing key.

No second API key: Groq keys are account-scoped, not per-model, so the
GROQ_API_KEY already in .env for the planning agents covers these too, as
long as the account has been granted the models. Checked directly against
the live account before writing this module (`GET /openai/v1/models`):

    whisper-large-v3-turbo        -- present
    canopylabs/orpheus-v1-english -- present
    playai-tts                    -- NOT present

Groq appears to have replaced playai-tts with the Orpheus models on this
account at some point after the public blog posts describing it were
written, so `synthesize()` targets Orpheus, not playai-tts.

Groq's REST docs quote a bare User-Agent as getting through; it does not, in
practice, from this network -- the raw request came back `403` with
Cloudflare error 1010 ("banned based on your browser's signature") until a
normal browser-style header was added. Kept here rather than relying on
httpx's default, which triggers the same block.

Orpheus' free-tier rate limit is reported at 10 requests/minute, 100/day --
thin for sustained use, generous for building and demoing this project. No
guardrail against it here beyond the shared retry/backoff in `agents._retry`:
a 429 waits and retries like any other Groq call, and `synthesize()` raising
is the caller's (the API layer's) signal to fall back to the browser's own
voice instead of failing the read-aloud outright.
"""

import os

import httpx

from agents._retry import retry_on_rate_limit

GROQ_BASE = "https://api.groq.com/openai/v1"
STT_MODEL = "whisper-large-v3-turbo"
TTS_MODEL = "canopylabs/orpheus-v1-english"
# One of Orpheus' six English voices -- picked for a plain, mid register
# that reads a business plan rather than performs it.
TTS_VOICE = "tara"

# Keeps a single call's cost and latency bounded. A full plan section rarely
# exceeds this; the caller truncates and the founder can still read the rest
# on screen -- speech here is a convenience, not the only copy of the text.
MAX_SYNTHESIZE_CHARS = 2000

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_HEADERS_BASE = {
    # See the module docstring: without a browser-shaped UA, Groq's edge
    # (Cloudflare) returns a 403 before the request reaches the API at all,
    # which otherwise reads exactly like an auth failure and is not one.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


class SpeechError(Exception):
    """Either side of the round trip failed. The message is already
    founder-safe -- callers show it, or fall back, without re-wrapping it."""


def _api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise SpeechError("Speech features need GROQ_API_KEY set in .env.")
    return key


@retry_on_rate_limit()
def transcribe(audio_bytes: bytes, filename: str) -> str:
    """Speech to text. Returns the transcript, or raises SpeechError.

    `filename`'s extension is what tells Groq the container format (webm,
    wav, m4a, ...) -- it is passed through from the browser's recording,
    never inferred from content, since MediaRecorder's own `mimeType` is the
    one source of truth for what it actually wrote.
    """
    if not audio_bytes:
        raise SpeechError("No audio was recorded.")

    try:
        response = httpx.post(
            f"{GROQ_BASE}/audio/transcriptions",
            headers={**_HEADERS_BASE, "Authorization": f"Bearer {_api_key()}"},
            data={"model": STT_MODEL, "response_format": "json"},
            files={"file": (filename or "audio.webm", audio_bytes, "application/octet-stream")},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # Re-raised as the plain exception types `_retry.py` already knows
        # how to read (it walks `str(exc)` for "429", "rate_limit", etc.) --
        # no separate marker vocabulary to keep in sync with that module.
        raise RuntimeError(f"Groq transcription failed: {exc}") from exc
    except httpx.HTTPError as exc:
        raise SpeechError(f"Could not reach the transcription service: {exc}") from exc

    text = (response.json().get("text") or "").strip()
    if not text:
        raise SpeechError("Didn't catch that -- try again, a bit closer to the mic.")
    return text


@retry_on_rate_limit()
def synthesize(text: str) -> bytes:
    """Text to speech. Returns WAV bytes, or raises SpeechError.

    Deliberately returns bytes rather than writing to disk: unlike the ad
    images (one per run, worth keeping), a read-aloud clip is used once and
    thrown away, and persisting it would be a cache with no eviction policy
    for no benefit anyone asked for.
    """
    clipped = text.strip()
    if not clipped:
        raise SpeechError("Nothing here to read aloud.")
    if len(clipped) > MAX_SYNTHESIZE_CHARS:
        clipped = clipped[:MAX_SYNTHESIZE_CHARS].rsplit(" ", 1)[0] + "…"

    try:
        response = httpx.post(
            f"{GROQ_BASE}/audio/speech",
            headers={**_HEADERS_BASE, "Authorization": f"Bearer {_api_key()}"},
            json={
                "model": TTS_MODEL,
                "voice": TTS_VOICE,
                "input": clipped,
                "response_format": "wav",
            },
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Groq speech synthesis failed: {exc}") from exc
    except httpx.HTTPError as exc:
        raise SpeechError(f"Could not reach the speech service: {exc}") from exc

    audio = response.content
    if not audio:
        raise SpeechError("The speech service returned nothing.")
    return audio
