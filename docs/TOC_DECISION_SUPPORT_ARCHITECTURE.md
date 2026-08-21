# Furnibox TOC Decision Support architektūra

Statusas: architektūros specifikacija prieš implementaciją.

Šaltiniai:

- [`toc-management-question-catalog.md`](toc-management-question-catalog.md), MQ-001–MQ-008;
- [`TOC_ODOO_DATA_CONTRACT_VALIDATION_2026-08-21.md`](TOC_ODOO_DATA_CONTRACT_VALIDATION_2026-08-21.md), Production read-only kontrakto validacija.

## 1. Tikslas

Sukurti Product Engine sprendimų palaikymo sluoksnį, kuris ne tik pateikia Odoo duomenis, bet formalizuotą sprendimo logiką paverčia audituojamais atsakymais ir rekomenduojamais vadybiniais veiksmais.

Pagrindinė grandinė:

```text
vadybinis klausimas
→ required data
→ sprendimo procedūra
→ paaiškinamas atsakymas
→ vadybinis veiksmas
→ rezultato patikra
```

Architektūra turi atsakyti:

1. kas lemia surenkamų SO vėlavimą;
2. ar Assembly turi pakankamą READY bufferį;
3. kas neleidžia darbams tapti READY;
4. ar Assembly užbaigia darbus reikiamu tempu;
5. kokia turi būti šiandienos Assembly eilė;
6. kas mažina Assembly našų laiką;
7. kiek laiku realizuojamo Throughput atidedama ir kodėl;
8. koks mažiausias pakeitimas duotų didžiausią poveikį.

## 2. Architektūros principai

1. **Question-first.** Naujas rodiklis ar laukas priimamas tik jei naudojamas patvirtintoje sprendimo procedūroje.
2. **Production Odoo – read-only.** Decision Support nerašo į Production Odoo ir nekeičia SO, MO, WO, BOM, tagų ar kitų objektų.
3. **Product Engine valdo tik savo sprendimų duomenis.** Rankiniai READY patvirtinimai, NOT READY priežastys, dienos pajėgumas, sekos išimtys ir analizės rezultatai saugomi Product Engine valdomoje saugykloje.
4. **Events over mutable status.** Svarbūs pokyčiai saugomi kaip nekintami audito įvykiai; dabartinė būsena iš jų išvedama.
5. **Explainable decisions.** Kiekviena išvada turi parodyti šaltinius, taisyklių versiją, pasitikėjimą, alternatyvias hipotezes ir rekomenduojamą veiksmą.
6. **No false precision.** Kasdienis READY timestamp turi vienos darbo dienos skiriamąją gebą ir negali būti rodomas kaip tikslus paskutinio komponento gavimo laikas.
7. **Separate flow loss from capacity loss.** WO blokavimo trukmė ir realiai prarastos Assembly žmogaus valandos yra skirtingi dydžiai.
8. **Delayed is not lost.** Pavėluotas Throughput nėra prarastas pelnas, nes Reform SO vėliau vis tiek išsiunčiami.
9. **Human-in-the-loop.** Product Engine rekomenduoja ir paaiškina; galutinį dienos planą bei pakeitimo pilotą patvirtina atsakingas vadovas.
10. **Start small, calibrate dynamically.** Pradinis READY bufferis yra 2 Assembly darbo dienos ir kalibruojamas pagal 3–4 savaičių faktą.

## 3. Ribos ir ne tikslai

### Įeina į pirmąją produkto ribą

- tik surenkamų Reform užsakymų srautas;
- Assembly ir upstream paruošimo diagnostika;
- Packaging tik kaip stebima downstream sąlyga, ne aktyvi constraint hipotezė;
- kasdienė kontrolė, savaitinė diagnostika ir what-if palyginimas;
- Odoo duomenų skaitymas;
- Product Engine rankinių sprendimų įvykių saugojimas.

### Neįeina

- rašymas į Production Odoo;
- automatinis SO `SKUBUS` tago keitimas;
- automatinis WO blokavimas, paleidimas ar darbuotojo priskyrimas;
- darbuotojų individualaus produktyvumo reitingavimas;
- viso Furnibox ERP ar gamybos planavimo pakeitimas;
- Packaging optimizavimo modulis, kol nėra naujų duomenų apie sistemingą eilę;
- galutinai prarasto Throughput rodymas, kol užsakymai neatšaukiami ir nemažinami;
- funkcionalumo implementacija šiame architektūros etape.

