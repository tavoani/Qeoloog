"""Read depth-linked measurements for the local Annex 5 basement log."""

import csv
from decimal import Decimal, DecimalException
from io import StringIO
from math import isfinite
from pathlib import Path
import re
from unicodedata import normalize

from .etl_xlsx import EtlWorkbookError, MAX_COLUMNS, MAX_ROWS, read_xlsx


class BasementImportError(ValueError):
    """The selected file did not contain an unambiguous measurement table."""


TRACKS = ("density_probe", "density_sample", "magnetic", "structures", "migmatization")
SHEET_NAMES = ("Mõõteandmed", "Measurements")
MAX_CSV_BYTES = 4_000_000
_SHEETS = {name.casefold() for name in SHEET_NAMES}


def _token(value):
    key = normalize("NFKD", str(value or "")).casefold()
    key = "".join(char for char in key if not 0x300 <= ord(char) <= 0x36F)
    return re.sub(r"[^a-z0-9]+", "_", key).strip("_")


_HEADERS = {
    alias: field
    for field, aliases in {
        "track": ("rada", "track"),
        "depth": ("sugavus_m", "sygavus_m", "depth_m", "sugavus", "sygavus", "depth",
                  "algus_m", "start_m", "from_m", "depth_from_m"),
        "end": ("lopp_m", "end_m", "to_m", "depth_to_m"),
        "value": ("vaartus", "value"),
        "unit": ("uhik", "yhik", "unit"),
        "kind": ("tuup", "tyyp", "type", "kind"),
        "angle": ("kalle_deg", "dip_deg", "angle_deg", "nurk_deg"),
        "azimuth": ("asimuut_deg", "azimuth_deg", "asimuut", "azimuth"),
    }.items()
    for alias in aliases
}
_TRACKS = {
    alias: track
    for track, aliases in {
        "density_probe": ("density_probe", "probe_density", "sonditihedus", "tihedus_sond", "sondi_tihedus"),
        "density_sample": ("density_sample", "sample_density", "proovitihedus", "tihedus_proov", "proovi_tihedus"),
        "magnetic": ("magnetic", "magnetic_susceptibility", "magnetiline_vastuvotlikkus", "mag_susc", "mag_susts"),
        "structures": ("structure", "structures", "struktuur", "struktuurielement", "struktuurielemendid"),
        "migmatization": ("migmatization", "migmatiseerumine", "migmatiseerumise_aste"),
    }.items()
    for alias in aliases
}
_KINDS = {
    "foliation": "foliation", "gneisilisus": "foliation", "gneissosity": "foliation",
    "fracture": "fracture", "fractures": "fracture", "lohe": "fracture", "lohed": "fracture",
    "other": "other", "muu": "other",
}
_MIGMATIZATION_GRADES = {
    alias: grade
    for grade, aliases in {
        "none": ("none", "unmigmatized", "migmatiseerumata"),
        "weak": ("weak", "weakly_migmatized", "norgalt_migmatiseerunud"),
        "moderate": ("moderate", "moderately_migmatized", "keskmiselt_migmatiseerunud"),
        "strong": ("strong", "strongly_migmatized", "tugevalt_migmatiseerunud"),
    }.items()
    for alias in aliases
}


def _unit_token(value):
    key = normalize("NFKC", str(value or "")).casefold()
    key = key.replace("−", "-").replace("·", "").replace("×", "x").replace("^", "")
    return "".join(key.split())


_DENSITY_FACTORS = {
    "g/cm3": 0, "gcm-3": 0, "g/cc": 0,
    "kg/m3": -3, "kgm-3": -3,
}
_MAGNETIC_FACTORS = {
    "msi": 0, "10-3si": 0, "x10-3si": 0, "1e-3si": 0,
    "si": 3,
    "μsi": -3, "usi": -3, "10-6si": -3, "x10-6si": -3, "1e-6si": -3,
}
_DEGREE_UNITS = {"", "°", "deg", "degrees", "degree", "kraad", "kraadi"}
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)(?:[eE][+-]?[0-9]+)?")


def _blank(value):
    return value is None or isinstance(value, str) and not value.strip()


def _short(value):
    return repr(str(value)[:72])


