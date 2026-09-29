"""User-approved 2026-09-29 HB composition correction for pricing only."""
from copy import copy
from dataclasses import replace
import re

VERSION = '2026-09-29-hrd-hb-v1'
REMOVED_COMPONENTS = {'NAIL-1', 'PRIZM-1'}


def is_hb(sku):
    return bool(re.search(r'(?:^|-)HRD\d+HB(?:-A)?$', str(sku).strip(), re.I))


def excluded(parent, child):
    return is_hb(parent) and str(child).strip().upper() in REMOVED_COMPONENTS


def apply(boms, graph):
    """Return isolated pricing structures and audit; retain quantities and metadata."""
    corrected_graph = {}
    changes = []
    for parent, children in graph.items():
        corrected_graph[parent] = []
        for child, qty in children:
            if excluded(parent, child):
                changes.append(dict(bom=parent, component=child, before=qty, after=0))
            else:
                corrected_graph[parent].append((child, qty))
    corrected_boms = copy(boms)
    for parent, (category, items) in boms.items():
        corrected_boms[parent] = (category, [
            replace(item, leaves=[(sku, qty) for sku, qty in item.leaves if not excluded(item.sku, sku)])
            for item in items if not excluded(parent, item.sku)
        ])
    return corrected_boms, corrected_graph, {'version': VERSION, 'changes': changes}
