from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from odoo_client import OdooClient


def canon(value: Any) -> str:
    return str(value or "").strip().upper()


@dataclass(frozen=True)
class ExternalIdPreparation:
    template_ids: tuple[int, ...]
    product_ids: tuple[int, ...]
    template_skus: tuple[str, ...]
    product_skus: tuple[str, ...]

    @property
    def change_count(self) -> int:
        return len(self.template_ids) + len(self.product_ids)


def _existing_external_ids(
    client: OdooClient,
    model: str,
    ids: set[int],
) -> set[int]:
    if not ids:
        return set()
    rows = client.search_read_all(
        "ir.model.data",
        [["model", "=", model], ["res_id", "in", sorted(ids)]],
        ["res_id"],
    )
    return {int(row["res_id"]) for row in rows}


def build_external_id_preparation(
    client: OdooClient,
    dataset: dict[str, Any],
) -> ExternalIdPreparation:
    bom_records = [
        row
        for row in dataset.get("products", [])
        if canon(row.get("sku"))
        and isinstance(row.get("components"), list)
    ]
    parent_skus = {canon(row.get("sku")) for row in bom_records}
    component_skus = {
        canon(component.get("sku"))
        for row in bom_records
        for component in row.get("components", [])
        if canon(component.get("sku"))
    }
    wanted_skus = parent_skus | component_skus

    rows = client.search_read_all(
        "product.product",
        [["default_code", "!=", False]],
        ["id", "default_code", "product_tmpl_id", "active"],
        context={"active_test": False},
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        sku = canon(row.get("default_code"))
        if sku in wanted_skus:
            grouped.setdefault(sku, []).append(row)

    missing = sorted(wanted_skus - set(grouped))
    duplicates = sorted(
        sku
        for sku, matches in grouped.items()
        if len({int(row["id"]) for row in matches}) != 1
        or len({
            int(row["product_tmpl_id"][0])
            for row in matches
            if row.get("product_tmpl_id")
        }) != 1
    )
    if missing or duplicates:
        messages = []
        if missing:
            messages.append("Odoo nerasti SKU: " + ", ".join(missing[:10]))
        if duplicates:
            messages.append(
                "Odoo neunikalūs SKU: " + ", ".join(duplicates[:10])
            )
        raise ValueError("; ".join(messages))

    products = {sku: matches[0] for sku, matches in grouped.items()}
    parent_template_by_sku = {
        sku: int(products[sku]["product_tmpl_id"][0])
        for sku in parent_skus
    }
    component_product_by_sku = {
        sku: int(products[sku]["id"])
        for sku in component_skus
    }
    template_ids = set(parent_template_by_sku.values())
    product_ids = set(component_product_by_sku.values())
    missing_template_ids = template_ids - _existing_external_ids(
        client, "product.template", template_ids
    )
    missing_product_ids = product_ids - _existing_external_ids(
        client, "product.product", product_ids
    )
    return ExternalIdPreparation(
        template_ids=tuple(sorted(missing_template_ids)),
        product_ids=tuple(sorted(missing_product_ids)),
        template_skus=tuple(sorted(
            sku
            for sku, record_id in parent_template_by_sku.items()
            if record_id in missing_template_ids
        )),
        product_skus=tuple(sorted(
            sku
            for sku, record_id in component_product_by_sku.items()
            if record_id in missing_product_ids
        )),
    )


def apply_external_id_preparation(
    client: OdooClient,
    preparation: ExternalIdPreparation,
) -> tuple[int, int]:
    prepared_templates = client.ensure_external_ids(
        "product.template",
        preparation.template_ids,
    )
    prepared_products = client.ensure_external_ids(
        "product.product",
        preparation.product_ids,
    )
    remaining_templates = set(preparation.template_ids) - _existing_external_ids(
        client, "product.template", set(preparation.template_ids)
    )
    remaining_products = set(preparation.product_ids) - _existing_external_ids(
        client, "product.product", set(preparation.product_ids)
    )
    if remaining_templates or remaining_products:
        raise RuntimeError(
            "Po paruošimo daliai įrašų External ID vis dar nesukurti."
        )
    return prepared_templates, prepared_products
