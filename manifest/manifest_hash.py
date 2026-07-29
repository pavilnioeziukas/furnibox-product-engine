from __future__ import annotations

import hashlib
from decimal import Decimal, InvalidOperation
from typing import Iterable

from manifest.manifest_models import ManifestComponent


class ManifestHashError(RuntimeError):
    """Nepavyko suformuoti stabilaus BOM parašo."""


def normalize_text(value: str | None) -> str:
    return str(value or "").strip().upper()


def normalize_quantity(value: float | int | str) -> str:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ManifestHashError(
            f"Neteisingas komponento kiekis: {value!r}"
        ) from exc

    normalized = decimal_value.normalize()

    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))

    return format(normalized, "f").rstrip("0").rstrip(".")


def canonical_component_lines(
    components: Iterable[ManifestComponent],
) -> list[str]:
    lines: list[str] = []

    for component in components:
        sku = normalize_text(component.sku)
        parent_sku = normalize_text(component.parent_sku)
        quantity = normalize_quantity(component.quantity)

        if not sku:
            raise ManifestHashError(
                "Komponentas neturi SKU."
            )

        lines.append(
            "|".join(
                [
                    sku,
                    quantity,
                    parent_sku,
                    str(int(component.level)),
                ]
            )
        )

    return sorted(lines)


def build_bom_signature(
    *,
    root_sku: str,
    bom_reference: str,
    bom_type: str,
    components: Iterable[ManifestComponent],
) -> str:
    normalized_root_sku = normalize_text(root_sku)
    normalized_reference = normalize_text(bom_reference)
    normalized_bom_type = normalize_text(bom_type)

    if not normalized_root_sku:
        raise ManifestHashError(
            "BOM neturi root SKU."
        )

    component_lines = canonical_component_lines(
        components
    )

    if not component_lines:
        raise ManifestHashError(
            f"BOM {normalized_root_sku} neturi komponentų."
        )

    signature_lines = [
        f"ROOT_SKU={normalized_root_sku}",
        f"BOM_REFERENCE={normalized_reference}",
        f"BOM_TYPE={normalized_bom_type}",
        "COMPONENTS:",
        *component_lines,
    ]

    return "\n".join(signature_lines)


def calculate_bom_hash(
    *,
    root_sku: str,
    bom_reference: str,
    bom_type: str,
    components: Iterable[ManifestComponent],
) -> tuple[str, str]:
    signature = build_bom_signature(
        root_sku=root_sku,
        bom_reference=bom_reference,
        bom_type=bom_type,
        components=components,
    )

    digest = hashlib.sha256(
        signature.encode("utf-8")
    ).hexdigest()

    return digest, signature