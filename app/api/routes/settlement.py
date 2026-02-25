"""Settlement ingestion endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/entries")
def list_settlement_entries():
    """List ingested settlement entries. (Stub - will be implemented)"""
    return {"message": "Settlement entries endpoint - coming soon"}
