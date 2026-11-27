"""Depth-specific descriptions for EGT observation points (no QGIS imports)."""

from math import isfinite


OBSERVATION_LABEL_DEPTH = 0.5
_EMPTY_VALUES = {"", "ei kohaldu", "teadmata", "null", "none", "na", "n/a"}


def _text(value):
    text = str(value or "").strip()
    return "" if text.casefold() in _EMPTY_VALUES else text


def _depth(value):
    try:
        result = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def unit_genesis(unit):
    """Use the published genesis code, never the numeric classifier ID."""
    return _text(unit.get("genees"))


def observation_index(unit, index):
    """Keep genesis next to (and independent of) the stratigraphic index."""
    return " · ".join(value for value in (index, unit_genesis(unit)) if value)


def observation_label(units, depth=OBSERVATION_LABEL_DEPTH):
    """Describe the interval at depth, without borrowing from other depths.

    The deeper interval wins at a shared boundary. A terminal bottom at the
    requested depth is usable if there is no deeper interval. Conflicting
    overlapping descriptions are retained, not arbitrarily chosen or mixed.
    """
    candidates = []
    terminal = []
    for unit in units:
        top = _depth(unit.get("z_suht_ylemine"))
        bottom = _depth(unit.get("z_suht_alumine"))
        if top is None or bottom is None or top < 0 or bottom <= top:
            continue
        if top <= depth < bottom:
            candidates.append(unit)
        elif top < depth and bottom == depth:
            terminal.append(unit)
    descriptions = set()
    for unit in candidates or terminal:
        lithology = (
            _text(unit.get("litoloogia"))
            or _text(unit.get("litoloogia_orig"))
        )
        description = " · ".join(
            value for value in (unit_genesis(unit), lithology) if value
        )
        if description:
            descriptions.add(description)
    return " / ".join(sorted(descriptions, key=str.casefold))


def observation_labels(rows):
    """Build one UUID-keyed label lookup from a batch of geological units."""
    grouped = {}
    for row in rows:
        parent = str(row.get("puurauk_vaatluspunkt_id") or "").strip().upper()
        if parent:
            grouped.setdefault(parent, []).append(row)
    return {
        parent: label for parent, units in grouped.items()
        if (label := observation_label(units))
    }
