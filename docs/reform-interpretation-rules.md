# Reform duomenų interpretavimo taisyklių registras

Versija 0.4 · 2026-11-09

Šis registras aprašo, kaip Furnibox interpretuoja Reform pateiktus duomenis ir paruošia juos peržiūrai. Reform gali išlaikyti savo kodus ir BOM struktūrą. Furnibox atsako už jų susiejimą su sutvarkytu ERP katalogu ir gamybos struktūra.

Registro sudarymas nepatvirtina konkrečių prekių atitikmenų ar BOM pakeitimų. Taisyklių susitarimai užfiksuoti pagal Edgaro nurodymus šiame darbo pokalbyje. Tamaros paketo patvirtinimas ir galutinis leidimas taikyti fiksuojami atskirai.

## Būsenų reikšmės

- **Sutarta** – principas aiškiai nustatytas darbo pokalbyje.
- **Tikslintina** – turime konkretų atvejį, tačiau bendros taikymo sąlygos dar nepatvirtintos.
- Įgyvendinimo būsena aprašo patikrintą kodo dalį. Ji nereiškia viso proceso užbaigimo.

## Taisyklės

| ID | Taisyklė | Taikymas ir išimtys | Pavyzdys | Susitarimas | Įgyvendinimas |
|---|---|---|---|---|---|
| R01 | Reform pateikimas yra siūlymas Furnibox peržiūrai. | Originalų failą, pateikėją, laiką ir palyginimo įrodymus išsaugoti. Vėlesnė patikra turi būti atskiras rezultatas. | Poul pateiktas paketas lieka užrakintas. | Sutarta | Portalo pateikimas užrakinamas. Automatinio perdavimo į vidinę patikrą dar nėra. |
| R02 | Furnibox patikros atskaitos taškas yra aktuali Odoo produkcija. | Fiksuoti nuskaitymo laiką ir naudotas korteles bei BOM revizijas. Portalo BOM v10 palyginimas vienas pats nepakankamas sprendimui taikyti. | Reform skirtumas gali jau būti įgyvendintas Odoo arba pateiktas kitame BOM lygyje. | Sutarta | Non-BOM skaitoma iš produkcijos. BOM patikra ir pilnas duomenų momentinės kopijos fiksavimas neįgyvendinti. |
| R03 | Prekę susieti pagal vidinį kodą ir konkretaus Reform tiekėjo prekės kodą. | Reform Product Code tikrinti pagal Internal Reference. Product Code ir prasmingą Supplier Code tikrinti pagal Reform Supply & Logistics, UAB Vendor Product Code. 0 ir (blank) nelaikyti tiekėjo kodais. | 91970369 → UNI-P-ACC02-MIS017 pagal tiekėjo kodą. | Sutarta | Įgyvendinta vidinėje Non-BOM patikroje. |
| R04 | Įtraukti aktyvias ir archyvuotas korteles. | Archyvo būsena turi būti matoma. Archyvuoto atitikmens radimas turi stabdyti automatinę prielaidą, kad reikia naujos kortelės. | Archyvuotas 91970369 ir aktyvus UNI-P-ACC02-MIS017 rodomi kartu. | Sutarta | Kortelės skaitomos su active_test=False. |
| R05 | Vienareikšmis tiekėjo kodo atitikmuo reiškia esamą prekę. | Rodyti informacinį susiejimą su Furnibox kortele. Naujos kortelės nesiūlyti. Archyvuoto atitikmens naudojimui ar atkūrimui reikia atskiro sprendimo. | Reform 210024442 → EUB-P-ACC02-MIS030. | Sutarta | vendor_existing grupė įgyvendinta. Dabartinis kodas į ją įtraukia ir vienintelį archyvuotą tiekėjo atitikmenį. Atskirą atkūrimo peržiūrą dar reikia papildyti. |
| R06 | Keli atitikmenys arba skirtingų kodų konfliktas reikalauja peržiūros. | Išsaugoti visus kandidatus ir sutapimo pagrindus. Aktyvi kortelė savaime nenugali archyvuotos kortelės. Taisyklei apie sutvarkytos kortelės pirmenybę reikia aiškaus patvirtinimo. | Tas pats Reform kodas sutampa su archyvuotos kortelės Internal Reference ir aktyvios kortelės Vendor Product Code. | Sutarta | conflict grupė įgyvendinta. |
| R07 | Nerasta pagal kodus reiškia kandidatą kurti. | Naujos prekės sukūrimo sprendimą priima peržiūrėtojas. Pavadinimas, matmenys, spalva ir matavimo vienetai naudojami sprendimui patikrinti. | 153 ankstesnio paketo eilutės buvo kandidatės. Skaičius nepriskiriamas kitiems paketams. | Sutarta | candidate grupė įgyvendinta. Semantinė savybių patikra dar rankinė. |
| R08 | Matavimo vienetų raidžių dydis ir kraštiniai tarpai nekeičia reikšmės. | unit ir Units susieti su vienareikšmiu katalogo vienetu. kg, m ir m² išlaikyti atskirai. Nežinomą ar dviprasmį vienetą parodyti kaip klaidą. | UNIT → Units. | Sutarta | Portalo Non-BOM validacijoje įgyvendinta. Vidinėje patikroje papildomas UOM sutikrinimas dar neprijungtas. |
| R09 | Produktų kodų raidžių dydžio skirtumą priimti tik esant vienareikšmiam atitikmeniui. | Išsaugoti originalų Reform kodą. Keli atitikmenys lieka konfliktu. | Shim-10x20 → SHIM-10x20. | Sutarta | Portalo validacijoje tikslus sutapimas turi pirmenybę. Vidinė patikra sujungia visus atitikmenis ignoruodama raidžių dydį. Skirtumą reikia suvienodinti. |
| R10 | Reform BOM ir Non-BOM gali aprašyti tą pačią Furnibox perkamą poziciją. | Tikrinti visą Reform BOM. Vieno komponento BOM, komponento Non-BOM eilutė ir to paties Furnibox produkto tiekėjo kodas sudaro persidengimo kandidatą. Vien pakeitimų eksporto nepakanka komponentų skaičiui nustatyti. | UNI-P-ACC02-MIS017 → vienintelis komponentas 91970369. Furnibox naudoja UNI-P-ACC02-MIS017 kaip perkamą kortelę. | Tikslintina | Neįgyvendinta. Reikia patvirtinti visą BOM ir prekės pirkimo konfigūraciją. |
| R11 | Reform BOM kodas ir faktinis keičiamas Odoo BOM turi būti atskiri laukai. | Tikslinį BOM nustatyti pagal patvirtintą struktūros ryšį, aktualią reviziją ir šalinamo komponento vietą. Kodo sufikso pašalinimas vienas pats nepakankamas. | Reform EUB-PACK-CAB03-SLF901-PP → Odoo EUB-C-CAB03-SLF901. | Sutarta kaip principas. Bendras algoritmas tikslintinas. | 12 konkrečių atvejų patikrinti Odoo 2026-11-06. Automatinis sprendimas neįgyvendintas. |
| R12 | Komponento pašalinimą ir pridėjimą galima rodyti kaip pakeitimą tik nustačius porą. | Turi sutapti patvirtintas tikslinis BOM ir pakeitimo kontekstas. Keli pridėjimai ir pašalinimai negali būti suporuoti vien pagal eiliškumą. Saugoti originalias eilutes ir kiekius. | EUB-LED-LAB01-1163-MB → EUB-LED-LAB01-1163-MS. | Tikslintina | Rankiniu būdu nustatytos 12 LED porų. Bendro poravimo algoritmo nėra. |
| R13 | Ankstesnis BOM su tuo pačiu komponentu savaime netampa pakeitimo tikslu. | Rodyti BOM ID, produktą, aktyvumą, revizijos žymą, tipą ir pasirinkimo pagrindą. Jei keli galimi aktualūs BOM, perduoti peržiūrai. | Ankstesni PP BOM ir v10 Cabinet Shelf BOM turi skirtingą paskirtį. | Sutarta | Dabartinės automatinės BOM patikros nėra. Vien aktyvumo filtro nepakanka. |
| R14 | Prieš taikymą reikia kelių atskirų patvirtinimų. | Reform pateikimas → Furnibox patikra → Tamaros turinio patvirtinimas → galutinis Furnibox leidimas. Pasikeitus susijusiems Odoo duomenims po patvirtinimo, paveiktas eilutes patikrinti iš naujo. | Patvirtinti tik konkrečiai peržiūrėtas eilutes ir kiekius. | Sutarta | Išsaugomi peržiūros sprendimai ir laikas. Vardinė tapatybė, etapų kontrolė ir pasikeitusių duomenų patikra neįgyvendintos. |
| R15 | Po patikros paruošti Reform grįžtamąją informaciją. | Rodyti patvirtintą kodų atitiktį, BOM/Non-BOM persidengimus ir klausimus. Vidinius sprendimus nuo Reform skirtos suvestinės atskirti pagal auditoriją. | 91970369 naudojamas kaip UNI-P-ACC02-MIS017 tiekėjo kodas. | Sutarta | Suvestinė ir jos eksportas dar neįgyvendinti. |
| R16 | Naujas BOM tik kai tinkamo Odoo BOM nėra; esamas koreguojamas per PLM. | Išspręsti produkto, varianto, BOM tipo ir įmonės kontekstą. Iš tinkamų aktyvių BOM pasirinkti vienintelį su mažiausiu sequence, nepriklausomai nuo pavadinimo, v10 žymos ar PLM revizijos. Kelios vienodos mažiausios sequence reikšmės, trūkstama sequence, neaiški paskirtis ar nepilnas nuskaitymas reiškia peržiūrą. Aukštesnių sequence tarpusavio sutapimas atrankai netrukdo. Tik archyvuoti BOM nesuteikia leidimo kurti naują. Stage nerastas BOM tėra kandidatas, galutinis etalonas — produkcija. Atranka nėra turinio patvirtinimas ar vykdymo leidimas. | Sequence 3 laimi prieš 10 net jeigu BOM su 10 pavadintas v10. | Sutarta | Stage piloto klasifikacija ir rodomas pasirinkimas naudoja tą pačią sequence atranką. Visam paketui ir produkciniam vykdymui dar neprijungta. |

