from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_DOCUMENT = {
    "adjustments": {},
}


def normalize_sku(value: Any) -> str:
    return str(value or "").strip()


def validate_adjustment(sku: str, document: dict[str, Any]) -> dict[str, Any]:
    sku = normalize_sku(sku)
    if not sku:
        raise ValueError("Internal Reference negali būti tuščias.")

    raw_price = document.get("adjusted_purchase_price")
    if raw_price in (None, ""):
        raise ValueError(
            f"SKU {sku}: Adjusted Purchase Price negali būti tuščia."
        )

    try:
        adjusted_purchase_price = float(str(raw_price).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"SKU {sku}: Adjusted Purchase Price nėra skaičius."
        ) from exc

    if adjusted_purchase_price < 0:
        raise ValueError(
            f"SKU {sku}: Adjusted Purchase Price negali būti neigiama."
        )

    return {
        "adjusted_purchase_price": adjusted_purchase_price,
        "comment": str(document.get("comment") or "").strip(),
    }


def load_adjustments(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Neteisingas Tamaros korekcijų JSON failas: {path}"
        ) from exc

    raw_adjustments = document.get("adjustments", {})
    if not isinstance(raw_adjustments, dict):
        raise ValueError(
            "Tamaros korekcijų faile 'adjustments' turi būti objektas."
        )

    result: dict[str, dict[str, Any]] = {}

    for raw_sku, raw_document in raw_adjustments.items():
        sku = normalize_sku(raw_sku)

        if not isinstance(raw_document, dict):
            raise ValueError(
                f"SKU {sku}: korekcijos įrašas turi būti objektas."
            )

        if sku in result:
            raise ValueError(f"Pirkimo kain? korekcijose kartojasi SKU: {sku}")

        result[sku] = validate_adjustment(sku, raw_document)

    return result


def save_adjustments(
    path: Path,
    adjustments: dict[str, dict[str, Any]],
) -> None:
    validated: dict[str, dict[str, Any]] = {}

    for raw_sku, document in adjustments.items():
        sku = normalize_sku(raw_sku)

        if sku in validated:
            raise ValueError(f"Pirkimo kain? korekcijose kartojasi SKU: {sku}")

        validated[sku] = validate_adjustment(sku, document)

    payload = {
        "adjustments": dict(
            sorted(validated.items(), key=lambda item: item[0].casefold())
        )
    }

    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)