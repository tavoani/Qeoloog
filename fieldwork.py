"""Validation helpers for authenticated EGT fieldwork imports."""

import csv
from math import hypot, isfinite
from pathlib import Path


MAX_FIELDWORK_FILE_BYTES = 100 * 1024 * 1024
MAX_FIELDWORK_POINTS = 1_000_000


def read_collar_points(path):
    """Read ordered ``x``, ``y`` and ``z`` points from a collar CSV file."""
    source = Path(path)
    if not source.is_file():
        raise ValueError("CSV-faili ei leitud.")
    if source.stat().st_size > MAX_FIELDWORK_FILE_BYTES:
        raise ValueError("CSV-fail on suurem kui 100 MB.")
    raw = source.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "cp1257"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("CSV-faili kodeering peab olema UTF-8 või Windows-1257.")

    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV-failil puudub päiserida.")
    fields = {
        str(name or "").strip().casefold(): name
        for name in reader.fieldnames
    }
    missing = [name for name in ("x", "y", "z") if name not in fields]
    if missing:
        raise ValueError(
            "CSV-failis puuduvad kohustuslikud veerud: " + ", ".join(missing)
        )

    result = []
    for row_number, row in enumerate(reader, 2):
        if len(result) >= MAX_FIELDWORK_POINTS:
            raise ValueError("CSV-failis on üle 1 000 000 punkti.")
        try:
            x = float(str(row.get(fields["x"], "")).strip().replace(",", "."))
            y = float(str(row.get(fields["y"], "")).strip().replace(",", "."))
            z = float(str(row.get(fields["z"], "")).strip().replace(",", "."))
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"CSV rea {row_number} x, y või z väärtus ei ole arv."
            ) from error
        if not all(isfinite(value) for value in (x, y, z)):
            raise ValueError(
                f"CSV rea {row_number} koordinaat ei ole lõplik arv."
            )
        identifier = ""
        if "holeid" in fields:
            identifier = str(row.get(fields["holeid"], "") or "").strip()
        result.append((x, y, z, identifier))
    if len(result) < 2:
        raise ValueError("Joone loomiseks peab CSV-failis olema vähemalt kaks punkti.")
    return result


def split_line_parts(points, maximum_gap=50.0):
    """Split an ordered point sequence where consecutive XY distance exceeds a limit."""
    if maximum_gap <= 0:
        raise ValueError("Joone katkestamise kaugus peab olema positiivne.")
    parts = []
    current = []
    for point in points:
        if current and hypot(
            float(point[0]) - float(current[-1][0]),
            float(point[1]) - float(current[-1][1]),
        ) > maximum_gap:
            if len(current) >= 2:
                parts.append(current)
            current = []
        current.append(point)
    if len(current) >= 2:
        parts.append(current)
    return parts


def coded_value_options(layer_metadata, field_name):
    """Return ``(code, label)`` pairs from a live ArcGIS coded-value domain."""
    for field in (layer_metadata or {}).get("fields") or []:
        if str(field.get("name") or "").casefold() != field_name.casefold():
            continue
        domain = field.get("domain") or {}
        if domain.get("type") != "codedValue":
            return []
        return [
            (item.get("code"), str(item.get("name") or item.get("code")))
            for item in domain.get("codedValues") or []
            if item.get("code") not in (None, "")
        ]
    return []


def value_map_options(config):
    """Return ``(code, label)`` pairs from a QGIS ValueMap configuration."""
    result = []
    for item in (config or {}).get("map") or []:
        if not isinstance(item, dict):
            continue
        for label, code in item.items():
            if code in (None, ""):
                continue
            result.append((code, str(label or code)))
    return result


def compatible_device_options(method_code, method_options, device_options):
    """Keep known EGT method/device combinations while retaining domain defaults."""
    method_name = next((
        label for code, label in method_options if code == method_code
    ), "").casefold()
    if "georadar" in method_name:
        tokens = ("zond", "määra", "select")
    elif "ttem" in method_name:
        tokens = ("1t", "3t", "määra", "select")
    elif "seismo" in method_name:
        tokens = ("määra", "select")
    else:
        return list(device_options)
    filtered = [
        item for item in device_options
        if any(token in item[1].casefold() for token in tokens)
    ]
    return filtered or list(device_options)
