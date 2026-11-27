"""Pure helpers for locally persisted drill-core box corrections."""


CORE_FIELDS = (
    "number", "top", "bottom", "diameter", "status", "description",
)

SOURCE_FIELDS = {
    "EGT": {
        "number": "kast_nr",
        "top": "z_suht_ylemine",
        "bottom": "z_suht_alumine",
        "diameter": "diameeter",
        "status": "staatus",
        "description": "kirjeldus",
    },
    "SARV": {
        "number": "number",
        "top": "depth_start",
        "bottom": "depth_end",
        "diameter": "diameter",
        "status": "_qeoloog_status",
        "description": "_qeoloog_description",
    },
    "MARU": {
        "number": "kast_nr",
        "top": "z_suht_ylemine",
        "bottom": "z_suht_alumine",
        "diameter": "diameeter",
        "status": "staatus",
        "description": "kirjeldus",
    },
}


def core_record_id(source, row):
    """Return the stable upstream record identifier for a core box."""
    row = row or {}
    if str(source).upper() in {"EGT", "MARU"}:
        value = (
            row.get("globalid")
            or row.get("objectid")
        )
    else:
        value = (
            row.get("id")
            or row.get("uuid")
            or row.get("image")
        )
    return str(value or "").strip()


def core_correction_key(source, row):
    """Return a source-qualified correction key, or an empty string."""
    source = str(source or "").upper()
    identifier = core_record_id(source, row)
    return f"{source}:{identifier}" if source and identifier else ""


def core_values(source, row):
    """Return editable standardized values from a source-specific row."""
    row = row or {}
    fields = SOURCE_FIELDS.get(str(source or "").upper(), {})
    values = {key: row.get(fields.get(key)) for key in CORE_FIELDS}
    if values.get("description") in (None, ""):
        values["description"] = next(
            (
                row.get(name) for name in (
                    "tx_kirjeldus", "kirjeldus", "description",
                    "description_et", "notes", "markus",
                ) if row.get(name) not in (None, "")
            ),
            None,
        )
    return values


def apply_core_values(source, row, values):
    """Return a copy of ``row`` with standardized local values applied."""
    result = dict(row or {})
    fields = SOURCE_FIELDS.get(str(source or "").upper(), {})
    for key in CORE_FIELDS:
        if key in (values or {}) and fields.get(key):
            result[fields[key]] = values[key]
    return result


def changed_core_values(original, corrected):
    """Return only standardized fields whose values actually differ."""
    changed = {}
    for key in CORE_FIELDS:
        before = original.get(key)
        after = corrected.get(key)
        if _comparable(key, before) != _comparable(key, after):
            changed[key] = after
    return changed


def core_intervals_overlap(first, second):
    """Return whether two complete depth intervals overlap by positive depth."""
    try:
        first_top = float(first.get("top"))
        first_bottom = float(first.get("bottom"))
        second_top = float(second.get("top"))
        second_bottom = float(second.get("bottom"))
    except (AttributeError, TypeError, ValueError):
        return False
    if first_bottom <= first_top or second_bottom <= second_top:
        return False
    return max(first_top, second_top) < min(first_bottom, second_bottom)


def _comparable(key, value):
    if value in (None, ""):
        return None
    if key in {"top", "bottom", "diameter"}:
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            pass
    if isinstance(value, str):
        return value.strip()
    return value
