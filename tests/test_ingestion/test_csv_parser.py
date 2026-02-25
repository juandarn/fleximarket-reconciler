"""Tests for the PayFlow CSV parser.

These tests exercise parsing logic only — no database required.
They read from the real data/ fixtures and verify SettlementCreate objects.
"""

import os
from decimal import Decimal

import pytest

from app.services.ingestion.csv_parser import CsvParser

# Resolve path to data/ directory relative to this test file
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"
)
CSV_FILE = os.path.join(DATA_DIR, "settlement_payflow.csv")


@pytest.fixture
def parser() -> CsvParser:
    return CsvParser()


@pytest.fixture
def csv_bytes() -> bytes:
    with open(CSV_FILE, "rb") as f:
        return f.read()


# ------------------------------------------------------------------
# Happy-path tests
# ------------------------------------------------------------------


class TestParseValidCsv:
    """Parse the real settlement_payflow.csv and verify entries returned."""

    def test_parse_valid_csv(self, parser: CsvParser, csv_bytes: bytes):
        entries = parser.parse(csv_bytes, "settlement_payflow.csv")
        # The CSV has a header + data rows; should return at least 1 entry
        assert len(entries) > 0
        # Every entry should be a SettlementCreate with processor_name set
        for entry in entries:
            assert entry.processor_name == "PayFlow"
            assert entry.source_file == "settlement_payflow.csv"

    def test_parse_csv_field_mapping(self, parser: CsvParser, csv_bytes: bytes):
        """Verify that CSV columns map to the correct schema fields."""
        entries = parser.parse(csv_bytes, "settlement_payflow.csv")
        first = entries[0]

        # transaction_ref -> transaction_id (uppercased)
        assert first.transaction_id is not None
        assert first.transaction_id == first.transaction_id.upper()

        # original_amount -> gross_amount (Decimal)
        assert isinstance(first.gross_amount, Decimal)

        # net_amount -> net_amount (Decimal)
        assert isinstance(first.net_amount, Decimal)

        # currency -> original_currency (3-letter uppercase)
        assert first.original_currency is not None
        assert len(first.original_currency) == 3

        # settlement_date should be parsed
        assert first.settlement_date is not None

        # fx_rate is None for PayFlow
        assert first.fx_rate is None

    def test_parse_csv_fee_breakdown(self, parser: CsvParser, csv_bytes: bytes):
        """Verify fee_breakdown contains processing + interchange."""
        entries = parser.parse(csv_bytes, "settlement_payflow.csv")
        first = entries[0]

        assert first.fee_breakdown is not None
        assert "processing" in first.fee_breakdown
        assert "interchange" in first.fee_breakdown

        # fee_amount should equal processing + interchange
        assert first.fee_amount is not None
        expected_fee = Decimal(str(first.fee_breakdown["processing"])) + Decimal(
            str(first.fee_breakdown["interchange"])
        )
        assert first.fee_amount == expected_fee

    def test_parse_csv_status_mapping(self, parser: CsvParser, csv_bytes: bytes):
        """Verify SETTLED -> completed mapping."""
        entries = parser.parse(csv_bytes, "settlement_payflow.csv")
        # Find entries with various statuses
        statuses = {e.status for e in entries}
        # The fixture uses SETTLED, so 'completed' should be present
        assert "completed" in statuses


# ------------------------------------------------------------------
# Edge-case tests
# ------------------------------------------------------------------


class TestCsvEdgeCases:
    def test_parse_csv_empty_file(self, parser: CsvParser):
        """Empty file should return an empty list, not crash."""
        entries = parser.parse(b"", "empty.csv")
        assert entries == []

    def test_parse_csv_header_only(self, parser: CsvParser):
        """File with only a header row returns an empty list."""
        header = b"settlement_id,transaction_ref,txn_date,settle_date,original_amount,currency,processing_fee,interchange_fee,net_amount,status\n"
        entries = parser.parse(header, "header_only.csv")
        assert entries == []

    def test_parse_csv_malformed_row(self, parser: CsvParser):
        """A row with bad data is skipped, not crash."""
        content = (
            b"settlement_id,transaction_ref,txn_date,settle_date,original_amount,"
            b"currency,processing_fee,interchange_fee,net_amount,status\n"
            b"PF-001,TXN-001,2024-01-01,2024-01-04,100.00,BRL,1.50,1.00,97.50,SETTLED\n"
            b"PF-002,,bad-date,bad-date,NOT_A_NUMBER,XXX,bad,bad,bad,UNKNOWN\n"
            b"PF-003,TXN-003,2024-01-02,2024-01-05,200.00,MXN,3.00,2.00,195.00,SETTLED\n"
        )
        entries = parser.parse(content, "malformed.csv")
        # Row 2 has empty transaction_ref so it's skipped; rows 1 and 3 pass
        assert len(entries) == 2
        assert entries[0].transaction_id == "TXN-001"
        assert entries[1].transaction_id == "TXN-003"
