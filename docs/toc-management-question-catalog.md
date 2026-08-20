# TOC vadybinių klausimų katalogas

Statusas: pradinis specifikacijos artefaktas, skirtas sprendimo logikai formalizuoti prieš projektuojant ar programuojant funkcionalumą.

## Paskirtis

Katalogas aprašo ne ataskaitas ar KPI, o vadybinius klausimus, kurių atsakymai turi pakeisti konkretų sprendimą ir veiksmą. Pagal Eliyahu M. Goldratto *The Haystack Syndrome* logiką Product Engine turi būti projektuojamas tokia seka:

`vadybinis klausimas → sprendimas → sprendimo logika → reikalingi duomenys → informacija → veiksmas`

Duomenų prieinamumas nėra pradinis kriterijus klausimui pasirinkti. Pirmiausia formalizuojamas vertingas klausimas ir sprendimo procedūra; tik tada nustatoma, kurie reikalingi duomenys jau egzistuoja, gali būti išvesti arba turi būti pradėti registruoti.

Šiame etape sąmoningai:

- neprojektuojama galutinė techninė architektūra;
- nekuriamas dashboardas ar KPI rinkinys;
- nekoduojamas Product Engine funkcionalumas;
- nedaromi įrašai į Production Odoo;
- neapsimetama, kad trūkstamus istorinius įvykius galima patikimai atkurti retrospektyviai.

## Katalogo įrašo struktūra

Kiekvienas įrašas privalo turėti šias dalis:

1. vadybinis klausimas;
2. sprendimas, kurį atsakymas keičia;
3. sprendimo logika;
4. required data (reikalingi duomenys);
5. esami / išvedami / trūkstami duomenys;
6. būsimas Product Engine modulis.

Klausimas paliekamas kataloge tik tada, jei skirtingi jo atsakymai lemia skirtingą vadybinį veiksmą.

---

## Patvirtintas Furnibox vadybinių klausimų sąrašas

1. **Ar surenkamų užsakymų vėlavimą daugiausia lemia Assembly pajėgumo trūkumas, ar tai, kad užsakymai per vėlai tampa visiškai paruošti surinkimui?**
2. **Ar Assembly darbo metu nuolat turi pakankamą prioritetizuotą `READY FOR ASSEMBLY` eilę?**
3. **Kas ir kiek laiko neleidžia užsakymams tapti `READY FOR ASSEMBLY`: Furnix detalės, kliento fasadai ar stalčiai, rūšiavimas, komplektavimas, informacija, neteisingi prioritetai ar kita priežastis?**
4. **Kai Assembly turi paruoštų užsakymų, ar jis juos užbaigia tokiu tempu, kokio reikia pristatymo įsipareigojimams įvykdyti?**
5. **Kokius užsakymus Assembly turi surinkti šiandien, kad būtų apsaugoti artimiausi išsiuntimai ir didžiausias Throughput?**
6. **Kas konkrečiai mažina Assembly našų laiką, kai paruošto darbo eilė nėra tuščia?**
7. **Kiek laiku išsiunčiamų užsakymų ir Throughput prarandame dėl neparuošto darbo, o kiek – dėl nepakankamo Assembly pajėgumo?**
8. **Koks mažiausias pakeitimas greičiausiai padidintų surenkamų užsakymų Throughput: patikimesnis komponentų prieinamumas, geresnis komplektavimas ir prioritetai ar papildomas Assembly pajėgumas?**

Klausimai detalizuojami po vieną. Žemiau formalizuojamas MQ-001; kitų klausimų formuluotės laikomos patvirtinta katalogo apimtimi, bet jų sprendimo logika dar nespecifikuota.

---

## MQ-001 — Kas lemia surenkamų užsakymų vėlavimą?

### 1. Vadybinis klausimas

**Ar surenkamų užsakymų vėlavimą daugiausia lemia Assembly pajėgumo trūkumas, ar tai, kad užsakymai per vėlai tampa visiškai paruošti surinkimui?**

