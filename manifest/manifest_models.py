from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ManifestSource:
    source_file: str
    source_sheet: str = ""
    source_file_hash: str = ""


@dataclass(frozen=True)
class ManifestOutputFile:
    file_name: str
    file_hash: str
    file_size_bytes: int
    bom_count: int
    purpose: str


@dataclass(frozen=True)
class ManifestComponent:
    sku: str
    quantity: float
    parent_sku: str
    level: int
    path: str


@dataclass(frozen=True)
class ManifestOperation:
    name: str
    workcenter: str
    time_mode: str
    time: float
    sequence: int


@dataclass(frozen=True)
class ManifestBom:
    root_sku: str
    level: int
    bom_reference: str
    bom_type: str
    generated_from: str
    bom_hash: str
    bom_signature: str

    components: list[ManifestComponent] = field(
        default_factory=list
    )

    operations: list[ManifestOperation] = field(
        default_factory=list
    )

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def operation_count(self) -> int:
        return len(self.operations)


@dataclass(frozen=True)
class BomManifest:
    schema_version: str
    manifest_type: str
    manifest_id: str
    batch_reference: str
    created_at_utc: str
    environment: str
    source: ManifestSource
    product_engine_version: str

    output_files: list[ManifestOutputFile] = field(
        default_factory=list
    )

    boms: list[ManifestBom] = field(
        default_factory=list
    )

    @property
    def bom_count(self) -> int:
        return len(self.boms)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)

        data["statistics"] = {
            "bom_count": self.bom_count,
            "component_rows": sum(
                bom.component_count
                for bom in self.boms
            ),
            "operation_rows": sum(
                bom.operation_count
                for bom in self.boms
            ),
            "output_file_count": len(
                self.output_files
            ),
        }

        return data