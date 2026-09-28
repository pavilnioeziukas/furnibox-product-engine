# Reform versijų pakeitimai

1. Įkelkite naują Reform Excel pagrindinio puslapio skiltyje **Reform BOM įvestis**.
2. Atverkite **Ataskaitos → Reform versijų pakeitimai** arba nuorodą po įkėlimo forma.
3. Pasirinkite ankstesnį ir naują failą iš įkėlimų istorijos. Pagal nutylėjimą siūlomi du paskutiniai įkėlimai, ne patvirtintos versijos; patikrinkite failų pavadinimus.
4. Spauskite **Palyginti versijas**. Ataskaita išsaugoma, ją galima filtruoti ir atsisiųsti Excel.

Ataskaita rodo naujus, pašalintus, pakeistus ir nepakitusius BOM; unikalius naujus ir pašalintus SKU (įskaitant komponentus); komponentų bei kiekių pakeitimus ir užpildytų duomenų laukų senas ir naujas reikšmes. Tas pats komponentas viename BOM sumuojamas; eilučių ir komponentų vieta nepaveikia rezultato.

Tai failų versijų palyginimas, ne palyginimas su Odoo. Pašalinimas faile nėra nurodymas archyvuoti Odoo produktą. Palyginimas nekeičia Odoo ar aktyvaus failo. Naujo failo įkėlimas išlaiko esamą Product Engine įkėlimo elgseną.

Skaitomas vienas lapas pagal prioritetą: `BOM - Input`, `BOM - Full DB`, `BOM VERTICAL`. Excel formulės neperskaičiuojamos: prieš įkeliant failą būtina perskaičiuoti ir išsaugoti Excel. Kiti lapai, formulių tekstas, formatavimas ir REF nelaikomi produktų pakeitimais. Skirtingų struktūrų lapai, tušti failai, pasikartojantys BOM, prieštaringi komponentų duomenys ir netinkami kiekiai sustabdo palyginimą. Trūkstamos ar tuščios laukų reikšmės laikomos tuščiomis.

Ekrane rodoma iki 1 000 filtruotų pakeitimų eilučių; Excel pateikiamos visos. JSON ataskaitos laikomos esamame persistent STATE_DIR aplanke `version_reports`, o šaltiniai imami iš esamo `uploads` aplanko. HTTP prieiga naudoja bendrą programos autentifikaciją, palyginimo POST papildomai tikrina CSRF. Failai pasirenkami tik iš serverio įkėlimų sąrašo.

Patikra: `python -m unittest test_reform_version_diff -v`.


## Skaitoma pakeitimų ataskaita

Pagrindinis vaizdas rodo išvadą, unikalių SKU išskaidymą pagal kategoriją ir savo BOM turėjimą, naujų BOM grupes pagal kategoriją ir kodo pradžią. SKU ir BOM skaičiai nesumuojami. Viena SKU sąrašo eilutė atitinka vieną kodą, o viena BOM sąrašo eilutė — vieną BOM su išskleidžiama komplektacija. Esamų BOM pakeitimai pateikiami sakiniais. Pašalinti SKU ir pašalinti BOM atskiriami.

Excel skyriai: Santrauka, Nauji SKU, Nauji BOM, BOM komponentai, Esamų BOM pakeitimai, Pašalintos pozicijos, Pakeitimai (pilnas techninis priedas). Trūkstami komponentų pavadinimai neinventuojami. Ankstesnės JSON ataskaitos pateikiamos nauju formatu jų neperskaičiuojant ir nekeičiant šaltinio failų.
