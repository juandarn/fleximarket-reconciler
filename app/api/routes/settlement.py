"""Settlement ingestion endpoints.

Handles file uploads from payment processors (PayFlow CSV, TransactMax JSON,
GlobalPay XML), bulk loading of expected transactions, and querying stored
settlement entries.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.settlement import SettlementEntry
from app.models.transaction import ExpectedTransaction
from app.schemas.settlement import SettlementCreate, SettlementResponse, UploadResponse
from app.schemas.transaction import TransactionCreate
from app.services.ingestion.csv_parser import CsvParser
from app.services.ingestion.json_parser import JsonParser
from app.services.ingestion.xml_parser import XmlParser

logger = get_logger(__name__)

router = APIRouter()

# Registry of parsers keyed by processor name (case-insensitive lookup)
_PARSERS = {
    "payflow": CsvParser(),
    "transactmax": JsonParser(),
    "globalpay": XmlParser(),
}


@router.post("/upload", response_model=UploadResponse)
async def upload_settlement_file(
    file: UploadFile = File(...),
    processor: str = Query(
        ..., description="Processor name: payflow, transactmax, or globalpay"
    ),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """Upload a settlement file for a specific payment processor.

    The file is parsed according to the processor format, normalized, and
    each valid entry is persisted to the settlement_entries table.
    """
    processor_key = processor.strip().lower()
    parser = _PARSERS.get(processor_key)
    if parser is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown processor '{processor}'. "
            f"Supported: {', '.join(_PARSERS.keys())}",
        )

    # Read file content
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    filename = file.filename or "unknown"
    logger.info(
        "Received upload: processor=%s file=%s size=%d",
        processor,
        filename,
        len(content),
    )

    # Parse
    parsed_entries: List[SettlementCreate] = parser.parse(content, filename)
    entries_processed = len(parsed_entries)

    # Persist to DB
    entries_saved = 0
    entries_skipped = 0
    errors: list[str] = []

    for entry_schema in parsed_entries:
        try:
            db_entry = SettlementEntry(**entry_schema.model_dump())
            db.add(db_entry)
            db.flush()  # catch integrity errors per row
            entries_saved += 1
        except Exception as exc:
            db.rollback()
            entries_skipped += 1
            error_msg = f"txn={entry_schema.transaction_id}: {exc}"
            errors.append(error_msg)
            logger.warning("Failed to save entry: %s", error_msg)

    db.commit()
    logger.info(
        "Upload complete: processed=%d saved=%d skipped=%d",
        entries_processed,
        entries_saved,
        entries_skipped,
    )

    if entries_saved == 0 and entries_processed > 0:
        status = "failed"
    elif entries_skipped > 0:
        status = "partial"
    else:
        status = "success"

    return UploadResponse(
        status=status,
        message=f"Processed {entries_processed} entries from {filename}",
        entries_processed=entries_processed,
        entries_saved=entries_saved,
        entries_skipped=entries_skipped,
        errors=errors,
    )


@router.post("/load-transactions")
async def load_expected_transactions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Bulk-insert expected transactions from a JSON file.

    The JSON file should contain a list of transaction objects matching
    the TransactionCreate schema.
    """
    import json

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    if not isinstance(data, list):
        raise HTTPException(
            status_code=400,
            detail="Expected a JSON array of transaction objects.",
        )

    saved = 0
    skipped = 0
    errors: list[str] = []

    for idx, item in enumerate(data):
        try:
            txn_schema = TransactionCreate(**item)
            db_txn = ExpectedTransaction(**txn_schema.model_dump())
            db.add(db_txn)
            db.flush()
            saved += 1
        except Exception as exc:
            db.rollback()
            skipped += 1
            errors.append(f"Item {idx}: {exc}")
            logger.warning("Failed to save transaction item %d: %s", idx, exc)

    db.commit()
    logger.info("Load transactions: saved=%d skipped=%d", saved, skipped)

    return {
        "status": "success" if skipped == 0 else "partial",
        "saved": saved,
        "skipped": skipped,
        "errors": errors,
    }


@router.get("/entries", response_model=List[SettlementResponse])
def list_settlement_entries(
    processor: Optional[str] = Query(None, description="Filter by processor name"),
    currency: Optional[str] = Query(None, description="Filter by original currency"),
    date_from: Optional[datetime] = Query(None, description="Settlement date >="),
    date_to: Optional[datetime] = Query(None, description="Settlement date <="),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    db: Session = Depends(get_db),
) -> List[SettlementEntry]:
    """List settlement entries with optional filters and pagination."""
    query = db.query(SettlementEntry)

    if processor:
        query = query.filter(SettlementEntry.processor_name.ilike(f"%{processor}%"))
    if currency:
        query = query.filter(SettlementEntry.original_currency == currency.upper())
    if date_from:
        query = query.filter(SettlementEntry.settlement_date >= date_from)
    if date_to:
        query = query.filter(SettlementEntry.settlement_date <= date_to)

    offset = (page - 1) * limit
    entries = (
        query.order_by(SettlementEntry.settlement_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return entries
