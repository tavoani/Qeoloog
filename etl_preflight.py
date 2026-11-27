"""Check the ETL export selection without modifying its local records."""

from collections import Counter
from dataclasses import dataclass

from .etl_domains import domain_match
from .etl_workbooks import (
    ETL6_SHEET, ETL_CHILD_SHEETS, ETL_PHENOMENON_SHEET, ETL_UNIT_SHEET,
    _access_issues, _blank, _code, _export_ids, _finite_number, _id_index,
    _interval_issues, _key, _lab_export_ids, _lab_issues, _row_issues,
    _typed, _validate_export_link,
)
from .faktika import COMPOUND_INDEX
from .local_objects import local_object_name
from .local_unit_rules import COMPOUND_COMPONENTS, unit_field_options


_RELATIVE = ("z_suht_ylemine", "z_suht_alumine")
_ABSOLUTE = ("z_abs_ylemine", "z_abs_alumine")
_EPSILON = 1e-8
_ROUNDING_TOLERANCE = 0.011
_FIELD_NAMES = {
    "genees": "Genees",
    "kivim_nimetus": "Litoloogia täiend",
    "kihistik": "Kihistik",
    "liityksus_indeks_ylemine": "Liitüksuse ülemine indeks",
    "liityksus_indeks_alumine": "Liitüksuse alumine indeks",
    "liityksus_kihistik_ylemine": "Liitüksuse ülemine kihistik",
    "liityksus_kihistik_alumine": "Liitüksuse alumine kihistik",
}
_UNKNOWN = frozenset({997, 998, 999})


@dataclass(frozen=True)
class EtlExportIssue:
    object_name: str
    sheet: str
    row: int | None
    field: str | None
    message: str
    row_id: str | None = None
    object_id: str | None = None

    def __str__(self):
        location = ", ".join(part for part in (self.object_name, self.sheet) if part)
        if self.row is not None:
            location += f", rida {self.row}"
        if self.row_id:
            location += f" ({self.row_id})"
        return f"{location}: {self.message}" if location else self.message


@dataclass(frozen=True)
class EtlExportReview:
    errors: tuple[EtlExportIssue, ...]
    warnings: tuple[EtlExportIssue, ...]


class _Review:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def reporter(self, record, sheet, row=None, values=None):
        name = str(local_object_name(record) or "")
        row_id = _code((values or {}).get("ID_ajutine")) or None
        object_id = record.get("id")

        def add(message, *, field=None, error=False):
            check = EtlExportIssue(name, sheet, row, field, message, row_id, object_id)
            (self.errors if error else self.warnings).append(check)

        return add


def _legacy_warnings(add, check, *args, **kwargs):
    """Retain the established ETL metadata/link messages at a known location."""
    details = []
    check(*args, "", details, **kwargs)
    for message in details:
        add(message.removeprefix(": "))


def _warn_text_code(add, field, name, raw, match):
    if isinstance(_typed(field, raw), str):
        add(f"{name} läheb faili tekstina ({raw}). Koodi {match[0]} salvestamiseks "
            "vali väärtus redaktori valikloendist uuesti.", field=field)


def _unit_classifiers(unit, add):
    main = domain_match(ETL_UNIT_SHEET, "indeks", unit.get("indeks"))
    compound = main is not None and main[0] == COMPOUND_INDEX
    for field, name in (("yksus_kood", "Üksuse kood"), ("indeks", "Indeks")):
        raw = unit.get(field)
        match = domain_match(ETL_UNIT_SHEET, field, raw, row=unit)
        if match:
            _warn_text_code(add, field, name, raw, match)
        elif field == "indeks" and main:
            add(f"{name} ei kuulu selle rea üksuse tüübi lubatud valikutesse: {raw}.", field=field)
    inactive = set()
    for field, name in _FIELD_NAMES.items():
        raw = unit.get(field)
        options = unit_field_options(field, unit)
        match = domain_match(ETL_UNIT_SHEET, field, raw, row=unit)
        global_match = match or domain_match(ETL_UNIT_SHEET, field, raw)
        code = global_match[0] if global_match else None
        if not options:
            inactive.add(field)
        if compound and field in COMPOUND_COMPONENTS:
            if _blank(raw) or code in _UNKNOWN:
                add(f"{name} on määramata. Vali konkreetne indeks.", field=field, error=True)
            elif match not in options:
                add(f"{name} ei ole selle rea lubatud indeks: {raw}.", field=field, error=True)
            else:
                _warn_text_code(add, field, name, raw, match)
            continue
        if _blank(raw):
            continue
        if not options:
            # Existing ETL archives legitimately use explicit unknown or
            # not-applicable placeholders even in an inactive classifier.
            if code not in _UNKNOWN:
                add(f"{name} ei kohaldu sellel real, kuid lahtris on väärtus {raw}.", field=field)
        elif match not in options:
            add(f"{name} ei kuulu selle rea lubatud valikutesse: {raw}.", field=field)
        else:
            _warn_text_code(add, field, name, raw, match)
    return inactive | COMPOUND_COMPONENTS


