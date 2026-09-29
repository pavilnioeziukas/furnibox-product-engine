# Reform Excel exchange

## Current format: vertical BOM

New downloads use **BOM** as the editing sheet, with two levels per block: the parent and its direct components. A cabinet lists its FPACK and HRD assemblies; each assembly has its own block listing its direct children. Shared sub-BOMs appear once. Editing a shared BOM affects every parent that uses it.

Visible columns are Parent BOM SKU, Component SKU, Quantity, Unit, Supplier Code, Action and Note. The hidden BOM key and Line ID retain stable identity. Quantities belong to the immediate parent and its output quantity in **BOMs**; they are not multiplied across a hierarchy. Nine-point text and compact rows reduce horizontal and vertical scrolling. Each complete BOM block has one fill colour; peach and blue alternate between BOMs. Dark lines separate the blocks.

Edit Component SKU or Quantity, or set Action to REMOVE. Keep existing rows, IDs and reference fields unchanged. Unit and Supplier Code refer to the original exported component, even when proposing a replacement SKU; a new download refreshes these references.

To add a component, append a row with Parent BOM SKU, Component SKU, Quantity and KEEP. Leave the reference fields and hidden IDs blank. The parent must identify exactly one BOM in **BOMs**. To create a BOM, first add its product card and a definition with a NEW- key in **BOMs**.

**Products** contains cards with BOMs; **Non-BOM** contains other cards. Both support card edits and additions. Supplier Code is read-only Odoo reference data. No prices are included. The separate Furnibox pricing MAP remains unchanged by this exchange format.

Uploads validate the workbook against its server-side export record, including ownership and source/draft revision. They create a draft only. Existing legacy and BOM Map exports remain importable through their saved format metadata. New default downloads do not contain BOM Map.

## Previous BOM Map format (existing files only)

Previously downloaded **BOM Map** workbooks show paths from top products through BOM levels to a component. Intermediate quantities belong to their parent BOM; the total is per one top product unit. Totals requiring unit conversion are left blank and marked for review.

Dark horizontal rules separate Top BOM groups; thinner rules mark changes of parent BOM within a group. Alternating blue and peach rows help track components. Coloured headers and vertical dividers distinguish hierarchy levels, component fields and references. The header and Top BOM column remain frozen while scrolling. These visual cues do not add rows or change the exchange data.

Edit a component code or quantity in one occurrence. The importer applies the edit to the underlying BOM line wherever it is used. Conflicting edits to the same line are rejected. Use `REMOVE` to remove the final component from its parent; keep original rows and hidden Row IDs.

To add a component, append a row with an empty Row ID, `Parent BOM SKU`, `Purchased Component SKU`, component quantity, and `KEEP`. For a new BOM, first add its product card and its definition in **BOMs**.

**Products** contains cards with BOMs. **Non-BOM** contains cards without BOMs. Both support card edits and additions. **Supplier Code** is reference data from Odoo; multiple supplier codes are separated by semicolons. It cannot be edited through this exchange.

Downloads retain an immutable server-side export record. Older exported workbooks remain supported. Uploads produce a proposed draft for review and version submission; they do not write to Odoo.

Administrators can load SKU-to-supplier-code reference data through the CSRF-protected `/reform/supplier-reference` endpoint. This updates reference data only and preserves the catalogue, drafts, releases, and existing export records.
