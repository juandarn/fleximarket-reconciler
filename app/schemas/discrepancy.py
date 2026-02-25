"""Pydantic schemas for discrepancies and summary views."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DiscrepancyResponse(BaseModel):
    """Full discrepancy record returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: str
    settlement_entry_id: Optional[UUID] = None
    type: str = Field(
        ...,
        description=(
            "missing_settlement | amount_mismatch | excessive_fee "
            "| currency_mismatch | duplicate_settlement"
        ),
    )
    severity: str = Field(
        ...,
        description="critical | high | medium | low",
    )
    expected_value: Optional[Decimal] = None
    actual_value: Optional[Decimal] = None
    difference_amount: Optional[Decimal] = None
    difference_currency: Optional[str] = None
    impact_usd: Optional[Decimal] = None
    processor_name: Optional[str] = None
    description: Optional[str] = None
    reconciliation_report_id: Optional[UUID] = None
    created_at: datetime


class DiscrepancySummary(BaseModel):
    """Aggregated discrepancy statistics for dashboards / reports."""

    total_count: int = Field(
        ...,
        description="Total number of discrepancies",
    )
    by_type: dict[str, int] = Field(
        default_factory=dict,
        description="Count of discrepancies grouped by type",
    )
    by_processor: dict[str, int] = Field(
        default_factory=dict,
        description="Count of discrepancies grouped by processor",
    )
    by_severity: dict[str, int] = Field(
        default_factory=dict,
        description="Count of discrepancies grouped by severity",
    )
    total_impact_usd: Decimal = Field(
        ...,
        description="Sum of impact_usd across all discrepancies",
    )
