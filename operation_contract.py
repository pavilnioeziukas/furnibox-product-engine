"""Bendros BOM operacijų sutarties taisyklės."""

from __future__ import annotations

from typing import Any


def canon(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def product_category(record: dict[str, Any]) -> str:
    return canon(
        record.get("reform_category")
        or record.get("product_type")
        or record.get("part_group")
        or record.get("category")
    )


def is_cabinet_shelf(*, sku: str, category: str) -> bool:
    """Production CABINET SHELF yra Manufacture BOM be operacijų."""
    return canon(category) == "CABINET SHELF"


def required_operation_names(*, sku: str, category: str) -> set[str]:
    normalized_sku = canon(sku)
    normalized_category = canon(category)
    # Produkto paskirtis turi viršenybę prieš istorinį SKU prefiksą.
    # FPACK-WTP92-HRD001 yra CABINET HARDWARE komplektas, o ne spintelės
    # FPACK, todėl jam privalomas komplektavimas, ne pakavimas.
    if normalized_category == "CABINET HARDWARE":
        return {"KOMPLEKTAVIMAS"}
    if normalized_sku.startswith("APACK-") or normalized_category == "APACK":
        return {"SURINKIMAS", "PAKAVIMAS"}
    if normalized_sku.startswith("FPACK-") or normalized_category == "FPACK":
        return {"PAKAVIMAS"}
    if normalized_sku.endswith("-A") and "HRD" in normalized_sku:
        return {"KOMPLEKTAVIMAS"}
    return set()


def recognized_operation_names(operations: list[dict[str, Any]]) -> set[str]:
    """Grąžina sutarties operacijų tipus iš pilnų Production pavadinimų."""
    recognized: set[str] = set()
    required_tokens = ("SURINKIMAS", "PAKAVIMAS", "KOMPLEKTAVIMAS")
    for operation in operations:
        name = canon(operation.get("name"))
        for token in required_tokens:
            if token in name.split():
                recognized.add(token)
        # Production CABINET HARDWARE etalonuose ši operacija istoriškai
        # vadinama „Furnitūros atrinkimas“, bet funkciškai tai yra tas pats
        # komplektavimo etapas tame pačiame darbo centre.
        if name == "FURNITŪROS ATRINKIMAS":
            recognized.add("KOMPLEKTAVIMAS")
    return recognized


def manufacture_operations_required(*, sku: str, category: str) -> bool:
    """Nurodo, ar Manufacture BOM privalo turėti bent vieną operaciją."""
    if is_cabinet_shelf(sku=sku, category=category):
        return False
    return True
