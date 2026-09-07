# Explicit Production BOM pricing scope

Some configured sales-pricing SKUs are absent from the current Reform input and
its Target Dataset but still have active Production Odoo BOMs. They must not be
silently injected into the authoritative release Dataset.

The optional `--production-bom-scope` argument to `refresh_reform_pricing.py`
and `reform_so_line_prices.py` supplements the in-memory pricing graph only.
Without this argument the existing fail-closed behavior is unchanged.

Scope format:

```json
{
  "schema_version": 1,
  "purpose": "pricing_only",
  "skus": ["EXPLICITLY-REVIEWED-SALES-SKU"]
}
```

Use only after a business owner confirms the selected SKUs belong in the pricing
scope. Quantities are read from the supplied Odoo MAP, never from the scope file.
The roots must already be configured pricing products. Target BOM nodes take
precedence. Unknown roots, missing selected BOMs, conflicting BOM IDs, repeated
components, non-positive/non-finite quantities and reachable cycles are rejected.
Neither Odoo nor the Target Dataset file is written. Full refresh records the
scope snapshot in `Production_Pricing_Scope.json` and in the result JSON.

The panel-pricing change separately includes `PANEL PART` / `PANEL PARTS` in the
category selection. Shelf prepack SKUs ending in `-PP` remain in the recursive BOM
pricing path. Target catalog products with BOMs are not treated as dimensional
leaves. Existing dimensions, material rates, surcharges and transfer markup are
unchanged. Unsupported material codes still produce diagnostics.

## Validation against 2026-09-07 snapshots

Base commit: `19b03e90fc62871956898b7cb2bd57ddfd117e51`.
Source pricing job: `2533719d3a18`; read-only Odoo MAP job: `a3a5eb578167`.
Input SHA-256: `2c778771e28dd831f38bf7eeb187b5589b795e88fdcee5929685ca0c99b605aa`.

- Baseline: all 4,018 complete BOM prices reproduced exactly (tolerance 1e-7),
  and all 127 blocked BOM identifiers matched. A further 70 complete and two
  blocked NONBOM positions are unchanged.
- Local opt-in trial: 110 additional BOMs complete after pricing the 82 PNL/PCL
  leaf parts with the existing parameters. No prior complete BOM price changed.
- Conditional total: 4,198 complete / 19 blocked, **not a Production job result**.
- All 54 expected SREW parts remain selected. The 204 SHELF-PP products no longer
  enter dimensional-part selection.
- 65 relevant unit/integration tests passed, covering pricing, refresh forwarding
  and scope provenance, panel categories, Target precedence, bad data and cycles.

The live Odoo category assignment for every one of the 82 trial panel SKUs was
not individually re-read in this offline trial; the trial uses the reviewed
PNL/PCL identifiers and frozen source snapshots. A fresh full Production run
after deployment and scope confirmation is required to confirm end-to-end coverage.

The 110 roots are 81 PNL/PCL kits, 16 transport BOMs, 12 HRD BOMs and one MIS BOM.
All 110 and all 82 panels are absent from the current Reform source. The business
owner approved all 110 roots for additional pricing on 2026-09-07. The approved
list is versioned in `manifest/production_pricing_scope.json`; the web application's
full refresh action passes that file explicitly. This approval does not authorize
writing Odoo or adding these BOMs to the release Target Dataset.
