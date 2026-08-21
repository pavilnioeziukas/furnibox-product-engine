# TOC Odoo duomenų kontrakto validacija – 2026-08-21

Statusas: Etapas A, Production Odoo read-only validacija.

Susiję dokumentai:

- [`toc-management-question-catalog.md`](toc-management-question-catalog.md)
- [`TOC_DECISION_SUPPORT_ARCHITECTURE.md`](TOC_DECISION_SUPPORT_ARCHITECTURE.md)

## 1. Saugumo riba

Validacija vykdyta naudojant tik šiuos XML-RPC metodus:

- `fields_get`;
- `search_count`;
- `search_read`;
- `read`.

Validatorius neleidžia kviesti kitų metodų. Production Odoo nebuvo vykdyti `create`, `write`, `unlink`, `export_data`, importai ar kitos būseną keičiančios operacijos. Prisijungimo reikšmės nebuvo kopijuotos į repozitoriją ar ataskaitą.

Agreguotas mašininis rezultatas sugeneruotas į git ignoruojamą `output/toc_contract/production_contract_20260821.json`. Jame nėra API rakto ar raw SO pavadinimų.

## 2. Imtis

Galutinės validacijos momentas: `2026-08-21T06:39:37Z`.

| Sritis | Imtis / apimtis |
|---|---:|
| Naujausi patvirtinti / užbaigti SO | 200 |
| Jų SO line | 2 000 |
| Pagal tikslų SO `origin` rasti MO | iki 2 000 imties ribos |
| Šių MO WO | 2 678 |
| Assembly darbo centro WO | 1 988 |
| Assembly productivity įrašai | 1 529 |
| Su SO susieti pickingai | 857 |
| Patikrinti Odoo modeliai | 12 |

Production objektų bendri skaičiai validacijos metu:

| Modelis | Įrašai |
|---|---:|
| `sale.order` | 4 250 |
| `sale.order.line` | 122 647 |
| `mrp.production` | 52 648 |
| `mrp.workorder` | 23 715 |
| `mrp.workcenter.productivity` | 22 221 |
| `mrp.workcenter.productivity.loss` | 7 |
| `mrp.routing.workcenter` | 6 825 |
| `mrp.bom` | 11 072 |
| `stock.picking` | 32 460 |
| `stock.move` | 633 644 |

## 3. Patvirtinti kontrakto elementai

### SO ir įsipareigojimai

- `sale.order.commitment_date` egzistuoja ir 200/200 imties SO užpildytas.
- `sale.order.tag_ids` egzistuoja ir 200/200 imties SO turi bent vieną tagą.
- Egzistuoja tiksliai vienas `SKUBUS` tagas.
- Production iš viso `SKUBUS` tagą turi 87 SO; naujausių 200 SO imtyje – 1 SO.
- `stock.picking.sale_id` ir `date_done` egzistuoja.
- 457/457 pirmosios imties užbaigtų pickingų turėjo `date_done`.

### SO ir gamybos srautas

- `mrp.production.origin` patikimai gali būti lyginamas su SO pavadinimu.
- Iš 200 SO imties 149 turi bent vieną MO su tiksliu SO `origin`.
- 51 SO tokio MO neturi; nė vienas iš jų neturėjo ir dalinio / nestandartinio `origin` atitikmens pagal `ilike`. Tai stipriai patvirtina Furnibox packing-only ir assembly+packing srautų atskyrimą.
- `mrp.production.workorder_ids` ir `mrp.workorder.production_id` egzistuoja.
- Rastas vienas darbo centras, kurio pavadinimas identifikuoja Assembly / surinkimą.

### Assembly operacijos

- Assembly WO turi `duration_expected`, `duration`, `date_start`, `date_finished` ir `time_ids`.
- 1 988 Assembly WO norminis `duration_expected` pasiskirstymas: minimumas 30, mediana 60, maksimumas 120.
- Šios reikšmės yra Odoo minutės, todėl kanoniniame modelyje turi būti konvertuojamos į žmogaus valandas dalijant iš 60.
- Assembly productivity įrašuose `employee_id` užpildytas 100 %.
- Assembly productivity įrašuose `loss_id` užpildytas 100 %.
- Darbuotojo perėjimą prie kito WO galima nustatyti pagal kito productivity įrašo `date_start`.

### BOM ir ekonomika

- `mrp.routing.workcenter.time_cycle` egzistuoja.
- `sale.order.line.price_subtotal`, `purchase_price` ir `margin` egzistuoja.
- `purchase_price` laukas 2 000/2 000 imties SO line turi reikšmę, įskaitant teisėtą nulį.
- SO line pardavimo vertę ir medžiagų savikainą galima agreguoti į SO Throughput.
- Imtyje buvo 320 užbaigtų outbound pickingų ir 2 095 jų `stock.move` eilutės.
- Visos 2 095 / 2 095 outbound move eilutės turėjo `sale_line_id`.
- 99 SO imtyje turėjo daugiau nei vieną faktinę išsiuntimo datą, todėl daliniai išsiuntimai yra reikšmingas realus scenarijus.
- Faktinį SO line išsiuntimo laiką galima nustatyti per `stock.move.sale_line_id` → `stock.picking.date_done`.

## 4. Riboti arba netinkami kontrakto elementai

### Nėra tiesioginio SO line–MO ryšio

Nerasti:

- `sale.order.line.production_ids`;
- `sale.order.line.mrp_production_ids`;
- `mrp.production.sale_line_id`;
- tiesioginės poros per `stock.move.sale_line_id` + `production_id`;
- tiesioginės poros per `stock.move.sale_line_id` + `raw_material_production_id`;
- patikimas bendras procurement group tiltas tarp SO line ir MO.

