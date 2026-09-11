"""User-approved SO unit prices, applied after all calculation and markup."""
PRICES = {'022': 3.3874, '023': 3.1474, '024': 4.6004,
          '025': 4.2404, '035': 3.5874, '036': 4.4674}
SOURCE = '2026-09-11: patvirtinta kojų komplekto galutinės kainos išimtis (su ir be -A)'


def apply(rows):
    prices = {('UNI-P-ACC01-HRD' + code + suffix).casefold(): price
              for code, price in PRICES.items() for suffix in ('', '-A')}
    for row in rows:
        price = prices.get(row['sku'].casefold())
        # Do not hide unresolved BOM or missing purchase prices.
        if price is None or row['final'] is None or row['status'] == 'BLOCKED':
            continue
        original = row.get('before_exception', row['final'])
        row.update(before_exception=original, price_exception=price-original,
                   price_exception_source=SOURCE, final=price)
