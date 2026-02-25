# FlexiMarket Settlement Reconciliation Engine

A multi-currency settlement reconciliation service that ingests settlement reports from three payment processors (PayFlow CSV, TransactMax JSON, GlobalPay XML), reconciles them against expected transactions, and exposes discrepancies through a RESTful API. Built as a take-home exercise demonstrating ingestion pipeline design, rule-based matching, and production-grade API design with Python and FastAPI.

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> && cd fleximarket-reconciler

# 2. Install dependencies
make install

# 3. Start PostgreSQL (dev + test containers)
make db-up

# 4. Generate test data (200 transactions, 3 settlement files, planted discrepancies)
make generate-data

# 5. Run the server
make run
# API docs: http://localhost:8000/docs

# 6. Run the full test suite (146 tests)
make test
```

> **One-liner setup:** `make all` runs install + db-up + generate-data + test in sequence.

---

## Architecture

```
                          FlexiMarket Reconciliation Engine
  ┌──────────────────────────────────────────────────────────────────────┐
  │                                                                      │
  │   Settlement Files              Expected Transactions                │
  │   ┌──────────────┐              ┌─────────────────────┐              │
  │   │ PayFlow .csv │              │ JSON (200 txns,     │              │
  │   │ TransactMax  │              │ 4 currencies,       │              │
  │   │   .json      │              │ 3 processors)       │              │
  │   │ GlobalPay    │              │                     │              │
  │   │   .xml       │              └────────┬────────────┘              │
  │   └──────┬───────┘                       │                           │
  │          │                               │                           │
  │          ▼                               ▼                           │
  │   ┌─────────────────────────────────────────────┐                    │
  │   │            Ingestion Layer                   │                    │
  │   │  ┌────────────┐ ┌──────────┐ ┌────────────┐ │                    │
  │   │  │ CSV Parser │ │JSON Parse│ │ XML Parser │ │                    │
  │   │  └─────┬──────┘ └────┬─────┘ └─────┬──────┘ │                    │
  │   │        └─────────────┼──────────────┘        │                    │
  │   │                      ▼                       │                    │
  │   │              ┌──────────────┐                 │                    │
  │   │              │  Normalizer  │                 │                    │
  │   │              │  (unified    │                 │                    │
  │   │              │   schema)    │                 │                    │
  │   │              └──────┬───────┘                 │                    │
  │   └─────────────────────┼────────────────────────┘                    │
  │                         ▼                                             │
  │   ┌──────────────────────────────────────────────┐                    │
  │   │              PostgreSQL                       │                    │
  │   │  ┌───────────────────┐ ┌──────────────────┐  │                    │
  │   │  │ settlement_entries│ │expected_transacts │  │                    │
  │   │  └───────────────────┘ └──────────────────┘  │                    │
  │   │  ┌───────────────────┐ ┌──────────────────┐  │                    │
  │   │  │  discrepancies    │ │ recon_reports     │  │                    │
  │   │  └───────────────────┘ └──────────────────┘  │                    │
  │   └──────────────────────┬───────────────────────┘                    │
  │                          ▼                                            │
  │   ┌──────────────────────────────────────────────┐                    │
  │   │         Reconciliation Engine                 │                    │
  │   │                                               │                    │
  │   │  Matcher: join expected <-> settled by txn_id │                    │
  │   │  Rules:                                       │                    │
  │   │    - Amount mismatch (configurable tolerance) │                    │
  │   │    - Excessive fees (vs expected %)           │                    │
  │   │    - Missing settlements                      │                    │
  │   │    - Duplicate detection                      │                    │
  │   │    - FX rate deviation (> threshold %)        │                    │
  │   │  Severity: critical / high / medium / low     │                    │
  │   └──────────────────────┬───────────────────────┘                    │
  │                          ▼                                            │
  │   ┌──────────────────────────────────────────────┐                    │
  │   │              FastAPI (REST)                    │                    │
  │   │                                               │                    │
  │   │  POST /api/v1/settlement/upload               │                    │
  │   │  POST /api/v1/settlement/load-transactions    │                    │
  │   │  POST /api/v1/reconciliation/run              │                    │
  │   │  GET  /api/v1/discrepancies                   │                    │
  │   │  GET  /api/v1/discrepancies/summary           │                    │
  │   │  GET  /api/v1/transactions/{id}/status         │                    │
  │   │  GET  /health                                 │                    │
  │   └──────────────────────────────────────────────┘                    │
  └──────────────────────────────────────────────────────────────────────┘
