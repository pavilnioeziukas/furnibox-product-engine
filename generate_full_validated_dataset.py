from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from analyze_apack_hrd_transfer import analyze_all
from apply_apack_hrd_transfer import transform_dataset
from bom_import_manufacture_v5 import load_reform_bom_lines
from bom_import_pilot_v2 import load_operation_templates
from bom_type_inference_v3 import canon
from config import load_settings
from manifest.manifest_writer import calculate_file_hash
from odoo_client import OdooClient
from output_paths import environment_slug
from product_detection_v2 import (
    find_bom_input,
    load_reform_universe,
)
from validated_dataset import write_validated_dataset_record
from validated_dataset.full_bom_type_catalog import (
    FullBomTypeCatalog,
    build_full_bom_type_catalog,
)
from validated_dataset.full_catalog_builder import (
    build_full_validated_dataset,
)
from shelf_pp import build_shelf_pp_templates, load_odoo_edges
import bom_operations_reference_v1
import odoo_map


class FullDatasetTransformationError(RuntimeError):
    """Production taisyklės neleidžia saugiai užbaigti target Dataset."""


def build_target_product_catalog(
    reform_products: dict[str, dict],
    dataset_record: dict,
) -> list[dict]:
    """Sujungia visą Reform produktų visatą ir sugeneruotas Furnibox korteles.

    ``products`` lieka tik BOM struktūrų rinkinys, kad release generatorius
    nepradėtų laikyti komponentų BOM tėvais. ``product_catalog`` yra pilnas
    kortelių katalogas, įskaitant component-only / ne BOM pozicijas.
    """
    bom_products = {
        str(row.get("sku") or "").strip().upper(): row
        for row in dataset_record.get("products") or []
        if str(row.get("sku") or "").strip()
    }
    rows: dict[str, dict] = {}
    for raw_sku, product in reform_products.items():
        sku = str(raw_sku or "").strip().upper()
        if not sku:
            continue
        is_parent = bool(product.get("is_parent"))
        is_component = bool(product.get("is_component"))
        role = (
            "BOM PARENT + COMPONENT"
            if is_parent and is_component
            else "BOM PARENT"
            if is_parent
            else "NON-BOM COMPONENT"
        )
        rows[sku] = {
            "sku": sku,
            "origin": "REFORM",
            "role": role,
            "has_bom": sku in bom_products,
            "is_bom_parent": is_parent,
            "is_component": is_component,
            "source_sku": sku,
            "generated_from": "",
            "product_type": str(product.get("category") or "").strip(),
            "part_group": str(product.get("part_group") or "").strip(),
            "name_1": str(product.get("name_1") or "").strip(),
            "name_2": str(product.get("name_2") or "").strip(),
        }

    for sku, product in sorted(bom_products.items()):
        if sku in rows:
            rows[sku]["has_bom"] = True
            continue
        generated_from = str(
            product.get("generated_from")
            or product.get("source_sku")
            or ""
        ).strip().upper()
        rows[sku] = {
            "sku": sku,
            "origin": "FURNIBOX GENERATED",
            "role": "GENERATED BOM PRODUCT",
            "has_bom": True,
            "is_bom_parent": True,
            "is_component": False,
            "source_sku": generated_from,
            "generated_from": generated_from,
            "product_type": str(product.get("product_type") or "").strip(),
            "part_group": "",
            "name_1": "",
            "name_2": "",
        }
    return [rows[sku] for sku in sorted(rows)]


def add_full_target_metadata(
    dataset_record: dict,
    reform_products: dict[str, dict],
) -> dict:
    catalog = build_target_product_catalog(reform_products, dataset_record)
    dataset_record["product_catalog"] = catalog
    statistics = dict(dataset_record.get("statistics") or {})
    statistics["catalog_product_count"] = len(catalog)
    statistics["non_bom_product_count"] = sum(
        not row["has_bom"] for row in catalog
    )
    dataset_record["statistics"] = statistics
    dataset_record["transformation_rules"] = [
        {
            "code": "SHELF_PP",
            "target": "Shelf KIT = Shelf PP + remaining component",
            "generated": "Shelf PP MANUFACTURE = Shelf Part + packaging + sticker + packing operation",
        },
        {
            "code": "CABINET_ASSEMBLED",
            "target": "Cabinet-A KIT = APACK + HRD-A",
            "generated": "APACK is generated from FPACK; HRD-A is generated from HRD",
        },
        {
            "code": "APACK_HRD_TRANSFER",
            "target": "Production analog assigns each transferable component to exactly one of APACK or HRD-A",
            "generated": "Ambiguous components stay in HRD-A and are marked DEFAULT_HRD_REVIEW",
        },
        {
            "code": "NON_BOM_PRODUCTS",
            "target": "Every Reform component-only SKU remains in the full product catalog",
            "generated": "No BOM is invented for a component-only product",
        },
    ]
    return dataset_record


