"""Tests for the health check endpoint."""

from __future__ import annotations


def test_health_check(client):
    """GET /health returns 200 with status=healthy."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "fleximarket-reconciler"
