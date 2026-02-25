"""Tests for the CurrencyReporter service.

Uses the SQLite-backed db_session fixture from conftest.py.
Inserts Discrepancy records directly to test aggregation and currency
conversion logic.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.discrepancy import Discrepancy
from app.services.reconciliation.currency_reporter import CurrencyReporter


@pytest.fixture
def reporter() -> CurrencyReporter:
    """Provide a fresh CurrencyReporter instance."""
    return CurrencyReporter()


def _make_discrepancy(
    transaction_id: str,
    disc_type: str = "amount_mismatch",
    severity: str = "medium",
    processor_name: str = "PayFlow",
    difference_amount: Decimal | None = Decimal("100.00"),
    difference_currency: str = "BRL",
    impact_usd: Decimal | None = Decimal("20.00"),
) -> Discrepancy:
    """Helper to build a Discrepancy with sensible defaults."""
    return Discrepancy(
        id=uuid.uuid4(),
        transaction_id=transaction_id,
        type=disc_type,
        severity=severity,
        processor_name=processor_name,
        difference_amount=difference_amount,
        difference_currency=difference_currency,
        impact_usd=impact_usd,
    )


# ── Test: empty database ────────────────────────────────────────────


class TestEmptyDatabase:
    def test_empty_db_returns_zeros(self, db_session, reporter):
        """No discrepancies → zero totals, empty aggregation dicts."""
        result = reporter.get_multi_currency_report(db_session)

        assert result["target_currency"] == "USD"
        assert result["total_impact"] == 0.0
        assert result["by_processor"] == {}
        assert result["by_type"] == {}
        assert result["by_original_currency"] == {}
        assert result["discrepancies"] == []


# ── Test: report with discrepancies ──────────────────────────────────


class TestReportWithDiscrepancies:
    def test_report_aggregates_totals(self, db_session, reporter):
        """Insert several discrepancies and verify total_impact sums up."""
        records = [
            _make_discrepancy("TXN-001", impact_usd=Decimal("20.00")),
            _make_discrepancy("TXN-002", impact_usd=Decimal("30.00")),
            _make_discrepancy("TXN-003", impact_usd=Decimal("50.00")),
        ]
        db_session.add_all(records)
        db_session.commit()

        result = reporter.get_multi_currency_report(db_session)

        assert result["total_impact"] == 100.0
        assert len(result["discrepancies"]) == 3

    def test_report_item_shape(self, db_session, reporter):
        """Each item in the discrepancies list has the expected keys."""
        db_session.add(
            _make_discrepancy(
                "TXN-100",
                disc_type="excessive_fee",
                severity="high",
                processor_name="GlobalPay",
                difference_amount=Decimal("500.00"),
                difference_currency="MXN",
                impact_usd=Decimal("29.50"),
            )
        )
        db_session.commit()

        result = reporter.get_multi_currency_report(db_session)
        item = result["discrepancies"][0]

        assert item["transaction_id"] == "TXN-100"
        assert item["type"] == "excessive_fee"
        assert item["processor"] == "GlobalPay"
        assert item["original_amount"] == 500.0
        assert item["original_currency"] == "MXN"
        assert item["impact_usd"] == 29.5
        assert item["severity"] == "high"

    def test_report_falls_back_to_conversion(self, db_session, reporter):
        """When impact_usd is None, to_usd should be used instead."""
        db_session.add(
            _make_discrepancy(
                "TXN-CONVERT",
                difference_amount=Decimal("1000.00"),
                difference_currency="BRL",
                impact_usd=None,  # force conversion path
            )
        )
        db_session.commit()

        result = reporter.get_multi_currency_report(db_session)
        item = result["discrepancies"][0]

        # BRL rate is 0.20, so 1000 BRL → 200 USD
        assert item["impact_usd"] == 200.0
        assert result["total_impact"] == 200.0


# ── Test: by_processor grouping ──────────────────────────────────────


class TestByProcessor:
    def test_report_by_processor(self, db_session, reporter):
        """Verify aggregation groups by processor correctly."""
        records = [
            _make_discrepancy(
                "PF-001", processor_name="PayFlow", impact_usd=Decimal("10.00")
            ),
            _make_discrepancy(
                "PF-002", processor_name="PayFlow", impact_usd=Decimal("15.00")
            ),
            _make_discrepancy(
                "TM-001", processor_name="TransactMax", impact_usd=Decimal("25.00")
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        result = reporter.get_multi_currency_report(db_session)
        by_proc = result["by_processor"]

        assert "PayFlow" in by_proc
        assert by_proc["PayFlow"]["count"] == 2
        assert by_proc["PayFlow"]["total_impact_usd"] == 25.0

        assert "TransactMax" in by_proc
        assert by_proc["TransactMax"]["count"] == 1
        assert by_proc["TransactMax"]["total_impact_usd"] == 25.0


# ── Test: by_type grouping ───────────────────────────────────────────


class TestByType:
    def test_report_by_type(self, db_session, reporter):
        """Verify aggregation groups by discrepancy type."""
        records = [
            _make_discrepancy(
                "A-001", disc_type="amount_mismatch", impact_usd=Decimal("10.00")
            ),
            _make_discrepancy(
                "A-002", disc_type="amount_mismatch", impact_usd=Decimal("20.00")
            ),
            _make_discrepancy(
                "F-001", disc_type="excessive_fee", impact_usd=Decimal("5.00")
            ),
            _make_discrepancy(
                "M-001", disc_type="missing_settlement", impact_usd=Decimal("40.00")
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        result = reporter.get_multi_currency_report(db_session)
        by_type = result["by_type"]

        assert by_type["amount_mismatch"]["count"] == 2
        assert by_type["amount_mismatch"]["total_impact_usd"] == 30.0
        assert by_type["excessive_fee"]["count"] == 1
        assert by_type["excessive_fee"]["total_impact_usd"] == 5.0
        assert by_type["missing_settlement"]["count"] == 1
        assert by_type["missing_settlement"]["total_impact_usd"] == 40.0


# ── Test: by_original_currency grouping ──────────────────────────────


class TestByCurrency:
    def test_report_by_original_currency(self, db_session, reporter):
        """Verify per-currency aggregation including local totals."""
        records = [
            _make_discrepancy(
                "BRL-001",
                difference_amount=Decimal("500.00"),
                difference_currency="BRL",
                impact_usd=Decimal("100.00"),
            ),
            _make_discrepancy(
                "BRL-002",
                difference_amount=Decimal("300.00"),
                difference_currency="BRL",
                impact_usd=Decimal("60.00"),
            ),
            _make_discrepancy(
                "MXN-001",
                difference_amount=Decimal("1000.00"),
                difference_currency="MXN",
                impact_usd=Decimal("59.00"),
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        result = reporter.get_multi_currency_report(db_session)
        by_curr = result["by_original_currency"]

        assert "BRL" in by_curr
        assert by_curr["BRL"]["count"] == 2
        assert by_curr["BRL"]["total_impact_usd"] == 160.0
        assert by_curr["BRL"]["total_impact_local"] == 800.0

        assert "MXN" in by_curr
        assert by_curr["MXN"]["count"] == 1
        assert by_curr["MXN"]["total_impact_usd"] == 59.0
        assert by_curr["MXN"]["total_impact_local"] == 1000.0
