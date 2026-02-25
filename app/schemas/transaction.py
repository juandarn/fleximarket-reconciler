"""Pydantic schemas for expected transactions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TransactionBase(BaseModel):
    """Shared fields for creating and reading transactions."""

    transaction_id: str = Field(
        ...,
        max_length=100,
        description="Unique transaction identifier from the platform",
    )
    amount: Decimal = Field(
        ...,
        max_digits=15,
        decimal_places=2,
        description="Transaction amount in original currency",
    )
    currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code (BRL, MXN, COP, CLP)",
    )
    expected_fee_percent: Optional[Decimal] = Field(
        None,
        max_digits=5,
        decimal_places=4,
    )
    expected_fee_amount: Optional[Decimal] = Field(
        None,
        max_digits=15,
        decimal_places=2,
    )
    expected_net_amount: Optional[Decimal] = Field(
        None,
        max_digits=15,
        decimal_places=2,
    )
    processor_name: str = Field(..., max_length=50)
    country: str = Field(
        ...,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code",
    )
    transaction_date: datetime
    status: str = Field(
        ...,
        max_length=20,
        description="authorized | captured | settled | refunded | failed | cancelled",
    )
    metadata_json: Optional[dict[str, Any]] = Field(
        None,
        description="Arbitrary metadata attached to the transaction",
    )


class TransactionCreate(TransactionBase):
    """Schema for creating a new expected transaction (request body)."""

    pass


class TransactionResponse(TransactionBase):
    """Schema returned when reading a transaction (includes DB-generated fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
