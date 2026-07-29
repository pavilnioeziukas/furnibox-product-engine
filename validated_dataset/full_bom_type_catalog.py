from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bom_type_inference_v3 import (
    business_rule,
    canon,
    infer_from_analogs,
    load_reference_boms,
)


MANUFACTURE = "MANUFACTURE"
KIT = "KIT"


class FullBomTypeCatalogError(RuntimeError):
    """Nepavyko sudaryti pilno Reform BOM tipų katalogo."""


@dataclass(frozen=True)
class FullBomTypeAssignment:
    sku: str
    bom_type: str
    source: str
    confidence: str
    reference_sku: str
    reason: str


@dataclass(frozen=True)
class FullBomTypeCatalog:
    assignments: dict[str, FullBomTypeAssignment]
    unresolved: dict[str, str]

    @property
    def resolved_count(self) -> int:
        return len(self.assignments)

    @property
    def unresolved_count(self) -> int:
        return len(self.unresolved)

    def get(
        self,
        sku: str,
    ) -> FullBomTypeAssignment | None:
        return self.assignments.get(
            canon(sku)
        )


def normalize_odoo_bom_type(
    value: object,
) -> str:
    normalized = canon(value).lower()

    if normalized in {
        "normal",
        "manufacture",
        "manufacture this product",
    }:
        return MANUFACTURE

    if normalized in {
        "phantom",
        "kit",
    }:
        return KIT

    return ""


def normalize_proposed_bom_type(
    value: object,
) -> str:
    normalized = canon(value).lower()

    if normalized == "normal":
        return MANUFACTURE

    if normalized == "phantom":
        return KIT

    return ""


def build_full_bom_type_catalog(
    *,
    reform_products: dict[str, dict],
    reform_lines: dict[str, list[dict]],
    odoo_map_path: Path,
    allow_review_assignments: bool = False,
) -> FullBomTypeCatalog:
    if not odoo_map_path.exists():
        raise FullBomTypeCatalogError(
            f"Nerastas Odoo BOM etalonų failas: "
            f"{odoo_map_path}"
        )

    references = load_reference_boms(
        odoo_map_path
    )

    references_by_sku = {
        canon(reference.get("Canonical SKU")): reference
        for reference in references
        if canon(reference.get("Canonical SKU"))
    }

    assignments: dict[
        str,
        FullBomTypeAssignment,
    ] = {}

    unresolved: dict[str, str] = {}

    for raw_sku in sorted(reform_lines):
        sku = canon(raw_sku)

        if not sku:
            continue

        existing_reference = references_by_sku.get(
            sku
        )

        # 1. Jei produktas jau turi aktyvų Production BOM,
        # jo faktinis tipas yra stipriausias etalonas.
        if existing_reference is not None:
            bom_type = normalize_odoo_bom_type(
                existing_reference.get("BOM Type")
            )

            if not bom_type:
                unresolved[sku] = (
                    "Aktyvus Odoo BOM turi neatpažintą tipą: "
                    f"{existing_reference.get('BOM Type')!r}"
                )
                continue

            assignments[sku] = FullBomTypeAssignment(
                sku=sku,
                bom_type=bom_type,
                source="ODOO_ACTIVE_BOM",
                confidence="HIGH",
                reference_sku=sku,
                reason=(
                    "Naudojamas aktyvaus Production BOM tipas."
                ),
            )
            continue

        product = (
            reform_products.get(sku)
            or reform_products.get(raw_sku)
            or {}
        )

        category = str(
            product.get("category") or ""
        ).strip()

        # 2. Naujiems / Odoo dar neegzistuojantiems BOM
        # pirmiausia taikoma patvirtinta verslo taisyklė.
        fixed = business_rule(
            category,
            sku,
        )

        if fixed is not None:
            proposed_type, reason = fixed
            bom_type = normalize_proposed_bom_type(
                proposed_type
            )

            if not bom_type:
                unresolved[sku] = (
                    "Verslo taisyklė grąžino neatpažintą "
                    f"BOM tipą: {proposed_type!r}"
                )
                continue

            assignments[sku] = FullBomTypeAssignment(
                sku=sku,
                bom_type=bom_type,
                source="BUSINESS_RULE",
                confidence="HIGH",
                reference_sku="",
                reason=reason,
            )
            continue

        # 3. Jei tiesioginės taisyklės nėra,
        # naudojami Production analogai.
        proposed_type, confidence, analog, reason = (
            infer_from_analogs(
                sku,
                references,
            )
        )

        bom_type = normalize_proposed_bom_type(
            proposed_type
        )

        if not bom_type:
            unresolved[sku] = reason
            continue

        if (
            confidence != "HIGH"
            and not allow_review_assignments
        ):
            unresolved[sku] = (
                f"{reason}; siūlomas tipas={bom_type}; "
                f"analogas={analog or '-'}; "
                f"confidence={confidence}"
            )
            continue

        assignments[sku] = FullBomTypeAssignment(
            sku=sku,
            bom_type=bom_type,
            source="PRODUCTION_ANALOG",
            confidence=confidence,
            reference_sku=analog,
            reason=reason,
        )

    return FullBomTypeCatalog(
        assignments=assignments,
        unresolved=unresolved,
    )