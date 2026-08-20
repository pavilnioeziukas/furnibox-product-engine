from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ProductStatus(StrEnum):
    UNCHANGED = "PRODUCT UNCHANGED"
    CREATE = "CREATE PRODUCT"
    UPDATE = "UPDATE PRODUCT"
    BLOCKED = "BLOCKED"


class BomStatus(StrEnum):
    UNCHANGED = "BOM UNCHANGED"
    CREATE = "CREATE BOM"
    ADD_COMPONENT = "ADD COMPONENT"
    REMOVE_COMPONENT = "REMOVE COMPONENT"
    CHANGE_QUANTITY = "CHANGE QUANTITY"
    CHANGE_TYPE = "CHANGE BOM TYPE"
    UPDATE_OPERATIONS = "UPDATE OPERATIONS"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Result:
    sku: str
    status: str
    changes: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["changes"] = list(self.changes)
        value["blocking_reasons"] = list(self.blocking_reasons)
        value["warnings"] = list(self.warnings)
        return value


@dataclass(frozen=True)
class Reconciliation:
    dataset_id: str
    environment: str
    created_at_utc: str
    products: tuple[Result, ...]
    boms: tuple[Result, ...]

    def to_dict(self) -> dict[str, Any]:
        from collections import Counter

        return {
            "schema_version": "1.0",
            "mode": "READ_ONLY",
            "dataset_id": self.dataset_id,
            "environment": self.environment,
            "created_at_utc": self.created_at_utc,
            "summary": {
                "product_count": len(self.products),
                "bom_count": len(self.boms),
                "product_statuses": dict(Counter(x.status for x in self.products)),
                "bom_statuses": dict(Counter(x.status for x in self.boms)),
            },
            "products": [x.to_dict() for x in self.products],
            "boms": [x.to_dict() for x in self.boms],
        }