```

### Layers

| Layer | Location | Responsibility |
|-------|----------|----------------|
| **API** | `app/api/routes/` | HTTP endpoints, request validation, response serialization |
| **Services** | `app/services/` | Business logic - ingestion parsers, normalizer, reconciliation engine |
| **Models** | `app/models/` | SQLAlchemy ORM models (4 tables) |
| **Schemas** | `app/schemas/` | Pydantic request/response DTOs |
| **Core** | `app/core/` | Config, database session, logging |

---

## API Reference

### `GET /health`

Health check.

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

```json
{
    "status": "healthy",
    "service": "fleximarket-reconciler"
}
```

---

### `POST /api/v1/settlement/load-transactions`

Bulk-load expected transactions from JSON.

```bash
curl -s -X POST http://localhost:8000/api/v1/settlement/load-transactions \
  -H "Content-Type: application/json" \
  -d @data/expected_transactions.json | python3 -m json.tool
```

```json
{
    "loaded": 200,
    "skipped": 0,
    "message": "Loaded 200 expected transactions"
}
```

---

### `POST /api/v1/settlement/upload`

Upload a settlement file. The `processor` query param determines which parser is used.

```bash
# PayFlow (CSV)
curl -s -X POST "http://localhost:8000/api/v1/settlement/upload?processor=PayFlow" \
  -F "file=@data/settlement_payflow.csv" | python3 -m json.tool

# TransactMax (JSON)
curl -s -X POST "http://localhost:8000/api/v1/settlement/upload?processor=TransactMax" \
  -F "file=@data/settlement_transactmax.json" | python3 -m json.tool

# GlobalPay (XML)
curl -s -X POST "http://localhost:8000/api/v1/settlement/upload?processor=GlobalPay" \
  -F "file=@data/settlement_globalpay.xml" | python3 -m json.tool
```

```json
{
    "processor": "PayFlow",
    "filename": "settlement_payflow.csv",
    "entries_loaded": 56,
    "errors": []
}
```

---

### `POST /api/v1/reconciliation/run`

Trigger a reconciliation run. Compares expected transactions against settlement entries within the given date range.

```bash
curl -s -X POST http://localhost:8000/api/v1/reconciliation/run \
  -H "Content-Type: application/json" \
  -d '{"date_from": "2024-01-01", "date_to": "2024-01-14"}' | python3 -m json.tool
```

```json
{
    "id": "a1b2c3d4-...",
    "status": "completed",
    "date_range_start": "2024-01-01",
    "date_range_end": "2024-01-14",
    "total_transactions": 170,
    "matched_count": 140,
    "discrepancy_count": 30,
    "missing_count": 15
}
```

---

### `GET /api/v1/discrepancies`

List discrepancies with filtering and pagination.

**Query params:** `type`, `processor`, `severity`, `date_from`, `date_to`, `page`, `limit`

```bash
# First 10 discrepancies
curl -s "http://localhost:8000/api/v1/discrepancies?limit=10" | python3 -m json.tool

# Filter by type
curl -s "http://localhost:8000/api/v1/discrepancies?type=amount_mismatch" | python3 -m json.tool

