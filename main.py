import logging
from config import load_settings
from odoo_client import OdooClient
from transformers import (
    flatten_products,
    flatten_boms,
    flatten_bom_lines,
    latest_purchase_prices,
)
from excel_writer import write_snapshot

def main():
    settings = load_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(settings.log_dir / "odoo_snapshot.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    client = OdooClient(settings)

    logging.info("Jungiamasi prie Odoo...")
    uid = client.authenticate()
    logging.info("Prisijungta. UID=%s", uid)

    logging.info("Nuskaitomi produktai...")
    products = flatten_products(client.products())
    logging.info("Produktų: %s", len(products))

    logging.info("Nuskaitomi BOM...")
    boms = flatten_boms(client.boms())
    logging.info("BOM: %s", len(boms))

    logging.info("Nuskaitomos BOM eilutės...")
    bom_lines = flatten_bom_lines(client.bom_lines())
    logging.info("BOM eilučių: %s", len(bom_lines))

    logging.info("Nuskaitomos patvirtintų pirkimų eilutės...")
    purchase_prices = latest_purchase_prices(client.purchase_order_lines(), products)
    logging.info("Produktų su paskutine pirkimo kaina: %s", len(purchase_prices))

    output_path = settings.output_dir / "Odoo_Snapshot.xlsx"
    write_snapshot(
        output_path,
        products,
        boms,
        bom_lines,
        purchase_prices,
        {
            "url": settings.url,
            "db": settings.db,
            "login": settings.login,
            "uid": uid,
        },
    )

    print()
    print("ODOO SNAPSHOT SUKURTAS")
    print("Failas:", output_path)
    print("Produktai:", len(products))
    print("BOM:", len(boms))
    print("BOM eilutės:", len(bom_lines))
    print("Paskutinės pirkimo kainos:", len(purchase_prices))

if __name__ == "__main__":
    main()
