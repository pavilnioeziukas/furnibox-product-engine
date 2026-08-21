# TOC Decision Support – darbo perdavimas 2026-08-21

## Sustabdymo būsena

- Darbas vykdomas branche `feature/toc-decision-support`.
- Paskutinis į GitHub išsiųstas commit: `53f3d14 Plan Assembly work across employee lanes`.
- Lokali darbo kopija sustabdymo metu buvo švari.
- Production Odoo šiame darbe naudojamas tik skaitymui; jokio rašymo į Production Odoo nėra.
- Bandymams skirta atskira Railway `stage` aplinka.

## Kas jau padaryta

1. Sudarytas aštuonių Furnibox vadybinių TOC klausimų katalogas.
2. MQ-001 įgyvendintas kaip šiandienos operacinis signalas, aiškiai atskirtas nuo patikimos sisteminės constraint išvados.
3. Rytinėje kontrolėje registruojamas Assembly pajėgumas ir fizinis Odoo nematomų komponentų patvirtinimas.
4. Odoo READY dalis nustatoma pagal MO komponentų rezervaciją; downstream `WH/PICK`, `WH/PACK` ir `WH/OUT` rezervacija READY sprendimui nenaudojama.
5. Sukuriama ir patvirtinama MQ-005 dienos Assembly eilė.
6. CONTROL dalis skaito faktines WO būsenas iš Production Odoo jų nekeisdama.
7. `mq005-v2` planavimas naudoja:
   - `Europe/Vilnius` laiko zoną;
   - darbo laiką 07:00–16:00;
   - pietų pertrauką 12:00–13:00, kurios laikas į pajėgumą neįtraukiamas;
   - 8 produktyvias valandas vienam darbuotojui;
   - atskirą lygiagretų takelį kiekvienam darbuotojui;
   - viso vieno SO priskyrimą vienam darbuotojo takeliui;
   - nebaigto SO tęsimą tame pačiame takelyje kitą darbo dieną;
   - savaitgalių neįtraukimą į planinį darbo laiką.
8. Paskutinė automatinė patikra: 32 testai sėkmingi.

## Kas dar nepatikrinta

Po `53f3d14` įdiegimo vartotojas negalėjo patikrinti Railway `stage` aplinkos. Todėl dar nepatvirtinta, kad naujai sugeneruotoje plano versijoje praktiškai teisingai rodomi:

- darbuotojų takeliai;
- planinė SO pradžia ir pabaiga;
- 12:00–13:00 pietų pertraukos praleidimas;
- SO perkėlimas į kitą darbo dieną.

Senas anksčiau patvirtintas `mq005-v1` planas automatiškai neperskaičiuojamas ir naujų laukų neturės. Tikrinimui būtina sugeneruoti naują `mq005-v2` plano versiją.

## Nuo ko pradedame kitą kartą

### 1. Trumpas `mq005-v2` priėmimo testas Railway stage

1. Atidaryti `https://furnibox-product-engine-stage.up.railway.app/toc/morning`.
2. Pasirinkti bandymo darbo datą ir patvirtinti tos dienos darbuotojų skaičių.
3. Patvirtinti fizinį pasirengimą keliems testiniams SO.
4. Paspausti **Generuoti naują plano versiją**.
5. Dar nepatvirtinus plano patikrinti darbuotojų takelius ir planinius laikus.
6. Ypač patikrinti SO, kurio darbas kerta 12:00, ir SO, kuris netelpa iki 16:00.
7. Jei rezultatas teisingas, patvirtinti plano versiją ir patikrinti CONTROL bloką.

### 2. Užfiksuoti priėmimo rezultatą

- Jei planas teisingas – pažymėti `mq005-v2` kaip priimtą stage aplinkoje.
- Jei ne – užrašyti konkretų SO, darbuotojo takelį, rodomą laiką ir tikėtiną laiką; taisyti tik atkuriamą neatitikimą.

### 3. Tik po priėmimo tęsti CONTROL

Kitas produkto pjūvis – palyginti patvirtinto SCHEDULE planinę pradžią su faktiniais Odoo WO įvykiais ir skaičiuoti planinio vykdymo nuokrypį. Iki `mq005-v2` priėmimo nepradedame MQ-002 ir neplečiame dabartinio ekrano kosmetiškai.

## Dar neįgyvendinta sąmoninga išimtis

Pagal sutartą Furnibox taisyklę vieną SO paprastai renka vienas darbuotojas. Vieno SO skaidymas keliems darbuotojams ateityje gali būti leidžiamas tik kaip gamybos vadovės audituojama išimtis. Šios išimties valdymo sąsaja dar neįgyvendinta.
