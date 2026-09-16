"""Tamara-confirmed purchased Furnibox products that must never use a BOM."""
from __future__ import annotations

CONFIRMED_PURCHASED_NON_BOM_SKUS = (
    "EUB-P-ACC01-HRD050", "EUB-P-ACC01-HRD050-A", "EUB-P-ACC01-HRD051", "EUB-P-ACC01-HRD051-A",
    "EUB-P-ACC01-HRD300", "EUB-P-ACC01-HRD300-A", "EUB-P-ACC02-MIS020", "EUB-P-ACC02-MIS021",
    "EUB-P-ACC02-MIS022", "EUB-P-ACC02-MIS023", "EUB-P-ACC02-MIS030", "EUB-P-ACC02-MIS031",
    "EUB-P-ACC02-MIS032", "EUB-P-ACC02-MIS800", "EUB-P-ACC02-MIS801", "EUB-P-ACC02-MIS802",
    "EUB-P-ACC02-MIS803", "EUB-P-ACC02-MIS804", "EUB-P-ACC02-MIS805", "EUB-P-ACC02-MIS806",
    "EUB-P-ACC02-MIS807", "EUB-P-ACC02-MIS830", "EUB-P-ACC02-MIS831", "EUB-P-ACC02-MIS832",
    "EUB-P-ACC02-MIS900", "EUB-P-ACC02-MIS901", "EUB-P-ACC02-MIS902", "EUB-P-ACC02-MIS903",
    "EUB-P-ACC02-MIS904", "EUB-P-ACC02-MIS905", "EUB-P-ACC02-MIS906", "EUB-P-ACC02-MIS907",
    "EUB-P-ACC02-SLF200", "EUB-P-ACC02-SLF201", "EUB-P-ACC02-SLF202", "EUB-P-ACC02-SLF203",
    "EUB-P-ACC02-SLF204", "EUB-P-ACC02-SLF205", "EUB-P-ACC02-SLF206", "EUB-P-ACC02-SLF207",
    "EUB-P-ACC02-SLF208", "EUB-P-ACC05-MIS001", "EUB-P-ACC05-MIS002", "EUB-P-ACC05-MIS003",
    "EUB-P-ACC05-MIS004", "UNI-P-ACC02-MIS015", "UNI-P-ACC02-MIS016", "UNI-P-ACC02-MIS017",
    "UNI-P-ACC02-MIS050", "UNI-P-ACC02-MIS051", "UNI-P-ACC02-MIS820", "UNI-P-ACC02-MIS950",
    "UNI-P-ACC02-MIS951", "UNI-P-ACC02-MIS952", "UNI-P-ACC03-MIS015", "USB-P-ACC01-HRD050", "USB-P-ACC01-HRD051",
    "USB-P-ACC01-HRD052", "USB-P-ACC01-HRD053", "USB-P-ACC01-HRD301", "USB-P-ACC02-MIS830",
    "USB-P-ACC02-MIS831", "USB-P-ACC02-MIS832", "USB-P-ACC02-SLF200", "USB-P-ACC02-SLF201",
    "USB-P-ACC02-SLF202", "USB-P-ACC02-SLF203", "USB-P-ACC02-SLF204", "USB-P-ACC02-SLF205",
    "USB-P-ACC02-SLF206", "USB-P-ACC02-SLF207", "USB-P-ACC02-SLF208",
)

APPROVED_SUPPLIER_ALIASES = {
    "EUB-P-ACC02-SLF201": "UTH1011", "UNI-P-ACC02-MIS950": "F0288000002",
    "UNI-P-ACC02-MIS952": "F0288000001", "UNI-P-ACC02-MIS017": "91970369",
}

CONFIRMED_PURCHASED_NON_BOM_KEYS = frozenset(sku.casefold() for sku in CONFIRMED_PURCHASED_NON_BOM_SKUS)
if len(CONFIRMED_PURCHASED_NON_BOM_SKUS) != 72 or len(CONFIRMED_PURCHASED_NON_BOM_KEYS) != 72:
    raise RuntimeError("Confirmed purchased product registry must contain 72 unique SKUs.")
if not set(APPROVED_SUPPLIER_ALIASES).issubset(CONFIRMED_PURCHASED_NON_BOM_SKUS):
    raise RuntimeError("Every approved supplier alias must belong to the purchased SKU registry.")


def is_confirmed_purchased(sku) -> bool:
    return str(sku or "").strip().casefold() in CONFIRMED_PURCHASED_NON_BOM_KEYS


def remove_confirmed_purchased_boms(boms, graph):
    """Remove current or cached BOMs while retaining the original containers."""
    removed = set()
    for mapping in (graph, boms):
        for sku in list(mapping):
            if is_confirmed_purchased(sku):
                removed.add(str(sku).strip().casefold())
                del mapping[sku]
    empty_issues = getattr(boms, "empty_bom_issues", None)
    if empty_issues is not None:
        for sku in list(empty_issues):
            if is_confirmed_purchased(sku):
                del empty_issues[sku]
    return removed


def purchased_price(prices, sku):
    """Resolve one price, never summing Furnibox and supplier identities."""
    sku_key = str(sku).strip().casefold()
    direct = prices.get(sku_key)
    if direct is not None and float(direct[1]) > 0:
        return direct, sku_key
    supplier = APPROVED_SUPPLIER_ALIASES.get(str(sku).strip().upper())
    supplier_key = supplier.casefold() if supplier else ""
    alias = prices.get(supplier_key) if supplier_key else None
    if alias is not None and float(alias[1]) > 0:
        return alias, supplier_key
    return None, ""
