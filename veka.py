"""Pure helpers for VEKA/EELIS well filtering and map metrics."""

from collections import defaultdict
from datetime import datetime
from html.parser import HTMLParser
from math import isfinite
import re
from urllib.parse import quote, urljoin


FILTER_CONSTRUCTION_TYPES = {
    "filter",
    "kruusakottfilter",
    "kruusfilter",
    "perfofilter",
    "pilufilter",
    "plastfilter",
    "plastpilufilter",
    "sõelfilter",
    "traatfilter",
    "varrasfilter",
    "võrkfilter",
}
CASING_CONSTRUCTION_TYPES = {
    "betoonrõngas",
    "juhttoru",
    "toru",
    "vasktoru",
}
ANALYSIS_KEY_SEPARATOR = "\x1f"
ANALYSIS_CODE_SEPARATOR = "\x1e"
SAFE_NAME_ALIASES = {
    "ammoonium (nh4+)",
    "arseen (as)",
    "coli-laadsed bakterid",
    "elektrijuhtivus",
    "enterokokid",
    "escherichia coli",
    "hagusus",
    "maitse",
    "oksudeeritavus",
    "varvus",
    "uldkaredus",
    "uldraud",
}


def number(value):
    """Return a finite float or ``None`` for an unusable API value."""
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def year_from_value(value):
    """Extract a four-digit year from ISO or VEKA display dates."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    for candidate in (text[:4], text[-4:]):
        if candidate.isdigit():
            year = int(candidate)
            if 1800 <= year <= 2200:
                return year
    return None


def date_key(value):
    """Return a sortable date key; missing/unparseable dates sort first."""
    if value in (None, ""):
        return (0, "")
    text = str(value).strip()
    for pattern in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            parsed = datetime.strptime(text[:19] if "T" in pattern else text, pattern)
            return (1, parsed.isoformat())
        except ValueError:
            continue
    return (0, text)


def in_range(value, minimum=None, maximum=None):
    """Return whether a numeric value lies in an optional inclusive range."""
    numeric = number(value)
    if numeric is None:
        return minimum is None and maximum is None
    return (
        (minimum is None or numeric >= minimum)
        and (maximum is None or numeric <= maximum)
    )


def interval_intersects(top, bottom, minimum=None, maximum=None):
    """Return whether a construction interval intersects a depth range."""
    top = number(top)
    bottom = number(bottom)
    if top is None or bottom is None:
        return False
    if bottom < top:
        top, bottom = bottom, top
    return (
        (minimum is None or bottom >= minimum)
        and (maximum is None or top <= maximum)
    )


def specific_capacity(row):
    """Calculate specific capacity in l/(s*m) from discharge and drawdown."""
    discharge = number(row.get("deebit"))
    drawdown = number(row.get("alandus"))
    if discharge is None or drawdown is None or drawdown <= 0:
        return None
    return discharge / drawdown


def latest_static_water_level(rows):
    """Return the newest pumping-test row with a valid static water level."""
    candidates = [
        row for row in (rows or ())
        if number(row.get("st_veetase")) is not None
        and number(row.get("st_veetase")) >= 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: date_key(row.get("katse_kp")))


def construction_category(value):
    """Classify a VEKA construction code for the detail presentation."""
    code = str(value or "").strip().casefold()
    if code == "p":
        return "drill"
    if code in FILTER_CONSTRUCTION_TYPES or (
        "filter" in code and code != "filtrita"
    ):
        return "filter"
    if code.startswith("manteltoru") or code in CASING_CONSTRUCTION_TYPES:
        return "casing"
    if code in {"manteldamata", "filtrita"}:
        return "open"
    return "other"


def cadastral_number(*values):
    """Return a VEKA chemistry key from a cadastral number or PRK code."""
    for value in values:
        text = str(value or "").strip()
        if not text or text.casefold() in {"null", "none", "<null>"}:
            continue
        numeric = re.fullmatch(r"(\d+)(?:\.0+)?", text)
        if numeric:
            return str(int(numeric.group(1)))
        registry = re.search(r"PRK0*(\d+)$", text, re.IGNORECASE)
        if registry:
            return str(int(registry.group(1)))
    return ""


def normalized_analysis_number(value):
    """Return a punctuation-insensitive key for a laboratory analysis number."""
    return re.sub(r"[^0-9a-z]+", "", str(value or "").casefold())


def converted_result(value, unit, indicator_name=""):
    """Convert a numeric or qualified result while preserving ``<``/``>``."""
    text = str(value or "").strip().replace(",", ".")
    match = re.match(r"^\s*(<=|>=|<|>|≤|≥)?\s*(-?(?:\d+(?:\.\d*)?|\.\d+))", text)
    if not match:
        return None, unit_spec(unit, indicator_name)[1]
    qualifier = {
        "≤": "<=",
        "≥": ">=",
    }.get(match.group(1), match.group(1) or "")
    numeric = float(match.group(2))
    _, target_unit, multiplier = unit_spec(unit, indicator_name)
    converted = numeric * multiplier
    if qualifier:
        return f"{qualifier}{converted:g}", target_unit
    return converted, target_unit


def merge_water_analyses(primary_rows, legacy_rows):
    """Append legacy VEKA rows unless an equivalent primary row exists."""
    primary = list(primary_rows or ())

    def fingerprint(row):
        date = str(row.get("proov_algus") or "").strip()
        try:
            date = datetime.strptime(date, "%d.%m.%Y").strftime("%Y-%m-%d")
        except ValueError:
            date = date[:10]
        return (
            date,
            normalized_indicator_name(
                row.get("naitaja_nimi") or row.get("naitaja_kood")
            ),
            str(row.get("naitaja_tulem") or "").strip().replace(",", "."),
            normalized_unit(row.get("naitaja_yhik")),
        )

    primary_keys = {fingerprint(row) for row in primary}
    return primary + [
        row for row in (legacy_rows or ())
        if fingerprint(row) not in primary_keys
    ]


def kotkas_registry_url(permit_number):
    """Return a public KOTKAS groundwater-monitoring report search URL."""
    permit = quote(str(permit_number or "").strip(), safe="")
    if not permit:
        return ""
    return (
        "https://kotkas.envir.ee/permits/public_assignment_index"
        f"?search=1&s__permit_nr_like={permit}&s__type=WATER_10"
    )


class _VekaAnalysisParser(HTMLParser):
    def __init__(self, source_url):
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.rows = []
        self._h6 = None
        self._analysis = None
        self._table = None
        self._tr = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        if tag == "h6":
            self._h6 = []
        elif tag == "table" and self._analysis:
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._tr = []
        elif tag in {"th", "td"} and self._tr is not None:
            self._cell = []

    def handle_data(self, data):
        if self._h6 is not None:
            self._h6.append(data)
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag in {"th", "td"} and self._cell is not None:
            self._tr.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._tr is not None:
            if any(self._tr):
                self._table.append(self._tr)
            self._tr = None
        elif tag == "table" and self._table is not None:
            self._finish_table()
            self._table = None
        elif tag == "h6" and self._h6 is not None:
            text = " ".join("".join(self._h6).split())
            self._h6 = None
            if "veeproovi analüüsi akt" in text.casefold():
                dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", text)
                identifiers = re.findall(r"\b\d{8,}\b", text)
                self._analysis = {
                    "analyys_number": identifiers[-1] if identifiers else "",
                    "proov_algus": dates[0] if dates else "",
                }

    def _finish_table(self):
        if not self._analysis or not self._table:
            return
        header = [value.casefold() for value in self._table[0]]
        if not {"nimetus", "tulemus", "ühik"}.issubset(set(header)):
            return
        indexes = {
            name: header.index(name) for name in ("nimetus", "tulemus", "ühik")
        }
        for values in self._table[1:]:
            if len(values) <= max(indexes.values()):
                continue
            name = values[indexes["nimetus"]]
            result = values[indexes["tulemus"]]
            if not name and not result:
                continue
            self.rows.append({
                **self._analysis,
                "naitaja_kood": "",
                "naitaja_nimi": name,
                "naitaja_tulem": result,
                "naitaja_yhik": values[indexes["ühik"]],
                "proov_liik": "",
                "_protocol_url": self.source_url,
                "_protocol_label": "VEKA",
                "_source": "VEKA",
            })


def parse_veka_water_analyses(payload, source_url=""):
    """Parse legacy water analyses embedded in a public VEKA well page."""
    parser = _VekaAnalysisParser(source_url)
    parser.feed(str(payload or ""))
    parser.close()
    return parser.rows


class _KotkasRegistryParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.reports = {}
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.casefold() == "tr":
            self._row = {"cells": [], "url": ""}
        elif tag.casefold() == "td" and self._row is not None:
            self._cell = []
        elif tag.casefold() == "a" and self._row is not None:
            href = attrs.get("href", "")
            if "public_assignment_view" in href:
                self._row["url"] = urljoin("https://kotkas.envir.ee", href)

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag.casefold() == "td" and self._cell is not None:
            self._row["cells"].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag.casefold() == "tr" and self._row is not None:
            text = " ".join(self._row["cells"])
            dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", text)
            if self._row["url"] and len(dates) >= 2:
                self.reports[
                    (_iso_date(dates[-2]), _iso_date(dates[-1]))
                ] = self._row["url"]
            self._row = None


def _iso_date(value):
    try:
        return datetime.strptime(str(value), "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        return str(value or "")[:10]


def parse_kotkas_report_registry(payload):
    """Map report periods to their public KOTKAS detail URLs."""
    parser = _KotkasRegistryParser()
    parser.feed(str(payload or ""))
    parser.close()
    return parser.reports


class _KotkasProtocolParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.samples = defaultdict(lambda: {"analysis": "", "files": []})
        self._field = None
        self._index = None
        self._text = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.casefold() == "td":
            data_id = attrs.get("data-id", "")
            match = re.search(
                r"AS_WATER_10_SELF_T:(\d+):"
                r"AS_WATER_10_SELF_T_(AnalyysiNumber|Failid)$",
                data_id,
            )
            if match:
                self._index = match.group(1)
                self._field = match.group(2)
                self._text = []
        elif (
            tag.casefold() == "a"
            and self._field == "Failid"
            and self._index is not None
        ):
            href = attrs.get("href", "")
            if "forms_file_download" in href:
                self.samples[self._index]["files"].append({
                    "url": urljoin("https://kotkas.envir.ee", href),
                    "label": "",
                })

    def handle_data(self, data):
        if self._text is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.casefold() == "a" and self._field == "Failid":
            text = " ".join("".join(self._text or []).split())
            files = self.samples[self._index]["files"]
            if files and text:
                files[-1]["label"] = text
        elif tag.casefold() == "td" and self._field:
            text = " ".join("".join(self._text or []).split())
            if self._field == "AnalyysiNumber":
                self.samples[self._index]["analysis"] = text
            self._field = None
            self._index = None
            self._text = None


def parse_kotkas_protocols(payload):
    """Map normalized analysis numbers to public original protocol files."""
    parser = _KotkasProtocolParser()
    parser.feed(str(payload or ""))
    parser.close()
    result = {}
    for sample in parser.samples.values():
        key = normalized_analysis_number(sample["analysis"])
        if key and sample["files"]:
            result[key] = sample["files"]
    return result


def aggregate(rows, value_getter, mode="latest", date_field="katse_kp"):
    """Reduce related rows to one scalar suitable for map symbology."""
    pairs = [
        (row, number(value_getter(row)))
        for row in rows
    ]
    pairs = [(row, value) for row, value in pairs if value is not None]
    if not pairs:
        return None
    values = [value for _, value in pairs]
    if mode == "max":
        return max(values)
    if mode == "min":
        return min(values)
    if mode == "mean":
        return sum(values) / len(values)
    return max(pairs, key=lambda pair: date_key(pair[0].get(date_field)))[1]


def group_rows(rows, key):
    """Group related API records by a normalized non-empty key."""
    grouped = defaultdict(list)
    for row in rows or ():
        value = row.get(key)
        if value not in (None, ""):
            grouped[str(value).strip()].append(row)
    return dict(grouped)


def normalized_unit(value):
    """Normalize unit spelling while retaining scientifically distinct units."""
    text = str(value or "").strip().casefold().replace("μ", "µ")
    text = text.replace("–", "-").replace("−", "-")
    return re.sub(r"\s+", " ", text)


def normalized_indicator_name(value):
    """Return a stable comparison key for names attached to generic codes."""
    text = str(value or "").strip().casefold()
    text = text.translate(str.maketrans("äöõüšž", "aoousz"))
    return re.sub(r"\s+", " ", text)


def unit_spec(value, indicator_name=""):
    """Return ``(family, canonical unit, multiplier to canonical unit)``."""
    unit = normalized_unit(value)
    compact = unit.replace(" ", "")
    compact = compact.replace("mg/i", "mg/l")

    # Platinum-cobalt colour is numerically equivalent to mg Pt/l.
    if (
        compact.startswith("mg/lpt")
        or compact.startswith(("pt-co", "pt/co"))
        or compact == "kraadi"
    ):
        return "colour_pt", "Pt-Co", 1.0

    # Mass concentration is normalized to mg/l. Suffixes in VEKA often
    # contain the analyte or a limit value, not a different unit.
    if compact.startswith(("µg/l", "ug/l", "mikrog/l", "qg/l")):
        return "mass_per_volume", "mg/l", 0.001
    if compact.startswith("pg/l"):
        return "mass_per_volume", "mg/l", 1e-9
    if compact.startswith("g/l"):
        return "mass_per_volume", "mg/l", 1000.0
    if (
        compact.startswith("mg/l")
        or re.match(r"^mg(?:o2?|n|p|sio2)/l", compact)
    ):
        return "mass_per_volume", "mg/l", 1.0

    # Colony counts and most-probable-number results share the same numeric
    # volume basis. The method remains part of the source row, but filtering
    # uses a common count per 100 ml.
    if re.match(r"^(?:pmü|mpn|arv)/100m(?:l)?", compact):
        return "count_per_volume", "arv/100 ml", 1.0
    if re.match(r"^(?:pmü|arv)/(?:1)?ml", compact):
        return "count_per_volume", "arv/100 ml", 100.0
    if compact == "ml":
        name = normalized_indicator_name(indicator_name)
        if "kolooniate arv" in name:
            return "count_per_volume", "arv/100 ml", 100.0
        if any(
            token in name
            for token in ("coli", "escherichia", "enterok", "clostridium")
        ):
            return "count_per_volume", "arv/100 ml", 1.0

    if compact.startswith("µs/cm") or compact.startswith("µscm-"):
        return "conductivity", "µS/cm", 1.0
    if compact in {"ph", "ph-ühik", "phühik"}:
        return "ph", "pH", 1.0
    if compact in {"pall", "palli", "5pall-sk"}:
        return "score", "palli", 1.0
    if compact in {"nhü", "nhu"}:
        return "threshold_odour", "NHÜ", 1.0
    if compact in {"lahjendusaste", "lahejendusaste"}:
        return "dilution", "lahjendusaste", 1.0
    if compact in {"mg-ekv/l", "mg-ek/l"}:
        return "equivalent_concentration", "mg-ekv/l", 1.0
    if compact.startswith("%o2küllastusastmest") or compact == "%":
        return "percentage", "%", 1.0

    # Unknown units are combined only when their normalized text is equal.
    return f"literal:{unit}", unit, 1.0


def analysis_key(code, unit, name=""):
    """Build a stable key for an indicator, optional name and target unit."""
    if isinstance(code, (list, tuple, set, frozenset)):
        code = ANALYSIS_CODE_SEPARATOR.join(
            sorted({str(item).strip() for item in code if str(item).strip()})
        )
    return ANALYSIS_KEY_SEPARATOR.join((
        str(code or "").strip(),
        normalized_indicator_name(name),
        str(unit or "").strip(),
    ))


def split_analysis_key(value):
    """Return ``(code, optional name key, target unit)`` from a selection key."""
    parts = str(value or "").split(ANALYSIS_KEY_SEPARATOR)
    if len(parts) >= 3:
        return parts[0].strip(), normalized_indicator_name(parts[1]), parts[2].strip()
    if len(parts) == 2:  # compatibility with the first 3.14.0 development build
        return parts[0].strip(), "", parts[1].strip()
    return parts[0].strip(), "", ""


def analysis_codes(value):
    """Return all source codes represented by a unified selection."""
    encoded, _, _ = split_analysis_key(value)
    return tuple(
        code for code in encoded.split(ANALYSIS_CODE_SEPARATOR) if code
    )


def _generic_analysis_code(code):
    return str(code or "").strip().casefold() in {
        "-", "none", "null", "puudub", "määramata", "maaramaata",
    }


def analysis_row_value(row, selection_key):
    """Return a selected result converted to its target unit, or ``None``."""
    _, name_key, target_unit = split_analysis_key(selection_key)
    if str(row.get("naitaja_kood") or "").strip() not in analysis_codes(
        selection_key
    ):
        return None
    if name_key and normalized_indicator_name(row.get("naitaja_nimi")) != name_key:
        return None
    numeric = number(row.get("_qeoloog_value"))
    if numeric is not None and row.get("_qeoloog_unit") == target_unit:
        return numeric
    numeric = number(row.get("naitaja_tulem"))
    if numeric is None:
        return None
    source_family, _, source_factor = unit_spec(
        row.get("naitaja_yhik"), row.get("naitaja_nimi")
    )
    target_family, _, target_factor = unit_spec(target_unit)
    if source_family != target_family:
        return None
    return numeric * source_factor / target_factor


def hydro_matches(rows, requirements):
    """Evaluate discharge/specific-capacity requirements for one well."""
    debit_min = requirements.get("debit_min")
    debit_max = requirements.get("debit_max")
    specific_min = requirements.get("specific_min")
    specific_max = requirements.get("specific_max")
    active = any(
        value is not None
        for value in (debit_min, debit_max, specific_min, specific_max)
    )
    if not active:
        return True
    rows = list(rows or ())
    mode = requirements.get("hydro_mode", "any")
    if mode == "any":
        return any(
            in_range(row.get("deebit"), debit_min, debit_max)
            and in_range(specific_capacity(row), specific_min, specific_max)
            for row in rows
        )
    if mode == "latest":
        usable = []
        for row in rows:
            if (debit_min is not None or debit_max is not None) and number(
                row.get("deebit")
            ) is None:
                continue
            if (specific_min is not None or specific_max is not None) and specific_capacity(
                row
            ) is None:
                continue
            usable.append(row)
        if not usable:
            return False
        row = max(usable, key=lambda item: date_key(item.get("katse_kp")))
        return (
            in_range(row.get("deebit"), debit_min, debit_max)
            and in_range(specific_capacity(row), specific_min, specific_max)
        )
    debit = aggregate(rows, lambda row: row.get("deebit"), mode)
    specific = aggregate(rows, specific_capacity, mode)
    return (
        in_range(debit, debit_min, debit_max)
        and in_range(specific, specific_min, specific_max)
    )


def analysis_matches(rows, requirements):
    """Evaluate one selected water-quality parameter for a cadastral number."""
    key = str(requirements.get("analysis_code") or "")
    codes = analysis_codes(key)
    minimum = requirements.get("analysis_min")
    maximum = requirements.get("analysis_max")
    year_min = requirements.get("analysis_year_min")
    year_max = requirements.get("analysis_year_max")
    if not codes:
        return True
    relevant = [
        row for row in rows or ()
        if analysis_row_value(row, key) is not None
        and (
            year_min is None
            or (year_from_value(row.get("proov_algus")) or -1) >= year_min
        )
        and (
            year_max is None
            or (year_from_value(row.get("proov_algus")) or 9999) <= year_max
        )
    ]
    if not relevant:
        return False
    mode = requirements.get("analysis_mode", "any")
    if mode == "any":
        return any(
            in_range(analysis_row_value(row, key), minimum, maximum)
            for row in relevant
        )
    value = aggregate(
        relevant,
        lambda row: analysis_row_value(row, key),
        mode,
        date_field="proov_algus",
    )
    return in_range(value, minimum, maximum)


def analysis_options(rows):
    """Return one option per indicator and safely convertible unit family."""
    groups = {}
    for row in rows or ():
        code = str(row.get("naitaja_kood") or "").strip()
        if not code:
            continue
        name = str(row.get("naitaja_nimi") or code).strip()
        normalized_name = normalized_indicator_name(name)
        merge_by_name = (
            normalized_name in SAFE_NAME_ALIASES
            or _generic_analysis_code(code)
        )
        # Keep the name in every selection key. A few VEKA source codes are
        # reused for genuinely different named indicators, so filtering only
        # by code would silently mix their results.
        name_key = normalized_name
        family, target_unit, _ = unit_spec(
            row.get("naitaja_yhik"), row.get("naitaja_nimi")
        )
        identity = f"name:{normalized_name}" if merge_by_name else f"code:{code}"
        group = groups.setdefault(
            (identity, name_key, family),
            {"names": defaultdict(int), "unit": target_unit, "codes": set()},
        )
        group["names"][name] += 1
        group["codes"].add(code)
    prepared = []
    for (_, name_key, _), group in groups.items():
        name = max(
            group["names"], key=lambda item: (group["names"][item], item)
        )
        unit = group["unit"]
        label = f"{name} [{unit}]" if unit else name
        prepared.append((
            analysis_key(group["codes"], unit, name_key), label,
            ", ".join(sorted(group["codes"])),
        ))
    label_counts = defaultdict(int)
    for _, label, _ in prepared:
        label_counts[label.casefold()] += 1
    values = [
        (
            key,
            f"{label} · {codes}" if label_counts[label.casefold()] > 1 else label,
        )
        for key, label, codes in prepared
    ]
    return sorted(values, key=lambda item: item[1].casefold())


def quantile_breaks(values, classes):
    """Return monotonically increasing upper breaks for a quantile renderer."""
    ordered = sorted(number(value) for value in values)
    ordered = [value for value in ordered if value is not None]
    if not ordered:
        return []
    classes = max(1, min(int(classes), len(ordered)))
    breaks = []
    for index in range(1, classes + 1):
        position = min(len(ordered) - 1, (index * len(ordered) - 1) // classes)
        value = ordered[position]
        if not breaks or value > breaks[-1]:
            breaks.append(value)
    return breaks


def equal_breaks(values, classes):
    """Return upper breaks for equal-interval classification."""
    usable = [number(value) for value in values]
    usable = [value for value in usable if value is not None]
    if not usable:
        return []
    minimum, maximum = min(usable), max(usable)
    if minimum == maximum:
        return [maximum]
    classes = max(1, int(classes))
    width = (maximum - minimum) / classes
    return [minimum + width * index for index in range(1, classes)] + [maximum]
