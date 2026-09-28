# Purchase input changes during Reform refresh

On 2026-09-28 the business owner approved using current Odoo purchase prices
with existing Tamara adjustment precedence. A difference from the frozen
R001/R007 baseline is informational during a full refresh, not a release error.

The refresh writes `Pricing_Input_Snapshot.json` and
`Pirkimo_kainu_pokyciai.csv`. The CSV compares effective prices with the most
recent prior calculated snapshot in the same run store, even if that prior run
was not released. It identifies that run, changed prices, added/removed inputs,
and available cost-source descriptions. R001 prices can include Reform markup;
these are effective pricing inputs, not necessarily raw supplier prices.

If no usable previous snapshot exists, the report explicitly says comparison
is unavailable; the current run becomes a reference for subsequent runs.
The historical approved-baseline hash is retained in the JSON for provenance.
Standalone strict-baseline validation remains available. Conflicting inputs,
BOM audits and existing BLOCKED-product release handling are unchanged.
