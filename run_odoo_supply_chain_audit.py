"""CLI entry point for the read-only Odoo supply-chain audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from config import load_settings
from odoo_client import OdooClient
from odoo_supply_chain_audit import run_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Odoo supply-chain audit")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = run_audit(OdooClient(load_settings()), args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
