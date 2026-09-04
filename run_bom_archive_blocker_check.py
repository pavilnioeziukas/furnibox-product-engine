from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from bom_archive_blockers import run_check
from config import load_settings
from odoo_client import OdooClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_check(OdooClient(load_settings()), args.query)
    (output_dir / "BOM_archyvavimo_blokatoriai.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fieldnames = list(report["rows"][0]) if report["rows"] else [
        "sale_line_id", "so_number", "so_state", "product_id", "product", "ordered_qty",
        "delivered_qty", "invoiced_qty", "blocks_archive", "zero_residual_line", "recommended_action",
    ]
    with (output_dir / "BOM_archyvavimo_blokatoriai.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report["rows"])
    print(f"BOM: {args.query}")
    print(f"Pardavimo eilučių: {report['summary']['sale_line_count']}")
    print(f"Realių blokatorių: {report['summary']['blocking_line_count']}")
    print(f"Nulinių likutinių eilučių: {report['summary']['zero_residual_line_count']}")
    print(report["note"])


if __name__ == "__main__":
    main()
