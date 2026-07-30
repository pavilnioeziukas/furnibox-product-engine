# Furnibox BOM Release Acceptance Rules

## Privalomos taisyklės

1. Kiekvienas bazinis `CABINETS` produktas turi turėti `-A` porą.
2. Bazinio kabineto BOM tipas turi būti `KIT` ir turėti tiksliai:
   - vieną `FPACK`;
   - vieną `HRD`.
3. Surinkto `-A` kabineto BOM tipas turi būti `KIT` ir turėti tiksliai:
   - vieną `APACK`;
   - vieną `HRD-A`.
4. Susijusių `FPACK` ir `APACK` Cabinet Parts SKU ir kiekiai turi sutapti.
5. `HRD-A` gali turėti tik komponentus ir kiekius, kurie egzistuoja baziniame `HRD`.
6. Kiekviena aktuali Dataset `CABINET PART` turi būti panaudota bent viename tikrinamame BOM.
7. BOM negali būti tušti, o komponentų kiekiai turi būti didesni už nulį.
8. BOM negali turėti dubliuotų eilučių ar komponentų, kurių nėra Validated Dataset produktų sąraše.
9. Odoo režime tam pačiam Parent SKU negali būti:
   - kelių to paties release ir sequence BOM;
   - kelių aktyvių BOM su `sequence = 0`;
   - neteisingo release reference arba sequence.
10. Odoo release turi tiksliai sutapti su Validated Dataset:
    - `MISSING = 0`;
    - `EXTRA = 0`;
    - komponentų ir kiekių skirtumai `= 0`;
    - BOM tipo skirtumai `= 0`;
    - reference ir sequence skirtumai `= 0`.

## Du atskiri vartai

`--source dataset` yra priešimportinė Dataset vidinės struktūros patikra.

`--source odoo` yra poimportinė faktinio Odoo release patikra ir pilnas
Dataset ↔ Odoo palyginimas. Production aktyvavimui būtini abu `PASS`.

## Paleidimo režimai

Prieš generuojant/importuojant:

```powershell
python .\pre_activation_acceptance.py --source dataset
```

Po naujų BOM importo su `sequence = 10`:

```powershell
python .\pre_activation_acceptance.py `
  --source odoo `
  --release-reference REFORM_v08_20260729 `
  --sequence 10
```

Po aktyvavimo su `sequence = 0`:

```powershell
python .\pre_activation_acceptance.py `
  --source odoo `
  --release-reference REFORM_v08_20260729 `
  --sequence 0
```

Release aktyvuoti arba leisti Tamarai kurti naujus SO galima tik kai galutinis rezultatas yra `PASS` ir visi klaidų skaičiai lygūs nuliui.
