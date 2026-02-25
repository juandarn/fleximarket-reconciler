"""Reporting and query endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/reports")
def list_reports():
    """List reconciliation reports. (Stub - will be implemented)"""
    return {"message": "Reports endpoint - coming soon"}
