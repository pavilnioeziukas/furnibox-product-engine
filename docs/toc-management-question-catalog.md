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
7. **Kiek laiku realizuojamo Throughput atidedame dėl neparuošto darbo, o kiek – dėl nepakankamo Assembly pajėgumo?**
8. **Koks mažiausias pakeitimas greičiausiai labiausiai padidintų laiku realizuojamą surenkamų užsakymų Throughput: patikimesnis komponentų prieinamumas, geresnis komplektavimas ir prioritetai ar papildomas Assembly pajėgumas?**

Visų aštuonių klausimų sprendimo logika formalizuota šiame kataloge. Kalibruotini dydžiai ir techniškai validuotini duomenų ryšiai pažymėti prie konkrečių klausimų; jų negalima pateikti kaip jau patvirtintų faktų.

---

## MQ-001 — Kas lemia surenkamų užsakymų vėlavimą?

### 1. Vadybinis klausimas

**Ar surenkamų užsakymų vėlavimą daugiausia lemia Assembly pajėgumo trūkumas, ar tai, kad užsakymai per vėlai tampa visiškai paruošti surinkimui?**

Klausimo laiko horizontas turi būti nurodomas kartu su atsakymu. Pradiniam diagnostikos etapui siūlomas slenkantis 3–4 savaičių stebėjimo langas po to, kai pradedami patikimai registruoti READY įvykiai. Atsakymas neturi būti išvedamas vien iš vėluojančių užsakymų skaičiaus ar darbuotojų užimtumo.

### 2. Sprendimas, kurį atsakymas keičia

| Atsakymas | Keičiamas vadybinis sprendimas ir veiksmas |
|---|---|
| **Assembly pajėgumas yra pagrindinė priežastis** | Apsaugoti ir maksimaliai išnaudoti Assembly: užtikrinti nuolatinę prioritetizuotą READY eilę, šalinti Assembly pajėgumo praradimus ir subordinuoti upstream Assembly ritmui; tik po išnaudojimo vertinti papildomą Assembly pajėgumą. |
| **Užsakymai per vėlai paruošiami Assembly** | Nedidinti Assembly pajėgumo vien dėl užsakymų vėlavimo. Spręsti komponentų, subrangovų tiekiamų fasadų / stalčių, Furnix detalių, komplektavimo, rūšiavimo, vidinės logistikos, informacijos arba prioritetų prieinamumą. |
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

Naudojimo taisyklė: jei darbo negalima tęsti dėl realaus trukdžio — pavyzdžiui, trūkstamos ar brokuotos detalės, informacijos, įrankio arba kitos nenormalios sąlygos — WO blokuojamas ir privalomai nurodoma priežastis. Paprastas operacijos sustabdymas naudojamas normalioms pertraukoms ir darbo dienos pabaigai. Šių įvykių paskirtis neturi būti maišoma.

#### 3.2. Diagnostikos signalai

Sprendimo procedūra turi vertinti ne vieną tašką, o eilių dydžio, senėjimo ir užbaigimo dinamiką per pasirinktą laiko langą.

| Stebimas raštas | Klasifikacija |
|---|---|
| Prieš Assembly nuolat yra prioritetizuoto paruošto darbo eilė, ji sensta arba auga, o Assembly užbaigimo tempas neleidžia vykdyti pristatymo įsipareigojimų. | **Assembly pajėgumo trūkumo kandidatas.** |
| Užsakymai vėluoja, bet Assembly READY eilė darbo metu dažnai tuščia arba per maža stabiliam darbui; didžioji laukimo dalis susidaro iki `READY FOR ASSEMBLY`. | **Per vėlaus paruošimo / upstream prieinamumo kandidatas.** |
| READY eilė dalį laiko badauja, o kitu metu sistemingai sensta; abi priežastys turi reikšmingą poveikį išsiuntimams. | **Mišri priežastis.** |
| Duomenų kokybė neleidžia patikimai atskirti laukimo iki READY nuo laukimo po READY. | **Nepakankamas signalas.** |

Constraint klasifikacija laikoma pakankama vadybiniam sprendimui tik tada, kai signalas kartojasi per sutartą langą ir alternatyvi hipotezė nėra geriau paaiškinama trūkstamu READY įvykiu. Pradinės kiekybinės ribos (pvz., eilės dienos, stebėjimų dalis, seniausio darbo amžius) turi būti kalibruojamos iš pirmųjų 3–4 savaičių patikimų duomenų; jų negalima iš anksto pateikti kaip empirinio fakto.

Vadybinis ritmas:

- kiekvienos darbo dienos pradžioje atliekama READY patikra, sudaroma Assembly prioritetų eilė ir peržiūrimi blokuoti WO;
- kartą per savaitę vertinama, ar surenkamų užsakymų vėlavimą daugiausia lemia per vėlai paruošiami užsakymai, ar Assembly pajėgumas;
- pirmoji MQ-001 išvada formuluojama sukaupus 3–4 savaites patikimų READY ir Assembly operacijų duomenų; iki tol rezultatas žymimas kaip preliminarus.

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

Šie duomenys reikalingi vėlesniems klausimams „kiek laiku realizuojamo Throughput atidedame?“ ir „kas neleidžia geriau išnaudoti constraint?“, tačiau jų trūkumas neturi sustabdyti pradinio READY eilių stebėjimo.

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

MQ-001 sprendimo logika ir pradinis READY būsenos verslo apibrėžimas yra patvirtinti. Vien šio klausimo patvirtinimas neautorizuoja funkcionalumo implementacijos; architektūra formuluojama tik remiantis užbaigtu visų klausimų duomenų ir sprendimų kontraktu.

## MQ-001 likusios kalibravimo užduotys

1. Iš pirmųjų 3–4 savaičių duomenų nustatyti signalų stabilumo ribas, reikalingas prieš priimant pajėgumo investicijos sprendimą.
2. Patikrinti, ar sutartos WO `PAUSED` ir `BLOCKED` naudojimo taisyklės praktiškai taikomos nuosekliai.

---

## MQ-002 — Ar Assembly turi pakankamą READY eilę?

### 1. Vadybinis klausimas

**Ar Assembly darbo metu nuolat turi pakankamą prioritetizuotą `READY FOR ASSEMBLY` eilę?**

„Pakankama“ reiškia ne kuo didesnę eilę, o mažiausią paruošto darbo bufferį, kuris apsaugo Assembly nuo badavimo dėl normalių kasdienių komponentų gavimo ir užsakymų paruošimo svyravimų.

### 2. Sprendimas, kurį atsakymas keičia

| Atsakymas | Keičiamas vadybinis sprendimas ir veiksmas |
|---|---|
| **Bufferis raudonoje zonoje** | Skubiai ruošti ir patvirtinti kitus artimiausio prioriteto užsakymus; eskaluoti komponentų prieinamumo kliūtis, galinčias palikti Assembly be darbo. |
| **Bufferis geltonoje zonoje** | Tą pačią dieną valdyti artimiausių užsakymų paruošimą, kad bufferis nepasiektų raudonos zonos. |
| **Bufferis žalioje zonoje** | Assembly artimiausiam laikotarpiui apsaugotas; nevykdyti papildomo skubinimo vien bufferio didinimo tikslu. |
| **Bufferis nuolat gerokai viršija tikslą ir sensta** | Nevertinti to kaip automatiškai gero rezultato. Tikrinti Assembly pajėgumą, prioritetų kokybę ir per anksti READY pažymėtų darbų kaupimąsi. |

### 3. Sprendimo logika

Pradinis tikslinis READY bufferis yra **2 Assembly darbo dienos**, išreikštos standartinėmis BOM Assembly operacijų valandomis.

Jei planuojamas arba patikimai demonstruojamas Assembly dienos pajėgumas yra `C` standartinių valandų, pradinis zonų modelis yra:

Pradiniame etape `C` skaičiuojamas kaip per rytinę patikrą gamybos vadovės įvestas tą dieną dirbančių Assembly darbuotojų skaičius, padaugintas iš 8 valandų. Assembly darbuotojai visą savo planuojamą laiką dirba tik surinkime, todėl papildomas laiko paskirstymo kitiems darbams koeficientas netaikomas. Darbuotojų prieinamumas šiuo metu žinomas tik gamybos vadovei ir Odoo nefiksuojamas. BOM Assembly operacijos laikas nustatytas vienam gaminiui, darant prielaidą, kad jį renka vienas darbuotojas; todėl viena BOM norminė valanda tiesiogiai atitinka vieną standartinę žmogaus Assembly valandą ir gali būti lyginama su `C`.

