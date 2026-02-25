"""FlexiMarket Settlement Reconciliation Engine - Main Application."""

import logging.config

from fastapi import FastAPI

from app.api.routes import settlement, reconciliation, reports
from app.core.database import Base, engine
from app.core.logging import setup_logging
from app.core.logging_config import LOGGING_CONFIG

# Configure logging before anything else
logging.config.dictConfig(LOGGING_CONFIG)
logger = setup_logging()

# Create all tables on startup
logger.info("Creating database tables...")
Base.metadata.create_all(bind=engine)
logger.info("Database tables ready")

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

logger.info("FlexiMarket Reconciler API ready - routes registered")


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "fleximarket-reconciler"}
