"""PayFlow CSV settlement file parser."""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import List

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


class CsvParser(BaseParser):
    """Parser for PayFlow CSV settlement reports.

    Expected CSV columns:
        settlement_id, transaction_ref, txn_date, settle_date,
        original_amount, currency, processing_fee, interchange_fee,
        net_amount, status
    """

    processor_name: str = "PayFlow"

    def parse(self, file_content: bytes, filename: str) -> List[SettlementCreate]:
        """Parse PayFlow CSV bytes into normalized SettlementCreate entries.

        Rows that are malformed or missing required fields are skipped
        with a warning — we never crash the whole upload for one bad row.
        """
        entries: List[SettlementCreate] = []
        text = file_content.decode("utf-8-sig")  # handle BOM if present
        reader = csv.DictReader(io.StringIO(text))

        for row_num, row in enumerate(reader, start=2):  # row 1 is header
            try:
                entry = self._parse_row(row, filename, row_num)
                if entry is not None:
                    entries.append(entry)
                    logger.debug(
                        "Parsed CSV row %d: txn=%s amount=%s",
                        row_num,
                        entry.transaction_id,
                        entry.gross_amount,
                    )
            except Exception as exc:
                logger.warning("Skipping CSV row %d in %s: %s", row_num, filename, exc)

        logger.info(
            "CSV parse complete for %s: %d entries parsed", filename, len(entries)
        )
        return entries

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_row(
        self, row: dict, filename: str, row_num: int
    ) -> SettlementCreate | None:
        """Convert a single CSV dict-row to a SettlementCreate.

        Returns None if a required field is missing or unparseable.
        """
        # --- required fields ------------------------------------------------
        transaction_ref = row.get("transaction_ref", "").strip()
        if not transaction_ref:
            logger.warning("Row %d: missing transaction_ref, skipping", row_num)
            return None

        # --- amounts --------------------------------------------------------
        gross_amount = self._to_decimal(
            row.get("original_amount"), "original_amount", row_num
        )
        processing_fee = self._to_decimal(
            row.get("processing_fee"), "processing_fee", row_num
        )
        interchange_fee = self._to_decimal(
            row.get("interchange_fee"), "interchange_fee", row_num
        )
        net_amount = self._to_decimal(row.get("net_amount"), "net_amount", row_num)

        # Total fee = processing + interchange (both may be None)
        fee_amount: Decimal | None = None
        if processing_fee is not None and interchange_fee is not None:
            fee_amount = processing_fee + interchange_fee
        elif processing_fee is not None:
            fee_amount = processing_fee
        elif interchange_fee is not None:
            fee_amount = interchange_fee

        # fee_breakdown
        fee_breakdown: dict | None = None
        if processing_fee is not None or interchange_fee is not None:
            fee_breakdown = {
                "processing": float(processing_fee)
                if processing_fee is not None
                else None,
                "interchange": float(interchange_fee)
                if interchange_fee is not None
                else None,
            }

        # --- currency -------------------------------------------------------
        raw_currency = row.get("currency", "").strip()
        try:
            currency = normalize_currency(raw_currency) if raw_currency else None
        except ValueError:
            logger.warning("Row %d: unknown currency %r", row_num, raw_currency)
            currency = raw_currency.upper() if raw_currency else None

        # --- dates ----------------------------------------------------------
        settle_date = (
            normalize_date(row.get("settle_date", "").strip())
            if row.get("settle_date", "").strip()
            else None
        )

        # --- status ---------------------------------------------------------
        raw_status = row.get("status", "").strip()
        status = normalize_status(raw_status, "payflow") if raw_status else None

        return SettlementCreate(
            transaction_id=normalize_transaction_id(transaction_ref),
            gross_amount=gross_amount,
            original_currency=currency,
            net_amount=net_amount,
            settlement_currency=currency,  # PayFlow settles in original currency
            fee_amount=fee_amount,
            fee_breakdown=fee_breakdown,
            fx_rate=None,  # PayFlow doesn't provide FX rate
            settlement_date=settle_date,
            processor_name=self.processor_name,
            status=status,
            source_file=filename,
            raw_data=dict(row),
        )

    @staticmethod
    def _to_decimal(value: str | None, field_name: str, row_num: int) -> Decimal | None:
        """Safely convert a string to Decimal, returning None on failure."""
        if value is None or value.strip() == "":
            return None
        try:
            return Decimal(value.strip())
        except (InvalidOperation, ValueError):
            logger.warning("Row %d: non-numeric %s=%r", row_num, field_name, value)
            return None
