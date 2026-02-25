"""Pydantic schemas for reconciliation requests and report responses."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReconciliationRequest(BaseModel):
    """Request body to kick off a new reconciliation run."""

    date_from: date = Field(
        ...,
        description="Start of the date range to reconcile (inclusive)",
    )
    date_to: date = Field(
        ...,
        description="End of the date range to reconcile (inclusive)",
    )
    processors: Optional[list[str]] = Field(
        None,
        description="Limit reconciliation to specific processor names; None = all",
    )


class ReconciliationResponse(BaseModel):
    """Lightweight response returned immediately after starting a run."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None
    total_transactions: int = 0
    matched_count: int = 0
    discrepancy_count: int = 0
    missing_count: int = 0
    total_expected_amount_usd: Optional[Decimal] = None
    total_settled_amount_usd: Optional[Decimal] = None
    total_discrepancy_amount_usd: Optional[Decimal] = None
    status: Optional[str] = None
    summary: Optional[dict[str, Any]] = None
    created_at: datetime


class ReportResponse(BaseModel):
    """Detailed report response (includes the summary JSON blob)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None
    total_transactions: int = 0
    matched_count: int = 0
    discrepancy_count: int = 0
    missing_count: int = 0
    total_expected_amount_usd: Optional[Decimal] = None
    total_settled_amount_usd: Optional[Decimal] = None
    total_discrepancy_amount_usd: Optional[Decimal] = None
    status: Optional[str] = None
    summary: Optional[dict[str, Any]] = None
    created_at: datetime
