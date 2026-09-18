"""Pure, auditable replay of the user-approved V10 BOM corrections.

The caller owns workbook I/O. This function never modifies its source rows;
unknown or conflicting rows are rejected rather than silently overwritten.
"""

from __future__ import annotations

from copy import deepcopy
import posixpath
import re
import shutil
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


SHELVES = (
    ("CAB01", "WW"), ("CAB02", "BB"), ("CAB03", "NO"),
)


def _sku(row):
    return str(row[2] or "").strip().upper()


def _components(row):
    return {
        str(row[column] or "").strip().upper(): float(row[column + 1])
        for column in range(13, min(len(row), 133), 4)
        if row[column]
    }


def replay_approved_v10_rows(source_rows, *, allow_conflicts=False):
    """Return new rows and a change log, leaving source_rows untouched."""
    rows = [list(row) + [None] * max(0, 133 - len(row)) for row in source_rows]
    by_sku = {}
    for row in rows:
        sku = _sku(row)
        if not sku:
            continue
        if sku in by_sku:
            raise ValueError(f"DUPLICATE_SOURCE_BOM: {sku}")
        by_sku[sku] = row
    changes = []

    def conflict(sku, reason):
        if not allow_conflicts:
            raise ValueError(reason)
        changes.append({"sku": sku, "action": "CONFLICT_REVIEW", "reason": reason})

    hrd_sku = "UNI-P-ACC01-HRD207D"
    hrd = by_sku.get(hrd_sku)
    analog = by_sku.get("UNI-P-ACC01-HRD227D")
    if hrd is None or analog is None:
        conflict(hrd_sku, "MISSING_APPROVED_HRD207D_OR_ANALOG")
    base_parts = {
        "CON7X50": 10, "DOW8X30": 4, "NAIL-1": 5,
        "FPACK-UNI-P-ACC01-HRD029": 2, "CAB_SPACER": 4, "PRIZM-1": 4,
    }
    corrected_parts = {**base_parts, "LAM186330": 4, "LAM276308": 1}
    found = _components(hrd) if hrd is not None else {}
    if hrd is not None and found == corrected_parts and hrd[4] == 8:
        changes.append({"sku": hrd_sku, "action": "ALREADY_MATCHING"})
    elif hrd is not None and analog is not None:
        if found == base_parts and hrd[4] == 6:
            if _components(analog).get("LAM186330") != 4 or _components(analog).get("LAM276308") != 1:
                conflict(hrd_sku, "CONFLICTING_HRD207D_ANALOG")
            else:
                hrd[4] = 8
                hrd[37:45] = analog[37:45]
                if _components(hrd) != corrected_parts:
                    conflict(hrd_sku, "CONFLICTING_HRD207D_REPLAY")
                else:
                    changes.append({"sku": hrd_sku, "action": "APPLIED_APPROVED_HRD207D"})
        else:
            conflict(hrd_sku, "CONFLICTING_APPROVED_BOM: UNI-P-ACC01-HRD207D")

    next_number = max(int(row[1]) for row in rows if isinstance(row[1], (int, float))) + 1
    for cabinet, color in SHELVES:
        for target, analog_slf, width, depth, pins in (
            ("SLF020", "SLF021", 1163, 564, 6),
            ("SLF022", "SLF023", 1163, 340, 4),
        ):
            sku = f"EUB-C-{cabinet}-{target}"
            source = by_sku.get(f"EUB-C-{cabinet}-{analog_slf}")
            if source is None or source[9] != width or source[11] != depth:
                conflict(sku, f"MISSING_OR_CHANGED_SHELF_ANALOG: {sku}")
                continue
            candidate = deepcopy(source)
            candidate[1] = next_number
            candidate[2] = sku
            candidate[8] = f"Shelf - W120 D{'60' if depth == 564 else '37'} - for HIGH cabinets"
            candidate[13] = f"EU-SREW-SHELF-{width}x{depth}-{color}"
            candidate[17] = f"SLF-PINS-HRD-{pins}"
            candidate[18] = 1
            candidate[19] = "SHELF HARDWARE"
            expected_parts = {candidate[13].upper(): 1, candidate[17].upper(): 1}
            if _components(candidate) != expected_parts:
                conflict(sku, f"CONFLICTING_SHELF_ANALOG: {sku}")
                continue
            existing = by_sku.get(sku)
            if existing is None:
                rows.append(candidate)
                by_sku[sku] = candidate
                next_number += 1
                changes.append({"sku": sku, "action": "ADDED_APPROVED_BOM"})
            elif _components(existing) == expected_parts and all(
                existing[column] == candidate[column] for column in (3, 4, 8, 9, 11, 13, 17, 18, 19)
            ):
                changes.append({"sku": sku, "action": "ALREADY_MATCHING"})
            else:
                conflict(sku, f"CONFLICTING_APPROVED_BOM: {sku}")

    sku = "EUB-C-CAB03-PNL013"
    panel = [None] * 133
    panel[1:12] = [next_number, sku, "PREPACK PANEL", 1, 1, 1,
                   "REFORM BOX - Oak laminate", "Filler - W15 H220 - for plinths",
                   150, 2200, 18]
    panel[13:17] = ["EU-PNL-2000x150-NO", 1, "PANEL", 0]
    existing = by_sku.get(sku)
    if existing is None:
        rows.append(panel)
        changes.append({"sku": sku, "action": "ADDED_APPROVED_BOM"})
    elif _components(existing) == {"EU-PNL-2000X150-NO": 1} and all(
        existing[column] == panel[column] for column in (3, 4, 8, 9, 10, 11, 13, 14, 15)
    ):
        changes.append({"sku": sku, "action": "ALREADY_MATCHING"})
    else:
        conflict(sku, f"CONFLICTING_APPROVED_BOM: {sku}")
    return rows, changes


