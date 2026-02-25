"""Configurable discrepancy-detection rules.

Each ``detect_*`` function inspects a (transaction, settlement) pair and
returns a lightweight dict describing the discrepancy if one is found,
or ``None`` if everything looks fine.  The engine later converts these dicts
into proper Discrepancy ORM objects for persistence.

Why dicts instead of ORM objects?  So the rules stay *pure* — they don't
need a database session, which makes them dead-simple to unit-test.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from app.core.config import Settings

# ── Reference FX rates (local currency -> USD) ──────────────────────
# These are approximate mid-market rates used *only* to estimate USD
# impact.  They are NOT authoritative for accounting.
FX_RATES_TO_USD: dict[str, float] = {
    "BRL": 0.20,
    "MXN": 0.059,
    "COP": 0.00025,
    "CLP": 0.0011,
    "USD": 1.0,
}


def to_usd(amount: float, currency: str) -> float:
    """Convert a local-currency amount to approximate USD.

    Args:
        amount: Value in the local currency.
        currency: ISO 4217 code (e.g. "BRL").

    Returns:
        Approximate USD equivalent.
    """
    rate = FX_RATES_TO_USD.get(currency, 1.0)
    return round(amount * rate, 2)


# ── Detection rules ─────────────────────────────────────────────────


def detect_amount_mismatch(
    transaction: Any,
    settlement: Any,
    tolerance_pct: float,
) -> Optional[dict]:
    """Compare expected_net_amount vs settlement.net_amount.

    A discrepancy is raised when the absolute difference exceeds
    ``tolerance_pct`` percent of the expected value.
    """
    expected = float(transaction.expected_net_amount or 0)
    actual = float(settlement.net_amount or 0)

    if expected == 0:
        return None

    diff = abs(expected - actual)
    pct_diff = (diff / abs(expected)) * 100

    if pct_diff <= tolerance_pct:
        return None

    currency = getattr(transaction, "currency", "USD")
    impact = to_usd(diff, currency)

    return {
        "type": "amount_mismatch",
        "transaction_id": transaction.transaction_id,
        "expected_value": expected,
        "actual_value": actual,
        "difference_amount": round(diff, 2),
        "difference_currency": currency,
        "impact_usd": impact,
        "processor_name": getattr(transaction, "processor_name", None),
        "description": (
            f"Net amount mismatch: expected {expected} vs actual {actual} "
            f"({currency}), diff={round(diff, 2)} ({pct_diff:.4f}%)"
        ),
    }


def detect_excessive_fee(
    transaction: Any,
    settlement: Any,
    fee_tolerance_pct: float,
) -> Optional[dict]:
    """Check whether the processor charged more than the expected fee %.

    ``actual_fee_pct = (fee_amount / gross_amount) * 100``
    A discrepancy is raised when actual_fee_pct > expected + tolerance.
    """
    expected_fee_pct = float(transaction.expected_fee_percent or 0)
    gross = float(settlement.gross_amount or 0)
    fee = float(settlement.fee_amount or 0)

    if gross == 0:
        return None

    actual_fee_pct = (fee / gross) * 100
    excess = actual_fee_pct - expected_fee_pct

    if excess <= fee_tolerance_pct:
        return None

    currency = getattr(transaction, "currency", "USD")
    expected_fee_amount = gross * (expected_fee_pct / 100)
    fee_diff = fee - expected_fee_amount
    impact = to_usd(fee_diff, currency)

    return {
        "type": "excessive_fee",
        "transaction_id": transaction.transaction_id,
        "expected_value": round(expected_fee_pct, 4),
        "actual_value": round(actual_fee_pct, 4),
        "difference_amount": round(fee_diff, 2),
        "difference_currency": currency,
        "impact_usd": impact,
        "processor_name": getattr(transaction, "processor_name", None),
        "description": (
            f"Excessive fee: expected {expected_fee_pct:.2f}% "
            f"vs actual {actual_fee_pct:.2f}% "
            f"(excess {excess:.2f}pp, fee_diff={round(fee_diff, 2)} {currency})"
        ),
    }


def detect_currency_mismatch(
    transaction: Any,
    settlement: Any,
    fx_tolerance_pct: float,
) -> Optional[dict]:
    """Flag when the settlement FX rate deviates significantly from reference.

    Only applies when the settlement carries an ``fx_rate`` value (i.e. a
    cross-currency settlement).
    """
    fx_rate = getattr(settlement, "fx_rate", None)
    if fx_rate is None:
        return None

    actual_rate = float(fx_rate)
    currency = getattr(transaction, "currency", "USD")
    expected_rate = FX_RATES_TO_USD.get(currency)

    if expected_rate is None or expected_rate == 0:
        return None

    deviation_pct = abs(actual_rate - expected_rate) / expected_rate * 100

    if deviation_pct <= fx_tolerance_pct:
        return None

    # Estimate impact: how much extra/less was received in USD due to
    # the rate deviation
    net_amount = float(settlement.net_amount or 0)
    expected_usd = net_amount * expected_rate
    actual_usd = net_amount * actual_rate
    impact = abs(actual_usd - expected_usd)

    return {
        "type": "currency_mismatch",
        "transaction_id": transaction.transaction_id,
        "expected_value": expected_rate,
        "actual_value": actual_rate,
        "difference_amount": round(abs(actual_rate - expected_rate), 6),
        "difference_currency": "USD",
        "impact_usd": round(impact, 2),
        "processor_name": getattr(transaction, "processor_name", None),
        "description": (
            f"FX rate deviation for {currency}->USD: "
            f"expected {expected_rate} vs actual {actual_rate} "
            f"(deviation {deviation_pct:.2f}%)"
        ),
    }


def detect_missing_settlement(
    transaction: Any,
    threshold_days: int,
    reference_date: date,
) -> Optional[dict]:
    """Flag a transaction as missing its settlement after a grace period.

    If ``transaction_date + threshold_days < reference_date`` and no
    settlement entry was found, this is a problem — the money may be stuck.
    """
    txn_date = transaction.transaction_date
    # Handle datetime objects — we only care about the date part
    if hasattr(txn_date, "date"):
        txn_date = txn_date.date()

    days_elapsed = (reference_date - txn_date).days

    if days_elapsed <= threshold_days:
        return None

    currency = getattr(transaction, "currency", "USD")
    expected_net = float(transaction.expected_net_amount or transaction.amount or 0)
    impact = to_usd(expected_net, currency)

    return {
        "type": "missing_settlement",
        "transaction_id": transaction.transaction_id,
        "expected_value": expected_net,
        "actual_value": None,
        "difference_amount": expected_net,
        "difference_currency": currency,
        "impact_usd": impact,
        "processor_name": getattr(transaction, "processor_name", None),
        "description": (
            f"No settlement found after {days_elapsed} days "
            f"(threshold={threshold_days}d). "
            f"Expected net: {expected_net} {currency}"
        ),
    }


def detect_duplicate_settlement(
    transaction_id: str,
    settlements: list,
) -> Optional[dict]:
    """Flag when the same transaction_id has 2+ settlement entries.

    Duplicates can cause double payouts — definitely something we need to
    catch.
    """
    if len(settlements) < 2:
        return None

    total = sum(float(s.net_amount or 0) for s in settlements)
    first = settlements[0]
    currency = getattr(first, "original_currency", None) or getattr(
        first, "settlement_currency", "USD"
    )
    processor = getattr(first, "processor_name", None)
    impact = to_usd(total, currency)

    return {
        "type": "duplicate_settlement",
        "transaction_id": transaction_id,
        "expected_value": None,
        "actual_value": total,
        "difference_amount": total,
        "difference_currency": currency,
        "impact_usd": impact,
        "processor_name": processor,
        "description": (
            f"Duplicate settlement: {len(settlements)} entries "
            f"for {transaction_id}, total net={total} {currency}"
        ),
    }


# ── Severity helpers ─────────────────────────────────────────────────


def calculate_severity(impact_usd: float, config: Settings) -> str:
    """Return severity label based on USD impact thresholds in config.

    Thresholds (defaults):
        critical: >= 1000 USD
        high:     >= 100 USD
        medium:   >= 10 USD
        low:      < 10 USD
    """
    if impact_usd >= config.severity_critical_threshold:
        return "critical"
    if impact_usd >= config.severity_high_threshold:
        return "high"
    if impact_usd >= config.severity_medium_threshold:
        return "medium"
    return "low"
