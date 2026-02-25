"""Tests to validate the generated test data files are correct and complete."""

import csv
import json
import os
from xml.etree import ElementTree

import pytest

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


@pytest.fixture
def expected_transactions():
    with open(os.path.join(DATA_DIR, "expected_transactions.json")) as f:
        return json.load(f)


@pytest.fixture
def manifest():
    with open(os.path.join(DATA_DIR, "discrepancy_manifest.json")) as f:
        return json.load(f)


@pytest.fixture
def payflow_csv():
    rows = []
    with open(os.path.join(DATA_DIR, "settlement_payflow.csv")) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


@pytest.fixture
def transactmax_json():
    with open(os.path.join(DATA_DIR, "settlement_transactmax.json")) as f:
        return json.load(f)


@pytest.fixture
def globalpay_xml():
    tree = ElementTree.parse(os.path.join(DATA_DIR, "settlement_globalpay.xml"))
    return tree.getroot()


# --- Expected Transactions Tests ---


class TestExpectedTransactions:
    def test_has_200_transactions(self, expected_transactions):
        assert len(expected_transactions) == 200

    def test_all_required_fields_present(self, expected_transactions):
        required_fields = [
            "transaction_id",
            "amount",
            "currency",
            "expected_fee_percent",
            "expected_fee_amount",
            "expected_net_amount",
            "processor_name",
            "country",
            "transaction_date",
            "status",
        ]
        for txn in expected_transactions:
            for field in required_fields:
                assert field in txn, f"Missing field {field} in {txn['transaction_id']}"

    def test_valid_currencies(self, expected_transactions):
        valid = {"BRL", "MXN", "COP", "CLP"}
        for txn in expected_transactions:
            assert txn["currency"] in valid, f"Invalid currency {txn['currency']}"

    def test_valid_processors(self, expected_transactions):
        valid = {"PayFlow", "TransactMax", "GlobalPay"}
        for txn in expected_transactions:
            assert txn["processor_name"] in valid

    def test_valid_statuses(self, expected_transactions):
        valid = {"captured", "refunded", "failed"}
        for txn in expected_transactions:
            assert txn["status"] in valid

    def test_unique_transaction_ids(self, expected_transactions):
        ids = [txn["transaction_id"] for txn in expected_transactions]
        assert len(ids) == len(set(ids)), "Duplicate transaction IDs found"

    def test_fee_calculation_correct(self, expected_transactions):
        for txn in expected_transactions:
            expected_fee = round(txn["amount"] * txn["expected_fee_percent"] / 100, 2)
            # Tolerance of 1.0 for large COP/CLP amounts where float rounding differs
            assert abs(txn["expected_fee_amount"] - expected_fee) < 1.0, (
                f"Fee mismatch for {txn['transaction_id']}: "
                f"expected {expected_fee}, got {txn['expected_fee_amount']}"
            )

    def test_net_amount_correct(self, expected_transactions):
        for txn in expected_transactions:
            expected_net = round(txn["amount"] - txn["expected_fee_amount"], 2)
            assert abs(txn["expected_net_amount"] - expected_net) < 0.02

    def test_processor_country_mapping(self, expected_transactions):
        """PayFlow=BR/MX, TransactMax=CO/CL, GlobalPay=MX/CO."""
        valid_mapping = {
            "PayFlow": {"BR", "MX"},
            "TransactMax": {"CO", "CL"},
            "GlobalPay": {"MX", "CO"},
        }
        for txn in expected_transactions:
            assert txn["country"] in valid_mapping[txn["processor_name"]]


# --- Settlement File Tests ---


class TestPayFlowCSV:
    def test_file_exists(self):
        assert os.path.exists(os.path.join(DATA_DIR, "settlement_payflow.csv"))

    def test_has_rows(self, payflow_csv):
        assert len(payflow_csv) > 0

    def test_required_columns(self, payflow_csv):
        required = [
            "settlement_id",
            "transaction_ref",
            "txn_date",
            "settle_date",
            "original_amount",
            "currency",
            "processing_fee",
            "interchange_fee",
            "net_amount",
            "status",
        ]
        for col in required:
            assert col in payflow_csv[0], f"Missing column {col}"

    def test_all_status_settled(self, payflow_csv):
        for row in payflow_csv:
            assert row["status"] == "SETTLED"

    def test_valid_currencies(self, payflow_csv):
        for row in payflow_csv:
            assert row["currency"] in {"BRL", "MXN"}


