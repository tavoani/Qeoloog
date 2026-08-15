"""Pure helpers for Leapfrog-compatible drillhole CSV exports."""

import re
from datetime import datetime
from math import isfinite
from unicodedata import normalize


def number(value):
    """Return a finite float or ``None``."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def compound_index(row):
    """Return an EGT index, expanding ``Liitüksus`` to lower-upper."""
    index = str(row.get("indeks") or row.get("indeks_orig") or "").strip()
    if index.casefold() not in {"liitüksus", "compound unit"}:
        return index
    invalid = {"", "ei kohaldu", "teadmata", "not applicable", "unknown"}

    def valid(value):
        text = str(value or "").strip()
        return "" if text.casefold() in invalid else text

    lower = valid(row.get("liityksus_indeks_alumine"))
    upper = valid(row.get("liityksus_indeks_ylemine"))
    if lower and upper and lower != upper:
        return f"{lower}-{upper}"
    return lower or upper


def safe_identifier(value, fallback="HOLE"):
    """Return a stable ASCII-ish identifier accepted by CSV consumers."""
    text = normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode("ascii")
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_.-")
    return text or fallback


def hole_identifier(source, role, attributes):
    """Build a source-qualified hole ID shared by all export tables."""
    attributes = attributes or {}
    if source == "EGT":
        value = (
            attributes.get("gea_id")
            or attributes.get("korrastatud_nr")
            or attributes.get("esri_globalid")
        )
        subtype = "VP" if role == "observations" else "PA"
        return safe_identifier(f"EGT_{subtype}_{value}")
    if source == "VEKA":
        value = (
            attributes.get("kkr_kood")
            or attributes.get("eelis_id")
            or attributes.get("katastri_nr")
        )
        return safe_identifier(f"VEKA_{value}")
    value = (
        attributes.get("sarv_id")
        or attributes.get("id")
        or attributes.get("number")
    )
    return safe_identifier(f"SARV_{value}")


def vertical_survey(hole_id):
    """Return one Leapfrog survey station for a vertical downward hole."""
    # Leapfrog's default convention treats negative dips as pointing upward,
    # so +90 degrees is vertically down unless the import option is inverted.
    return {
        "HoleID": str(hole_id),
        "Depth": 0.0,
        "Azimuth": 0.0,
        "Dip": 90.0,
    }


def interval_row(
    hole_id, top, bottom, lithology="", stratigraphy="",
    source="", interval_type="Geology", description="",
):
    """Return a normalized interval row, or ``None`` for invalid depths."""
    start = number(top)
    end = number(bottom)
    if start is None or end is None or start < 0 or end <= start:
        return None
    return {
        "HoleID": str(hole_id),
        "From": start,
        "To": end,
        "Lithology": str(lithology or ""),
        "Stratigraphy": str(stratigraphy or ""),
        "Source": str(source or ""),
        "IntervalType": str(interval_type or ""),
        "Description": str(description or ""),
    }


def date_key(value):
    """Return a deterministic sortable timestamp tuple."""
    text = str(value or "").strip()
    if not text:
        return (0, "")
    candidate = text[:19].replace("Z", "")
    try:
        return (1, datetime.fromisoformat(candidate))
    except ValueError:
        return (0, text)


def latest_row(rows, required_key):
    """Return the newest row containing a numeric required value."""
    usable = [
        row for row in rows or ()
        if number(row.get(required_key)) is not None
    ]
    return max(
        usable,
        key=lambda row: date_key(
            row.get("katse_kp") or row.get("proov_algus")
        ),
        default=None,
    )


def safe_column(value, fallback="Value"):
    """Return a compact CSV field name for a selected analysis."""
    text = normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"V_{text}"
    return text[:54]
