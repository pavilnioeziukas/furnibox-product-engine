"""Persistent, application-owned configuration for Reform SO pricing."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


SCHEMA_VERSION = 1
ADDON_FIELDS = ("assembly", "storage", "packaging", "put_on_pallet", "other", "markup")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Tikėtasi skaičiaus, gauta {value!r}")
    return float(value)


@dataclass(frozen=True)
class PricingRule:
    sku: str
    category_id: str
    category_name: str
    odoo_category: str
    assembly: float = 0.0
    storage: float = 0.0
    packaging: float = 0.0
    put_on_pallet: float = 0.0
    other: float = 0.0
    markup: float = 0.0

    @property
    def addons(self) -> tuple[float, float, float, float, float, float]:
        return tuple(getattr(self, field) for field in ADDON_FIELDS)


@dataclass(frozen=True)
class NonBomRule:
    sku: str
    name: str
    product_category: str
    pricing_category: str
    preparation: float = 0.0
    storage: float = 0.0
    bag: float = 0.0
    sticker: float = 0.0


def empty_config() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "adjustment_rate": -0.07,
        "pricing_rules": [],
        "bom_products": [],
        "non_bom_rules": [],
        "migration_warnings": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_config(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Nepalaikoma SO kainodaros konfigūracijos versija.")
    adjustment = document.get("adjustment_rate")
    if isinstance(adjustment, bool) or not isinstance(adjustment, (int, float)) or not -1 < adjustment <= 0:
        raise ValueError("Korekcija turi būti didesnė nei -100 % ir ne didesnė nei 0 %.")
    seen: set[str] = set()
    for raw in document.get("pricing_rules", []):
        rule = PricingRule(**raw)
        normalized = rule.sku.casefold()
        if not normalized:
            raise ValueError("Kainodaros taisyklėje trūksta SKU.")
        if normalized in seen:
            raise ValueError(f"Pasikartojanti kainodaros taisyklė: {rule.sku}")
        seen.add(normalized)
    seen.clear()
    for raw in document.get("bom_products", []):
        sku = _text(raw.get("sku"))
        if not sku:
            raise ValueError("BOM produktų sąraše trūksta SKU.")
        normalized = sku.casefold()
        if normalized in seen:
            raise ValueError(f"Pasikartojantis BOM produktas: {sku}")
        seen.add(normalized)
    seen.clear()
    for raw in document.get("non_bom_rules", []):
        rule = NonBomRule(**raw)
        normalized = rule.sku.casefold()
        if not normalized:
            raise ValueError("Ne BOM taisyklėje trūksta SKU.")
        if normalized in seen:
            raise ValueError(f"Pasikartojanti ne BOM taisyklė: {rule.sku}")
        seen.add(normalized)
    return document


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_config()
    return validate_config(json.loads(path.read_text(encoding="utf-8")))


def save_config(path: Path, document: dict[str, Any]) -> None:
    document = dict(document)
    document["updated_at"] = datetime.now(timezone.utc).isoformat()
    validate_config(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def migrate_legacy_workbook(source: Path) -> dict[str, Any]:
    """Read the legacy workbook once and return application-owned rules."""
    workbook = load_workbook(source, data_only=True, read_only=True)
    required = {"bomai", "Kainodaros kategorijos", "Ne BOM pozicijos"}
    missing = required.difference(workbook.sheetnames)
    if missing:
        workbook.close()
        raise ValueError(f"Sename faile trūksta lapų: {', '.join(sorted(missing))}")

    pricing_rules: list[dict[str, Any]] = []
    migration_warnings: list[str] = []
    seen: set[str] = set()
    for row in workbook["Kainodaros kategorijos"].iter_rows(min_row=2, values_only=True):
        sku = _text(row[0])
        if not sku:
            continue
        normalized = sku.casefold()
        values = tuple(_number(value) for value in row[4:10])
        if normalized in seen:
            migration_warnings.append(f"Pasikartojanti taisyklė {sku}: perkelta pirmoji seno Excel eilutė.")
            continue
        seen.add(normalized)
        pricing_rules.append(asdict(PricingRule(
            sku=sku,
            category_id=_text(row[1]),
            category_name=_text(row[2]),
            odoo_category=_text(row[3]),
            **dict(zip(ADDON_FIELDS, values)),
        )))

    bom_products: list[dict[str, str]] = []
    seen.clear()
    for row in workbook["bomai"].iter_rows(min_row=3, values_only=True):
        sku = _text(row[1])
        if sku and sku.casefold() not in seen:
            seen.add(sku.casefold())
            bom_products.append({"sku": sku, "product_category": _text(row[2])})

    non_bom_rules: list[dict[str, Any]] = []
    seen.clear()
    for row in workbook["Ne BOM pozicijos"].iter_rows(min_row=2, values_only=True):
        sku = _text(row[0])
        if not sku:
            continue
        normalized = sku.casefold()
        if normalized in seen:
            workbook.close()
            raise ValueError(f"Pasikartojanti ne BOM taisyklė: {sku}")
        seen.add(normalized)
        non_bom_rules.append(asdict(NonBomRule(
            sku=sku,
            name=_text(row[1]),
            product_category=_text(row[2]),
            pricing_category=_text(row[3]),
            preparation=_number(row[6]),
            storage=_number(row[7]),
            bag=_number(row[8]),
            sticker=_number(row[9]),
        )))
    workbook.close()
    document = empty_config()
    document["pricing_rules"] = pricing_rules
    document["bom_products"] = bom_products
    document["non_bom_rules"] = non_bom_rules
    document["migration_warnings"] = migration_warnings
    return validate_config(document)


def migrate_generated_audit(source: Path) -> dict[str, Any]:
    """Recover the already-verified rules from a generated pricing audit."""
    workbook = load_workbook(source, data_only=True, read_only=True)
    required = {"SO LINE PRICES", "BOM CATEGORY BREAKDOWN", "NON-BOM RULES"}
    missing = required.difference(workbook.sheetnames)
    if missing:
        workbook.close()
        raise ValueError(f"Audito faile trūksta lapų: {', '.join(sorted(missing))}")
    pricing: dict[str, dict[str, Any]] = {}
    for row in workbook["BOM CATEGORY BREAKDOWN"].iter_rows(min_row=2, values_only=True):
        sku = _text(row[2])
        if not sku:
            continue
        multiplier = _number(row[6], 1.0)
        if multiplier == 0:
            continue
        pricing.setdefault(sku.casefold(), asdict(PricingRule(
            sku, _text(row[3]), _text(row[4]), _text(row[5]),
            *(_number(value) / multiplier for value in row[7:13]),
        )))
    products: list[dict[str, str]] = []
    for row in workbook["SO LINE PRICES"].iter_rows(min_row=2, values_only=True):
        if _text(row[2]) == "BOM":
            products.append({"sku": _text(row[0]), "product_category": _text(row[3])})
    non_bom: list[dict[str, Any]] = []
    for row in workbook["NON-BOM RULES"].iter_rows(min_row=2, values_only=True):
        if _text(row[0]):
            non_bom.append(asdict(NonBomRule(
                sku=_text(row[0]), name=_text(row[1]), product_category=_text(row[2]),
                pricing_category=_text(row[3]), preparation=_number(row[5]), storage=_number(row[6]),
                bag=_number(row[7]), sticker=_number(row[8]),
            )))
    workbook.close()
    document = empty_config()
    document["pricing_rules"] = list(pricing.values())
    document["bom_products"] = products
    document["non_bom_rules"] = non_bom
    return validate_config(document)
