"""Local ETL6/7/8/10 workbook interchange (no database publication)."""

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
from math import isfinite
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from .etl_lab import (
    ETL7_FIELDS, ETL8_FIELDS, LAB_FIELDS, LAB_REFERENCES, LAB_REQUIRED,
    LAB_DATE_FIELDS, LAB_INT_FIELDS, LAB_NUMBER_FIELDS, LAB_TEXT_FIELDS,
    SERIES, SAMPLE, MEASUREMENT, RESULT, is_guid, lab_key, link_lab_tables, check_lab_links,
)
from .etl_xlsx import MAX_ARCHIVE, EtlWorkbookError, read_xlsx, write_xlsx


ETL6_SHEET = "Mall"
ETL_UNIT_SHEET = "geol_yksus_mall"
ETL_PHENOMENON_SHEET = "nahtus_mall"
ETL6_FIELDS = tuple("""
ID_ajutine geom_x geom_y geom_z korrastatud_nr ma_orig_id sarv_id hydro_id nimi alias
objekti_tyyp yksus_kood pikkus vertikaalne_ulatus maaratud_veealune_sygavus sygavuse_viis
kande_alus kande_alus_nr puursydamik asukoha_tapsusklass puurimisfirma valmimise_kuupaev
tellija juurdepaasupiirang puurauk_staatus geomorfoloogia paiknemine kaardistus_q
kaardistus_ap markus egt_ylevaatus lisainfo juurdepaasu_alus1 kehtiv_kuni1
juurdepaasu_alus2 kehtiv_kuni2 juurdepaasu_alus3 kehtiv_kuni3 lisaja lisamise_aeg
""".split())
ETL10_FIELDS = {
    ETL_UNIT_SHEET: tuple("""
ID_ajutine aktiivne z_abs_ylemine z_abs_alumine z_suht_ylemine z_suht_alumine paksus
aasta kande_alus kande_alus_nr yksus_kood indeks kihistik genees litoloogia kivim_nimetus
terasuurus struktuur tekstuur tekstuuri_taiend sekundaarsed_muutused litoloogia_dunham
alumine_kontaktpind varvus_kirjeldus tsementeerumisaste tsemendi_liik ymardusaste
org_aine_protsent org_aine_meetod org_aine_instrument_protsent valjatulek
liityksus_indeks_ylemine liityksus_indeks_alumine liityksus_kihistik_ylemine
liityksus_kihistik_alumine indeks_orig litoloogia_orig markus egt_ylevaatus
puurauk_vaatluspunkt_id isik_nimi lisaja lisamise_aeg
""".split()),
    "geol_vahekiht_mall": tuple("ID_ajutine yksus_kood litoloogia protsent markus lisaja lisamise_aeg".split()),
    "geol_mineraal_mall": tuple("ID_ajutine mineraal analyys_meetod protsent protsent_instrument markus lisaja lisamise_aeg".split()),
    "geol_fos_det_mall": tuple("ID_ajutine fossiilid_detriidid protsent markus lisaja lisamise_aeg".split()),
    ETL_PHENOMENON_SHEET: tuple("""
ID_ajutine aktiivne z_abs_ylemine z_abs_alumine z_suht_ylemine z_suht_alumine paksus
aasta kande_alus kande_alus_nr yksus_kood nahtus protsent markus
puurauk_vaatluspunkt_id isik_nimi lisaja lisamise_aeg
""".split()),
}
ETL_CHILD_SHEETS = tuple(sheet for sheet in ETL10_FIELDS if sheet != ETL_UNIT_SHEET)
ETL_DATE_FIELDS = frozenset({
    "valmimise_kuupaev", "kehtiv_kuni1", "kehtiv_kuni2", "kehtiv_kuni3", "lisamise_aeg",
}) | LAB_DATE_FIELDS
ETL_INT_FIELDS = frozenset({
    "korrastatud_nr", "ma_orig_id", "sarv_id", "aasta", "protsent_instrument",
    "org_aine_instrument_protsent",
}) | LAB_INT_FIELDS
ETL_NUMERIC_FIELDS = frozenset({
    "geom_x", "geom_y", "geom_z", "pikkus", "vertikaalne_ulatus", "maaratud_veealune_sygavus",
    "z_abs_ylemine", "z_abs_alumine", "z_suht_ylemine", "z_suht_alumine", "paksus",
    "valjatulek",
}) | ETL_INT_FIELDS | LAB_NUMBER_FIELDS
ETL_TEXT_FIELDS = frozenset({
    "ID_ajutine", "hydro_id", "nimi", "alias", "kande_alus_nr", "puurauk_vaatluspunkt_id",
}) | LAB_TEXT_FIELDS
_ETL6_OPTIONAL = frozenset("""
korrastatud_nr ma_orig_id sarv_id hydro_id nimi alias vertikaalne_ulatus
maaratud_veealune_sygavus kande_alus_nr valmimise_kuupaev markus lisainfo
juurdepaasu_alus1 kehtiv_kuni1 juurdepaasu_alus2 kehtiv_kuni2 juurdepaasu_alus3 kehtiv_kuni3
""".split())
_ETL10_OPTIONAL = frozenset("""
kande_alus_nr varvus_kirjeldus org_aine_instrument_protsent valjatulek indeks_orig
litoloogia_orig markus protsent_instrument sekundaarsed_muutused
""".split())
ETL_REQUIRED_FIELDS = {
    ETL6_SHEET: frozenset(ETL6_FIELDS) - _ETL6_OPTIONAL,
    **{sheet: frozenset(fields) - _ETL10_OPTIONAL for sheet, fields in ETL10_FIELDS.items()},
    **LAB_REQUIRED,
}
_SCHEMAS = {ETL6_SHEET: ETL6_FIELDS, **ETL10_FIELDS, **LAB_FIELDS}
_PARENT_REF_FIELD = "puurauk_vaatluspunkt_id"
_PARENT_KEYS = ("ID_ajutine", "globalid", "esri_globalid", "gea_id", "alias")
_EXPLICIT_UNIT_FIELDS = ("geol_yksus_id", "geoloogiline_yksus_id")