class TestTransactMaxJSON:
    def test_file_exists(self):
        assert os.path.exists(os.path.join(DATA_DIR, "settlement_transactmax.json"))

    def test_has_settlements(self, transactmax_json):
        assert "settlements" in transactmax_json
        assert len(transactmax_json["settlements"]) > 0

    def test_required_fields(self, transactmax_json):
        required = [
            "id",
            "original_transaction_id",
            "transaction_date",
            "settlement_date",
            "gross_amount",
            "currency",
            "total_fees",
            "net_amount",
            "settlement_status",
        ]
        for stl in transactmax_json["settlements"]:
            for field in required:
                assert field in stl, f"Missing {field}"

    def test_valid_currencies(self, transactmax_json):
        for stl in transactmax_json["settlements"]:
            assert stl["currency"] in {"COP", "CLP"}


class TestGlobalPayXML:
    def test_file_exists(self):
        assert os.path.exists(os.path.join(DATA_DIR, "settlement_globalpay.xml"))

    def test_has_settlements(self, globalpay_xml):
        settlements = globalpay_xml.findall("Settlement")
        assert len(settlements) > 0

    def test_required_elements(self, globalpay_xml):
        required = [
            "SettlementId",
            "TransactionRef",
            "OriginalAmount",
            "FeeAmount",
            "NetAmount",
            "SettlementDate",
            "Status",
        ]
        for stl in globalpay_xml.findall("Settlement"):
            for elem_name in required:
                assert stl.find(elem_name) is not None, f"Missing element {elem_name}"

    def test_has_fx_rate(self, globalpay_xml):
        for stl in globalpay_xml.findall("Settlement"):
            fx = stl.find("FxRate")
            assert fx is not None, "Missing FxRate element"
            assert float(fx.text) > 0


# --- Discrepancy Manifest Tests ---


class TestDiscrepancyManifest:
    def test_has_all_types(self, manifest):
        assert "amount_mismatches" in manifest
        assert "excessive_fees" in manifest
        assert "missing_settlements" in manifest
        assert "duplicates" in manifest
        assert "currency_issues" in manifest

    def test_minimum_amount_mismatches(self, manifest):
        assert len(manifest["amount_mismatches"]) >= 5

    def test_minimum_excessive_fees(self, manifest):
        assert len(manifest["excessive_fees"]) >= 3

    def test_minimum_missing_settlements(self, manifest):
        assert len(manifest["missing_settlements"]) >= 10

    def test_minimum_duplicates(self, manifest):
        assert len(manifest["duplicates"]) >= 2

    def test_has_currency_issues(self, manifest):
        assert len(manifest["currency_issues"]) >= 1

    def test_missing_settlements_are_valid_transactions(
        self, manifest, expected_transactions
    ):
        """All missing settlement txn IDs should exist in expected transactions."""
        expected_ids = {txn["transaction_id"] for txn in expected_transactions}
        for item in manifest["missing_settlements"]:
            assert item["transaction_id"] in expected_ids, (
                f"Missing settlement {item['transaction_id']} not in expected transactions"
            )

    def test_duplicates_exist_in_settlement_files(
        self, manifest, payflow_csv, transactmax_json, globalpay_xml
    ):
        """Duplicate txn IDs should appear multiple times in their processor file."""
        # Build lookup of txn_id -> count per processor
        pf_refs = [row["transaction_ref"] for row in payflow_csv]
        tm_refs = [
            s["original_transaction_id"] for s in transactmax_json["settlements"]
        ]
        gp_refs = [
            s.find("TransactionRef").text for s in globalpay_xml.findall("Settlement")
        ]

        for dup in manifest["duplicates"]:
            txn_id = dup["transaction_id"]
            processor = dup["processor"]
            if processor == "PayFlow":
                count = pf_refs.count(txn_id)
            elif processor == "TransactMax":
                count = tm_refs.count(txn_id)
            else:
                count = gp_refs.count(txn_id)
            assert count >= 2, (
                f"Duplicate {txn_id} in {processor} only appears {count} time(s)"
            )
