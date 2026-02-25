#!/usr/bin/env python3
"""
Generate test data for the FlexiMarket multi-currency settlement reconciliation engine.

Creates:
  - data/expected_transactions.json   (200 transactions FlexiMarket expects)
  - data/settlement_payflow.csv       (PayFlow settlement report with planted discrepancies)
  - data/settlement_transactmax.json  (TransactMax settlement report with planted discrepancies)
  - data/settlement_globalpay.xml     (GlobalPay settlement report with planted discrepancies)
  - data/discrepancy_manifest.json    (manifest of every planted discrepancy)

Reproducible: uses random.seed(42).
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED = 42
random.seed(SEED)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Processor -> (countries, fee_percent)
PROCESSOR_CONFIG: dict[str, dict[str, Any]] = {
    "PayFlow": {
        "countries": [("BR", "BRL", 40), ("MX", "MXN", 30)],
        "fee_percent": 2.5,
        "settle_lag_days": 3,
    },
    "TransactMax": {
        "countries": [("CO", "COP", 35), ("CL", "CLP", 30)],
        "fee_percent": 3.2,
        "settle_lag_days": 5,
    },
    "GlobalPay": {
        "countries": [("MX", "MXN", 35), ("CO", "COP", 30)],
        "fee_percent": 2.8,
        "settle_lag_days": 4,
    },
}

# Currency -> (min_amount, max_amount, decimals)
CURRENCY_RANGES: dict[str, tuple[float, float, int]] = {
    "BRL": (20.0, 5000.0, 2),
    "MXN": (50.0, 15000.0, 2),
    "COP": (5000.0, 2000000.0, 0),  # COP rarely uses decimals
    "CLP": (1000.0, 500000.0, 0),  # CLP rarely uses decimals
}

# Approximate FX rates to USD
FX_RATES: dict[str, float] = {
    "BRL": 0.20,
    "MXN": 0.058824,
    "COP": 0.00025,
    "CLP": 0.0011,
}

STATUS_WEIGHTS = [("captured", 0.85), ("refunded", 0.10), ("failed", 0.05)]

DATE_START = datetime(2024, 1, 1)
DATE_END = datetime(2024, 1, 14)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _round_money(value: float, decimals: int = 2) -> float:
    """Round to the given decimal places, useful for currency amounts."""
    return round(value, decimals)


def _random_datetime(start: datetime, end: datetime) -> datetime:
    """Return a random datetime between start and end."""
    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=random_seconds)


def _weighted_choice(choices: list[tuple[str, float]]) -> str:
    """Pick from a list of (value, weight) tuples."""
    values, weights = zip(*choices)
    return random.choices(values, weights=weights, k=1)[0]


def _realistic_amount(currency: str) -> float:
    """Generate a realistic-looking amount for the given currency."""
    lo, hi, decimals = CURRENCY_RANGES[currency]
    raw = random.uniform(lo, hi)
    if decimals == 0:
        # For COP/CLP make amounts that look like real prices (multiples of ~100/50)
        raw = round(raw / 50) * 50
        if raw < lo:
            raw = lo
        return float(raw)
    # For BRL/MXN add realistic cents
    return _round_money(raw, decimals)


# ---------------------------------------------------------------------------
# Step 1: Generate expected transactions
# ---------------------------------------------------------------------------


def generate_expected_transactions() -> list[dict[str, Any]]:
    """Generate 200 expected transaction records."""
    transactions: list[dict[str, Any]] = []
    global_counter = 0
    order_counter = 100000

    for processor_name, cfg in PROCESSOR_CONFIG.items():
        fee_pct = cfg["fee_percent"]
        for country, currency, count in cfg["countries"]:
            for _ in range(count):
                global_counter += 1
                order_counter += 1
                txn_id = f"TXN-{country}-2024-{global_counter:06d}"
                amount = _realistic_amount(currency)
                decimals = CURRENCY_RANGES[currency][2]
                fee_amount = _round_money(amount * fee_pct / 100, decimals)
                net_amount = _round_money(amount - fee_amount, decimals)
                txn_date = _random_datetime(DATE_START, DATE_END)
                status = _weighted_choice(STATUS_WEIGHTS)

                transactions.append(
                    {
                        "transaction_id": txn_id,
                        "amount": amount,
                        "currency": currency,
                        "expected_fee_percent": fee_pct,
                        "expected_fee_amount": fee_amount,
                        "expected_net_amount": net_amount,
                        "processor_name": processor_name,
                        "country": country,
                        "transaction_date": txn_date.isoformat(),
                        "status": status,
                        "metadata": {"order_id": f"ORD-{order_counter}"},
                    }
                )

    # Shuffle so they're not neatly grouped
    random.shuffle(transactions)
    return transactions


# ---------------------------------------------------------------------------
# Step 2: Settlement generators (with planted discrepancies)
# ---------------------------------------------------------------------------


class DiscrepancyManifest:
    """Collects all planted discrepancies for the manifest file."""

    def __init__(self) -> None:
        self.amount_mismatches: list[dict] = []
        self.excessive_fees: list[dict] = []
        self.missing_settlements: list[dict] = []
        self.duplicates: list[dict] = []
        self.currency_issues: list[dict] = []

    def to_dict(self) -> dict:
        return {
            "generated_at": datetime.now().isoformat(),
            "seed": SEED,
            "amount_mismatches": self.amount_mismatches,
            "excessive_fees": self.excessive_fees,
            "missing_settlements": self.missing_settlements,
            "duplicates": self.duplicates,
            "currency_issues": self.currency_issues,
        }


def _captured_txns_for_processor(
    transactions: list[dict], processor: str
) -> list[dict]:
    """Return only captured transactions for the given processor."""
    return [
        t
        for t in transactions
        if t["processor_name"] == processor and t["status"] == "captured"
    ]


# ---- PayFlow (CSV) -------------------------------------------------------


def generate_payflow_csv(
    transactions: list[dict], manifest: DiscrepancyManifest
) -> str:
    """Generate PayFlow settlement CSV content with planted discrepancies."""
    captured = _captured_txns_for_processor(transactions, "PayFlow")
    random.shuffle(captured)

    # Decide which transactions get discrepancies
    # We need at least 3 + 2 + 5 + 1 = 11 captured transactions; PayFlow has ~60
    available = list(captured)

    # 5 missing settlements: remove them from the output entirely
    missing = available[:5]
    for t in missing:
        manifest.missing_settlements.append(
            {
                "transaction_id": t["transaction_id"],
                "processor": "PayFlow",
                "expected_net": t["expected_net_amount"],
                "currency": t["currency"],
                "reason": "transaction not present in settlement file",
            }
        )
    included = available[5:]

    # Pick indices for other discrepancies from the included set
    random.shuffle(included)
    amount_mismatch_txns = included[:3]
    excessive_fee_txns = included[3:5]
    duplicate_txn = included[5]

    # Build rows
    rows: list[dict[str, Any]] = []
    stl_counter = 0

    for txn in included:
        stl_counter += 1
        settle_id = f"PF-STL-{stl_counter:05d}"
        txn_date = datetime.fromisoformat(txn["transaction_date"])
        settle_date = txn_date + timedelta(days=3)

        total_fee = txn["expected_fee_amount"]
        processing_fee = _round_money(
            total_fee * 0.60, CURRENCY_RANGES[txn["currency"]][2]
        )
        interchange_fee = _round_money(
            total_fee - processing_fee, CURRENCY_RANGES[txn["currency"]][2]
        )
        net_amount = txn["expected_net_amount"]

        # --- Plant discrepancies ---
        if txn in amount_mismatch_txns:
            decimals = CURRENCY_RANGES[txn["currency"]][2]
            shortage = _round_money(random.uniform(2, 50), decimals)
            original_net = net_amount
            net_amount = _round_money(net_amount - shortage, decimals)
            manifest.amount_mismatches.append(
                {
                    "transaction_id": txn["transaction_id"],
                    "processor": "PayFlow",
                    "expected_net": original_net,
                    "actual_net": net_amount,
                    "difference": _round_money(original_net - net_amount, decimals),
                    "currency": txn["currency"],
                }
            )

        if txn in excessive_fee_txns:
            decimals = CURRENCY_RANGES[txn["currency"]][2]
            multiplier = random.uniform(1.5, 2.0)
            original_processing = processing_fee
            original_interchange = interchange_fee
            processing_fee = _round_money(processing_fee * multiplier, decimals)
            interchange_fee = _round_money(interchange_fee * multiplier, decimals)
            net_amount = _round_money(
                txn["amount"] - processing_fee - interchange_fee, decimals
            )
            manifest.excessive_fees.append(
                {
                    "transaction_id": txn["transaction_id"],
                    "processor": "PayFlow",
                    "expected_total_fee": txn["expected_fee_amount"],
                    "actual_total_fee": _round_money(
                        processing_fee + interchange_fee, decimals
                    ),
                    "currency": txn["currency"],
                }
            )

        rows.append(
            {
                "settlement_id": settle_id,
                "transaction_ref": txn["transaction_id"],
                "txn_date": txn_date.strftime("%Y-%m-%d"),
                "settle_date": settle_date.strftime("%Y-%m-%d"),
                "original_amount": txn["amount"],
                "currency": txn["currency"],
                "processing_fee": processing_fee,
                "interchange_fee": interchange_fee,
                "net_amount": net_amount,
                "status": "SETTLED",
            }
        )

    # 1 duplicate: add duplicate_txn again with a different settlement_id
    stl_counter += 1
    dup_settle_id = f"PF-STL-{stl_counter:05d}"
    dup_txn_date = datetime.fromisoformat(duplicate_txn["transaction_date"])
    dup_settle_date = dup_txn_date + timedelta(days=3)
    dup_total_fee = duplicate_txn["expected_fee_amount"]
    dup_decimals = CURRENCY_RANGES[duplicate_txn["currency"]][2]
    dup_processing = _round_money(dup_total_fee * 0.60, dup_decimals)
    dup_interchange = _round_money(dup_total_fee - dup_processing, dup_decimals)

    rows.append(
        {
            "settlement_id": dup_settle_id,
            "transaction_ref": duplicate_txn["transaction_id"],
            "txn_date": dup_txn_date.strftime("%Y-%m-%d"),
            "settle_date": dup_settle_date.strftime("%Y-%m-%d"),
            "original_amount": duplicate_txn["amount"],
            "currency": duplicate_txn["currency"],
            "processing_fee": dup_processing,
            "interchange_fee": dup_interchange,
            "net_amount": duplicate_txn["expected_net_amount"],
            "status": "SETTLED",
        }
    )
    manifest.duplicates.append(
        {
            "transaction_id": duplicate_txn["transaction_id"],
            "processor": "PayFlow",
            "settlement_ids": [
                # find original settle_id
                next(
                    r["settlement_id"]
                    for r in rows
                    if r["transaction_ref"] == duplicate_txn["transaction_id"]
                ),
                dup_settle_id,
            ],
        }
    )

    return rows


# ---- TransactMax (JSON) ---------------------------------------------------


def generate_transactmax_json(
    transactions: list[dict], manifest: DiscrepancyManifest
) -> dict:
    """Generate TransactMax settlement JSON with planted discrepancies."""
    captured = _captured_txns_for_processor(transactions, "TransactMax")
    random.shuffle(captured)

    available = list(captured)

    # 7 missing
    missing = available[:7]
    for t in missing:
        manifest.missing_settlements.append(
            {
                "transaction_id": t["transaction_id"],
                "processor": "TransactMax",
                "expected_net": t["expected_net_amount"],
                "currency": t["currency"],
                "reason": "transaction not present in settlement file",
            }
        )
    included = available[7:]

    random.shuffle(included)
    amount_mismatch_txns = included[:4]
    excessive_fee_txns = included[4:6]
    duplicate_txn = included[6]

    settlements: list[dict] = []
    stl_counter = 0

    for txn in included:
        stl_counter += 1
        txn_date = datetime.fromisoformat(txn["transaction_date"])
        settle_date = txn_date + timedelta(days=5)
        decimals = CURRENCY_RANGES[txn["currency"]][2]

        total_fees = txn["expected_fee_amount"]
        net_amount = txn["expected_net_amount"]

        if txn in amount_mismatch_txns:
            shortage = _round_money(random.uniform(2, 50), decimals)
            if decimals == 0:
                shortage = round(shortage / 50) * 50
                if shortage < 50:
                    shortage = 50
            original_net = net_amount
            net_amount = _round_money(net_amount - shortage, decimals)
            manifest.amount_mismatches.append(
                {
                    "transaction_id": txn["transaction_id"],
                    "processor": "TransactMax",
                    "expected_net": original_net,
                    "actual_net": net_amount,
                    "difference": _round_money(original_net - net_amount, decimals),
                    "currency": txn["currency"],
                }
            )

        if txn in excessive_fee_txns:
            multiplier = random.uniform(1.5, 2.0)
            original_fee = total_fees
            total_fees = _round_money(total_fees * multiplier, decimals)
            net_amount = _round_money(txn["amount"] - total_fees, decimals)
            manifest.excessive_fees.append(
                {
                    "transaction_id": txn["transaction_id"],
                    "processor": "TransactMax",
                    "expected_total_fee": original_fee,
                    "actual_total_fee": total_fees,
                    "currency": txn["currency"],
                }
            )

        settlements.append(
            {
                "id": f"TM-STL-{stl_counter:05d}",
                "original_transaction_id": txn["transaction_id"],
                "transaction_date": txn_date.strftime("%Y-%m-%d"),
                "settlement_date": settle_date.strftime("%Y-%m-%d"),
                "gross_amount": txn["amount"],
                "currency": txn["currency"],
                "total_fees": total_fees,
                "net_amount": net_amount,
                "settlement_status": "completed",
            }
        )

    # Duplicate
    stl_counter += 1
    dup_txn_date = datetime.fromisoformat(duplicate_txn["transaction_date"])
    dup_settle_date = dup_txn_date + timedelta(days=5)
    dup_entry = {
        "id": f"TM-STL-{stl_counter:05d}",
        "original_transaction_id": duplicate_txn["transaction_id"],
        "transaction_date": dup_txn_date.strftime("%Y-%m-%d"),
        "settlement_date": dup_settle_date.strftime("%Y-%m-%d"),
        "gross_amount": duplicate_txn["amount"],
        "currency": duplicate_txn["currency"],
        "total_fees": duplicate_txn["expected_fee_amount"],
        "net_amount": duplicate_txn["expected_net_amount"],
        "settlement_status": "completed",
    }
    settlements.append(dup_entry)

    original_id = next(
        s["id"]
        for s in settlements
        if s["original_transaction_id"] == duplicate_txn["transaction_id"]
    )
    manifest.duplicates.append(
        {
            "transaction_id": duplicate_txn["transaction_id"],
            "processor": "TransactMax",
            "settlement_ids": [original_id, dup_entry["id"]],
        }
    )

    return {
        "report_date": "2024-01-18",
        "processor": "TransactMax",
        "settlements": settlements,
    }


# ---- GlobalPay (XML) ------------------------------------------------------


def generate_globalpay_xml(
    transactions: list[dict], manifest: DiscrepancyManifest
) -> str:
    """Generate GlobalPay settlement XML with planted discrepancies."""
    captured = _captured_txns_for_processor(transactions, "GlobalPay")
    random.shuffle(captured)

    available = list(captured)

    # 3 missing
    missing = available[:3]
    for t in missing:
        manifest.missing_settlements.append(
            {
                "transaction_id": t["transaction_id"],
                "processor": "GlobalPay",
                "expected_net": t["expected_net_amount"],
                "currency": t["currency"],
                "reason": "transaction not present in settlement file",
            }
        )
    included = available[3:]

    random.shuffle(included)
    amount_mismatch_txns = included[:3]
    excessive_fee_txns = included[3:4]
    duplicate_txn = included[4]
    currency_issue_txns = included[5:7]

    root = ET.Element("SettlementReport", processor="GlobalPay", date="2024-01-18")

    stl_counter = 0
    xml_entries: list[tuple[ET.Element, dict]] = []  # for tracking duplicates

    for txn in included:
        stl_counter += 1
        txn_date = datetime.fromisoformat(txn["transaction_date"])
        settle_date = txn_date + timedelta(days=4)
        decimals = CURRENCY_RANGES[txn["currency"]][2]
        currency = txn["currency"]

        fee_amount = txn["expected_fee_amount"]
        net_amount = txn["expected_net_amount"]
        fx_rate = FX_RATES[currency]

        # --- Plant discrepancies ---
        if txn in amount_mismatch_txns:
            shortage = _round_money(random.uniform(2, 50), decimals)
            if decimals == 0:
                shortage = round(shortage / 50) * 50
                if shortage < 50:
                    shortage = 50
            original_net = net_amount
            net_amount = _round_money(net_amount - shortage, decimals)
            manifest.amount_mismatches.append(
                {
                    "transaction_id": txn["transaction_id"],
                    "processor": "GlobalPay",
                    "expected_net": original_net,
                    "actual_net": net_amount,
                    "difference": _round_money(original_net - net_amount, decimals),
                    "currency": currency,
                }
            )

        if txn in excessive_fee_txns:
            multiplier = random.uniform(1.5, 2.0)
            original_fee = fee_amount
            fee_amount = _round_money(fee_amount * multiplier, decimals)
            net_amount = _round_money(txn["amount"] - fee_amount, decimals)
            manifest.excessive_fees.append(
                {
                    "transaction_id": txn["transaction_id"],
                    "processor": "GlobalPay",
                    "expected_total_fee": original_fee,
                    "actual_total_fee": fee_amount,
                    "currency": currency,
                }
            )

        if txn in currency_issue_txns:
            # Make FX rate >5% off from the normal rate
            direction = random.choice([-1, 1])
            deviation = random.uniform(0.06, 0.15)  # 6-15% off
            bad_fx_rate = round(fx_rate * (1 + direction * deviation), 6)
            manifest.currency_issues.append(
                {
                    "transaction_id": txn["transaction_id"],
                    "processor": "GlobalPay",
                    "currency": currency,
                    "expected_fx_rate": fx_rate,
                    "actual_fx_rate": bad_fx_rate,
                    "deviation_percent": round(
                        abs(bad_fx_rate - fx_rate) / fx_rate * 100, 2
                    ),
                }
            )
            fx_rate = bad_fx_rate

        # Build XML element
        settlement_el = ET.SubElement(root, "Settlement")
        ET.SubElement(settlement_el, "SettlementId").text = f"GP-2024-{stl_counter:04d}"
        ET.SubElement(settlement_el, "TransactionRef").text = txn["transaction_id"]

        orig_amount_el = ET.SubElement(
            settlement_el, "OriginalAmount", currency=currency
        )
        orig_amount_el.text = f"{txn['amount']:.{max(decimals, 2)}f}"

        ET.SubElement(
            settlement_el, "FeeAmount"
        ).text = f"{fee_amount:.{max(decimals, 2)}f}"

        net_el = ET.SubElement(settlement_el, "NetAmount", currency=currency)
        net_el.text = f"{net_amount:.{max(decimals, 2)}f}"

        fx_el = ET.SubElement(settlement_el, "FxRate", toCurrency="USD")
        fx_el.text = f"{fx_rate:.6f}"

        ET.SubElement(settlement_el, "SettlementDate").text = settle_date.strftime(
            "%Y-%m-%d"
        )
        ET.SubElement(settlement_el, "Status").text = "COMPLETED"

        xml_entries.append((settlement_el, txn))

    # Duplicate
    stl_counter += 1
    dup_txn_date = datetime.fromisoformat(duplicate_txn["transaction_date"])
    dup_settle_date = dup_txn_date + timedelta(days=4)
    dup_currency = duplicate_txn["currency"]
    dup_decimals = CURRENCY_RANGES[dup_currency][2]

    dup_el = ET.SubElement(root, "Settlement")
    dup_stl_id = f"GP-2024-{stl_counter:04d}"
    ET.SubElement(dup_el, "SettlementId").text = dup_stl_id
    ET.SubElement(dup_el, "TransactionRef").text = duplicate_txn["transaction_id"]

    dup_orig = ET.SubElement(dup_el, "OriginalAmount", currency=dup_currency)
    dup_orig.text = f"{duplicate_txn['amount']:.{max(dup_decimals, 2)}f}"

    ET.SubElement(
        dup_el, "FeeAmount"
    ).text = f"{duplicate_txn['expected_fee_amount']:.{max(dup_decimals, 2)}f}"

    dup_net_el = ET.SubElement(dup_el, "NetAmount", currency=dup_currency)
    dup_net_el.text = f"{duplicate_txn['expected_net_amount']:.{max(dup_decimals, 2)}f}"

    dup_fx_el = ET.SubElement(dup_el, "FxRate", toCurrency="USD")
    dup_fx_el.text = f"{FX_RATES[dup_currency]:.6f}"

    ET.SubElement(dup_el, "SettlementDate").text = dup_settle_date.strftime("%Y-%m-%d")
    ET.SubElement(dup_el, "Status").text = "COMPLETED"

    # Find original settlement ID
    orig_stl_id = None
    for el, txn_ref in xml_entries:
        if txn_ref["transaction_id"] == duplicate_txn["transaction_id"]:
            orig_stl_id = el.find("SettlementId").text
            break

    manifest.duplicates.append(
        {
            "transaction_id": duplicate_txn["transaction_id"],
            "processor": "GlobalPay",
            "settlement_ids": [orig_stl_id, dup_stl_id],
        }
    )

    # Pretty-print XML
    rough_string = ET.tostring(root, encoding="unicode", xml_declaration=False)
    xml_string = minidom.parseString(rough_string).toprettyxml(indent="  ")
    # minidom adds its own xml declaration; replace it with a proper one
    lines = xml_string.split("\n")
    lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("FlexiMarket Reconciler — Test Data Generator")
    print(f"Seed: {SEED}")
    print("=" * 70)

    # --- 1. Expected transactions ---
    print("\n[1/5] Generating expected transactions...")
    transactions = generate_expected_transactions()
    txn_path = DATA_DIR / "expected_transactions.json"
    with open(txn_path, "w") as f:
        json.dump(transactions, f, indent=2)
    print(f"  -> {txn_path.name}: {len(transactions)} transactions")

    # Count by processor/country
    by_proc: dict[str, dict[str, int]] = {}
    for t in transactions:
        proc = t["processor_name"]
        country = t["country"]
        by_proc.setdefault(proc, {})
        by_proc[proc][country] = by_proc[proc].get(country, 0) + 1
    for proc, countries in sorted(by_proc.items()):
        parts = ", ".join(f"{c}={n}" for c, n in sorted(countries.items()))
        print(f"     {proc}: {parts} (total {sum(countries.values())})")

    # Status breakdown
    status_counts = {}
    for t in transactions:
        status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1
    print(f"     Statuses: {status_counts}")

    manifest = DiscrepancyManifest()

    # --- 2. PayFlow CSV ---
    print("\n[2/5] Generating PayFlow settlement CSV...")
    pf_rows = generate_payflow_csv(transactions, manifest)
    pf_path = DATA_DIR / "settlement_payflow.csv"
    with open(pf_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        writer.writerows(pf_rows)
    print(f"  -> {pf_path.name}: {len(pf_rows)} settlement rows")

    # --- 3. TransactMax JSON ---
    print("\n[3/5] Generating TransactMax settlement JSON...")
    tm_data = generate_transactmax_json(transactions, manifest)
    tm_path = DATA_DIR / "settlement_transactmax.json"
    with open(tm_path, "w") as f:
        json.dump(tm_data, f, indent=2)
    print(f"  -> {tm_path.name}: {len(tm_data['settlements'])} settlements")

    # --- 4. GlobalPay XML ---
    print("\n[4/5] Generating GlobalPay settlement XML...")
    gp_xml = generate_globalpay_xml(transactions, manifest)
    gp_path = DATA_DIR / "settlement_globalpay.xml"
    with open(gp_path, "w") as f:
        f.write(gp_xml)
    settlement_count = gp_xml.count("<Settlement>")
    print(f"  -> {gp_path.name}: {settlement_count} settlements")

    # --- 5. Discrepancy manifest ---
    print("\n[5/5] Writing discrepancy manifest...")
    manifest_data = manifest.to_dict()
    manifest_path = DATA_DIR / "discrepancy_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)

    # --- Summary ---
    print("\n" + "=" * 70)
    print("DISCREPANCY SUMMARY")
    print("=" * 70)
    print(f"  Amount mismatches : {len(manifest_data['amount_mismatches'])}")
    for d in manifest_data["amount_mismatches"]:
        print(
            f"    - {d['transaction_id']} ({d['processor']}): expected {d['expected_net']}, got {d['actual_net']} ({d['currency']})"
        )
    print(f"  Excessive fees    : {len(manifest_data['excessive_fees'])}")
    for d in manifest_data["excessive_fees"]:
        print(
            f"    - {d['transaction_id']} ({d['processor']}): expected fee {d['expected_total_fee']}, got {d['actual_total_fee']} ({d['currency']})"
        )
    print(f"  Missing settlements: {len(manifest_data['missing_settlements'])}")
    for d in manifest_data["missing_settlements"]:
        print(f"    - {d['transaction_id']} ({d['processor']})")
    print(f"  Duplicates        : {len(manifest_data['duplicates'])}")
    for d in manifest_data["duplicates"]:
        print(
            f"    - {d['transaction_id']} ({d['processor']}): IDs {d['settlement_ids']}"
        )
    print(f"  Currency/FX issues: {len(manifest_data['currency_issues'])}")
    for d in manifest_data.get("currency_issues", []):
        print(
            f"    - {d['transaction_id']} ({d['processor']}): expected FX {d['expected_fx_rate']}, got {d['actual_fx_rate']} ({d['deviation_percent']}% off)"
        )

    total = (
        len(manifest_data["amount_mismatches"])
        + len(manifest_data["excessive_fees"])
        + len(manifest_data["missing_settlements"])
        + len(manifest_data["duplicates"])
        + len(manifest_data["currency_issues"])
    )
    print(f"\n  TOTAL PLANTED DISCREPANCIES: {total}")
    print("=" * 70)

    # File sizes
    print("\nGenerated files:")
    for p in [txn_path, pf_path, tm_path, gp_path, manifest_path]:
        size = p.stat().st_size
        print(f"  {p.name}: {size:,} bytes")

    print("\nDone!")


if __name__ == "__main__":
    main()
