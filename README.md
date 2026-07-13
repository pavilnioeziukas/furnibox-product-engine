# Reform BOM Transformer – Odoo Connector v0.1

1. Išarchyvuokite projektą į `C:\Projects\Reform BOM Transformer`.
2. Nukopijuokite `.env.example` ir pervadinkite kopiją į `.env`.
3. `.env` faile įrašykite API raktą.
4. Paleiskite `paleisti_odoo_snapshot.bat`.

Rezultatas: `output\Odoo_Snapshot.xlsx`

Lapai:
- INFO
- ODOO PRODUCTS
- ODOO BOM
- ODOO BOM LINES
- LAST PURCHASE PRICES

Paskutinė pirkimo kaina imama iš naujausios patvirtinto arba užbaigto pirkimo užsakymo eilutės.