def apply_apack_hrd_target_rules(
    dataset_record: dict,
    client: OdooClient,
) -> tuple[dict, dict, dict]:
    """Perkelia Production analogais patvirtintus HRD-A komponentus į APACK.

    Nevienareikšmiai atvejai lieka HRD-A ir yra aiškiai pažymimi audite kaip
    ``DEFAULT_HRD_REVIEW``. Taip komponentas niekada nėra dubliuojamas abiejuose
    BOM, o rankinio tarpinio failo nereikia.
    """
    analysis = analyze_all(dataset=dataset_record, client=client)
    apack_total = int(
        (analysis.get("statistics") or {}).get("apack_total") or 0
    )
    if apack_total == 0:
        audit = {
            "status": "PASS",
            "policy": "NO_APACK_IN_DATASET",
            "statistics": {
                "analysis_rows": 0,
                "changed_products": 0,
                "component_transfers": 0,
                "default_hrd_review": 0,
            },
            "rows": [],
        }
        return dataset_record, analysis, audit

    try:
        transformed, audit = transform_dataset(dataset_record, analysis)
    except Exception as exc:
        raise FullDatasetTransformationError(
            "APACK / HRD-A target transformacija nepavyko: " + str(exc)
        ) from exc
    return transformed, analysis, audit


def write_apack_hrd_audit(
    output_directory: Path,
    analysis: dict,
    audit: dict,
) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    analysis_path = output_directory / "APACK_HRD_Transfer_Analysis.json"
    audit_path = output_directory / "APACK_HRD_Transfer_Audit.json"
    analysis_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return analysis_path, audit_path


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
    parser.add_argument(
        "--output-path",
        type=Path,
        help="Papildoma konkreti pilno Target Dataset JSON kopija.",
    )
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    environment = environment_slug()

    if environment not in {"stage", "production"}:
        raise PermissionError(
            "Pilnas Dataset leidžiamas tik Stage arba Production."
        )

    if environment != "production":
        raise PermissionError(
            "Pilnas Dataset turi būti ruošiamas iš Production Odoo. "
            "Pasirinkite Production aplinką; Stage naudojama tik importo testui."
        )

    print("Atnaujinamas Production Odoo MAP...")
    odoo_map.main()
    print("Atnaujinamas Production BOM operacijų etalonas...")
    bom_operations_reference_v1.main()

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

    settings = load_settings()
    client = OdooClient(settings)
    client.authenticate()
    target_record, analysis, audit = apply_apack_hrd_target_rules(
        dataset.to_dict(),
        client,
    )
    target_record = add_full_target_metadata(
        target_record,
        reform_products,
    )
    analysis_path, audit_path = write_apack_hrd_audit(
        settings.output_dir,
        analysis,
        audit,
    )
    output_path = write_validated_dataset_record(target_record)
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            json.dumps(target_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print("\nFULL VALIDATED PRODUCT DATASET SUKURTAS")
    print("Aplinka:", dataset.environment)
    print("Reform BOM:", len(reform_lines))
    print("Dataset produktai:", len(target_record["products"]))
    print(
        "Pilno katalogo produktai:",
        len(target_record["product_catalog"]),
    )
    print(
        "Ne BOM pozicijos:",
        target_record["statistics"]["non_bom_product_count"],
    )
    print(
        "Operacijų eilutės:",
        sum(
            len(product.get("operations") or [])
            for product in target_record["products"]
        ),
    )
    print(
        "APACK / HRD-A komponentų perkėlimai:",
        audit["statistics"]["component_transfers"],
    )
    print(
        "APACK palikti peržiūrai:",
        audit["statistics"]["default_hrd_review"],
    )
    print("BOM tipai neišspręsti:", type_catalog.unresolved_count)
    print("Diagnostikai praleisti BOM:", len(skipped))
    print("APACK / HRD-A analizė:", analysis_path)
    print("APACK / HRD-A auditas:", audit_path)
    print("Failas:", output_path)
    if args.output_path is not None:
        print("Target Dataset kopija:", args.output_path.resolve())


if __name__ == "__main__":
    main()
