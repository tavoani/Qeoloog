"""Pure helpers for locally persisted drill-core box corrections."""


CORE_FIELDS = ("number", "top", "bottom", "diameter", "status")

SOURCE_FIELDS = {
    "EGT": {
        "number": "kast_nr",
        "top": "z_suht_ylemine",
        "bottom": "z_suht_alumine",
        "diameter": "diameeter",
        "status": "staatus",
    },
    "SARV": {
        "number": "number",
        "top": "depth_start",
        "bottom": "depth_end",
        "diameter": "diameter",
        "status": "_qeoloog_status",
    },
}


def core_record_id(source, row):
    """Return the stable upstream record identifier for a core box."""
    row = row or {}
    if str(source).upper() == "EGT":
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
    return {
        key: row.get(fields.get(key))
        for key in CORE_FIELDS
    }


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