## 4. Loginė architektūra

```text
┌──────────────────────────────────────────────────────────────┐
│                      Product Engine UI                       │
│ Morning Control │ Live Control │ Weekly Review │ What-if     │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                    Decision Application API                  │
│ Commands │ Queries │ Approval/Audit │ Decision Explanations  │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
┌───────────────▼────────────────┐  ┌──────────▼───────────────┐
│ Decision Engines              │  │ Projection / Read Models │
│ Readiness                     │  │ Current order state      │
│ Ready Buffer                  │  │ Daily priority board     │
│ Pace                          │  │ Weekly constraint view   │
│ Priority                      │  │ Throughput attribution   │
│ Assembly Loss                 │  │ Scenario comparison      │
│ Throughput Delay              │  └──────────┬───────────────┘
│ Constraint Synthesis          │             │
│ What-if                       │             │
└───────────────┬────────────────┘             │
                └──────────────┬───────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                 Canonical Domain + Event Store               │
│ Odoo snapshots │ Decision events │ Rule versions │ Results   │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
┌───────────────▼────────────────┐  ┌──────────▼───────────────┐
│ Odoo Read Adapter             │  │ Product Engine Store     │
│ SO / lines / tags / dates     │  │ READY checks             │
│ MO / WO / work logs / blocks  │  │ NOT READY blockers       │
│ BOM operation times / costs   │  │ Daily capacity           │
│ shipments                     │  │ Priority overrides       │
│ READ ONLY                     │  │ Audits / decisions       │
└────────────────────────────────┘  └──────────────────────────┘
```

## 5. Goldratt produkto sluoksniai

### 5.1. SCHEDULE

Tikslas – atsakyti „ką Assembly turi daryti šiandien?“

Komponentai:

- **Morning Readiness Check** – gamybos vadovės kasdienis patvirtinimas;
- **Daily Capacity Input** – dirbančių darbuotojų skaičius, `C = count × 8 h`;
- **Assembly Priority Board** – MQ-005 keturių lygių seka;
- **Worker Assignment Draft** – rekomenduojamas READY darbų paskirstymas darbuotojams;
- **Schedule Approval** – gamybos vadovės patvirtintas dienos planas;
- **Urgent Insertion Rule** – dieną atsiradęs `SKUBUS` tampa pirmas po aktyvaus darbo.

SCHEDULE negali įtraukti NOT READY darbo ar nutraukti aktyvaus WO.

### 5.2. CONTROL

Tikslas – atsakyti „ar planas ir srautas saugūs dabar, o jei ne – kodėl?“

Komponentai:

- **Ready Buffer Control** – MQ-002 raudona / geltona / žalia zona;
- **Readiness Blocker Control** – MQ-003 priežastys ir intervalai;
- **Assembly Pace Control** – MQ-004 reikalingas, planinis ir užbaigtas tempas;
- **Assembly Loss Control** – MQ-006 PAUSED, BLOCKED ir realiai prarastos valandos;
- **Delivery Risk Control** – prognozuojami SO po `Delivery Date`;
- **Constraint Synthesis** – MQ-001 galutinė klasė: late readiness, Assembly, mixed arba insufficient data;
- **Throughput Delay Attribution** – MQ-007 ekonominis poveikis.

CONTROL turi teikti išimtis, o ne skatinti nuolatinį dashboardo stebėjimą.

### 5.3. WHAT-IF

Tikslas – atsakyti „kuris mažiausias pakeitimas duotų didžiausią poveikį?“

Komponentai:

- komponentų prieinamumo scenarijus;
- READY ir prioritetų disciplinos scenarijus;
- didžiausio Assembly blokatoriaus scenarijus;
- papildomo darbuotojo / valandų scenarijus;
- vienodas poveikio, OE, investicijos, laiko ir pasitikėjimo palyginimas;
- piloto pasiūlymas ir sėkmės kriterijus;
- constraint perkėlimo rizika.

