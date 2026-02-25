"""Unit tests for the discrepancy detection rules.

All tests are *pure* — no database, no I/O.  We use SimpleNamespace to
create lightweight stand-ins with exactly the attributes each rule needs.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.reconciliation.rules import (
    FX_RATES_TO_USD,
    calculate_severity,
    detect_amount_mismatch,
    detect_currency_mismatch,
    detect_duplicate_settlement,
    detect_excessive_fee,
    detect_missing_settlement,
    to_usd,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_config(**overrides) -> Settings:
    """Build a Settings instance with sensible test defaults.

    We disable .env loading by providing the model_config inline,
    and override only the fields under test.
    """
    defaults = {
        "database_url": "sqlite://",
        "test_database_url": "sqlite://",
        "severity_critical_threshold": 1000.0,
        "severity_high_threshold": 100.0,
        "severity_medium_threshold": 10.0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _txn(**kwargs) -> SimpleNamespace:
    """Create a transaction-like object with sensible defaults."""
    defaults = {
        "transaction_id": "TXN-TEST-001",
        "amount": 1000.0,
        "expected_net_amount": 975.0,
        "expected_fee_percent": 2.5,
        "currency": "BRL",
        "processor_name": "PayFlow",
        "transaction_date": date(2024, 1, 15),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _stl(**kwargs) -> SimpleNamespace:
    """Create a settlement-like object with sensible defaults."""
    defaults = {
        "transaction_id": "TXN-TEST-001",
        "net_amount": 975.0,
        "gross_amount": 1000.0,
        "fee_amount": 25.0,
        "original_currency": "BRL",
        "settlement_currency": "USD",
        "fx_rate": None,
        "processor_name": "PayFlow",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── Amount mismatch ─────────────────────────────────────────────────


class TestDetectAmountMismatch:
    def test_triggers_when_beyond_tolerance(self) -> None:
        """Net amount differs beyond the tolerance -> discrepancy."""
        txn = _txn(expected_net_amount=1000.0)
        stl = _stl(net_amount=980.0)  # 2% off

        result = detect_amount_mismatch(txn, stl, tolerance_pct=0.01)

        assert result is not None
        assert result["type"] == "amount_mismatch"
        assert result["difference_amount"] == 20.0

    def test_within_tolerance_returns_none(self) -> None:
        """Small difference within tolerance -> no discrepancy."""
        txn = _txn(expected_net_amount=1000.0)
        stl = _stl(net_amount=999.95)  # 0.005% off

        result = detect_amount_mismatch(txn, stl, tolerance_pct=0.01)

        assert result is None


# ── Excessive fee ────────────────────────────────────────────────────


class TestDetectExcessiveFee:
    def test_triggers_when_fee_too_high(self) -> None:
        """Actual fee % exceeds expected + tolerance -> discrepancy."""
        txn = _txn(expected_fee_percent=2.5)
        stl = _stl(gross_amount=1000.0, fee_amount=50.0)  # 5.0% actual

        result = detect_excessive_fee(txn, stl, fee_tolerance_pct=0.5)

        assert result is not None
        assert result["type"] == "excessive_fee"
        # 5.0% actual vs 2.5% expected, excess = 2.5pp > 0.5pp tolerance
        assert result["actual_value"] == pytest.approx(5.0, rel=1e-2)

    def test_within_tolerance_returns_none(self) -> None:
        """Fee is normal (at or below expected + tolerance) -> no discrepancy."""
        txn = _txn(expected_fee_percent=2.5)
        stl = _stl(gross_amount=1000.0, fee_amount=28.0)  # 2.8% actual

        result = detect_excessive_fee(txn, stl, fee_tolerance_pct=0.5)

        assert result is None


# ── Missing settlement ───────────────────────────────────────────────


class TestDetectMissingSettlement:
    def test_triggers_past_threshold(self) -> None:
        """Transaction past threshold with no settlement -> discrepancy."""
        txn = _txn(transaction_date=date(2024, 1, 1))
        ref = date(2024, 1, 10)  # 9 days later

        result = detect_missing_settlement(txn, threshold_days=5, reference_date=ref)

        assert result is not None
        assert result["type"] == "missing_settlement"
        assert "9 days" in result["description"]

    def test_not_yet_due_returns_none(self) -> None:
        """Transaction within the grace period -> no discrepancy."""
        txn = _txn(transaction_date=date(2024, 1, 1))
        ref = date(2024, 1, 4)  # only 3 days later

        result = detect_missing_settlement(txn, threshold_days=5, reference_date=ref)

        assert result is None


# ── Duplicate settlement ─────────────────────────────────────────────


class TestDetectDuplicate:
    def test_triggers_for_two_settlements(self) -> None:
        """Two settlements for the same transaction_id -> discrepancy."""
        stl1 = _stl(net_amount=500.0, original_currency="BRL")
        stl2 = _stl(net_amount=500.0, original_currency="BRL")

        result = detect_duplicate_settlement("TXN-DUP-001", [stl1, stl2])

        assert result is not None
        assert result["type"] == "duplicate_settlement"
        assert result["actual_value"] == 1000.0

    def test_single_settlement_returns_none(self) -> None:
        """Only one settlement -> no duplicate."""
        stl = _stl()
        result = detect_duplicate_settlement("TXN-001", [stl])
        assert result is None


# ── Currency mismatch ────────────────────────────────────────────────


class TestDetectCurrencyMismatch:
    def test_triggers_when_fx_rate_deviates(self) -> None:
        """FX rate off by more than tolerance -> discrepancy."""
        txn = _txn(currency="COP")
        # Expected COP->USD rate is 0.00025, actual is 0.000266 (6.4% off)
        stl = _stl(fx_rate=0.000266, net_amount=1000000.0)

        result = detect_currency_mismatch(txn, stl, fx_tolerance_pct=2.0)

        assert result is not None
        assert result["type"] == "currency_mismatch"

    def test_within_tolerance_returns_none(self) -> None:
        """FX rate close to expected -> no discrepancy."""
        txn = _txn(currency="BRL")
        # Expected BRL->USD rate is 0.20, actual is 0.201 (0.5% off)
        stl = _stl(fx_rate=0.201, net_amount=1000.0)

        result = detect_currency_mismatch(txn, stl, fx_tolerance_pct=2.0)

        assert result is None

    def test_no_fx_rate_returns_none(self) -> None:
        """Settlement has no fx_rate -> skip check."""
        txn = _txn(currency="BRL")
        stl = _stl(fx_rate=None)

        result = detect_currency_mismatch(txn, stl, fx_tolerance_pct=2.0)

        assert result is None


# ── Severity calculation ─────────────────────────────────────────────


class TestCalculateSeverity:
    def test_critical(self) -> None:
        """Impact >= 1000 USD -> critical."""
        config = _make_config()
        assert calculate_severity(1500.0, config) == "critical"

    def test_high(self) -> None:
        """100 <= impact < 1000 -> high."""
        config = _make_config()
        assert calculate_severity(500.0, config) == "high"

    def test_medium(self) -> None:
        """10 <= impact < 100 -> medium."""
        config = _make_config()
        assert calculate_severity(50.0, config) == "medium"

    def test_low(self) -> None:
        """Impact < 10 USD -> low."""
        config = _make_config()
        assert calculate_severity(5.0, config) == "low"


# ── USD conversion ───────────────────────────────────────────────────


class TestToUsd:
    def test_brl_conversion(self) -> None:
        assert to_usd(100.0, "BRL") == pytest.approx(20.0)

    def test_mxn_conversion(self) -> None:
        assert to_usd(1000.0, "MXN") == pytest.approx(59.0)

    def test_cop_conversion(self) -> None:
        assert to_usd(4_000_000.0, "COP") == pytest.approx(1000.0)

    def test_clp_conversion(self) -> None:
        assert to_usd(1_000_000.0, "CLP") == pytest.approx(1100.0)

    def test_usd_passthrough(self) -> None:
        assert to_usd(42.0, "USD") == pytest.approx(42.0)

    def test_unknown_currency_defaults_to_1(self) -> None:
        """Unknown currency code uses rate=1.0 (treated as USD)."""
        assert to_usd(100.0, "ZZZ") == pytest.approx(100.0)
