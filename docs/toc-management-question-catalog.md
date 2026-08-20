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

## MQ-001 — Kas šiuo metu riboja Furnibox Throughput?

### 1. Vadybinis klausimas

**Kas šiuo metu riboja Furnibox galimybę laiku išsiųsti daugiau užsakymų ir generuoti daugiau Throughput: DC Assembly pajėgumas, DC Packaging pajėgumas ar upstream prieinamumas iki Assembly?**

Klausimo laiko horizontas turi būti nurodomas kartu su atsakymu. Pradiniam diagnostikos etapui siūlomas slenkantis 3–4 savaičių stebėjimo langas po to, kai pradedami patikimai registruoti READY įvykiai. Atsakymas neturi būti išvedamas vien iš vėluojančių užsakymų skaičiaus ar darbuotojų užimtumo.

### 2. Sprendimas, kurį atsakymas keičia

| Atsakymas | Keičiamas vadybinis sprendimas ir veiksmas |
|---|---|
| **Assembly riboja Throughput** | Apsaugoti ir maksimaliai išnaudoti Assembly: užtikrinti nuolatinę prioritetizuotą READY eilę, šalinti Assembly pajėgumo praradimus, subordinuoti upstream ir Packaging Assembly ritmui; tik po išnaudojimo vertinti papildomą Assembly pajėgumą. |
| **Packaging riboja Throughput** | Apsaugoti ir maksimaliai išnaudoti Packaging: valdyti bendrą packing-only ir assembly+packing srautų prioritetą, šalinti Packaging pajėgumo praradimus; tik po išnaudojimo vertinti papildomą Packaging pajėgumą. |
| **Upstream prieinamumas riboja srautą** | Nedidinti Assembly pajėgumo vien dėl Assembly užsakymų vėlavimo. Spręsti komponentų, kliento tiekiamų fasadų / stalčių, Furnix detalių, kitting, rūšiavimo, vidinės logistikos, informacijos arba prioritetų prieinamumą, dėl kurio Assembly neturi paruošto darbo. |
| **Signalas nepakankamas arba constraint migruoja** | Nepriimti pajėgumo investicijos sprendimo. Tęsti matavimą, tikslinti READY apibrėžimus ir analizuoti atskirus laiko langus / srautus. |

### 3. Sprendimo logika

#### 3.1. Srauto modelis

Vertinami du srautai:

```text
packing-only:       READY FOR PACKING → Packaging → Packed / Shipped
assembly+packing:   upstream → READY FOR ASSEMBLY → Assembly
                              → READY FOR PACKING → Packaging → Packed / Shipped
```

`READY FOR ASSEMBLY` reiškia pirmą momentą, kai konkrečiam Assembly MO fiziškai ir informaciškai prieinami visi darbui pradėti būtini komponentai, įskaitant kliento tiekiamus fasadus ir stalčius, ir nėra kitos žinomos pradžią blokuojančios sąlygos. Vien Odoo rezervacija arba Furnix detalių atvykimas savaime nėra pakankamas READY įrodymas.

`READY FOR PACKING` reiškia pirmą momentą, kai konkretaus užsakymo pakavimo darbą fiziškai ir informaciškai galima pradėti. Tikslus šios būsenos verslo apibrėžimas turi būti patvirtintas prieš duomenų rinkimą.

#### 3.2. Diagnostikos signalai

Sprendimo procedūra turi vertinti ne vieną tašką, o eilių dydžio, senėjimo ir užbaigimo dinamiką per pasirinktą laiko langą.

| Stebimas raštas | Klasifikacija |
|---|---|
| Prieš Assembly nuolat yra paruošto darbo eilė, ji sensta arba auga, o po Assembly analogiška Packaging eilė nėra sistemingai dominuojanti. | **Assembly constraint kandidatas.** |
| Prieš Packaging nuolat kaupiasi ir sensta bendras packing-only bei assembly+packing darbas; surinkti gaminiai laukia pakavimo. | **Packaging constraint kandidatas.** |
| Klientų užsakymai vėluoja, bet Assembly READY eilė dažnai tuščia arba per maža stabiliam darbui; laikas daugiausia prarandamas iki `READY FOR ASSEMBLY`. | **Upstream availability / flow constraint kandidatas.** |
| Skirtingais laikotarpiais dominuoja skirtingos eilės arba duomenų kokybė neleidžia atskirti būsenų. | **Migruojantis constraint arba nepakankamas signalas.** |