## Patikrinti LED BOM struktūros atvejai

Patikrinta produkciniame Odoo 2026-11-06 pagal šalinamo MB komponento naudojimą. Tai konkrečių atvejų įrodymai, kuriuos prieš taikymą reikia atnaujinti. Ši lentelė nesuteikia bendro leidimo perkelti visus PP pakeitimus į Cabinet Shelf BOM.

| Reform BOM numeriai | Reform produkto kodo forma | Odoo v10 produkto kodo forma | Šalinamas komponentas | Siūlomas komponentas |
|---|---|---|---|---|
| 901, 905, 909 | EUB-PACK-CAB03-SLF{nr}-PP | EUB-C-CAB03-SLF{nr} | EUB-LED-LAB01-1163-MB | EUB-LED-LAB01-1163-MS |
| 902, 906, 910 | EUB-PACK-CAB03-SLF{nr}-PP | EUB-C-CAB03-SLF{nr} | EUB-LED-LAB01-363-MB | EUB-LED-LAB01-363-MS |
| 903, 907, 911 | EUB-PACK-CAB03-SLF{nr}-PP | EUB-C-CAB03-SLF{nr} | EUB-LED-LAB01-563-MB | EUB-LED-LAB01-563-MS |
| 904, 908, 912 | EUB-PACK-CAB03-SLF{nr}-PP | EUB-C-CAB03-SLF{nr} | EUB-LED-LAB01-763-MB | EUB-LED-LAB01-763-MS |