@dataclass
class EtlImportResult:
    records: list
    warnings: list
    unlinked: dict
    updates: list = field(default_factory=list)


def _blank(value):
    return value is None or isinstance(value, str) and not value.strip()


def _finite_number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    try:
        numeric = float(value)
        return numeric if isfinite(numeric) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _key(value):
    if _blank(value):
        return ""
    text = str(value).strip()
    try:
        return str(UUID(text))
    except ValueError:
        return text.casefold()


def _code(value):
    return "" if _blank(value) else str(value).strip()


def _iso_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip()).date()
        except ValueError:
            return None
    return None


def _known_columns(sheet, row):
    canonical = {key.casefold(): key for key in _SCHEMAS[sheet]}
    canonical["puusydamik"] = "puursydamik"
    canonical.update({key: key for key in (*_PARENT_KEYS[1:-1], *_EXPLICIT_UNIT_FIELDS)})
    result = {}
    for position, value in row.items():
        if isinstance(value, str) and value.strip():
            name = value.strip()
            result[position] = canonical.get(name.casefold(), name)
    return result


def _typed(field, value):
    if _blank(value):
        return None
    if field in ETL_TEXT_FIELDS:
        # These are record identifiers, even if the source cell is numeric.
        return str(int(value) if isinstance(value, float) and value.is_integer() else value)
    if field in ETL_NUMERIC_FIELDS and isinstance(value, str):
        number = _finite_number(value)
        if number is not None and field not in ETL_INT_FIELDS:
            return number
        if number is not None and number.is_integer():
            return int(number)
    return value