| Zona | READY, NOT STARTED standartinės valandos | Interpretacija |
|---|---:|---|
| **Raudona** | `< 1 × C` | Mažiau nei viena darbo diena; reikšminga Assembly badavimo rizika. |
| **Geltona** | `≥ 1 × C` ir `< 2 × C` | Viena–dvi darbo dienos; reikia aktyviai užtikrinti kitų darbų paruošimą. |
| **Žalia** | `≥ 2 × C` | Bent dvi darbo dienos; Assembly apsaugotas nuo artimiausių normalių svyravimų. |

Pavyzdys: jei Assembly dienos pajėgumas yra 24 standartinės valandos, pradinis tikslas yra 48 READY valandos; raudona zona yra mažiau nei 24 val., geltona – 24–48 val., žalia – bent 48 val.

Į bufferį įtraukiami tik `READY, NOT STARTED` darbai. `ASSEMBLY WIP ACTIVE`, `PAUSED` ir `BLOCKED` rodomi atskirai ir nedidina apsaugos nuo naujo darbo trūkumo. Eilė turi būti prioritetizuota pagal patvirtintą dienos seką; vien valandų suma be vykdomos prioritetų tvarkos nelaikoma pakankama apsauga.

Pradinis 2 dienų bufferis nėra nuolatinė norma. Jis kalibruojamas po 3–4 savaičių:

- jei Assembly pritrūksta READY darbo, reikia didinti apsaugą arba gerinti upstream paruošimo patikimumą;
- jei READY eilė nuolat gerokai viršija 2 dienas ir darbai sensta, tikslas arba darbų paleidimo taisyklė gali būti per dideli, arba Assembly pajėgumas yra pagrindinis srauto apribojimas;
- jei bufferis dažniausiai laikosi tarp 1 ir 2 dienų ir Assembly nebadauja, pradinis dydis laikomas tinkamu;
- bufferio dydis keičiamas tik pagal pasikartojantį signalą, o ne dėl vienos neįprastos dienos.

### 4. Required data (reikalingi duomenys)

| Duomuo | Paskirtis |
|---|---|
| Kasdienio READY patvirtinimo timestamp | Nustatyti, kurie darbai patenka į rytinį bufferį. |
| Assembly operacijos pradžios timestamp | Pašalinti pradėtą darbą iš `READY, NOT STARTED` bufferio. |
| Kiekvieno READY darbo standartinės BOM Assembly valandos | Susumuoti nevienodo dydžio darbų bufferį. |
| Assembly dienos pajėgumas standartinėmis valandomis | READY valandas paversti darbo dienų apsauga ir nustatyti zonų ribas. |
| Dienos Assembly prioritetų seka | Patikrinti, ar bufferį sudaro realiai vykdytini ir tinkama tvarka sudėti darbai. |
| Assembly badavimo įvykis arba laikotarpis | Patikrinti, ar nustatytas bufferio dydis realiai apsaugo srautą. |
| READY darbo amžius | Aptikti per didelę arba senstančią eilę. |

### 5. Esami / išvedami / trūkstami duomenys

#### Esami arba jau sutarti

- BOM Assembly operacijų norminiai laikai;
- Odoo Assembly operacijos pradžios ir pabaigos momentai;
- kartą per dieną gamybos vadovės patvirtinamas `READY FOR ASSEMBLY` įvykis;
- WO `PAUSED` ir `BLOCKED` būsenos.

#### Išvedami

- `READY, NOT STARTED` standartinių valandų suma;
- READY bufferio padėtis raudonoje, geltonoje arba žalioje zonoje;
- bufferio dydis Assembly darbo dienomis;
- READY eilės seniausio darbo amžius ir bufferio dinamika;
- Assembly badavimo dažnis, jei badavimo taisyklė formalizuota.

#### Trūkstami arba kalibruotini

- gamybos vadovės per rytinę patikrą įvedamas dirbančių Assembly darbuotojų skaičius; `C = darbuotojų skaičius × 8 val.`;
- aiški Assembly badavimo įvykio registravimo arba išvedimo taisyklė;
- MQ-005 apibrėžta dienos prioritetų sudarymo taisyklė, kurią reikia techniškai realizuoti ir validuoti;
- po 3–4 savaičių patvirtintos galutinės bufferio zonų ribos.

### 6. Būsimas Product Engine modulis

MQ-002 naudos būsimo **TOC Constraint Diagnostic** modulio dalį **Assembly Ready Buffer Control**. Ji turės pateikti:

```text
Assembly dienos pajėgumas: C standartinių valandų
READY, NOT STARTED: X standartinių valandų / Y darbo dienų
Bufferio zona: RED / YELLOW / GREEN
Seniausias READY darbas: ...
Artimiausia badavimo rizika: ...
Rekomenduojamas veiksmas šiandien: ...
```

Modulis neturi skatinti kaupti kuo daugiau READY darbo. Jo paskirtis – palaikyti mažiausią bufferį, kuris apsaugo Assembly, ir iš anksto signalizuoti apie badavimo riziką.

---

## MQ-003 — Kas neleidžia užsakymams tapti READY?

### 1. Vadybinis klausimas

**Kas ir kiek laiko neleidžia užsakymams tapti `READY FOR ASSEMBLY`: Furnix detalės, subrangovo fasadai ar stalčiai, kiti komponentai, fizinis suradimas, identifikavimas ar kita priežastis?**

Klausimas turi parodyti ne bendrą vėluojančių užsakymų skaičių, o konkrečius aktyvius blokatorius, jų trukmę, paveiktas standartines Assembly valandas ir poveikį artimiausiam READY bufferiui.

### 2. Sprendimas, kurį atsakymas keičia

| Atsakymas | Keičiamas vadybinis sprendimas ir veiksmas |
|---|---|
| **Dominuoja Furnix detalių trūkumas** | Eskaluoti Furnix tiekimo, užsakymo, gamybos arba pristatymo patikimumą ir pirmiausia spręsti tuos trūkumus, kurie kelia READY bufferio badavimo riziką. |
| **Dominuoja subrangovo fasadų ar stalčių trūkumas** | Keisti subrangovų pristatymo kontrolę, patvirtinimus ir prioritetus pagal būsimą Assembly poreikį. |
| **Dominuoja kitų perkamų komponentų trūkumas** | Keisti pirkimo ir gavimo prioritetus pagal Assembly bufferio riziką, o ne vien bendrą vėlavimo datą. |
| **Komponentai DC, bet nerandami ar neidentifikuojami** | Spręsti fizinio srauto, žymėjimo, lokacijų, priėmimo ar užsakymo priskyrimo procesą; nelaikyti problemos tiekėjo pajėgumo trūkumu. |
| **Priežastys mišrios** | Prioritetizuoti pagal prarandamas Assembly standartines valandas, blokavimo trukmę ir artimiausių išsiuntimų riziką. |
| **Priežastis nežinoma** | Tą pačią dieną išsiaiškinti ir perklasifikuoti; „kita“ negali tapti nuolatine dominuojančia kategorija. |

### 3. Sprendimo logika

Kiekvienos darbo dienos pradžioje per READY patikrą kiekvienam surenkamam užsakymui taikoma ši seka:

1. Jei visi būtini komponentai fiziškai yra DC, užsakymas pažymimas `READY FOR ASSEMBLY`.
2. Jei bent vieno būtino komponento nėra arba jo neįmanoma patikimai surasti / priskirti, užsakymas lieka `NOT READY`.
3. `NOT READY` užsakymui pažymima viena ar kelios aktyvios blokavimo priežastys.
4. Kiekviena priežastis turi pirmos aptikimo patikros timestamp ir pašalinimo patikros timestamp.
5. Kai pašalinamos visos aktyvios priežastys, užsakymas kitos patikros metu tampa READY.

Patvirtintas pradinis priežasčių katalogas:

