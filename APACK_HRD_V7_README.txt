APACK / HRD-A VALIDATED DATASET TRANSFORMACIJA v7

Taisyklė:
- patvirtinti komponentai perkeliami iš HRD-A į APACK;
- neaiškūs komponentai lieka tik HRD-A;
- komponentas negali būti automatiškai paliktas ir APACK, ir HRD-A;
- Odoo šis žingsnis nekeičia.

1. Testai

python -m unittest test_analyze_apack_hrd_transfer.py test_apply_apack_hrd_transfer.py -v

2. Transformacija

$datasetV7 = Join-Path $importDir "Validated_Product_Dataset_APACK_HRD_v7.json"
$auditV7 = Join-Path $importDir "APACK_HRD_Transformation_Audit_v7.json"

python apply_apack_hrd_transfer.py `
  --dataset $dataset.FullName `
  --analysis $analysis `
  --output $datasetV7 `
  --audit $auditV7

Tik jei transformacijos statusas PASS, galima iš naujo generuoti BOM Release
naudojant $datasetV7. Ankstesni 4067 BOM importo failai nebegalioja.

3. Naujo BOM Release generavimas

$releaseId = "REFORM_v09_20260730"
$releaseDir = Join-Path $importDir "BOM_Release_$releaseId"

python generate_bom_release.py `
  --dataset $datasetV7 `
  --release-id $releaseId `
  --release-reference $releaseId `
  --output-dir $releaseDir

4. Priešimportinė patikra

python validate_bom_release_imports.py `
  --dataset $datasetV7 `
  --release-id $releaseId `
  --release-reference $releaseId `
  --import-dir $releaseDir

Importuoti galima tik naujai sugeneruotą release, kai:
- generatoriaus BLOCKED = 0;
- priešimportinės patikros Statusas = PASS;
- BOM aprėptis actual/expected sutampa;
- senieji 4067 BOM failai nenaudojami.
