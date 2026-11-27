"""Small bounded OOXML reader/writer for the plug-in's offline ETL data tables."""

from datetime import date, datetime, timedelta
from math import isfinite
from pathlib import Path, PurePosixPath
import posixpath
import re
from xml.etree import ElementTree as ET  # nosec B405 - bounded, no declarations accepted
from xml.sax.saxutils import escape, quoteattr
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile


class EtlWorkbookError(ValueError):
    """Unsupported, malformed, ambiguous or unwritable workbook."""


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_PART = 20 * 1024 * 1024
MAX_PARTS = 256
MAX_ROWS = 20000
MAX_COLUMNS = 128
MAX_TEXT = 32767
_CELL_REF = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})")
_BAD_XML_DECL = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)", re.I)
_BAD_TEXT = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]")
_DATE_IDS = set(range(14, 23)) | {27, 28, 29, 30, 31, 34, 35, 36, 45, 46, 47, 50, 51, 52, 53, 54, 55, 56, 57, 58}
_DATE_1900 = datetime(1899, 12, 30)
_DATE_1904 = datetime(1904, 1, 1)


def _col_index(name):
    n = 0
    for letter in name:
        n = n * 26 + ord(letter) - ord("A") + 1
    return n


def _column(n):
    name = ""
    while n:
        n, index = divmod(n - 1, 26)
        name = chr(65 + index) + name
    return name


def _serial_to_iso(value, date_1904):
    # Excel's fictitious date 1900-02-29 has no valid ISO equivalent.
    if (not date_1904 and 60 <= value < 61) or value < 0:
        return value
    if date_1904:
        epoch = _DATE_1904
    else:
        epoch = _DATE_1900 + timedelta(days=1 if value < 60 else 0)
    try:
        result = epoch + timedelta(days=value)
    except (OverflowError, ValueError):
        return value
    return result.date().isoformat() if result.time() == datetime.min.time() else result.isoformat()


def _date_serial(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())
    if not isinstance(value, datetime) or value.tzinfo is not None:
        return None
    if value < datetime(1899, 12, 31):
        return None
    serial = (value - _DATE_1900).total_seconds() / 86400
    if value < datetime(1900, 3, 1):
        serial -= 1
    return serial


def _format_is_date(code):
    # Ignore display-only literals and bracketed colours/conditions.
    body = re.sub(r'"[^"]*"|\\.|\[[^]]*\]|_.|\*.', "", code.casefold())
    return re.search(r"[ydhs]|m{2,}", body) is not None


def read_xlsx(path, sheets):
    """Read literal cells of requested sheets; never run formulas or links.

    Returns {actual sheet name: [(row number, {column number: value}), ...]}.
    Formula expressions are ignored. Only an existing finite numeric formula
    cache is usable, with a warning; error and other formula cells stay blank.
    """
    path = Path(path)
    try:
        if path.stat().st_size > MAX_ARCHIVE:
            raise EtlWorkbookError(f"{path.name}: XLSX ületab mahupiiri.")
        with ZipFile(path) as archive:
            return _WorkbookReader(archive, path.name).read(sheets)
    except (OSError, BadZipFile, RuntimeError, UnicodeError, ET.ParseError) as error:
        raise EtlWorkbookError(f"{path.name}: XLSX-i ei saa lugeda ({error}).") from error


