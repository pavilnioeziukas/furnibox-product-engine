from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from bom_import_manufacture_v5 import load_reform_bom_lines
from bom_import_pilot_v2 import load_operation_templates
from bom_type_inference_v3 import canon
from manifest.manifest_writer import calculate_file_hash
from output_paths import environment_slug
from product_detection_v2 import (
    find_bom_input,
    load_reform_universe,
)
from validated_dataset import write_validated_dataset
from validated_dataset.full_bom_type_catalog import (
    FullBomTypeCatalog,
    build_full_bom_type_catalog,
)
from validated_dataset.full_catalog_builder import (
    build_full_validated_dataset,
)
from shelf_pp import build_shelf_pp_templates, load_odoo_edges


def prepare_diagnostic_catalog(
    reform_lines: dict[str, list[dict]],
    type_catalog: FullBomTypeCatalog,
) -> tuple[dict[str, list[dict]], FullBomTypeCatalog, list[tuple[str, str]]]:
    skipped = sorted(type_catalog.unresolved.items())
    if not skipped:
        return reform_lines, type_catalog, []

    unresolved_skus = {sku for sku, _ in skipped}
    filtered_lines = {
        sku: lines
        for sku, lines in reform_lines.items()
        if canon(sku) not in unresolved_skus
    }
    resolved_catalog = FullBomTypeCatalog(
        assignments=type_catalog.assignments,
        unresolved={},
    )
    return filtered_lines, resolved_catalog, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generuoja pilną Validated Product Dataset.",
    )
    parser.add_argument(
        "--bom-input",
        type=Path,
        help="Konkretus Reform BOM .xlsx failas.",
    )
    parser.add_argument(
        "--skip-unresolved-bom-types",
        action="store_true",
        help=(
            "Diagnostiniam Dataset praleidžia BOM tėvus, kurių tipas "
            "neišspręstas. Nenaudoti release ar importui."
        ),
    )
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    environment = environment_slug()

    if environment not in {"stage", "production"}:
        raise PermissionError(
            "Pilnas Dataset leidžiamas tik Stage arba Production."
        )

    reform_path = (args.bom_input or find_bom_input(base)).resolve()
    if not reform_path.is_file():
        raise FileNotFoundError(f"Nerastas Reform BOM failas: {reform_path}")
    reform_products, _, _ = load_reform_universe(
        reform_path
    )
    reform_lines = load_reform_bom_lines(
        reform_path
    )

    odoo_map_path = (
        base / "output" / "production" / "Odoo_MAP.xlsx"
    )
    type_catalog = build_full_bom_type_catalog(
        reform_products=reform_products,
        reform_lines=reform_lines,
        odoo_map_path=odoo_map_path,
    )
    shelf_pp_templates = build_shelf_pp_templates(
        load_odoo_edges(odoo_map_path)
    )
    skipped: list[tuple[str, str]] = []
    if args.skip_unresolved_bom_types:
        reform_lines, type_catalog, skipped = prepare_diagnostic_catalog(
            reform_lines,
            type_catalog,
        )
        if skipped:
            print("\nDIAGNOSTINIS DATASET — PRALEISTI NEIŠSPRĘSTI BOM:")
            for sku, reason in skipped:
                print(f"- {sku}: {reason}")
    operation_templates = load_operation_templates(
        base
        / "output"
        / "production"
        / "BOM_Operations_Reference.xlsx"
    )

    dataset = build_full_validated_dataset(
        environment=environment,
        batch_reference=(
            f"{date.today():%Y%m%d}_"
            f"{'DIAGNOSTIC' if args.skip_unresolved_bom_types else 'FULL'}_"
            f"{reform_path.stem}"
        ),
        source_file=reform_path,
        source_file_hash=calculate_file_hash(reform_path),
        reform_products=reform_products,
        reform_lines=reform_lines,
        type_catalog=type_catalog,
        operation_templates=operation_templates,
        shelf_pp_templates=shelf_pp_templates,
    )

    output_path = write_validated_dataset(dataset)

    print("\nFULL VALIDATED PRODUCT DATASET SUKURTAS")
    print("Aplinka:", dataset.environment)
    print("Reform BOM:", len(reform_lines))
    print("Dataset produktai:", dataset.product_count)
    print(
        "Operacijų eilutės:",
        sum(product.operation_count for product in dataset.products),
    )
    print("BOM tipai neišspręsti:", type_catalog.unresolved_count)
    print("Diagnostikai praleisti BOM:", len(skipped))
    print("Failas:", output_path)


if __name__ == "__main__":
    main()
