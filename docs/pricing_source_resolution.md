# Resolution of the 171 blocked SO positions

The earlier output contained 54 previously priced shelf positions that were
blocked by exact-SKU lookup, and 117 newly included positions absent from the
previous 4,215-position scope. The prior clean run did not validate these 117.

New plain/FIX/FIXVEN/OVEN/CORNER shelf dimensions now use the same shared
family formula as the calculator. Packaging/cardboard values come only from
unanimous populated source rows of that market and family. Exact source rows
and their exceptions still win. Additional source-row x3 exceptions do not
extend to new dimensions. LED/ROD still need their dedicated cost breakdown.

The previously omitted ORDER LINE sheet in the identical approved BOM workbook
(SHA256 ad879bb45126ce6b9922fa473f6fe96c9a10236873285a2acf3fcd63855ed13a)
contains 52 explicit finished-SKU / supplier-SKU pairs and category 6/11
assignments. Their current prepared purchase prices can price the named
supplier components. Extra BOM components remain separate. Existing supplier
prices and existing SKU rules win; conflicting aliases are not averaged.

The user confirmed that the ten additional storage-product purchase prices
listed in PRIMARY_MECHANISMS cover the main mechanism only. They therefore
price that mechanism, with all additional screws/documents still charged by
BOM quantities. Their current purchase prices are used, not historic workbook
amounts. The two-TIP-ON product requires a separate clarification of whether
the quoted purchase amount covers one or both parts.

Missing non-A INTERIOR STORAGE rules use the existing named category 6.
Missing FRONT HARDWARE rules inherit only if at least two existing parent
rules in that exact product type unanimously agree on every charge. Existing
SKU rules are preserved. A variants with different operations and products
without supported categories are not assigned arbitrary zero rates.
