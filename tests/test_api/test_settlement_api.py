"""API integration tests for the settlement ingestion endpoints."""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def test_upload_csv_file(client):
    """POST /api/v1/settlement/upload with PayFlow CSV file returns 200."""
    csv_path = DATA_DIR / "settlement_payflow.csv"
    assert csv_path.exists(), f"Test data not found: {csv_path}"

    with open(csv_path, "rb") as f:
        response = client.post(
            "/api/v1/settlement/upload",
            params={"processor": "PayFlow"},
            files={"file": ("settlement_payflow.csv", f, "text/csv")},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["entries_processed"] > 0
    assert data["entries_saved"] > 0
    assert data["status"] in ("success", "partial")


def test_upload_json_file(client):
    """POST /api/v1/settlement/upload with TransactMax JSON file returns 200."""
    json_path = DATA_DIR / "settlement_transactmax.json"
    assert json_path.exists(), f"Test data not found: {json_path}"

    with open(json_path, "rb") as f:
        response = client.post(
            "/api/v1/settlement/upload",
            params={"processor": "TransactMax"},
            files={"file": ("settlement_transactmax.json", f, "application/json")},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["entries_processed"] > 0
    assert data["entries_saved"] > 0


def test_upload_unsupported_processor(client):
    """POST /api/v1/settlement/upload with unknown processor returns 400."""
    response = client.post(
        "/api/v1/settlement/upload",
        params={"processor": "UnknownProcessor"},
        files={"file": ("dummy.csv", b"some,data\n1,2", "text/csv")},
    )

    assert response.status_code == 400
    data = response.json()
    assert "Unknown processor" in data["detail"]


def test_list_entries_empty(client):
    """GET /api/v1/settlement/entries returns empty list when no data."""
    response = client.get("/api/v1/settlement/entries")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_load_transactions(client):
    """POST /api/v1/settlement/load-transactions with expected_transactions.json returns 200."""
    json_path = DATA_DIR / "expected_transactions.json"
    assert json_path.exists(), f"Test data not found: {json_path}"

    with open(json_path, "rb") as f:
        response = client.post(
            "/api/v1/settlement/load-transactions",
            files={"file": ("expected_transactions.json", f, "application/json")},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["saved"] > 0
    assert data["status"] in ("success", "partial")
