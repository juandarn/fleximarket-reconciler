"""Expected transaction model — the 'source of truth' from our platform."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import DateTime, Index, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExpectedTransaction(Base):
    """Represents a transaction as recorded by our platform.

    This is compared against settlement entries from payment processors
    to find discrepancies (missing settlements, fee mismatches, etc.).
    """

    __tablename__ = "expected_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        comment="ISO 4217 currency code: BRL, MXN, COP, CLP",
    )
    expected_fee_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
    )
    expected_fee_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
    )
    expected_net_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
    )
    processor_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        comment="ISO 3166-1 alpha-2 country code",
    )
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="authorized | captured | settled | refunded | failed | cancelled",
    )
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_expected_tx_processor_date", "processor_name", "transaction_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExpectedTransaction(transaction_id={self.transaction_id!r}, "
            f"amount={self.amount}, currency={self.currency!r})>"
        )
