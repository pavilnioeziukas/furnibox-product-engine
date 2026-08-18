# Product Engine architektūra

## Atsakomybės

`Product Engine` karkasas valdo žiniatinklio sąsają, autentifikaciją, darbų
eilę, rezultatų failus ir papildinių registrą. Karkasas neturi žinoti konkretaus
kliento Odoo lokacijų, kategorijų ar verslo taisyklių.

Bendra biblioteka vadinama `odoo-tools`. Joje gali būti tik pakartotinai
naudojami Odoo elementai: tik skaitymo klientas, konfigūracija, UoM konversija,
ataskaitų bazinės klasės ir bendri Excel eksporto įrankiai. Istorinis
`furnibox-odoo-tools` pavadinimas laikomas pereinamuoju ir neturi būti naudojamas
naujiems klientams.

Kiekvienas klientas turi atskirą repozitoriją ir Railway projektą. Kliento
repozitorijoje laikomi jo veiksmai, ataskaitos, lokacijų parinkimas, tekstai bei
prekės ženklas.

## Papildiniai

Papildinio Python modulis turi pateikti `ACTIONS` žodyną arba funkciją
`register_actions()`. Modulis įjungiamas per `PRODUCT_ENGINE_ACTION_MODULES`, o
konkrečiam diegimui matomi veiksmai pasirenkami per
`PRODUCT_ENGINE_ENABLED_ACTIONS`.

Pavyzdžiui, Furnix diegimas gali naudoti:

```text
PRODUCT_ENGINE_BRAND=Furnix
PRODUCT_ENGINE_APP_NAME=Furnix Product Engine
PRODUCT_ENGINE_ACTION_MODULES=furnix_engine.actions
PRODUCT_ENGINE_ENABLED_ACTIONS=stock_by_location
PRODUCT_ENGINE_SHOW_BOM_WORKSPACE=false
PRODUCT_ENGINE_SHOW_PRICING_NAV=false
```

Neįvardijus naujų kintamųjų, dabartinis Furnibox diegimas veikia kaip anksčiau.
Pereinamuoju laikotarpiu palaikomi esami `FURNIBOX_*` kintamieji.

## Tolimesnė migracija

1. Bendrą Odoo kodą perkelti į neutralią `odoo-tools` repozitoriją ir vardų
   erdvę.
2. Furnibox specifines ataskaitas palikti `furnibox-product-engine`.
3. Sukurti `furnix-product-engine`, kuris priklauso nuo `odoo-tools` ir turi tik
   Furnix papildinius.
4. Seną `furnibox-odoo-tools` priklausomybę pašalinti tik po to, kai abu
   Product Engine diegimai naudoja naują paketą.
