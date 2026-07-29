from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bom_release.models import (
    BomReleasePlan,
    BomReleasePlanItem,
    ReleaseAction,
    ReleaseStatus,
)
from odoo_client import OdooClient


DEFAULT_SHARED_DATA_ROOT = Path(
    r"C:\Projects\furnibox-shared-data"
)
DATASET_SUBDIR = Path(
    "validated_datasets"
) / "production"


class BomReleaseAnalysisError(RuntimeError):
    """Nepavyko saugiai sudaryti BOM release plano."""


def canon(value: Any) -> str:
    return str(value or "").strip().upper()


def many2one_id(value: Any) -> int | None:
    if (
        isinstance(value, (list, tuple))
        and value
    ):
        try:
            return int(value[0])
        except (TypeError, ValueError):
            return None

    if isinstance(value, int):
        return value

    return None


def _shared_data_root() -> Path:
    configured = os.getenv(
        "FURNIBOX_SHARED_DATA_DIR",
        "",
    ).strip()

    if configured:
        return Path(configured)

    return DEFAULT_SHARED_DATA_ROOT


def load_latest_dataset_record(
    dataset_path: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    if dataset_path is not None:
        path = dataset_path.resolve()
        if not path.exists():
            raise FileNotFoundError(
                f"Nerastas Dataset failas: {path}"
            )
    else:
        directory = (
            _shared_data_root()
            / DATASET_SUBDIR
        )

        if not directory.exists():
            raise FileNotFoundError(
                "Nerastas Production Dataset katalogas: "
                f"{directory}"
            )

        candidates = list(
            directory.glob("*.json")
        )

        if not candidates:
            raise FileNotFoundError(
                f"Kataloge nėra Dataset JSON: {directory}"
            )

        path = max(
            candidates,
            key=lambda item: item.stat().st_mtime,
        )

    try:
        record = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise BomReleaseAnalysisError(
            f"Nepavyko nuskaityti Dataset {path}: {exc}"
        ) from exc

    if not isinstance(
        record.get("products"),
        list,
    ):
        raise BomReleaseAnalysisError(
            "Dataset neturi products sąrašo."
        )

    return record, path


class BomReleaseAnalyzer:
    """Tik skaito Product Catalog ir Odoo; nieko nekeičia."""

    def __init__(
        self,
        client: OdooClient,
        *,
        environment: str = "production",
    ) -> None:
        self.client = client
        self.environment = environment

    def build_release_plan(
        self,
        *,
        release_id: str,
        release_reference: str,
        dataset_record: dict[str, Any],
        dataset_path: Path,
    ) -> BomReleasePlan:
        normalized_release_id = str(
            release_id or ""
        ).strip()
        normalized_reference = str(
            release_reference or ""
        ).strip()

        if not normalized_release_id:
            raise ValueError(
                "Nenurodytas release_id."
            )

        if not normalized_reference:
            raise ValueError(
                "Nenurodytas release_reference."
            )

        products = self.client.search_read_all(
            "product.product",
            [],
            [
                "id",
                "default_code",
                "active",
                "product_tmpl_id",
                "display_name",
            ],
            context={
                "active_test": False,
            },
        )

        product_ids_by_sku: dict[
            str,
            list[int],
        ] = defaultdict(list)
        product_by_id: dict[
            int,
            dict[str, Any],
        ] = {}
        variant_ids_by_template: dict[
            int,
            list[int],
        ] = defaultdict(list)

        for product in products:
            product_id = int(product["id"])
            product_by_id[product_id] = product

            sku = canon(
                product.get("default_code")
            )
            if sku:
                product_ids_by_sku[
                    sku
                ].append(product_id)

            template_id = many2one_id(
                product.get(
                    "product_tmpl_id"
                )
            )
            if template_id is not None:
                variant_ids_by_template[
                    template_id
                ].append(product_id)

        boms = self.client.search_read_all(
            "mrp.bom",
            [],
            [
                "id",
                "code",
                "active",
                "sequence",
                "type",
                "product_id",
                "product_tmpl_id",
                "product_qty",
                "write_date",
            ],
            context={
                "active_test": False,
            },
        )

        boms_by_parent_sku: dict[
            str,
            list[dict[str, Any]],
        ] = defaultdict(list)

        unresolved_bom_ids: list[int] = []

        for bom in boms:
            parent_sku = self._resolve_parent_sku(
                bom=bom,
                product_by_id=product_by_id,
                variant_ids_by_template=(
                    variant_ids_by_template
                ),
            )

            if parent_sku:
                boms_by_parent_sku[
                    parent_sku
                ].append(bom)
            else:
                unresolved_bom_ids.append(
                    int(bom["id"])
                )

        dataset_products = [
            row
            for row in dataset_record[
                "products"
            ]
            if (
                canon(row.get("sku"))
                and isinstance(
                    row.get("components"),
                    list,
                )
            )
        ]

        items: list[BomReleasePlanItem] = []

        for record in dataset_products:
            parent_sku = canon(
                record.get("sku")
            )

            component_skus = tuple(
                sorted(
                    {
                        canon(
                            component.get("sku")
                        )
                        for component
                        in record.get(
                            "components",
                            [],
                        )
                        if canon(
                            component.get("sku")
                        )
                    }
                )
            )

            parent_ids = tuple(
                sorted(
                    product_ids_by_sku.get(
                        parent_sku,
                        [],
                    )
                )
            )

            product_exists = (
                len(parent_ids) == 1
            )
            product_id = (
                parent_ids[0]
                if product_exists
                else None
            )
            template_id = (
                many2one_id(
                    product_by_id[
                        product_id
                    ].get(
                        "product_tmpl_id"
                    )
                )
                if product_id is not None
                else None
            )

            missing_components = tuple(
                sku
                for sku in component_skus
                if len(
                    product_ids_by_sku.get(
                        sku,
                        [],
                    )
                )
                != 1
            )

            parent_boms = (
                boms_by_parent_sku.get(
                    parent_sku,
                    [],
                )
            )

            sequence_zero_boms = [
                bom
                for bom in parent_boms
                if (
                    bool(
                        bom.get(
                            "active",
                            True,
                        )
                    )
                    and int(
                        bom.get(
                            "sequence",
                            0,
                        )
                        or 0
                    )
                    == 0
                )
            ]

            release_boms = [
                bom
                for bom in parent_boms
                if str(
                    bom.get("code")
                    or ""
                ).strip()
                == normalized_reference
            ]

            active_bom = (
                max(
                    sequence_zero_boms,
                    key=lambda bom: (
                        str(
                            bom.get(
                                "write_date"
                            )
                            or ""
                        ),
                        int(bom["id"]),
                    ),
                )
                if sequence_zero_boms
                else None
            )

            release_bom = (
                max(
                    release_boms,
                    key=lambda bom: int(
                        bom["id"]
                    ),
                )
                if release_boms
                else None
            )

            blocking_reasons: list[
                str
            ] = []
            warnings: list[str] = []

            if not parent_ids:
                blocking_reasons.append(
                    "Parent SKU nerastas Odoo."
                )
            elif len(parent_ids) > 1:
                blocking_reasons.append(
                    "Odoo rasti keli produktai su tuo pačiu Parent SKU."
                )

            if missing_components:
                blocking_reasons.append(
                    "Trūksta komponentų arba jų SKU dubliuoti."
                )

            if len(
                sequence_zero_boms
            ) > 1:
                blocking_reasons.append(
                    "Rasti keli aktyvūs Sequence 0 BOM."
                )

            if not component_skus:
                blocking_reasons.append(
                    "Dataset BOM neturi komponentų."
                )

            bom_type = str(
                record.get("bom_type")
                or ""
            ).strip()

            if not bom_type:
                blocking_reasons.append(
                    "Dataset BOM tipas nenustatytas."
                )

            operation_count = len(
                record.get(
                    "operations",
                    [],
                )
                or []
            )

            if release_boms:
                if len(release_boms) > 1:
                    blocking_reasons.append(
                        "Tam pačiam Parent SKU yra keli BOM su release reference."
                    )
                else:
                    warnings.append(
                        "Release BOM jau egzistuoja; turinys šiame Analyze etape dar nelyginamas."
                    )

            if blocking_reasons:
                action = ReleaseAction.BLOCK
                status = ReleaseStatus.BLOCKED
            elif release_bom is not None:
                action = ReleaseAction.SKIP
                status = (
                    ReleaseStatus.ALREADY_EXISTS
                )
            else:
                action = ReleaseAction.CREATE
                status = ReleaseStatus.READY

            items.append(
                BomReleasePlanItem(
                    parent_sku=parent_sku,
                    bom_type=bom_type,
                    component_count=len(
                        component_skus
                    ),
                    operation_count=(
                        operation_count
                    ),
                    product_exists=(
                        product_exists
                    ),
                    product_id=product_id,
                    product_template_id=(
                        template_id
                    ),
                    active_bom_count=len(
                        sequence_zero_boms
                    ),
                    active_bom_id=(
                        int(
                            active_bom["id"]
                        )
                        if active_bom
                        else None
                    ),
                    active_reference=(
                        str(
                            active_bom.get(
                                "code"
                            )
                            or ""
                        ).strip()
                        if active_bom
                        else ""
                    ),
                    active_sequence=(
                        int(
                            active_bom.get(
                                "sequence",
                                0,
                            )
                            or 0
                        )
                        if active_bom
                        else None
                    ),
                    active_bom_type=(
                        str(
                            active_bom.get(
                                "type"
                            )
                            or ""
                        ).strip()
                        if active_bom
                        else ""
                    ),
                    release_exists=(
                        release_bom is not None
                    ),
                    release_bom_id=(
                        int(
                            release_bom["id"]
                        )
                        if release_bom
                        else None
                    ),
                    release_reference=(
                        normalized_reference
                    ),
                    missing_components=(
                        missing_components
                    ),
                    duplicate_product_ids=(
                        parent_ids
                        if len(parent_ids) > 1
                        else tuple()
                    ),
                    action=action,
                    status=status,
                    blocking_reasons=tuple(
                        blocking_reasons
                    ),
                    warnings=tuple(warnings),
                )
            )

        items.sort(
            key=lambda item: (
                item.status.value,
                item.parent_sku,
            )
        )

        plan_warnings = []
        if unresolved_bom_ids:
            plan_warnings.append(
                "Dalis istorinių Odoo BOM nepriskirta Parent SKU: "
                + ", ".join(
                    str(value)
                    for value
                    in unresolved_bom_ids[:20]
                )
                + (
                    " ..."
                    if len(
                        unresolved_bom_ids
                    )
                    > 20
                    else ""
                )
            )

        plan = BomReleasePlan(
            release_id=normalized_release_id,
            release_reference=(
                normalized_reference
            ),
            environment=self.environment,
            dataset_id=str(
                dataset_record.get(
                    "dataset_id"
                )
                or ""
            ),
            dataset_batch_reference=str(
                dataset_record.get(
                    "batch_reference"
                )
                or ""
            ),
            dataset_path=str(
                dataset_path.resolve()
            ),
            created_at_utc=datetime.now(
                timezone.utc
            ).isoformat(),
            items=items,
        )

        # Plan warnings are currently represented as a synthetic blocked
        # item only if they can affect current Dataset parents. Historical
        # unresolved Odoo BOM alone does not block the release plan.
        return plan

    @staticmethod
    def _resolve_parent_sku(
        *,
        bom: dict[str, Any],
        product_by_id: dict[
            int,
            dict[str, Any],
        ],
        variant_ids_by_template: dict[
            int,
            list[int],
        ],
    ) -> str:
        product_id = many2one_id(
            bom.get("product_id")
        )

        if product_id is not None:
            return canon(
                product_by_id.get(
                    product_id,
                    {},
                ).get("default_code")
            )

        template_id = many2one_id(
            bom.get("product_tmpl_id")
        )

        if template_id is None:
            return ""

        candidates = [
            product_by_id[product_id]
            for product_id
            in variant_ids_by_template.get(
                template_id,
                [],
            )
            if canon(
                product_by_id[
                    product_id
                ].get("default_code")
            )
        ]

        active_candidates = [
            product
            for product in candidates
            if product.get(
                "active",
                True,
            )
        ]

        resolved = (
            active_candidates
            or candidates
        )

        if len(resolved) != 1:
            return ""

        return canon(
            resolved[0].get(
                "default_code"
            )
        )
