FURNIBOX APACK / HRD-A STAGE PILOTAS v2

Paketą išskleisti į:
C:\Projects\furnibox-product-engine

Testas:
python -m unittest test_prepare_bom_release_pilot.py -v

PowerShell:
$lv2Manufacture = Join-Path $releaseDir "BOM_Release_${releaseId}_lv2_Manufacture.xlsx"
$pilotFile = Join-Path $releaseDir "BOM_Release_${releaseId}_STAGE_PILOT.xlsx"

python prepare_bom_release_pilot.py `
  --source $lv2Manufacture `
  --audit $auditV7 `
  --output $pilotFile

Generatorius:
- renkasi tik transformuotą APACK;
- atmeta DEFAULT_HRD_REVIEW ir USB legacy išimtis;
- prideda susietą HRD-A;
- jei HRD-A bendras, prideda visus jį naudojančius APACK;
- Odoo neskaito ir nekeičia.

Sugeneruoto piloto dar neimportuoti, kol neperžiūrėta terminalo suvestinė.
