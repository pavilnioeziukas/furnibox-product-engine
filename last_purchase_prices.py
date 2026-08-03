"""Eksportuoja paskutinę patvirtintą kiekvieno produkto pirkimo kainą iš Odoo."""

from __future__ import annotations

import logging
from datetime import datetime

from openpyxl import Workbook

from config import load_settings
from excel_writer import write_rows
from odoo_client import OdooClient
from transformers import latest_purchase_prices


def write_purchase_prices(path, purchase_prices, metadata):
    """Sukuria atskirą paskutinių pirkimo kainų Excel failą."""
    workbook = Workbook()

    info = workbook.active
    info.title = "INFO"
    for row in [
        ("Generated", datetime.now().isoformat(sep=" ", timespec="seconds")),
        ("Odoo URL", metadata["url"]),
        ("Database", metadata["db"]),
        ("User", metadata["login"]),
        ("Odoo UID", metadata["uid"]),
        ("Products with Last Purchase Price", len(purchase_prices)),
    ]:
        info.append(row)
    info.column_dimensions["A"].width = 36
    info.column_dimensions["B"].width = 45

    prices = workbook.create_sheet("LAST PURCHASE PRICES")
    write_rows(prices, purchase_prices)

    workbook.save(path)


def main():
    settings = load_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(
                settings.log_dir / "last_purchase_prices.log",
                encoding="utf-8",
            ),
            logging.StreamHandler(),
        ],
    )

    client = OdooClient(settings)

    logging.info("Jungiamasi prie Odoo...")
    uid = client.authenticate()
    logging.info("Prisijungta. UID=%s", uid)

    logging.info("Nuskaitomos patvirtintų ir užbaigtų pirkimų eilutės...")
    purchase_prices = latest_purchase_prices(client.purchase_order_lines())
    logging.info(
        "Produktų su paskutine pirkimo kaina: %s",
        len(purchase_prices),
    )

    output_path = settings.output_dir / "Last_Purchase_Prices.xlsx"
    write_purchase_prices(
        output_path,
        purchase_prices,
        {
            "url": settings.url,
            "db": settings.db,
            "login": settings.login,
            "uid": uid,
        },
    )

    print()
    print("PASKUTINIŲ PIRKIMO KAINŲ FAILAS SUKURTAS")
    print("Failas:", output_path)
    print("Produktai su kaina:", len(purchase_prices))


if __name__ == "__main__":
    main()
