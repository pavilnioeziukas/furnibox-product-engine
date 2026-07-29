from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidatedComponent:
    """Vienas tiesioginis produkto BOM komponentas."""

    sku: str
    quantity: float
    parent_sku: str
    level: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidatedOperation:
    """Viena Manufacture BOM operacija."""

    name: str
    workcenter: str
    time_mode: str
    time_minutes: float
    sequence: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidatedProduct:
    """Product Engine patvirtintas produktas ir jo BOM apibrėžimas."""

    sku: str
    product_type: str
    bom_type: str
    level: int

    source_sku: str
    generated_from: str
    reform_category: str

    content_hash: str
    content_signature: str

    components: list[ValidatedComponent] = field(
        default_factory=list
    )
    operations: list[ValidatedOperation] = field(
        default_factory=list
    )

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def operation_count(self) -> int:
        return len(self.operations)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)

        data["statistics"] = {
            "component_count": self.component_count,
            "operation_count": self.operation_count,
        }

        return data


@dataclass(frozen=True)
class ValidatedDataset:
    """Oficialus Product Engine patvirtintų produktų duomenų rinkinys."""

    schema_version: str
    dataset_id: str
    batch_reference: str
    environment: str
    created_at_utc: str

    source_file: str
    source_file_hash: str

    products: list[ValidatedProduct] = field(
        default_factory=list
    )

    @property
    def product_count(self) -> int:
        return len(self.products)

    def find_product(
        self,
        sku: str,
    ) -> ValidatedProduct | None:
        normalized_sku = str(sku or "").strip().upper()

        matches = [
            product
            for product in self.products
            if product.sku.strip().upper() == normalized_sku
        ]

        if not matches:
            return None

        if len(matches) > 1:
            raise ValueError(
                f"Dataset turi kelis produktus tuo pačiu SKU: "
                f"{normalized_sku}"
            )

        return matches[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "batch_reference": self.batch_reference,
            "environment": self.environment,
            "created_at_utc": self.created_at_utc,
            "source": {
                "file_name": self.source_file,
                "file_hash": self.source_file_hash,
            },
            "statistics": {
                "product_count": self.product_count,
                "component_rows": sum(
                    product.component_count
                    for product in self.products
                ),
                "operation_rows": sum(
                    product.operation_count
                    for product in self.products
                ),
            },
            "products": [
                product.to_dict()
                for product in self.products
            ],
        }