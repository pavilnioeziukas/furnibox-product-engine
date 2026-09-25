"""User-facing catalogue of business reports."""
from flask import Blueprint, current_app, render_template

reports = Blueprint('reports', __name__)

# Link to existing screens and action forms; opening the catalogue never starts a job.
CATALOGUE = [
    ('Pardavimai', [
        ('Cabinet ir shelf kiekiai', 'Patvirtintų SO ir sąskaitų kiekiai, atėmus kreditines. Spintelės pagal tipus.', 'sales_quantities.index', None, 'Peržiūra'),
        ('SO tiekimo būklė', 'Konkretaus SO gamybos poreikis ir detalių vieta tiekimo grandinėje.', 'index', 'so_supply_status', 'Generuojama ataskaita'),
        ('SO komponentų rezervacijos', 'Gamybos komponentų poreikis, rezervuoti kiekiai ir trūkumai pagal SO.', 'index', 'so_reservation_audit', 'Generuojama ataskaita'),
    ]),
    ('Pirkimai ir kainos', [
        ('Detalių kainų palyginimas', 'Reform pardavimo, Furnibox pirkimo ir apskaičiuotų Furnix kainų palyginimas. Galimas Excel eksportas.', 'furnibox_comparison.index', None, 'Kainų peržiūra'),
        ('Reform kainų peržiūra', 'Reform kainodaros rezultatai, kainų šaltiniai ir skaičiavimo paaiškinimai.', 'pricing_control', None, 'Kainų peržiūra'),
        ('Paskutinės pirkimo kainos', 'Paskutinių faktinių pirkimo kainų failas Last_Purchase_Prices.xlsx.', 'index', 'purchase_prices', 'Generuojama ataskaita'),
        ('Pirkimo kainos ir Tamaros korekcijos', 'Tamaros peržiūros failo paruošimo eiga, korekcijų įkėlimas ir pirkimo kainų parametrai.', 'purchase_pricing', None, 'Kainų valdymas'),
    ]),
    ('Sandėlis ir tiekimas', [
        ('SKU likučiai pagal lokaciją', 'Likučiai WH/Stock ir C/Stock bei paskutiniai faktiniai pirkimų gavimai.', 'index', 'stock_by_location', 'Generuojama ataskaita'),
        ('Tiekimo grandinių auditas', 'Vidinių perkėlimų būklė, aktyvūs MO su išrašytais SO ir WH/Input-Custom likučiai.', 'index', 'odoo_supply_chain_audit', 'Generuojama ataskaita'),
    ]),
    ('Gamyba ir produktai', [
        ('Gamybos komponentų sunaudojimas', 'Užbaigtų MO planuoti, faktiškai sunaudoti ir trūkstami komponentų kiekiai.', 'index', 'mo_component_consumption_audit', 'Generuojama ataskaita'),
        ('Produktų ir BOM aktualumas', 'Likučiai, aktyvūs dokumentai, BOM priklausomybės ir archyvavimo kandidatai.', 'index', 'product_lifecycle_audit', 'Generuojama ataskaita'),
        ('BOM archyvavimo blokatoriai', 'Susijusios SO eilutės ir archyvavimo kliūtys pagal BOM arba produktą.', 'index', 'bom_archive_blockers', 'Generuojama ataskaita'),
    ]),
]


@reports.get('/reports')
def index():
    actions = current_app.config.get('REPORT_ACTIONS', {})
    pricing_enabled = current_app.config.get('REPORT_PRICING_ENABLED', True)
    groups = []
    for title, entries in CATALOGUE:
        cards = [dict(title=name, description=description, endpoint=endpoint,
                      action=action, kind=kind)
                 for name, description, endpoint, action, kind in entries
                 if (not action or action in actions)
                 and (pricing_enabled or endpoint not in
                      {'furnibox_comparison.index', 'pricing_control', 'purchase_pricing'})]
        if cards:
            groups.append(dict(title=title, cards=cards))
    return render_template('reports.html', groups=groups)