## Peržiūros rezultato reikalavimai

Kiekvienai eilutei saugoti originalų Reform kodą, pavadinimą, tiekėjo kodą ir šaltinio eilutę. Pridėti Odoo kortelių ID, vidinius kodus, pavadinimus, archyvo būseną ir sutapimo pagrindą. BOM atvejui pridėti Reform BOM, tikslinį Odoo BOM ID ir reviziją, komponentus bei kiekius prieš ir po siūlomo pakeitimo.

Prie patikros turi būti nurodyta naudojama šio registro versija, Reform paketo tapatybė, Odoo nuskaitymo laikas ir patikros būsena. Peržiūros sprendimui reikia sprendėjo tapatybės, laiko, pastabos ir konkrečios patvirtintos apimties.

Dabartinis vidinis įrankis paketo sprendimus sieja su įkelto XLSX baitų SHA256 ir visos sutikrintos eilutės SHA256. Perkūrus tą patį eksportą gali pasikeisti failo tapatybė. Paketo kontrolinė suma kol kas naudojama parodymui, o paties eksporto turinio atitiktis originaliam portalo paketui kriptografiškai nepatikrinama. Tai reikia išspręsti prieš patvirtinimus naudojant pakeitimų taikymui.

## Dar nepatvirtinti arba neatlikti darbai

