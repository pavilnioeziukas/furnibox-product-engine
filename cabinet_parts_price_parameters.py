from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CabinetPartsPriceParameters:
    back_rate_per_m2: float = 11.0
    processing_rate_per_m2: float = 17.04
    ww_material_rate_per_m2: float = 8.720350877192983
    bb_material_rate_per_m2: float = 7.153333333333333
    no_material_rate_per_m2: float = 8.720350877192983
    small_part_threshold_m2: float = 0.5
    small_part_surcharge: float = 1.0
    furnix_markup_percent: float = 0.0
    output_decimals: int = 4

    def material_rate(self, color: str) -> float | None:
        return {
            "WW": self.ww_material_rate_per_m2,
            "BB": self.bb_material_rate_per_m2,
            "NO": self.no_material_rate_per_m2,
        }.get(color)

DEFAULT_PARAMETERS = CabinetPartsPriceParameters()


def validate_parameters(document: dict) -> CabinetPartsPriceParameters:
    required = set(asdict(DEFAULT_PARAMETERS))
    missing = sorted(required - set(document))
    extra = sorted(set(document) - required)

    if missing:
        raise ValueError(
            "Trūksta Cabinet Parts kainodaros parametrų: "
            + ", ".join(missing)
        )

    if extra:
        raise ValueError(
            "Nežinomi Cabinet Parts kainodaros parametrai: "
            + ", ".join(extra)
        )

    values = dict(document)

    for name in required - {"output_decimals"}:
        try:
            values[name] = float(values[name])
        except (TypeError, ValueError):
            raise ValueError(f"Parametras '{name}' turi būti skaičius.")

        if values[name] < 0:
            raise ValueError(
                f"Parametras '{name}' negali būti neigiamas."
            )

    try:
        output_decimals = int(values["output_decimals"])
    except (TypeError, ValueError):
        raise ValueError("output_decimals turi būti sveikas skaičius.")

    if output_decimals < 0 or output_decimals > 8:
        raise ValueError(
            "output_decimals turi būti nuo 0 iki 8."
        )

    values["output_decimals"] = output_decimals

    return CabinetPartsPriceParameters(**values)


def load_parameters(path: Path) -> CabinetPartsPriceParameters:
    if not path.exists():
        return DEFAULT_PARAMETERS

    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)

    return validate_parameters(document)


def save_parameters(
    path: Path,
    parameters: CabinetPartsPriceParameters,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            asdict(parameters),
            handle,
            indent=2,
            ensure_ascii=False,
        )
        handle.write("\n")