# Filter by processor and severity
curl -s "http://localhost:8000/api/v1/discrepancies?processor=PayFlow&severity=high" | python3 -m json.tool
```

```json
[
    {
        "id": "...",
        "type": "amount_mismatch",
        "transaction_id": "TXN-BR-2024-000022",
        "processor_name": "PayFlow",
        "severity": "medium",
        "expected_amount": 4111.96,
        "actual_amount": 4107.86,
        "impact_usd": 0.82,
        "description": "Net amount mismatch: expected 4111.96, got 4107.86 (BRL)"
    }
]
```

---

### `GET /api/v1/discrepancies/summary`

Aggregated discrepancy statistics.

```bash
curl -s http://localhost:8000/api/v1/discrepancies/summary | python3 -m json.tool
```

```json
{
    "total_count": 35,
    "by_type": {
        "amount_mismatch": 10,
        "excessive_fee": 5,
        "missing_settlement": 15,
        "duplicate": 3,
        "fx_rate_deviation": 2
    },
    "by_processor": {
        "PayFlow": 11,
        "TransactMax": 14,
        "GlobalPay": 10
    },
    "by_severity": {
        "critical": 2,
        "high": 8,
        "medium": 15,
        "low": 10
    },
    "total_impact_usd": 1234.56
}
```

---

### `GET /api/v1/transactions/{transaction_id}/status`

Full status for a single transaction: expected data, settlement entries, and any discrepancies.

```bash
curl -s http://localhost:8000/api/v1/transactions/TXN-BR-2024-000006/status | python3 -m json.tool
```

```json
{
    "transaction_id": "TXN-BR-2024-000006",
    "transaction": {
        "amount": 178.4,
        "currency": "BRL",
        "processor_name": "PayFlow",
        "status": "captured",
        "transaction_date": "2024-01-05T12:30:00"
    },
    "settlements": [
        {
            "id": "...",
            "net_amount": 173.94,
            "gross_amount": 178.4,
            "status": "SETTLED",
            "settlement_date": "2024-01-08",
            "processor_name": "PayFlow"
        }
    ],
    "discrepancies": [],
    "settlement_count": 1,
    "discrepancy_count": 0
}
```

---

## Test Data

The `scripts/generate_test_data.py` script (deterministic, `seed=42`) produces:

| File | Description |
|------|-------------|
| `data/expected_transactions.json` | 200 transactions across 3 processors, 4 currencies (BRL, MXN, COP, CLP) |
| `data/settlement_payflow.csv` | PayFlow settlement report (CSV format) |
| `data/settlement_transactmax.json` | TransactMax settlement report (JSON format) |
| `data/settlement_globalpay.xml` | GlobalPay settlement report (XML format) |
| `data/discrepancy_manifest.json` | Manifest of every planted discrepancy (ground truth) |

### Planted Discrepancies

| Type | Count | Description |
|------|-------|-------------|
| Amount mismatches | 10 | Net amount differs from expected (shortages of $2-$50 in local currency) |
| Excessive fees | 5 | Processing fees 1.5x-2x higher than configured rate |
| Missing settlements | 15 | Transactions present in expected data but absent from settlement files |
| Duplicates | 3 | Same transaction appears twice in a settlement file (one per processor) |
| FX rate deviations | 2 | Exchange rate >5% off from expected (GlobalPay only) |
| **Total** | **35** | |

Processors and currencies:

- **PayFlow** (CSV): Brazil (BRL), Mexico (MXN) -- 2.5% fee
- **TransactMax** (JSON): Colombia (COP), Chile (CLP) -- 3.2% fee
- **GlobalPay** (XML): Mexico (MXN), Colombia (COP) -- 2.8% fee

---

## Running Tests

The full suite has **146 tests** across 5 test modules and runs in under 1 second.

```bash
# Run everything
make test

# Individual suites
make test-data              # Data generation validation (30 tests)
make test-ingestion         # CSV, JSON, XML parsers + normalizer (74 tests)
make test-normalizer        # Normalizer unit tests (58 tests)
make test-reconciliation    # Matcher + rules engine (25 tests)
make test-api               # API integration tests (11 tests)

# Fast feedback
make test-fast              # Parallel execution (all CPU cores)
make test-live              # Stop on first failure, short output
make test-failed            # Re-run only last failures
make test-watch             # File-watcher auto-rerun

# Coverage
make test-coverage          # Terminal + HTML report (htmlcov/index.html)
make test-coverage-quick    # Terminal only
```

Tests use **SQLite in-memory** databases (no Docker required for testing).

---

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make help` | Show all available targets |
| `make install` | Create venv and install dependencies |
| `make setup` | Full setup: install + db-up |
| `make all` | Setup + generate data + run tests |
| `make db-up` | Start PostgreSQL containers (dev + test) |
| `make db-down` | Stop PostgreSQL containers |
| `make db-reset` | Destroy volumes and recreate databases |
| `make run` | Dev server with hot reload (port 8000) |
| `make run-prod` | Production server (4 workers) |
| `make generate-data` | Generate all test data files |
| `make validate-data` | Validate test data integrity |
| `make demo` | Run end-to-end demo script |
| `make clean` | Remove caches and generated files |

---

## Architecture Decisions & Trade-offs

### 1. Python + FastAPI (vs Go / Node.js)

**Decision:** Python with FastAPI for the web layer.

**Rationale:** FastAPI gives us automatic OpenAPI docs, Pydantic validation on every request, and async support out of the box. For a reconciliation engine that's I/O-bound (database queries, file parsing), Python's ecosystem is a good fit. Go would offer better raw throughput but at the cost of more boilerplate for JSON/XML parsing and less expressive data validation. Node.js was a reasonable alternative but Python's data-processing libraries (decimal handling, XML/CSV stdlib) are more mature for financial calculations.

