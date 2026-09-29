# HB hardware pricing correction

Approved by the user on 2026-09-29 from HRD201HB and HRD211HB examples.
Remove direct NAIL-1 and PRIZM-1 lines from every HRD<number>HB pricing BOM,
including generated -A variants. Keep all other components and quantities.
The supplied Reform v11 contains HRD201HB, HRD211HB and HRD221HB; each loses
15 NAIL-1 and 8 PRIZM-1. Their respective HRD029/030/032 packs remain at two.

The correction is applied to isolated pricing structures before recursive cost
resolution and affects both standalone HB prices and their parent products.
An old direct HB price cannot override the corrected composition. The component
cost audit uses the corrected lines, and application runs export the removed
quantities to HRD_HB_Corrections_Applied.json. Reapplying the correction does not
change the result. Other hardware families retain these components.

This is a pricing rule: source workbooks, the Target dataset and Odoo BOMs are
not rewritten. Deployment remains pending user approval.
