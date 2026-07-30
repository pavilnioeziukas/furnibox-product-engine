from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from bom_release import BomReleaseAnalyzer, load_latest_dataset_record
from bom_release.generator import generate_release_files
from config import load_settings
from dotenv import load_dotenv
from odoo_client import OdooClient
from output_paths import environment_slug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Iš patvirtinto Validated Dataset sugeneruoja Odoo BOM "
            "release importo failus. Odoo duomenų nekeičia."
        )
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--release-id",
        default=f"REFORM_v08_{date.today():%Y%m%d}",
    )
    parser.add_argument("--release-reference", default=None)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    base = Path(__file__).resolve().parent
    load_dotenv(base / ".env")
    args = parse_args()
    environment = environment_slug()
    if environment != "production":
        raise PermissionError(
            "BOM Release generatorius skirtas Production analizei. "
            "Pasirink Production aplinką .env."
        )

    release_reference = (
        args.release_reference or args.release_id
    ).strip()
    settings = load_settings()
    client = OdooClient(settings)
    client.authenticate()
    dataset, dataset_path = load_latest_dataset_record(args.dataset)
    plan = BomReleaseAnalyzer(
        client,
        environment="production",
    ).build_release_plan(
        release_id=args.release_id,
        release_reference=release_reference,
        dataset_record=dataset,
        dataset_path=dataset_path,
    )
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else settings.output_dir / f"BOM_Release_{args.release_id}"
    )
    files = generate_release_files(
        dataset=dataset,
        plan=plan,
        client=client,
        output_dir=output_dir,
    )

    print()
    print("=" * 80)
    print("BOM RELEASE IMPORT FILES")
    print("=" * 80)
    print("Dataset:", dataset_path)
    print("Release:", plan.release_id)
    print("Reference:", plan.release_reference)
    print("READY:", plan.ready_count)
    print("ALREADY EXISTS:", plan.already_exists_count)
    print("BLOCKED:", plan.blocked_count)
    print("Failai:", len(files))
    for item in files:
        print(
            f"lv{item.level} {item.bom_type}: "
            f"{item.bom_count} BOM -> {item.path}"
        )
    print("Odoo pakeitimai: 0")


if __name__ == "__main__":
    main()
