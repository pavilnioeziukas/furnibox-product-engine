from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ReleaseAction(StrEnum):
    CREATE = "CREATE"
    SKIP = "SKIP"
    BLOCK = "BLOCK"


class ReleaseStatus(StrEnum):
    READY = "READY"
    ALREADY_EXISTS = "ALREADY EXISTS"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ActiveBomInfo:
    bom_id: int
    reference: str
    sequence: int
    bom_type: str
    write_date: str


@dataclass(frozen=True)
class BomReleasePlanItem:
    parent_sku: str
    bom_type: str
    component_count: int
    operation_count: int

    product_exists: bool
    product_id: int | None
    product_template_id: int | None

    active_bom_count: int
    active_bom_id: int | None
    active_reference: str
    active_sequence: int | None
    active_bom_type: str

    release_exists: bool
    release_bom_id: int | None
    release_reference: str

    missing_components: tuple[str, ...] = field(
        default_factory=tuple
    )
    duplicate_product_ids: tuple[int, ...] = field(
        default_factory=tuple
    )

    action: ReleaseAction = ReleaseAction.BLOCK
    status: ReleaseStatus = ReleaseStatus.BLOCKED
    blocking_reasons: tuple[str, ...] = field(
        default_factory=tuple
    )
    warnings: tuple[str, ...] = field(
        default_factory=tuple
    )

    @property
    def missing_component_count(self) -> int:
        return len(self.missing_components)

    @property
    def multiple_sequence_zero(self) -> bool:
        return self.active_bom_count > 1

    @property
    def is_ready(self) -> bool:
        return self.status in {
            ReleaseStatus.READY,
            ReleaseStatus.ALREADY_EXISTS,
        }

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["action"] = self.action.value
        result["status"] = self.status.value
        result["missing_components"] = "; ".join(
            self.missing_components
        )
        result["duplicate_product_ids"] = "; ".join(
            str(value)
            for value in self.duplicate_product_ids
        )
        result["blocking_reasons"] = "; ".join(
            self.blocking_reasons
        )
        result["warnings"] = "; ".join(
            self.warnings
        )
        return result


@dataclass
class BomReleasePlan:
    release_id: str
    release_reference: str
    environment: str
    dataset_id: str
    dataset_batch_reference: str
    dataset_path: str
    created_at_utc: str

    items: list[BomReleasePlanItem] = field(
        default_factory=list
    )

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def ready_count(self) -> int:
        return sum(
            item.status == ReleaseStatus.READY
            for item in self.items
        )

    @property
    def already_exists_count(self) -> int:
        return sum(
            item.status
            == ReleaseStatus.ALREADY_EXISTS
            for item in self.items
        )

    @property
    def blocked_count(self) -> int:
        return sum(
            item.status == ReleaseStatus.BLOCKED
            for item in self.items
        )

    @property
    def missing_parent_count(self) -> int:
        return sum(
            not item.product_exists
            for item in self.items
        )

    @property
    def missing_component_parent_count(self) -> int:
        return sum(
            bool(item.missing_components)
            for item in self.items
        )

    @property
    def multiple_sequence_zero_count(self) -> int:
        return sum(
            item.multiple_sequence_zero
            for item in self.items
        )

    @property
    def can_generate(self) -> bool:
        return self.blocked_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "release_reference": self.release_reference,
            "environment": self.environment,
            "dataset_id": self.dataset_id,
            "dataset_batch_reference": (
                self.dataset_batch_reference
            ),
            "dataset_path": self.dataset_path,
            "created_at_utc": self.created_at_utc,
            "total_count": self.total_count,
            "ready_count": self.ready_count,
            "already_exists_count": (
                self.already_exists_count
            ),
            "blocked_count": self.blocked_count,
            "missing_parent_count": (
                self.missing_parent_count
            ),
            "missing_component_parent_count": (
                self.missing_component_parent_count
            ),
            "multiple_sequence_zero_count": (
                self.multiple_sequence_zero_count
            ),
            "can_generate": self.can_generate,
            "items": [
                item.to_dict()
                for item in self.items
            ],
        }
