"""Reconciliation engine endpoints.

Provides routes to trigger a reconciliation run, list past reports,
and retrieve individual report details.
"""

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
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
