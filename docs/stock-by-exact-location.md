# SKU stock by exact location — issue #35

Scope: a separate read-only report and web action for odoo.furnibox.lt. The existing WH/C report is unchanged.

Acceptance: one row per product and exact internal location with its complete path, on-hand, reserved and available quantity. All internal locations with nonzero on-hand or reserved totals are included. The existing active stockable product filter and purchase metadata remain. Lot/package/owner quants aggregate only within the same product/location. Global incoming PO quantities appear once per SKU in a separate summary sheet.

Run: `python -m run_stock_by_exact_location --output-dir output`
Web action: `stock_by_exact_location` / Generuoti SKU likučius kiekvienoje lokacijoje.

Validation: `python -m pytest test_stock_by_exact_location.py test_stock_by_location.py -q` — 8 passed. Syntax compilation passed. Tested parent/child separation, multiple quants, negative balances, reserved-only quantities, excluded products, duplicate SKU codes, missing location paths, empty export headers, summary totals and web action output isolation.

Diff review: only the new report, tests, this record and one new built-in web action. Odoo methods are search/read only; no business data mutation.
Adversarial review: duplicate SKU codes must not merge distinct product/location rows; covered. Incoming PO totals must not multiply by number of locations; covered. Concurrent jobs must not collect each other's report files; new action writes only its job output directory and disables global output collection.

Deployment and Production verification: NOT VERIFIED. Railway hostname could not be resolved from the execution environment and browser inspection was unavailable. Do not mark DONE until deployment and a real read-only report are checked.

Production acceptance after deployment: run the new action; compare at least one SKU held in multiple exact locations against Odoo quants; confirm parent and child locations are separate, reservations match, available = on-hand - reserved, summary totals reconcile, and existing WH/C action still works.
