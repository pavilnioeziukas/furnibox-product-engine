# Shared calculator pricing

The SO pricing run loads one snapshot of `calculator_settings.json` from the
application shared data directory. `/calculators/settings` persists panel and
shelf rates and the final cost markup (initially 0%). The standalone calculators
start with those same rates. Their unsaved scenario inputs remain temporary.
The LED / ROD form saves historical comparison scenarios only; these never override SO pricing.
Cabinet part rates remain in the existing purchase-pricing workspace and are
consumed by the existing cabinet-part preparation step in the full pipeline.

Exact panel pack SKUs use K + W + X; their raw panel SKUs use K. Shelf wooden
parts use U and their source pack SKUs use U + R + S. LED, ROD and LEDROD use the shelf family-rate calculator: U for the detail and U + R + S for the pack. Historical C:K sums do not override this calculation. These complete
calculator recipes replace the old pack calculation, rather than adding old
category packaging fees or the -7% fee adjustment again. An enclosing product
can still have its own category-level service fees.

Historical workbook BOM rows are not substituted into Target: many repeat
components and the cached J formula ignores quantity. Their review workspace
remains available. Recipe costs are explicitly labelled CALCULATOR and their
cost terms are recorded in the component-cost audit. They are not a claim that
the historical workbook BOM is an approved manufacturing BOM.

Repeated identical recipes collapse; conflicting recipes block. Missing panel
or shelf recipes block rather than using old generic cabinet-part prices.
All Target BOM products are included in the SO output, including products
without a pricing rule. Such products remain BLOCKED with their reason.

The final markup is applied once after all component/pack costs and existing
service fees: `final = before_markup * (1 + markup_percent / 100)`. Recursive
component prices do not include this final markup. The existing Furnix transfer
markup remains a separate procurement layer. Reruns reconstruct base costs
instead of multiplying prior selling prices.

SO LINE PRICES and PRICE RESULTS include before-markup amount, final markup
percent and amount. The settings snapshot is written next to the output as
Calculator_Settings.json. No Odoo or Target release mutation occurs.