def _number(value, field, error, *, factor=0):
    raw = str(value).strip()
    if len(raw) > 80 or not _DECIMAL.fullmatch(raw):
        raise error(f"{field} peab olema arv (leiti {_short(value)}).")
    try:
        # Power-of-ten unit changes preserve the written decimal before the
        # final float conversion (also used for duplicate depth checking).
        source = Decimal(raw.replace(",", "."))
        result = float(source.scaleb(factor))
    except (DecimalException, OverflowError, ValueError) as exc:
        raise error(f"{field} ei ole lõplik arv.") from exc
    if not isfinite(result) or result == 0 and source:
        raise error(f"{field} ei ole esitatav arv.")
    return result


def _csv_rows(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise BasementImportError(f"{path.name}: CSV/TSV ületab 4 MB mahupiiri.")
    source = raw.decode("utf-8-sig")
    first = next((line for line in source.splitlines() if line.strip()), "")
    if not first:
        return []
    separator = max((";", "\t", ","), key=first.count)
    rows = []
    reader = csv.reader(StringIO(source, newline=""), delimiter=separator, strict=True)
    try:
        for values in reader:
            line = reader.line_num
            if len(values) > MAX_COLUMNS:
                raise BasementImportError(f"{path.name}, rida {line}: liiga palju veerge.")
            if any(not _blank(value) for value in values):
                rows.append((line, dict(enumerate(values, 1))))
                if len(rows) > MAX_ROWS + 1:
                    raise BasementImportError(f"{path.name}, rida {line}: üle {MAX_ROWS} andmerea.")
    except csv.Error as exc:
        raise BasementImportError(f"{path.name}, rida {reader.line_num}: vigane CSV/TSV ({exc}).") from exc
    return rows


def _columns(row, error):
    columns = {}
    for index, value in row.items():
        if _blank(value):
            continue
        field = _HEADERS.get(_token(value))
        if field is not None:
            if field in columns:
                raise error(f"Korduv või samatähenduslik veerupealkiri: {_short(value)}.")
            columns[field] = index
    if not {"track", "depth"} <= columns.keys() or not (
        {"value", "angle"} & columns.keys() or {"end", "kind"} <= columns.keys()
    ):
        raise error("Päises peavad olema rada ja sügavus_m. Lisa väärtus, struktuuridel "
                    "kalle_deg või migmatiseerumisel lõpp_m ja tüüp.")
    return columns


def _structure(values, depth, error):
    value, angle = values["value"], values["angle"]
    if _unit_token(values["unit"]) not in _DEGREE_UNITS:
        raise error("Struktuuri nurga ühik peab olema kraad.")
    result = _number(angle if not _blank(angle) else value, "Struktuuri nurk", error)
    if not _blank(angle) and not _blank(value) and _number(value, "Struktuuri nurk", error) != result:
        raise error("Väärtus ja kalle_deg on vastuolus.")
    if not 0 <= result <= 90:
        raise error("Struktuuri nurk peab olema vahemikus 0–90°.")
    kind = _KINDS.get(_token(values["kind"]))
    if kind is None:
        raise error("Struktuuri tüüp peab olema gneisilisus, lõhe või muu.")
    azimuth = None
    if not _blank(values["azimuth"]):
        azimuth = _number(values["azimuth"], "Asimuut", error)
        if not 0 <= azimuth <= 360:
            raise error("Asimuut peab olema vahemikus 0–360°.")
        azimuth %= 360
    return [depth, result, kind, azimuth]


def _measurement(values, track, depth, error):
    if any(not _blank(values[field]) for field in ("angle", "kind", "azimuth")):
        raise error("Kalle, tüüp ja asimuut kuuluvad struktuurielemendi reale.")
    density = track != "magnetic"
    unit = _unit_token(values["unit"])
    factor = (_DENSITY_FACTORS if density else _MAGNETIC_FACTORS).get(unit)
    if track == "density_probe" and _blank(values["value"]):
        if not unit or factor is not None:
            return [depth, None]  # explicit break, not a zero reading
    if factor is None:
        raise error("Määra tiheduse ühikuks g/cm³ või kg/m³." if density
                    else "Määra vastuvõtlikkuse ühikuks mSI, SI või µSI.")
    result = _number(values["value"], "Väärtus", error, factor=factor)
    if density and result <= 0:
        raise error("Tihedus peab olema positiivne.")
    return [depth, result]


def _migmatization(values, start, error):
    end = _number(values["end"], "Vahemiku lõppsügavus meetrites (lõpp_m)", error)
    if end <= start:
        raise error("Lõppsügavus peab olema algussügavusest suurem.")
    if any(not _blank(values[field]) for field in ("unit", "angle", "azimuth")):
        raise error("Migmatiseerumise astmel pole ühikut, kallet ega asimuuti.")
    grades = [
        _MIGMATIZATION_GRADES.get(_token(values[field]))
        for field in ("kind", "value") if not _blank(values[field])
    ]
    if not grades or None in grades:
        raise error("Tundmatu või puuduv migmatiseerumise aste: vali migmatiseerumata, "
                    "nõrgalt, keskmiselt või tugevalt migmatiseerunud.")
    if len(set(grades)) != 1:
        raise error("Migmatiseerumise aste ja väärtus on vastuolus.")
    return [start, end, grades[0]]


def _parse_rows(rows, label):
    if not rows:
        raise BasementImportError(f"{label}: mõõteandmed puuduvad.")
    header_line, header = rows[0]
    columns = _columns(header, lambda message: BasementImportError(f"{label}, rida {header_line}: {message}"))
    named_columns = {index for index, name in header.items() if not _blank(name)}
    result = {track: [] for track in TRACKS}
    probe_seen = {}
    intervals = []
    for line, row in rows[1:]:
        def error(message):
            return BasementImportError(f"{label}, rida {line}: {message}")

        if any(index not in named_columns and not _blank(value) for index, value in row.items()):
            raise error("Andmed on veerus, millel puudub pealkiri.")
        values = {field: row.get(columns.get(field)) for field in
                  ("track", "depth", "end", "value", "unit", "kind", "angle", "azimuth")}
        if all(_blank(value) for value in values.values()):
            continue
        track = _TRACKS.get(_token(values["track"]))
        if track is None:
            raise error("Tundmatu rada (density_probe, density_sample, magnetic, structure või migmatization).")
        depth = _number(values["depth"], "Sügavus meetrites", error)
        if depth < 0:
            raise error("Sügavus ei tohi olla negatiivne.")
        if track == "migmatization":
            intervals.append((line, _migmatization(values, depth, error)))
            continue
        if not _blank(values["end"]):
            raise error("Lõppsügavust saab määrata ainult migmatiseerumise astme real.")
        if track == "structures":
            entry = _structure(values, depth, error)
        else:
            entry = _measurement(values, track, depth, error)
        if track == "density_probe":
            if depth in probe_seen and probe_seen[depth][0] != entry[1]:
                raise error(f"Sonditiheduse väärtus samal sügavusel on vastuolus reaga {probe_seen[depth][1]}.")
            probe_seen[depth] = (entry[1], line)
        result[track].append(entry)
    previous = None
    for line, entry in sorted(intervals, key=lambda interval: interval[1][0]):
        if previous is not None and entry[0] < previous[1][1]:
            raise BasementImportError(
                f"{label}, rida {line}: migmatiseerumise vahemik kattub reaga {previous[0]}."
            )
        result["migmatization"].append(entry)
        previous = line, entry
    if not any(entry[1] is not None for series in result.values() for entry in series):
        raise BasementImportError(f"{label}: kasutatavaid mõõteandmeid ei leitud.")
    for series in result.values():
        series.sort(key=lambda entry: entry[0])  # stable for repeated observations at the same depth
    return result


def read_basement_measurements(path):
    """Return JSON-ready readings and migmatization intervals, with depth in metres."""
    path = Path(path)
    try:
        extension = path.suffix.casefold()
        if extension in {".csv", ".tsv", ".txt"}:
            return _parse_rows(_csv_rows(path), path.name)
        if extension == ".xlsx":
            sheets, warnings = read_xlsx(path, _SHEETS)
            if len(sheets) != 1:
                raise BasementImportError(f"{path.name}: XLSX-is peab olema üks leht Mõõteandmed või Measurements.")
            if warnings:
                # Do not turn formula/error cells into planned probe gaps,
                # or trust a potentially stale cached formula result.
                raise BasementImportError(f"{warnings[0]} Kleebi mõõtetulemused väärtustena.")
            (name, rows), = sheets.items()
            return _parse_rows(rows, f"{path.name}/{name}")
        raise BasementImportError(f"{path.name}: vali CSV-, TSV- või XLSX-fail.")
    except (OSError, UnicodeError, EtlWorkbookError) as exc:
        raise BasementImportError(f"{path.name}: mõõtefaili ei saa lugeda ({exc}).") from exc