WHAT-IF negali rodyti papildomo bendro Throughput, kai nėra papildomos paklausos įrodymo. Tokiu atveju rodoma tik sumažinta vėlavimo rizika ir laiku realizuojamo Throughput pagerėjimas.

## 6. Kanoninis domeno modelis

### 6.1. Odoo skaitomi objektai

| Objektas | Pagrindiniai laukai | Pastaba |
|---|---|---|
| `SalesOrder` | id, name, Delivery Date, tags, state | `SKUBUS` yra SO tagas; Reform – vienintelis klientas. |
| `SalesOrderLine` | id, SO id, product, qty, sales value, material cost | Throughput skaičiavimo grūdas. |
| `ManufacturingOrder` | id, source SO / lines, product, qty, state | SO–MO ryšį būtina validuoti. |
| `WorkOrder` | id, MO id, operation, state, planned duration | Assembly operacijos gyvenimo ciklas. |
| `WorkLog` | WO id, employee, start, stop | Darbuotojo aktyvaus laiko ir persijungimo šaltinis. |
| `WorkOrderLoss` | WO id, generic loss, start, end | Odoo turi bendras productivity loss kategorijas; jos nepakeičia detalaus MQ-006 priežasčių katalogo. |
| `BomOperation` | product / BOM, Assembly duration | 1 norminė valanda = 1 žmogaus valanda. |
| `Shipment` | SO / lines, actual shipped timestamp, qty | Validuota per `stock.move.sale_line_id` → `stock.picking.date_done`; daliniai išsiuntimai dažni. |

### 6.2. Product Engine valdomi įvykiai

| Įvykis | Privalomi atributai |
|---|---|
| `DailyAssemblyCapacityConfirmed` | business date, employee count, capacity hours, actor, timestamp |
| `ReadinessCheckStarted` | business date, actor, timestamp |
| `ReadinessConfirmed` | SO / MO, readiness date, actor, check id, rule version |
| `ReadinessRevokedBeforeStart` | SO / MO, reason, actor, timestamp, previous event id |
| `ReadinessBlockerOpened` | SO / MO, reason code, actor, timestamp, optional comment |
| `ReadinessBlockerClosed` | blocker id, actor, timestamp |
| `AssemblyBlockerOpened` | WO, MQ-006 reason code, actor, timestamp, optional comment, Odoo loss reference |
| `AssemblyBlockerClosed` | blocker id, actor, timestamp |
| `DailyPriorityPlanGenerated` | business date, source snapshot id, rule version |
| `DailyPriorityPlanApproved` | plan id, actor, timestamp |
| `PriorityOverrideRecorded` | plan id, SO / MO, old/new position, reason, actor, timestamp |
| `DecisionResultPublished` | question id, period, result, confidence, evidence refs, rule version |
| `ScenarioEvaluated` | assumptions, baseline id, result, actor, timestamp |

Įvykiai nekoreguojami perrašant. Klaida taisoma nauju korekcijos įvykiu, išsaugant istoriją.

### 6.3. Išvedamos būsenos

```text
NOT READY
READY, NOT STARTED
ASSEMBLY WIP ACTIVE
ASSEMBLY WIP PAUSED
ASSEMBLY WIP BLOCKED
ASSEMBLY COMPLETED
SHIPPED
```

`READY FOR ASSEMBLY` patvirtinamas kartą per darbo dieną, kai visi konkrečiam darbui būtini komponentai fiziškai yra DC. Komponentai neprivalo būti surūšiuoti ar pristatyti į darbo vietą.

## 7. Sprendimų varikliai ir MQ atsekamumas

| Variklis | MQ | Įvestys | Pagrindinis rezultatas |
|---|---|---|---|
| `ConstraintSynthesisEngine` | MQ-001 | READY istorija, bufferis, tempas, WIP | late readiness / Assembly / mixed / insufficient |
| `ReadyBufferEngine` | MQ-002 | READY darbai, BOM valandos, C | bufferio dienos ir zona |
| `ReadinessBlockerEngine` | MQ-003 | NOT READY įvykiai, SO rizika | dominuojančios priežastys ir eskalavimas |
| `AssemblyPaceEngine` | MQ-004 | Delivery Date, C, READY, užbaigimai | adequate / capacity / execution / starvation / priority |
| `PriorityEngine` | MQ-005 | READY, overdue, SKUBUS, Delivery Date, READY time | paaiškinama dienos seka |
| `AssemblyLossEngine` | MQ-006 | blocks, work logs, kitas WO, grafikas | block duration ir lost person-hours |
| `ThroughputDelayEngine` | MQ-007 | SO line T agreguotas į SO, shipment, SO priežasties klasė | T at risk, delayed T, T delay-days |
| `WhatIfEngine` | MQ-008 | MQ-001–007 rezultatai, OE / investicija | alternatyvų palyginimas ir pilotas |

