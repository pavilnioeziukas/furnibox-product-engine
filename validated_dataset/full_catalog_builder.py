from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from bom_import_manufacture_v5 import (
    KIT,
    MANUFACTURE,
    add_generated_apack_boms,
    add_generated_cabinet_assembled_kits,
    add_generated_hrd_assembled_boms,
    choose_apack_operation_template,
    choose_hrd_assembled_operation_template,
)
from bom_import_pilot_v1 import calculate_levels
from bom_import_pilot_v2 import choose_operation_template
from operation_contract import is_cabinet_shelf
from manifest.manifest_hash import calculate_bom_hash
from manifest.manifest_models import ManifestComponent
from validated_dataset.full_bom_type_catalog import FullBomTypeCatalog
from validated_dataset.models import (
    ValidatedComponent,
    ValidatedDataset,
    ValidatedOperation,
    ValidatedProduct,
)


class FullCatalogBuildError(RuntimeError):
    pass


def _category_for(
    sku: str,
    generated_from: str,
    reform_products: dict[str, dict],
) -> str:
    source_sku = generated_from or sku
    product = (
        reform_products.get(source_sku)
        or reform_products.get(sku)
        or {}
    )
    return str(product.get("category") or "").strip()


def build_full_validated_dataset(
    *,
    environment: str,
    batch_reference: str,
    source_file: Path,
    source_file_hash: str,
    reform_products: dict[str, dict],
    reform_lines: dict[str, list[dict]],
    type_catalog: FullBomTypeCatalog,
    operation_templates: dict[int, dict],
) -> ValidatedDataset:
    environment = str(environment or "").strip().lower()
    if environment == "prod":
        environment = "production"
    if environment not in {"stage", "production"}:
        raise FullCatalogBuildError(
            f"Neleistina aplinka: {environment!r}"
        )

    if type_catalog.unresolved_count:
        details = "\n".join(
            f"- {sku}: {reason}"
            for sku, reason in sorted(
                type_catalog.unresolved.items()
            )
        )
        raise FullCatalogBuildError(
            "Yra neišspręstų BOM tipų: "
            f"{type_catalog.unresolved_count}\n"
            f"{details}"
        )

    parents = set(reform_lines)
    lines = {
        sku: [dict(line) for line in bom_lines]
        for sku, bom_lines in reform_lines.items()
    }

    bom_types = {}
    for sku in parents:
        assignment = type_catalog.get(sku)
        if assignment is None:
            raise FullCatalogBuildError(
                f"Nerastas BOM tipas: {sku}"
            )
        bom_types[sku] = (
            MANUFACTURE
            if assignment.bom_type == "MANUFACTURE"
            else KIT
        )

    levels = calculate_levels(parents, lines)

    generated_apack = add_generated_apack_boms(
        parents, lines, levels, bom_types
    )
    generated_hrd = add_generated_hrd_assembled_boms(
        parents,
        lines,
        levels,
        bom_types,
        reform_products,
        reform_lines,
    )
    generated_cabinet = add_generated_cabinet_assembled_kits(
        parents,
        lines,
        levels,
        bom_types,
        reform_products,
        reform_lines,
    )
    generated_from = {
        **generated_apack,
        **generated_hrd,
        **generated_cabinet,
    }

    products = []

    for sku in sorted(
        parents,
        key=lambda value: (levels.get(value, 1), value),
    ):
        components = []
        for line in lines.get(sku, []):
            component_sku = str(
                line.get("component") or ""
            ).strip()
            quantity = float(
                line.get("quantity") or 0
            )
            if not component_sku or quantity <= 0:
                raise FullCatalogBuildError(
                    f"BOM {sku} turi netinkamą komponentą."
                )

            components.append(
                ValidatedComponent(
                    sku=component_sku,
                    quantity=quantity,
                    parent_sku=sku,
                    level=int(levels.get(sku, 1)),
                )
            )

        if not components:
            raise FullCatalogBuildError(
                f"BOM {sku} neturi komponentų."
            )

        bom_type = (
            "MANUFACTURE"
            if bom_types[sku] == MANUFACTURE
            else "KIT"
        )
        generated_source = generated_from.get(sku, "")
        category = _category_for(
            sku,
            generated_source,
            reform_products,
        )

        operations: list[ValidatedOperation] = []
        if bom_type == "MANUFACTURE":
            template: dict = {"operations": []}
            if not is_cabinet_shelf(sku=sku, category=category):
                try:
                    if sku in generated_hrd:
                        template = choose_hrd_assembled_operation_template(
                            operation_templates
                        )
                    elif sku in generated_apack:
                        template = choose_apack_operation_template(
                            sku,
                            category,
                            operation_templates,
                        )
                    else:
                        template = choose_operation_template(
                            sku,
                            category,
                            operation_templates,
                        )
                except ValueError as exc:
                    raise FullCatalogBuildError(
                        f"BOM {sku} operacijų etalonas nerastas: {exc}"
                    ) from exc

            for operation in template.get("operations", []):
                operations.append(
                    ValidatedOperation(
                        name=str(operation.get("name") or "").strip(),
                        workcenter=str(
                            operation.get("workcenter") or ""
                        ).strip(),
                        time_mode=str(
                            operation.get("time_mode") or ""
                        ).strip(),
                        time_minutes=float(
                            operation.get("time") or 0
                        ),
                        sequence=int(
                            operation.get("sequence") or 0
                        ),
                    )
                )
            if (
                not operations
                and not is_cabinet_shelf(sku=sku, category=category)
            ):
                raise FullCatalogBuildError(
                    f"Manufacture BOM {sku} neturi operacijų."
                )

        hash_components = [
            ManifestComponent(
                sku=component.sku,
                quantity=component.quantity,
                parent_sku=component.parent_sku,
                level=component.level,
                path=f"{component.parent_sku} > {component.sku}",
            )
            for component in components
        ]

        content_hash, content_signature = calculate_bom_hash(
            root_sku=sku,
            bom_reference="",
            bom_type=bom_type,
            components=hash_components,
        )

        products.append(
            ValidatedProduct(
                sku=sku,
                product_type=category or bom_type,
                bom_type=bom_type,
                level=int(levels.get(sku, 1)),
                source_sku=generated_source or sku,
                generated_from=generated_source,
                reform_category=category,
                content_hash=content_hash,
                content_signature=content_signature,
                components=components,
                operations=operations,
            )
        )

    return ValidatedDataset(
        schema_version="1.0",
        dataset_id=str(uuid.uuid4()),
        batch_reference=batch_reference,
        environment=environment,
        created_at_utc=datetime.now(
            timezone.utc
        ).isoformat(),
        source_file=source_file.name,
        source_file_hash=source_file_hash,
        products=products,
    )
