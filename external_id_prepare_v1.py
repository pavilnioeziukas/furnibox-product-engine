"""Paruošia trūkstamus produktų External ID BOM importui.

Veiksmas leidžiamas Stage ir Production aplinkose. Jis suranda MAP palyginime
reikalingus jau egzistuojančius produktus bei generatoriaus kuriamas APACK,
CABINET-A ir HRD-A korteles. Per standartinį Odoo eksportą sugeneruojami
trūkstami ``__export__`` External ID abiem BOM importui reikalingiems modeliams:
``product.template`` ir ``product.product``.

Produktai nekuriami, nedubliuojami ir jų verslo laukai nekeičiami. Odoo
sukuriami tik techniniai ``ir.model.data`` įrašai.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from bom_import_pilot_v1 import load_new_bom_graph
from config import load_settings
from odoo_client import OdooClient
from output_paths import environment_output_dir, environment_slug
from product_import_v3 import apack_sku
from product_import_v7 import (
    cabinet_assembled_sku,
    hrd_assembled_sku,
    is_cabinet_bom_parent,
    is_hrd_bom_parent,
)
from product_detection_v2 import find_bom_input, load_reform_universe


def canon(value) -> str:
    return str(value or "").strip().upper()


def external_id_res_ids(
    client: OdooClient, model: str, res_ids: set[int]
) -> set[int]:
    if not res_ids:
        return set()
    rows = client.search_read_all(
        "ir.model.data",
        [["model", "=", model], ["res_id", "in", sorted(res_ids)]],
        ["res_id"],
    )
    return {int(row["res_id"]) for row in rows}


def main() -> None:
    base = Path(__file__).resolve().parent
    environment = environment_slug()
    if environment not in {"stage", "production"}:
        raise PermissionError(
            "External ID paruošimas leidžiamas tik pasirinkus Stage arba "
            "Production aplinką."
        )

    output_dir = environment_output_dir(base)
    comparison_path = output_dir / "MAP_Comparison.xlsx"
    parents, lines = load_new_bom_graph(comparison_path)
    map_skus = set(parents) | {
        row["component"] for values in lines.values() for row in values
    }
    generated_apack_skus = {
        canon(apack_sku(parent))
        for parent in parents
        if canon(parent).startswith("FPACK-")
    }
    reform_products, _, _ = load_reform_universe(find_bom_input(base))
    generated_hrd_assembled_skus = {
        canon(hrd_assembled_sku(sku))
        for sku, product in reform_products.items()
        if is_hrd_bom_parent(sku, product)
    }
    generated_cabinet_assembled_skus = {
        canon(cabinet_assembled_sku(sku))
        for sku, product in reform_products.items()
        if is_cabinet_bom_parent(sku, product)
    }
    # APACK produktai generuojami iš FPACK ir todėl MAP_Comparison grafe
    # neegzistuoja. Sugeneruoti CABINET-A ir HRD-A taip pat gali nebūti MAP
    # grafe. Juos būtina įtraukti atskirai, kitaip 11A klaidingai praneša,
    # kad External ID netrūksta.
    wanted_skus = (
        map_skus
        | generated_apack_skus
        | generated_cabinet_assembled_skus
        | generated_hrd_assembled_skus
    )

    settings = load_settings()
    url = str(settings.url).lower()
    if environment == "stage" and "stage" not in url:
        raise PermissionError(
            f"Saugos blokavimas: URL neatrodo kaip Stage aplinka: {settings.url}"
        )
    if environment == "production" and "stage" in url:
        raise PermissionError(
            "Saugos blokavimas: pasirinkta Production, bet URL atrodo kaip "
            f"Stage aplinka: {settings.url}"
        )

    client = OdooClient(settings)
    uid = client.authenticate()
    rows = client.search_read_all(
        "product.product",
        [["default_code", "!=", False]],
        ["id", "default_code", "product_tmpl_id", "active"],
        context={"active_test": False},
    )

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        sku = canon(row.get("default_code"))
        if sku in wanted_skus:
            grouped[sku].append(row)

    missing_skus = sorted(wanted_skus - set(grouped))
    duplicate_skus = sorted(
        sku for sku, matches in grouped.items()
        if len({int(row["id"]) for row in matches}) != 1
        or len({
            int(row["product_tmpl_id"][0])
            for row in matches if row.get("product_tmpl_id")
        }) != 1
    )
    safe_rows = [
        matches[0]
        for sku, matches in grouped.items()
        if sku not in set(duplicate_skus)
    ]

    product_ids = {int(row["id"]) for row in safe_rows}
    template_ids = {
        int(row["product_tmpl_id"][0])
        for row in safe_rows if row.get("product_tmpl_id")
    }
    product_ids_with_external_id = external_id_res_ids(
        client, "product.product", product_ids
    )
    template_ids_with_external_id = external_id_res_ids(
        client, "product.template", template_ids
    )
    missing_product_ids = product_ids - product_ids_with_external_id
    missing_template_ids = template_ids - template_ids_with_external_id

    prepared_products = client.ensure_external_ids(
        "product.product", missing_product_ids
    )
    prepared_templates = client.ensure_external_ids(
        "product.template", missing_template_ids
    )

    remaining_product_ids = missing_product_ids - external_id_res_ids(
        client, "product.product", missing_product_ids
    )
    remaining_template_ids = missing_template_ids - external_id_res_ids(
        client, "product.template", missing_template_ids
    )

    print(f"Prisijungta prie {environment.title()} Odoo. UID=", uid)
    print("\nEXTERNAL ID PARUOŠIMAS BAIGTAS")
    print("MAP SKU:", len(map_skus))
    print("Papildomai tikrinami sugeneruoti APACK SKU:", len(generated_apack_skus))
    print(
        "Papildomai tikrinami sugeneruoti CABINET-A SKU:",
        len(generated_cabinet_assembled_skus),
    )
    print(
        "Papildomai tikrinami sugeneruoti HRD-A SKU:",
        len(generated_hrd_assembled_skus),
    )
    print("Reikalingi unikalūs SKU:", len(safe_rows))
    print("Nerasti Stage SKU:", len(missing_skus))
    print("Dviprasmiški / pasikartojantys SKU:", len(duplicate_skus))
    print("Paruošti product.template External ID:", prepared_templates)
    print("Paruošti product.product External ID:", prepared_products)
    print("Likę be product.template External ID:", len(remaining_template_ids))
    print("Likę be product.product External ID:", len(remaining_product_ids))
    if missing_skus:
        print("Pirmi nerasti SKU:", ", ".join(missing_skus[:20]))
    if duplicate_skus:
        print("Pirmi dviprasmiški SKU:", ", ".join(duplicate_skus[:20]))
    if remaining_product_ids or remaining_template_ids:
        raise RuntimeError(
            "Po eksportavimo daliai įrašų External ID vis dar nerastas. "
            "12 veiksmo neleiskite, kol ši klaida neišspręsta."
        )
    print("Dabar galima kartoti 12 veiksmą.")


if __name__ == "__main__":
    main()