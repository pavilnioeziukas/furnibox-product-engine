"""Generate auditable final Reform SO unit prices without changing Odoo."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

MODEL_FILE = "map 1_MC_v3.xlsx"
PRICE_FILE = "Reform_Final_Prices.xlsx"
OUTPUT_FILE = "Reform_SO_Line_Prices.xlsx"
ADJUSTMENT = -0.07
ADDONS = ("Assembly", "Storage", "Packaging", "Put on pallet", "Other", "Markup")


def text(value):
    return str(value or "").strip()


def key(value):
    return text(value).casefold()


def number(value, default=0.0):
    if value in (None, ""):
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Expected number, got {value!r}")
    return float(value)


def headers(sheet):
    return {text(cell.value): cell.column for cell in sheet[1] if cell.value not in (None, "")}


@dataclass(frozen=True)
class Rule:
    sku: str
    category_id: str
    category_name: str
    odoo_category: str
    addons: tuple[float, float, float, float, float, float]


@dataclass
class Item:
    sku: str
    qty: float | None
    leaves: list[tuple[str, float]] = field(default_factory=list)


def load_prices(path: Path):
    wb = load_workbook(path, data_only=False, read_only=True)
    result = {}
    if "REFORM PRICE LIST" in wb.sheetnames:
        ws = wb["REFORM PRICE LIST"]
        h = headers(ws)
        needed = ["Internal Reference", "Name", "Adjusted Furnibox Purchase Price", "Reform Markup Factor", "Reform Purchase Price"]
        missing = [name for name in needed if name not in h]
        if missing:
            wb.close(); raise ValueError(f"REFORM PRICE LIST missing: {', '.join(missing)}")
        for row in ws.iter_rows(min_row=2, values_only=True):
            sku = text(row[h[needed[0]] - 1])
            if not sku:
                continue
            price = row[h[needed[4]] - 1]
            if not isinstance(price, (int, float)):
                adjusted, factor = row[h[needed[2]] - 1], row[h[needed[3]] - 1]
                if not isinstance(adjusted, (int, float)) or not isinstance(factor, (int, float)):
                    continue
                price = adjusted * factor
            if key(sku) in result:
                wb.close(); raise ValueError(f"Duplicate Reform price SKU: {sku}")
            result[key(sku)] = (text(row[h[needed[1]] - 1]), float(price))
    elif "Purchase prices" in wb.sheetnames or "kainos" in wb.sheetnames:
        source_sheet = "Purchase prices" if "Purchase prices" in wb.sheetnames else "kainos"
        for row in wb[source_sheet].iter_rows(min_row=2, values_only=True):
            if text(row[0]) and isinstance(row[7], (int, float)):
                # VLOOKUP returns the first match.
                result.setdefault(key(row[0]), (text(row[1]), float(row[7])))
    else:
        wb.close(); raise ValueError(f"No Reform price sheet in {path.name}")
    wb.close()
    return result


def load_rules(path: Path):
    wb = load_workbook(path, data_only=True, read_only=True)
    result = {}
    for row in wb["Kainodaros kategorijos"].iter_rows(min_row=2, values_only=True):
        sku = text(row[0])
        if not sku:
            continue
        rule = Rule(sku, text(row[1]), text(row[2]), text(row[3]), tuple(number(v) for v in row[4:10]))
        # Legacy VLOOKUP uses the first match. Preserve that result; conflicting
        # duplicates are exposed separately in DIAGNOSTICS.
        result.setdefault(key(sku), rule)
    wb.close()
    return result


def load_boms(path: Path):
    wb = load_workbook(path, data_only=True, read_only=True)
    result, current_top, current_item = {}, "", None
    for row in wb["bomai"].iter_rows(min_row=3, values_only=True):
        top = text(row[1])
        if not top:
            continue
        if top != current_top:
            current_top, current_item = top, None
            result.setdefault(top, (text(row[2]), []))
        if text(row[3]):
            current_item = Item(text(row[3]), number(row[5]) if row[5] not in (None, "") else None)
            result[top][1].append(current_item)
        if text(row[6]):
            if current_item is None:
                current_item = Item("", None)
                result[top][1].append(current_item)
            current_item.leaves.append((text(row[6]), number(row[7], 1.0)))
    wb.close()
    return result


def load_non_bom(path: Path):
    wb = load_workbook(path, data_only=True, read_only=True)
    rows = []
    for row in wb["Ne BOM pozicijos"].iter_rows(min_row=2, values_only=True):
        if text(row[0]):
            rows.append((text(row[0]), text(row[1]), text(row[2]), text(row[3]), *[number(v) for v in row[6:10]]))
    wb.close()
    return rows


def load_rule_conflicts(path: Path):
    wb = load_workbook(path, data_only=True, read_only=True)
    seen, conflicts = {}, []
    for excel_row, row in enumerate(wb["Kainodaros kategorijos"].iter_rows(min_row=2, values_only=True), 2):
        sku = text(row[0])
        if not sku:
            continue
        values = tuple(number(v) for v in row[4:10])
        if key(sku) in seen and seen[key(sku)][1] != values:
            conflicts.append((sku, seen[key(sku)][0], excel_row, seen[key(sku)][1], values))
        else:
            seen.setdefault(key(sku), (excel_row, values))
    wb.close()
    return conflicts


def breakdown(rule, multiplier, level):
    return {"level": level, "rule": rule, "multiplier": multiplier,
            "addons": tuple(value * multiplier for value in rule.addons)}


def calculate_boms(boms, prices, rules, adjustment=ADJUSTMENT):
    results, details = [], []
    for top, (category, items) in boms.items():
        cost, issues, applied = 0.0, [], []
        for item in items:
            if not item.sku:
                issues.append("Leaf components have no Level II BOM item")
            if item.qty is None:
                issues.append(f"Missing Level II quantity: {item.sku or '[unknown]'}")
            item_qty = item.qty or 0.0
            if item.leaves:
                sub_cost = 0.0
                for sku, qty in item.leaves:
                    if key(sku) not in prices:
                        issues.append(f"Missing component price: {sku}")
                    else:
                        sub_cost += prices[key(sku)][1] * qty
                cost += sub_cost * item_qty
                multiplier, level = item_qty, "LEVEL II BOM"
            else:
                if key(item.sku) not in prices:
                    issues.append(f"Missing component price: {item.sku}")
                else:
                    cost += prices[key(item.sku)][1] * item_qty
                # Exact legacy rule: direct item pricing add-on is applied once, not by quantity.
                multiplier, level = 1.0, "DIRECT LEVEL II"
            if not item.sku:
                continue
            if key(item.sku) not in rules:
                issues.append(f"Missing {level} pricing rule: {item.sku}")
            else:
                applied.append(breakdown(rules[key(item.sku)], multiplier, level))
        if key(top) not in rules:
            issues.append(f"Missing LEVEL I BOM pricing rule: {top}")
        else:
            applied.append(breakdown(rules[key(top)], 1.0, "LEVEL I BOM"))
        addon_values = tuple(sum(row["addons"][i] for row in applied) for i in range(6))
        addon_total = sum(addon_values)
        issue_text = "; ".join(dict.fromkeys(issues))
        results.append({"sku": top, "name": prices.get(key(top), ("", 0))[0], "type": "BOM",
                        "category": category, "cost": cost, "addons": addon_values,
                        "adjustment": addon_total * adjustment,
                        "final": cost + addon_total * (1 + adjustment) if not issues else None,
                        "status": "COMPLETE" if not issues else "BLOCKED", "issues": issue_text})
        for row in applied:
            row["top"] = top
            details.append(row)
    return results, details


def calculate_non_bom(items, prices):
    results = []
    for sku, name, category, pricing_category, preparation, storage, bag, sticker in items:
        missing = key(sku) not in prices
        cost = prices.get(key(sku), ("", 0))[1]
        addon_values = (0.0, storage, preparation + bag + sticker, 0.0, 0.0, 0.0)
        results.append({"sku": sku, "name": name, "type": "NON-BOM", "category": category,
                        "pricing_category": pricing_category, "cost": cost, "addons": addon_values,
                        "preparation": preparation, "bag": bag, "sticker": sticker, "adjustment": 0.0,
                        "final": cost + sum(addon_values) if not missing else None,
                        "status": "BLOCKED" if missing else "COMPLETE",
                        "issues": f"Missing purchase price: {sku}" if missing else ""})
    return results


def style(sheet, color="1F4E78"):
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor=color)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 42
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_view.showGridLines = False


def widths(sheet, values):
    for index, value in enumerate(values, 1):
        sheet.column_dimensions[sheet.cell(1, index).column_letter].width = value


def build_reform_so_line_prices(model_path: Path, price_path: Path, output_path: Path, adjustment=ADJUSTMENT):
    if not -1 < adjustment <= 0:
        raise ValueError("Adjustment must be between -100% and 0%")
    prices, rules = load_prices(price_path), load_rules(model_path)
    bom_rows, details = calculate_boms(load_boms(model_path), prices, rules, adjustment)
    non_rows = calculate_non_bom(load_non_bom(model_path), prices)
    all_rows = sorted(bom_rows + non_rows, key=lambda row: (row["type"], row["sku"].casefold()))

    wb = Workbook()
    ws = wb.active; ws.title = "SO LINE PRICES"
    ws.append(["SKU", "Name", "Position Type", "Product Category", "Component / Purchase Cost",
               *ADDONS, "Pricing Add-ons Total", "Adjustment Rate", "Adjustment Amount",
               "Final Reform SO Unit Price", "Status", "Issues"])
    for row in all_rows:
        ws.append([row["sku"], row["name"], row["type"], row["category"], row["cost"], *row["addons"],
                   sum(row["addons"]), adjustment if row["type"] == "BOM" else 0, row["adjustment"],
                   row["final"], row["status"], row["issues"]])
    style(ws); widths(ws, [31, 42, 14, 30, 22, 14, 14, 14, 16, 14, 14, 20, 16, 19, 25, 14, 75])
    for row in range(2, ws.max_row + 1):
        for col in list(range(5, 13)) + [14, 15]: ws.cell(row, col).number_format = '0.0000 [$€-x-euro2]'
        ws.cell(row, 13).number_format = "0.0%"

    ws = wb.create_sheet("BOM CATEGORY BREAKDOWN")
    ws.append(["Top SKU", "Application Level", "Pricing Rule SKU", "Category ID", "Category Name",
               "Odoo Product Category", "Multiplier", *ADDONS, "Add-ons Total", "Adjustment Rate", "Adjusted Add-ons"])
    for row in details:
        rule, total = row["rule"], sum(row["addons"])
        ws.append([row["top"], row["level"], rule.sku, rule.category_id, rule.category_name,
                   rule.odoo_category, row["multiplier"], *row["addons"], total, adjustment, total * (1 + adjustment)])
    style(ws, "5B9BD5"); widths(ws, [31, 19, 31, 13, 24, 31, 12] + [14] * 6 + [18, 16, 18])

    ws = wb.create_sheet("CATEGORY RULES")
    ws.append(["Category ID", "Category Name", "Odoo Product Category", "Products", *ADDONS, "Total",
               *[f"{name} Applied" for name in ADDONS]])
    variants = Counter((r.category_id, r.category_name, r.odoo_category, *r.addons) for r in rules.values())
    for values, count in sorted(variants.items(), key=lambda item: tuple(str(v) for v in item[0][:3])):
        cid, name, odoo, *addon_values = values
        ws.append([cid, name, odoo, count, *addon_values, sum(addon_values),
                   *["YES" if value else "NO" for value in addon_values]])
    style(ws, "70AD47"); widths(ws, [13, 25, 32, 12] + [14] * 7 + [18] * 6)

    ws = wb.create_sheet("NON-BOM RULES")
    ws.append(["SKU", "Name", "Product Category", "Pricing Category", "Purchase Price",
               "Pack Preparation", "Storage", "Bag", "Sticker", "Final Unit Price", "Status", "Issues"])
    for row in non_rows:
        ws.append([row["sku"], row["name"], row["category"], row["pricing_category"], row["cost"],
                   row["preparation"], row["addons"][1], row["bag"], row["sticker"], row["final"],
                   row["status"], row["issues"]])
    style(ws, "8064A2"); widths(ws, [31, 42, 27, 17, 18, 18, 14, 12, 12, 18, 14, 65])

    ws = wb.create_sheet("DIAGNOSTICS"); ws.append(["Position Type", "SKU", "Status", "Issues"])
    for row in all_rows:
        if row["status"] == "BLOCKED": ws.append([row["type"], row["sku"], row["status"], row["issues"]])
    for sku, first_row, duplicate_row, first_values, duplicate_values in load_rule_conflicts(model_path):
        ws.append(["PRICING RULE", sku, "CONFLICT",
                   f"Rows {first_row} and {duplicate_row} differ; first row used. {first_values} vs {duplicate_values}"])
    style(ws, "C00000"); widths(ws, [18, 34, 14, 100])

    ws = wb.create_sheet("INFO")
    for row in [("Purpose", "Final Reform SO line unit price"),
                ("BOM rule", "Components + Assembly + Storage + Packaging + Put on pallet + Other + Markup"),
                ("Adjustment", adjustment), ("Markup meaning", "Additive monetary amount, not percentage"),
                ("Non-BOM rule", "Purchase price + pack preparation + storage + bag + sticker"),
                ("BOM products", len(bom_rows)), ("Non-BOM products", len(non_rows)),
                ("Blocked", sum(r["status"] == "BLOCKED" for r in all_rows)), ("Odoo changed", "NO")]: ws.append(row)
    ws.column_dimensions["A"].width = 30; ws.column_dimensions["B"].width = 110; ws.sheet_view.showGridLines = False

    wb.calculation.fullCalcOnLoad = True; wb.calculation.forceFullCalc = True; wb.calculation.calcMode = "auto"
    output_path.parent.mkdir(parents=True, exist_ok=True); wb.save(output_path)
    return len(bom_rows), len(non_rows), sum(row["status"] == "BLOCKED" for row in all_rows)


def main():
    from config import load_settings
    settings = load_settings()
    model_path, price_path = Path(MODEL_FILE), settings.output_dir / PRICE_FILE
    for path in (model_path, price_path):
        if not path.exists(): raise FileNotFoundError(f"Nerastas šaltinio failas: {path.resolve()}")
    output = settings.output_dir / OUTPUT_FILE
    bom, non_bom, blocked = build_reform_so_line_prices(model_path, price_path, output)
    print("GALUTINĖS REFORM SO EILUČIŲ KAINOS APSKAIČIUOTOS")
    print("Failas:", output); print("BOM pozicijos:", bom); print("Ne BOM pozicijos:", non_bom)
    print("BLOCKED:", blocked); print("Odoo duomenys nepakeisti.")


if __name__ == "__main__": main()
