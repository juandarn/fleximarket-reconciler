"""Tests for the normalizer utility functions.

The normalizer handles the messy reality of multi-processor data:
inconsistent date formats, currency symbols vs codes, processor-specific
status labels, and transaction ID cleanup.

These are pure functions -- no database, no I/O.
"""

from datetime import datetime

import pytest

from app.services.ingestion.normalizer import (
    normalize_currency,
    normalize_date,
    normalize_status,
    normalize_transaction_id,
)


# ==================================================================
# Currency normalization
# ==================================================================


class TestNormalizeCurrency:
    """Test normalize_currency() with ISO codes, aliases, and edge cases."""

    # -- Standard ISO codes --

    @pytest.mark.parametrize(
        "input_code, expected",
        [
            ("BRL", "BRL"),
            ("MXN", "MXN"),
            ("COP", "COP"),
            ("CLP", "CLP"),
            ("USD", "USD"),
            ("EUR", "EUR"),
            ("GBP", "GBP"),
            ("ARS", "ARS"),
        ],
    )
    def test_standard_iso_codes(self, input_code: str, expected: str):
        """Standard 3-letter ISO codes should pass through uppercased."""
        assert normalize_currency(input_code) == expected

    # -- Case insensitivity --

    @pytest.mark.parametrize(
        "input_code, expected",
        [
            ("brl", "BRL"),
            ("mxn", "MXN"),
            ("cop", "COP"),
            ("Usd", "USD"),
        ],
    )
    def test_case_insensitive(self, input_code: str, expected: str):
        """Currency codes should be case-insensitive."""
        assert normalize_currency(input_code) == expected

    # -- Symbol aliases --

    def test_real_sign_to_brl(self):
        """Brazilian Real symbol R$ should normalize to BRL."""
        assert normalize_currency("R$") == "BRL"

    def test_dollar_sign_to_usd(self):
        """Dollar sign $ should normalize to USD."""
        assert normalize_currency("$") == "USD"

    def test_mx_dollar_to_mxn(self):
        """Mexican pesos symbol MX$ should normalize to MXN."""
        assert normalize_currency("MX$") == "MXN"

    # -- Whitespace handling --

    def test_strips_whitespace(self):
        """Leading/trailing whitespace should be stripped."""
        assert normalize_currency("  BRL  ") == "BRL"
        assert normalize_currency("\tMXN\n") == "MXN"

    # -- Unknown 3-letter codes fallback --

    def test_unknown_three_letter_code_uppercased(self):
        """Unknown 3-letter alpha codes are accepted and uppercased."""
        assert normalize_currency("xyz") == "XYZ"
        assert normalize_currency("pen") == "PEN"

    # -- Invalid codes --

    def test_invalid_code_raises(self):
        """Non-3-letter, non-alias codes should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown currency"):
            normalize_currency("DOLLAR")

    def test_empty_string_raises(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown currency"):
            normalize_currency("")

    def test_numeric_code_raises(self):
        """Numeric strings should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown currency"):
            normalize_currency("986")


# ==================================================================
# Date normalization
# ==================================================================


