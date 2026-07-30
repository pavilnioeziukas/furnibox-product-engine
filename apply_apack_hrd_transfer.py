from __future__ import annotations

import argparse
import copy
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from manifest.manifest_hash import calculate_bom_hash
from manifest.manifest_models import ManifestComponent


QTY_TOLERANCE = 1e-9
ALLOWED_ANALYSIS_STATUSES = {"TRANSFERRED", "NO_TRANSFER", "BLOCKED"}


class DatasetTransferError(RuntimeError):
    """Dataset arba analizė neleidžia saugiai pritaikyti transformacijos."""


def canon(value: Any) -> str:
    return str(value or "").strip().upper()


def component_map(product: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = defaultdict(float)
    for row in product.get("components") or []:
        sku = canon(row.get("sku"))
        quantity = float(row.get("quantity") or 0)
        if not sku or quantity <= 0:
            raise DatasetTransferError(
                f"{canon(product.get('sku'))}: tuščias komponentas arba "
                "neteisingas kiekis."
            )
        values[sku] += quantity
    return dict(sorted(values.items()))


def product_index(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for product in dataset.get("products") or []:
        sku = canon(product.get("sku"))
        if not sku:
            raise DatasetTransferError("Dataset turi produktą be SKU.")
        if sku in result:
            raise DatasetTransferError(f"Dataset SKU kartojasi: {sku}")
        result[sku] = product
    if not result:
        raise DatasetTransferError("Dataset neturi produktų.")
    return result


def write_components(product: dict[str, Any], values: dict[str, float]) -> None:
    level = int(product.get("level") or 1)
    parent_sku = canon(product.get("sku"))
    product["components"] = [
        {
            "sku": sku,
            "quantity": quantity,
            "parent_sku": parent_sku,
            "level": level,
        }
        for sku, quantity in sorted(values.items())
        if quantity > QTY_TOLERANCE
    ]
    statistics = dict(product.get("statistics") or {})
    statistics["component_count"] = len(product["components"])
    statistics["operation_count"] = len(product.get("operations") or [])
    product["statistics"] = statistics


def refresh_product_hash(product: dict[str, Any]) -> None:
    sku = canon(product.get("sku"))
    bom_type = canon(product.get("bom_type"))
    components = [
        ManifestComponent(
            sku=row["sku"],
            quantity=float(row["quantity"]),
            parent_sku=sku,
            level=int(row.get("level") or product.get("level") or 1),
            path=f"{sku} > {row['sku']}",
        )
        for row in product.get("components") or []
    ]
    content_hash, content_signature = calculate_bom_hash(
        root_sku=sku,
        bom_reference="",
        bom_type=bom_type,
        components=components,
    )
    product["content_hash"] = content_hash
    product["content_signature"] = content_signature


def validate_analysis(
    analysis: dict[str, Any],
    apack_skus: set[str],
) -> list[dict[str, Any]]:
    rows = list(analysis.get("results") or [])
    if not rows:
        raise DatasetTransferError("Analizė neturi results eilučių.")
    seen: set[str] = set()
    for row in rows:
        apack_sku = canon(row.get("apack_sku"))
        status = canon(row.get("status"))
        if not apack_sku or apack_sku in seen:
            raise DatasetTransferError(
                f"Analizėje APACK SKU tuščias arba kartojasi: {apack_sku}"
            )
        if status not in ALLOWED_ANALYSIS_STATUSES:
            raise DatasetTransferError(
                f"{apack_sku}: neleistinas analizės statusas {status}."
            )
        if apack_sku not in apack_skus:
            raise DatasetTransferError(
                f"Analizės APACK nerastas Dataset: {apack_sku}"
            )
        seen.add(apack_sku)
    missing = sorted(apack_skus - seen)
    if missing:
        raise DatasetTransferError(
            "Analizė neapima visų Dataset APACK: " + ", ".join(missing[:20])
        )
    return rows


def transform_dataset(
    dataset: dict[str, Any],
    analysis: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    output = copy.deepcopy(dataset)
    products = product_index(output)
    apack_skus = {
        sku for sku in products if sku.startswith("APACK-") and sku.endswith("-A")
    }
    rows = validate_analysis(analysis, apack_skus)

    audit_rows: list[dict[str, Any]] = []
    changed_products: set[str] = set()
    transferred_components = 0
    default_hrd = 0
    # Vieną HRD-A gali naudoti keli APACK. Todėl šaltinio kiekius saugome
    # atskirai, o komponentus iš bendro HRD-A pašaliname tik po to, kai
    # apdoroti visi su juo susieti APACK.
    source_components = {
        sku: component_map(product) for sku, product in products.items()
    }
    hrd_removals: dict[str, dict[str, float]] = defaultdict(dict)

    for row in rows:
        status = canon(row.get("status"))
        apack_sku = canon(row.get("apack_sku"))
        if status == "BLOCKED":
            default_hrd += 1
            audit_rows.append(
                {
                    "apack_sku": apack_sku,
                    "hrd_a_sku": "",
                    "component_sku": "",
                    "quantity": 0,
                    "decision": "DEFAULT_HRD_REVIEW",
                    "reason": str(row.get("reason") or ""),
                }
            )
            continue
        if status == "NO_TRANSFER":
            audit_rows.append(
                {
                    "apack_sku": apack_sku,
                    "hrd_a_sku": canon(row.get("hrd_a_sku")),
                    "component_sku": "",
                    "quantity": 0,
                    "decision": "NO_TRANSFER",
                    "reason": "",
                }
            )
            continue

        hrd_a_sku = canon(row.get("hrd_a_sku"))
        apack = products.get(apack_sku)
        hrd_a = products.get(hrd_a_sku)
        if apack is None or hrd_a is None:
            raise DatasetTransferError(
                f"{apack_sku}: nerastas APACK arba HRD-A {hrd_a_sku}."
            )
        apack_values = component_map(apack)
        hrd_values = source_components[hrd_a_sku]
        plan = list(row.get("transfer_plan") or [])
        if not plan:
            raise DatasetTransferError(
                f"{apack_sku}: TRANSFERRED statusas, bet planas tuščias."
            )
        for transfer in plan:
            component_sku = canon(transfer.get("component_sku"))
            quantity = float(transfer.get("quantity") or 0)
            if not component_sku or quantity <= 0:
                raise DatasetTransferError(
                    f"{apack_sku}: neteisinga perkėlimo eilutė."
                )
            available = hrd_values.get(component_sku, 0)
            if abs(available - quantity) > QTY_TOLERANCE:
                raise DatasetTransferError(
                    f"{apack_sku}: {component_sku} analizės kiekis {quantity} "
                    f"nesutampa su HRD-A kiekiu {available}."
                )
            if apack_values.get(component_sku, 0) > QTY_TOLERANCE:
                raise DatasetTransferError(
                    f"{apack_sku}: {component_sku} prieš transformaciją jau "
                    "yra ir APACK, ir HRD-A."
                )
            previous_quantity = hrd_removals[hrd_a_sku].get(component_sku)
            if (
                previous_quantity is not None
                and abs(previous_quantity - quantity) > QTY_TOLERANCE
            ):
                raise DatasetTransferError(
                    f"{hrd_a_sku}: bendram HRD-A komponentui {component_sku} "
                    f"analizė nurodo skirtingus kiekius "
                    f"({previous_quantity} ir {quantity})."
                )
            apack_values[component_sku] = quantity
            hrd_removals[hrd_a_sku][component_sku] = quantity
            transferred_components += 1
            audit_rows.append(
                {
                    "apack_sku": apack_sku,
                    "hrd_a_sku": hrd_a_sku,
                    "component_sku": component_sku,
                    "quantity": quantity,
                    "decision": "TRANSFER_TO_APACK",
                    "reason": canon(row.get("analog_match_method")),
                }
            )
        write_components(apack, apack_values)
        changed_products.add(apack_sku)

    for hrd_a_sku, removals in hrd_removals.items():
        hrd_a = products[hrd_a_sku]
        hrd_values = dict(source_components[hrd_a_sku])
        for component_sku, quantity in removals.items():
            available = hrd_values.get(component_sku, 0)
            if abs(available - quantity) > QTY_TOLERANCE:
                raise DatasetTransferError(
                    f"{hrd_a_sku}: {component_sku} šaltinio kiekis "
                    f"{available} nesutampa su šalinamu kiekiu {quantity}."
                )
            hrd_values.pop(component_sku)
        write_components(hrd_a, hrd_values)
        changed_products.add(hrd_a_sku)

    for sku in changed_products:
        refresh_product_hash(products[sku])

    # Po transformacijos kiekvienas faktiškai perkeltas komponentas privalo
    # būti APACK ir nebegali likti susietame HRD-A.
    for audit in audit_rows:
        if audit["decision"] != "TRANSFER_TO_APACK":
            continue
        apack_values = component_map(products[audit["apack_sku"]])
        hrd_values = component_map(products[audit["hrd_a_sku"]])
        component_sku = audit["component_sku"]
        if component_sku not in apack_values or component_sku in hrd_values:
            raise DatasetTransferError(
                f"Transformacijos kontrolė nepraėjo: {component_sku}."
            )

    output["dataset_id"] = str(uuid.uuid4())
    output["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    batch_reference = str(output.get("batch_reference") or "").strip()
    output["batch_reference"] = f"{batch_reference}_APACK_HRD_V7".strip("_")
    statistics = dict(output.get("statistics") or {})
    statistics["product_count"] = len(products)
    statistics["component_rows"] = sum(
        len(product.get("components") or []) for product in products.values()
    )
    statistics["operation_rows"] = sum(
        len(product.get("operations") or []) for product in products.values()
    )
    output["statistics"] = statistics
    output["apack_hrd_transformation"] = {
        "version": "v7",
        "policy": "AMBIGUOUS_COMPONENT_STAYS_IN_HRD_A",
        "changed_products": len(changed_products),
        "component_transfers": transferred_components,
        "default_hrd_review": default_hrd,
        "source_analysis_statistics": analysis.get("statistics") or {},
    }
    audit = {
        "status": "PASS",
        "policy": "AMBIGUOUS_COMPONENT_STAYS_IN_HRD_A",
        "statistics": {
            "analysis_rows": len(rows),
            "changed_products": len(changed_products),
            "component_transfers": transferred_components,
            "default_hrd_review": default_hrd,
        },
        "rows": audit_rows,
    }
    return output, audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pritaiko APACK/HRD-A analizę Validated Dataset. "
            "Neaiškūs komponentai lieka HRD-A. Odoo nekeičia."
        )
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    transformed, audit = transform_dataset(dataset, analysis)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(transformed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    args.audit.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("=" * 80)
    print("APACK / HRD-A VALIDATED DATASET TRANSFORMATION v7")
    print("=" * 80)
    print("Statusas: PASS")
    print("Taisyklė: neaiškūs komponentai lieka HRD-A")
    print("Pakeisti produktai:", audit["statistics"]["changed_products"])
    print("Komponentų perkėlimai:", audit["statistics"]["component_transfers"])
    print("DEFAULT_HRD_REVIEW:", audit["statistics"]["default_hrd_review"])
    print("Dataset:", args.output.resolve())
    print("Auditas:", args.audit.resolve())
    print("Odoo pakeitimai: 0")


if __name__ == "__main__":
    main()
