from __future__ import annotations

import argparse
from pathlib import Path

from stage_product_id_map import (
    export_stage_product_id_map,
    read_bom_skus,
    save_map,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pagal BOM Internal Reference ištraukia Stage product.template ir "
            "product.product External ID į JSON. Odoo nekeičia."
        )
    )
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env.stage"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from dotenv import load_dotenv
    from config import load_settings
    from odoo_client import OdooClient

    env_file = args.env_file.resolve()
    if not env_file.is_file():
        raise FileNotFoundError(f"Nerastas Stage env failas: {env_file}")
    load_dotenv(env_file, override=True)
    settings = load_settings()
    if "stage" not in settings.url.lower():
        raise PermissionError(f"BLOCKED: URL nėra Stage aplinka: {settings.url}")

    parent_skus, component_skus = read_bom_skus(args.source)
    client = OdooClient(settings)
    client.authenticate()
    data = export_stage_product_id_map(
        client, parent_skus, component_skus, settings.url
    )
    save_map(data, args.output)

    print("=" * 80)
    print("STAGE PRODUCT EXTERNAL ID EXPORT")
    print("=" * 80)
    print("Statusas: PASS")
    print("Stage URL:", settings.url)
    print("BOM produktai:", len(parent_skus))
    print("Komponentai:", len(component_skus))
    print("Unikalūs SKU:", len(data["records"]))
    print("Žodynas:", args.output.resolve())
    print("Odoo pakeitimai: 0")


if __name__ == "__main__":
    main()
