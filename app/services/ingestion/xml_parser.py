"""GlobalPay XML settlement file parser."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import List, Optional

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


class XmlParser(BaseParser):
    """Parser for GlobalPay XML settlement reports.

    Expected XML structure::

        <SettlementReport processor="GlobalPay" date="2024-01-18">
          <Settlement>
            <SettlementId>GP-2024-0001</SettlementId>
            <TransactionRef>TXN-CO-2024-000185</TransactionRef>
            <OriginalAmount currency="COP">1546100.00</OriginalAmount>
            <FeeAmount>43291.00</FeeAmount>
            <NetAmount currency="COP">1502759.00</NetAmount>
            <FxRate toCurrency="USD">0.000250</FxRate>
            <SettlementDate>2024-01-07</SettlementDate>
            <Status>COMPLETED</Status>
          </Settlement>
          ...
        </SettlementReport>
    """

    processor_name: str = "GlobalPay"

    def parse(self, file_content: bytes, filename: str) -> List[SettlementCreate]:
        """Parse GlobalPay XML bytes into normalized SettlementCreate entries."""
        entries: List[SettlementCreate] = []

        try:
            root = ET.fromstring(file_content)
        except ET.ParseError as exc:
            logger.error("Failed to parse XML file %s: %s", filename, exc)
            return entries

        for idx, settlement_el in enumerate(root.findall("Settlement")):
            try:
                entry = self._parse_element(settlement_el, filename, idx)
                if entry is not None:
                    entries.append(entry)
                    logger.debug(
                        "Parsed XML element %d: txn=%s amount=%s",
                        idx,
                        entry.transaction_id,
                        entry.gross_amount,
                    )
            except Exception as exc:
                logger.warning("Skipping XML element %d in %s: %s", idx, filename, exc)

        logger.info(
            "XML parse complete for %s: %d entries parsed", filename, len(entries)
        )
        return entries

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_element(
        self, el: ET.Element, filename: str, idx: int
    ) -> SettlementCreate | None:
        """Convert a single <Settlement> XML element to a SettlementCreate."""

        # --- required: transaction ref --------------------------------------
        txn_ref = self._text(el, "TransactionRef")
        if not txn_ref:
            logger.warning("Element %d: missing TransactionRef, skipping", idx)
            return None

        # --- amounts --------------------------------------------------------
        gross_amount = self._decimal(el, "OriginalAmount", idx)
        fee_amount = self._decimal(el, "FeeAmount", idx)
        net_amount = self._decimal(el, "NetAmount", idx)

        # --- currency (from OriginalAmount/@currency) -----------------------
        original_currency = self._attr(el, "OriginalAmount", "currency")
        settlement_currency = self._attr(el, "NetAmount", "currency")
        try:
            original_currency = (
                normalize_currency(original_currency) if original_currency else None
            )
        except ValueError:
            logger.warning(
                "Element %d: unknown original currency %r", idx, original_currency
            )
        try:
            settlement_currency = (
                normalize_currency(settlement_currency) if settlement_currency else None
            )
        except ValueError:
            logger.warning(
                "Element %d: unknown settlement currency %r", idx, settlement_currency
            )

        # --- FX rate --------------------------------------------------------
        fx_rate = self._decimal(el, "FxRate", idx)

        # --- settlement date ------------------------------------------------
        raw_date = self._text(el, "SettlementDate")
        settle_date = normalize_date(raw_date) if raw_date else None

        # --- status ---------------------------------------------------------
        raw_status = self._text(el, "Status")
        status = normalize_status(raw_status, "globalpay") if raw_status else None

        # --- raw data dict for auditing -------------------------------------
        raw_data = self._element_to_dict(el)

        return SettlementCreate(
            transaction_id=normalize_transaction_id(txn_ref),
            gross_amount=gross_amount,
            original_currency=original_currency,
            net_amount=net_amount,
            settlement_currency=settlement_currency,
            fee_amount=fee_amount,
            fee_breakdown=None,  # GlobalPay gives a single fee amount
            fx_rate=fx_rate,
            settlement_date=settle_date,
            processor_name=self.processor_name,
            status=status,
            source_file=filename,
            raw_data=raw_data,
        )

    # ------------------------------------------------------------------
    # XML convenience methods
    # ------------------------------------------------------------------

    @staticmethod
    def _text(parent: ET.Element, tag: str) -> Optional[str]:
        """Get the text content of a child element, or None."""
        child = parent.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None

    @staticmethod
    def _attr(parent: ET.Element, tag: str, attr: str) -> Optional[str]:
        """Get an attribute of a child element, or None."""
        child = parent.find(tag)
        if child is not None:
            return child.get(attr)
        return None

    @staticmethod
    def _decimal(parent: ET.Element, tag: str, idx: int) -> Optional[Decimal]:
        """Get text of a child element as a Decimal, or None."""
        child = parent.find(tag)
        if child is None or not child.text:
            return None
        try:
            return Decimal(child.text.strip())
        except (InvalidOperation, ValueError):
            logger.warning("Element %d: non-numeric %s=%r", idx, tag, child.text)
            return None

    @staticmethod
    def _element_to_dict(el: ET.Element) -> dict:
        """Convert a shallow XML element into a dict for raw_data storage."""
        result: dict = {}
        for child in el:
            key = child.tag
            value = child.text.strip() if child.text else None
            if child.attrib:
                result[key] = {"value": value, **child.attrib}
            else:
                result[key] = value
        return result
