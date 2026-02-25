"""Multi-currency discrepancy reporting.

Aggregates all discrepancies and converts financial impact amounts into
a single target currency (USD by default) using the reference FX rates
from the rules module.  This gives stakeholders a unified view of
reconciliation impact regardless of the original transaction currencies.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.discrepancy import Discrepancy
from app.services.reconciliation.rules import to_usd

logger = get_logger(__name__)


class CurrencyReporter:
    """Reports all discrepancies converted to a single target currency."""

    def get_multi_currency_report(
        self, db: Session, target_currency: str = "USD"
    ) -> dict:
        """Aggregate all discrepancies, converting amounts to target currency.

        Returns a dict with:
          - target_currency: the currency everything is denominated in
          - total_impact: sum of all |impact_usd| values
          - by_processor: {name: {count, total_impact_usd}}
          - by_type: {type: {count, total_impact_usd}}
          - by_original_currency: {currency: {count, total_impact_usd, total_impact_local}}
          - discrepancies: list of per-item dicts
        """
        discrepancies = db.query(Discrepancy).all()

        total_impact = 0.0
        by_processor: dict[str, dict] = {}
        by_type: dict[str, dict] = {}
        by_currency: dict[str, dict] = {}
        items: list[dict] = []

        for d in discrepancies:
            # Use pre-computed impact_usd when available, otherwise convert
            impact = (
                float(d.impact_usd)
                if d.impact_usd
                else to_usd(
                    float(d.difference_amount or 0), d.difference_currency or "USD"
                )
            )
            total_impact += abs(impact)

            # --- Aggregate by processor ---
            proc = d.processor_name or "unknown"
            if proc not in by_processor:
                by_processor[proc] = {"count": 0, "total_impact_usd": 0.0}
            by_processor[proc]["count"] += 1
            by_processor[proc]["total_impact_usd"] += abs(impact)

            # --- Aggregate by discrepancy type ---
            dtype = d.type or "unknown"
            if dtype not in by_type:
                by_type[dtype] = {"count": 0, "total_impact_usd": 0.0}
            by_type[dtype]["count"] += 1
            by_type[dtype]["total_impact_usd"] += abs(impact)

            # --- Aggregate by original currency ---
            curr = d.difference_currency or "USD"
            if curr not in by_currency:
                by_currency[curr] = {
                    "count": 0,
                    "total_impact_usd": 0.0,
                    "total_impact_local": 0.0,
                }
            by_currency[curr]["count"] += 1
            by_currency[curr]["total_impact_usd"] += abs(impact)
            by_currency[curr]["total_impact_local"] += abs(
                float(d.difference_amount or 0)
            )

            items.append(
                {
                    "transaction_id": d.transaction_id,
                    "type": d.type,
                    "processor": proc,
                    "original_amount": float(d.difference_amount or 0),
                    "original_currency": curr,
                    "impact_usd": round(abs(impact), 2),
                    "severity": d.severity,
                }
            )

        # Round all USD totals for clean output
        for v in by_processor.values():
            v["total_impact_usd"] = round(v["total_impact_usd"], 2)
        for v in by_type.values():
            v["total_impact_usd"] = round(v["total_impact_usd"], 2)
        for v in by_currency.values():
            v["total_impact_usd"] = round(v["total_impact_usd"], 2)
            v["total_impact_local"] = round(v["total_impact_local"], 2)

        return {
            "target_currency": target_currency,
            "total_impact": round(total_impact, 2),
            "by_processor": by_processor,
            "by_type": by_type,
            "by_original_currency": by_currency,
            "discrepancies": items,
        }
