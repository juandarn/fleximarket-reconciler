#!/bin/bash
# ===========================================================================
# FlexiMarket Settlement Reconciliation Engine - End-to-End Demo
# ===========================================================================
#
# Prerequisites:
#   1. make setup        (install deps + start PostgreSQL)
#   2. make generate-data (generate test data files)
#   3. make run          (start server in another terminal)
#
# Usage:
#   ./scripts/demo.sh
#   make demo
#
# ===========================================================================

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RESET='\033[0m'

step=0

run_step() {
    step=$((step + 1))
    echo ""
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${BOLD}  Step ${step}: $1${RESET}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
}

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║  FlexiMarket Settlement Reconciliation Engine - Demo    ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Target: ${BOLD}${BASE_URL}${RESET}"

# ── Step 1: Health Check ──────────────────────────────────────────────────

run_step "Health Check"
echo -e "${YELLOW}GET /health${RESET}"
curl -s "$BASE_URL/health" | python3 -m json.tool

# ── Step 2: Load Expected Transactions ────────────────────────────────────

run_step "Load expected transactions (200 txns, 4 currencies, 3 processors)"
echo -e "${YELLOW}POST /api/v1/settlement/load-transactions${RESET}"
curl -s -X POST "$BASE_URL/api/v1/settlement/load-transactions" \
  -H "Content-Type: application/json" \
  -d @data/expected_transactions.json | python3 -m json.tool

# ── Step 3: Upload PayFlow CSV ────────────────────────────────────────────

run_step "Upload PayFlow settlement (CSV format)"
echo -e "${YELLOW}POST /api/v1/settlement/upload?processor=PayFlow${RESET}"
curl -s -X POST "$BASE_URL/api/v1/settlement/upload?processor=PayFlow" \
  -F "file=@data/settlement_payflow.csv" | python3 -m json.tool

# ── Step 4: Upload TransactMax JSON ───────────────────────────────────────

run_step "Upload TransactMax settlement (JSON format)"
echo -e "${YELLOW}POST /api/v1/settlement/upload?processor=TransactMax${RESET}"
curl -s -X POST "$BASE_URL/api/v1/settlement/upload?processor=TransactMax" \
  -F "file=@data/settlement_transactmax.json" | python3 -m json.tool

# ── Step 5: Upload GlobalPay XML ──────────────────────────────────────────

run_step "Upload GlobalPay settlement (XML format)"
echo -e "${YELLOW}POST /api/v1/settlement/upload?processor=GlobalPay${RESET}"
curl -s -X POST "$BASE_URL/api/v1/settlement/upload?processor=GlobalPay" \
  -F "file=@data/settlement_globalpay.xml" | python3 -m json.tool

# ── Step 6: Run Reconciliation ────────────────────────────────────────────

run_step "Run reconciliation (2024-01-01 to 2024-01-14)"
echo -e "${YELLOW}POST /api/v1/reconciliation/run${RESET}"
curl -s -X POST "$BASE_URL/api/v1/reconciliation/run" \
  -H "Content-Type: application/json" \
  -d '{"date_from": "2024-01-01", "date_to": "2024-01-14"}' | python3 -m json.tool

# ── Step 7: Discrepancy Summary ───────────────────────────────────────────

run_step "Discrepancy summary (aggregated stats)"
echo -e "${YELLOW}GET /api/v1/discrepancies/summary${RESET}"
curl -s "$BASE_URL/api/v1/discrepancies/summary" | python3 -m json.tool

# ── Step 8: List Discrepancies ────────────────────────────────────────────

run_step "List discrepancies (first 10)"
echo -e "${YELLOW}GET /api/v1/discrepancies?limit=10${RESET}"
curl -s "$BASE_URL/api/v1/discrepancies?limit=10" | python3 -m json.tool

# ── Step 9: Transaction Status ────────────────────────────────────────────

run_step "Check individual transaction status"
echo -e "${YELLOW}GET /api/v1/transactions/TXN-BR-2024-000006/status${RESET}"
curl -s "$BASE_URL/api/v1/transactions/TXN-BR-2024-000006/status" | python3 -m json.tool

# ── Done ──────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║  Demo Complete                                          ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Interactive API docs:  ${BOLD}${BASE_URL}/docs${RESET}"
echo -e "  ReDoc:                 ${BOLD}${BASE_URL}/redoc${RESET}"
echo ""
