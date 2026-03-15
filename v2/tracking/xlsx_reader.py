from __future__ import annotations

"""
Minimal XLSX reader (single-sheet oriented), using only Python stdlib.

Parses:
- xl/workbook.xml (+ rels)
- xl/sharedStrings.xml
- xl/worksheets/sheet*.xml
"""

from dataclasses import dataclass
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"a": NS_MAIN, "r": NS_REL}


@dataclass
class XlsxSheet:
    name: str
    target: str


def _col_to_idx(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch.upper()) - ord("A") + 1)
    return n - 1


def _split_cell_ref(cell_ref: str) -> Tuple[int, int]:
    m = re.match(r"^([A-Z]+)(\d+)$", cell_ref)
    if not m:
        return 0, 0
    col = _col_to_idx(m.group(1))
    row = int(m.group(2)) - 1
    return row, col


def _load_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    out: List[str] = []
    for si in root.findall("a:si", NS):
        text_parts: List[str] = []
        t = si.find("a:t", NS)
        if t is not None and t.text is not None:
            text_parts.append(t.text)
        for r in si.findall("a:r", NS):
            tt = r.find("a:t", NS)
            if tt is not None and tt.text is not None:
                text_parts.append(tt.text)
        out.append("".join(text_parts))
    return out


def _resolve_first_sheet(zf: zipfile.ZipFile) -> XlsxSheet:
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets = wb.find("a:sheets", NS)
    if sheets is None or len(list(sheets)) == 0:
        raise ValueError("No sheet found in workbook")

    first = list(sheets)[0]
    name = first.attrib.get("name", "Sheet1")
    rid = first.attrib.get(f"{{{NS_REL}}}id")
    if not rid:
        raise ValueError("Missing relationship id for first sheet")

    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rid_to_target: Dict[str, str] = {}
    for rel in rels:
        r_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if r_id and target:
            rid_to_target[r_id] = target

    target = rid_to_target.get(rid)
    if not target:
        raise ValueError("Cannot resolve first sheet target")

    if not target.startswith("xl/"):
        target = "xl/" + target

    return XlsxSheet(name=name, target=target)


def read_first_sheet_rows(path: Path) -> List[List[str]]:
    with zipfile.ZipFile(path) as zf:
        sheet = _resolve_first_sheet(zf)
        shared = _load_shared_strings(zf)
        root = ET.fromstring(zf.read(sheet.target))

    sheet_data = root.find(".//a:sheetData", NS)
    if sheet_data is None:
        return []

    grid: Dict[int, Dict[int, str]] = {}
    max_col = 0

    for row in sheet_data.findall("a:row", NS):
        row_cells: Dict[int, str] = {}
        for c in row.findall("a:c", NS):
            ref = c.attrib.get("r", "A1")
            r_idx, c_idx = _split_cell_ref(ref)
            t = c.attrib.get("t")

            val = ""
            is_node = c.find("a:is/a:t", NS)
            if is_node is not None and is_node.text is not None:
                val = is_node.text
            else:
                v = c.find("a:v", NS)
                if v is not None and v.text is not None:
                    raw = v.text
                    if t == "s":
                        try:
                            val = shared[int(raw)]
                        except Exception:
                            val = raw
                    else:
                        val = raw

            row_cells[c_idx] = val
            if c_idx > max_col:
                max_col = c_idx

        r_attr = row.attrib.get("r")
        if r_attr and r_attr.isdigit():
            r_idx = int(r_attr) - 1
        else:
            r_idx = len(grid)

        grid[r_idx] = row_cells

    if not grid:
        return []

    max_row = max(grid.keys())
    rows: List[List[str]] = []
    for r in range(max_row + 1):
        row_cells = grid.get(r, {})
        rows.append([row_cells.get(c, "") for c in range(max_col + 1)])
    return rows