Constraint klasifikacija laikoma pakankama vadybiniam sprendimui tik tada, kai signalas kartojasi per sutartą langą ir alternatyvi hipotezė nėra geriau paaiškinama trūkstamu READY įvykiu. Pradinės kiekybinės ribos (pvz., eilės dienos, stebėjimų dalis, seniausio darbo amžius) turi būti kalibruojamos iš pirmųjų 3–4 savaičių patikimų duomenų; jų negalima iš anksto pateikti kaip empirinio fakto.

#### 3.3. Apsaugos nuo klaidingos išvados

- Assembly užsakymų vėlavimas pats savaime neįrodo, kad Assembly yra constraint.
- Darbas, kuriam trūksta bet kurio būtino komponento, nepriklauso Assembly READY eilei.
- Žemas lokalus utilization neįrodo perteklinio pajėgumo, o aukštas utilization neįrodo sistemos constraint.
- Packing-only ir assembly+packing srautai turi būti matomi atskirai, nes Packaging yra bendras jų resursas.
- Istorinis `READY FOR ASSEMBLY` momentas negali būti patikimai atkurtas iš dabartinių Odoo duomenų; retrospektyvinė išvada turi būti žymima kaip nepatikima, o ne pateikiama kaip faktas.
- Constraint yra sistemos savybė pasirinktame laiko lange, ne nuolatinė darbo centro etiketė.

### 4. Required data (reikalingi duomenys)

Minimalus sprendimo procedūros duomenų rinkinys vienam užsakymui / darbui:

| Duomuo | Paskirtis |
|---|---|
| Srauto tipas: `packing-only` arba `assembly+packing` | Atskirti Packaging bendrą apkrovą nuo tik Assembly reikalaujančio srauto. |
| Užsakymo, Assembly MO ir susijusio Packaging darbo stabilūs identifikatoriai | Susieti vieno klientų poreikio būsenas per visą srautą. |
| Pažadėta / planuota išsiuntimo data | Nustatyti Throughput riziką ir eilės prioritetą. |
| `READY FOR ASSEMBLY` timestamp ir būsenos versija | Nustatyti, kada darbas realiai pateko į Assembly valdomą eilę. |
| Assembly pradžios ir užbaigimo timestamp | Matuoti laukimą po READY, užbaigimo tempą ir darbų išėjimą. |
| `READY FOR PACKING` timestamp ir būsenos versija | Nustatyti, kada darbas realiai pateko į Packaging valdomą eilę. |
| Packaging pradžios ir užbaigimo timestamp | Matuoti laukimą po READY, užbaigimo tempą ir darbų išėjimą. |
| Packed / shipped timestamp | Susieti operacinį srautą su laiku realizuotu išsiuntimu. |
| Kiekis ir vienodas darbo / srauto svorio matas | Neleisti skirtingo dydžio darbų klaidingai lyginti vien pagal MO skaičių. Pradinis matas turi būti patvirtintas. |
| READY būsenos atšaukimas ir priežastis, jei vėliau paaiškėja blokatorius | Išlaikyti teisingą eilės istoriją ir duomenų auditą. |
| Snapshot / event timestamp | Atkurti eilės dydį ir amžių bet kuriuo stebėjimo momentu. |

Papildomi, bet ne pradinės klasifikacijos būtini duomenys:

- darbo grafikai ir realiai prieinamos Assembly / Packaging valandos;
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
- atsargų judėjimai, rezervacijos ir komponentų sąrašai;
- pakavimo / pristatymo operacijų būsenos ir užbaigimo datos;
- produktų kiekiai ir maršrutai.

#### Išvedami duomenys — tik patvirtinus šaltinių semantiką

- srauto tipas `packing-only` / `assembly+packing`;
- dabartinė READY eilė, jos dydis, amžius ir seniausias darbas;
- savaitinis įėjimo į eilę ir užbaigimo tempas;
- OTD palyginimas tarp dviejų srautų;
- galimas `READY FOR PACKING` momentas, jei verslo procesas ir esami įvykiai leidžia jį nustatyti be dviprasmybės.

