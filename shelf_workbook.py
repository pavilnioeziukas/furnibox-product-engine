"""Traceable cross-sheet cost views for the complete supplied shelf workbook."""
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

LED_LABELS = ['Lentynos gamyba','Profilio / LED montavimas','Pakuotė','LED profilis',
              'LED sandėliavimas','Lipdukas ir klijavimas','Aliuminio profilis su išeiga',
              'Pripjovimas / montavimas','Profilio sandėliavimas']


@lru_cache(maxsize=1)
def load():
    return json.loads((Path(__file__).parent/'manifest/shelf_workbook.json').read_text(encoding='utf8'))


def numeric(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def purchase_index(data):
    result=defaultdict(list)
    for row in data['purchase']:result[row['sku']].append(row)
    return result


def resolve_price(matches):
    if not matches:return None,'Nėra pirkimo kainų lape'
    values=[r['reform'] for r in matches]
    if not all(numeric(x) for x in values):return None,'Trūksta Reform kainos arba šaltinio klaida'
    if len(set(values))>1:return None,'Skirtingos to paties kodo Reform kainos'
    return values[0], 'Pasikartojanti vienoda kaina' if len(values)>1 else ''


def bom_results(data=None):
    data=data or load();prices=purchase_index(data);groups={}
    for row in data['bom']:
        group=groups.setdefault(row['parent'],{'sku':row['parent'],'bom_id':row['bom_id'],'lines':[], 'issues':[]})
        price,issue=resolve_price(prices.get(row['sku'],[]))
        line=dict(row,unit=price,price_rows=[r['row']for r in prices.get(row['sku'],[])],issue=issue)
        line['cost']=row['qty']*price if numeric(row['qty'])and row['qty']>=0 and price is not None else None
        if line['cost'] is None:group['issues'].append(f"{row['sku']}: {issue or 'Netinkamas kiekis'}")
        if numeric(price) and numeric(row['source_unit']) and abs(price-row['source_unit'])>1e-8:
            group['issues'].append(f"{row['sku']}: išsaugota BOM vieneto kaina nesutampa su Purchase Price H")
        if row['category']=='All / SHELF PART' and row['qty']!=1:
            group['issues'].append(f"{row['sku']}: medinės dalies kiekis {row['qty']} – patikrinti")
        group['lines'].append(line)
    for g in groups.values():
        seen=set()
        repeated=set()
        for line in g['lines']:
            if line['sku'] in seen:repeated.add(line['sku'])
            seen.add(line['sku'])
        if repeated:
            g['issues'].append('Šaltinyje kartojasi komponentų kodai: '+', '.join(sorted(repeated))+'. Suma apima visas eilutes; patikrinkite, ar tai nėra alternatyvios sudėtys.')
        g['total']=sum(r['cost']for r in g['lines'])if all(r['cost']is not None for r in g['lines'])else None
        g['unweighted']=sum(r['unit']for r in g['lines'])if all(r['unit']is not None for r in g['lines'])else None
        g['difference']=g['total']-g['unweighted'] if g['total']is not None else None
        headers=[r['source_sum'] for r in g['lines']if r['is_header']]
        g['source_total']=headers[0]if headers else None
    return list(groups.values())


def legacy_results(data=None):
    data=data or load();result=[]
    for group in data['legacy']:
        lines=group['components']
        total=sum(r['line_cost']for r in lines)if lines and all(numeric(r['line_cost'])for r in lines)else None
        result.append(dict(group,calculated=total,difference=total-group['total']if total is not None and numeric(group['total'])else None))
    return result


def led_results(data=None):
    data=data or load();rows=[]
    for r in data['led']:
        # Empty source cost cells represent omitted LED operations on ROD-only rows.
        total=sum(v for v in r['costs']if numeric(v))
        rows.append(dict(r,total=total,parts=list(zip(LED_LABELS,r['costs'])),difference=total-r['source_total']))
    return rows


def evidence(sku):
    data=load()
    return {
        'purchase':[r for r in data['purchase']if r['sku']==sku],
        'led':[r for r in led_results(data)if r['sku']==sku or r['plain_sku']==sku],
        'legacy':[r for r in legacy_results(data)if r['sku']==sku or any(c['sku']==sku for c in r['components'])],
        'bom':[r for r in bom_results(data)if r['sku']==sku or any(c['sku']==sku for c in r['lines'])],
    }
