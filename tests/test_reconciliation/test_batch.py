"""Tests for the batch reconciliation job module.

These are pure unit tests — no database required.  We mock the db_factory
and BackgroundTasks to verify job submission, listing, and lookup.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

# Clear the in-memory job store before each test so tests are isolated.
from app.services.reconciliation import batch


@pytest.fixture(autouse=True)
def _clear_jobs():
    """Reset the in-memory job tracker between tests."""
    batch._jobs.clear()
    yield
    batch._jobs.clear()


def _make_background_tasks() -> MagicMock:
    """Return a mock BackgroundTasks that records added tasks."""
    return MagicMock()


# ── Test: submit_reconciliation_job ──────────────────────────────────


class TestSubmitJob:
    def test_submit_job_returns_job_id(self):
        """submit_reconciliation_job should return a UUID string and
        register a pending job."""
        bg = _make_background_tasks()
        db_factory = MagicMock()

        job_id = batch.submit_reconciliation_job(
            db_factory=db_factory,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 1, 31),
            processors=None,
            background_tasks=bg,
        )

        # Job ID is a valid UUID-format string
        assert isinstance(job_id, str)
        assert len(job_id) == 36  # standard UUID length

        # Job was registered as pending
        job = batch.get_job_status(job_id)
        assert job is not None
        assert job["status"] == "pending"
        assert job["date_from"] == "2025-01-01"
        assert job["date_to"] == "2025-01-31"
        assert job["processors"] is None
        assert job["report_id"] is None
        assert job["error"] is None

    def test_submit_job_schedules_background_task(self):
        """The background task should be scheduled via add_task."""
        bg = _make_background_tasks()
        db_factory = MagicMock()

        batch.submit_reconciliation_job(
            db_factory=db_factory,
            date_from=date(2025, 6, 1),
            date_to=date(2025, 6, 30),
            processors=["PayFlow"],
            background_tasks=bg,
        )

        bg.add_task.assert_called_once()

    def test_submit_job_with_processors(self):
        """Processors list should be stored in the job record."""
        bg = _make_background_tasks()
        db_factory = MagicMock()

        job_id = batch.submit_reconciliation_job(
            db_factory=db_factory,
            date_from=date(2025, 3, 1),
            date_to=date(2025, 3, 31),
            processors=["PayFlow", "TransactMax"],
            background_tasks=bg,
        )

        job = batch.get_job_status(job_id)
        assert job["processors"] == ["PayFlow", "TransactMax"]


# ── Test: list_jobs ──────────────────────────────────────────────────


class TestListJobs:
    def test_list_jobs_empty(self):
        """No jobs submitted → empty list."""
        assert batch.list_jobs() == []

    def test_list_jobs_returns_all(self):
        """Submit 2 jobs, list_jobs should return both."""
        bg = _make_background_tasks()
        db_factory = MagicMock()

        id1 = batch.submit_reconciliation_job(
            db_factory=db_factory,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 1, 31),
            processors=None,
            background_tasks=bg,
        )
        id2 = batch.submit_reconciliation_job(
            db_factory=db_factory,
            date_from=date(2025, 2, 1),
            date_to=date(2025, 2, 28),
            processors=["PayFlow"],
            background_tasks=bg,
        )

        jobs = batch.list_jobs()
        assert len(jobs) == 2
        job_ids = {j["job_id"] for j in jobs}
        assert id1 in job_ids
        assert id2 in job_ids


# ── Test: get_job_status ─────────────────────────────────────────────


class TestGetJobStatus:
    def test_get_job_not_found(self):
        """Unknown job_id should return None."""
        assert batch.get_job_status("nonexistent-uuid") is None

    def test_get_job_found(self):
        """A submitted job should be retrievable by its ID."""
        bg = _make_background_tasks()
        db_factory = MagicMock()

        job_id = batch.submit_reconciliation_job(
            db_factory=db_factory,
            date_from=date(2025, 4, 1),
            date_to=date(2025, 4, 30),
            processors=None,
            background_tasks=bg,
        )

        job = batch.get_job_status(job_id)
        assert job is not None
        assert job["job_id"] == job_id
        assert job["status"] == "pending"
