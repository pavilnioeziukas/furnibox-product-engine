from __future__ import annotations

import argparse
import json
from pathlib import Path

from bom_release.analyzer import load_latest_dataset_record
from config import load_settings
from odoo_client import OdooClient
from target_reconciliation import reconcile
from target_reconciliation.odoo_reader import read_production_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only transformed Furnibox Target Dataset vs Production Odoo reconciliation."
    )
    parser.add_argument("--dataset", type=Path, help="Target Dataset JSON; otherwise latest Production dataset")
    parser.add_argument("--output", type=Path, required=True, help="Machine-readable reconciliation JSON")
    args = parser.parse_args()
    settings = load_settings()
    if "stage" in settings.url.lower():
        raise PermissionError("Palyginimui būtina Production Odoo aplinka.")
    dataset, _ = load_latest_dataset_record(args.dataset)
    client = OdooClient(settings)
    client.authenticate()
    result = reconcile(dataset, read_production_snapshot(client)).to_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print("READ-ONLY rezultatas:", args.output.resolve())


if __name__ == "__main__":
    main()