def _read_tables(paths):
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    tables = defaultdict(list)
    warnings = []
    found = set()
    seen_workbooks = set()
    if len(paths := list(paths)) > 24:
        raise EtlWorkbookError("Vali kuni 24 ETL-töövihikut korraga.")
    canonical = {name.casefold(): name for name in _SCHEMAS}
    for path in dict.fromkeys(Path(path).resolve() for path in paths):
        if path.suffix.casefold() != ".xlsx":
            raise EtlWorkbookError(f"{path.name}: toetatud on XLSX, mitte vana XLS või XLSM.")
        digest = sha256()
        size = 0
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(block)
                if size > MAX_ARCHIVE:
                    raise EtlWorkbookError(f"{path.name}: XLSX ületab mahupiiri.")
                digest.update(block)
        identity = digest.hexdigest()
        if identity in seen_workbooks:
            warnings.append(f"{path.name}: samasisuline töövihik oli juba valitud.")
            continue
        seen_workbooks.add(identity)
        sheets, notes = read_xlsx(path, canonical)
        warnings.extend(notes)
        if not sheets:
            raise EtlWorkbookError(f"{path.name}: ETL6, ETL7, ETL8 ega ETL10 andmelehti ei leitud.")
        for raw_sheet, rows in sheets.items():
            sheet = canonical[raw_sheet.casefold()]
            if not rows:
                continue
            headings = _known_columns(sheet, rows[0][1])
            if "ID_ajutine" not in headings.values():
                raise EtlWorkbookError(f"{path.name}/{raw_sheet}: päises puudub ID_ajutine.")
            if len({name.casefold() for name in headings.values()}) != len(headings):
                raise EtlWorkbookError(f"{path.name}/{raw_sheet}: korduvad veerunimed.")
            found.add(sheet)
            missing = [key for key in _SCHEMAS[sheet] if key not in headings.values()]
            additional = [key for key in headings.values() if key not in _SCHEMAS[sheet]]
            if missing:
                warnings.append(f"{path.name}/{raw_sheet}: puuduvad malliveerud: {', '.join(missing)}.")
            if additional:
                warnings.append(f"{path.name}/{raw_sheet}: lisaveerud säilivad kohalikult, "
                                f"kuid ei kuulu standardsesse eksporti: {', '.join(additional)}.")
            for row_number, cells in rows[1:]:
                record = dict.fromkeys(_SCHEMAS[sheet])
                record.update({name: _typed(name, cells.get(index))
                               for index, name in headings.items()})
                if any(not _blank(value) for value in record.values()):
                    origin = {"file": path.name, "sheet": raw_sheet, "row": row_number}
                    if sheet == ETL6_SHEET:
                        origin["import_key"] = f"ETL6:{identity}:{row_number}"
                    tables[sheet].append((record, origin))
    return tables, warnings, found


def _id_index(records, fields):
    result = defaultdict(set)
    for index, row in enumerate(records):
        for field in fields:
            if key := _key(row.get(field)):
                result[key].add(index)
    return result


def _prefix_match(identifier, index):
    """Longest unique token prefix, never PA1 inside PA11."""
    prefix = identifier
    while "_" in prefix:
        prefix = prefix.rsplit("_", 1)[0]
        if candidates := index.get(prefix):
            return next(iter(candidates)) if len(candidates) == 1 else None
    return None


def import_etl(paths, *, existing_records=()):
    """Preview exact lab links and ETL6/10 points without modifying a workspace."""
    tables, warnings, found = _read_tables(paths)
    lab_present = bool(found.intersection(LAB_FIELDS))
    existing_records = list(existing_records) if lab_present else []
    if ETL6_SHEET not in found or not tables[ETL6_SHEET]:
        if not lab_present or not existing_records:
            raise EtlWorkbookError("Lisa ETL6 Mall-leht punktidega või vali ETL7/8 jaoks olemasolevad kohalikud objektid.")
    parent_rows = [row for row, _ in tables[ETL6_SHEET]]
    records = [
        {
            "id": uuid4().hex,
            "attributes": row,
            "units": [],
            "related": {sheet: [] for sheet in ETL_CHILD_SHEETS},
            "provenance": origin,
        }
        for row, origin in tables[ETL6_SHEET]
    ]
    exact = _id_index(parent_rows, _PARENT_KEYS)
    temporary = _id_index(parent_rows, ("ID_ajutine",))
    linked_units = defaultdict(set)
    # Each array entry denotes an actual unique unit, not a location.
    unit_locations = []
    unlinked = defaultdict(list)
    inferred = Counter()

    def parent_index(row, sheet):
        if explicit := _key(row.get(_PARENT_REF_FIELD)):
            options = exact.get(explicit, set())
            return next(iter(options)) if len(options) == 1 else None
        index = _prefix_match(_key(row.get("ID_ajutine")), temporary)
        if index is not None:
            inferred[sheet] += 1
        return index

    for row, _ in tables[ETL_UNIT_SHEET]:
        parent = parent_index(row, ETL_UNIT_SHEET)
        if parent is None:
            unlinked[ETL_UNIT_SHEET].append(row)
            continue
        for key in ("ID_ajutine", "globalid", "esri_globalid"):
            if identifier := _key(row.get(key)):
                linked_units[identifier].add(len(unit_locations))
        unit_locations.append(parent)
        records[parent]["units"].append(row)

    for sheet in ETL_CHILD_SHEETS:
        for row, _ in tables[sheet]:
            if sheet == ETL_PHENOMENON_SHEET:
                parent = parent_index(row, sheet)
            else:
                explicit = next((_key(row.get(key)) for key in _EXPLICIT_UNIT_FIELDS if not _blank(row.get(key))), "")
                options = linked_units.get(explicit or _key(row.get("ID_ajutine")), set())
                parent = unit_locations[next(iter(options))] if len(options) == 1 else None
            if parent is None:
                unlinked[sheet].append(row)
            else:
                records[parent]["related"][sheet].append(row)
    if inferred:
        counts = "; ".join(f"{sheet}: {count}" for sheet, count in inferred.items())
        warnings.append(f"Puuduva vanemviite tõttu kasutati pikimat üheselt sobivat "
                        f"ID_ajutine eesliidet ({counts}). Kontrolli seosed üle.")
    updates = []
    if lab_present:
        targets = records + deepcopy(existing_records)
        changed = link_lab_tables(tables, targets, warnings, unlinked)
        updates = [targets[index] for index in sorted(changed) if index >= len(records)]
    for sheet, rows in unlinked.items():
        examples = ", ".join(_code(row.get("ID_ajutine")) or "(tühi)" for row in rows[:4])
        warnings.append(f"{sheet}: {len(rows)} rida jäi sidumata (puuduv, vastuoluline "
                        f"või mitmetähenduslik viide). Näited: {examples}.")
    duplicates = [identifier for identifier, indexes in temporary.items() if len(indexes) > 1]
    if duplicates:
        warnings.append(f"ETL6: korduvad ID_ajutine väärtused ({', '.join(duplicates[:4])}); "
                        "mitmetähenduslikke alamridu ei seostatud.")
    return EtlImportResult(records, warnings, dict(unlinked), updates)


