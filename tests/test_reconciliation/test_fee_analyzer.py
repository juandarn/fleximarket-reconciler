"""Tests for the FeeAnalyzer service.

Uses the SQLite-backed db_session fixture from conftest.py.
Inserts settlement entries directly via SQLAlchemy to test fee pattern
analysis and anomaly detection.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app.models.settlement import SettlementEntry
from app.services.reconciliation.fee_analyzer import FeeAnalyzer


@pytest.fixture
def analyzer() -> FeeAnalyzer:
    """Provide a fresh FeeAnalyzer instance."""
    return FeeAnalyzer()


def _make_entry(
    transaction_id: str,
    processor_name: str,
    original_currency: str,
    gross_amount: Decimal,
    fee_amount: Decimal,
    net_amount: Decimal | None = None,
    status: str = "completed",
) -> SettlementEntry:
    """Helper to build a SettlementEntry with sensible defaults."""
    if net_amount is None:
        net_amount = gross_amount - fee_amount
    return SettlementEntry(
        transaction_id=transaction_id,
        processor_name=processor_name,
        original_currency=original_currency,
        gross_amount=gross_amount,
        fee_amount=fee_amount,
        net_amount=net_amount,
        settlement_currency=original_currency,
        settlement_date=datetime(2025, 6, 15),
        status=status,
        source_file="test_fixture.csv",
    )


# ── Test: empty database ────────────────────────────────────────────


class TestFeePatterns:
    def test_fee_patterns_empty_db(self, db_session, analyzer):
        """No settlement data → empty patterns dict."""
        patterns = analyzer.analyze_fee_patterns(db_session)
        assert patterns == {}

    def test_fee_patterns_with_data(self, db_session, analyzer):
        """Insert entries for two processors, verify avg/std are computed."""
        # PayFlow BRL: fees at 2.5% of gross (100 * 0.025 = 2.50)
        entries = [
            _make_entry("PF-001", "PayFlow", "BRL", Decimal("100.00"), Decimal("2.50")),
            _make_entry("PF-002", "PayFlow", "BRL", Decimal("200.00"), Decimal("5.00")),
            _make_entry("PF-003", "PayFlow", "BRL", Decimal("150.00"), Decimal("3.75")),
            # TransactMax MXN: fees at ~3.0%
            _make_entry(
                "TM-001", "TransactMax", "MXN", Decimal("500.00"), Decimal("15.00")
            ),
            _make_entry(
                "TM-002", "TransactMax", "MXN", Decimal("300.00"), Decimal("9.00")
            ),
        ]
        db_session.add_all(entries)
        db_session.commit()

        patterns = analyzer.analyze_fee_patterns(db_session)

        # PayFlow BRL: all exactly 2.5%, so std_dev should be 0
        assert "PayFlow" in patterns
        assert "BRL" in patterns["PayFlow"]
        pf_brl = patterns["PayFlow"]["BRL"]
        assert pf_brl["avg_fee_pct"] == 2.5
        assert pf_brl["std_dev"] == 0.0
        assert pf_brl["sample_count"] == 3

        # TransactMax MXN: all exactly 3.0%, so std_dev should be 0
        assert "TransactMax" in patterns
        assert "MXN" in patterns["TransactMax"]
        tm_mxn = patterns["TransactMax"]["MXN"]
        assert tm_mxn["avg_fee_pct"] == 3.0
        assert tm_mxn["std_dev"] == 0.0
        assert tm_mxn["sample_count"] == 2

    def test_fee_patterns_ignores_zero_gross(self, db_session, analyzer):
        """Entries with gross_amount = 0 should be excluded."""
        entry = _make_entry(
            "ZERO-001",
            "PayFlow",
            "BRL",
            Decimal("0.00"),
            Decimal("0.00"),
            net_amount=Decimal("0.00"),
        )
        db_session.add(entry)
        db_session.commit()

        patterns = analyzer.analyze_fee_patterns(db_session)
        assert patterns == {}


# ── Test: anomaly detection ─────────────────────────────────────────


class TestDetectUnusualFees:
    def test_detect_unusual_fees(self, db_session, analyzer):
        """One outlier fee should be flagged among otherwise uniform entries."""
        # Normal entries: fee = 2.5% of gross
        normal_entries = [
            _make_entry(
                f"PF-{i:03d}", "PayFlow", "BRL", Decimal("1000.00"), Decimal("25.00")
            )
            for i in range(1, 11)
        ]
        # Outlier: fee = 8% of gross (way above 2.5%)
        outlier = _make_entry(
            "PF-OUTLIER",
            "PayFlow",
            "BRL",
            Decimal("1000.00"),
            Decimal("80.00"),
        )
        db_session.add_all(normal_entries + [outlier])
        db_session.commit()

        unusual = analyzer.detect_unusual_fees(db_session, std_dev_threshold=2.0)

        # The outlier should be flagged
        assert len(unusual) >= 1
        outlier_ids = [u["transaction_id"] for u in unusual]
        assert "PF-OUTLIER" in outlier_ids

        # Verify shape of returned data
        flagged = next(u for u in unusual if u["transaction_id"] == "PF-OUTLIER")
        assert flagged["processor"] == "PayFlow"
        assert flagged["currency"] == "BRL"
        assert flagged["actual_fee_pct"] == 8.0
        assert flagged["deviation_score"] > 2.0

    def test_detect_no_anomalies(self, db_session, analyzer):
        """When all fees are identical, nothing should be flagged."""
        entries = [
            _make_entry(
                f"GP-{i:03d}",
                "GlobalPay",
                "COP",
                Decimal("2000.00"),
                Decimal("56.00"),
            )
            for i in range(1, 6)
        ]
        db_session.add_all(entries)
        db_session.commit()

        unusual = analyzer.detect_unusual_fees(db_session, std_dev_threshold=2.0)
        assert unusual == []

    def test_detect_unusual_fees_empty_db(self, db_session, analyzer):
        """Empty database → no anomalies."""
        unusual = analyzer.detect_unusual_fees(db_session)
        assert unusual == []


# ── Test: full report ───────────────────────────────────────────────


class TestGetFeeReport:
    def test_get_fee_report_structure(self, db_session, analyzer):
        """Report should contain the expected top-level keys."""
        report = analyzer.get_fee_report(db_session)
        assert "fee_patterns" in report
        assert "unusual_fees" in report
        assert "threshold_std_devs" in report
        assert report["threshold_std_devs"] == 2.0

    def test_get_fee_report_with_data(self, db_session, analyzer):
        """Full report with data should populate both patterns and anomalies."""
        # Mix of normal + outlier
        entries = [
            _make_entry(
                f"N-{i:03d}", "PayFlow", "BRL", Decimal("500.00"), Decimal("12.50")
            )
            for i in range(1, 8)
        ]
        outlier = _make_entry(
            "N-OUTLIER",
            "PayFlow",
            "BRL",
            Decimal("500.00"),
            Decimal("50.00"),  # 10% vs normal 2.5%
        )
        db_session.add_all(entries + [outlier])
        db_session.commit()

        report = analyzer.get_fee_report(db_session)

        assert "PayFlow" in report["fee_patterns"]
        assert len(report["unusual_fees"]) >= 1
