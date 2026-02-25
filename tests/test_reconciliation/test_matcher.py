"""Unit tests for the TransactionMatcher.

These tests are *pure* — no database, no network, no side effects.
We use SimpleNamespace to create lightweight stand-ins for ORM objects
so we can verify matching logic in isolation.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.reconciliation.matcher import TransactionMatcher


def _txn(txn_id: str) -> SimpleNamespace:
    """Create a minimal transaction-like object."""
    return SimpleNamespace(transaction_id=txn_id)


def _stl(txn_id: str) -> SimpleNamespace:
    """Create a minimal settlement-like object."""
    return SimpleNamespace(transaction_id=txn_id)


@pytest.fixture
def matcher() -> TransactionMatcher:
    return TransactionMatcher()


# ── Tests ────────────────────────────────────────────────────────────


class TestTransactionMatcher:
    """Tests for TransactionMatcher.match()."""

    def test_match_single_pair(self, matcher: TransactionMatcher) -> None:
        """One transaction matches exactly one settlement."""
        txns = [_txn("TXN-001")]
        stls = [_stl("TXN-001")]

        result = matcher.match(txns, stls)

        assert len(result.matched) == 1
        assert result.matched[0][0].transaction_id == "TXN-001"
        assert result.matched[0][1].transaction_id == "TXN-001"
        assert result.unmatched_transactions == []
        assert result.unmatched_settlements == []
        assert result.duplicates == {}

    def test_match_no_settlement(self, matcher: TransactionMatcher) -> None:
        """Transaction has no matching settlement -> unmatched."""
        txns = [_txn("TXN-001")]
        stls = []

        result = matcher.match(txns, stls)

        assert result.matched == []
        assert len(result.unmatched_transactions) == 1
        assert result.unmatched_transactions[0].transaction_id == "TXN-001"
        assert result.unmatched_settlements == []
        assert result.duplicates == {}

    def test_match_duplicate_settlement(self, matcher: TransactionMatcher) -> None:
        """One transaction_id appears in 2 settlement entries -> duplicate."""
        txns = [_txn("TXN-001")]
        stls = [_stl("TXN-001"), _stl("TXN-001")]

        result = matcher.match(txns, stls)

        # The first settlement is still recorded as a matched pair
        assert len(result.matched) == 1
        assert result.matched[0][0].transaction_id == "TXN-001"

        # Both settlements recorded under duplicates
        assert "TXN-001" in result.duplicates
        assert len(result.duplicates["TXN-001"]) == 2

        # No unmatched transactions (the txn was claimed)
        assert result.unmatched_transactions == []

    def test_match_multiple_transactions(self, matcher: TransactionMatcher) -> None:
        """Mix of matched, unmatched, and duplicate scenarios."""
        txns = [
            _txn("TXN-001"),  # will match
            _txn("TXN-002"),  # no settlement -> unmatched
            _txn("TXN-003"),  # duplicate settlements
        ]
        stls = [
            _stl("TXN-001"),
            _stl("TXN-003"),
            _stl("TXN-003"),
            _stl("TXN-999"),  # no transaction -> unmatched settlement
        ]

        result = matcher.match(txns, stls)

        # TXN-001 and TXN-003 each produce a matched pair
        assert len(result.matched) == 2
        matched_ids = {m[0].transaction_id for m in result.matched}
        assert matched_ids == {"TXN-001", "TXN-003"}

        # TXN-002 is unmatched
        assert len(result.unmatched_transactions) == 1
        assert result.unmatched_transactions[0].transaction_id == "TXN-002"

        # TXN-999 settlement is unmatched
        assert len(result.unmatched_settlements) == 1
        assert result.unmatched_settlements[0].transaction_id == "TXN-999"

        # TXN-003 is duplicated
        assert "TXN-003" in result.duplicates
        assert len(result.duplicates["TXN-003"]) == 2
