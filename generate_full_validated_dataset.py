from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from bom_import_manufacture_v5 import load_reform_bom_lines
from bom_import_pilot_v2 import load_operation_templates
from manifest.manifest_writer import calculate_file_hash
from output_paths import environment_slug
from product_detection_v2 import (
    find_bom_input,
    load_reform_universe,
)
from validated_dataset import write_validated_dataset
from validated_dataset.full_bom_type_catalog import (
    build_full_bom_type_catalog,
)
from validated_dataset.full_catalog_builder import (
    build_full_validated_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generuoja pilną Validated Product Dataset.",
    )
    parser.add_argument(
        "--bom-input",
        type=Path,
        help="Konkretus Reform BOM .xlsx failas.",
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

    type_catalog = build_full_bom_type_catalog(
        reform_products=reform_products,
        reform_lines=reform_lines,
        odoo_map_path=(
            base / "output" / "production" / "Odoo_MAP.xlsx"
        ),
    )
    operation_templates = load_operation_templates(
        base
        / "output"
        / "production"
        / "BOM_Operations_Reference.xlsx"
    )

    dataset = build_full_validated_dataset(
        environment=environment,
        batch_reference=(
            f"{date.today():%Y%m%d}_FULL_{reform_path.stem}"
        ),
        source_file=reform_path,
        source_file_hash=calculate_file_hash(reform_path),
        reform_products=reform_products,
        reform_lines=reform_lines,
        type_catalog=type_catalog,
        operation_templates=operation_templates,
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
    print("Failas:", output_path)


if __name__ == "__main__":
    main()
