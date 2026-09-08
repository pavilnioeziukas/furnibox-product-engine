"""Apply Tamara's explicit component destinations without changing quantities."""
import json
import re
from collections import defaultdict
from pathlib import Path


def apply_allocation(products):
    from apply_apack_hrd_transfer import component_map, write_components
    rules = json.loads((Path(__file__).parent / 'manifest/apack_hrd_allocation_rules.json').read_text(encoding='utf-8'))
    before = {sku: component_map(p) for sku, p in products.items()}
    proposals = defaultdict(dict)
    pairs = []
    for sku, p in products.items():
        children = before[sku]
        aps = [c for c in children if c.startswith('APACK-')]
        hrs = [c for c in children if 'HRD' in c and c.endswith('-A')]
        if not aps:
            continue
        match = re.search(r'CAB\d+-([A-Z]{3})\d+', sku)
        group = match[1] if match else ''
        if group not in rules:
            continue
        if len(aps) != 1 or len(hrs) != 1 or len(children) != 2:
            raise ValueError(f'{sku}: ambiguous APACK / HRD-A pair')
        a, h = aps[0], hrs[0]
        if a not in before or h not in before:
            raise ValueError(f'{sku}: missing APACK / HRD-A BOM')
        if children[a] != 1 or children[h] != 1:
            raise ValueError(f'{sku}: allocation requires unit BOM quantities')
        pairs.append((sku, a, h, group))
        for destination, components in rules[group].items():
            for c in components:
                total = before[a].get(c, 0) + before[h].get(c, 0)
                if not total:
                    continue
                for target, qty in ((a, total if destination == 'APACK' else 0), (h, total if destination == 'HRD-A' else 0)):
                    previous = proposals[target].get(c)
                    if previous is not None and abs(previous - qty) > 1e-9:
                        raise ValueError(f'{target}: conflicting allocation for shared component {c}')
                    proposals[target][c] = qty
    after = {sku: dict(rows) for sku, rows in before.items()}
    audit = []
    for sku, components in proposals.items():
        for c, qty in components.items():
            old = after[sku].get(c, 0)
            if abs(old - qty) <= 1e-9:
                continue
            if qty:
                after[sku][c] = qty
            else:
                after[sku].pop(c, None)
            audit.append({'bom': sku, 'component': c, 'before': old, 'after': qty})
    # Check every consumer, including families outside the explicit matrix.
    changed = {r['bom'] for r in audit}
    for parent, children in before.items():
        if not changed.intersection(children):
            continue
        old, new = defaultdict(float), defaultdict(float)
        for child, qty in children.items():
            for c, q in before.get(child, {child: 1}).items(): old[c] += qty*q
            for c, q in after.get(child, {child: 1}).items(): new[c] += qty*q
        if any(abs(old[c]-new[c]) > 1e-9 for c in old.keys() | new.keys()):
            raise ValueError(f'{parent}: allocation would change component quantities')
    for sku in changed:
        write_components(products[sku], after[sku])
    return changed, {'version': 'tamara-2026-09-08', 'checked_pairs': len(pairs), 'changes': audit}
