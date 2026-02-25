"""Discrepancy model — records mismatches found during reconciliation."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Discrepancy(Base):
    """A single reconciliation discrepancy between expected and settled data.

    Think of this as an 'alert' — it tells us something doesn't match
    between what our platform recorded and what the processor settled.
    """

    __tablename__ = "discrepancies"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    settlement_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("settlement_entries.id"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment=(
            "missing_settlement | amount_mismatch | excessive_fee "
            "| currency_mismatch | duplicate_settlement"
        ),
    )
    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="critical | high | medium | low",
    )
    expected_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )
    actual_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )
    difference_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
    )
    difference_currency: Mapped[Optional[str]] = mapped_column(
        String(3),
    )
    impact_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
    )
    processor_name: Mapped[Optional[str]] = mapped_column(
        String(50),
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
    )
    reconciliation_report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("reconciliation_reports.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    # -- Relationships --
    settlement_entry: Mapped[Optional[SettlementEntry]] = relationship(
        "SettlementEntry",
        lazy="joined",
    )
    reconciliation_report: Mapped[Optional[ReconciliationReport]] = relationship(
        "ReconciliationReport",
        back_populates="discrepancies",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<Discrepancy(type={self.type!r}, severity={self.severity!r}, "
            f"transaction_id={self.transaction_id!r})>"
        )
