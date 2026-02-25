"""Reconciliation engine endpoints.

Provides routes to trigger a reconciliation run, list past reports,
and retrieve individual report details.
"""

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.reconciliation import ReconciliationReport
from app.schemas.reconciliation import (
    ReconciliationRequest,
    ReconciliationResponse,
    ReportResponse,
)
from app.services.reconciliation.engine import ReconciliationEngine

logger = get_logger(__name__)

router = APIRouter()


@router.post("/run", response_model=ReconciliationResponse)
def run_reconciliation(
    body: ReconciliationRequest,
    db: Session = Depends(get_db),
) -> ReconciliationReport:
    """Trigger a reconciliation run for the given date range.

    Accepts an optional list of processor names to limit scope.
    Returns the completed report with summary statistics.
    """
    logger.info(
        "Reconciliation requested: %s to %s, processors=%s",
        body.date_from,
        body.date_to,
        body.processors,
    )

    engine = ReconciliationEngine(db=db, config=settings)

    try:
        report = engine.run(
            date_from=body.date_from,
            date_to=body.date_to,
            processors=body.processors,
        )
    except Exception as exc:
        logger.exception("Reconciliation run failed")
        raise HTTPException(status_code=500, detail=str(exc))

    return report


@router.get("/reports", response_model=List[ReconciliationResponse])
def list_reports(
    db: Session = Depends(get_db),
) -> list[ReconciliationReport]:
    """List all reconciliation reports, ordered by creation date descending."""
    reports = (
        db.query(ReconciliationReport)
        .order_by(ReconciliationReport.created_at.desc())
        .all()
    )
    return reports


@router.get("/reports/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: UUID,
    db: Session = Depends(get_db),
) -> ReconciliationReport:
    """Retrieve a single reconciliation report by ID."""
    report = (
        db.query(ReconciliationReport)
        .filter(ReconciliationReport.id == report_id)
        .first()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


# ── Batch / async reconciliation endpoints ───────────────────────────


@router.post("/run-async")
def run_reconciliation_async(
    request: ReconciliationRequest,
    background_tasks: BackgroundTasks,
):
    """Submit reconciliation as a background job.

    Returns immediately with a job_id that can be polled via GET /jobs/{id}.
    """
    from app.core.database import SessionLocal
    from app.services.reconciliation.batch import submit_reconciliation_job

    job_id = submit_reconciliation_job(
        db_factory=SessionLocal,
        date_from=request.date_from,
        date_to=request.date_to,
        processors=request.processors,
        background_tasks=background_tasks,
    )
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Reconciliation job submitted",
    }


@router.get("/jobs")
def list_jobs():
    """List all submitted reconciliation jobs."""
    from app.services.reconciliation.batch import list_jobs as _list_jobs

    return {"jobs": _list_jobs()}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Poll a specific job's status by its ID."""
    from app.services.reconciliation.batch import get_job_status

    job = get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
