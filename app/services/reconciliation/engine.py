"""Reconciliation engine — the HEART of the system.

The engine orchestrates a full reconciliation run:
  1. Record a new report (status=running).
  2. Fetch expected transactions and settlement entries from the DB.
  3. Match them together by transaction_id.
  4. Run every detection rule on matched pairs, orphans, and duplicates.
  5. Persist discrepancies, update the report, and return it.

Think of this like an auditor going through two stacks of paper —
one from our system and one from the bank — and flagging every mismatch.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.discrepancy import Discrepancy
from app.models.reconciliation import ReconciliationReport
from app.models.settlement import SettlementEntry
from app.models.transaction import ExpectedTransaction
from app.services.reconciliation.matcher import TransactionMatcher
from app.services.reconciliation.rules import (
    calculate_severity,
    detect_amount_mismatch,
    detect_currency_mismatch,
    detect_duplicate_settlement,
    detect_excessive_fee,
    detect_missing_settlement,
    to_usd,
)

logger = get_logger(__name__)


class ReconciliationEngine:
    """Runs a full reconciliation cycle for a given date range."""

    def __init__(self, db: Session, config: Settings) -> None:
        self.db = db
        self.config = config
        self.matcher = TransactionMatcher()

    # ── Public API ───────────────────────────────────────────────────

    def run(
        self,
        date_from: date,
        date_to: date,
        processors: Optional[list[str]] = None,
    ) -> ReconciliationReport:
        """Execute a full reconciliation run.

        Args:
            date_from: Start of the date range (inclusive).
            date_to: End of the date range (inclusive).
            processors: If provided, limit to these processor names.

        Returns:
            A persisted ``ReconciliationReport`` with linked discrepancies.
        """
        # 1. Create report record (status=running)
        report = self._create_report(date_from, date_to)
        logger.info(
            "Reconciliation run started: id=%s range=%s..%s",
            report.id,
            date_from,
            date_to,
        )

        try:
            # 2. Fetch source data
            transactions = self._fetch_transactions(date_from, date_to, processors)
            settlements = self._fetch_settlements(date_from, date_to, processors)

            logger.info(
                "Data loaded: transactions=%d settlements=%d",
                len(transactions),
                len(settlements),
            )

            # 3. Match
            match_result = self.matcher.match(transactions, settlements)

            # 4 + 5. Detect discrepancies
            discrepancy_dicts: list[dict] = []

            # 4a. Check matched pairs for amount/fee/currency issues
            for txn, stl in match_result.matched:
                self._check_matched_pair(txn, stl, discrepancy_dicts)

            # 4b. Missing settlements
            reference_date = date_to
            for txn in match_result.unmatched_transactions:
                disc = detect_missing_settlement(
                    txn,
                    self.config.settlement_delay_threshold_days,
                    reference_date,
                )
                if disc:
                    discrepancy_dicts.append(disc)

            # 4c. Duplicates
            for txn_id, dup_settlements in match_result.duplicates.items():
                disc = detect_duplicate_settlement(txn_id, dup_settlements)
                if disc:
                    discrepancy_dicts.append(disc)

            # 6. Calculate severity and impact for each discrepancy
            for d in discrepancy_dicts:
                impact = d.get("impact_usd") or 0.0
                d["severity"] = calculate_severity(impact, self.config)

            # 7. Persist discrepancies
            db_discrepancies = self._save_discrepancies(discrepancy_dicts, report.id)

            # 8. Update report with summary stats
            self._finalize_report(
                report,
                transactions,
                settlements,
                match_result,
                db_discrepancies,
            )

            logger.info(
                "Reconciliation complete: id=%s discrepancies=%d",
                report.id,
                len(db_discrepancies),
            )

        except Exception:
            report.status = "failed"
            report.completed_at = datetime.utcnow()
            self.db.commit()
            logger.exception("Reconciliation run failed: id=%s", report.id)
            raise

        return report

    # ── Private helpers ──────────────────────────────────────────────

    def _create_report(self, date_from: date, date_to: date) -> ReconciliationReport:
        """Insert a new report row with status='running'."""
        report = ReconciliationReport(
            id=uuid.uuid4(),
            started_at=datetime.utcnow(),
            date_range_start=date_from,
            date_range_end=date_to,
            status="running",
        )
        self.db.add(report)
        self.db.flush()
        return report

    def _fetch_transactions(
        self,
        date_from: date,
        date_to: date,
        processors: Optional[list[str]],
    ) -> list[ExpectedTransaction]:
        """Load expected transactions (status=captured) in the date range."""
        query = (
            self.db.query(ExpectedTransaction)
            .filter(ExpectedTransaction.status == "captured")
            .filter(
                ExpectedTransaction.transaction_date
                >= datetime(date_from.year, date_from.month, date_from.day)
            )
            .filter(
                ExpectedTransaction.transaction_date
                <= datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59)
            )
        )
        if processors:
            query = query.filter(ExpectedTransaction.processor_name.in_(processors))
        return query.all()

    def _fetch_settlements(
        self,
        date_from: date,
        date_to: date,
        processors: Optional[list[str]],
    ) -> list[SettlementEntry]:
        """Load settlement entries in the date range."""
        query = (
            self.db.query(SettlementEntry)
            .filter(
                SettlementEntry.settlement_date
                >= datetime(date_from.year, date_from.month, date_from.day)
            )
            .filter(
                SettlementEntry.settlement_date
                <= datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59)
            )
        )
        if processors:
            query = query.filter(SettlementEntry.processor_name.in_(processors))
        return query.all()

    def _check_matched_pair(
        self,
        txn: ExpectedTransaction,
        stl: SettlementEntry,
        out: list[dict],
    ) -> None:
        """Run all matched-pair rules and append any discrepancies to *out*."""
        disc = detect_amount_mismatch(txn, stl, self.config.amount_tolerance_percent)
        if disc:
            out.append(disc)

        disc = detect_excessive_fee(txn, stl, self.config.fee_tolerance_percent)
        if disc:
            out.append(disc)

        disc = detect_currency_mismatch(txn, stl, self.config.fx_rate_tolerance_percent)
        if disc:
            out.append(disc)

    def _save_discrepancies(
        self,
        disc_dicts: list[dict],
        report_id: uuid.UUID,
    ) -> list[Discrepancy]:
        """Convert raw dicts to ORM objects and persist them."""
        db_objects: list[Discrepancy] = []
        for d in disc_dicts:
            obj = Discrepancy(
                id=uuid.uuid4(),
                transaction_id=d["transaction_id"],
                type=d["type"],
                severity=d["severity"],
                expected_value=d.get("expected_value"),
                actual_value=d.get("actual_value"),
                difference_amount=d.get("difference_amount"),
                difference_currency=d.get("difference_currency"),
                impact_usd=d.get("impact_usd"),
                processor_name=d.get("processor_name"),
                description=d.get("description"),
                reconciliation_report_id=report_id,
            )
            self.db.add(obj)
            db_objects.append(obj)

        self.db.flush()
        return db_objects

    def _finalize_report(
        self,
        report: ReconciliationReport,
        transactions: list[ExpectedTransaction],
        settlements: list[SettlementEntry],
        match_result,
        discrepancies: list[Discrepancy],
    ) -> None:
        """Fill in the report summary fields and mark it completed."""
        # Compute totals in USD
        total_expected_usd = Decimal(0)
        for txn in transactions:
            amt = float(txn.expected_net_amount or txn.amount or 0)
            total_expected_usd += Decimal(str(to_usd(amt, txn.currency)))

        total_settled_usd = Decimal(0)
        for stl in settlements:
            amt = float(stl.net_amount or 0)
            currency = stl.original_currency or stl.settlement_currency or "USD"
            total_settled_usd += Decimal(str(to_usd(amt, currency)))

        total_disc_usd = sum(Decimal(str(d.impact_usd or 0)) for d in discrepancies)

        # Count missing
        missing_count = sum(1 for d in discrepancies if d.type == "missing_settlement")

        # Build summary breakdown
        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_processor: dict[str, int] = {}
        for d in discrepancies:
            by_type[d.type] = by_type.get(d.type, 0) + 1
            by_severity[d.severity] = by_severity.get(d.severity, 0) + 1
            if d.processor_name:
                by_processor[d.processor_name] = (
                    by_processor.get(d.processor_name, 0) + 1
                )

        report.completed_at = datetime.utcnow()
        report.status = "completed"
        report.total_transactions = len(transactions)
        report.matched_count = len(match_result.matched)
        report.discrepancy_count = len(discrepancies)
        report.missing_count = missing_count
        report.total_expected_amount_usd = total_expected_usd
        report.total_settled_amount_usd = total_settled_usd
        report.total_discrepancy_amount_usd = total_disc_usd
        report.summary = {
            "by_type": by_type,
            "by_severity": by_severity,
            "by_processor": by_processor,
        }

        self.db.commit()
