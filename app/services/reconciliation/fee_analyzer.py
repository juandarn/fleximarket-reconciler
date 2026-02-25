"""Smart fee analysis service — learns fee patterns and detects anomalies.

Analyzes historical settlement data to compute average fee percentages
per processor+currency combination, then flags entries whose fees
deviate significantly from the norm.

Note: All statistical computations (mean, std dev) are done in Python
rather than SQL, ensuring compatibility with SQLite (which lacks STDDEV).
"""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.settlement import SettlementEntry

logger = get_logger(__name__)


class FeeAnalyzer:
    """Analyzes fee patterns from historical settlement data and detects anomalies."""

    def analyze_fee_patterns(self, db: Session) -> dict:
        """Query settlement_entries, compute average fee % per processor+currency.

        Only considers entries where gross_amount > 0 and both fee_amount
        and processor_name are present.

        Returns:
            Dict keyed by processor_name -> currency -> stats dict:
            {
                "PayFlow": {
                    "BRL": {"avg_fee_pct": 2.51, "std_dev": 0.12, "sample_count": 40},
                    ...
                },
                ...
            }
        """
        entries = (
            db.query(SettlementEntry)
            .filter(
                SettlementEntry.gross_amount > 0,
                SettlementEntry.fee_amount.isnot(None),
                SettlementEntry.processor_name.isnot(None),
                SettlementEntry.original_currency.isnot(None),
            )
            .all()
        )

        # Group fee percentages by (processor, currency)
        grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
        for entry in entries:
            gross = float(entry.gross_amount)
            fee = float(entry.fee_amount)
            fee_pct = (fee / gross) * 100
            key = (entry.processor_name, entry.original_currency)
            grouped[key].append(fee_pct)

        # Compute statistics per group
        result: dict[str, dict[str, dict]] = {}
        for (processor, currency), fee_pcts in grouped.items():
            n = len(fee_pcts)
            avg = sum(fee_pcts) / n
            if n >= 2:
                variance = sum((x - avg) ** 2 for x in fee_pcts) / (n - 1)
                std_dev = math.sqrt(variance)
            else:
                std_dev = 0.0

            result.setdefault(processor, {})[currency] = {
                "avg_fee_pct": round(avg, 4),
                "std_dev": round(std_dev, 4),
                "sample_count": n,
            }

        logger.info(
            "Computed fee patterns for %d processor+currency combos from %d entries",
            len(grouped),
            len(entries),
        )
        return result

    def detect_unusual_fees(
        self, db: Session, std_dev_threshold: float = 2.0
    ) -> list[dict]:
        """Find settlement entries where fee % deviates significantly from the mean.

        An entry is flagged when its fee percentage is more than
        ``std_dev_threshold`` standard deviations from the mean for its
        processor+currency combination.

        Args:
            db: Active database session.
            std_dev_threshold: Number of standard deviations to consider
                unusual (default 2.0).

        Returns:
            List of dicts, each containing:
                transaction_id, processor, currency, actual_fee_pct,
                avg_fee_pct, std_dev, deviation_score
        """
        patterns = self.analyze_fee_patterns(db)

        if not patterns:
            return []

        entries = (
            db.query(SettlementEntry)
            .filter(
                SettlementEntry.gross_amount > 0,
                SettlementEntry.fee_amount.isnot(None),
                SettlementEntry.processor_name.isnot(None),
                SettlementEntry.original_currency.isnot(None),
            )
            .all()
        )

        unusual: list[dict] = []
        for entry in entries:
            processor = entry.processor_name
            currency = entry.original_currency

            stats = patterns.get(processor, {}).get(currency)
            if stats is None:
                continue

            std_dev = stats["std_dev"]
            if std_dev == 0:
                # Can't compute deviation when there's no spread
                continue

            gross = float(entry.gross_amount)
            fee = float(entry.fee_amount)
            actual_fee_pct = (fee / gross) * 100
            avg_fee_pct = stats["avg_fee_pct"]

            deviation_score = abs(actual_fee_pct - avg_fee_pct) / std_dev

            if deviation_score > std_dev_threshold:
                unusual.append(
                    {
                        "transaction_id": entry.transaction_id,
                        "processor": processor,
                        "currency": currency,
                        "actual_fee_pct": round(actual_fee_pct, 4),
                        "avg_fee_pct": avg_fee_pct,
                        "std_dev": std_dev,
                        "deviation_score": round(deviation_score, 4),
                    }
                )

        logger.info(
            "Unusual fee detection complete: %d anomalies found out of %d entries "
            "(threshold=%.1f std devs)",
            len(unusual),
            len(entries),
            std_dev_threshold,
        )
        return unusual

    def get_fee_report(self, db: Session) -> dict:
        """Return complete fee analysis report with patterns + anomalies.

        Returns:
            Dict with keys: fee_patterns, unusual_fees, threshold_std_devs
        """
        return {
            "fee_patterns": self.analyze_fee_patterns(db),
            "unusual_fees": self.detect_unusual_fees(db),
            "threshold_std_devs": 2.0,
        }
