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

MQ-001 sprendimo logika ir pradinis READY būsenos verslo apibrėžimas yra patvirtinti. Modulio projektavimas vis dar nepradedamas, kol katalogo klausimai nėra nuosekliai formalizuoti ir bendras duomenų bei sprendimų kontraktas neparodo būsimos architektūros ribų.

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

Pradiniame etape `C` skaičiuojamas kaip tą darbo dieną faktiškai suplanuotų Assembly darbuotojų planinių darbo valandų suma. Assembly darbuotojai visą savo planuojamą laiką dirba tik surinkime, todėl papildomas laiko paskirstymo kitiems darbams koeficientas netaikomas. Neatvykimai, trumpesnės pamainos ir kiti iš anksto žinomi prieinamumo sumažėjimai turi mažinti konkrečios dienos `C`. BOM Assembly operacijos laikas nustatytas vienam gaminiui, darant prielaidą, kad jį renka vienas darbuotojas; todėl viena BOM norminė valanda tiesiogiai atitinka vieną standartinę žmogaus Assembly valandą ir gali būti lyginama su `C`.

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

- aiški Assembly badavimo įvykio registravimo arba išvedimo taisyklė;
- MQ-005 formalizuojama dienos prioritetų sudarymo taisyklė;
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

## Kitas specifikacijos etapas

MQ-003 priežasčių ir persidengiančių intervalų taisyklės patvirtintos. Toliau ta pačia pilna struktūra formalizuoti MQ-004 — „Kai Assembly turi paruoštų užsakymų, ar jis juos užbaigia reikiamu tempu?“ — nekeičiant patvirtinto aštuonių klausimų sąrašo be naujo verslo aptarimo.