class TestNormalizeDate:
    """Test normalize_date() with the 8 supported date formats."""

    # -- ISO formats --

    def test_iso_datetime_with_microseconds(self):
        """Format: 2024-01-15T10:30:45.123456"""
        result = normalize_date("2024-01-15T10:30:45.123456")
        assert result == datetime(2024, 1, 15, 10, 30, 45, 123456)

    def test_iso_datetime_without_microseconds(self):
        """Format: 2024-01-15T10:30:45"""
        result = normalize_date("2024-01-15T10:30:45")
        assert result == datetime(2024, 1, 15, 10, 30, 45)

    def test_iso_datetime_with_space(self):
        """Format: 2024-01-15 10:30:45"""
        result = normalize_date("2024-01-15 10:30:45")
        assert result == datetime(2024, 1, 15, 10, 30, 45)

    def test_iso_date_only(self):
        """Format: 2024-01-15"""
        result = normalize_date("2024-01-15")
        assert result == datetime(2024, 1, 15, 0, 0, 0)

    # -- European/LATAM formats --

    def test_dd_mm_yyyy_with_time(self):
        """Format: 15/01/2024 10:30:45"""
        result = normalize_date("15/01/2024 10:30:45")
        assert result == datetime(2024, 1, 15, 10, 30, 45)

    def test_dd_mm_yyyy_date_only(self):
        """Format: 15/01/2024"""
        result = normalize_date("15/01/2024")
        assert result == datetime(2024, 1, 15, 0, 0, 0)

    # -- US format --

    def test_mm_dd_yyyy(self):
        """Format: 01/15/2024 (US-style month first)."""
        result = normalize_date("01/15/2024")
        assert result == datetime(2024, 1, 15, 0, 0, 0)

    # -- Dashes european --

    def test_dd_dash_mm_dash_yyyy(self):
        """Format: 15-01-2024"""
        result = normalize_date("15-01-2024")
        assert result == datetime(2024, 1, 15, 0, 0, 0)

    # -- Edge cases --

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace should be stripped before parsing."""
        result = normalize_date("  2024-01-15  ")
        assert result == datetime(2024, 1, 15, 0, 0, 0)

    def test_unparseable_returns_none(self):
        """Strings that match no format should return None."""
        assert normalize_date("not-a-date") is None
        assert normalize_date("") is None

    def test_garbage_string_returns_none(self):
        """Random garbage should not crash, just return None."""
        assert normalize_date("abc123xyz") is None

    def test_partial_date_returns_none(self):
        """Incomplete dates should return None."""
        assert normalize_date("2024-01") is None


# ==================================================================
# Status normalization
# ==================================================================


class TestNormalizeStatus:
    """Test normalize_status() for all three processors."""

    # -- PayFlow statuses --

    @pytest.mark.parametrize(
        "raw_status, expected",
        [
            ("SETTLED", "completed"),
            ("FAILED", "failed"),
            ("HELD", "held"),
            ("REVERSED", "reversed"),
        ],
    )
    def test_payflow_statuses(self, raw_status: str, expected: str):
        assert normalize_status(raw_status, "payflow") == expected

    # -- TransactMax statuses --

    @pytest.mark.parametrize(
        "raw_status, expected",
        [
            ("completed", "completed"),
            ("failed", "failed"),
            ("held", "held"),
            ("reversed", "reversed"),
            ("on_hold", "held"),
        ],
    )
    def test_transactmax_statuses(self, raw_status: str, expected: str):
        assert normalize_status(raw_status, "transactmax") == expected

    # -- GlobalPay statuses --

    @pytest.mark.parametrize(
        "raw_status, expected",
        [
            ("COMPLETED", "completed"),
            ("FAILED", "failed"),
            ("ON_HOLD", "held"),
            ("REVERSED", "reversed"),
        ],
    )
    def test_globalpay_statuses(self, raw_status: str, expected: str):
        assert normalize_status(raw_status, "globalpay") == expected

    # -- Case-insensitive processor name --

    def test_processor_name_case_insensitive(self):
        """Processor name matching should be case-insensitive."""
        assert normalize_status("SETTLED", "PayFlow") == "completed"
        assert normalize_status("SETTLED", "PAYFLOW") == "completed"
        assert normalize_status("SETTLED", "payflow") == "completed"

    # -- Case-insensitive status fallback --

    def test_status_case_insensitive_fallback(self):
        """Status matching should try case-insensitive as a fallback."""
        assert normalize_status("settled", "payflow") == "completed"
        assert normalize_status("Settled", "payflow") == "completed"

    # -- Whitespace handling --

    def test_strips_whitespace(self):
        """Whitespace on processor name and status should be stripped."""
        assert normalize_status("  SETTLED  ", "  payflow  ") == "completed"

    # -- Unknown statuses --

    def test_unknown_status_returns_lowercase(self):
        """Unknown status falls back to lowercased original string."""
        assert normalize_status("WEIRD_STATUS", "payflow") == "weird_status"

    def test_unknown_processor_returns_lowercase_status(self):
        """Unknown processor falls back to lowercased original status."""
        assert normalize_status("ACTIVE", "unknown_proc") == "active"


# ==================================================================
# Transaction ID normalization
# ==================================================================


class TestNormalizeTransactionId:
    """Test normalize_transaction_id() for uppercasing and stripping."""

    def test_uppercase(self):
        """IDs should be uppercased."""
        assert normalize_transaction_id("txn-br-2024-000001") == "TXN-BR-2024-000001"

    def test_already_upper(self):
        """Already uppercase IDs should pass through unchanged."""
        assert normalize_transaction_id("TXN-MX-2024-000042") == "TXN-MX-2024-000042"

    def test_mixed_case(self):
        """Mixed case should be uppercased."""
        assert normalize_transaction_id("Txn-Co-2024-000099") == "TXN-CO-2024-000099"

    def test_strips_whitespace(self):
        """Leading/trailing whitespace should be removed."""
        assert (
            normalize_transaction_id("  TXN-BR-2024-000001  ") == "TXN-BR-2024-000001"
        )

    def test_tabs_and_newlines(self):
        """Tabs and newlines should be stripped."""
        assert (
            normalize_transaction_id("\tTXN-CL-2024-000010\n") == "TXN-CL-2024-000010"
        )


# ==================================================================
# Cross-cutting: data fixture validation via normalizer
# ==================================================================


class TestNormalizerWithFixtureData:
    """Verify normalizer works correctly on real data from our fixtures.

    This is an integration-level check: we load the generated data files
    and confirm that the normalizer handles all real values gracefully.
    """

    @pytest.fixture
    def expected_transactions(self):
        import json
        import os

        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"
        )
        with open(os.path.join(data_dir, "expected_transactions.json")) as f:
            return json.load(f)

    def test_all_fixture_currencies_normalize(self, expected_transactions):
        """Every currency in our fixture data should normalize cleanly."""
        for txn in expected_transactions:
            result = normalize_currency(txn["currency"])
            assert result in {"BRL", "MXN", "COP", "CLP"}

    def test_all_fixture_dates_normalize(self, expected_transactions):
        """Every transaction_date in fixtures should parse successfully."""
        for txn in expected_transactions:
            result = normalize_date(txn["transaction_date"])
            assert result is not None, (
                f"Failed to parse date: {txn['transaction_date']}"
            )

    def test_all_fixture_transaction_ids_normalize(self, expected_transactions):
        """Every transaction_id should normalize to an uppercase string."""
        for txn in expected_transactions:
            result = normalize_transaction_id(txn["transaction_id"])
            assert result == result.upper()
            assert len(result) > 0
