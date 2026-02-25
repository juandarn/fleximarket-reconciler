"""Transaction-to-settlement matching logic.

This module is responsible for pairing expected transactions with their
corresponding settlement entries.  Think of it like matching receipts to
bank statements: every purchase (transaction) should have a corresponding
deposit (settlement).  When they don't line up, we have a problem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MatchResult:
    """Container for matching outcomes.

    Attributes:
        matched: Pairs of (transaction, settlement) that share a transaction_id.
        unmatched_transactions: Transactions that have *no* settlement entry.
        unmatched_settlements: Settlement entries that have *no* expected transaction.
        duplicates: Mapping of transaction_id -> list of settlements when a
            single transaction_id appears in 2+ settlement entries.
    """

    matched: List[Tuple[Any, Any]] = field(default_factory=list)
    unmatched_transactions: List[Any] = field(default_factory=list)
    unmatched_settlements: List[Any] = field(default_factory=list)
    duplicates: dict[str, List[Any]] = field(default_factory=dict)


class TransactionMatcher:
    """Matches expected transactions to settlement entries by transaction_id.

    The algorithm:
    1. Build a lookup dict of settlements keyed by transaction_id.
    2. Walk through every expected transaction:
       - 0 matching settlements  -> unmatched_transaction
       - 1 matching settlement   -> matched pair
       - 2+ matching settlements -> duplicate (AND still produce matched pairs)
    3. Any settlements *not* claimed by a transaction -> unmatched_settlement
    """

    def match(
        self,
        transactions: list,
        settlements: list,
    ) -> MatchResult:
        """Match transactions to settlements by transaction_id.

        Args:
            transactions: Iterable of objects with a ``transaction_id`` attribute.
            settlements: Iterable of objects with a ``transaction_id`` attribute.

        Returns:
            A ``MatchResult`` describing matched pairs, orphans, and duplicates.
        """
        result = MatchResult()

        # --- Step 1: index settlements by transaction_id ---------------
        settlement_map: dict[str, list] = {}
        for s in settlements:
            txn_id = s.transaction_id
            settlement_map.setdefault(txn_id, []).append(s)

        # Track which settlement transaction_ids have been "claimed"
        claimed_txn_ids: set[str] = set()

        # --- Step 2: walk transactions ---------------------------------
        for txn in transactions:
            txn_id = txn.transaction_id
            entries = settlement_map.get(txn_id, [])

            if len(entries) == 0:
                # No settlement found for this transaction
                result.unmatched_transactions.append(txn)

            elif len(entries) == 1:
                # Perfect 1-to-1 match
                result.matched.append((txn, entries[0]))
                claimed_txn_ids.add(txn_id)

            else:
                # Duplicate: 2+ settlements share the same transaction_id
                result.duplicates[txn_id] = entries
                # Still record the first as a matched pair so downstream
                # rules can detect amount/fee mismatches on the "primary" entry
                result.matched.append((txn, entries[0]))
                claimed_txn_ids.add(txn_id)

        # --- Step 3: find unclaimed settlements ------------------------
        for txn_id, entries in settlement_map.items():
            if txn_id not in claimed_txn_ids:
                result.unmatched_settlements.extend(entries)

        logger.info(
            "Matching complete: matched=%d unmatched_txn=%d "
            "unmatched_stl=%d duplicates=%d",
            len(result.matched),
            len(result.unmatched_transactions),
            len(result.unmatched_settlements),
            len(result.duplicates),
        )

        return result
