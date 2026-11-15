"""Files a run produced, kept in the database (see storage/models.RunAsset)."""

from sqlalchemy import select

from storage.db import session_scope
from storage.models import RunAsset
from storage.runs import current_run_id


def save_asset(kind: str, data: bytes, content_type: str = "application/octet-stream", run_id: int | None = None) -> None:
    """Store `data` for the run, replacing an earlier asset of the same kind.

    One asset per (run, kind): a refined Marketing plan generates a new image,
    and the founder should see that one, not a pile of old ones.
    """
    target = run_id if run_id is not None else current_run_id()
    with session_scope(write=True) as session:
        for old in session.scalars(select(RunAsset).where(RunAsset.run_id == target, RunAsset.kind == kind)).all():
            session.delete(old)
        session.add(RunAsset(run_id=target, kind=kind, content_type=content_type, data=data))


def get_asset(run_id: int, kind: str) -> tuple[bytes, str] | None:
    """(bytes, content type) of the run's newest asset of this kind, or None."""
    with session_scope() as session:
        row = session.scalars(
            select(RunAsset).where(RunAsset.run_id == run_id, RunAsset.kind == kind).order_by(RunAsset.id.desc())
        ).first()
        return (bytes(row.data), row.content_type) if row else None
