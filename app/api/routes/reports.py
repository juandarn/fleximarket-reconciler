"""Reporting and query endpoints.

Provides routes to query discrepancies, transaction status, and
reconciliation reports with filtering and pagination.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.discrepancy import Discrepancy
from app.models.reconciliation import ReconciliationReport
from app.models.settlement import SettlementEntry
from app.models.transaction import ExpectedTransaction
from app.schemas.discrepancy import DiscrepancyResponse, DiscrepancySummary

logger = get_logger(__name__)

router = APIRouter()


@router.get("/discrepancies", response_model=list[DiscrepancyResponse])
def list_discrepancies(
    type: Optional[str] = Query(None, description="Filter by discrepancy type"),
    processor: Optional[str] = Query(None, description="Filter by processor name"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    date_from: Optional[str] = Query(
        None, description="Filter by created_at >= date (YYYY-MM-DD)"
    ),
    date_to: Optional[str] = Query(
        None, description="Filter by created_at <= date (YYYY-MM-DD)"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    db: Session = Depends(get_db),
) -> list:
    """List discrepancies with optional filters and pagination."""
    query = db.query(Discrepancy)

    if type is not None:
        query = query.filter(Discrepancy.type == type)
    if processor is not None:
        query = query.filter(Discrepancy.processor_name.ilike(f"%{processor}%"))
    if severity is not None:
        query = query.filter(Discrepancy.severity == severity)
    if date_from is not None:
        try:
            dt_from = datetime.fromisoformat(date_from)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid date_from format: {date_from}"
            )
        query = query.filter(Discrepancy.created_at >= dt_from)
    if date_to is not None:
        try:
            dt_to = datetime.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid date_to format: {date_to}"
            )
        query = query.filter(Discrepancy.created_at <= dt_to)

    total = query.count()
    offset = (page - 1) * limit
    items = (
        query.order_by(Discrepancy.created_at.desc()).offset(offset).limit(limit).all()
    )

    logger.info(
        "Discrepancies query: total=%d page=%d limit=%d returned=%d",
        total,
        page,
        limit,
        len(items),
    )
    return items


@router.get("/discrepancies/summary", response_model=DiscrepancySummary)
def discrepancy_summary(db: Session = Depends(get_db)) -> DiscrepancySummary:
    """Summary statistics: total count, by_type, by_processor, by_severity, total_impact_usd."""
    total_count = db.query(Discrepancy).count()

    # Group by type
    by_type_rows = (
        db.query(Discrepancy.type, func.count(Discrepancy.id))
        .group_by(Discrepancy.type)
        .all()
    )
    by_type = {row[0]: row[1] for row in by_type_rows}

    # Group by processor
    by_processor_rows = (
        db.query(Discrepancy.processor_name, func.count(Discrepancy.id))
        .filter(Discrepancy.processor_name.isnot(None))
        .group_by(Discrepancy.processor_name)
        .all()
    )
    by_processor = {row[0]: row[1] for row in by_processor_rows}

    # Group by severity
    by_severity_rows = (
        db.query(Discrepancy.severity, func.count(Discrepancy.id))
        .group_by(Discrepancy.severity)
        .all()
    )
    by_severity = {row[0]: row[1] for row in by_severity_rows}

    # Total impact
    total_impact_result = db.query(func.sum(Discrepancy.impact_usd)).scalar()
    total_impact_usd = (
        Decimal(str(total_impact_result)) if total_impact_result else Decimal("0")
    )

    return DiscrepancySummary(
        total_count=total_count,
        by_type=by_type,
        by_processor=by_processor,
        by_severity=by_severity,
        total_impact_usd=total_impact_usd,
    )


@router.get("/transactions/{transaction_id}/status")
def transaction_status(
    transaction_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Get settlement status for a specific transaction.

    Returns: transaction info, settlement info (if exists), any discrepancies.
    """
    # Look up expected transaction
    txn = (
        db.query(ExpectedTransaction)
        .filter(ExpectedTransaction.transaction_id == transaction_id)
        .first()
    )

    if txn is None:
        raise HTTPException(
            status_code=404, detail=f"Transaction '{transaction_id}' not found"
        )

    # Look up settlement entries
    settlements = (
        db.query(SettlementEntry)
        .filter(SettlementEntry.transaction_id == transaction_id)
        .all()
    )

    # Look up discrepancies
    discrepancies = (
        db.query(Discrepancy).filter(Discrepancy.transaction_id == transaction_id).all()
    )

    return {
        "transaction_id": transaction_id,
        "transaction": {
            "amount": float(txn.amount),
            "currency": txn.currency,
            "processor_name": txn.processor_name,
            "status": txn.status,
            "transaction_date": txn.transaction_date.isoformat()
            if txn.transaction_date
            else None,
        },
        "settlements": [
            {
                "id": str(s.id),
                "net_amount": float(s.net_amount) if s.net_amount else None,
                "gross_amount": float(s.gross_amount) if s.gross_amount else None,
                "status": s.status,
                "settlement_date": s.settlement_date.isoformat()
                if s.settlement_date
                else None,
                "processor_name": s.processor_name,
            }
            for s in settlements
        ],
        "discrepancies": [
            {
                "id": str(d.id),
                "type": d.type,
                "severity": d.severity,
                "impact_usd": float(d.impact_usd) if d.impact_usd else None,
                "description": d.description,
            }
            for d in discrepancies
        ],
        "settlement_count": len(settlements),
        "discrepancy_count": len(discrepancies),
    }


@router.get("/reconciliation/report")
def reconciliation_report(
    date_from: Optional[str] = Query(
        None, description="Filter by date_range_start >= (YYYY-MM-DD)"
    ),
    date_to: Optional[str] = Query(
        None, description="Filter by date_range_end <= (YYYY-MM-DD)"
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Get reconciliation report for a date range.

    Returns latest report matching the date range, or 404.
    """
    query = db.query(ReconciliationReport)

    if date_from is not None:
        try:
            dt_from = datetime.fromisoformat(date_from).date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid date_from format: {date_from}"
            )
        query = query.filter(ReconciliationReport.date_range_start >= dt_from)

    if date_to is not None:
        try:
            dt_to = datetime.fromisoformat(date_to).date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid date_to format: {date_to}"
            )
        query = query.filter(ReconciliationReport.date_range_end <= dt_to)

    report = query.order_by(ReconciliationReport.created_at.desc()).first()

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No reconciliation report found for the given date range",
        )

    return {
        "id": str(report.id),
        "status": report.status,
        "started_at": report.started_at.isoformat() if report.started_at else None,
        "completed_at": report.completed_at.isoformat()
        if report.completed_at
        else None,
        "date_range_start": report.date_range_start.isoformat()
        if report.date_range_start
        else None,
        "date_range_end": report.date_range_end.isoformat()
        if report.date_range_end
        else None,
        "total_transactions": report.total_transactions,
        "matched_count": report.matched_count,
        "discrepancy_count": report.discrepancy_count,
        "missing_count": report.missing_count,
        "total_expected_amount_usd": float(report.total_expected_amount_usd)
        if report.total_expected_amount_usd
        else 0,
        "total_settled_amount_usd": float(report.total_settled_amount_usd)
        if report.total_settled_amount_usd
        else 0,
        "total_discrepancy_amount_usd": float(report.total_discrepancy_amount_usd)
        if report.total_discrepancy_amount_usd
        else 0,
        "summary": report.summary,
    }
