"""Batch reconciliation job management.

Allows submitting reconciliation runs as background tasks and tracking
their progress.  Uses an in-memory dict for job tracking (MVP approach —
a production system would use Redis, a DB table, or a proper task queue
like Celery).
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.services.reconciliation.engine import ReconciliationEngine

logger = get_logger(__name__)

# In-memory job tracker (simple dict for MVP)
_jobs: dict[str, dict] = {}


def submit_reconciliation_job(
    db_factory,  # callable that creates a new session
    date_from: date,
    date_to: date,
    processors: list[str] | None,
    background_tasks: BackgroundTasks,
) -> str:
    """Submit a reconciliation job to run in background.

    Returns job_id immediately so the caller can poll for status later.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "date_from": str(date_from),
        "date_to": str(date_to),
        "processors": processors,
        "report_id": None,
        "error": None,
    }
    background_tasks.add_task(
        _run_job, job_id, db_factory, date_from, date_to, processors
    )
    return job_id


def _run_job(
    job_id: str,
    db_factory,
    date_from: date,
    date_to: date,
    processors: list[str] | None,
) -> None:
    """Background task that runs the full reconciliation cycle."""
    _jobs[job_id]["status"] = "running"
    try:
        db: Session = db_factory()
        try:
            engine = ReconciliationEngine(db, settings)
            report = engine.run(date_from, date_to, processors)
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["report_id"] = str(report.id)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)


def get_job_status(job_id: str) -> dict | None:
    """Look up a job by ID.  Returns None if not found."""
    return _jobs.get(job_id)


def list_jobs() -> list[dict]:
    """Return all tracked jobs (newest first by insertion order)."""
    return list(_jobs.values())
