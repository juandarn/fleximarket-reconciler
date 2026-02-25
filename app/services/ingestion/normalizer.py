"""Normalizer utility functions for settlement data.

These functions provide a single place to handle the messy reality of
multi-processor data: inconsistent date formats, currency symbols vs codes,
processor-specific status labels, etc.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# Maps common currency symbols / aliases to ISO 4217 codes
_CURRENCY_ALIASES: dict[str, str] = {
    "R$": "BRL",
    "BRL": "BRL",
    "$": "USD",
    "USD": "USD",
    "MXN": "MXN",
    "MX$": "MXN",
    "COP": "COP",
    "CLP": "CLP",
    "ARS": "ARS",
    "EUR": "EUR",
    "GBP": "GBP",
}

# Processor-specific status -> our canonical status
_STATUS_MAP: dict[str, dict[str, str]] = {
    "payflow": {
        "SETTLED": "completed",
        "FAILED": "failed",
        "HELD": "held",
        "REVERSED": "reversed",
    },
    "transactmax": {
        "completed": "completed",
        "failed": "failed",
        "held": "held",
        "reversed": "reversed",
        "on_hold": "held",
    },
    "globalpay": {
        "COMPLETED": "completed",
        "FAILED": "failed",
        "ON_HOLD": "held",
        "REVERSED": "reversed",
    },
}

# Date formats we accept, ordered from most specific to least
_DATE_FORMATS: list[str] = [
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
]


def normalize_currency(code: str) -> str:
    """Normalize currency codes: 'brl' -> 'BRL', 'R$' -> 'BRL', etc.

    Args:
        code: Raw currency string from the processor file.

    Returns:
        Three-letter uppercase ISO 4217 currency code.

    Raises:
        ValueError: If the code cannot be resolved.
    """
    stripped = code.strip()
    # Try exact match first (case-insensitive)
    upper = stripped.upper()
    if upper in _CURRENCY_ALIASES:
        return _CURRENCY_ALIASES[upper]
    # Try alias map with original casing (for symbols like R$)
    if stripped in _CURRENCY_ALIASES:
        return _CURRENCY_ALIASES[stripped]
    # If it looks like a 3-letter code, just uppercase it
    if len(stripped) == 3 and stripped.isalpha():
        return upper
    raise ValueError(f"Unknown currency code: {code!r}")


def normalize_date(date_str: str) -> Optional[datetime]:
    """Try multiple date formats and return a datetime.

    Args:
        date_str: Raw date string from the processor file.

    Returns:
        Parsed datetime object, or None if all formats fail.
    """
    stripped = date_str.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt)
        except ValueError:
            continue
    logger.warning("Could not parse date: %s", date_str)
    return None


def normalize_status(status: str, processor: str) -> str:
    """Map processor-specific status to standard: completed/failed/held/reversed.

    Args:
        status: Raw status string from the processor.
        processor: Processor name (lowercase).

    Returns:
        Canonical status string.
    """
    proc_key = processor.strip().lower()
    status_stripped = status.strip()

    proc_map = _STATUS_MAP.get(proc_key, {})
    # Try exact match
    if status_stripped in proc_map:
        return proc_map[status_stripped]
    # Try case-insensitive
    for key, value in proc_map.items():
        if key.lower() == status_stripped.lower():
            return value

    logger.warning(
        "Unknown status %r for processor %r, defaulting to original lowercase",
        status,
        processor,
    )
    return status_stripped.lower()


def normalize_transaction_id(txn_id: str) -> str:
    """Strip whitespace and uppercase the transaction ID.

    Args:
        txn_id: Raw transaction identifier.

    Returns:
        Cleaned, uppercased transaction ID.
    """
    return txn_id.strip().upper()