Kiekvienas variklis turi būti gryna domeno logika, nepriklausoma nuo HTTP, HTML ir tiesioginio Odoo kliento. Adapteriai paruošia kanoninius duomenis; varikliai grąžina versijuojamus rezultatus.

## 8. Read modeliai ir naudotojo ekranai

### 8.1. Morning Control

Vienas nuoseklus darbo srautas gamybos vadovei:

1. įvesti dirbančių Assembly darbuotojų skaičių;
2. peržiūrėti ankstesnį WIP ir aktyvius BLOCKED WO;
3. kiekvienam kandidatui patvirtinti READY arba aktyvias NOT READY priežastis;
4. sugeneruoti dienos eilę;
5. peržiūrėti netelpančius ir rizikuojančius SO;
6. patvirtinti planą arba audituojamai jį koreguoti.

### 8.2. Live Control

Rodomos tik sprendimo reikalaujančios išimtys:

- READY bufferis raudonas;
- aktyvus BLOCKED WO, dėl kurio prarandamos žmogaus valandos;
- naujas `SKUBUS` po aktyvaus darbo;
- prognozuojamas `Delivery Date` praleidimas;
- darbuotojas neturi kito READY darbo;
- duomenų kokybės klaida.

### 8.3. Weekly Review

- MQ-001 klasifikacija ir pasitikėjimas;
- READY bufferio zona per laiką;
- MQ-003 readiness priežasčių Pareto;
- poreikis, pajėgumas ir užbaigtas tempas;
- MQ-006 block duration ir lost person-hours atskirai;
- `Throughput at risk`, delayed Throughput ir delay-days;
- rekomenduojamas vienas vadybinis fokusas kitai savaitei.

### 8.4. What-if Review

- keturios alternatyvos vienoje palyginimo lentelėje;
- visos prielaidos redaguojamos ir matomos;
- bazinio lango bei taisyklių versija;
- rekomenduojamas pilotas;
- sprendimą patvirtinantis vadovas ir sprendimo data.

## 9. Duomenų srautai

### 9.1. Odoo sinchronizacija

```text
scheduled/manual read
→ raw snapshot
→ schema validation
→ canonical mapping
→ projection rebuild / increment
→ decision engines
→ decision result
```

Reikalavimai:

- tik read-only Odoo credentials;
- kiekvienas snapshot turi `source_read_at`, šaltinio identifikatorius ir adapterio versiją;
- pakartotinis to paties lango skaitymas turi būti idempotentiškas;
- Odoo duomenų dingimas ar schemos pokytis negali tyliai ištrinti ankstesnės audito istorijos;
- nei vienas Odoo adapterio metodas negali turėti create/write/unlink operacijos.

2026-08-21 Production validacija patvirtino, kad tiesioginio SO line–MO ryšio nėra nei modelio lauke, nei per `stock.move` / procurement group. Patikimas gamybos ryšys yra SO lygio `mrp.production.origin`; todėl priežastis priskiriama SO. Negalima automatiškai teigti, kuri konkreti SO line sukūrė konkretų MO. Faktinis išsiuntimas ir jo ekonominė vertė skaidomi SO line lygiu per `stock.move.sale_line_id` → `stock.picking.date_done`, tada agreguojami pagal SO priežasties klasę.

### 9.2. Rytinė patikra

```text
latest Odoo snapshot
+ previous Product Engine events
→ readiness candidates
→ manager confirmation
→ immutable decision events
→ capacity + buffer + priority projections
→ approved daily plan
```

### 9.3. Savaitinė diagnostika

```text
3–4 week event window
+ Odoo actuals
→ MQ-001–MQ-007 engines
→ evidence bundle
→ constraint synthesis
→ weekly decision result
```

