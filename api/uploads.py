"""Holding an uploaded order file between the preview and the plan.

The founder uploads, sees what was parsed, then submits the form. Those are
two requests, so the file has to live somewhere in between.

It is kept as the **original bytes on disk**, keyed by an unguessable token,
and re-parsed when the plan starts. Two reasons: the parse is deterministic,
so nothing is gained by caching the DataFrame; and an order history is a list
of real customers and what they spent, which should not sit in process memory
for as long as the server happens to live.

Files are deleted once used, and anything older than `MAX_AGE_SECONDS` is
swept on the next upload -- an abandoned form must not leave a customer list
on disk indefinitely.
"""

import io
import secrets
import time
from pathlib import Path

import pandas as pd

from tools.orders_file import OrdersFileError, load_orders

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
MAX_AGE_SECONDS = 6 * 60 * 60
MAX_BYTES = 25 * 1024 * 1024
ALLOWED_SUFFIXES = {".csv", ".xlsx"}


class UploadError(ValueError):
    """Something the founder can fix, phrased for them."""


def save(content: bytes, filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadError("Upload a .csv or .xlsx file.")
    if len(content) > MAX_BYTES:
        raise UploadError(f"That file is larger than {MAX_BYTES // (1024 * 1024)}MB.")

    _sweep()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    (UPLOAD_DIR / f"{token}{suffix}").write_bytes(content)
    return token


def load(token: str) -> pd.DataFrame:
    """Re-parse a held upload. Raises OrdersFileError on a bad file."""
    path = _path(token)
    if path is None:
        raise UploadError("That upload has expired. Please attach the file again.")
    # A BytesIO rather than the path: pandas needs a file-like object, and
    # reading through one leaves nothing half-open if the parse raises.
    return load_orders(io.BytesIO(path.read_bytes()), path.name)


def discard(token: str) -> None:
    path = _path(token)
    if path is not None:
        path.unlink(missing_ok=True)


def _path(token: str) -> Path | None:
    # Tokens are generated here, so anything that isn't one is either expired
    # or an attempt to read an arbitrary path -- reject both the same way.
    if not token or not token.replace("-", "").replace("_", "").isalnum():
        return None
    for suffix in ALLOWED_SUFFIXES:
        candidate = UPLOAD_DIR / f"{token}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _sweep() -> None:
    if not UPLOAD_DIR.exists():
        return
    cutoff = time.time() - MAX_AGE_SECONDS
    for path in UPLOAD_DIR.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            # A file being read right now stays; the next sweep gets it.
            continue


__all__ = ["OrdersFileError", "UploadError", "discard", "load", "save"]