def _row_issues(sheet, row, label, issues, *, optional_fields=(), checked_numeric_fields=()):
    missing = [key for key in _SCHEMAS[sheet] if key in ETL_REQUIRED_FIELDS[sheet]
               and key not in optional_fields and _blank(row.get(key))]
    if missing:
        issues.append(f"{label}: kohustuslikud väljad: {', '.join(missing)}.")
    invalid = []
    for key in _SCHEMAS[sheet]:
        value = row.get(key)
        if _blank(value):
            continue
        if key in ETL_NUMERIC_FIELDS and key not in checked_numeric_fields:
            number = _finite_number(value)
            if number is None or key in ETL_INT_FIELDS and not number.is_integer():
                invalid.append(key)
        elif key in ETL_DATE_FIELDS and _iso_date(value) is None:
            invalid.append(key)
    if invalid:
        issues.append(f"{label}: arv või kuupäev on vigase tüübiga ({', '.join(invalid)}).")
    # A real source GUID is not replaceable with the example's local ID.
    parent = row.get(_PARENT_REF_FIELD)
    if sheet not in LAB_FIELDS and _PARENT_REF_FIELD in _SCHEMAS[sheet] and not _blank(parent):
        try:
            UUID(str(parent).strip())
        except ValueError:
            issues.append(f"{label}: puurauk_vaatluspunkt_id ei ole GUID.")


def _access_issues(row, label, issues):
    access = _key(row.get("juurdepaasupiirang"))
    for pair in range(1, 4):
        base, until = row.get(f"juurdepaasu_alus{pair}"), row.get(f"kehtiv_kuni{pair}")
        only_one = _blank(base) != _blank(until)
        if access in {"1", "jah", "true"}:
            invalid = only_one or (pair == 1 and _blank(base))
        elif access in {"0", "ei", "false"}:
            invalid = only_one or (not _blank(until) and (_iso_date(until) or date.max) > date.today())
        elif access in {"997", "998", "teadmata", "ei kohaldu"}:
            invalid = not _blank(base) or not _blank(until)
        else:
            invalid = only_one
        if invalid:
            issues.append(f"{label}: juurdepaasu_alus{pair} ja kehtiv_kuni{pair} ei vasta juurdepääsureeglile.")


