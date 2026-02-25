.PHONY: help install db-up db-down db-reset run test test-verbose lint generate-data clean demo

# Default target
help: ## Show this help message
	@echo "FlexiMarket Settlement Reconciliation Engine"
	@echo "============================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ---- Setup ----

install: ## Install Python dependencies in venv
	python3 -m venv venv
	./venv/bin/pip install -r requirements.txt

# ---- Database ----

db-up: ## Start PostgreSQL containers (dev + test)
	docker compose up -d

db-down: ## Stop PostgreSQL containers
	docker compose down

db-reset: ## Reset database (destroy volumes and recreate)
	docker compose down -v
	docker compose up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@sleep 3
	@echo "Database reset complete"

# ---- Application ----

run: ## Run the FastAPI server (dev mode with hot reload)
	./venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-prod: ## Run the FastAPI server (production mode)
	./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# ---- Testing ----

test: ## Run all tests
	./venv/bin/python -m pytest tests/ -v

test-data: ## Run only test data validation tests
	./venv/bin/python -m pytest tests/test_data_generation.py -v

test-ingestion: ## Run only ingestion tests
	./venv/bin/python -m pytest tests/test_ingestion/ -v

test-reconciliation: ## Run only reconciliation tests
	./venv/bin/python -m pytest tests/test_reconciliation/ -v

test-api: ## Run only API tests
	./venv/bin/python -m pytest tests/test_api/ -v

test-coverage: ## Run tests with coverage report
	./venv/bin/python -m pytest tests/ -v --tb=short

# ---- Data Generation ----

generate-data: ## Generate test data files (CSV, JSON, XML)
	./venv/bin/python scripts/generate_test_data.py

# ---- Demo ----

demo: ## Run the end-to-end demo script
	@echo "Running end-to-end demo..."
	./scripts/demo.sh

# ---- Utilities ----

clean: ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov

# ---- Quick Start ----

setup: install db-up ## Full setup: install deps + start DB
	@echo ""
	@echo "Setup complete! Run 'make run' to start the server."
	@echo "API docs available at http://localhost:8000/docs"

all: setup generate-data test ## Full setup + generate data + run tests
	@echo ""
	@echo "All done! Everything is green."
