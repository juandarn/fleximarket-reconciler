"""FlexiMarket Settlement Reconciliation Engine - Main Application."""

import logging.config

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

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

# -- OpenAPI tag metadata for Swagger grouping --
tags_metadata = [
    {
        "name": "Health",
        "description": "Service health and readiness checks.",
    },
    {
        "name": "Settlement",
        "description": (
            "Ingest settlement files from payment processors (PayFlow CSV, "
            "TransactMax JSON, GlobalPay XML), load expected transactions, "
            "and query stored settlement entries."
        ),
    },
    {
        "name": "Reconciliation",
        "description": (
            "Run reconciliation jobs that compare expected transactions against "
            "settlement entries and produce reports with detected discrepancies."
        ),
    },
    {
        "name": "Reports",
        "description": (
            "Query discrepancies with filtering (type, processor, severity, "
            "date range), get summary statistics, check individual transaction "
            "settlement status, and retrieve reconciliation reports."
        ),
    },
]


app = FastAPI(
    title="FlexiMarket Settlement Reconciliation Engine",
    description=(
        "## Multi-Currency Settlement Reconciliation API\n\n"
        "This service ingests settlement reports from multiple LATAM payment "
        "processors, reconciles them against expected transactions, and exposes "
        "discrepancies via a structured REST API.\n\n"
        "### Supported Processors\n"
        "| Processor | Format | Currencies | Region |\n"
        "|-----------|--------|------------|--------|\n"
        "| **PayFlow** | CSV | BRL, MXN | Brazil, Mexico |\n"
        "| **TransactMax** | JSON | COP, CLP | Colombia, Chile |\n"
        "| **GlobalPay** | XML | MXN, COP | Mexico, Colombia |\n\n"
        "### Discrepancy Types Detected\n"
        "- `missing_settlement` - Transaction expected but not found in settlement\n"
        "- `amount_mismatch` - Settled amount differs from expected\n"
        "- `excessive_fee` - Processor fees higher than expected\n"
        "- `currency_mismatch` - FX rate deviates beyond tolerance\n"
        "- `duplicate_settlement` - Same transaction settled more than once\n\n"
        "### Quick Start\n"
        "```bash\n"
        "# 1. Load expected transactions\n"
        "curl -X POST /api/v1/settlement/load-transactions -F file=@data/expected_transactions.json\n\n"
        "# 2. Upload settlement files\n"
        "curl -X POST '/api/v1/settlement/upload?processor=PayFlow' -F file=@data/settlement_payflow.csv\n\n"
        "# 3. Run reconciliation\n"
        'curl -X POST /api/v1/reconciliation/run -H "Content-Type: application/json" '
        '-d \'{"date_from":"2024-01-01","date_to":"2024-01-14"}\'\n\n'
        "# 4. Query discrepancies\n"
        "curl /api/v1/discrepancies?severity=critical\n"
        "```\n"
    ),
    version="1.0.0",
    openapi_tags=tags_metadata,
    contact={
        "name": "FlexiMarket Engineering",
        "url": "https://github.com/juandarn/fleximarket-reconciler",
    },
    license_info={
        "name": "MIT",
    },
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(settlement.router, prefix="/api/v1/settlement", tags=["Settlement"])
app.include_router(
    reconciliation.router, prefix="/api/v1/reconciliation", tags=["Reconciliation"]
)
app.include_router(reports.router, prefix="/api/v1", tags=["Reports"])

logger.info("FlexiMarket Reconciler API ready - routes registered")


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint.

    Returns a simple JSON object confirming the service is running.
    Useful for load balancers and monitoring systems.
    """
    return {"status": "healthy", "service": "fleximarket-reconciler"}
