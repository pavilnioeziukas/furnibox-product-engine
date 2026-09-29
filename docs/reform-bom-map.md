# Reform Excel exchange

New downloads use **BOM Map** as the main editing sheet. Each row shows a path from a top product through its BOM levels to a component. Intermediate quantities belong to their parent BOM; the total is per one top product unit. Totals requiring unit conversion are left blank and marked for review.

Dark horizontal rules separate Top BOM groups; thinner rules mark changes of parent BOM within a group. Alternating blue and peach rows help track components. Coloured headers and vertical dividers distinguish hierarchy levels, component fields and references. The header and Top BOM column remain frozen while scrolling. These visual cues do not add rows or change the exchange data.

Edit a component code or quantity in one occurrence. The importer applies the edit to the underlying BOM line wherever it is used. Conflicting edits to the same line are rejected. Use `REMOVE` to remove the final component from its parent; keep original rows and hidden Row IDs.

To add a component, append a row with an empty Row ID, `Parent BOM SKU`, `Purchased Component SKU`, component quantity, and `KEEP`. For a new BOM, first add its product card and its definition in **BOMs**.

**Products** contains cards with BOMs. **Non-BOM** contains cards without BOMs. Both support card edits and additions. **Supplier Code** is reference data from Odoo; multiple supplier codes are separated by semicolons. It cannot be edited through this exchange.

Downloads retain an immutable server-side export record. Older exported workbooks remain supported. Uploads produce a proposed draft for review and version submission; they do not write to Odoo.

Administrators can load SKU-to-supplier-code reference data through the CSRF-protected `/reform/supplier-reference` endpoint. This updates reference data only and preserves the catalogue, drafts, releases, and existing export records.
