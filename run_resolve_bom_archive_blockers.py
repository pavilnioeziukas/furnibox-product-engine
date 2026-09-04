from __future__ import annotations

import argparse
import json
from pathlib import Path

from config import load_settings
from odoo_client import OdooClient
from resolve_bom_archive_blockers import parse_queries, resolve


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("Trūksta privalomo --apply patvirtinimo; Odoo nekeistas.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = resolve(OdooClient(load_settings()), parse_queries(args.queries))
    result_path = output_dir / "BOM_archyvavimo_sprendimas.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result["message"])
    print("Suarchyvuoti BOM ID:", ", ".join(map(str, result["archived_bom_ids"])) or "nėra")
    print("Atkurta SO eilučių:", len(result["restored_lines"]))


if __name__ == "__main__":
    main()