| Kodas | Priežastis |
|---|---|
| `FURNIX_PARTS_MISSING` | Trūksta Furnix detalių. |
| `SUBCONTRACTOR_FRONTS_MISSING` | Neatvežti subrangovo fasadai. |
| `SUBCONTRACTOR_DRAWERS_MISSING` | Neatvežti subrangovo stalčiai. |
| `OTHER_PURCHASED_COMPONENTS_MISSING` | Trūksta kitų perkamų komponentų. |
| `COMPONENTS_NOT_FOUND` | Komponentai laikomi esančiais DC, bet jų nepavyksta fiziškai rasti. |
| `COMPONENT_ORDER_UNKNOWN` | Neaišku, kuriam užsakymui skirti atvežti komponentai. |
| `OTHER` | Kita priežastis; privalomas trumpas komentaras. |

Vienam užsakymui leidžiamos kelios vienu metu aktyvios priežastys. Bendra užsakymo NOT READY trukmė negali būti skaičiuojama sudedant persidengiančias priežasčių trukmes. Atskirai rodoma:

- kiek kalendorinių / darbo dienų užsakymas iš viso buvo NOT READY;
- kiek dienų buvo aktyvi kiekviena priežastis;
- kiek užsakymų ir standartinių Assembly valandų kiekviena priežastis blokavo;
- kuri priežastis buvo paskutinė pašalinta prieš READY momentą.

Prioritetas priežasčiai suteikiamas ne vien pagal atvejų skaičių. Aukščiausias dėmesys skiriamas blokatoriui, kuris kelia didžiausią riziką READY bufferiui ir artimiausiems išsiuntimams.

### 4. Required data (reikalingi duomenys)

| Duomuo | Paskirtis |
|---|---|
| Užsakymo ir Assembly MO identifikatoriai | Susieti blokatorių su konkrečiu darbu. |
| NOT READY priežasties kodas | Grupavimas ir vadybinio veiksmo parinkimas. |
| Priežasties pirmo aptikimo timestamp | Nustatyti blokavimo pradžią dienos tikslumu. |
| Priežasties pašalinimo timestamp | Nustatyti trukmę ir patvirtinti, kad kliūtis nebeaktyvi. |
| Patvirtinusi gamybos vadovė / deleguotas tikrintojas | Auditas ir duomenų patikimumas. |
| Komentaras kategorijai `OTHER` | Neleisti nežinomoms priežastims pasislėpti bendroje kategorijoje. |
| Užsakymo standartinės Assembly valandos | Įvertinti blokuojamo būsimo Assembly darbo svorį. |
| Pažadėta išsiuntimo data ir dienos prioritetas | Įvertinti pristatymo bei bufferio riziką. |
| READY timestamp | Uždaryti NOT READY intervalą, kai pašalinamos visos priežastys. |

### 5. Esami / išvedami / trūkstami duomenys

#### Esami arba jau sutarti

- užsakymo ir Assembly MO identifikatoriai;
- BOM Assembly operacijų norminės valandos;
- kiekviename Sales Order esantis `Delivery Date`, reiškiantis datą, kada užsakymas turi būti išsiųstas iš Furnibox;
- kasdienė gamybos vadovės READY patikra.

#### Išvedami

- bendra užsakymo NOT READY trukmė;
- aktyvių priežasčių trukmė nepersidengiančiais intervalais ir pagal atskiras kategorijas;
- kiekvienos priežasties paveiktų užsakymų bei Assembly standartinių valandų suma;
- paskutinė kliūtis, kurios pašalinimas leido užsakymui tapti READY;
- priežasčių poveikis prognozuojamam READY bufferiui.

#### Trūkstami

- rankinis NOT READY priežasties atidarymo ir uždarymo įvykis;
- galimybė vienam užsakymui pažymėti kelias vienu metu aktyvias priežastis;
- privalomas komentaras kategorijai `OTHER`;
- duomenų kokybės kontrolė, aptinkanti NOT READY užsakymus be aktyvios priežasties.

### 6. Būsimas Product Engine modulis

MQ-003 naudos būsimo **TOC Constraint Diagnostic** modulio dalį **Readiness Blocker Control**. Ji turės pateikti:

```text
Aktyvūs NOT READY užsakymai: ...
Blokuojamos Assembly standartinės valandos: ...
READY bufferiui gresiantys užsakymai: ...
Dominuojanti priežastis pagal valandas / trukmę / išsiuntimo riziką: ...
Seniausi neišspręsti blokatoriai: ...
Rekomenduojamas eskalavimo veiksmas šiandien: ...
```

Modulis turi leisti nuo agreguotos priežasties pereiti iki konkrečių užsakymų ir jų audito įvykių. Jis neturi bandyti retrospektyviai išgalvoti istorinių priežasčių iš nepilno Odoo BOM.

---

## MQ-004 — Ar Assembly užbaigia darbus reikiamu tempu?

### 1. Vadybinis klausimas

**Kai Assembly turi paruoštų užsakymų, ar jis juos užbaigia tokiu tempu, kokio reikia SO `Delivery Date` įsipareigojimams įvykdyti?**

SO `Delivery Date` reiškia datą, kada užsakymas turi būti išsiųstas iš Furnibox. Tarp Assembly pabaigos ir Packaging nėra nustatyto privalomo laiko tarpo: pakuotojai gali pradėti pakuoti iš karto užbaigus surinkimą. Todėl pradiniame dienos tikslumo modelyje Assembly operacija laikoma užbaigta laiku, jei ji užbaigta ne vėliau kaip SO `Delivery Date`. Dirbtinis papildomas Packaging rezervas netaikomas; taisyklė kalibruojama tik atsiradus faktiniams tos pačios dienos išsiuntimo vėlavimams.

### 2. Sprendimas, kurį atsakymas keičia

| Atsakymas | Keičiamas vadybinis sprendimas ir veiksmas |
|---|---|
| **Tempas pakankamas** | Nedidinti Assembly pajėgumo vien dėl pavienių vėlavimų; saugoti READY bufferį ir patvirtintą prioritetų seką. |
| **Tempas nepakankamas, nors READY darbo ir planinių valandų pakanka** | Analizuoti aktyvaus laiko praradimus, WO blokavimus, normų tikslumą, darbo seką ir realų Assembly pajėgumą; tik išnaudojus esamą pajėgumą svarstyti jo didinimą. |
| **Reikiamas tempas viršija turimą planinį pajėgumą** | Perplanuoti pajėgumą, prioritetus ar pažadus; įvertinti papildomas Assembly valandas / darbuotojus ir ekonominį poveikį. |
| **Tempas mažas, nes trūko READY darbo** | Nepriskirti nuostolio Assembly pajėgumui; spręsti MQ-002 bufferio ir MQ-003 paruošimo priežastis. |
| **Bendras tempas pakankamas, bet vėluoja prioritetiniai SO** | Taisyti darbų seką ir MQ-005 prioritetų taisyklę, o ne automatiškai didinti bendrą pajėgumą. |

### 3. Sprendimo logika

Vertinimas atliekamas kasdien operacinei kontrolei ir kartą per savaitę stabiliai tendencijai nustatyti.

Pagrindiniai dydžiai:

- **Planuotas pajėgumas (`C`)** – suplanuotų Assembly darbuotojų darbo valandų suma.
- **Užbaigtas standartinis darbas** – per laikotarpį užbaigtų Assembly operacijų BOM norminių valandų suma.
- **Reikalingas tempas** – Assembly standartinės valandos, kurias pagal SO `Delivery Date` būtina užbaigti pasirinktame laikotarpyje.
- **READY prieinamumas** – ar vertinamu darbo metu buvo pakankamai `READY, NOT STARTED` darbo.
- **Pajėgumo vykdymas** – užbaigto standartinio darbo santykis su planiniu pajėgumu, interpretuojamas tik kartu su READY prieinamumu, WIP, pauzėmis ir blokavimais.
- **Paklausos apkrova** – reikalingo tempo santykis su planiniu pajėgumu.

Klasifikavimo logika:

