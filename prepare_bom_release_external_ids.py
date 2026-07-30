from __future__ import annotations

import argparse
from pathlib import Path

from bom_release import load_latest_dataset_record
from bom_release.external_ids import (
    apply_external_id_preparation,
    build_external_id_preparation,
)
from config import load_settings
from dotenv import load_dotenv
from odoo_client import OdooClient
from output_paths import environment_slug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Patikrina arba paruošia esamų Production produktų techninius "
            "External ID BOM release importui. Produktų nekuria."
        )
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Sugeneruoti trūkstamus techninius External ID.",
    )
    return parser.parse_args()


def main() -> None:
    base = Path(__file__).resolve().parent
    load_dotenv(base / ".env")
    args = parse_args()
    if environment_slug() != "production":
        raise PermissionError(
            "External ID paruošimas skirtas Production aplinkai."
        )

    settings = load_settings()
    if "stage" in str(settings.url).lower():
        raise PermissionError(
            "Pasirinkta Production, bet URL atrodo kaip Stage."
        )
    client = OdooClient(settings)
    client.authenticate()
    dataset, dataset_path = load_latest_dataset_record(args.dataset)
    preparation = build_external_id_preparation(client, dataset)

    print()
    print("=" * 80)
    print("BOM RELEASE EXTERNAL ID PREPARATION")
    print("=" * 80)
    print("Dataset:", dataset_path)
    print("Trūksta product.template External ID:", len(preparation.template_ids))
    print("Trūksta product.product External ID:", len(preparation.product_ids))
    if preparation.template_skus:
        print("Parent SKU:", ", ".join(preparation.template_skus))
    if preparation.product_skus:
        print("Component SKU:", ", ".join(preparation.product_skus))

    if not args.apply:
        print("Pakeitimai: 0 (peržiūra)")
        print("Norint pritaikyti, pakartokite su --apply.")
        return

    templates, products = apply_external_id_preparation(client, preparation)
    print("Paruošta product.template External ID:", templates)
    print("Paruošta product.product External ID:", products)
    print("Produktai sukurti: 0")
    print("Verslo laukai pakeisti: 0")


if __name__ == "__main__":
    main()