#### Kritiškai trūkstami duomenys

- patikimas istorinis ir nuo šiol registruojamas `READY FOR ASSEMBLY` timestamp;
- patvirtintas `READY FOR ASSEMBLY` verslo apibrėžimas, apimantis kliento tiekiamus fasadus / stalčius ir fizinį, ne vien sisteminį, prieinamumą;
- patikimas `READY FOR PACKING` timestamp, jei jo negalima vienareikšmiškai išvesti;
- READY būsenos atšaukimo įvykis, kai darbas po pažymėjimo vėl tampa neprieinamas;
- patvirtintas darbo svorio matas, leidžiantis palyginti nevienodo dydžio darbus.

**Duomenų spraga, dėl kurios šiandien negalimas patikimas retrospektyvus atsakymas:** iš Odoo negalima nustatyti pirmo momento, kai konkrečiam Assembly MO vienu metu fiziškai buvo prieinami visi reikalingi komponentai, įskaitant kliento tiekiamas dalis. Todėl istoriniai vėlavimai negali patikimai atskirti Assembly pajėgumo trūkumo nuo Assembly badavimo dėl upstream prieinamumo.

### 6. Būsimas Product Engine modulis

Darbinis modulio pavadinimas: **TOC Constraint Diagnostic**.

Modulio atsakomybė — vykdyti formalizuotą sprendimo procedūrą ir pateikti ne vien žalius KPI, o audituojamą atsakymą:

```text
Vertinimo langas: 2026-XX-XX – 2026-XX-XX
Išvada: Assembly / Packaging / Upstream / Nepakanka duomenų
Pasitikėjimas: aukštas / vidutinis / žemas
Sprendimą pagrindžiantys signalai: ...
Duomenų spragos ir alternatyvios hipotezės: ...
Rekomenduojamas vadybinis veiksmas: ...
```

Numatomos, bet dar neprojektuojamos produkto architektūros dalys:

1. **Event / Readiness Contract** — READY būsenų semantika, versijavimas ir auditas.
2. **Flow Timeline** — vieno užsakymo įvykių seka per upstream, Assembly ir Packaging.
3. **Buffer Control** — READY eilių dydis, amžius, įėjimo ir išėjimo tempas.
4. **Constraint Classifier** — sprendimo taisyklės, alternatyvių hipotezių ir duomenų kokybės patikra.
5. **Decision Output** — išvada, paaiškinimas ir konkretus veiksmas vadovui.
6. **What-if** (vėlesnis etapas) — poveikio modeliavimas pakeitus Assembly, Packaging ar upstream pajėgumą / patikimumą.

Modulio projektavimas ir implementavimas pradedamas tik patvirtinus MQ-001 sprendimo logiką bei READY būsenų verslo apibrėžimus.

## Atviri patvirtinimo klausimai

1. Koks tikslus fizinis ir informacinis kriterijų rinkinys reiškia `READY FOR ASSEMBLY` Furnibox procese?
2. Kas, kada ir kokiu įvykiu patvirtina READY būseną; kaip registruojamas jos atšaukimas?
3. Ar `READY FOR PACKING` galima vienareikšmiškai išvesti iš esamų Odoo įvykių abiem srautams?
4. Koks pradinis darbo svorio matas tinkamiausias eilių palyginimui: standartinės darbo minutės, vienetai, užsakymų pozicijos ar kitas matas?
5. Koks vadybinio sprendimo ritmas: kasdienė kontrolė, savaitinė constraint peržiūra ar abu?
6. Kiek savaičių duomenų ir kokio signalo stabilumo reikia prieš priimant pajėgumo investicijos sprendimą?

## Kitas specifikacijos etapas

Patvirtinus MQ-001, katalogą tęsti bent šiais klausimais:

- Kiek Throughput prarandame dėl dabartinio constraint?
- Kas konkrečiai neleidžia maksimaliai išnaudoti dabartinio constraint?
- Ar likusi sistema subordinuota constraint prioritetui?
- Kurie užsakymai geriausiai naudoja ribojantį resursą?
- Kuris constraint taps kitu, jeigu pašalinsime dabartinį?

Kiekvienas klausimas turi būti aprašytas ta pačia pilna struktūra ir atmestas, jei jo atsakymas nekeičia sprendimo.