| Stebimas raštas | Išvada |
|---|---|
| READY bufferis pakankamas, užbaigtos standartinės valandos atitinka reikalingą tempą, prioritetiniai SO užbaigiami iki `Delivery Date`. | **Assembly tempas pakankamas.** |
| READY bufferis pakankamas, tačiau užbaigtos standartinės valandos sistemingai mažesnės už reikalingą tempą, READY eilė auga ar sensta. | **Assembly vykdymo arba pajėgumo problema.** |
| Reikalingos standartinės valandos sistemingai viršija planinį `C`, net jei esamas darbas vykdomas pagal normą. | **Nominalus Assembly pajėgumo trūkumas.** |
| Užbaigtas tempas mažas tomis dienomis, kai READY bufferis buvo raudonas arba tuščias. | **Upstream badavimas; ne Assembly pajėgumo įrodymas.** |
| Bendrai užbaigtų valandų pakanka, bet praleidžiami artimiausio `Delivery Date` darbai. | **Prioritetų / sekos problema.** |

Vienos dienos nuokrypis nėra pakankamas pajėgumo sprendimui. Savaitinė išvada remiasi pasikartojančiu raštu, o pirmoji pajėgumo hipotezė vertinama kartu su MQ-001 po 3–4 savaičių patikimų duomenų.

### 4. Required data (reikalingi duomenys)

| Duomuo | Paskirtis |
|---|---|
| SO `Delivery Date` | Nustatyti išsiuntimo įsipareigojimą ir reikiamą Assembly užbaigimo terminą. |
| SO, MO ir WO sąsajos | Priskirti Assembly darbą konkrečiam išsiuntimo įsipareigojimui. |
| BOM norminės Assembly valandos | Išreikšti poreikį ir užbaigtą darbą vienodu žmogaus valandų matu. |
| Assembly operacijos pradžios ir pabaigos timestamp | Nustatyti WIP ir faktinę užbaigimo dieną. |
| Dienos planinis Assembly pajėgumas `C` | Palyginti reikiamą ir galimą tempą. |
| Kasdienis READY bufferis | Atskirti pajėgumo trūkumą nuo darbo badavimo. |
| WO `PAUSED` ir `BLOCKED` intervalai bei blokavimo priežastys | Paaiškinti neužbaigtą pajėgumą, kai darbo buvo. |
| Dienos prioritetų seka | Patikrinti, ar laiku vykdyti svarbiausi SO. |
| Faktinis išsiuntimo timestamp | Patikrinti, ar tos pačios dienos Assembly pabaiga praktiškai leido išsiųsti pagal `Delivery Date`. |

### 5. Esami / išvedami / trūkstami duomenys

#### Esami arba jau sutarti

- kiekvieno SO `Delivery Date` – planuojama išsiuntimo iš Furnibox data;
- BOM Assembly operacijų laikas vienam gaminiui, atitinkantis vieno darbuotojo standartines valandas;
- Odoo WO pradžios, pabaigos, pauzės ir blokavimo įvykiai;
- Assembly darbuotojai planiniu darbo metu dirba tik surinkime;
- pakuotojai gali pradėti pakuoti iš karto užbaigus Assembly.

#### Išvedami

- kasdien ir kas savaitę užbaigtos standartinės Assembly valandos;
- pagal `Delivery Date` reikalingos standartinės valandos;
- planinio pajėgumo vykdymo ir paklausos apkrovos santykiai;
- laiku ir pavėluotai užbaigtų Assembly darbų dalis;
- dienos, kai tempą ribojo READY badavimas, atskirai nuo dienų, kai READY darbo buvo pakankamai;
- prioritetų neatitikimai, kai vėlesnis SO vykdytas prieš artimesnio termino SO be patvirtintos išimties.

#### Trūkstami arba kalibruotini

- gamybos vadovės ryte įvedamas dirbančių Assembly darbuotojų skaičius; sistema apskaičiuoja `C = darbuotojų skaičius × 8 val.`;
- techniškai įgyvendinta ir su realiais atvejais validuota MQ-005 prioritetų bei leidžiamų išimčių taisyklė;
- faktinio išsiuntimo timestamp semantikos patikra;
- po 3–4 savaičių kalibruotos ribos, kada vykdymo nuokrypis laikomas sisteminiu;
- patikra, ar tos pačios `Delivery Date` dienos Assembly pabaiga realiai nesukelia Packaging / išsiuntimo vėlavimo.

### 6. Būsimas Product Engine modulis

MQ-004 naudos būsimo **TOC Constraint Diagnostic** modulio dalį **Assembly Pace Control**. Ji turės pateikti:

```text
Laikotarpis: ...
Planuotas Assembly pajėgumas: ... standartinių valandų
Reikalingas tempas pagal Delivery Date: ... standartinių valandų
Užbaigtas standartinis darbas: ... valandų
READY prieinamumas: pakankamas / nepakankamas
Pagrindinė nuokrypio klasė: capacity / execution / starvation / priority
Rizikuojantys SO: ...
Rekomenduojamas vadybinis veiksmas: ...
```

Modulis neturi vertinti darbuotojų pagal lokalų užimtumą. Jo paskirtis – nustatyti, ar bendras Assembly srautas pajėgia įvykdyti išsiuntimo įsipareigojimus ir kas konkrečiai paaiškina nuokrypį.

---

## MQ-005 — Kokius užsakymus Assembly turi surinkti šiandien?

### 1. Vadybinis klausimas

**Kokius `READY FOR ASSEMBLY` užsakymus ir kokia seka Assembly turi vykdyti šiandien, kad būtų apsaugoti artimiausi išsiuntimo įsipareigojimai ir bendras Furnibox Throughput?**

Šiandien Assembly darbų eilę daugiausia lemia žodiniai skubūs prašymai. Šis prioritetų šaltinis nėra audituojamas, gali keisti seką be matomo poveikio kitiems SO ir nebūtinai apsaugo artimiausią `Delivery Date`. MQ-005 pakeičia šią praktiką skaidria numatytąja eile ir oficialiu Odoo `SKUBUS` signalu.

### 2. Sprendimas, kurį atsakymas keičia

MQ-005 atsakymas kiekvienos darbo dienos pradžioje nustato:

- kuriuos READY darbus pradėti šiandien;
- kokia jų tarpusavio seka;
- kurių READY darbų šiandien nepradėti dėl riboto pajėgumo;
- kuriuos SO būtina eskaluoti, nes net teisinga seka nebeleidžia įvykdyti `Delivery Date`;
- kokį kitų SO pavėlavimo pavojų sukuria kiekviena patvirtinta prioriteto išimtis.

### 3. Sprendimo logika

#### 3.1. Tinkamumas eilėje

Į dienos Assembly eilę patenka tik `READY, NOT STARTED` darbai. `NOT READY`, `WIP ACTIVE`, `WIP PAUSED`, `WIP BLOCKED` ir `COMPLETED` darbai į naujai pradedamų darbų eilę neįtraukiami; jie rodomi atskirose kontrolės grupėse.

#### 3.2. Patvirtinta numatytoji prioritetų seka

| Prioriteto lygis | Taisyklė |
|---:|---|
| **1** | Jau vėluojantys READY užsakymai, pirmiausia su seniausia pradelsta SO `Delivery Date`. |
| **2** | Dar nevėluojantys `READY + SKUBUS` užsakymai, pirmiausia su artimiausia `Delivery Date`. |
| **3** | Kiti READY užsakymai, pirmiausia su artimiausia `Delivery Date`. |
| **4** | Kai to paties prioriteto lygio SO `Delivery Date` vienoda, pirmiau vykdomas anksčiau READY tapęs užsakymas. |

`SKUBUS` žyma saugoma Odoo kaip Sales Order tagas ir per SO–MO sąsają perduodama Assembly eilei. SO kuria, `SKUBUS` tagą priskiria ir nuima gamybos vadovė, todėl ji yra prioriteto savininkė. `SKUBUS` yra aukščiau visų dar nevėluojančių įprastų SO, bet neužgožia jau vėluojančio READY užsakymo.

#### 3.3. Dienos pajėgumo užpildymas

Rytinės patikros metu gamybos vadovė įveda dirbančių Assembly darbuotojų skaičių, o sistema apskaičiuoja `C = darbuotojų skaičius × 8 val.`. READY darbai pagal patvirtintą seką pridedami į dienos planą iki planinio `C`.

Kadangi vieną gaminį renka vienas darbuotojas, sistema turi rodyti ne tik bendrą dienos valandų sumą, bet ir konkretų darbų paskirstymą prieinamiems darbuotojams. Jei paskutinis darbas netelpa į likusias dienos valandas, jis gali būti pradėtas tik tada, jei gamybos vadovė sąmoningai priima WIP perkėlimo į kitą dieną sprendimą; sistema neturi apsimesti, kad visa jo norminė trukmė bus užbaigta tą dieną.