### 9.4. What-if

```text
frozen baseline snapshot
+ explicit scenario assumptions
→ replay selected events / capacity
→ compare outcomes
→ recommendation + confidence
```

## 10. Saugykla ir auditas

Product Engine sprendimų būsena turi būti saugoma transakcinėje, patvarioje duomenų bazėje. Railway aplinkoje rekomenduojama PostgreSQL arba lygiavertė patvari reliacinė saugykla; aplikacijos lokalus failų katalogas neturi būti laikomas vieninteliu audito šaltiniu.

Loginės schemos:

- `source_snapshots` – Odoo skaitymo metaduomenys;
- `source_entities` arba normalizuotos Odoo projekcijos;
- `decision_events` – nekintami rankiniai ir sisteminiai įvykiai;
- `current_projections` – greiti ekranų read modeliai;
- `decision_results` – MQ rezultatai, paaiškinimai ir pasitikėjimas;
- `rule_versions` – taisyklių bei kategorijų versijos;
- `scenario_runs` – what-if prielaidos ir rezultatai.

Kiekvienas audituojamas įrašas turi:

- organizacijos / diegimo scope;
- business date ir UTC timestamp;
- actor arba system identity;
- source snapshot / ankstesnio įvykio nuorodą;
- rule version;
- creation timestamp;
- korekcijos ryšį, jei taikoma.

## 11. Taisyklių versijavimas

Versijuojami bent:

- READY apibrėžimas;
- NOT READY priežasčių katalogas;
- BLOCKED priežasčių katalogas;
- bufferio zonų ribos;
- prioritetų seka;
- pajėgumo formulė;
- Throughput formulė;
- constraint klasifikavimo ribos;
- what-if scenarijų logika.

Istorinis rezultatas visada perskaičiuojamas arba rodomas su aiškia taisyklių versija. Nauja taisyklė neturi tyliai pakeisti jau publikuoto vadybinio sprendimo prasmės.

## 12. Pasitikėjimas ir duomenų kokybė

Kiekvienas MQ rezultatas turi `HIGH`, `MEDIUM` arba `LOW` pasitikėjimą.

Pasitikėjimą mažina:

- trūkstamas rytinis READY patvirtinimas;
- NOT READY be priežasties;
- BLOCKED be priežasties;
- SO–MO–WO ryšio spraga arba nepatikimas SO line ekonomikos agregavimas į SO;
- trūkstamas BOM operacijos laikas;
- trūkstamas faktinis išsiuntimas;
- nepatvirtintas dienos darbuotojų skaičius;
- didelė `OTHER` arba `UNKNOWN` dalis;
- nepakankamas 3–4 savaičių langas.

LOW confidence rezultatas negali automatiškai rekomenduoti investicijos į papildomą pajėgumą.

## 13. Saugumas ir teisės

Minimalios rolės:

| Rolė | Teisės |
|---|---|
| **Gamybos vadovė** | READY, blockeriai, dienos C, plano patvirtinimas, prioritetų išimtys, `SKUBUS` valdymas Odoo esamame procese |
| **Assembly darbuotojas** | Savo WO darbo įvykiai Odoo esamame procese; Decision Support pradžioje read-only peržiūra, jei reikalinga |
| **Vadovybė** | Weekly Review, ekonominis poveikis, what-if ir piloto patvirtinimas |
| **System reader** | Tik read-only Odoo integracija ir projekcijų atnaujinimas |
| **Administratorius** | Taisyklių / rolės konfigūracija, bet ne istorinių įvykių perrašymas |

Product Engine negali išsaugoti Production Odoo rašymo kredencialų šiame modulyje.

Dabartinė Product Engine autentifikacija naudoja vieną bendrą slaptažodį ir sesijoje saugo tik `authenticated = true`; individualaus naudotojo identiteto nėra. Tai nepakankama READY, dienos pajėgumo, prioritetų išimčių ir scenarijų auditui. Prieš Manual Decision Event Foundation būtina įdiegti individualų arba patikimai pasirenkamą ir audituojamą aktoriaus identitetą.

## 14. Gedimų elgsena

