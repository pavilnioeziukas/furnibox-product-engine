"""CLI for the read-only completed-MO component consumption audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from config import load_settings
from mo_component_consumption_audit import run_mo_component_consumption_audit
from odoo_client import OdooClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only completed MO component consumption audit")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--days", type=int, default=550)
    args = parser.parse_args()
    summary = run_mo_component_consumption_audit(
        OdooClient(load_settings()), args.output_dir, days=max(args.days, 1),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
