# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, select
from core.config import config
from core.db.models import JobDB, WorkerHeartbeatDB
from core.db.session import session_scope


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enqueue(job_type: str, payload: dict, *, job_id: str | None = None) -> str:
    job_id = job_id or str(uuid.uuid4())
    with session_scope() as db:
        if db.get(JobDB, job_id) is None:
            db.add(JobDB(job_id=job_id, job_type=job_type, payload=payload,
                         max_attempts=config.JOB_MAX_ATTEMPTS, available_at=_now()))
    return job_id


def claim(worker_id: str) -> dict | None:
    now = _now()
    with session_scope() as db:
        query = (select(JobDB).where(
            JobDB.status.in_(["queued", "retry", "running"]), JobDB.available_at <= now,
            or_(JobDB.lease_until.is_(None), JobDB.lease_until < now),
        ).order_by(JobDB.available_at, JobDB.created_at).limit(1))
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        row = db.execute(query).scalar_one_or_none()
        if row is None:
            return None
        row.status = "running"; row.worker_id = worker_id; row.attempts += 1
        row.lease_until = now + timedelta(seconds=config.JOB_LEASE_SECONDS); row.updated_at = now
        db.flush()
        return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def complete(job_id: str, result: dict | None = None) -> None:
    with session_scope() as db:
        row = db.get(JobDB, job_id)
        if row:
            row.status = "completed"; row.result = result or {}; row.lease_until = None; row.updated_at = _now()


def fail(job_id: str, error: str) -> str:
    with session_scope() as db:
        row = db.get(JobDB, job_id)
        if row is None:
            return "missing"
        row.last_error = error[:10_000]; row.lease_until = None; row.updated_at = _now()
        if row.attempts >= row.max_attempts:
            row.status = "dead"
        else:
            row.status = "retry"
            row.available_at = _now() + timedelta(seconds=min(300, 2 ** row.attempts * 5))
        return row.status


def get(job_id: str) -> dict | None:
    with session_scope() as db:
        row = db.get(JobDB, job_id)
        return None if row is None else {c.name: getattr(row, c.name) for c in row.__table__.columns}


def list_jobs(status: str | None = None, limit: int = 100) -> list[dict]:
    with session_scope() as db:
        query = select(JobDB)
        if status:
            query = query.where(JobDB.status == status)
        rows = db.execute(query.order_by(JobDB.created_at.desc()).limit(limit)).scalars().all()
        return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]


def retry(job_id: str) -> dict | None:
    with session_scope() as db:
        row = db.get(JobDB, job_id)
        if row is None:
            return None
        if row.status not in {"dead", "retry"}:
            raise ValueError("Only failed jobs can be retried")
        row.status = "queued"; row.attempts = 0; row.available_at = _now()
        row.lease_until = None; row.worker_id = None; row.last_error = None; row.updated_at = _now()
        db.flush()
        return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def renew(job_id: str, worker_id: str) -> bool:
    with session_scope() as db:
        row = db.get(JobDB, job_id)
        if row is None or row.status != "running" or row.worker_id != worker_id:
            return False
        row.lease_until = _now() + timedelta(seconds=config.JOB_LEASE_SECONDS)
        row.updated_at = _now()
        return True


def heartbeat(worker_id: str, hostname: str, process_id: int, current_job_id: str | None = None) -> None:
    with session_scope() as db:
        row = db.get(WorkerHeartbeatDB, worker_id)
        if row is None:
            row = WorkerHeartbeatDB(worker_id=worker_id, hostname=hostname, process_id=process_id,
                                    current_job_id=current_job_id, started_at=_now())
            db.add(row)
        row.current_job_id = current_job_id; row.last_seen_at = _now()
