from collections import OrderedDict

def rel_id(value):
    return value[0] if isinstance(value, list) and value else None

def rel_name(value):
    return value[1] if isinstance(value, list) and len(value) >= 2 else ""

def flatten_products(records):
    return [{
        "ID": r.get("id"),
        "Internal Reference": r.get("default_code") or "",
        "Name": r.get("name") or "",
        "Active": r.get("active"),
        "Product Template ID": rel_id(r.get("product_tmpl_id")),
        "Product Template": rel_name(r.get("product_tmpl_id")),
        "Category ID": rel_id(r.get("categ_id")),
        "Category": rel_name(r.get("categ_id")),
        "UoM ID": rel_id(r.get("uom_id")),
        "UoM": rel_name(r.get("uom_id")),
        "Type": r.get("type") or "",
        "Standard Price": r.get("standard_price"),
        "Currency ID": rel_id(r.get("currency_id")),
        "Currency": rel_name(r.get("currency_id")),
        "Write Date": r.get("write_date") or "",
    } for r in records]

def flatten_boms(records):
    return [{
        "BOM ID": r.get("id"),
        "BOM Code": r.get("code") or "",
        "Active": r.get("active"),
        "Product Template ID": rel_id(r.get("product_tmpl_id")),
        "Product Template": rel_name(r.get("product_tmpl_id")),
        "Product Variant ID": rel_id(r.get("product_id")),
        "Product Variant": rel_name(r.get("product_id")),
        "BOM Quantity": r.get("product_qty"),
        "BOM UoM ID": rel_id(r.get("product_uom_id")),
        "BOM UoM": rel_name(r.get("product_uom_id")),
        "BOM Type": r.get("type") or "",
        "Company ID": rel_id(r.get("company_id")),
        "Company": rel_name(r.get("company_id")),
        "Write Date": r.get("write_date") or "",
    } for r in records]

def flatten_bom_lines(records):
    return [{
        "BOM Line ID": r.get("id"),
        "BOM ID": rel_id(r.get("bom_id")),
        "BOM": rel_name(r.get("bom_id")),
        "Component Product ID": rel_id(r.get("product_id")),
        "Component Product": rel_name(r.get("product_id")),
        "Quantity": r.get("product_qty"),
        "UoM ID": rel_id(r.get("product_uom_id")),
        "UoM": rel_name(r.get("product_uom_id")),
        "Sequence": r.get("sequence"),
        "Company ID": rel_id(r.get("company_id")),
        "Company": rel_name(r.get("company_id")),
        "Write Date": r.get("write_date") or "",
    } for r in records]

def latest_purchase_prices(records):
    latest = OrderedDict()
    for r in records:
        product_id = rel_id(r.get("product_id"))
        if product_id is None or product_id in latest:
            continue
        latest[product_id] = {
            "Product ID": product_id,
            "Product": rel_name(r.get("product_id")),
            "Purchase Order Line ID": r.get("id"),
            "Purchase Order ID": rel_id(r.get("order_id")),
            "Purchase Order": rel_name(r.get("order_id")),
            "Vendor ID": rel_id(r.get("partner_id")),
            "Vendor": rel_name(r.get("partner_id")),
            "Ordered Quantity": r.get("product_qty"),
            "Last Purchase Price": r.get("price_unit"),
            "Currency ID": rel_id(r.get("currency_id")),
            "Currency": rel_name(r.get("currency_id")),
            "Order Date": r.get("date_order") or "",
            "Company ID": rel_id(r.get("company_id")),
            "Company": rel_name(r.get("company_id")),
            "Write Date": r.get("write_date") or "",
        }
    return list(latest.values())