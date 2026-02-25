"""Pydantic schemas for settlement entries and upload responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SettlementBase(BaseModel):
    """Shared fields for settlement entries."""

    transaction_id: str = Field(..., max_length=100)
    gross_amount: Optional[Decimal] = Field(
        None,
        max_digits=15,
        decimal_places=2,
    )
    original_currency: Optional[str] = Field(None, max_length=3)
    net_amount: Optional[Decimal] = Field(
        None,
        max_digits=15,
        decimal_places=2,
    )
    settlement_currency: Optional[str] = Field(None, max_length=3)
    fee_amount: Optional[Decimal] = Field(
        None,
        max_digits=15,
        decimal_places=2,
    )
    fee_breakdown: Optional[dict[str, Any]] = None
    fx_rate: Optional[Decimal] = Field(
        None,
        max_digits=12,
        decimal_places=6,
    )
    settlement_date: Optional[datetime] = None
    processor_name: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(
        None,
        max_length=20,
        description="completed | failed | held | reversed",
    )
    source_file: Optional[str] = Field(None, max_length=255)
    raw_data: Optional[dict[str, Any]] = None


class SettlementCreate(SettlementBase):
    """Schema for creating a new settlement entry."""

    pass


class SettlementResponse(SettlementBase):
    """Schema returned when reading a settlement entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class UploadResponse(BaseModel):
    """Schema returned after uploading a settlement file."""

    status: str = Field(
        ...,
        description="Upload result status (success, partial, failed)",
    )
    message: str
    entries_processed: int = Field(
        ...,
        description="Total rows parsed from the file",
    )
    entries_saved: int = Field(
        ...,
        description="Rows successfully persisted to DB",
    )
    entries_skipped: int = Field(
        ...,
        description="Rows skipped (duplicates, invalid, etc.)",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Human-readable error messages for failed rows",
    )
