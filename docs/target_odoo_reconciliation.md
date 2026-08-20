# Target Dataset vs Production Odoo reconciliation

## Kodėl reikėjo atskiro palyginimo

- `map_comparison_v5.py` lygina Reform MAP ryšius, todėl nemato galutinės
  Furnibox transformacijos (Cabinet-A, APACK, HRD-A ir Shelf-PP).
- `bom_release/analyzer.py` tik nustato, ar naują BOM saugu kurti. Jame aiškiai
  nebuvo lyginamas jau egzistuojančio BOM turinys.
- `product_import_v10.py` generuoja tik trūkstamų kortelių importą. Jis
  nepriskiria statuso kiekvienai Target katalogo kortelei ir netikrina esamų
  kortelių laukų pokyčių.
- Nebuvo vieno rezultato, apimančio ne-BOM produktus, SKU dublikatus, aktyvumą,
  External ID, kategorijas, maršrutus, BOM tipą, Sequence 0 pasirinkimą,
  komponentus ir operacijas.

## Naujas read-only srautas

`reconcile_target_odoo.py` priima tik galutinį JSON, turintį `product_catalog`
ir `products`. Production Odoo nuskaitoma tik per `search_read`; `create`,
`write`, `unlink`, `export_data` ir importo generatoriai nekviečiami.

```text
python reconcile_target_odoo.py \
  --dataset path/to/Full_Target_Dataset.json \
  --output output/production/Target_Odoo_Reconciliation.json
```

Rezultatas yra JSON su `mode: READ_ONLY`, suvestine ir atskiromis `products`
bei `boms` eilutėmis. Viena BOM eilutė gali turėti kelis detalius pakeitimus;
jos pagrindinis statusas parenkamas deterministine tvarka: BOM tipas,
operacijos, kiekis, šalinimas, pridėjimas.

Produkto importo profilis pirmiausia imamas iš Dataset `import_profile` arba
`expected`. Jei jo nėra, kategorija, maršrutai, produkto tipas, sąskaitų
politika ir tiekėjas nustatomi pagal vyraujantį tos pačios galutinės Furnibox
grupės Production profilį. Jei etalonas dviprasmis arba jo nėra, rezultatas yra
`BLOCKED`, o ne spėjimas.

Shelf lyginama jau transformuota: galutinė Shelf kortelė ir jos KIT BOM atskirai
nuo Shelf-PP kortelės ir jos MANUFACTURE BOM. Todėl Production PP etalono
pakuotė, lipdukai ir pakavimo operacija patenka į įprastą komponentų bei
operacijų palyginimą. Reform struktūra šiame etape nebetransformuojama ir PP
nedubliuojamas.