def _interval_issues(row, label, parent_z, issues):
    top, base, thickness = [_finite_number(row.get(k)) for k in
                            ("z_suht_ylemine", "z_suht_alumine", "paksus")]
    if top is not None and base is not None:
        if top < 0 or base < top:
            issues.append(f"{label}: suhtelise sügavuse piirid on vigased.")
        if thickness is not None and abs((base - top) - thickness) > 0.011:
            issues.append(f"{label}: paksus ei ühti suhteliste piiridega.")
    top_abs, base_abs = [_finite_number(row.get(k)) for k in ("z_abs_ylemine", "z_abs_alumine")]
    if top_abs is not None and base_abs is not None and top_abs < base_abs - 0.011:
        issues.append(f"{label}: absoluutkõrguse piirid on vastupidises järjekorras.")
    if parent_z is not None and ((top is not None and top_abs is not None and abs(parent_z - top - top_abs) > 0.011)
                                 or (base is not None and base_abs is not None and abs(parent_z - base - base_abs) > 0.011)):
        issues.append(f"{label}: absoluutkõrgus ei ühti punkti kõrguse ja suhtelise sügavusega.")
    return top, base


def _export_ids(records):
    """Create a working-only set of identifiers for blank local records."""
    parents = {_key((record.get("attributes") or {}).get("ID_ajutine")) for record in records}
    details = {_key(row.get("ID_ajutine"))
               for record in records for row in (
                   list(record.get("units") or ()) +
                   list((record.get("related") or {}).get(ETL_PHENOMENON_SHEET) or ())
               )}
    for ordinal, record in enumerate(records, 1):
        attrs = dict(record.get("attributes") or {})
        parent = _code(attrs.get("ID_ajutine"))
        if not parent:
            identity = record.get("id")
            seed = f"qeoloog-etl:{identity}" if identity else f"qeoloog-etl:row:{ordinal}"
            try:
                parent = f"Q_{UUID(str(identity)).hex}"
            except ValueError:
                parent = f"Q_{uuid5(NAMESPACE_URL, seed).hex}"
            collision = 0
            while _key(parent) in parents:
                collision += 1
                parent = f"Q_{uuid5(NAMESPACE_URL, f'{seed}:{collision}').hex}"
            attrs["ID_ajutine"] = parent
            parents.add(_key(parent))
        units = [dict(unit) for unit in record.get("units") or ()]
        related = {sheet: [dict(row) for row in rows]
                   for sheet, rows in (record.get("related") or {}).items()}
        for prefix, rows in (("K", units), ("N", related.get(ETL_PHENOMENON_SHEET, ()))):
            number = 0
            for row in rows:
                if not _blank(row.get("ID_ajutine")):
                    continue
                while True:
                    number += 1
                    candidate = f"{parent}_{prefix}{number:04d}"
                    if _key(candidate) not in details:
                        break
                row["ID_ajutine"] = candidate
                details.add(_key(candidate))
        yield {**record, "attributes": attrs, "units": units, "related": related}


def _validate_export_link(row, label, ordinal, explicit, temporary, issues):
    identifier = _key(row.get(_PARENT_REF_FIELD))
    if identifier:
        expected = explicit.get(identifier) == {ordinal}
    else:
        expected = _prefix_match(_key(row.get("ID_ajutine")), temporary) == ordinal
    if not expected:
        issues.append(f"{label}: ETL6/ETL10 paaris uuesti importimisel ei saa "
                      "vanemobjekti standardväljade järgi üheselt tuvastada.")


def _lab_export_ids(records):
    """Fill portable draft IDs where object ownership is already explicit."""
    ids = {sheet: {lab_key(row.get("ID_ajutine")) for record in records
                   for row in (record.get("related") or {}).get(sheet, ())}
           for sheet in (SERIES, SAMPLE, MEASUREMENT)}
    for record in records:
        parent = record["attributes"]["ID_ajutine"]
        for sheet, prefix in ((SERIES, "S"), (SAMPLE, "P"), (MEASUREMENT, "M")):
            number = 0
            for row in record["related"].get(sheet, ()):
                if not lab_key(row.get("ID_ajutine")):
                    while True:
                        number += 1
                        candidate = f"{parent}_{prefix}{number:04d}"
                        key = lab_key(candidate)
                        if key not in ids[sheet]:
                            break
                    row["ID_ajutine"] = candidate
                    ids[sheet].add(key)
                if sheet in (SAMPLE, MEASUREMENT) and not lab_key(row.get(_PARENT_REF_FIELD)):
                    # The destination object is known locally, not from a
                    # service GUID lookup. In the XLSX this is a draft ref.
                    row[_PARENT_REF_FIELD] = parent


