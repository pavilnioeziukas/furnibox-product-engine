"""Run the complete read-only Reform pricing refresh pipeline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook


BASE_DIR = Path(__file__).resolve().parent
PRODUCTION_DIR = BASE_DIR / "output" / "production"
RULES_PATH = BASE_DIR / "web_state" / "shared_data" / "so_pricing_rules.json"


def run_step(title: str, *arguments: str) -> None:
    print(f"\n=== {title} ===", flush=True)
    result = subprocess.run(
        [sys.executable, "-u", *arguments],
        cwd=BASE_DIR,
        env={
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "FURNIBOX_ENVIRONMENT": "PRODUCTION",
        },
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Žingsnis nepavyko: {title} (kodas {result.returncode})")


def read_pricing_status(path: Path) -> tuple[Counter, list[dict]]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["SO LINE PRICES"]
    rows = sheet.iter_rows(values_only=True)
    header = next(rows)
    columns = {value: index for index, value in enumerate(header)}
    statuses: Counter = Counter()
    blocked = []
    for row in rows:
        status = str(row[columns["Status"]] or "")
        statuses[status] += 1
        if status != "COMPLETE":
            blocked.append({
                "sku": row[columns["SKU"]],
                "position_type": row[columns["Position Type"]],
                "status": status,
                "issues": row[columns["Issues"]],
            })
    workbook.close()
    return statuses, blocked


def write_blocker_report(path: Path, statuses: Counter, blocked: list[dict]) -> None:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "SUMMARY"
    summary.append(["Status", "Count"])
    for status, count in sorted(statuses.items()):
        summary.append([status, count])
    summary.append([])
    summary.append(["Decision", "FINAL FILE NOT RELEASED"])
    summary.append(["Reason", "Pricing contains BLOCKED positions"])

    details = workbook.create_sheet("BLOCKERS")
    details.append(["SKU", "Position Type", "Status", "Issues"])
    for row in blocked:
        details.append([
            row["sku"], row["position_type"], row["status"], row["issues"]
        ])
    details.freeze_panes = "A2"
    details.auto_filter.ref = details.dimensions
    details.column_dimensions["A"].width = 38
    details.column_dimensions["B"].width = 18
    details.column_dimensions["C"].width = 15
    details.column_dimensions["D"].width = 100
    workbook.save(path)


def write_furnibox_purchase_prices(source: Path, destination: Path) -> None:
    """Publish the real and Tamara-adjusted Furnibox purchase prices."""
    source_workbook = load_workbook(source, data_only=True, read_only=True)
    source_sheet = source_workbook["REFORM PRICE LIST"]
    rows = source_sheet.iter_rows(values_only=True)
    source_header = next(rows)
    columns = {value: index for index, value in enumerate(source_header)}
    selected = [
        ("Internal Reference", "Internal Reference"),
        ("Name", "Name"),
        ("Price Source", "Price Source"),
        ("Vendor / Supply Source", "Vendor / Supply Source"),
        ("Real Furnibox Purchase Price", "Real Furnibox Purchase Price"),
        ("Adjusted Furnibox Purchase Price", "Furnibox (Tamara) Purchase Price"),
        ("Status / BOM Source", "Status / BOM Source"),
    ]

    result = Workbook()
    sheet = result.active
    sheet.title = "FURNIBOX PURCHASE PRICES"
    sheet.append([output_name for _, output_name in selected])
    for row in rows:
        sheet.append([row[columns[source_name]] for source_name, _ in selected])
    source_workbook.close()

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.column_dimensions["A"].width = 38
    sheet.column_dimensions["B"].width = 50
    sheet.column_dimensions["C"].width = 28
    sheet.column_dimensions["D"].width = 35
    for column in ("E", "F"):
        sheet.column_dimensions[column].width = 28
        for cell in sheet[column][1:]:
            cell.number_format = '0.0000 [$€-x-euro2]'

    info = result.create_sheet("INFO")
    info.append(["Parameter", "Value"])
    info.append(["Real purchase price", "Latest approved vendor purchase price"])
    info.append([
        "Furnibox (Tamara) Purchase Price",
        "Tamara-adjusted Furnibox purchase price used by Reform pricing",
    ])
    info.append(["Odoo changed", "NO"])
    result.save(destination)


def refresh(bom_input: Path, output_dir: Path, rules_path: Path = RULES_PATH) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)

    reform_map = PRODUCTION_DIR / "Reform_MAP.xlsx"
    odoo_map = PRODUCTION_DIR / "Odoo_MAP.xlsx"
    detection = PRODUCTION_DIR / "Product_Detection_All.xlsx"
    comparison = PRODUCTION_DIR / "MAP_Comparison.xlsx"

    run_step("1/8 Reform BOM paruošimas", "reform_map.py", "--input", str(bom_input), "--output", str(reform_map))
    run_step("2/8 Aktualus Odoo BOM žemėlapis", "odoo_map.py")
    run_step("3/8 Reform SKU patikra Odoo", "product_detection_v3.py", "--bom-input", str(bom_input))
    run_step(
        "4/8 Reform ir Odoo BOM palyginimas",
        "map_comparison_v5.py", "--reform", str(reform_map), "--odoo", str(odoo_map),
        "--products", str(detection), "--bom-input", str(bom_input), "--output", str(comparison),
    )
    run_step("5/8 Cabinet Parts kainos", "cabinet_parts_price_v1.py")
    run_step("6/8 Naujausios pirkimo kainos", "last_purchase_prices.py")
    run_step("7/8 Bendras Reform pirkimo kainų šaltinis", "reform_price_list.py")

    with tempfile.TemporaryDirectory(prefix="reform-pricing-") as temporary:
        candidate_dir = Path(temporary)
        run_step(
            "8/8 Galutinės Reform pardavimo kainos",
            "reform_so_line_prices.py", "--bom-input", str(bom_input),
            "--price-input", str(PRODUCTION_DIR / "Reform_Final_Prices.xlsx"),
            "--rules", str(rules_path), "--output-dir", str(candidate_dir),
        )
        candidate = candidate_dir / "Reform_SO_Line_Prices.xlsx"
        statuses, blocked = read_pricing_status(candidate)

        result = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "bom_input": str(bom_input),
            "statuses": dict(statuses),
            "blocked": blocked,
            "released": not blocked,
            "odoo_changed": False,
        }
        (output_dir / "Reform_Pricing_Result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if blocked:
            write_blocker_report(
                output_dir / "Reform_Pricing_BLOCKED.xlsx", statuses, blocked
            )
            print(f"\nSUSTABDYTA: {len(blocked)} BLOCKED pozicijos.")
            print("Galutiniai kainų failai nepateikti.")
            return 2

        write_furnibox_purchase_prices(
            PRODUCTION_DIR / "Reform_Final_Prices.xlsx",
            output_dir / "Furnibox_Tamara_Purchase_Prices.xlsx",
        )
        shutil.copy2(
            PRODUCTION_DIR / "Reform_Final_Prices.xlsx",
            output_dir / "Reform_Pricing_Source.xlsx",
        )
        shutil.copy2(candidate, output_dir / "Reform_SO_Line_Prices.xlsx")

    print("\nREFORM KAINODARA ATNAUJINTA: 0 BLOCKED")
    print("Parengtos faktinės, Furnibox (Tamara) pirkimo ir Reform pardavimo kainos.")
    print("Odoo nekeistas.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Atnaujinti visą Reform kainodarą")
    parser.add_argument("--bom-input", required=True, type=Path)
    parser.add_argument("--rules", type=Path, default=RULES_PATH)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.bom_input.exists():
        raise FileNotFoundError(args.bom_input)
    raise SystemExit(refresh(args.bom_input, args.output_dir, args.rules))


if __name__ == "__main__":
    main()
