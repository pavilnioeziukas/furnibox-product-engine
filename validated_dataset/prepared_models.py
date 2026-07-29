from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


class PreparedBomError(RuntimeError):
    """Netinkami Product Engine paruošto BOM duomenys."""


@dataclass(frozen=True)
class PreparedComponent:
    sku: str
    quantity: float

    @classmethod
    def from_record(
        cls,
        record: dict[str, Any],
    ) -> "PreparedComponent":
        sku = str(
            record.get("component") or ""
        ).strip()

        if not sku:
            raise PreparedBomError(
                "BOM komponentas neturi SKU."
            )

        raw_quantity = record.get("quantity")

        try:
            quantity = float(raw_quantity)
        except (TypeError, ValueError) as exc:
            raise PreparedBomError(
                f"Komponentas {sku} turi netinkamą kiekį: "
                f"{raw_quantity!r}"
            ) from exc

        if quantity <= 0:
            raise PreparedBomError(
                f"Komponentas {sku} turi neigiamą arba nulinį "
                f"kiekį: {quantity}"
            )

        return cls(
            sku=sku,
            quantity=quantity,
        )


@dataclass(frozen=True)
class PreparedOperation:
    name: str
    workcenter: str
    time_mode: str
    time_minutes: float
    sequence: int

    @classmethod
    def from_record(
        cls,
        record: dict[str, Any],
    ) -> "PreparedOperation":
        name = str(
            record.get("name") or ""
        ).strip()

        workcenter = str(
            record.get("workcenter") or ""
        ).strip()

        time_mode = str(
            record.get("time_mode") or ""
        ).strip()

        raw_time = record.get("time")

        try:
            time_minutes = float(raw_time or 0)
        except (TypeError, ValueError) as exc:
            raise PreparedBomError(
                f"Operacija {name or '<be pavadinimo>'} turi "
                f"netinkamą laiką: {raw_time!r}"
            ) from exc

        try:
            sequence = int(
                record.get("sequence") or 0
            )
        except (TypeError, ValueError) as exc:
            raise PreparedBomError(
                f"Operacija {name or '<be pavadinimo>'} turi "
                "netinkamą sequence."
            ) from exc

        if not name:
            raise PreparedBomError(
                "Operacija neturi pavadinimo."
            )

        if not workcenter:
            raise PreparedBomError(
                f"Operacija {name} neturi darbo centro."
            )

        if time_minutes < 0:
            raise PreparedBomError(
                f"Operacija {name} turi neigiamą laiką: "
                f"{time_minutes}"
            )

        return cls(
            name=name,
            workcenter=workcenter,
            time_mode=time_mode,
            time_minutes=time_minutes,
            sequence=sequence,
        )


@dataclass(frozen=True)
class PreparedBom:
    sku: str
    bom_type: str
    level: int

    generated_from: str
    reform_category: str

    components: list[PreparedComponent] = field(
        default_factory=list
    )

    operations: list[PreparedOperation] = field(
        default_factory=list
    )

    @classmethod
    def from_record(
        cls,
        record: dict[str, Any],
        *,
        bom_type: str,
    ) -> "PreparedBom":
        sku = str(
            record.get("sku") or ""
        ).strip()

        if not sku:
            raise PreparedBomError(
                "Paruoštas BOM neturi SKU."
            )

        normalized_bom_type = str(
            bom_type or ""
        ).strip().upper()

        if normalized_bom_type not in {
            "MANUFACTURE",
            "KIT",
        }:
            raise PreparedBomError(
                f"Neatpažintas BOM tipas: {bom_type!r}"
            )

        try:
            level = int(
                record.get("level") or 0
            )
        except (TypeError, ValueError) as exc:
            raise PreparedBomError(
                f"BOM {sku} turi netinkamą level."
            ) from exc

        if level < 1:
            raise PreparedBomError(
                f"BOM {sku} turi netinkamą level={level}"
            )

        components = [
            PreparedComponent.from_record(line)
            for line in record.get("lines", [])
        ]

        if not components:
            raise PreparedBomError(
                f"BOM {sku} neturi komponentų."
            )

        operations = [
            PreparedOperation.from_record(operation)
            for operation in record.get(
                "operations",
                [],
            )
        ]

        if (
            normalized_bom_type == "MANUFACTURE"
            and not operations
        ):
            raise PreparedBomError(
                f"Manufacture BOM {sku} neturi operacijų."
            )

        if (
            normalized_bom_type == "KIT"
            and operations
        ):
            raise PreparedBomError(
                f"KIT BOM {sku} neturi turėti operacijų."
            )

        return cls(
            sku=sku,
            bom_type=normalized_bom_type,
            level=level,
            generated_from=str(
                record.get("generated_from") or ""
            ).strip(),
            reform_category=str(
                record.get("subcategory") or ""
            ).strip(),
            components=components,
            operations=operations,
        )


def prepare_boms(
    *,
    manufacture_records: Iterable[
        dict[str, Any]
    ],
    kit_records: Iterable[
        dict[str, Any]
    ],
) -> list[PreparedBom]:
    prepared: list[PreparedBom] = []

    for record in manufacture_records:
        prepared.append(
            PreparedBom.from_record(
                record,
                bom_type="MANUFACTURE",
            )
        )

    for record in kit_records:
        prepared.append(
            PreparedBom.from_record(
                record,
                bom_type="KIT",
            )
        )

    duplicate_skus = sorted(
        sku
        for sku in {
            item.sku
            for item in prepared
        }
        if sum(
            item.sku == sku
            for item in prepared
        ) > 1
    )

    if duplicate_skus:
        raise PreparedBomError(
            "Paruoštuose BOM kartojasi SKU: "
            + ", ".join(duplicate_skus)
        )

    return sorted(
        prepared,
        key=lambda item: (
            item.level,
            item.sku,
            item.bom_type,
        ),
    )