Klausimo laiko horizontas turi būti nurodomas kartu su atsakymu. Pradiniam diagnostikos etapui siūlomas slenkantis 3–4 savaičių stebėjimo langas po to, kai pradedami patikimai registruoti READY įvykiai. Atsakymas neturi būti išvedamas vien iš vėluojančių užsakymų skaičiaus ar darbuotojų užimtumo.

### 2. Sprendimas, kurį atsakymas keičia

| Atsakymas | Keičiamas vadybinis sprendimas ir veiksmas |
|---|---|
| **Assembly pajėgumas yra pagrindinė priežastis** | Apsaugoti ir maksimaliai išnaudoti Assembly: užtikrinti nuolatinę prioritetizuotą READY eilę, šalinti Assembly pajėgumo praradimus ir subordinuoti upstream Assembly ritmui; tik po išnaudojimo vertinti papildomą Assembly pajėgumą. |
| **Užsakymai per vėlai paruošiami Assembly** | Nedidinti Assembly pajėgumo vien dėl užsakymų vėlavimo. Spręsti komponentų, kliento tiekiamų fasadų / stalčių, Furnix detalių, komplektavimo, rūšiavimo, vidinės logistikos, informacijos arba prioritetų prieinamumą. |
| **Reikšmingos abi priežastys** | Atskirti prarastą laiką iki READY nuo laukimo po READY; pirmiausia šalinti priežastį, kuri labiau riboja laiku užbaigiamų užsakymų srautą. |
| **Signalo nepakanka** | Nepriimti pajėgumo investicijos sprendimo. Tęsti READY įvykių matavimą ir tikslinti būsenos apibrėžimą. |

### 3. Sprendimo logika

#### 3.1. Srauto modelis

Vertinamas surenkamų užsakymų srautas:

```text
užsakymo poreikis → upstream prieinamumas → READY FOR ASSEMBLY
                  → Assembly → tolesnis vykdymas → Shipped
```

`READY FOR ASSEMBLY` reiškia pirmą momentą, kai visi konkrečiam Assembly MO būtini komponentai fiziškai yra DC, įskaitant Furnix detales ir subrangovų atvežamus fasadus bei stalčius. Komponentai neprivalo būti iš anksto surūšiuoti, sukomplektuoti ar pristatyti į Assembly darbo vietą: nuo šio momento tokių vidinių veiksmų sukeltas laukimas jau priskiriamas procesui po READY. Vien Odoo rezervacija ar planuojamas pristatymas nėra fizinio buvimo DC įrodymas. Kadangi Furnibox Odoo nenaudoja pilno BOM ir jame neregistruojamas subrangovų fasadų bei stalčių fizinis gavimas, READY momento negalima patikimai apskaičiuoti vien iš dabartinių Odoo duomenų. Šiandien darbuotojai komponentų buvimą nustato vizualiai, kai fasadai ir stalčiai fiziškai atvežami į DC; todėl pradinis patikimas READY šaltinis turi būti rankinis patvirtinimas po fizinės patikros. READY būsenos savininkė ir už jos teisingumą atsakinga rolė yra gamybos vadovė; fizinę patikrą ji gali deleguoti, tačiau patvirtinimo audito įraše turi likti atsakingas asmuo. Patikra ir naujų READY būsenų patvirtinimas atliekami kiekvienos darbo dienos pradžioje, prieš nustatant tos dienos Assembly prioritetus.

Kasdienio patvirtinimo timestamp žymi pirmą patikrą, per kurią visas komplektas jau rastas DC, o ne tikslų paskutinio komponento atvykimo momentą. Todėl MQ-001 analizės laiko skiriamoji geba yra maždaug viena darbo diena; sistema neturi rodyti šio timestamp kaip tikslaus fizinio gavimo laiko.

Jei netinkamas komponentas nustatomas per rytinę patikrą iki Assembly pradžios, užsakymas nelaikomas READY, nes tinkamo komponento fiziškai nėra. Jei brokas ar kitas komponento netinkamumas nustatomas jau pradėjus Assembly, istorinis READY timestamp nekeičiamas: užsakymas yra WIP ir registruojamas kaip `ASSEMBLY BLOCKED` nuo sutrikimo pradžios iki jo pašalinimo. Šis praradimas analizuojamas MQ-006, o ne priskiriamas per vėlam pasiruošimui iki Assembly.

