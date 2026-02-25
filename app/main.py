"""FlexiMarket Settlement Reconciliation Engine - Main Application."""

from fastapi import FastAPI

from app.api.routes import settlement, reconciliation, reports
from app.core.database import Base, engine

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FlexiMarket Settlement Reconciliation Engine",
    description=(
        "Multi-currency settlement reconciliation service that ingests "
        "settlement reports from multiple payment processors, reconciles "
        "them against expected transactions, and exposes discrepancies via API."
    ),
    version="1.0.0",
)

app.include_router(settlement.router, prefix="/api/v1/settlement", tags=["Settlement"])
app.include_router(
    reconciliation.router, prefix="/api/v1/reconciliation", tags=["Reconciliation"]
)
app.include_router(reports.router, prefix="/api/v1", tags=["Reports"])


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "fleximarket-reconciler"}
