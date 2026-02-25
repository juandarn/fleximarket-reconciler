.PHONY: help install db-up db-down db-reset run run-prod \
       test test-data test-ingestion test-normalizer test-reconciliation test-api \
       test-coverage test-fast test-live test-watch test-failed \
       validate-data generate-data demo clean setup all \
       docker-build docker-up docker-down docker-logs docker-demo

# Default target
help: ## Show this help message
	@echo "FlexiMarket Settlement Reconciliation Engine"
	@echo "============================================="
	@echo ""
	@echo "  Setup & Infrastructure"
	@echo "  ----------------------"
	@grep -E '^(install|setup|all|db-|run|clean):.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Testing"
	@echo "  -------"
	@grep -E '^test[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[33m%-24s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Data & Validation"
	@echo "  -----------------"
	@grep -E '^(generate-data|validate-data|demo):.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[32m%-24s\033[0m %s\n", $$1, $$2}'
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

# ==============================================================================
# TESTING
# ==============================================================================

# ---- Run by suite ----

test: ## Run ALL tests with verbose output
	./venv/bin/python -m pytest tests/ -v

test-data: ## Run only test data validation tests
	./venv/bin/python -m pytest tests/test_data_generation.py -v

test-ingestion: ## Run only ingestion parser tests (CSV, JSON, XML)
	./venv/bin/python -m pytest tests/test_ingestion/ -v

test-normalizer: ## Run only normalizer unit tests
	./venv/bin/python -m pytest tests/test_ingestion/test_normalizer.py -v

test-reconciliation: ## Run only reconciliation tests
	./venv/bin/python -m pytest tests/test_reconciliation/ -v

test-api: ## Run only API integration tests
	./venv/bin/python -m pytest tests/test_api/ -v

# ---- Live / fast feedback ----

test-fast: ## Run tests in parallel (uses all CPU cores)
	./venv/bin/python -m pytest tests/ -v -n auto

test-failed: ## Re-run only tests that failed last time
	./venv/bin/python -m pytest tests/ -v --lf

test-live: ## Run tests with short output, stop on first failure
	./venv/bin/python -m pytest tests/ --tb=short -x -q

test-watch: ## Watch for file changes and re-run tests automatically
	@echo "Watching for changes... (Ctrl+C to stop)"
	@echo "================================================"
	./venv/bin/python -c "\
	import subprocess, sys; \
	from watchfiles import run_process; \
	run_process( \
		'app', 'tests', \
		target=lambda: subprocess.run( \
			[sys.executable, '-m', 'pytest', 'tests/', '--tb=short', '-x', '-q'], \
			cwd='.' \
		), \
		watch_filter=lambda change, path: path.endswith('.py'), \
	)"

# ---- Coverage ----

test-coverage: ## Run tests with coverage report (terminal + HTML)
	./venv/bin/python -m pytest tests/ -v \
		--cov=app \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-branch
	@echo ""
	@echo "HTML report: open htmlcov/index.html"

test-coverage-quick: ## Run tests with coverage (terminal only, no HTML)
	./venv/bin/python -m pytest tests/ -q \
		--cov=app \
		--cov-report=term-missing \
		--cov-branch

# ==============================================================================
# DATA GENERATION & VALIDATION
# ==============================================================================

generate-data: ## Generate test data files (CSV, JSON, XML)
	./venv/bin/python scripts/generate_test_data.py

validate-data: ## Validate that test data files are consistent and correct
	@echo "Validating test data integrity..."
	@echo ""
	./venv/bin/python -m pytest tests/test_data_generation.py -v --tb=short
	@echo ""
	@echo "Validating normalizer handles all fixture data..."
	./venv/bin/python -m pytest tests/test_ingestion/test_normalizer.py::TestNormalizerWithFixtureData -v --tb=short
	@echo ""
	@echo "Validating all parsers against fixture files..."
	./venv/bin/python -m pytest tests/test_ingestion/ -v --tb=short -k "ValidCsv or ValidJson or ValidXml"
	@echo ""
	@echo "All data validation checks passed!"

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

# ==============================================================================
# DOCKER (Full stack)
# ==============================================================================

docker-build: ## Build the Docker image for the app
	docker compose build app

docker-up: ## Start everything in Docker (DB + App)
	docker compose up -d
	@echo ""
	@echo "Waiting for services to be ready..."
	@sleep 5
	@echo "FlexiMarket Reconciler running at http://localhost:8000"
	@echo "API docs at http://localhost:8000/docs"
	@echo "PostgreSQL at localhost:5432"

docker-down: ## Stop all Docker containers
	docker compose down

docker-logs: ## Tail logs from the app container
	docker compose logs -f app

docker-demo: docker-up ## Run full Docker stack + E2E demo
	@echo ""
	@echo "Running E2E demo against Docker stack..."
	@sleep 2
	./scripts/demo.sh
