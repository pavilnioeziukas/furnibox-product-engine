# Reviewed pricing corrections, 2026-09-09

The user supplied `Reform_SO_Line_Prices_COMPLETE_ONLY (16) (1).xlsx` and explicitly
instructed that red Name cells replace product names, red Issues / Review Reason
cells specify category expressions, and red final prices mark incorrect results
to recalculate rather than manual price overrides. The manifest records the
source SHA256 and exact cell coordinates for 22 products.

Sixteen ventilation products use category 7, two brackets use 9+30+33+34, and
HRDW-ACC01-MIS101 uses 9+34. UNI-P-ACC02-MIS952 explicitly becomes NON-BOM with
existing non-BOM category 6 (preparation 1, storage 4, bag .02, sticker .02).
Names are supplied for 21 rows; two rows change only their names. Three red
Product Category values are retained as pricing-report metadata, without an
Odoo product write. Red CATEGORY RULES A59:B59 identifies category 7; no tariff
amounts are red, so central category 7 rates remain authoritative.

Configuration migration applies each SKU once and records the review version.
Generated A variants are included after dataset discovery. Reviewed BOM categories
retain business expressions and refresh amounts from central tariffs. Their
product expressions suppress repeated child product/packaging add-ons, but
separately assigned Components tariffs are included (user correction 2026-09-10).
The later corrected C1-C12 table supersedes the original component rates.
C7 is LED HARDWARE, C10 is SHELF HARDWARE, C8 totals .08 EUR as explicitly
confirmed. All component rates multiply by the component quantity, including
direct items (four screws at .01 contribute .04 EUR). EU-VENRAIL-561-BB now
contributes storage .15, packaging .05 and pallet .02 EUR per unit
before the BOM adjustment, in addition to its parent's product tariffs.
Existing calculator and internal manufacturing cost protections still apply.
Reviewed NON-BOM products
lose their outgoing costing edges, keep incoming parent references, and require
their own positive prepared purchase price. Metadata is applied before exports,
so SO LINE PRICES and derived PRICE RESULTS agree. Successful calculation saves
the configuration used; subsequent manual edits are not replayed over by the
same migration.

The supplied workbook and Odoo records are not modified. The normal application
run produces the new workbook, trace and search index from these corrections.