def _unit_interval(unit, parent_z, add):
    top, base = (_finite_number(unit.get(key)) for key in _RELATIVE)
    for field, depth in zip(_RELATIVE, (top, base)):
        raw = unit.get(field)
        if depth is None and not _blank(raw):
            add(f"Suhteline sügavus ei ole lõplik arv: {raw}.", field=field, error=True)
        elif depth is not None and depth < 0:
            add(f"Suhteline sügavus on negatiivne: {depth:g} m.", field=field, error=True)
    if top is not None and base is not None:
        if base < top:
            add(f"Suhtelise sügavuse piirid on vigased: alumine piir {base:g} m "
                f"on ülemisest piirist {top:g} m kõrgemal.", field=_RELATIVE[1], error=True)
        elif base == top:
            add(f"Sügavusvahemikul on sama ülemine ja alumine piir ({top:g} m).", field=_RELATIVE[1])
        thickness = _finite_number(unit.get("paksus"))
        if base >= top and thickness is not None and abs(base - top - thickness) > _ROUNDING_TOLERANCE:
            add("paksus ei ühti suhteliste piiridega.", field="paksus")
    top_abs, base_abs = (_finite_number(unit.get(key)) for key in _ABSOLUTE)
    if top_abs is not None and base_abs is not None and top_abs < base_abs - _EPSILON:
        add("Absoluutkõrguse piirid on vastupidises järjekorras.", field=_ABSOLUTE[1], error=True)
    if parent_z is not None:
        for field, depth, absolute in zip(_ABSOLUTE, (top, base), (top_abs, base_abs)):
            if depth is not None and absolute is not None and abs(parent_z - depth - absolute) > _ROUNDING_TOLERANCE:
                add("absoluutkõrgus ei ühti punkti kõrguse ja suhtelise sügavusega. "
                    "Kontrolli nullpunkti ja kõrgussüsteemi.", field=field)
    if top is not None and base is not None and 0 <= top < base:
        return top, base
    return None


def _check_intersections(sequence):
    # Keep the interval extending furthest below the current start. Checking
    # just the previous sorted row misses an overlap after a contained interval.
    frontier = None
    for top, base, row, add in sorted(sequence, key=lambda item: item[:3]):
        if frontier is not None:
            prior_base, prior_row = frontier
            if top < prior_base - _EPSILON:
                add(f"Suhtelised vahemikud kattuvad reaga {prior_row}: "
                    f"algus {top:g} m, varasema rea lõpp {prior_base:g} m.",
                    field=_RELATIVE[0], error=True)
            elif top > prior_base + _ROUNDING_TOLERANCE:
                add(f"Eelmise üksuseni (rida {prior_row}) on lünk: "
                    f"{prior_base:g}–{top:g} m.", field=_RELATIVE[0])
        if frontier is None or base > frontier[0]:
            frontier = (base, row)


def review_etl(records, *, lab=False):
    """Classify export findings; never edit records or claim EGT approval."""
    records = list(_export_ids(list(records)))
    review = _Review()
    table = [record["attributes"] for record in records]
    parent_ids = Counter(_key(row.get("ID_ajutine")) for row in table)
    unit_ids = Counter(_key(row.get("ID_ajutine")) for record in records for row in record.get("units") or ())
    explicit = _id_index(table, ("ID_ajutine", "alias"))
    temporary = _id_index(table, ("ID_ajutine",))

    for ordinal, record in enumerate(records):
        attrs = record["attributes"]
        add = review.reporter(record, ETL6_SHEET, values=attrs)
        _legacy_warnings(add, _row_issues, ETL6_SHEET, attrs)
        if parent_ids[_key(attrs.get("ID_ajutine"))] > 1:
            add("ID_ajutine kordub.", field="ID_ajutine")
        _legacy_warnings(add, _access_issues, attrs)
        parent_z = _finite_number(attrs.get("geom_z"))
        sequence = []
        parent_units = set()

        def check_link(row, report):
            messages = []
            _validate_export_link(row, "", ordinal, explicit, temporary, messages)
            for message in messages:
                report(message.removeprefix(": "), field="puurauk_vaatluspunkt_id")

        for line, row in enumerate(record.get("units") or (), 1):
            unit_id = _key(row.get("ID_ajutine"))
            parent_units.add(unit_id)
            add = review.reporter(record, ETL_UNIT_SHEET, line, row)
            inapplicable = _unit_classifiers(row, add)
            _legacy_warnings(add, _row_issues, ETL_UNIT_SHEET, row,
                             optional_fields=inapplicable, checked_numeric_fields=_RELATIVE)
            check_link(row, add)
            if interval := _unit_interval(row, parent_z, add):
                sequence.append((*interval, line, add))
            if unit_id and unit_ids[unit_id] > 1:
                add("Üksuse ID_ajutine kordub.", field="ID_ajutine")
        _check_intersections(sequence)

        for sheet in ETL_CHILD_SHEETS:
            for line, row in enumerate((record.get("related") or {}).get(sheet) or (), 1):
                add = review.reporter(record, sheet, line, row)
                _legacy_warnings(add, _row_issues, sheet, row)
                if sheet == ETL_PHENOMENON_SHEET:
                    messages = []
                    _interval_issues(row, "", parent_z, messages)
                    for message in messages:
                        add(message.removeprefix(": "))
                    check_link(row, add)
                else:
                    row_id = _key(row.get("ID_ajutine"))
                    if not row_id or row_id not in parent_units or unit_ids[row_id] != 1:
                        add("Geoloogilise üksuse ID_ajutine seos pole üheselt määratud.", field="ID_ajutine")
    if lab:
        _lab_export_ids(records)
        review.warnings.extend(EtlExportIssue("", "", None, None, message)
                               for message in _lab_issues(records))
    return EtlExportReview(tuple(review.errors), tuple(review.warnings))