def stage_approved_v10_input(source: Path, destination: Path):
    """Patch only BOM sheet XML in an isolated copy of a large XLSX."""
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("APPROVED_REPLAY_MUST_NOT_OVERWRITE_SOURCE")
    workbook = load_workbook(source, read_only=True, data_only=True)
    try:
        sheet = workbook["BOM - Input"]
        if sheet.cell(8, 3).value != "BOM SKU Code":
            raise ValueError("UNSUPPORTED_REFORM_BOM_LAYOUT")
        source_rows = [
            list(row) for row in sheet.iter_rows(min_row=9, max_col=133, values_only=True)
        ]
        replayed, changes = replay_approved_v10_rows(source_rows, allow_conflicts=True)
        existing_rows, source_values = {}, {}
        for number, row in enumerate(source_rows, 9):
            sku = _sku(row)
            if sku:
                existing_rows[sku] = number
                source_values[sku] = row
        targets = {_sku(row): row for row in replayed if _sku(row)}
        with ZipFile(source, "r") as original:
            workbook_xml = etree.fromstring(original.read("xl/workbook.xml"))
            rels_xml = etree.fromstring(original.read("xl/_rels/workbook.xml.rels"))
            office_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            relation_id = next(
                node.attrib[office_rel] for node in workbook_xml.iter()
                if node.tag.endswith("}sheet") and node.get("name") == "BOM - Input"
            )
            relationship = next(
                node for node in rels_xml if node.get("Id") == relation_id
            )
            location = relationship.get("Target").lstrip("/")
            sheet_path = (
                location if location.startswith("xl/")
                else posixpath.normpath(posixpath.join("xl", location))
            )
            root = etree.fromstring(original.read(sheet_path))
            namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
            sheet_data = root.find(namespace + "sheetData")
            xml_rows = {
                int(element.get("r")): element
                for element in sheet_data.findall(namespace + "row")
            }
            for sku, original_number in existing_rows.items():
                if sku != "UNI-P-ACC01-HRD207D":
                    continue
                element = xml_rows[original_number]
                for column, (before, after) in enumerate(zip(source_values[sku], targets[sku]), 1):
                    if before != after:
                        _set_xml_cell(element, column, original_number, after, namespace)
            next_physical_row = max(xml_rows) + 1
            for row in replayed:
                sku = _sku(row)
                if not sku or sku in existing_rows:
                    continue
                analog_code = (
                    "SLF021" if sku.endswith("SLF020") else
                    "SLF023" if sku.endswith("SLF022") else "SLF021"
                )
                analog_sku = (
                    sku.rsplit("-", 1)[0] + "-" + analog_code
                    if not sku.endswith("PNL013") else "EUB-C-CAB03-SLF021"
                )
                template = xml_rows[existing_rows[analog_sku]]
                element = deepcopy(template)
                element.set("r", str(next_physical_row))
                for cell in element.findall(namespace + "c"):
                    cell.set("r", re.sub(r"\d+$", str(next_physical_row), cell.get("r")))
                    for child in list(cell):
                        cell.remove(child)
                    cell.attrib.pop("t", None)
                for column, value in enumerate(row[:133], 1):
                    if value is not None:
                        _set_xml_cell(element, column, next_physical_row, value, namespace)
                sheet_data.append(element)
                next_physical_row += 1
            dimension = root.find(namespace + "dimension")
            if dimension is not None:
                dimension.set("ref", f"B1:EC{next_physical_row - 1}")
            patched_xml = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with ZipFile(destination, "w") as output:
                for item in original.infolist():
                    if item.filename == sheet_path:
                        output.writestr(item, patched_xml)
                    else:
                        with original.open(item) as reader, output.open(item, "w") as writer:
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
        return changes
    finally:
        workbook.close()


def _set_xml_cell(row, column, row_number, value, namespace):
    reference = f"{get_column_letter(column)}{row_number}"
    cell = next((item for item in row.findall(namespace + "c") if item.get("r") == reference), None)
    if cell is None:
        cell = etree.SubElement(row, namespace + "c", r=reference)
    for child in list(cell):
        cell.remove(child)
    if isinstance(value, str):
        cell.set("t", "inlineStr")
        etree.SubElement(etree.SubElement(cell, namespace + "is"), namespace + "t").text = value
    elif value is None:
        cell.attrib.pop("t", None)
    else:
        cell.attrib.pop("t", None)
        etree.SubElement(cell, namespace + "v").text = str(value)
