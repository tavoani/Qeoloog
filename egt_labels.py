"""Pure helpers for EGT borehole and observation-point map labels."""

from math import isfinite


_EMPTY_VALUES = {
    "", "ei kohaldu", "teadmata", "null", "none", "na", "n/a",
}


def _text(value):
    text = str(value or "").strip()
    return "" if text.casefold() in _EMPTY_VALUES else text


def _number(value):
    try:
        result = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def unit_index(unit):
    """Return a normal or compound stratigraphic index for display."""
    index = _text(unit.get("indeks") or unit.get("indeks_orig"))
    if index.casefold() != "liitüksus":
        return index
    lower = _text(unit.get("liityksus_indeks_alumine"))
    upper = _text(unit.get("liityksus_indeks_ylemine"))
    if lower and upper and lower != upper:
        return f"{lower}-{upper}"
    return lower or upper


def _depth_description(unit):
    lithology = _text(unit.get("litoloogia")) or _text(
        unit.get("litoloogia_orig")
    )
    # Genesis remains useful for observation points and preserves the earlier
    # 0.5 m label while the requested stratigraphic index is added in front.
    values = (unit_index(unit), _text(unit.get("genees")), lithology)
    return " · ".join(value for value in values if value)


def _units_at_depth(units, depth):
    candidates = []
    terminal = []
    for unit in units:
        top = _number(unit.get("z_suht_ylemine"))
        bottom = _number(unit.get("z_suht_alumine"))
        if top is None or bottom is None or top < 0 or bottom <= top:
            continue
        if top <= depth < bottom:
            candidates.append(unit)
        elif top < depth and bottom == depth:
            terminal.append(unit)
    return candidates or terminal


def _is_bedrock(unit):
    try:
        if int(float(unit.get("klassif_yksus_kood"))) == 2:
            return True
    except (TypeError, ValueError):
        pass
    return _text(unit.get("yksus_kood")).casefold() == "aluspõhi"


def egt_label_summary(units, depth=0.5):
    """Summarize one EGT object's intervals for configurable map labels.

    Cover thickness is the relative depth of the shallowest valid bedrock
    interval.  The same interval supplies the bedrock-surface elevation and
    outcrop/subcrop index, keeping the three derived values internally
    consistent.
    """
    result = {}
    descriptions = {
        description for unit in _units_at_depth(units, depth)
        if (description := _depth_description(unit))
    }
    if descriptions:
        result["depth_0_5"] = " / ".join(
            sorted(descriptions, key=str.casefold)
        )

    bedrock = []
    for unit in units:
        if not _is_bedrock(unit):
            continue
        top = _number(unit.get("z_suht_ylemine"))
        if top is not None and top >= 0:
            bedrock.append((top, unit))
    if not bedrock:
        return result

    first_depth = min(item[0] for item in bedrock)
    first_units = [
        unit for top, unit in bedrock if abs(top - first_depth) <= 1e-6
    ]
    # A bedrock surface less than one metre below ground is considered the
    # representative 0.5 m unit.  This avoids labelling a very thin cover
    # interval when the map label is intended to describe the practically
    # exposed bedrock.
    if first_depth < 1.0:
        bedrock_descriptions = {
            description for unit in first_units
            if (description := _depth_description(unit))
        }
        if bedrock_descriptions:
            result["depth_0_5"] = " / ".join(
                sorted(bedrock_descriptions, key=str.casefold)
            )
    result["cover_thickness"] = first_depth
    elevation = next((
        value for unit in first_units
        if (value := _number(unit.get("z_abs_ylemine"))) is not None
    ), None)
    if elevation is not None:
        result["bedrock_elevation"] = elevation
    indices = {
        index for unit in first_units if (index := unit_index(unit))
    }
    if indices:
        result["bedrock_outcrop"] = " / ".join(
            sorted(indices, key=str.casefold)
        )
    return result


def egt_label_summaries(rows, depth=0.5):
    """Build uppercase parent-UUID keyed summaries from WFS interval rows."""
    grouped = {}
    for row in rows:
        parent = str(row.get("puurauk_vaatluspunkt_id") or "").strip().upper()
        if parent:
            grouped.setdefault(parent, []).append(row)
    return {
        parent: summary for parent, units in grouped.items()
        if (summary := egt_label_summary(units, depth=depth))
    }
