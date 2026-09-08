# Panel and shelf review calculators

Authenticated routes `/calculators/panel` and `/calculators/shelf` provide independent, request-scoped calculations and CSV export. They do not modify Odoo, Target, purchase adjustments or the SO pricing pipeline. Changing a selected row affects its detail result; the catalogue export uses source rows and the submitted common rates. Parameters are not persisted.

Panel source: `Copy of Detaliu kainos perskaiciavimas.xlsx`, `PNL kainso` and `Sheet5`, supplied 2026-09-08. All 81 PNL/PCL rows are retained. Base K is `(material rate + 18.95) * area + 4.17`; W is `area * 2`; X is `area * 1`. Total K+W+X is an explicitly labelled derived total, without a 7% discount. Sheet5 comparison values are historical source values, not a current sales-price feed.

Shelf source: `Copy of LENTYNU KAINU SKAICIAVIMAI_2026 04 20+ankstesnis skaiciavimai.xlsx`, `Lentynu med dal loginis persk`. All 297 source rows are retained with row identifiers. U is `(area * type rate - packaging - cardboard) * coefficient`; coefficient is 3 below 0.1 m², 1.5 below 0.2 m², otherwise 1. Source rows 7, 49 and 91 additionally multiply by 3; that exception is preserved and displayed. Total U+R+S is labelled separately from U.

The source has 120 rows with repeated SKUs, 24 type/code mismatches and 66 missing packaging/cardboard inputs. These counts overlap. No automatic deduplication or inferred SKU correction is applied. Blank packaging inputs yield an unavailable total; explicit zero is valid. Filled source calculations match all 231 cached U results. Missing-input source rows are retained for review and can be calculated by entering their missing inputs.

Tests cover all panel/source bases, all populated shelf/source U results, area threshold boundaries, exceptional multipliers, input changes, invalid numbers, authenticated routes and CSV row coverage. Two existing process-group tests in `test_webapp.py` require POSIX `os.killpg` and cannot run on Windows.
