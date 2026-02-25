"""TransactMax JSON settlement file parser."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, List

from app.core.logging import get_logger
from app.schemas.settlement import SettlementCreate
from app.services.ingestion.base_parser import BaseParser
from app.services.ingestion.normalizer import (
    normalize_currency,
    normalize_date,
    normalize_status,
    normalize_transaction_id,
)

logger = get_logger(__name__)


class JsonParser(BaseParser):
    """Parser for TransactMax JSON settlement reports.

    Expected JSON structure::

        {
            "report_date": "2024-01-18",
            "processor": "TransactMax",
            "settlements": [
                {
                    "id": "TM-STL-00001",
                    "original_transaction_id": "TXN-CO-2024-000098",
                    "transaction_date": "2024-01-04",
                    "settlement_date": "2024-01-09",
                    "gross_amount": 670450.0,
                    "currency": "COP",
                    "total_fees": 21454.0,
                    "net_amount": 648946.0,
                    "settlement_status": "completed"
                },
                ...
            ]
        }
    """

    processor_name: str = "TransactMax"

    def parse(self, file_content: bytes, filename: str) -> List[SettlementCreate]:
        """Parse TransactMax JSON bytes into normalized SettlementCreate entries."""
        entries: List[SettlementCreate] = []

        try:
            data = json.loads(file_content.decode("utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error("Failed to decode JSON file %s: %s", filename, exc)
            return entries

        settlements = data.get("settlements", [])
        if not isinstance(settlements, list):
            logger.error("'settlements' key is not a list in %s", filename)
            return entries

        for idx, item in enumerate(settlements):
            try:
                entry = self._parse_item(item, filename, idx)
                if entry is not None:
                    entries.append(entry)
                    logger.debug(
                        "Parsed JSON item %d: txn=%s amount=%s",
                        idx,
                        entry.transaction_id,
                        entry.gross_amount,
                    )
            except Exception as exc:
                logger.warning("Skipping JSON item %d in %s: %s", idx, filename, exc)

        logger.info(
            "JSON parse complete for %s: %d entries parsed", filename, len(entries)
        )
        return entries

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_item(
        self, item: dict[str, Any], filename: str, idx: int
    ) -> SettlementCreate | None:
        """Convert a single JSON settlement object to a SettlementCreate."""
        if not isinstance(item, dict):
            logger.warning("Item %d: expected dict, got %s", idx, type(item).__name__)
            return None

        # --- required: transaction ID ---------------------------------------
        txn_id = item.get("original_transaction_id", "")
        if not txn_id:
            logger.warning("Item %d: missing original_transaction_id, skipping", idx)
            return None

        # --- amounts --------------------------------------------------------
        gross_amount = self._to_decimal(item.get("gross_amount"), "gross_amount", idx)
        net_amount = self._to_decimal(item.get("net_amount"), "net_amount", idx)
        fee_amount = self._to_decimal(item.get("total_fees"), "total_fees", idx)

        # --- currency -------------------------------------------------------
        raw_currency = str(item.get("currency", "")).strip()
        try:
            currency = normalize_currency(raw_currency) if raw_currency else None
        except ValueError:
            logger.warning("Item %d: unknown currency %r", idx, raw_currency)
            currency = raw_currency.upper() if raw_currency else None

        # --- dates ----------------------------------------------------------
        raw_settle_date = str(item.get("settlement_date", "")).strip()
        settle_date = normalize_date(raw_settle_date) if raw_settle_date else None

        # --- status ---------------------------------------------------------
        raw_status = str(item.get("settlement_status", "")).strip()
        status = normalize_status(raw_status, "transactmax") if raw_status else None

        return SettlementCreate(
            transaction_id=normalize_transaction_id(str(txn_id)),
            gross_amount=gross_amount,
            original_currency=currency,
            net_amount=net_amount,
            settlement_currency=currency,  # TransactMax settles in original currency
            fee_amount=fee_amount,
            fee_breakdown=None,  # TransactMax doesn't provide breakdown
            fx_rate=None,
            settlement_date=settle_date,
            processor_name=self.processor_name,
            status=status,
            source_file=filename,
            raw_data=item,
        )

    @staticmethod
    def _to_decimal(value: Any, field_name: str, idx: int) -> Decimal | None:
        """Safely convert a value to Decimal."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            logger.warning("Item %d: non-numeric %s=%r", idx, field_name, value)
            return None
