"""Dependency-free .xlsx writer AND reader (stdlib zipfile + ElementTree).

Why: the acceptance criterion "能出一张表" must be provable on this Linux box
with no openpyxl.  The writer emits a real SpreadsheetML package that Excel and
WPS open; the reader normalises an offline copy of the creator-backend export.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS_CORE = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_DCTERMS = "http://purl.org/dc/terms/"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
NS_EP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

_COL_RE = re.compile(r"([A-Z]+)(\d+)")


def column_letter(index: int) -> str:
    """1 -> A, 27 -> AA."""
    letters = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _cell_xml(col: int, row: int, value, style_index: int = 0) -> str:
    ref = f"{column_letter(col)}{row}"
    style = f' s="{style_index}"' if style_index else ""
    if value is None:
        return ""
    if isinstance(value, bool):
        return f'<c r="{ref}"{style} t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{style}><v>{value}</v></c>'
    text = escape(str(value))
    if text.startswith(" ") or text.endswith(" "):
        return (f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">'
                f"{text}</t></is></c>")
    return f'<c r="{ref}"{style} t="inlineStr"><is><t>{text}</t></is></c>'


def _sheet_xml(rows, column_styles=None) -> str:
    column_styles = column_styles or {}
    body = []
    for r, row in enumerate(rows, start=1):
        cells = "".join(_cell_xml(c, r, v, column_styles.get(c, 0))
                        for c, v in enumerate(row, start=1))
        body.append(f'<row r="{r}">{cells}</row>')
    max_cols = max((len(r) for r in rows), default=1)
    dim = f"A1:{column_letter(max_cols)}{max(len(rows), 1)}"
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<worksheet xmlns="{NS_MAIN}"><dimension ref="{dim}"/>'
            f'<sheetData>{"".join(body)}</sheetData></worksheet>')


def _styles_xml(number_formats=None) -> tuple[str, dict]:
    """Return (styles.xml, {1-based column: style index}).

    ``number_formats`` is a mapping of 1-based column number to an Excel number
    format such as ``"0.00"``.  It exists so money columns look like money in
    Excel/WPS without pulling in openpyxl just to apply one cell format.
    """
    number_formats = {int(col): str(fmt) for col, fmt in
                      (number_formats or {}).items() if int(col) > 0}
    formats = []
    for fmt in number_formats.values():
        if fmt not in formats:
            formats.append(fmt)
    format_ids = {fmt: 164 + index for index, fmt in enumerate(formats)}
    column_styles = {col: 1 + formats.index(fmt)
                     for col, fmt in number_formats.items()}
    num_fmts = "".join(
        f'<numFmt numFmtId="{format_ids[fmt]}" formatCode="{escape(fmt)}"/>'
        for fmt in formats)
    num_fmts = f'<numFmts count="{len(formats)}">{num_fmts}</numFmts>' if formats else ""
    extra_xfs = "".join(
        f'<xf numFmtId="{format_ids[fmt]}" fontId="0" fillId="0" '
        f'borderId="0" xfId="0" applyNumberFormat="1"/>'
        for fmt in formats)
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<styleSheet xmlns="{NS_MAIN}">'
        f"{num_fmts}"
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        f'<cellXfs count="{1 + len(formats)}">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        f"{extra_xfs}</cellXfs>"
        "</styleSheet>")
    return styles, column_styles


def write_xlsx(path, rows, sheet_name="Sheet1", number_formats=None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Types xmlns="{NS_CT}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>")
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{NS_PKG_REL}">'
        f'<Relationship Id="rId1" Type="{NS_REL}/officeDocument" Target="xl/workbook.xml"/>'
        f'<Relationship Id="rId2" Type="{NS_PKG_REL}/metadata/core-properties" Target="docProps/core.xml"/>'
        f'<Relationship Id="rId3" Type="{NS_REL}/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>")
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_REL}"><sheets>'
        f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
        "</sheets></workbook>")
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{NS_PKG_REL}">'
        f'<Relationship Id="rId1" Type="{NS_REL}/worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{NS_REL}/styles" Target="styles.xml"/>'
        "</Relationships>")
    styles, column_styles = _styles_xml(number_formats)
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<cp:coreProperties xmlns:cp="{NS_CORE}" xmlns:dc="{NS_DC}" '
        f'xmlns:dcterms="{NS_DCTERMS}" xmlns:xsi="{NS_XSI}">'
        "<dc:creator>publish-assistant</dc:creator>"
        "<cp:lastModifiedBy>publish-assistant</cp:lastModifiedBy>"
        "</cp:coreProperties>")
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Properties xmlns="{NS_EP}"><Application>publish-assistant</Application>'
        "</Properties>")

    # 1.2.5: build into a same-directory temp file and atomically replace, so a
    # crash / full disk never truncates the previous good report (GPT item 12).
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".xlsx")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", root_rels)
            zf.writestr("xl/workbook.xml", workbook)
            zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            zf.writestr("xl/styles.xml", styles)
            zf.writestr("xl/worksheets/sheet1.xml",
                        _sheet_xml(rows, column_styles))
            zf.writestr("docProps/core.xml", core)
            zf.writestr("docProps/app.xml", app)
        # 1.2.5 round-3 (GPT suggestion): fsync the temp file before the atomic
        # replace, so a power cut cannot leave the *renamed* file with unwritten
        # bytes (the same durability guarantee the JSON/CSV writers already have).
        with open(tmp, "rb+") as _fh:
            os.fsync(_fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


# --------------------------------------------------------------------------
def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _shared_strings(zf) -> list:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    out = []
    for si in root:
        if _local(si.tag) != "si":
            continue
        out.append("".join(node.text or "" for node in si.iter()
                           if _local(node.tag) == "t"))
    return out


def read_xlsx(path) -> list:
    """Return rows as lists of strings; missing cells become ''."""
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        shared = _shared_strings(zf)
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in zf.namelist():
            sheets = [n for n in zf.namelist()
                      if n.startswith("xl/worksheets/") and n.endswith(".xml")]
            if not sheets:
                return []
            sheet_name = sorted(sheets)[0]
        root = ET.fromstring(zf.read(sheet_name))
    rows = []
    for row in root.iter():
        if _local(row.tag) != "row":
            continue
        values = {}
        for cell in row:
            if _local(cell.tag) != "c":
                continue
            ref = cell.attrib.get("r", "")
            m = _COL_RE.match(ref)
            index = _col_index(m.group(1)) if m else len(values) + 1
            ctype = cell.attrib.get("t")
            text = ""
            if ctype == "inlineStr":
                text = "".join(n.text or "" for n in cell.iter()
                               if _local(n.tag) == "t")
            else:
                v = next((n for n in cell if _local(n.tag) == "v"), None)
                if v is not None and v.text is not None:
                    text = v.text
                    if ctype == "s":
                        text = shared[int(text)] if int(text) < len(shared) else ""
            values[index] = text
        if values:
            width = max(values)
            rows.append([values.get(i, "") for i in range(1, width + 1)])
        else:
            rows.append([])
    return rows


def _col_index(letters: str) -> int:
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - 64)
    return index
