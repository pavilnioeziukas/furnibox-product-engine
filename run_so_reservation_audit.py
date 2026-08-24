"""CLI entry point for a read-only SO component reservation audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from config import load_settings
from odoo_client import OdooClient
from so_reservation_audit import audit_so_reservations, write_reservation_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only SO reservation audit")
    parser.add_argument("--so-number", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = audit_so_reservations(OdooClient(load_settings()), args.so_number)
    files = write_reservation_report(report, args.output_dir)
    summary = {key: value for key, value in report.items() if key != "rows"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for path in files:
        print(f"Ataskaita: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