Odoo patikimai fiksuoja Assembly operacijos pradžios ir pabaigos momentus, o pradėta operacija gali būti sustabdyta. Sustabdant priežasties nurodyti neprivaloma. WO taip pat galima atskirai blokuoti nurodant blokavimo priežastį. Todėl būsenų seka yra: `NOT READY` → `READY, NOT STARTED` → `ASSEMBLY WIP ACTIVE` / `ASSEMBLY WIP PAUSED` / `ASSEMBLY WIP BLOCKED` → `ASSEMBLY COMPLETED`. BOM pateikia bendrą norminį operacijos laiką, tačiau operacija neskaidoma į dalines operacijas, todėl pradėto WIP likusios norminės valandos iš operacijos progreso patikimai neišvedamos. READY eilės svoriui iki operacijos pradžios naudojama visa BOM norminė trukmė; WIP rodomas atskirai. Sustabdymo ir atnaujinimo momentai naudojami aktyviam operacijos laikui atskirti nuo neaktyvaus WIP laiko, tačiau paprasta pauzė be priežasties negali būti priskirta konkrečiam blokatoriui.

#### 3.2. Diagnostikos signalai

Sprendimo procedūra turi vertinti ne vieną tašką, o eilių dydžio, senėjimo ir užbaigimo dinamiką per pasirinktą laiko langą.

| Stebimas raštas | Klasifikacija |
|---|---|
| Prieš Assembly nuolat yra prioritetizuoto paruošto darbo eilė, ji sensta arba auga, o Assembly užbaigimo tempas neleidžia vykdyti pristatymo įsipareigojimų. | **Assembly pajėgumo trūkumo kandidatas.** |
| Užsakymai vėluoja, bet Assembly READY eilė darbo metu dažnai tuščia arba per maža stabiliam darbui; didžioji laukimo dalis susidaro iki `READY FOR ASSEMBLY`. | **Per vėlaus paruošimo / upstream prieinamumo kandidatas.** |
| READY eilė dalį laiko badauja, o kitu metu sistemingai sensta; abi priežastys turi reikšmingą poveikį išsiuntimams. | **Mišri priežastis.** |
| Duomenų kokybė neleidžia patikimai atskirti laukimo iki READY nuo laukimo po READY. | **Nepakankamas signalas.** |

Constraint klasifikacija laikoma pakankama vadybiniam sprendimui tik tada, kai signalas kartojasi per sutartą langą ir alternatyvi hipotezė nėra geriau paaiškinama trūkstamu READY įvykiu. Pradinės kiekybinės ribos (pvz., eilės dienos, stebėjimų dalis, seniausio darbo amžius) turi būti kalibruojamos iš pirmųjų 3–4 savaičių patikimų duomenų; jų negalima iš anksto pateikti kaip empirinio fakto.

#### 3.3. Apsaugos nuo klaidingos išvados

- Assembly užsakymų vėlavimas pats savaime neįrodo, kad Assembly yra constraint.
- Darbas, kuriam trūksta bet kurio būtino komponento, nepriklauso Assembly READY eilei.
- Žemas lokalus utilization neįrodo perteklinio pajėgumo, o aukštas utilization neįrodo sistemos constraint.
- Packaging šiame klausime nelaikomas aktyvia constraint hipoteze: pagal patvirtintą Furnibox situaciją surinkti užsakymai prieš Packaging sistemingai nesikaupia.
- Istorinis `READY FOR ASSEMBLY` momentas negali būti patikimai atkurtas iš dabartinių Odoo duomenų; retrospektyvinė išvada turi būti žymima kaip nepatikima, o ne pateikiama kaip faktas.
- Constraint yra sistemos savybė pasirinktame laiko lange, ne nuolatinė darbo centro etiketė.

### 4. Required data (reikalingi duomenys)

Minimalus sprendimo procedūros duomenų rinkinys vienam užsakymui / darbui:

| Duomuo | Paskirtis |
|---|---|
| Surenkamo užsakymo ir Assembly MO stabilūs identifikatoriai | Susieti vieno klientų poreikio būsenas iki READY ir po jo. |
| Pažadėta / planuota išsiuntimo data | Nustatyti Throughput riziką ir eilės prioritetą. |
| `READY FOR ASSEMBLY` timestamp ir būsenos versija | Nustatyti, kada darbas realiai pateko į Assembly valdomą eilę. |
| Odoo fiksuojami Assembly operacijos pradžios ir užbaigimo timestamp | Matuoti laukimą po READY, patikimai atskirti nepradėtą eilę nuo WIP ir nustatyti užbaigimo tempą. Pradžios–pabaigos intervalas savaime nelaikomas grynu našiu darbo laiku. |
| Assembly operacijos sustabdymo ir atnaujinimo įvykiai | Atskirti aktyviai vykdomą operaciją nuo sustabdyto WIP ir nevertinti viso pradžios–pabaigos intervalo kaip darbo laiko; priežastis gali būti nežinoma. |
| WO blokavimo pradžia, pabaiga ir nurodyta priežastis | Atskirti aiškiai užblokuotą WIP nuo paprastos pauzės ir vėliau analizuoti konkrečius Assembly srauto trikdžius. |
| Packed / shipped timestamp | Susieti operacinį srautą su laiku realizuotu išsiuntimu. |
| Standartinės Assembly darbo valandos, apskaičiuotos iš BOM operacijų laikų | Palyginti nevienodo dydžio darbus ir READY eilę išreikšti laukiančiu Assembly darbo krūviu, o ne vien MO skaičiumi. |
| READY būsenos atšaukimas ir priežastis, jei iki Assembly pradžios nustatomas klaidingas patvirtinimas | Išlaikyti teisingą eilės istoriją ir duomenų auditą neperrašant pradinio įvykio. |
| `ASSEMBLY BLOCKED` pradžios, pabaigos ir priežasties įvykiai | Atskirti po Assembly pradžios užblokuotą WIP nuo vėlavimo iki READY. |
| Snapshot / event timestamp | Atkurti eilės dydį ir amžių bet kuriuo stebėjimo momentu. |

Papildomi, bet ne pradinės klasifikacijos būtini duomenys:

- darbo grafikai ir realiai prieinamos Assembly valandos;
- svarbiausių pajėgumo praradimų kategorijos;
- Throughput eurais vienam užsakymui ar prioritetui;
- komponento ar proceso tipas, blokavęs READY būseną.

Šie duomenys reikalingi vėlesniems klausimams „kiek Throughput prarandame?“ ir „kas neleidžia geriau išnaudoti constraint?“, tačiau jų trūkumas neturi sustabdyti pradinio READY eilių stebėjimo.

### 5. Esami / išvedami / trūkstami duomenys

Prieš implementaciją visi laukai turi būti patikrinti prieš faktinę Furnibox Odoo schemą tik skaitymo režimu. Žemiau pateiktas pradinis duomenų kontraktas, o ne teiginys, kad visi pažymėti laukai jau tikrai tinkami.

#### Esami arba tikėtina, kad esami Odoo duomenys — būtina validuoti

- Sales Order / Manufacturing Order ir jų identifikatoriai bei sąsajos;
- užsakymo planuotos arba pažadėtos datos;
- MO būsenos ir užbaigimo datos;
- Furnix ir kitų Odoo apskaitomų komponentų atsargų judėjimai bei rezervacijos, tačiau ne visas faktinis Assembly komponentų rinkinys;
- pakavimo / pristatymo operacijų būsenos ir užbaigimo datos;
- produktų kiekiai ir maršrutai.

#### Išvedami duomenys — tik patvirtinus šaltinių semantiką

- dabartinė READY eilė, jos dydis, amžius ir seniausias darbas;
- savaitinis įėjimo į eilę ir užbaigimo tempas;
- surenkamų užsakymų laukimo iki READY ir po READY palyginimas.