1. Apibrėžti bendrą Reform ir Furnibox BOM struktūrų atitiktį. Atskirai patvirtinti PP, galutinio Shelf, KIT ir vieno komponento perkamos pozicijos atvejus.
2. Patikrinti UNI-P-ACC02-MIS017 visą Reform BOM ir produkcinę tiekėjo kodo reikšmę. Ankstesnėje Odoo patikroje rasta 91970369, o vienoje žinutėje nurodyta 197036. Pastarosios reikšmės nenaudoti kaip patvirtinto atitikmens.
3. Sutarti, kada aktyvus tiekėjo atitikmuo ir archyvuotas vidinio kodo atitikmuo laikomi sutvarkyto katalogo istorija, o kada tikru konfliktu.
4. Įgyvendinti vardinę Tamaros peržiūrą, galutinio leidimo vaidmenį ir pasikeitusių Odoo duomenų tikrinimą.
5. Prijungti viso Reform pateikimo automatinį perdavimą, BOM patikrą ir Reform grįžtamąją suvestinę.

## Pakeitimų žurnalas

| Data | Versija | Pakeitimas | Pagrindas |
|---|---|---|---|
| 2026-11-09 | 0.4 | Papildyta R14 įgyvendinimo būsena: Stage sprendimų žurnalas, vardinių paskyrų kontrolė, atskiri patvirtinimai ir pasikeitusių duomenų apsauga. | Sutarto peržiūros proceso realizacija. |
| 2026-11-09 | 0.3 | R16 patikslinta: aktualus BOM atrenkamas pagal vienintelį mažiausią sequence, ne pagal v10 pavadinimą. | Edgaro patvirtinta atrankos taisyklė. |
| 2026-11-08 | 0.2 | Pridėta R16: naujo BOM ir esamo BOM PLM korekcijos klasifikacija, archyvo ir dviprasmiškumo išimtys. | Edgaro patvirtinimas šiame pokalbyje. |
| 2026-11-08 | 0.1 | Sukurtas bendras registras. Sujungti sesijos susitarimai, konkretūs pavyzdžiai ir esamo įgyvendinimo ribos. | Edgaro prašymas turėti apibrėžtą taisyklių sąrašą. |

Taisyklės keitimas turi papildyti šį žurnalą, nurodyti patvirtinusį asmenį ir susijusį kodo pakeitimą. Konkrečių paketo eilučių patvirtinimai saugomi atskirai nuo bendrų taisyklių.