class _WorkbookReader:
    def __init__(self, archive, name):
        self.archive = archive
        self.name = name
        self.warnings = []
        entries = archive.infolist()
        if (len(entries) > MAX_PARTS or sum(item.file_size for item in entries) > MAX_ARCHIVE
                or any(item.file_size > MAX_PART for item in entries)
                or len({item.filename for item in entries}) != len(entries)):
            raise EtlWorkbookError(f"{name}: XLSX osade piir või korduv osanimi.")
        self.parts = {item.filename: item for item in entries}

    def _xml(self, part, optional=False):
        info = self.parts.get(part)
        if info is None:
            if optional:
                return None
            raise EtlWorkbookError(f"{self.name}: XLSX osa puudub ({part}).")
        with self.archive.open(info) as stream:
            raw = stream.read(MAX_PART + 1)
        if len(raw) > MAX_PART:
            raise EtlWorkbookError(f"{self.name}: liiga suur XLSX osa ({part}).")
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            data = raw.decode("utf-16")
        else:
            data = raw.decode("utf-8-sig")
        if "\x00" in data or _BAD_XML_DECL.search(data):
            raise EtlWorkbookError(f"{self.name}: XML-i olemid või dokumenditüüp on keelatud.")
        return ET.fromstring(data)  # nosec B314 - UTF-decoded, bounded, DTD/entity declarations rejected

    @staticmethod
    def _target(rel):
        if rel.get("TargetMode") == "External":
            return None
        path = rel.get("Target", "")
        if "\\" in path or ":" in path or "%" in path or "?" in path or "#" in path:
            return None
        target = posixpath.normpath(path.lstrip("/") if path.startswith("/") else "xl/" + path)
        if not target.startswith("xl/") or ".." in PurePosixPath(target).parts:
            return None
        return target

    @staticmethod
    def _text(element):
        # Only visible plain/rich text, not phonetic workbook annotations.
        if element is None:
            return ""
        return "".join(
            child.text or "" for child in (
                element.findall("{*}t") + element.findall("{*}r/{*}t")
            )
        )

    def read(self, wanted):
        doc = self._xml("xl/workbook.xml")
        prop = doc.find("{*}workbookPr")
        date_1904 = prop is not None and prop.get("date1904") in {"1", "true"}
        rels = self._xml("xl/_rels/workbook.xml.rels")
        id_map = {node.get("Id"): node for node in rels}
        self.strings = []
        self.date_styles = set()
        for rel in rels:
            kind = rel.get("Type", "").rsplit("/", 1)[-1]
            if kind not in {"sharedStrings", "styles"}:
                continue
            target = self._target(rel)
            if target is None:
                raise EtlWorkbookError(f"{self.name}: ebaturvaline XLSX {kind} viide.")
            source = self._xml(target)
            if kind == "sharedStrings":
                self.strings = [self._text(element) for element in source.findall("{*}si")]
            else:
                formats = {
                    node.get("numFmtId") for node in source.findall("{*}numFmts/{*}numFmt")
                    if _format_is_date(node.get("formatCode", ""))
                }
                for i, node in enumerate(source.findall("{*}cellXfs/{*}xf")):
                    fmt = node.get("numFmtId", "")
                    if fmt in formats or len(fmt) <= 8 and fmt.isdigit() and int(fmt) in _DATE_IDS:
                        self.date_styles.add(str(i))
        result = {}
        for sheet in doc.findall("{*}sheets/{*}sheet"):
            name = sheet.get("name", "")
            if name.casefold() not in wanted:
                continue
            if name.casefold() in {existing.casefold() for existing in result}:
                raise EtlWorkbookError(f"{self.name}: korduv leht {name}.")
            relation_id = next((value for key, value in sheet.attrib.items() if key.endswith("}id")), None)
            relation = id_map.get(relation_id)
            if relation is None or relation.get("Type", "").rsplit("/", 1)[-1] != "worksheet":
                raise EtlWorkbookError(f"{self.name}: lehe {name} viide ei ole tööleht.")
            target = self._target(relation)
            if target is None:
                raise EtlWorkbookError(f"{self.name}: lehe {name} XLSX viide on ebaturvaline.")
            result[name] = self._read_sheet(self._xml(target), name, date_1904)
        return result, self.warnings

    def _read_sheet(self, root, sheet, date_1904):
        output = []
        ignored = []
        cached = []
        for row in root.findall("{*}sheetData/{*}row"):
            values = {}
            r = None
            for cell in row.findall("{*}c"):
                text_value = cell.findtext("{*}v")
                kind = cell.get("t", "n")
                formula = cell.find("{*}f") is not None
                if text_value is None and kind != "inlineStr" and not formula:
                    continue
                ref = cell.get("r", "")
                match = _CELL_REF.fullmatch(ref)
                if not match:
                    raise EtlWorkbookError(f"{self.name}/{sheet}: vigane lahtriviide.")
                column, row_number = _col_index(match[1]), int(match[2])
                if (column > MAX_COLUMNS or row_number > MAX_ROWS + 1
                        or (r is not None and r != row_number) or column in values):
                    raise EtlWorkbookError(f"{self.name}/{sheet}: lahtripiiri või korduse viga ({ref}).")
                r = row_number
                if kind == "e" or formula and (kind != "n" or text_value is None):
                    ignored.append(ref)
                    values[column] = None
                    continue
                value = self._parse_cell(kind, text_value, cell, date_1904)
                if formula:
                    if not isinstance(value, (int, float)) and cell.get("s", "") not in self.date_styles:
                        ignored.append(ref)
                        values[column] = None
                        continue
                    cached.append(ref)
                if isinstance(value, str) and len(value) > MAX_TEXT:
                    raise EtlWorkbookError(f"{self.name}/{sheet}/{ref}: liiga pikk tekst.")
                values[column] = value
            if r is not None and any(v not in (None, "") for v in values.values()):
                output.append((r, values))
        if ignored:
            self.warnings.append(
                f"{self.name}/{sheet}: {len(ignored)} valemi- või vealahtrit jäeti lugemata ({', '.join(ignored[:4])})."
            )
        if cached:
            self.warnings.append(
                f"{self.name}/{sheet}: {len(cached)} valemilahtrist loeti ainult olemasolev "
                f"arvväärtus, mitte valem ({', '.join(cached[:4])})."
            )
        if len({row for row, _ in output}) != len(output):
            raise EtlWorkbookError(f"{self.name}/{sheet}: korduvad reanumbrid.")
        return sorted(output, key=lambda item: item[0])

    def _parse_cell(self, kind, value, cell, date_1904):
        if kind == "s":
            if not value or len(value) > 8 or not value.isascii() or not value.isdigit() or int(value) >= len(self.strings):
                raise EtlWorkbookError(f"{self.name}: vigane jagatud stringi indeks.")
            return self.strings[int(value)]
        if kind == "inlineStr":
            return self._text(cell.find("{*}is"))
        if kind in {"str", "d"}:
            return value
        if kind == "b":
            return {"0": False, "1": True}.get(value, value)
        try:
            number = int(value) if re.fullmatch(r"[-+]?[0-9]+", value) else float(value)
        except (ValueError, TypeError, OverflowError):
            return value
        try:
            if not isfinite(number):
                return value
        except OverflowError:
            return value
        if cell.get("s", "") in self.date_styles:
            return _serial_to_iso(number, date_1904)
        return number