def _lab_issues(records):
    issues = []
    for record in records:
        parent = _code((record.get("attributes") or {}).get("ID_ajutine"))
        for sheet, rows in (record.get("related") or {}).items():
            if sheet not in LAB_FIELDS:
                continue
            for i, row in enumerate(rows, 1):
                label = f"{sheet} {parent}:{i}"
                _row_issues(sheet, row, label, issues)
                if "z_suht_ylemine" in LAB_FIELDS[sheet]:
                    _interval_issues(row, label, None, issues)
                for key in LAB_REFERENCES.get(sheet, ()):
                    if key != "ID_ajutine" and (ref := lab_key(row.get(key))) and not is_guid(ref):
                        issues.append(f"{label}: {key} on kohalik ajutine viide, mitte välise andmebaasi GUID.")
                if sheet == RESULT:
                    low = _finite_number(row.get("alumine_maaramispiir"))
                    high = _finite_number(row.get("ylemine_maaramispiir"))
                    uncertainty = _finite_number(row.get("tulemi_kordustapsus"))
                    if low is not None and high is not None and low > high:
                        issues.append(f"{label}: alumine määramispiir ületab ülemist.")
                    if uncertainty is not None and uncertainty < 0:
                        issues.append(f"{label}: kordustäpsus ei tohi olla negatiivne.")
    # Names and provider-only extra fields are not present in exported schemas.
    exported = [{**record, "attributes": _export_fields(ETL6_SHEET, record["attributes"])}
                for record in records]
    issues.extend(check_lab_links(exported))
    return issues


def validate_etl_lab(records):
    """Check laboratory drafts separately from the ETL6/10 field checklist."""
    records = list(_export_ids(list(records)))
    _lab_export_ids(records)
    return _lab_issues(records)


def validate_etl(records, *, lab=False):
    """Return preflight findings as strings for callers of the original API."""
    from .etl_preflight import review_etl

    report = review_etl(records, lab=lab)
    return [str(issue) for issue in (*report.errors, *report.warnings)]


def _export_fields(sheet, row):
    return {field: _typed(field, row.get(field)) for field in _SCHEMAS[sheet]}


def export_etl(directory, records, *, lab=False):
    """Write a non-overwriting ETL6/10 pair, optionally with ETL7/8 drafts."""
    directory = Path(directory)
    records = list(_export_ids(list(records)))
    if not records:
        raise EtlWorkbookError("Eksporditavaid ETL-punkte ei ole.")
    groups = [("ETL6.xlsx", {ETL6_SHEET: ETL6_FIELDS}), ("ETL10.xlsx", ETL10_FIELDS)]
    if lab:
        _lab_export_ids(records)
        groups.extend((("ETL7.xlsx", ETL7_FIELDS), ("ETL8.xlsx", ETL8_FIELDS)))
    paths = tuple(directory / filename for filename, _ in groups)
    if not directory.is_dir() or any(os.path.lexists(path) for path in paths):
        raise EtlWorkbookError("Vali olemasolev kaust, kus valitud ETL-töövihikuid veel ei ole.")
    tables = {name: [] for name in _SCHEMAS}
    for record in records:
        tables[ETL6_SHEET].append(_export_fields(ETL6_SHEET, record.get("attributes") or {}))
        tables[ETL_UNIT_SHEET].extend(_export_fields(ETL_UNIT_SHEET, row) for row in record.get("units") or ())
        for sheet in (*ETL_CHILD_SHEETS, *(LAB_FIELDS if lab else ())):
            tables[sheet].extend(_export_fields(sheet, row) for row in (record.get("related") or {}).get(sheet) or ())
    try:
        with TemporaryDirectory(prefix=".qeoloog-etl-", dir=directory) as staging:
            temporary = tuple(Path(staging) / path.name for path in paths)
            for path, (_, schemas) in zip(temporary, groups):
                write_xlsx(path, {sheet: (fields, tables[sheet]) for sheet, fields in schemas.items()},
                           ETL_DATE_FIELDS)
            created = []
            try:
                for tmp, path in zip(temporary, paths):
                    # Hard-link publication is atomic and refuses existing files.
                    os.link(tmp, path)
                    created.append((tmp, path))
            except OSError:
                for tmp, path in created:
                    if path.exists() and os.path.samefile(tmp, path):
                        path.unlink()
                raise
    except (OSError, ValueError) as error:
        if isinstance(error, EtlWorkbookError):
            raise
        raise EtlWorkbookError(f"ETL töövihikuid ei saanud salvestada ({error}).") from error
    return paths
