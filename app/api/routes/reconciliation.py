"""Reconciliation engine endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
def reconciliation_status():
    """Get reconciliation engine status. (Stub - will be implemented)"""
    return {"message": "Reconciliation endpoint - coming soon"}