- Jei Odoo nepasiekiamas, rodomas paskutinio sėkmingo snapshot laikas; nauja išvada nežymima kaip aktuali.
- Jei trūksta rytinės patikros, dienos planas nepatvirtinamas tyliai pagal vakarykščius duomenis.
- Jei nepavyksta susieti SO–MO–WO, įrašas patenka į data quality queue ir neįtraukiamas į tariamai pilną rezultatą.
- Jei darbuotojų skaičius neįvestas, bufferis rodomas valandomis, bet ne darbo dienomis.
- Jei trūksta kainos ar savikainos, operaciniai moduliai veikia, o ekonominis rezultatas rodomas kaip nepilnas.
- Jei taisyklės versija nežinoma, rezultatas nepublikuojamas.

## 15. Įgyvendinimo etapai

Šie etapai yra būsimo darbo seka, ne autorizacija pradėti koduoti.

### Etapas A – Data contract validation

- read-only validuoti SO–MO–WO ryšius ir SO line ekonomikos agregavimą į SO;
- validuoti `Delivery Date`, `SKUBUS`, BOM laikus, work logs, blocks ir shipment timestamp;
- patvirtinti dalinių išsiuntimų semantiką;
- parengti kanoninių modelių testinius pavyzdžius be Odoo rašymo.

### Etapas B – Manual decision event foundation

- rytinis darbuotojų skaičius;
- READY / NOT READY ir kelios priežastys;
- dienos plano generavimo snapshot bei patvirtinimas;
- pilnas auditas.

### Etapas C – SCHEDULE MVP

- READY bufferis;
- patvirtinta MQ-005 eilė;
- dienos darbuotojų paskirstymo rekomendacija;
- rizikuojančių SO rodymas.

### Etapas D – CONTROL MVP

- MQ-001–MQ-004 diagnostika;
- BLOCKED priežastys ir realiai prarastos žmogaus valandos;
- savaitinis sprendimų review;
- pasitikėjimo ir data quality mechanizmas.

### Etapas E – Economic control

- SO line Throughput;
- atidėto Throughput priskyrimas;
- delay-days;
- ekonominio poveikio Pareto.

### Etapas F – WHAT-IF

- keturi scenarijai;
- OE / investicijos įvestys;
- rekomenduojamas pilotas;
- rezultatų palyginimas su faktu.

## 16. Architektūros priėmimo kriterijai

Architektūra laikoma parengta implementacijos planavimui, kai patvirtinta:

1. Production Odoo read-only riba;
2. SO–MO–WO atsekamumas ir SO line ekonomikos agregavimas į SO;
3. Product Engine įvykių saugyklos technologija;
4. rytinės patikros ir dienos plano UX;
5. taisyklių bei audito versijavimas;
6. bufferio, prioriteto, tempo ir nuostolių variklių atsakomybės;
7. Throughput formulės sąnaudų apimtis;
8. dalinių išsiuntimų taisyklė;
9. pasitikėjimo ir data quality blokavimo taisyklės;
10. etapų A–F priėmimo kriterijai.

## 17. Atviri techninės validacijos klausimai

1. Ar Odoo block reason ir work log istorija pateikia visas MQ-006 reikalingas pradžios / pabaigos reikšmes, ar detalūs intervalai visiškai priklausys Product Engine įvykiams?
2. Ar `SKUBUS` tago pakeitimo auditą galima perskaityti, ar Product Engine turi saugoti tik snapshot pokytį?
3. Kaip SO line medžiagų savikainoje atvaizduojamos subrangovų sąnaudos?
4. Kuri patvari DB technologija ir migracijų mechanizmas bus standartas šiame Railway diegime?

## 18. Sprendimo santrauka

Furnibox TOC Decision Support nėra dar vienas KPI dashboardas. Tai trijų sluoksnių informacinis produktas:

```text
SCHEDULE
Kas turi būti daroma šiandien?

CONTROL
Ar srautas apsaugotas, kur yra nuokrypis ir ką eskaluoti?

WHAT-IF
Kuris mažiausias pakeitimas duotų didžiausią pamatuojamą poveikį?
```

Odoo lieka read-only operacinių faktų šaltinis. Product Engine saugo tik jam priklausančius vadybinių sprendimų įvykius, vykdo versijuotą sprendimo logiką ir pateikia audituojamus atsakymus bei rekomenduojamus veiksmus.