#### 3.4. Išimtys ir auditas

- Žodinis skubus prašymas savaime eilės nekeičia.
- Jei poreikis yra tikrai skubus, gamybos vadovė priskiria SO `SKUBUS` tagą.
- Jei naujas `READY + SKUBUS` SO atsiranda jau vykstant darbo dienai, jis nenutraukia šiuo metu vykdomos Assembly operacijos ir įtraukiamas kaip pirmas darbas po jos.
- Rankinis nukrypimas nuo apskaičiuotos sekos leidžiamas tik gamybos vadovei, nurodant priežastį.
- Prieš patvirtinant nukrypimą sistema parodo, kurie kiti SO dėl jo gali pereiti į vėlavimo riziką.
- Išimties audite saugoma kas, kada, ką perkėlė, priežastis ir prieš / po buvusi seka.

### 4. Required data (reikalingi duomenys)

| Duomuo | Paskirtis |
|---|---|
| READY būsena ir timestamp | Atrinkti vykdytinus darbus ir išspręsti vienodų datų prioritetą. |
| SO `Delivery Date` | Nustatyti vėluojančius ir artimiausius įsipareigojimus. |
| SO `SKUBUS` tagas | Taikyti oficialų aukštesnį prioritetą nevėluojantiems SO. |
| SO–MO–WO sąsajos | Perduoti SO prioritetą konkrečiam Assembly darbui. |
| BOM norminės Assembly valandos | Užpildyti dienos pajėgumą ir prognozuoti užbaigimą. |
| Ryte dirbančių Assembly darbuotojų skaičius | Apskaičiuoti dienos `C` ir paskirstyti darbus. |
| Esamas WIP bei WO `PAUSED` / `BLOCKED` būsenos | Neplanuoti to paties darbo kaip naujo ir rezervuoti dėmesį pradėtam darbui. |
| Rankinio sekos pakeitimo įvykis ir priežastis | Audituoti išimtis bei jų poveikį kitiems SO. |

### 5. Esami / išvedami / trūkstami duomenys

#### Esami arba jau sutarti

- SO `Delivery Date`;
- Odoo SO `SKUBUS` tagas;
- SO–MO ir MO–WO ryšiai, kuriuos reikia techniškai validuoti;
- BOM norminės Assembly valandos;
- WO pradžios, pabaigos, pauzės ir blokavimo būsenos;
- kasdienis gamybos vadovės READY patvirtinimas;
- gamybos vadovės įvedamas dirbančių darbuotojų skaičius.

#### Išvedami

- keturių lygių prioritetų seka;
- į dienos pajėgumą telpantys ir netelpantys darbai;
- numatoma kiekvieno READY darbo pradžios ir užbaigimo diena;
- SO, kuriems gresia praleisti `Delivery Date` net laikantis taisyklės;
- rankinio eilės pakeitimo paveikti SO.

#### Trūkstami

- rankinio sekos pakeitimo priežasties ir audito įvykis;
- patvirtintos leidžiamų išimčių priežasčių kategorijos arba pradinis laisvas komentaras;
- aiškus dienos plano patvirtinimo momentas;
- techninė patikra, ar Odoo `SKUBUS` tago pakeitimo istorijoje prieinami kas / kada duomenys.

### 6. Būsimas Product Engine modulis

MQ-005 naudos būsimo **TOC Constraint Diagnostic** modulio dalį **Assembly Priority Board**. Ji turės pateikti:

```text
Dirbantys Assembly darbuotojai: ...
Dienos pajėgumas: ... standartinių valandų
Šiandienos eilė: SO / MO / prioritetas / Delivery Date / SKUBUS / norminės valandos
Netelpantys į dienos pajėgumą darbai: ...
Delivery Date rizika: ...
Rankinės išimties poveikis kitiems SO: ...
```

Modulis turi pateikti paaiškinamą rekomenduojamą seką, bet galutinį dienos planą patvirtina gamybos vadovė. Jo tikslas – panaikinti nematomą žodinių skubinimų valdymą, o ne atimti atsakomybę už pagrįstas išimtis.

---

## MQ-006 — Kas mažina Assembly našų laiką?

### 1. Vadybinis klausimas

**Kas konkrečiai mažina Assembly našų laiką, kai prioritetizuoto `READY FOR ASSEMBLY` darbo eilė nėra tuščia?**

Klausimas atskiria tris skirtingus reiškinius:

- normalų `PAUSED` laiką, pavyzdžiui, darbo dienos pabaigą ar įprastą pertrauką;
- konkretaus WO `BLOCKED` trukmę ir jos poveikį užsakymo lead time;
- realiai prarastas Assembly žmogaus valandas, kai darbuotojas negalėjo produktyviai vykdyti nei užblokuoto, nei kito READY darbo.

### 2. Sprendimas, kurį atsakymas keičia

| Dominuojantis praradimas | Keičiamas vadybinis sprendimas ir veiksmas |
|---|---|
| **Brokuotos Furnix detalės** | Taisyti Furnix kokybės kontrolę, pakeitimo prioritetą ir grįžtamąjį ryšį pagal prarandamas Assembly valandas bei rizikuojančius SO. |
| **Brokuoti subrangovo fasadai ar stalčiai** | Keisti subrangovo kokybės, priėmimo ir pakaitinių detalių eskalavimo procesą. |
| **Trūkumas nustatomas tik pradėjus Assembly** | Gerinti rytinę READY / pilno komplekto patikrą, jei trūkumą buvo įmanoma nustatyti iš anksto. |
| **Techninė informacija ar brėžiniai** | Užtikrinti pilną informaciją prieš Assembly pradžią ir aiškų greito sprendimo savininką. |
| **Įrankis ar įranga** | Prioritetizuoti priežiūrą, atsarginį įrankį ar proceso pakeitimą pagal constraint valandų nuostolį. |
| **Laukiama vadovo sprendimo** | Nustatyti sprendimo SLA ir delegavimo ribas, kad Assembly nelauktų vadybinio atsako. |
| **Daug WO blokavimų, bet beveik nėra prarastų valandų** | Neskubėti didinti pajėgumo; gerinti užsakymų srautą ir WIP, tačiau pripažinti, kad darbuotojai persijungė į kitą READY darbą. |
| **Nežinoma arba `OTHER` dominuoja** | Gerinti priežasčių registravimo discipliną; bendroji kategorija negali būti pagrindas investiciniam sprendimui. |

### 3. Sprendimo logika

#### 3.1. `PAUSED` ir `BLOCKED` naudojimo taisyklė

- `PAUSED` naudojamas normalioms pertraukoms ir darbo dienos pabaigai; priežastis neprivaloma.
- `BLOCKED` naudojamas, kai WO negalima tęsti dėl nenormalaus trukdžio; priežastis privaloma.
- Pradėjus kitą darbo dieną arba pasibaigus normaliai pertraukai darbuotojas turi atnaujinti WO būseną pagal faktinę situaciją.

#### 3.2. Patvirtintas `BLOCKED` priežasčių katalogas

| Kodas | Priežastis |
|---|---|
| `DEFECTIVE_FURNIX_PART` | Brokuota Furnix detalė. |
| `DEFECTIVE_SUBCONTRACTOR_FRONT` | Brokuotas subrangovo fasadas. |
| `DEFECTIVE_SUBCONTRACTOR_DRAWER` | Brokuotas subrangovo stalčius. |
| `MISSING_COMPONENT_FOUND_DURING_ASSEMBLY` | Trūkumas pastebėtas tik pradėjus surinkimą. |
| `TECHNICAL_INFORMATION_MISSING` | Trūksta techninės informacijos arba neaiškus brėžinys. |
| `TOOL_OR_EQUIPMENT_UNAVAILABLE` | Trūksta įrankio arba įranga neveikia. |
| `WAITING_FOR_MANAGER_DECISION` | Laukiama vadovo sprendimo. |
| `OTHER` | Kita priežastis; privalomas trumpas komentaras. |

#### 3.3. Dvi atskiros trukmės

Kiekvienam `BLOCKED` įvykiui skaičiuojama:

1. **WO blokavimo trukmė** – kiek darbo laiko užsakymas negalėjo būti tęsiamas; ji matuoja užsakymo srauto / lead time poveikį.
2. **Prarastos Assembly žmogaus valandos** – kiek suplanuoto darbo laiko priskirtas darbuotojas negalėjo vykdyti jokio kito READY darbo dėl šio trukdžio.

Jei darbuotojas užblokuoja WO ir nedelsdamas pradeda kitą READY darbą, pirmoji trukmė didėja, bet antroji lygi nuliui. Todėl negalima visos WO blokavimo trukmės automatiškai vadinti prarastu Assembly pajėgumu.

Skaičiuojamas tik suplanuoto darbo grafiko laikas. Naktis, savaitgalis, normali pertrauka ar laikas po darbo dienos pabaigos nepriskiriami prarastoms Assembly žmogaus valandoms.

#### 3.4. Prioritetų logika

Kasdien pirmiausia eskaluojami blokatoriai, kurie:

1. šiuo metu sukelia realų Assembly žmogaus valandų praradimą;
2. blokuoja vėluojantį arba `SKUBUS` SO;
3. gali sumažinti READY bufferį iki raudonos zonos;
4. kartojasi ir per savaitę praranda daugiausia Assembly valandų.

### 4. Required data (reikalingi duomenys)

| Duomuo | Paskirtis |
|---|---|
| WO `BLOCKED` pradžios ir pabaigos timestamp | Matuoti blokavimo intervalą. |
| Privalomas blokavimo priežasties kodas | Susieti nuostolį su konkrečiu vadybiniu veiksmu. |
| Komentaras kategorijai `OTHER` | Neleisti nežinomoms priežastims pasislėpti. |
| WO, MO ir SO identifikatoriai | Susieti blokatorių su `Delivery Date`, `SKUBUS` ir norminėmis valandomis. |
| Darbuotojo / darbo centro darbo įrašai | Nustatyti, ar blokuojant vieną WO buvo pradėtas kitas READY darbas. |
| Dienos planinis pajėgumas ir darbo grafikas | Skaičiuoti tik realiai suplanuoto laiko praradimus. |
| READY bufferis blokavimo metu | Įvertinti, ar darbuotojas turėjo alternatyvaus darbo. |
| Kito WO pradžios timestamp | Nustatyti persijungimo laiką ir faktines prarastas žmogaus valandas. |

### 5. Esami / išvedami / trūkstami duomenys

#### Esami arba jau sutarti

- Odoo WO gali būti blokuojamas nurodant priežastį;
- WO operacijos gali būti pradėtos, sustabdytos, atnaujintos ir užbaigtos;
- Odoo darbo įrašuose galima identifikuoti konkretų Assembly darbuotoją ir momentą, kada jis nuo užblokuoto WO pradėjo kitą WO;
- `PAUSED` naudojamas normalioms pertraukoms bei darbo dienos pabaigai;
- dienos Assembly pajėgumas apskaičiuojamas iš dirbančių darbuotojų skaičiaus × 8 val.;
- READY bufferis ir prioritetų eilė apibrėžti MQ-002 bei MQ-005.

#### Išvedami

- WO blokavimo darbo laiko trukmė pagal priežastį;
- laikas iki kito READY darbo pradžios;
- realiai prarastos Assembly žmogaus valandos, kai nevyko joks alternatyvus darbas;
- paveiktų SO, standartinių valandų ir `Delivery Date` rizikos suma;
- savaitinis priežasčių Pareto pagal blokavimo trukmę ir atskirai pagal prarastas žmogaus valandas;
- pasikartojantys blokatoriai ir vidutinis jų pašalinimo laikas.

#### Trūkstami arba kalibruotini

- patvirtintos Odoo blokavimo priežasčių reikšmės pagal šį katalogą;
- taisyklė situacijai, kai vieną WO kartu vykdo ar gali perimti daugiau nei vienas darbuotojas;
- duomenų kokybės kontrolė, neleidžianti naudoti `BLOCKED` be priežasties;
- darbo grafiko ribos, reikalingos naktims, savaitgaliams ir normalioms pertraukoms atmesti.

### 6. Būsimas Product Engine modulis

MQ-006 naudos būsimo **TOC Constraint Diagnostic** modulio dalį **Assembly Loss Control**. Ji turės pateikti:

```text
Aktyvūs BLOCKED WO: ...
Šiuo metu prarandamos Assembly žmogaus valandos: ...
Blokavimo trukmė pagal priežastį: ...
Realiai prarastos žmogaus valandos pagal priežastį: ...
Vėluojantys / SKUBUS paveikti SO: ...
Didžiausias šiandienos eskalavimo prioritetas: ...
Savaitinis pasikartojančių nuostolių Pareto: ...
```

Modulis neturi WO blokavimo kalendorinės trukmės automatiškai vadinti prarastu constraint pajėgumu. Jis turi parodyti ir užsakymo srauto žalą, ir tikrą Assembly žmogaus laiko nuostolį kaip du skirtingus dydžius.

---

## MQ-007 — Kiek laiku realizuojamo Throughput atidedame?

### 1. Vadybinis klausimas

**Kiek laiku realizuojamo Throughput atidedame dėl to, kad užsakymai per vėlai tampa `READY FOR ASSEMBLY`, o kiek – dėl nepakankamo Assembly pajėgumo ar vykdymo po READY?**

Kadangi pavėluoti Furnibox SO visada vėliau išsiunčiami, klausimas nematuoja galutinai prarastų pardavimų. Jis įvertina, kiek ekonominės vertės neišsiunčiama pažadėtu laiku, kiek dienų ji atidedama ir kuri proceso dalis sukėlė vėlavimą.

### 2. Sprendimas, kurį atsakymas keičia

| Ekonominio poveikio šaltinis | Keičiamas vadybinis sprendimas ir veiksmas |
|---|---|
| **Daugiausia Throughput atideda vėlyvas READY** | Investuoti vadovų dėmesį į MQ-003 dominuojančius komponentų ir paruošimo blokatorius; nedidinti Assembly pajėgumo vien dėl pavėluotų SO. |
| **Daugiausia Throughput atideda Assembly po READY** | Gerinti MQ-005 seką, šalinti MQ-006 laiko nuostolius ir tik tada vertinti papildomą Assembly pajėgumą. |
| **Reikšmingos abi priežastys** | Prioritetizuoti pakeitimą pagal didžiausią sumažinamą `Throughput × vėlavimo dienos` ir realų įgyvendinimo laiką. |
| **Throughput at risk didelis, bet dar nevėluoja** | Imtis prevencinio veiksmo prieš `Delivery Date`, nelaukiant faktinio vėlavimo. |
| **Užsakymų skaičius didelis, bet ekonominis poveikis mažas** | Neleisti atvejų kiekiui užgožti mažesnio skaičiaus didelės Throughput vertės SO. |

### 3. Sprendimo logika

#### 3.1. Throughput skaičiavimas

Throughput skaičiuojamas SO line lygiu:

```text
SO line Throughput = SO line pardavimo vertė
                     − medžiagų sąnaudos
                     − subrangovų sąnaudos
```

Assembly darbo užmokestis ir kitos fiksuotos / laikotarpio sąnaudos į SO line Throughput neatimamos, jei jos nesikeičia dėl konkretaus papildomo pardavimo; jos priklauso Operating Expense. Assembly reikalaujančių SO line Throughput agreguojamas į SO ir priežasties kategoriją.

#### 3.2. Ekonominio laiko būsenos

| Būsena | Taisyklė |
|---|---|
| **Throughput at risk** | SO dar nevėluoja, bet pagal READY būseną, standartines valandas, dienos pajėgumą ir prioritetų eilę prognozuojamas išsiuntimas po `Delivery Date`. |
| **Atidėtas / pavėluotas Throughput** | Faktinis išsiuntimas įvyko po SO `Delivery Date`; visa atitinkamų Assembly SO line Throughput vertė priskiriama pavėluotai. |
| **Galutinai prarastas Throughput** | Furnibox dabartinėje situacijoje lygus nuliui, nes pavėluoti SO visada išsiunčiami ir nėra atšaukiami ar mažinami dėl vėlavimo. |

Pagrindinis poveikio matas:

```text
Throughput delay-days = SO Throughput × darbo dienų skaičius
                        nuo Delivery Date iki faktinio išsiuntimo
```

Šis matas leidžia atskirti, pavyzdžiui, vienos dienos nedidelio SO vėlavimą nuo savaitę vėluojančio didelės Throughput vertės SO. Jis nėra apskaitinis nuostolis eurais ir neturi būti rodomas kaip prarastas pelnas.

#### 3.3. Vėlavimo priežasties priskyrimas

| Stebimas raštas | Priežasties klasė |
|---|---|
| Užsakymas tapo READY per vėlai, kad pagal likusias standartines valandas ir tuo metu galiojusį pajėgumą galėtų būti užbaigtas iki `Delivery Date`. | **Upstream / late readiness.** |
| Užsakymas tapo READY pakankamai anksti, tačiau teisingoje prioritetų eilėje nebuvo užbaigtas dėl nepakankamo `C`, sisteminių vykdymo nuostolių ar blokavimų. | **Assembly capacity / execution.** |
| Užsakymas vėlai tapo READY ir po READY dar patyrė reikšmingą Assembly laukimą ar blokavimą. | **Mixed.** |
| Užsakymas buvo READY ir bendro pajėgumo pakako, bet jį nustūmė nepatvirtinta arba neteisinga seka. | **Priority policy.** |
| Įvykių nepakanka patikimam kontrafaktiniam terminui apskaičiuoti. | **Unknown / insufficient data.** |

Priežastis priskiriama pagal tuo metu buvusią informaciją ir pajėgumą, ne pagal vėliau paaiškėjusius duomenis. Sistema turi išsaugoti skaičiavimo paaiškinimą; ji neturi pavėluotam SO automatiškai priskirti vienos priežasties vien todėl, kad paskutinis matomas etapas buvo Assembly.

### 4. Required data (reikalingi duomenys)

| Duomuo | Paskirtis |
|---|---|
| SO line pardavimo vertė | Throughput skaičiavimo bazė. |
| SO line medžiagų ir subrangovų sąnaudos | Visiškai kintamoms sąnaudoms atimti. |
| Požymis, kurioms SO line reikalingas Assembly | Ekonominę vertę susieti su analizuojamu srautu. |
| SO–MO–WO–SO line sąsajos | Priskirti READY, Assembly ir vėlavimo įvykius ekonominei vertei. |
| SO `Delivery Date` ir faktinis išsiuntimo timestamp | Nustatyti vėlavimo faktą ir trukmę. |
| READY timestamp bei NOT READY priežasčių intervalai | Nustatyti upstream indėlį. |
| BOM norminės Assembly valandos | Apskaičiuoti, kada darbas galėjo būti užbaigtas. |
| Dienos pajėgumas `C`, prioritetų seka ir WO būsenos | Nustatyti Assembly capacity, execution ir policy indėlį. |

### 5. Esami / išvedami / trūkstami duomenys

#### Esami arba jau sutarti

- SO line pardavimo vertė;
- SO line Odoo savikaina, apimanti medžiagų sąnaudas ir neapimanti Assembly darbo užmokesčio;
- SO `Delivery Date`;
- BOM norminės Assembly valandos;
- READY, WO ir dienos pajėgumo duomenų kontraktai iš MQ-001–MQ-006.

#### Išvedami

- SO line ir SO Throughput;
- `Throughput at risk` eurais;
- pavėluotas Throughput eurais ir darbo dienomis;
- `Throughput delay-days`;
- poveikio paskirstymas į `late readiness`, `Assembly capacity / execution`, `mixed`, `priority policy` ir `unknown`;
- savaitinis ir mėnesinis ekonominio poveikio Pareto pagal priežastį.

#### Trūkstami arba validuotini

- patikimas faktinis išsiuntimo timestamp ir SO line kiekių susiejimas dalinių išsiuntimų atveju;
- techninė SO line–MO–WO sąsajos validacija;
- patikra, kaip SO line savikainoje atvaizduojamos tiesiogiai dėl konkretaus pardavimo patiriamos subrangovų sąnaudos, jei jos nėra medžiagų savikainos dalis;
- kontrafaktinio „galėjo būti užbaigtas iki Delivery Date“ algoritmo validacija su realiais atvejais;
- dalinio vėlavimo taisyklė, jei vieno SO dalis išsiunčiama laiku, o dalis vėliau.

### 6. Būsimas Product Engine modulis

MQ-007 naudos būsimo **TOC Constraint Diagnostic** modulio dalį **Throughput Delay Attribution**. Ji turės pateikti:

```text
Throughput at risk: ... €
Pavėluotas Throughput: ... €
Throughput delay-days: ... €·darbo dienos
Late readiness dalis: ...
Assembly capacity / execution dalis: ...
Priority policy dalis: ...
Mixed / unknown dalis: ...
Didžiausio ekonominio poveikio konkretūs SO: ...
Rekomenduojamas vadybinis fokusas: ...
```

Modulis neturi pavėluoto Throughput vadinti prarastu pelnu. Jo paskirtis – parodyti, kurio proceso pakeitimas labiausiai sumažintų ekonominės vertės vėlavimą ir apsaugotų pristatymo patikimumą.

---

## MQ-008 — Koks mažiausias pakeitimas duotų didžiausią poveikį?

### 1. Vadybinis klausimas

**Koks mažiausias konkretus pakeitimas greičiausiai labiausiai padidintų laiku realizuojamą surenkamų užsakymų Throughput: patikimesnis komponentų prieinamumas, griežtesnė READY ir prioritetų tvarka, didžiausio Assembly blokatoriaus pašalinimas ar papildomas Assembly pajėgumas?**

„Mažiausias pakeitimas“ reiškia mažiausios investicijos, mažiausios papildomos Operating Expense ir trumpiausio įgyvendinimo laiko pakeitimą, kuris duoda didžiausią pamatuojamą laiku realizuojamo Throughput pagerėjimą.

Kadangi Furnibox pavėluotus SO visada vėliau išsiunčia, greitesnis esamų SO išsiuntimas pirmiausia mažina atidėtą Throughput ir gerina pristatymo patikimumą. Tikras bendro Throughput padidėjimas atsiranda tik tada, kai atlaisvintas pajėgumas leidžia per tą patį laikotarpį išsiųsti papildomą paklausą, kuri kitu atveju būtų laukusi, nepriimta ar perkelta į vėlesnį laikotarpį.

Šiuo metu Reform yra vienintelis Furnibox klientas, `Delivery Date` nurodo pats klientas, o Furnibox dėl Assembly pajėgumo užsakymų neatsisako ir sąmoningai nenukelia kliento pageidaujamos datos. Todėl dabartiniame duomenų kontrakte nėra nepriimtos papildomos paklausos, kuri pagrįstų tikro bendro Throughput augimo skaičiavimą. MQ-008 pradinis rezultatas vertina tik laiku realizuojamo Throughput pagerėjimą ir vėlavimo sumažinimą; papildomas bendras Throughput rodomas kaip `not evidenced`.

### 2. Sprendimas, kurį atsakymas keičia

| Geriausia alternatyva | Keičiamas vadybinis sprendimas ir veiksmas |
|---|---|
| **Komponentų prieinamumas** | Pirmiausia įgyvendinti MQ-003 dominuojančio readiness blokatoriaus mažinimo veiksmą; nedidinti Assembly pajėgumo, kol jis badauja. |
| **READY ir prioritetų disciplina** | Įdiegti kasdienį READY patvirtinimą bei MQ-005 seką prieš investuojant į žmones ar įrangą. |
| **Didžiausio Assembly blokatoriaus pašalinimas** | Nukreipti mažą tikslinę investiciją į MQ-006 priežastį, prarandančią daugiausia Assembly žmogaus valandų ir atidedančią daugiausia Throughput. |
| **Papildomas Assembly pajėgumas** | Didinti darbuotojų skaičių ar papildomas valandas tik jei READY bufferis pakankamas, esamas pajėgumas išnaudojamas, o reikiamas tempas sistemingai viršija `C`. |
| **Nė viena alternatyva nepatikima** | Nepriimti investicijos sprendimo; tęsti duomenų rinkimą arba vykdyti mažą grįžtamą pilotą su aiškiu sėkmės kriterijumi. |

