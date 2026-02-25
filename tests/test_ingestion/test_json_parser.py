"""Tests for the TransactMax JSON parser.

These tests exercise parsing logic only — no database required.
"""

import json
import os
from decimal import Decimal

import pytest

from app.services.ingestion.json_parser import JsonParser

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"
)
JSON_FILE = os.path.join(DATA_DIR, "settlement_transactmax.json")


@pytest.fixture
def parser() -> JsonParser:
    return JsonParser()


@pytest.fixture
def json_bytes() -> bytes:
    with open(JSON_FILE, "rb") as f:
        return f.read()


# ------------------------------------------------------------------
# Happy-path tests
# ------------------------------------------------------------------


class TestParseValidJson:
    def test_parse_valid_json(self, parser: JsonParser, json_bytes: bytes):
        """Parse the real TransactMax JSON fixture and verify entries."""
        entries = parser.parse(json_bytes, "settlement_transactmax.json")
        assert len(entries) > 0
        for entry in entries:
            assert entry.processor_name == "TransactMax"
            assert entry.source_file == "settlement_transactmax.json"

    def test_parse_json_field_mapping(self, parser: JsonParser, json_bytes: bytes):
        """Verify JSON fields map to the correct schema fields."""
        entries = parser.parse(json_bytes, "settlement_transactmax.json")
        first = entries[0]

        # original_transaction_id -> transaction_id
        assert first.transaction_id is not None
        assert first.transaction_id == first.transaction_id.upper()

        # gross_amount -> gross_amount (Decimal)
        assert isinstance(first.gross_amount, Decimal)

        # total_fees -> fee_amount (Decimal)
        assert isinstance(first.fee_amount, Decimal)

        # net_amount
        assert isinstance(first.net_amount, Decimal)

        # currency -> original_currency
        assert first.original_currency is not None
        assert len(first.original_currency) == 3

        # settlement_date should be parsed
        assert first.settlement_date is not None

        # fee_breakdown is None for TransactMax
        assert first.fee_breakdown is None

    def test_parse_json_status_mapping(self, parser: JsonParser, json_bytes: bytes):
        """Verify status mapping: completed -> completed."""
        entries = parser.parse(json_bytes, "settlement_transactmax.json")
        statuses = {e.status for e in entries}
        assert "completed" in statuses


# ------------------------------------------------------------------
# Edge-case tests
# ------------------------------------------------------------------


class TestJsonEdgeCases:
    def test_parse_json_empty_settlements(self, parser: JsonParser):
        """Empty settlements list returns empty."""
        content = json.dumps(
            {"report_date": "2024-01-01", "processor": "TransactMax", "settlements": []}
        ).encode()
        entries = parser.parse(content, "empty.json")
        assert entries == []

    def test_parse_json_missing_fields(self, parser: JsonParser):
        """Entry with missing required field is skipped."""
        content = json.dumps(
            {
                "report_date": "2024-01-01",
                "processor": "TransactMax",
                "settlements": [
                    {
                        "id": "TM-001",
                        # missing original_transaction_id
                        "transaction_date": "2024-01-01",
                        "settlement_date": "2024-01-05",
                        "gross_amount": 100.0,
                        "currency": "BRL",
                        "total_fees": 3.0,
                        "net_amount": 97.0,
                        "settlement_status": "completed",
                    },
                    {
                        "id": "TM-002",
                        "original_transaction_id": "TXN-002",
                        "transaction_date": "2024-01-02",
                        "settlement_date": "2024-01-06",
                        "gross_amount": 200.0,
                        "currency": "MXN",
                        "total_fees": 6.0,
                        "net_amount": 194.0,
                        "settlement_status": "completed",
                    },
                ],
            }
        ).encode()
        entries = parser.parse(content, "partial.json")
        # First entry is skipped (no transaction ID), second is valid
        assert len(entries) == 1
        assert entries[0].transaction_id == "TXN-002"

    def test_parse_json_invalid_json(self, parser: JsonParser):
        """Completely invalid JSON returns empty list."""
        entries = parser.parse(b"NOT JSON {{{", "bad.json")
        assert entries == []

    def test_parse_json_missing_settlements_key(self, parser: JsonParser):
        """JSON without 'settlements' key returns empty list."""
        content = json.dumps({"report_date": "2024-01-01"}).encode()
        entries = parser.parse(content, "no_settlements.json")
        assert entries == []
