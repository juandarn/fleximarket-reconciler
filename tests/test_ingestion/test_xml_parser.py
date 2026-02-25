"""Tests for the GlobalPay XML parser.

These tests exercise parsing logic only — no database required.
"""

import os
from decimal import Decimal

import pytest

from app.services.ingestion.xml_parser import XmlParser

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"
)
XML_FILE = os.path.join(DATA_DIR, "settlement_globalpay.xml")


@pytest.fixture
def parser() -> XmlParser:
    return XmlParser()


@pytest.fixture
def xml_bytes() -> bytes:
    with open(XML_FILE, "rb") as f:
        return f.read()


# ------------------------------------------------------------------
# Happy-path tests
# ------------------------------------------------------------------


class TestParseValidXml:
    def test_parse_valid_xml(self, parser: XmlParser, xml_bytes: bytes):
        """Parse the real GlobalPay XML fixture and verify entries."""
        entries = parser.parse(xml_bytes, "settlement_globalpay.xml")
        assert len(entries) > 0
        for entry in entries:
            assert entry.processor_name == "GlobalPay"
            assert entry.source_file == "settlement_globalpay.xml"

    def test_parse_xml_field_mapping(self, parser: XmlParser, xml_bytes: bytes):
        """Verify XML elements map to the correct schema fields."""
        entries = parser.parse(xml_bytes, "settlement_globalpay.xml")
        first = entries[0]

        # TransactionRef -> transaction_id
        assert first.transaction_id is not None
        assert first.transaction_id == first.transaction_id.upper()

        # OriginalAmount -> gross_amount (Decimal)
        assert isinstance(first.gross_amount, Decimal)

        # FeeAmount -> fee_amount
        assert isinstance(first.fee_amount, Decimal)

        # NetAmount -> net_amount
        assert isinstance(first.net_amount, Decimal)

        # OriginalAmount/@currency -> original_currency
        assert first.original_currency is not None
        assert len(first.original_currency) == 3

        # SettlementDate -> settlement_date
        assert first.settlement_date is not None

    def test_parse_xml_fx_rate(self, parser: XmlParser, xml_bytes: bytes):
        """Verify FxRate is extracted as a Decimal."""
        entries = parser.parse(xml_bytes, "settlement_globalpay.xml")
        first = entries[0]

        # GlobalPay provides FxRate
        assert first.fx_rate is not None
        assert isinstance(first.fx_rate, Decimal)
        assert first.fx_rate > 0

    def test_parse_xml_status_mapping(self, parser: XmlParser, xml_bytes: bytes):
        """Verify COMPLETED -> completed mapping."""
        entries = parser.parse(xml_bytes, "settlement_globalpay.xml")
        statuses = {e.status for e in entries}
        assert "completed" in statuses


# ------------------------------------------------------------------
# Edge-case tests
# ------------------------------------------------------------------


class TestXmlEdgeCases:
    def test_parse_xml_empty(self, parser: XmlParser):
        """Empty report returns empty list."""
        content = b'<?xml version="1.0"?><SettlementReport></SettlementReport>'
        entries = parser.parse(content, "empty.xml")
        assert entries == []

    def test_parse_xml_invalid(self, parser: XmlParser):
        """Invalid XML returns empty list, not crash."""
        entries = parser.parse(b"<not valid xml", "bad.xml")
        assert entries == []

    def test_parse_xml_missing_transaction_ref(self, parser: XmlParser):
        """Settlement without TransactionRef is skipped."""
        content = b"""<?xml version="1.0"?>
        <SettlementReport>
          <Settlement>
            <SettlementId>GP-001</SettlementId>
            <OriginalAmount currency="BRL">100.00</OriginalAmount>
            <FeeAmount>2.80</FeeAmount>
            <NetAmount currency="BRL">97.20</NetAmount>
            <FxRate toCurrency="USD">0.20</FxRate>
            <SettlementDate>2024-01-05</SettlementDate>
            <Status>COMPLETED</Status>
          </Settlement>
          <Settlement>
            <SettlementId>GP-002</SettlementId>
            <TransactionRef>TXN-002</TransactionRef>
            <OriginalAmount currency="MXN">200.00</OriginalAmount>
            <FeeAmount>5.60</FeeAmount>
            <NetAmount currency="MXN">194.40</NetAmount>
            <FxRate toCurrency="USD">0.06</FxRate>
            <SettlementDate>2024-01-06</SettlementDate>
            <Status>COMPLETED</Status>
          </Settlement>
        </SettlementReport>
        """
        entries = parser.parse(content, "partial.xml")
        # First element is skipped (no TransactionRef), second is valid
        assert len(entries) == 1
        assert entries[0].transaction_id == "TXN-002"

    def test_parse_xml_raw_data_stored(self, parser: XmlParser, xml_bytes: bytes):
        """Verify raw_data dict is populated for auditing."""
        entries = parser.parse(xml_bytes, "settlement_globalpay.xml")
        first = entries[0]
        assert first.raw_data is not None
        assert isinstance(first.raw_data, dict)
        assert "SettlementId" in first.raw_data
