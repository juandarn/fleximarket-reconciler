"""Reconciliation report model — tracks each reconciliation run."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Date, DateTime, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReconciliationReport(Base):
    """Aggregated result of one reconciliation run.

    Each run compares expected transactions against settlement entries
    for a specific date range and produces a summary with linked
    discrepancy records.
    """

    __tablename__ = "reconciliation_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )
    date_range_start: Mapped[Optional[date]] = mapped_column(
        Date,
    )
    date_range_end: Mapped[Optional[date]] = mapped_column(
        Date,
    )
    total_transactions: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    matched_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    discrepancy_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    missing_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    total_expected_amount_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        default=0,
    )
    total_settled_amount_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        default=0,
    )
    total_discrepancy_amount_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        default=0,
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="running | completed | failed",
    )
    summary: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    # -- Relationships --
    discrepancies: Mapped[list[Discrepancy]] = relationship(
        "Discrepancy",
        back_populates="reconciliation_report",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<ReconciliationReport(id={self.id!r}, status={self.status!r}, "
            f"discrepancy_count={self.discrepancy_count})>"
        )
