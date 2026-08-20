from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import isclose
from typing import Any

from .models import BomStatus, ProductStatus, Reconciliation, Result


def canon(value: Any) -> str:
    return str(value or "").strip().upper()


def _ids(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = value.split(",")
    else:
        values = value or []
    return tuple(sorted(canon(x) for x in values if canon(x)))


def _components(rows: list[dict[str, Any]]) -> tuple[dict[str, float], tuple[str, ...]]:
    totals: defaultdict[str, float] = defaultdict(float)
    invalid = []
    for row in rows or []:
        sku = canon(row.get("sku") or row.get("component_sku"))
        try:
            qty = float(row.get("quantity", row.get("product_qty", 0)))
        except (TypeError, ValueError):
            qty = 0
        if not sku or qty <= 0:
            invalid.append(sku or "<EMPTY SKU>")
        else:
            totals[sku] += qty
    return dict(totals), tuple(invalid)


def _operations(rows: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    result = []
    for row in rows or []:
        result.append((
            int(row.get("sequence") or 0),
            canon(row.get("name")),
            canon(row.get("workcenter") or row.get("workcenter_name")),
            canon(row.get("time_mode")),
            round(float(row.get("time_minutes", row.get("time", 0)) or 0), 6),
        ))
    return tuple(sorted(result))


def _expected_profile(catalog: dict[str, Any], bom: dict[str, Any] | None) -> dict[str, Any]:
    profile = dict(catalog.get("import_profile") or catalog.get("expected") or {})
    # Dataset producers may store import column names; normalize them here.
    aliases = {
        "categ_id": "category_external_id",
        "route_ids/id": "route_external_ids",
        "type": "product_type_field",
        "invoice_policy": "invoice_policy",
        "variant_seller_ids/partner_id/id": "vendor_external_id",
    }
    for source, target in aliases.items():
        if source in profile and target not in profile:
            profile[target] = profile[source]
    if bom and "bom_type" not in profile:
        profile["bom_type"] = bom.get("bom_type")
    role = canon(catalog.get("role"))
    expected_name = (
        catalog.get("sku")
        if role == "NON-BOM COMPONENT"
        else catalog.get("name_1") or catalog.get("name_2") or catalog.get("sku")
    )
    profile.setdefault("name", str(expected_name or "").strip())
    return profile


def _profile_group(catalog: dict[str, Any], bom: dict[str, Any] | None) -> tuple[str, ...]:
    """Same business groups used by the existing product-import inference."""
    role = canon(catalog.get("role"))
    if role == "NON-BOM COMPONENT":
        return ("COMPONENT", canon(catalog.get("part_group") or "BLANK"))
    return (
        "BOM" if bom else "PRODUCT",
        canon(catalog.get("product_type")),
        canon((bom or {}).get("bom_type")),
        role,
    )


def _infer_profiles(catalog_rows: list[dict[str, Any]], target_boms: dict[str, dict[str, Any]],
                    matches: dict[str, list[dict[str, Any]]]) -> None:
    votes: defaultdict[tuple[str, ...], Counter[tuple[Any, ...]]] = defaultdict(Counter)
    for row in catalog_rows:
        sku = canon(row.get("sku"))
        current = matches.get(sku, [])
        if len(current) != 1:
            continue
        value = current[0]
        signature = (
            value.get("category_external_id") or "",
            _ids(value.get("route_external_ids")),
            value.get("product_type_field") or "",
            value.get("invoice_policy") or "",
            value.get("vendor_external_id") or "",
        )
        if all(signature[:4]):
            votes[_profile_group(row, target_boms.get(sku))][signature] += 1
    for row in catalog_rows:
        if row.get("import_profile") or row.get("expected"):
            continue
        ranked = votes[_profile_group(row, target_boms.get(canon(row.get("sku"))))].most_common()
        if not ranked or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
            continue
        signature, evidence = ranked[0]
        row["expected"] = {
            "category_external_id": signature[0],
            "route_external_ids": signature[1],
            "product_type_field": signature[2],
            "invoice_policy": signature[3],
            "vendor_external_id": signature[4],
            "inferred_from_production_count": evidence,
        }


def _product_result(catalog: dict[str, Any], bom: dict[str, Any] | None,
                    matches: list[dict[str, Any]]) -> Result:
    sku = canon(catalog.get("sku"))
    if not sku:
        return Result("", ProductStatus.BLOCKED, blocking_reasons=("Target kataloge tuščias SKU.",))
    if len(matches) > 1:
        return Result(sku, ProductStatus.BLOCKED, blocking_reasons=(
            "Production rasti keli produktai su tuo pačiu SKU.",
        ))
    profile = _expected_profile(catalog, bom)
    required = ("name", "category_external_id", "route_external_ids", "product_type_field", "invoice_policy")
    missing = tuple(name for name in required if not profile.get(name))
    if missing:
        return Result(sku, ProductStatus.BLOCKED, blocking_reasons=(
            "Nenustatytas vienareikšmis Production etalonas laukams: " + ", ".join(missing),
        ))
    if not matches:
        return Result(sku, ProductStatus.CREATE)

    current = matches[0]
    changes: list[dict[str, Any]] = []
    if not str(current.get("name") or "").strip():
        changes.append({"field": "name", "target": profile["name"], "production": ""})
    if not bool(current.get("active", True)):
        changes.append({"field": "active", "target": True, "production": False})
    checks = (
        ("category_external_id", "category_external_id", False),
        ("route_external_ids", "route_external_ids", True),
        ("product_type_field", "product_type_field", False),
        ("invoice_policy", "invoice_policy", False),
        ("vendor_external_id", "vendor_external_id", False),
    )
    for target_key, current_key, many in checks:
        expected = profile.get(target_key)
        if expected in (None, "", []):
            continue
        actual = current.get(current_key)
        equal = _ids(expected) == _ids(actual) if many else canon(expected) == canon(actual)
        if not equal:
            changes.append({"field": target_key, "target": expected, "production": actual})
    if not current.get("external_id"):
        changes.append({"field": "external_id", "target": "REQUIRED", "production": ""})
    return Result(sku, ProductStatus.UPDATE if changes else ProductStatus.UNCHANGED,
                  changes=tuple(changes))


def _bom_result(target: dict[str, Any], matches: list[dict[str, Any]],
                product_counts: Counter[str], target_product_skus: set[str]) -> Result:
    sku = canon(target.get("sku"))
    wanted, invalid = _components(target.get("components") or [])
    reasons = []
    warnings = []
    evidence = []
    if invalid:
        reasons.append("Target BOM turi netinkamų komponentų eilučių.")
    planned = sorted(
        component for component in wanted
        if product_counts[component] == 0 and component in target_product_skus
    )
    missing = sorted(
        component for component in wanted
        if product_counts[component] != 1 and component not in planned
    )
    if planned:
        warnings.append(
            "Komponentai bus sukurti pagal to paties Target reconciliation planą: "
            + ", ".join(planned)
        )
    if missing:
        reasons.append("Production trūksta arba dubliuoti komponentų SKU: " + ", ".join(missing))
    if len(matches) > 1:
        reasons.append("Production rasti keli aktyvūs Sequence 0 BOM.")
        evidence.append({
            "diagnostic": "MULTIPLE ACTIVE SEQUENCE 0 BOM",
            "production_bom_ids": sorted(
                int(row["id"]) for row in matches if row.get("id") is not None
            ),
        })
    if reasons:
        return Result(
            sku, BomStatus.BLOCKED, changes=tuple(evidence),
            blocking_reasons=tuple(reasons), warnings=tuple(warnings),
        )
    if not matches:
        return Result(sku, BomStatus.CREATE, warnings=tuple(warnings))

    current = matches[0]
    have, have_invalid = _components(current.get("components") or [])
    if have_invalid:
        return Result(sku, BomStatus.BLOCKED, blocking_reasons=(
            "Production BOM turi neišsprendžiamų komponentų eilučių.",
        ))
    changes = []
    for component in sorted(wanted.keys() - have.keys()):
        changes.append({"action": BomStatus.ADD_COMPONENT, "component_sku": component,
                        "target_quantity": wanted[component]})
    for component in sorted(have.keys() - wanted.keys()):
        changes.append({"action": BomStatus.REMOVE_COMPONENT, "component_sku": component,
                        "production_quantity": have[component]})
    for component in sorted(wanted.keys() & have.keys()):
        if not isclose(wanted[component], have[component], rel_tol=1e-9, abs_tol=1e-9):
            changes.append({"action": BomStatus.CHANGE_QUANTITY, "component_sku": component,
                            "target_quantity": wanted[component], "production_quantity": have[component]})
    target_type = canon(target.get("bom_type"))
    current_type = canon(current.get("bom_type"))
    normalized = {"NORMAL": "MANUFACTURE", "PHANTOM": "KIT"}
    if normalized.get(target_type, target_type) != normalized.get(current_type, current_type):
        changes.append({"action": BomStatus.CHANGE_TYPE, "target": target_type,
                        "production": current_type})
    if _operations(target.get("operations") or []) != _operations(current.get("operations") or []):
        changes.append({"action": BomStatus.UPDATE_OPERATIONS,
                        "target": list(_operations(target.get("operations") or [])),
                        "production": list(_operations(current.get("operations") or []))})
    if not changes:
        return Result(sku, BomStatus.UNCHANGED, warnings=tuple(warnings))
    precedence = (BomStatus.CHANGE_TYPE, BomStatus.UPDATE_OPERATIONS, BomStatus.CHANGE_QUANTITY,
                  BomStatus.REMOVE_COMPONENT, BomStatus.ADD_COMPONENT)
    actions = {change["action"] for change in changes}
    status = next(value for value in precedence if value in actions)
    return Result(sku, status, changes=tuple(changes), warnings=tuple(warnings))


def reconcile(dataset: dict[str, Any], production: dict[str, Any]) -> Reconciliation:
    raw_catalog_rows = dataset.get("product_catalog")
    if not isinstance(raw_catalog_rows, list):
        raise ValueError("Target Dataset neturi pilno product_catalog sąrašo.")
    # Profile inference is report-local and must never alter the source Dataset.
    catalog_rows = [dict(row) for row in raw_catalog_rows]
    target_boms = {canon(row.get("sku")): row for row in dataset.get("products") or []}
    catalog_skus = [canon(row.get("sku")) for row in catalog_rows]
    target_product_skus = {sku for sku in catalog_skus if sku}
    duplicates = sorted(sku for sku, count in Counter(catalog_skus).items() if sku and count > 1)
    if duplicates:
        raise ValueError("Target product_catalog turi dubliuotų SKU: " + ", ".join(duplicates))

    product_matches: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in production.get("products") or []:
        if canon(row.get("sku")):
            product_matches[canon(row.get("sku"))].append(row)
    _infer_profiles(catalog_rows, target_boms, product_matches)
    product_counts = Counter({sku: len(rows) for sku, rows in product_matches.items()})
    bom_matches: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in production.get("boms") or []:
        if bool(row.get("active", True)) and int(row.get("sequence") or 0) == 0:
            bom_matches[canon(row.get("sku"))].append(row)

    products = tuple(sorted(
        (_product_result(row, target_boms.get(canon(row.get("sku"))),
                         product_matches[canon(row.get("sku"))]) for row in catalog_rows),
        key=lambda value: value.sku,
    ))
    boms = tuple(sorted(
        (
            _bom_result(row, bom_matches[sku], product_counts, target_product_skus)
            for sku, row in target_boms.items()
        ),
        key=lambda value: value.sku,
    ))
    return Reconciliation(
        dataset_id=str(dataset.get("dataset_id") or ""),
        environment=str(production.get("environment") or "production"),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        products=products,
        boms=boms,
    )
