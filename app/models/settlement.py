"""Settlement entry model — data imported from payment processor reports."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import DateTime, Index, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SettlementEntry(Base):
    """Represents a single line from a processor's settlement report.

    Each entry corresponds to one transaction's settlement outcome.
    We compare these against ExpectedTransaction records to reconcile.
    """

    __tablename__ = "settlement_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    gross_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
    )
    original_currency: Mapped[Optional[str]] = mapped_column(
        String(3),
    )
    net_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
    )
    settlement_currency: Mapped[Optional[str]] = mapped_column(
        String(3),
    )
    fee_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
    )
    fee_breakdown: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    fx_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 6),
        nullable=True,
    )
    settlement_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
    )
    processor_name: Mapped[Optional[str]] = mapped_column(
        String(50),
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="completed | failed | held | reversed",
    )
    source_file: Mapped[Optional[str]] = mapped_column(
        String(255),
    )
    raw_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_settlement_processor_date", "processor_name", "settlement_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<SettlementEntry(transaction_id={self.transaction_id!r}, "
            f"net_amount={self.net_amount}, status={self.status!r})>"
        )
