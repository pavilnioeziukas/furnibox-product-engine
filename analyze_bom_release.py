from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from bom_release import (
    BomReleaseAnalyzer,
    load_latest_dataset_record,
    write_release_plan,
)
from config import load_settings
from odoo_client import OdooClient
from output_paths import environment_slug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Tik skaito Production ir sugeneruoja "
            "pilno BOM release planą."
        )
    )

    parser.add_argument(
        "--release-id",
        default=f"REFORM_v08_{date.today():%Y%m%d}",
    )

    parser.add_argument(
        "--release-reference",
        default=f"REFORM_v08_{date.today():%Y%m%d}",
    )

    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    environment = environment_slug()

    if environment != "production":
        raise PermissionError(
            "Šis Analyze paleidimas skirtas Production. "
            "Pasirink Production aplinką GUI arba .env."
        )

    settings = load_settings()
    client = OdooClient(settings)
    client.authenticate()

    dataset_record, dataset_path = (
        load_latest_dataset_record(
            args.dataset
        )
    )

    analyzer = BomReleaseAnalyzer(
        client,
        environment="production",
    )

    plan = analyzer.build_release_plan(
        release_id=args.release_id,
        release_reference=(
            args.release_reference
        ),
        dataset_record=dataset_record,
        dataset_path=dataset_path,
    )

    output_path = (
        args.output.resolve()
        if args.output
        else (
            settings.output_dir
            / (
                "BOM_Release_Plan_"
                f"{args.release_id}.xlsx"
            )
        )
    )

    write_release_plan(
        plan,
        output_path,
    )

    print()
    print("=" * 80)
    print("BOM RELEASE ANALYZE")
    print("=" * 80)
    print("Release:", plan.release_id)
    print("Dataset:", plan.dataset_batch_reference)
    print("Visi BOM:", plan.total_count)
    print("READY:", plan.ready_count)
    print(
        "ALREADY EXISTS:",
        plan.already_exists_count,
    )
    print("BLOCKED:", plan.blocked_count)
    print(
        "Missing Parent:",
        plan.missing_parent_count,
    )
    print(
        "Parents with Missing Components:",
        plan.missing_component_parent_count,
    )
    print(
        "Parents Missing Template External ID:",
        plan.missing_parent_external_id_count,
    )
    print(
        "Parents with Components Missing Variant External ID:",
        plan.missing_component_external_id_parent_count,
    )
    print(
        "Multiple Sequence 0:",
        plan.multiple_sequence_zero_count,
    )
    print(
        "Generate leidžiamas:",
        "TAIP"
        if plan.can_generate
        else "NE",
    )
    print("Ataskaita:", output_path)


if __name__ == "__main__":
    main()
