"""Explicit read-only Production BOM supplementation for pricing, not releases."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook


def supplement_pricing_graph(graph, pricing_skus, scope_path: Path, map_path: Path):
    """Return a copy with selected missing BOMs; never replace Target nodes.

    The opt-in scope contains SKU identifiers only. Actual quantities always
    come from the freshly supplied read-only Odoo MAP. Unknown roots, conflicting
    BOM selections, invalid quantities and cycles fail before calculation.
    """
    key = lambda value: str(value or "").strip().casefold()
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    if scope.get("purpose") != "pricing_only" or scope.get("schema_version") != 1:
        raise ValueError("Production BOM scope must be schema 1, purpose pricing_only.")
    skus = scope.get("skus")
    if not isinstance(skus, list) or not skus or any(not isinstance(s, str) or not key(s) for s in skus):
        raise ValueError("Production BOM scope requires non-empty SKU strings.")
    selected = {key(s) for s in skus}
    if len(selected) != len(skus):
        raise ValueError("Production BOM scope has duplicate SKU identifiers.")
    unknown = selected - {key(s) for s in pricing_skus}
    if unknown:
        raise ValueError("Scope contains unconfigured pricing SKU: " + ", ".join(sorted(unknown)))
    if map_path is None:
        raise ValueError("Production BOM scope requires a read-only Odoo MAP.")
    workbook = load_workbook(map_path, read_only=True, data_only=True)
    try:
        rows = iter(workbook["ODOO EDGES"].values)
        headers = next(rows)
        required = {"Parent SKU", "Component SKU", "Quantity", "BOM ID"}
        if not required.issubset(headers):
            raise ValueError("Odoo MAP is missing BOM edge columns.")
        production = defaultdict(list)
        for row in rows:
            edge = dict(zip(headers, row))
            production[key(edge["Parent SKU"])].append(edge)
    finally:
        workbook.close()

    result = {key(s): list(children) for s, children in graph.items()}
    visiting, completed, added = set(), set(), set()

    def visit(sku):
        sku = key(sku)
        if sku in visiting:
            raise ValueError("Cycle in supplemental pricing BOM: " + sku)
        if sku in completed:
            return
        visiting.add(sku)
        if sku not in result:
            edges = production.get(sku, [])
            if not edges:
                if sku in selected:
                    raise ValueError("Selected Production BOM is missing: " + sku)
                visiting.remove(sku)
                completed.add(sku)
                return
            bom_ids = {edge["BOM ID"] for edge in edges}
            if len(bom_ids) != 1 or None in bom_ids:
                raise ValueError("Ambiguous Production BOM selection: " + sku)
            children, seen = [], set()
            for edge in edges:
                child, qty = edge["Component SKU"], edge["Quantity"]
                if not key(child) or isinstance(qty, bool) or not isinstance(qty, (int, float)) or not math.isfinite(qty) or qty <= 0:
                    raise ValueError("Invalid Production BOM component or quantity: " + sku)
                if key(child) in seen:
                    raise ValueError("Duplicate Production BOM component: " + sku)
                seen.add(key(child))
                children.append((str(child).strip(), float(qty)))
            result[sku] = children
            added.add(sku)
        for child, _qty in result[sku]:
            visit(child)
        visiting.remove(sku)
        completed.add(sku)

    for sku in sorted(selected):
        visit(sku)
    return result, added
