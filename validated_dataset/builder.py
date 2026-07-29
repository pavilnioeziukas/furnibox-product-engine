from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from manifest.manifest_hash import calculate_bom_hash
from manifest.manifest_models import ManifestComponent
from validated_dataset.models import (
    ValidatedComponent,
    ValidatedDataset,
    ValidatedOperation,
    ValidatedProduct,
)
from validated_dataset.prepared_models import (
    PreparedBom,
    PreparedBomError,
    prepare_boms,
)


DATASET_SCHEMA_VERSION = "1.0"


class DatasetBuildError(RuntimeError):
    """Nepavyko sukurti Validated Product Dataset."""


class DatasetBuilder:
    """Formuoja Dataset iš Product Engine jau patikrintų BOM įrašų."""

    def build(
        self,
        *,
        environment: str,
        batch_reference: str,
        source_file: str,
        source_file_hash: str,
        manufacture_records: Iterable[dict[str, Any]],
        kit_records: Iterable[dict[str, Any]],
    ) -> ValidatedDataset:
        normalized_environment = str(
            environment or ""
        ).strip().lower()

        if normalized_environment == "prod":
            normalized_environment = "production"

        if normalized_environment not in {
            "stage",
            "production",
        }:
            raise DatasetBuildError(
                f"Neleistina aplinka: {environment!r}"
            )

        normalized_batch_reference = str(
            batch_reference or ""
        ).strip()

        if not normalized_batch_reference:
            raise DatasetBuildError(
                "Nenurodytas batch_reference."
            )

        normalized_source_file = str(
            source_file or ""
        ).strip()

        if not normalized_source_file:
            raise DatasetBuildError(
                "Nenurodytas Reform šaltinio failas."
            )

        normalized_source_hash = str(
            source_file_hash or ""
        ).strip()

        if not normalized_source_hash:
            raise DatasetBuildError(
                "Nenurodytas Reform šaltinio failo hash."
            )

        try:
            prepared_boms = prepare_boms(
                manufacture_records=manufacture_records,
                kit_records=kit_records,
            )
        except PreparedBomError as exc:
            raise DatasetBuildError(
                f"Nepavyko paruošti BOM Dataset generavimui: {exc}"
            ) from exc

        products = [
            self.build_product(prepared_bom)
            for prepared_bom in prepared_boms
        ]

        if not products:
            raise DatasetBuildError(
                "Nėra nė vieno produkto Validated Dataset generavimui."
            )

        return ValidatedDataset(
            schema_version=DATASET_SCHEMA_VERSION,
            dataset_id=str(uuid.uuid4()),
            batch_reference=normalized_batch_reference,
            environment=normalized_environment,
            created_at_utc=datetime.now(
                timezone.utc
            ).isoformat(),
            source_file=normalized_source_file,
            source_file_hash=normalized_source_hash,
            products=products,
        )

    def build_product(
        self,
        prepared_bom: PreparedBom,
    ) -> ValidatedProduct:
        components = [
            ValidatedComponent(
                sku=component.sku,
                quantity=component.quantity,
                parent_sku=prepared_bom.sku,
                level=prepared_bom.level,
            )
            for component in prepared_bom.components
        ]

        operations = [
            ValidatedOperation(
                name=operation.name,
                workcenter=operation.workcenter,
                time_mode=operation.time_mode,
                time_minutes=operation.time_minutes,
                sequence=operation.sequence,
            )
            for operation in prepared_bom.operations
        ]

        hash_components = [
            ManifestComponent(
                sku=component.sku,
                quantity=component.quantity,
                parent_sku=component.parent_sku,
                level=component.level,
                path=(
                    f"{component.parent_sku} > "
                    f"{component.sku}"
                ),
            )
            for component in components
        ]

        # Sąmoningai nenaudojame batch_reference.
        # Content hash turi keistis tik pasikeitus BOM turiniui,
        # o ne kiekvieną kartą sugeneravus naują paketą.
        content_hash, content_signature = (
            calculate_bom_hash(
                root_sku=prepared_bom.sku,
                bom_reference="",
                bom_type=prepared_bom.bom_type,
                components=hash_components,
            )
        )

        source_sku = (
            prepared_bom.generated_from
            or prepared_bom.sku
        )

        product_type = (
            prepared_bom.reform_category
            or prepared_bom.bom_type
        )

        return ValidatedProduct(
            sku=prepared_bom.sku,
            product_type=product_type,
            bom_type=prepared_bom.bom_type,
            level=prepared_bom.level,
            source_sku=source_sku,
            generated_from=prepared_bom.generated_from,
            reform_category=prepared_bom.reform_category,
            content_hash=content_hash,
            content_signature=content_signature,
            components=components,
            operations=operations,
        )