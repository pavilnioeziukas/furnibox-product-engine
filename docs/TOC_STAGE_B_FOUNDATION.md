# TOC etapas B – audituojamų sprendimų pagrindas

Statusas: pirmoji techninė dalis parengta; Production Odoo nerašoma.

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

Ant šio pagrindo kuriamas vienas rytinis darbo srautas:

1. dienos Assembly darbuotojų skaičius ir 8 val. pajėgumo patvirtinimas;
2. READY / NOT READY patikra su keliomis vienu metu galiojančiomis priežastimis;
3. dienos plano snapshot;
4. plano patvirtinimas ir audituojamos eilės išimtys.

Odoo šiame sraute lieka tik skaitomas faktų šaltinis.