### 2. PostgreSQL for production, SQLite for tests

**Decision:** PostgreSQL as the production database, SQLite in-memory for the test suite.

**Rationale:** PostgreSQL provides the ACID guarantees, decimal precision, and concurrent access that a financial reconciliation system needs. Tests use SQLite in-memory to eliminate Docker as a test dependency, keeping the feedback loop under 1 second for 146 tests. The ORM layer (SQLAlchemy) abstracts the differences. The trade-off is that we can't test Postgres-specific features (e.g., `JSONB` queries) in unit tests, but our integration tests cover the critical paths.

### 3. Layered architecture (vs microservices)

**Decision:** Single-service layered architecture (API -> Services -> Models).

**Rationale:** For a take-home exercise and a system of this scope, a monolith with clear layer boundaries is the right call. Each layer has a single responsibility: routes handle HTTP, services handle business logic, models handle persistence. This makes it easy to test each layer independently. If this scaled to production, the ingestion layer and reconciliation engine would be natural extraction points for separate services.

### 4. Parser-per-processor with shared normalizer

**Decision:** Dedicated parser for each file format (CSV, JSON, XML) feeding into a single normalizer that outputs a unified schema.

**Rationale:** Payment processors will never agree on a format. By isolating format-specific parsing from business logic, adding a new processor is a single new parser class -- the normalizer, reconciliation engine, and API remain untouched. This is the Strategy pattern in practice.

### 5. Synchronous request handling (vs async workers / queues)

**Decision:** Reconciliation runs synchronously within the HTTP request.

**Rationale:** With 200 transactions, reconciliation completes in milliseconds. Adding Celery/Redis would be overengineering for this scale. The `POST /reconciliation/run` endpoint blocks until complete and returns the report directly. For production scale (millions of transactions), we'd move to an async architecture: the endpoint would enqueue a job, return a `202 Accepted` with a job ID, and the client would poll or receive a webhook on completion.

### 6. Configurable thresholds via environment variables

**Decision:** All reconciliation thresholds (fee tolerance, amount tolerance, FX rate tolerance, severity brackets) are in `app/core/config.py` and overridable via `.env`.

**Rationale:** Different markets and processors have different acceptable tolerances. Hard-coding these values would require code changes and redeployment for tuning. With Pydantic Settings, ops can adjust thresholds without touching code.

### 7. Deterministic test data generation (seed=42)

**Decision:** A single script generates all test data with a fixed random seed, plus a manifest of every planted discrepancy.

**Rationale:** Reproducibility is critical for debugging. Any developer can regenerate the exact same data and know exactly which discrepancies the engine should find. The manifest acts as a ground-truth file for validating reconciliation correctness.

---

## What I'd Add With More Time

- **Async job queue** -- Celery + Redis for reconciliation runs, with webhook/polling for status. Needed at scale.
- **Streaming file upload** -- For 100MB+ settlement files, stream-parse instead of loading into memory.
- **Authentication & RBAC** -- API keys or OAuth2 scopes (e.g., `reconciliation:write` vs `reports:read`).
- **Audit log** -- Immutable log of every reconciliation run, who triggered it, what changed.
- **Alerting** -- Webhook/Slack/PagerDuty integration when critical discrepancies are detected.
- **Retry & idempotency** -- Idempotent uploads (hash-based dedup), retry logic for transient DB failures.
- **Database migrations** -- Alembic is in `requirements.txt` but migrations aren't wired up yet; currently using `create_all()`.
- **CI/CD pipeline** -- GitHub Actions for lint, test, build Docker image, deploy.
- **Prometheus metrics** -- Request latency, reconciliation duration, discrepancy counts as Prometheus gauges.
- **CSV/PDF export** -- Download discrepancy reports as CSV or PDF for finance teams.

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.9+ |
| Web framework | FastAPI | 0.115.0 |
| ASGI server | Uvicorn | 0.30.6 |
| ORM | SQLAlchemy | 2.0.35 |
| Database | PostgreSQL | 16 (Alpine) |
| Validation | Pydantic | 2.9.2 |
| Config | pydantic-settings | 2.5.2 |
| XML parsing | lxml | 5.3.0 |
| Testing | pytest | 8.3.3 |
| Test coverage | pytest-cov | 7.0.0 |
| Parallel tests | pytest-xdist | 3.8.0 |
| HTTP test client | httpx | 0.27.2 |
| Containers | Docker Compose | 3.8 |