### 3. Sprendimo logika

#### 3.1. Vertinamos alternatyvos

1. **Patikimesnis komponentų prieinamumas** – sumažinti vienos ar kelių MQ-003 priežasčių trukmę ir padidinti READY bufferio stabilumą.
2. **READY ir dienos prioritetų tvarka** – taikyti rytinį READY patvirtinimą, dviejų dienų bufferį ir MQ-005 seką vietoje žodinių skubinimų.
3. **Didžiausio Assembly blokatoriaus pašalinimas** – sumažinti MQ-006 priežastį, prarandančią daugiausia realių žmogaus valandų arba blokuojančią didžiausią Throughput.
4. **Papildomas Assembly darbuotojas / valandos** – padidinti dienos `C` ir perskaičiuoti, kiek SO galėtų būti užbaigta iki `Delivery Date`.

#### 3.2. Vienodas alternatyvos kontraktas

Kiekvienai alternatyvai pateikiama:

| Vertinimas | Reikšmė |
|---|---|
| **Poveikio hipotezė** | Kurį MQ-001–MQ-007 signalą pakeitimas veikia ir kodėl. |
| **Tikėtinas laiku realizuoto Throughput pagerėjimas** | Sumažintas `Throughput at risk`, pavėluotas Throughput ir `Throughput delay-days`. |
| **Tikėtinas papildomas bendras Throughput** | Tik jei yra papildoma paklausa, kuri gali naudoti atlaisvintą pajėgumą. |
| **Papildoma Operating Expense** | Pasikartojančios darbo, viršvalandžių, priežiūros ar kitos sąnaudos. |
| **Vienkartinė investicija** | Įrankiai, įranga, sistema, proceso pakeitimo kaštas. |
| **Laikas iki poveikio** | Kada realiai galima tikėtis rezultato. |
| **Pasitikėjimas** | Duomenų kokybė, pasikartojimų skaičius ir prielaidų stiprumas. |
| **Constraint perkėlimo rizika** | Ar pagerinus vieną vietą kita proceso dalis taps nauju apribojimu. |

#### 3.3. Scenarijų skaičiavimas

Alternatyvos lyginamos su bazine faktine situacija tame pačiame 3–4 savaičių ar ilgesniame duomenų lange:

- **Komponentų scenarijus:** sutrumpinami pasirinktos MQ-003 priežasties intervalai iki pagrįsto piloto tikslo ir perskaičiuojami READY momentai bei vėlavimai.
- **Prioritetų scenarijus:** faktiniai READY darbai perrikiuojami pagal MQ-005 taisyklę, nekeičiant faktinio `C`, ir perskaičiuojami SO užbaigimo terminai.
- **Blokatoriaus scenarijus:** grąžinama pagrįsta dalis MQ-006 realiai prarastų žmogaus valandų, o ne visa WO kalendorinė blokavimo trukmė.
- **Pajėgumo scenarijus:** prie kiekvienos pasirinkto laikotarpio dienos `C` pridedamas konkretus valandų skaičius, pavyzdžiui, `+8 val.` už vieną papildomą darbuotoją, jei READY darbo pakanka.

Scenarijus negali pašalinti 100 % svyravimo be empirinio pagrindo. Nežinomos prielaidos rodomos atvirai ir mažina pasitikėjimo lygį.

#### 3.4. Pasirinkimo taisyklė

Rekomenduojamas pakeitimas turi:

1. veikti patvirtintą dominuojančią priežastį;
2. turėti pamatuojamą poveikį laiku realizuojamam Throughput;
3. būti mažesnės papildomos OE / investicijos ir greitesnis už panašaus poveikio alternatyvas;
4. nesiremti Assembly pajėgumo didinimu, jei READY bufferis sistemingai badauja;
5. būti įgyvendinamas kaip grįžtamas pilotas, kai pasitikėjimas dar neaukštas.

Rezultatas nėra automatinis sprendimas. Product Engine pateikia palyginimą ir rekomendaciją, o galutinį pakeitimą patvirtina vadovybė.

### 4. Required data (reikalingi duomenys)

| Duomuo | Paskirtis |
|---|---|
| MQ-001 constraint / priežasties klasifikacija | Neoptimizuoti neapribojančios vietos. |
| MQ-002 READY bufferio istorija | Nustatyti Assembly badavimo dažnį ir pajėgumo scenarijaus tinkamumą. |
| MQ-003 readiness priežasčių intervalai | Modeliuoti komponentų prieinamumo pagerinimą. |
| MQ-004 pajėgumas, poreikis ir užbaigimo tempas | Modeliuoti tempo bei pajėgumo pakeitimus. |
| MQ-005 faktinė ir rekomenduota prioritetų seka | Modeliuoti policy pakeitimą. |
| MQ-006 realiai prarastos žmogaus valandos pagal priežastį | Modeliuoti konkretaus blokatoriaus pašalinimą. |
| MQ-007 SO line Throughput ir vėlavimo priskyrimas | Išreikšti poveikį ekonomine verte. |
| Alternatyvos OE, investicija ir įgyvendinimo trukmė | Palyginti pakeitimo dydį ir atsipirkimo logiką. |
| Papildomos paklausos / nepriimtų užsakymų duomenys | Atskirti greitesnį esamų SO išsiuntimą nuo tikro papildomo Throughput. |

### 5. Esami / išvedami / trūkstami duomenys

#### Esami arba atsirasiantys iš ankstesnių klausimų

- visi MQ-001–MQ-007 sutarti įvykiai, būsenos ir išvedami rodikliai;
- SO line pardavimo vertė ir medžiagų savikaina;
- BOM norminės Assembly valandos;
- dienos `C`, READY bufferis, WO būsenos ir `Delivery Date`.

#### Išvedami

- kiekvienos alternatyvos sumažinamas `Throughput at risk` ir `Throughput delay-days`;
- papildomai laiku išsiunčiamų SO skaičius;
- galimas papildomas bendras Throughput, jei egzistuoja papildoma paklausa;
- poveikio, OE / investicijos, įgyvendinimo laiko ir pasitikėjimo palyginimas;
- rekomenduojamas mažiausias pakeitimas ir jį pagrindžiantys signalai.

#### Trūkstami arba įvedami sprendimo metu

- konkrečių alternatyvų papildoma OE ir vienkartinė investicija;
- įgyvendinimo trukmė bei piloto apimtis;
- realistiškas numatomas priežasties sumažinimo procentas;
- papildomos paklausos arba dėl pajėgumo nepriimamų / atidedamų užsakymų duomenys, kurių dabartinėje situacijoje nėra;
- vadovybės pasirinktas sėkmės kriterijus ir piloto stabdymo taisyklė.

### 6. Būsimas Product Engine modulis

MQ-008 naudos būsimo **TOC Constraint Diagnostic** modulio dalį **TOC What-if Advisor**. Ji turės pateikti:

```text
Dominuojanti priežastis: ...
Alternatyva A – komponentų prieinamumas: poveikis / OE / investicija / laikas / pasitikėjimas
Alternatyva B – READY ir prioritetų disciplina: ...
Alternatyva C – didžiausias Assembly blokatorius: ...
Alternatyva D – papildomas Assembly pajėgumas: ...
Rekomenduojamas mažiausias pakeitimas: ...
Kodėl: ...
Constraint perkėlimo rizika: ...
Siūlomas pilotas ir sėkmės kriterijus: ...
```

Modulis neturi rekomenduoti papildomo žmogaus vien todėl, kad užsakymai vėluoja. Jis pirmiausia turi patikrinti, ar Assembly turi READY darbo, ar esamas pajėgumas išnaudojamas ir ar papildomas pajėgumas turėtų paklausą, kurią galima paversti papildomu Throughput.

## Kitas specifikacijos etapas

Visų aštuonių klausimų sprendimo logika ir pradinis duomenų kontraktas formalizuoti bei tarpusavyje peržiūrėti. Reform yra vienintelis klientas, jo nurodyta `Delivery Date` nėra Furnibox sąmoningai nukeliama, o užsakymai dėl Assembly pajėgumo neatmetami. Kitas etapas – remiantis šiuo katalogu suformuluoti Product Engine sprendimų palaikymo architektūrą, dar nepradedant funkcionalumo implementacijos.
