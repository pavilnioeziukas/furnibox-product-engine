STAGE PRODUCT EXTERNAL ID WORKFLOW v1

Tikslas
------
1. Iš vieno ar kelių BOM XLSX surinkti Internal Reference.
2. Iš Stage ištraukti faktinius product.template ir product.product External ID.
3. Išsaugoti juos JSON žodyne.
4. Pagal žodyną persieti BOM XLSX neprisijungiant prie Odoo.

Sauga
-----
- Eksportas leidžiamas tik kai ODOO_URL turi "stage".
- Odoo duomenys nekeičiami.
- Nerastas, neunikalus ar External ID neturintis SKU blokuoja rezultatą.
- Persiejimas keičia tik:
  Product/External ID
  BoM Lines/Component/External ID
- Operation Type, kiekiai, operacijos ir kiti laukai nekeičiami.

Failai
------
stage_product_id_map.py
export_stage_product_ids.py
remap_bom_external_ids.py
test_stage_product_id_workflow.py

Pastaba
--------
Atnaujinus Stage duomenų bazę iš Production kopijos, JSON žodyną reikia
sugeneruoti iš naujo.