_STYLES = f"""<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="{MAIN}">
  <numFmts count="2"><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/><numFmt numFmtId="165" formatCode="yyyy-mm-dd hh:mm:ss"/></numFmts>
  <fonts count="2"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="10"/><name val="Arial"/><color rgb="FFFFFFFF"/></font></fonts>
  <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF354754"/><bgColor indexed="64"/></patternFill></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="5">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
  </cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def _cell(value, ref, *, heading=False, date_field=False, wrapped=False):
    if value is None or value == "":
        return ""
    serial = _date_serial(value) if date_field else None
    if serial is not None:
        style = 2 if serial.is_integer() else 3
        return f'<c r="{ref}" s="{style}"><v>{serial!r}</v></c>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)) and isfinite(value):
        return f'<c r="{ref}"><v>{value!r}</v></c>'
    text_value = str(value)
    if len(text_value) > MAX_TEXT or _BAD_TEXT.search(text_value):
        raise EtlWorkbookError(f"{ref}: tekst ei mahu XLSX lahtrisse või sisaldab juhtmärki.")
    style = ' s="1"' if heading else ' s="4"' if wrapped else ""
    # inlineStr writes arbitrary values as text, never as Excel formulas.
    return f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{escape(text_value)}</t></is></c>'


def _write_sheet(archive, part, headings, rows, date_fields):
    if len(headings) > MAX_COLUMNS or len(rows) > MAX_ROWS:
        raise EtlWorkbookError("ETL tabel ületab XLSX andmepiiri.")
    columns = [_column(i) for i in range(1, len(headings) + 1)]
    long_texts = {'markus', 'lisainfo', 'litoloogia_orig', 'varvus_kirjeldus'}
    with archive.open(part, "w") as stream:
        def output(text):
            stream.write(text.encode("utf-8"))
        output(
            f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{MAIN}">'
            f'<dimension ref="A1:{columns[-1]}{len(rows)+1}"/><sheetViews><sheetView '
            'showGridLines="0" workbookViewId="0"><pane xSplit="1" ySplit="1" topLeftCell="B2" '
            'activePane="bottomRight" state="frozen"/></sheetView></sheetViews><cols>'
        )
        for i, name in enumerate(headings, 1):
            longest = max((len(str(row.get(name))) for row in rows if row.get(name) is not None), default=0)
            width = max(13, min(48, round(1.15 * max(len(name), longest) + 3)))
            if name in long_texts:
                width = 48
            output(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>')
        output('</cols><sheetData><row r="1">')
        output("".join(_cell(name, f"{col}1", heading=True) for col, name in zip(columns, headings)))
        output('</row>')
        for i, row in enumerate(rows, 2):
            lines = max((sum(max(1, (len(line) + 41) // 42)
                             for line in str(row.get(name) or '').splitlines())
                         for name in long_texts), default=1)
            height = f' ht="{min(105, 15 * lines)}" customHeight="1"' if lines > 1 else ''
            output(f'<row r="{i}"{height}>')
            output("".join(_cell(row.get(name), f"{col}{i}", date_field=name in date_fields,
                                  wrapped=name in long_texts)
                           for col, name in zip(columns, headings)))
            output('</row>')
        output('</sheetData></worksheet>')


def write_xlsx(path, tables, date_fields):
    """Write typed literal data rows in supplied order, without dependencies."""
    with ZipFile(path, "x", compression=ZIP_DEFLATED) as archive:
        items = [(index, name, f"worksheets/sheet{index}.xml")
                 for index, name in enumerate(tables, 1)]
        overview = "".join(
            f'<sheet name={quoteattr(name)} sheetId="{i}" r:id="rId{i}"/>' for i, name, _ in items
        )
        specs = "".join(
            f'<Relationship Id="rId{i}" Type="{OFFICE}/worksheet" Target="{part}"/>'
            for i, _, part in items
        )
        content = "".join(
            f'<Override PartName="/xl/{part}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for _, _, part in items
        )
        archive.writestr(
            "[Content_Types].xml",
            f'<Types xmlns="{CONTENT}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f'{content}</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            f'<Relationships xmlns="{PACKAGE}"><Relationship Id="rId1" Type="{OFFICE}/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{MAIN}" xmlns:r="{OFFICE}"><bookViews><workbookView/></bookViews><sheets>{overview}</sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{PACKAGE}">{specs}'
            f'<Relationship Id="rId{len(items)+1}" Type="{OFFICE}/styles" Target="styles.xml"/></Relationships>',
        )
        archive.writestr("xl/styles.xml", _STYLES)
        for _, name, part in items:
            columns, records = tables[name]
            _write_sheet(archive, "xl/" + part, columns, records, date_fields)