#### Kritiškai trūkstami duomenys

- patikimas istorinis ir nuo šiol registruojamas `READY FOR ASSEMBLY` timestamp;
- atskiras rankinis `READY FOR ASSEMBLY` patvirtinimo įvykis po vizualios komponentų patikros, nes dabartinis Odoo neturi pilno BOM ir neregistruoja subrangovų fasadų bei stalčių fizinio gavimo DC;
- patikimas šio įvykio timestamp, užsakymo / Assembly MO identifikatorius ir patvirtinęs asmuo arba šaltinis;
- `ASSEMBLY BLOCKED` įvykis darbui, kuris po Assembly pradžios tampa nebetęsiamas; tokiu atveju istorinis READY įvykis neatšaukiamas;
- WIP likusio darbo įvertinimo taisyklė, jei jos vėliau reikės, nes bendros Assembly operacijos neskaidomos į dalines operacijas; MQ-001 pradžioje WIP rodomas atskirai, nepriskiriant jam tariamai tikslių likusių valandų.

**Duomenų spraga, dėl kurios šiandien negalimas patikimas retrospektyvus atsakymas:** Furnibox Odoo nenaudojamas pilnas BOM, o kliento fasadų ir stalčių fizinis gavimas DC jame neregistruojamas. Todėl iš Odoo negalima nustatyti pirmo momento, kai konkrečiam Assembly MO vienu metu fiziškai buvo prieinami visi reikalingi komponentai. Istoriniai vėlavimai negali patikimai atskirti Assembly pajėgumo trūkumo nuo Assembly badavimo dėl upstream prieinamumo.

### 6. Būsimas Product Engine modulis

Darbinis modulio pavadinimas: **TOC Constraint Diagnostic**.

Modulio atsakomybė — vykdyti formalizuotą sprendimo procedūrą ir pateikti ne vien žalius KPI, o audituojamą atsakymą:

```text
Vertinimo langas: 2026-XX-XX – 2026-XX-XX
Išvada: Assembly pajėgumas / Per vėlus paruošimas / Mišri priežastis / Nepakanka duomenų
Pasitikėjimas: aukštas / vidutinis / žemas
Sprendimą pagrindžiantys signalai: ...
Duomenų spragos ir alternatyvios hipotezės: ...
Rekomenduojamas vadybinis veiksmas: ...
```

Numatomos, bet dar neprojektuojamos produkto architektūros dalys:

1. **Event / Readiness Contract** — READY būsenų semantika, versijavimas ir auditas.
2. **Flow Timeline** — vieno surenkamo užsakymo įvykių seka iki READY, per Assembly ir iki išsiuntimo.
3. **Buffer Control** — READY eilių dydis, amžius, įėjimo ir išėjimo tempas.
4. **Constraint Classifier** — sprendimo taisyklės, alternatyvių hipotezių ir duomenų kokybės patikra.
5. **Decision Output** — išvada, paaiškinimas ir konkretus veiksmas vadovui.
6. **What-if** (vėlesnis etapas) — poveikio modeliavimas pakeitus Assembly pajėgumą arba upstream paruošimo patikimumą.

Modulio projektavimas ir implementavimas pradedamas tik patvirtinus MQ-001 sprendimo logiką bei READY būsenų verslo apibrėžimus.

## Atviri patvirtinimo klausimai

1. Kokiomis aplinkybėmis darbuotojai turi naudoti WO blokavimą su priežastimi, o kada pakanka paprasto operacijos sustabdymo?
2. Koks vadybinio sprendimo ritmas: kasdienė kontrolė, savaitinė constraint peržiūra ar abu?
3. Kiek savaičių duomenų ir kokio signalo stabilumo reikia prieš priimant pajėgumo investicijos sprendimą?

## Kitas specifikacijos etapas

Patvirtinti MQ-001 sprendimo logiką ir `READY FOR ASSEMBLY` verslo apibrėžimą. Tada ta pačia pilna struktūra formalizuoti MQ-002, nekeičiant patvirtinto aštuonių klausimų sąrašo be naujo verslo aptarimo.
