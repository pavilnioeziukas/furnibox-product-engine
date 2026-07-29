from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from manifest.manifest_hash import calculate_bom_hash
from manifest.manifest_models import (
    BomManifest,
    ManifestBom,
    ManifestComponent,
    ManifestOperation,
    ManifestOutputFile,
    ManifestSource,
)
from manifest.manifest_paths import (
    manifest_environment_dir,
)


SCHEMA_VERSION = "1.0"
MANIFEST_TYPE = "bom_import_package"


class ManifestWriterError(RuntimeError):
    """Nepavyko sukurti arba išsaugoti BOM manifesto."""


def calculate_file_hash(
    path: Path,
    *,
    chunk_size: int = 1024 * 1024,
) -> str:
    if not path.exists():
        raise ManifestWriterError(
            f"Failas nerastas: {path}"
        )

    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def normalize_quantity(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ManifestWriterError(
            f"Neteisingas BOM komponento kiekis: {value!r}"
        ) from exc


def build_components(
    record: dict[str, Any],
) -> list[ManifestComponent]:
    root_sku = str(
        record.get("sku") or ""
    ).strip()

    level = int(
        record.get("level") or 0
    )

    components: list[ManifestComponent] = []

    for line in record.get("lines", []):
        component_sku = str(
            line.get("component") or ""
        ).strip()

        if not component_sku:
            raise ManifestWriterError(
                f"BOM {root_sku} turi komponentą be SKU."
            )

        quantity = normalize_quantity(
            line.get("quantity")
        )

        components.append(
            ManifestComponent(
                sku=component_sku,
                quantity=quantity,
                parent_sku=root_sku,
                level=level,
                path=(
                    f"{root_sku} > {component_sku}"
                ),
            )
        )

    return components


def build_operations(
    record: dict[str, Any],
) -> list[ManifestOperation]:
    operations: list[ManifestOperation] = []

    for operation in record.get(
        "operations",
        [],
    ):
        raw_time = operation.get("time")

        try:
            operation_time = float(
                raw_time or 0
            )
        except (TypeError, ValueError) as exc:
            raise ManifestWriterError(
                "Neteisingas operacijos laikas "
                f"{raw_time!r} BOM {record.get('sku')}"
            ) from exc

        operations.append(
            ManifestOperation(
                name=str(
                    operation.get("name") or ""
                ).strip(),
                workcenter=str(
                    operation.get("workcenter") or ""
                ).strip(),
                time_mode=str(
                    operation.get("time_mode") or ""
                ).strip(),
                time=operation_time,
                sequence=int(
                    operation.get("sequence") or 0
                ),
            )
        )

    return operations


def build_manifest_bom(
    *,
    record: dict[str, Any],
    batch_reference: str,
    bom_type: str,
) -> ManifestBom:
    root_sku = str(
        record.get("sku") or ""
    ).strip()

    if not root_sku:
        raise ManifestWriterError(
            "BOM įrašas neturi SKU."
        )

    components = build_components(record)
    operations = build_operations(record)

    bom_hash, bom_signature = calculate_bom_hash(
        root_sku=root_sku,
        bom_reference=batch_reference,
        bom_type=bom_type,
        components=components,
    )

    return ManifestBom(
        root_sku=root_sku,
        level=int(
            record.get("level") or 0
        ),
        bom_reference=batch_reference,
        bom_type=bom_type,
        generated_from=str(
            record.get("generated_from") or ""
        ).strip(),
        bom_hash=bom_hash,
        bom_signature=bom_signature,
        components=components,
        operations=operations,
    )


def build_output_file(
    *,
    path: Path,
    bom_count: int,
    purpose: str,
) -> ManifestOutputFile:
    resolved_path = path.resolve()

    return ManifestOutputFile(
        file_name=resolved_path.name,
        file_hash=calculate_file_hash(
            resolved_path
        ),
        file_size_bytes=resolved_path.stat().st_size,
        bom_count=bom_count,
        purpose=purpose,
    )


def write_import_package_manifest(
    *,
    environment: str,
    batch_reference: str,
    source_file: Path,
    manufacture_records: Iterable[
        dict[str, Any]
    ],
    kit_records: Iterable[
        dict[str, Any]
    ],
    output_files: list[
        tuple[Path, int, str]
    ],
    product_engine_version: str = "",
) -> Path:
    environment_normalized = (
        str(environment or "")
        .strip()
        .lower()
    )

    if environment_normalized not in {
        "stage",
        "production",
    }:
        raise ManifestWriterError(
            f"Neleistina aplinka: {environment!r}"
        )

    source_file = source_file.resolve()

    if not source_file.exists():
        raise ManifestWriterError(
            f"Reform šaltinio failas nerastas: "
            f"{source_file}"
        )

    manufacture_records = list(
        manufacture_records
    )
    kit_records = list(
        kit_records
    )

    manifest_boms: list[ManifestBom] = []

    for record in manufacture_records:
        manifest_boms.append(
            build_manifest_bom(
                record=record,
                batch_reference=batch_reference,
                bom_type="MANUFACTURE",
            )
        )

    for record in kit_records:
        manifest_boms.append(
            build_manifest_bom(
                record=record,
                batch_reference=batch_reference,
                bom_type="KIT",
            )
        )

    manifest_boms.sort(
        key=lambda bom: (
            bom.level,
            bom.root_sku,
            bom.bom_type,
        )
    )

    manifest_output_files = [
        build_output_file(
            path=path,
            bom_count=bom_count,
            purpose=purpose,
        )
        for path, bom_count, purpose in output_files
    ]

    created_at = datetime.now(
        timezone.utc
    )

    manifest = BomManifest(
        schema_version=SCHEMA_VERSION,
        manifest_type=MANIFEST_TYPE,
        manifest_id=str(uuid.uuid4()),
        batch_reference=batch_reference,
        created_at_utc=created_at.isoformat(),
        environment=environment_normalized,
        source=ManifestSource(
            source_file=source_file.name,
            source_sheet="BOM - Input",
            source_file_hash=calculate_file_hash(
                source_file
            ),
        ),
        product_engine_version=(
            product_engine_version
        ),
        output_files=manifest_output_files,
        boms=manifest_boms,
    )

    output_directory = (
        manifest_environment_dir()
        / created_at.strftime("%Y-%m-%d")
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = created_at.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_path = (
        output_directory
        / (
            f"BOM_Import_Manifest_"
            f"{timestamp}.json"
        )
    )

    output_path.write_text(
        json.dumps(
            manifest.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return output_path.resolve()