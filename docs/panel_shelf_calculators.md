# Panel and shelf review calculators

Authenticated routes `/calculators/panel` and `/calculators/shelf` provide independent, request-scoped calculations and CSV export. They do not modify Odoo, Target, purchase adjustments or the SO pricing pipeline. Changing a selected row affects its detail result; the catalogue export uses source rows and the submitted common rates. Parameters are not persisted.

Panel source: `Copy of Detaliu kainos perskaiciavimas.xlsx`, `PNL kainso` and `Sheet5`, supplied 2026-09-08. All 81 PNL/PCL rows are retained. Base K is `(material rate + 18.95) * area + 4.17`; W is `area * 2`; X is `area * 1`. Total K+W+X is an explicitly labelled derived total, without a 7% discount. Sheet5 comparison values are historical source values, not a current sales-price feed.

Shelf source: `Copy of LENTYNU KAINU SKAICIAVIMAI_2026 04 20+ankstesnis skaiciavimai.xlsx`, `Lentynu med dal loginis persk`. All 297 source rows are retained with row identifiers. U is `(area * type rate - packaging - cardboard) * coefficient`; coefficient is 3 below 0.1 m², 1.5 below 0.2 m², otherwise 1. Source rows 7, 49 and 91 additionally multiply by 3; that exception is preserved and displayed. Total U+R+S is labelled separately from U.

The source has 120 rows with repeated SKUs, 24 type/code mismatches and 66 missing packaging/cardboard inputs. These counts overlap. No automatic deduplication or inferred SKU correction is applied. Blank packaging inputs yield an unavailable total; explicit zero is valid. Filled source calculations match all 231 cached U results. Missing-input source rows are retained for review and can be calculated by entering their missing inputs.

Tests cover all panel/source bases, all populated shelf/source U results, area threshold boundaries, exceptional multipliers, input changes, invalid numbers, authenticated routes and CSV row coverage. Two existing process-group tests in `test_webapp.py` require POSIX `os.killpg` and cannot run on Windows.

## Complete shelf workbook

`/shelf-workbook` uses all six worksheets. The immutable import retains every populated cell's address, cached value and original formula, together with the source file SHA-256. Sheet6 is empty. The source browser provides searchable, paginated access rather than executing arbitrary workbook formulas.

- `BOM 2026 04_prepack kainu skaic`: 224 parent BOMs / 1,655 lines. Correct component totals multiply G quantity by the exact SKU's `Purchase Price` H rate. Source J totals instead sum unweighted H prices; both are displayed. All 224 quantity-weighted totals differ. One shelf wood component has source quantity 0.4 and is flagged, not changed. Quantity/unit-price form edits are temporary scenarios.
- `Purchase Price`: all 659 keyed rows, retaining E purchase, F adjusted, G Reform adjustment and H final Reform separately, plus names/categories/vendors. Missing/error/conflicting prices cannot silently become zero or select the first duplicate. Identical duplicate prices can resolve with a note. Current BOM records all resolve; seven H errors elsewhere remain visible in purchase/source views.
- `Paprastu lentynu kainos`: 309 parent assemblies with 788 component lines. E is already an extended line cost; sum E without multiplying by D again. Every sum reconciles to F. All source rates, detailed panel/wood calculations and other cells remain available in the source view.
- `LED lentynos`: 48 independent LED/ROD cost breakdowns, including all nine C:K cost drivers, updated O, proposal P and analogous plain shelf T/U. All nine-driver sums reconcile to source L. Blank LED-operation costs on ROD rows are shown as zero in the editable scenario; the raw blank is preserved in source data. Historical proposal values are not silently substituted for calculated totals.
- `Lentynu med dal loginis persk`: the existing 297-row calculator remains the wood-part method. Its AI type tariffs are compared with the earlier sheet's AH weighted averages and AI suggestions; they are not merged. Ambiguous/missing rows remain flagged.

Exact-SKU cross-links connect purchase records, LED/plain shelf relationships, old assemblies and new BOM uses. No inferred code substitutions, global price updates, Odoo writes or SO pipeline changes are made.