Vien SO `origin` + produkto atitikimas taip pat nėra pakankamas: 2 000 SO line imtyje tik 19 turėjo vieną kandidatą, 20 – kelis kandidatus, o 1 961 – nė vieno to paties produkto MO. Tai tikėtina dėl transformuoto / tarpinio gamybos produkto struktūros.

**Architektūros sprendimas:**

- gamybos ir vėlavimo priežastis priskiriama SO lygiu per `mrp.production.origin`;
- SO line Throughput agreguojamas į SO;
- sistema neteigia, kad konkretus MO priklauso konkrečiai SO line;
- vėlavimo priežastis lieka SO lygio, tačiau ekonominę vertę ir faktinį išsiuntimo laiką galima skaidyti SO line lygiu per picking / move ryšius.

### `working_state` netinka WO blokavimo būsenai

Visi 1 988 Assembly WO imtyje turėjo `working_state = done`, nors jų faktinės `state` reikšmės buvo:

- `done`: 1 119;
- `waiting`: 488;
- `ready`: 301;
- `cancel`: 65;
- `progress`: 15.

**Architektūros sprendimas:** WO gyvenimo ciklui naudoti `state`, pradžios / pabaigos laukus ir productivity įvykius. `working_state` nelaikyti patikimu kontrolės šaltiniu šioje instaliacijoje.

### Odoo loss kategorijos per bendros MQ-006

Production turi septynias kategorijas:

| Kategorija | Tipas | Rankinė |
|---|---|---|
| Fully Productive Time | productive | ne |
| Material Availability | availability | taip |
| Equipment Failure | availability | taip |
| Setup and Adjustments | availability | taip |
| Reduced Speed | performance | ne |
| Process Defect | quality | taip |
| Reduced Yield | quality | taip |

Assembly productivity imtyje faktiškai naudota:

- `Fully Productive Time`: 1 332;
- `Reduced Speed`: 197.

Imtyje nėra detalaus Furnix detalės, subrangovo fasado, stalčiaus, informacijos ar vadovo sprendimo blokavimo atskyrimo.

**Architektūros sprendimas:**

- Odoo productivity loss lieka read-only aukšto lygio faktas;
- detalus MQ-006 priežasties kodas saugomas Product Engine `AssemblyBlockerOpened` / `AssemblyBlockerClosed` įvykiuose;
- jei yra Odoo loss įrašas, Product Engine įvykis gali saugoti jo nuorodą;
- Production Odoo kategorijos šiame etape nekeičiamos.

## 5. MQ atsekamumo būklė

| MQ | Būklė po Etapo A | Pastaba |
|---|---|---|
| MQ-001 | Įgyvendinama | Reikia naujų READY įvykių ir 3–4 savaičių lango. |
| MQ-002 | Įgyvendinama | BOM / WO minutės konvertuojamos į valandas; dienos darbuotojų skaičius bus rankinis. |
| MQ-003 | Reikia Product Engine įvykių | Odoo neturi pilno BOM ir subrangovų gavimo fakto. |
| MQ-004 | Įgyvendinama | Delivery Date, WO laikai ir planinis C prieinami / apibrėžti. |
| MQ-005 | Įgyvendinama | `SKUBUS`, Delivery Date ir READY seka prieinami; override auditas naujas. |
| MQ-006 | Ribotai iš Odoo | Darbuotojo laikas prieinamas, detalios blocker priežastys – nauji Product Engine įvykiai. |
| MQ-007 | Įgyvendinama SO lygiu | SO line ekonomika agreguojama į SO; tiesioginio line–MO ryšio nėra. |
| MQ-008 | Įgyvendinama po istorijos | Reikia MQ-001–MQ-007 faktinio lango ir alternatyvų OE / investicijos įvesčių. |

## 6. Dar atviri patikrinimai

1. Patikrinti, ar `purchase_price` visuose aktualiuose produktuose tiksliai atitinka TOC visiškai kintamas medžiagų ir subrangovų sąnaudas.
2. Pasirinkti patvarią Product Engine įvykių DB ir migracijų mechanizmą.

## 7. Product Engine autentifikacijos išvada

Dabartinis web sluoksnis tikrina vieną bendrą `PRODUCT_ENGINE_WEB_PASSWORD` / `FURNIBOX_WEB_PASSWORD` ir sesijoje saugo tik `authenticated = true`. Individualaus naudotojo arba rolės identiteto nėra.

Tai nepakankama šiems privalomiems auditams:

- kas patvirtino READY;
- kas įvedė dienos darbuotojų skaičių;
- kas pakeitė rekomenduotą seką;
- kas atidarė ar uždarė detalų blockerį;
- kas patvirtino what-if pilotą.

**Architektūros sprendimas:** Manual Decision Event Foundation etape būtinas individualus arba patikimai audituojamas aktoriaus identitetas. Vien bendros autentifikuotos sesijos naudoti įvykio `actor` laukui negalima.

## 8. Etapo A išvada

Duomenų kontraktas yra pakankamas pradėti Manual Decision Event Foundation projektavimą, bet su dviem privalomomis ribomis:

1. MQ-007 priežasties priskyrimo grūdas yra **SO**, o dalinio išsiuntimo ekonominis laikas ir vertė skaidomi **SO line** lygiu.
2. MQ-003 ir detalios MQ-006 priežastys yra **Product Engine valdomi audito įvykiai**, ne retrospektyviai iš Odoo išvedami faktai.

Production Odoo validacijos metu nepakeista.
