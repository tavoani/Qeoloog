"""Build translated map-label expressions from typed, loaded point fields.

Provider-specific rules belong here so a water-level, identifier, or other
unrelated field cannot inadvertently stand in for a geological measurement.
The caller owns layer labeling, settings, and any separate EGT detail cache.
"""

from decimal import Decimal, InvalidOperation
import re


_SARV_ROLES = {"sarv_drillcores", "sarv_localities", "sarv_sites"}
_EGT_ROLES = {"boreholes", "observations", "field_mapping", "faktika"}
_SUPPORTED_ROLES = _EGT_ROLES | _SARV_ROLES | {"veka_boreholes"}

_NAMES = {
    "boreholes": ("nimi",),
    "observations": ("nimi", "korrastatud_nr"),
    "field_mapping": ("valitoo_id",),
    "faktika": ("nimi", "korrastatud_nr"),
    "veka_boreholes": ("nimi",),
}
_TEXT_KEYS = {
    "veka_boreholes": {"kkr_kood": ("kkr_kood", "Registrikood")},
    "sarv": {"number": ("number", "Number")},
}
_EGT_EXTRA_KEYS = {
    "cover_thickness": ("PP", True),
    "bedrock_elevation": ("APR", True),
    "depth_0_5": ("0,5 m", False),
    "bedrock_outcrop": ("AP", False),
}
_SARV_DEPTH_NUMBER = r"(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+)"
_SARV_DEPTH = re.compile(
    rf"\s*({_SARV_DEPTH_NUMBER})(?:\s*(?:[-–—]|\.\.)\s*({_SARV_DEPTH_NUMBER}))?\s*"
)
_CANONICAL_SARV_DEPTH = r"^[0-9]+([.][0-9]+)?(–[0-9]+([.][0-9]+)?)?$"


def normalize_sarv_core_depth(value):
    """Return a core's recorded scalar/range in metres, with decimal dots.

    The SARV drill-core API returns textual values. Preserve ranges as
    reported rather than turning their lower boundary into a borehole depth.
    A missing, ambiguous or reversed value is unsupported, not zero.
    """
    if isinstance(value, str):
        match = _SARV_DEPTH.fullmatch(value)
        if not match:
            return None
        readings = [part.replace(",", ".") for part in match.groups() if part is not None]
    elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        readings = [str(value)]
    else:
        return None
    try:
        values = [Decimal(reading) for reading in readings]
    except InvalidOperation:
        return None
    if any(not number.is_finite() or number < 0 for number in values):
        return None
    if len(values) == 2 and values[1] < values[0]:
        return None
    rendered = [format(number if number else Decimal(0), "f") for number in values]
    return "–".join(text.rstrip("0").rstrip(".") if "." in text else text for text in rendered)


def _literal(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def _text(fields):
    if not fields:
        return ""
    branches = [
        f"with_variable('qeoloog_label_text', trim(to_string(\"{field}\")), "
        "if(lower(@qeoloog_label_text) IN ('', 'null', '<null>', 'none', "
        "'teadmata', 'unknown', 'ei kohaldu', 'n/a'), NULL, @qeoloog_label_text))"
        for field in fields
    ]
    return f"coalesce({', '.join([*branches, repr('')])})"


def _prefix_value(expression, prefix, suffix=""):
    if not expression:
        return ""
    return (
        "with_variable('qeoloog_label_value', "
        f"{expression}, if(@qeoloog_label_value IS NULL OR @qeoloog_label_value = '', "
        f"'', {_literal(prefix)} || @qeoloog_label_value || {_literal(suffix)}))"
    )


def _measurement(fields, prefix, language, *, nonnegative):
    if not fields:
        return ""
    readings = [
        f"""try(to_real(replace(trim(to_string("{field}")), ',', '.')), NULL)"""
        for field in fields
    ]
    # The self-difference check excludes ±inf/NaN without imposing a
    # depth limit or losing valid negative bedrock elevations.
    valid = "@element - @element = 0"
    if nonnegative:
        valid += " AND @element >= 0"
    text = "to_string(round(@qeoloog_label_measurement, 2))"
    if language == "et":
        text = f"replace({text}, '.', ',')"
    return (
        "with_variable('qeoloog_label_measurement', array_first(array_filter("
        f"array({', '.join(readings)}), {valid})), "
        f"if(@qeoloog_label_measurement IS NULL, '', "
        f"{_literal(prefix)} || {text} || ' m'))"
    )


def label_component(fields, role, key, *, language="et", translate=lambda text: text):
    """Return a QgsExpression string or '' when a key has no native field.

    ``fields`` can be a QgsFields or a collection of plain field names. An
    available field with missing/invalid data emits an empty value for that
    feature, so label composition does not introduce an empty row.
    """
    if role not in _SUPPORTED_ROLES:
        return ""
    available = set(fields.names() if hasattr(fields, "names") else fields)

    def present(candidates):
        return [name for name in candidates if name in available]

    if key == "name":
        candidates = _NAMES.get(role)
        if not candidates:
            candidates = ("name_en", "name") if language == "en" else ("name",)
        return _text(present(candidates))
    if key == "alias":
        # Do not promote English translations, site numbers, registry
        # numbers, or addresses to aliases.
        return _text(present(("alias",)))
    if key == "borehole_depth":
        if role == "sarv_drillcores":
            # The legacy drill-core depth field historically inherited the
            # locality's value if the core record had no depth. Do not use
            # that potentially inherited number, even on old layers where
            # the explicit core-only field is unavailable.
            if "label_depth" not in available:
                return ""
            rendered = (
                "replace(@qeoloog_core_depth, '.', ',')" if language == "et"
                else "@qeoloog_core_depth"
            )
            value = (
                "with_variable('qeoloog_core_depth', trim(to_string(\"label_depth\")), "
                f"if(regexp_replace(@qeoloog_core_depth, {_literal(_CANONICAL_SARV_DEPTH)}, '') = '', "
                f"{rendered}, ''))"
            )
            return _prefix_value(value, translate("Sügavus") + ": ", " m")
        elif role in _SARV_ROLES:
            candidates = ("depth",)
        elif role == "veka_boreholes":
            candidates = ("sygavus",)
        else:
            # Both public EGT point types use the logged object's length;
            # the observation-point water depth is separate and unrelated.
            candidates = ("pikkus", "vertikaalne_ulatus")
        return _measurement(
            present(candidates), translate("Sügavus") + ": ", language, nonnegative=True,
        )
    if role in _EGT_ROLES and key in _EGT_EXTRA_KEYS:
        caption, numeric = _EGT_EXTRA_KEYS[key]
        prefix = translate(caption) + ": "
        if numeric:
            return _measurement(
                present((key,)), prefix, language, nonnegative=(key == "cover_thickness"),
            )
        return _prefix_value(_text(present((key,))), prefix)
    text_specs = _TEXT_KEYS.get("sarv" if role in _SARV_ROLES else role, {})
    if key in text_specs:
        field, caption = text_specs[key]
        return _prefix_value(_text(present((field,))), translate(caption) + ": ")
    return ""


def join_label_components(components):
    """Combine nonempty expression components without blank label lines."""
    parts = [component for component in components if component]
    if not parts:
        return ""
    return (
        "coalesce(array_to_string(array_filter(array("
        + ", ".join(parts)
        + "), @element IS NOT NULL AND @element <> ''), char(10)), '')"
    )
