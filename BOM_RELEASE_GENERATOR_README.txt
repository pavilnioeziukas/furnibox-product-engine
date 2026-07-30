FURNIBOX BOM RELEASE GENERATOR

Paketą išskleisti į:
C:\Projects\furnibox-product-engine

Leisti testus:
python -m unittest test_bom_release_generator.py test_legacy_apack_generation.py test_pre_activation_acceptance.py -v

Generatorius:
python generate_bom_release.py --dataset $dataset.FullName

Generatorius:
- skaito tik patvirtintą Validated Product Dataset;
- iš naujo atlieka Dataset acceptance;
- read-only režimu patikrina Production produktus, External ID, darbo centrus
  ir release planą;
- sukuria nepersidengiančius importo failus pagal BOM lygį ir tipą;
- nieko nekuria ir nekeičia Odoo.

Sugeneruotų Excel failų į Production dar neimportuoti, kol neperžiūrėta
generatoriaus suvestinė ir failų skaičiai.
