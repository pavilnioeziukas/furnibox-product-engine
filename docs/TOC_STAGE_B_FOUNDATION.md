# TOC etapas B – audituojamų sprendimų pagrindas

Statusas: individualių paskyrų, audito ir pirmojo rytinio darbo srauto dalis parengta; Production Odoo nerašoma.

## Priimti sprendimai

- Patvari saugykla: PostgreSQL (`DATABASE_URL`).
- Kiekvienas žmogus jungiasi individualia paskyra.
- Pradinės rolės: gamybos vadovė, vadovybė, administratorius ir sisteminis skaitytojas.
- Vadybiniai sprendimai saugomi kaip nekintami įvykiai. Klaidos netaisomos perrašant istoriją – registruojamas naujas korekcijos įvykis.
- Kiekvienas įvykis turi aktorių, darbo datą, tikslų UTC laiką, taisyklės versiją, organizacijos ribą ir turinį.

## Parengtas pagrindas

- individualių paskyrų saugojimas ir saugus slaptažodžių maišos tikrinimas;
- rolės;
- pradinis administratoriaus sukūrimas tuščioje DB iš saugių aplinkos kintamųjų;
- sprendimų įvykių lentelė ir draudimas keisti ar šalinti jau įrašytą įvykį;
- korekcijos ryšys su ankstesniu įvykiu;
- B etapui patvirtintų įvykių tipų katalogas;
- senasis bendras Product Engine slaptažodis veikia tik kol individualių paskyrų lentelė tuščia. Sukūrus pirmą individualią paskyrą bendras prisijungimas automatiškai išjungiamas.

## Railway paruošimas

Diegime turi būti prijungta PostgreSQL paslauga ir nustatyti:

```text
DATABASE_URL=<Railway PostgreSQL ryšys>
PRODUCT_ENGINE_INITIAL_ADMIN_USERNAME=<pradinis administratorius>
PRODUCT_ENGINE_INITIAL_ADMIN_PASSWORD=<stiprus laikinas slaptažodis>
PRODUCT_ENGINE_WEB_SECRET=<pastovi stipri sesijos paslaptis>
```

Pirmasis administratorius sukuriamas tik tada, kai naudotojų lentelė tuščia. Vėliau naują paskyrą galima sukurti saugiu administraciniu paleidimu:

```text
python create_toc_user.py vardas --role production_manager
```

Slaptažodis perduodamas interaktyviai ir nepatenka į komandų istoriją.

## Kitas B etapo pjūvis

Parengtas pirmasis ekranas **Rytinė kontrolė** leidžia gamybos vadovei:

- patvirtinti dienos Assembly darbuotojų skaičių ir automatiškai apskaičiuoti `C = darbuotojai × 8 val.`;
- pradėti audituojamą rytinę READY patikrą;
- patvirtinti konkretų SO kaip READY;
- pažymėti vieną arba kelias vienu metu galiojančias NOT READY priežastis;
- nedubliuoti jau aktyvios tos pačios priežasties;
- patvirtinus READY uždaryti visas aktyvias to SO NOT READY priežastis;
- matyti tos dienos veiksmų auditą suprantamais pavadinimais.

2026-08-21 automatinė kandidatų atranka patikrinta Production Odoo tik skaitymo režimu. Ji rado 91 tikrintiną surenkamą SO, 619,09 standartinės Assembly valandos, vieną `SKUBUS` ir nė vieno WO be tikslaus SO ryšio. Visos 91 `Delivery Date` reikšmės buvo užpildytos. Šie skaičiai yra konkretaus nuskaitymo momentinė būsena, ne pastovus proceso dydis.

Parengtas ir dienos plano snapshot bei patvirtinimas:

- į planą patenka tik Product Engine įvykiu patvirtinti READY kandidatai;
- 1 prioritetas – vėluojantys READY, nuo seniausios `Delivery Date`;
- 2 prioritetas – nevėluojantys `READY + SKUBUS`, nuo artimiausios `Delivery Date`;
- 3 prioritetas – kiti READY, nuo artimiausios `Delivery Date`;
- vienodos datos sprendžiamos pagal ankstesnę READY darbo datą;
- darbas žymimas šiandienos planu, jei jo pradžios momentu kumuliacinės valandos dar nepasiekė `C`; todėl paskutinis nedalomas darbas gali persikelti už C ribos;
- snapshot išsaugo visą eilę, Odoo nuskaitymo laiką, pajėgumo įvykio nuorodą, taisyklės versiją ir kiekvieno darbo paaiškinimą;
- gamybos vadovė patvirtina konkrečią nekintamą snapshot versiją; vėliau sugeneruota versija vėl reikalauja atskiro patvirtinimo.

### Likusi B etapo dalis

Ant šio pagrindo kuriamas vienas rytinis darbo srautas:

1. audituojamos rankinės eilės išimtys;
2. vieno darbuotojo aktyvaus darbo apsauga, kad dieną atsiradęs `SKUBUS` būtų pirmas tik po jo.

Odoo šiame sraute lieka tik skaitomas faktų šaltinis.
