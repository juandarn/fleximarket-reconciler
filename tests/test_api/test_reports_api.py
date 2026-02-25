"""API integration tests for the reports / query endpoints."""

from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def test_discrepancies_empty(client):
    """GET /api/v1/discrepancies returns empty list when no data."""
    response = client.get("/api/v1/discrepancies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_discrepancy_summary_empty(client):
    """GET /api/v1/discrepancies/summary returns zeroes when no data."""
    response = client.get("/api/v1/discrepancies/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert data["by_type"] == {}
    assert data["by_processor"] == {}
    assert data["by_severity"] == {}
    assert float(data["total_impact_usd"]) == 0


def test_transaction_status_not_found(client):
    """GET /api/v1/transactions/FAKE-ID/status returns 404."""
    response = client.get("/api/v1/transactions/FAKE-ID/status")
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_reconciliation_report_not_found(client):
    """GET /api/v1/reconciliation/report returns 404 when no reports exist."""
    response = client.get("/api/v1/reconciliation/report")
    assert response.status_code == 404


def test_full_flow(client):
    """End-to-end: load transactions -> upload settlements -> reconcile -> query discrepancies.

    This is the most important test: it exercises the entire pipeline
    from data ingestion through reconciliation to querying results.
    """
    # Step 1: Load expected transactions
    txn_path = DATA_DIR / "expected_transactions.json"
    with open(txn_path, "rb") as f:
        resp = client.post(
            "/api/v1/settlement/load-transactions",
            files={"file": ("expected_transactions.json", f, "application/json")},
        )
    assert resp.status_code == 200, f"Load transactions failed: {resp.text}"
    txn_data = resp.json()
    assert txn_data["saved"] > 0, "No transactions were saved"

    # Step 2: Upload PayFlow CSV settlements
    payflow_path = DATA_DIR / "settlement_payflow.csv"
    with open(payflow_path, "rb") as f:
        resp = client.post(
            "/api/v1/settlement/upload",
            params={"processor": "PayFlow"},
            files={"file": ("settlement_payflow.csv", f, "text/csv")},
        )
    assert resp.status_code == 200, f"PayFlow upload failed: {resp.text}"
    pf_data = resp.json()
    assert pf_data["entries_saved"] > 0, "No PayFlow entries saved"

    # Step 3: Upload TransactMax JSON settlements
    tm_path = DATA_DIR / "settlement_transactmax.json"
    with open(tm_path, "rb") as f:
        resp = client.post(
            "/api/v1/settlement/upload",
            params={"processor": "TransactMax"},
            files={"file": ("settlement_transactmax.json", f, "application/json")},
        )
    assert resp.status_code == 200, f"TransactMax upload failed: {resp.text}"
    tm_data = resp.json()
    assert tm_data["entries_saved"] > 0, "No TransactMax entries saved"

    # Step 4: Run reconciliation
    resp = client.post(
        "/api/v1/reconciliation/run",
        json={"date_from": "2024-01-01", "date_to": "2024-01-14"},
    )
    assert resp.status_code == 200, f"Reconciliation run failed: {resp.text}"
    recon_data = resp.json()
    assert recon_data["status"] == "completed"
    assert recon_data["total_transactions"] > 0

    # Step 5: Query discrepancies and verify they exist
    resp = client.get("/api/v1/discrepancies")
    assert resp.status_code == 200
    discrepancies = resp.json()
    assert len(discrepancies) > 0, "Expected discrepancies after reconciliation"

    # Step 6: Check summary
    resp = client.get("/api/v1/discrepancies/summary")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_count"] > 0, "Expected total_count > 0 in summary"
    assert len(summary["by_type"]) > 0, "Expected at least one discrepancy type"

    # Step 7: Check a known transaction's status
    # Pick the first discrepancy's transaction_id
    test_txn_id = discrepancies[0]["transaction_id"]
    resp = client.get(f"/api/v1/transactions/{test_txn_id}/status")
    assert resp.status_code == 200
    status_data = resp.json()
    assert status_data["transaction_id"] == test_txn_id

    # Step 8: Check reconciliation report endpoint
    resp = client.get(
        "/api/v1/reconciliation/report",
        params={"date_from": "2024-01-01", "date_to": "2024-01-14"},
    )
    assert resp.status_code == 200
    report = resp.json()
    assert report["status"] == "completed"
    assert report["total_transactions"] > 0
