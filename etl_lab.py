"""ETL7/ETL8 schemas and exact local laboratory relationships."""

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID


SERIES = "mall_seeria"
SAMPLE = "mall_proov"
MEMBERSHIP = "mall_seos"
MEASUREMENT = "mall_mootmine"
CITATION = "mall_viitamine"
RESULT = "mall_tulem"
OBJECT_REF = "puurauk_vaatluspunkt_id"

ETL7_FIELDS = {
    SERIES: tuple("ID_ajutine nimi protokolli_nr markus lisaja lisamise_aeg".split()),
    SAMPLE: tuple("""
ID_ajutine proov_tyyp proov_tahis_alg z_suht_ylemine z_suht_alumine eesmark yksus_kood
aeg kogus yhik proov_meetod lito kivim_nimetus lito_vabatekst ettevalmistus_meetod
stratigraafia staatus markus puurauk_vaatluspunkt_id isik_nimi lisaja lisamise_aeg
""".split()),
    MEMBERSHIP: tuple("ID_ajutine markus algne_id lisaja lisamise_aeg".split()),
}
ETL8_FIELDS = {
    MEASUREMENT: tuple("""
ID_ajutine analyys_kood labor_analyys_nr kuupaev labor_eeltootlus analyys_meetod
meetod_markus labor seade markus z_suht_ylemine z_suht_alumine puurauk_vaatluspunkt_id
proov_id lisaja lisamise_aeg
""".split()),
    CITATION: tuple("ID_ajutine egf_nr kirjandus_viit markus lisaja lisamise_aeg".split()),
    RESULT: tuple("""
ID_ajutine tulem tulemi_kordustapsus analyys_naitaja z_suht_ylemine z_suht_alumine
alumine_maaramispiir ylemine_maaramispiir erimark yhik analyys_tulem_tyyp markus lisaja lisamise_aeg
""".split()),
}
LAB_FIELDS = {**ETL7_FIELDS, **ETL8_FIELDS}
# The sheets without a foreign-key column carry the parent temporary ID in
# ID_ajutine for Qeoloog drafts. This is not an assertion about an EGT loader.
LAB_REFERENCES = {
    SAMPLE: {OBJECT_REF: None},
    MEMBERSHIP: {"ID_ajutine": SERIES, "algne_id": SAMPLE},
    MEASUREMENT: {OBJECT_REF: None, "proov_id": SAMPLE},
    CITATION: {"ID_ajutine": MEASUREMENT},
    RESULT: {"ID_ajutine": MEASUREMENT},
}
LAB_REQUIRED = {
    SERIES: "ID_ajutine nimi lisaja lisamise_aeg",
    SAMPLE: ("ID_ajutine proov_tyyp eesmark yksus_kood yhik proov_meetod lito "
             "kivim_nimetus ettevalmistus_meetod stratigraafia staatus "
             "puurauk_vaatluspunkt_id isik_nimi lisaja lisamise_aeg"),
    MEMBERSHIP: "ID_ajutine algne_id lisaja lisamise_aeg",
    MEASUREMENT: ("ID_ajutine labor_eeltootlus analyys_meetod labor seade "
                  "puurauk_vaatluspunkt_id proov_id lisaja lisamise_aeg"),
    CITATION: "ID_ajutine lisaja lisamise_aeg",
    RESULT: "ID_ajutine tulem analyys_naitaja erimark yhik analyys_tulem_tyyp lisaja lisamise_aeg",
}
LAB_REQUIRED = {sheet: frozenset(fields.split()) for sheet, fields in LAB_REQUIRED.items()}
LAB_INT_FIELDS = frozenset({"egf_nr", "kirjandus_viit"})
LAB_NUMBER_FIELDS = frozenset({"kogus", "tulem", "tulemi_kordustapsus",
                              "alumine_maaramispiir", "ylemine_maaramispiir"})
LAB_DATE_FIELDS = frozenset({"aeg", "kuupaev"})
LAB_TEXT_FIELDS = frozenset({"protokolli_nr", "proov_tahis_alg", "analyys_kood",
                             "labor_analyys_nr", "proov_id", "algne_id"})


def lab_key(value):
    """Match literal identifiers only; normalize unambiguous GUID spellings."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    try:
        return str(UUID(text))
    except ValueError:
        return text.casefold()


def _object_ids(record):
    attributes = record.get("attributes") or {}
    values = [attributes.get(key) for key in ("ID_ajutine", "globalid", "esri_globalid")]
    # A explicitly supplied local UUID can serve as a portable reference.
    if record.get("id"):
        values.append(record["id"])
    source = record.get("source_ref") or {}
    if str(source.get("source", "")).upper() == "EGT":
        # Never treat a provider's numeric ID like a database object GUID.
        original = record.get("source_original") or {}
        raw_attributes = original.get("raw_attributes") or {}
        captured = (source.get("id"), raw_attributes.get("globalid"), raw_attributes.get("esri_globalid"))
        for identifier in captured:
            if is_guid(identifier):
                values.append(identifier)
    return {lab_key(value) for value in values} - {""}


def _row_ids(row):
    return {lab_key(row.get(key)) for key in ("ID_ajutine", "globalid", "esri_globalid")} - {""}


def _fingerprint(sheet, row):
    return tuple(str(row.get(field) if row.get(field) is not None else "") for field in LAB_FIELDS[sheet])


@dataclass(eq=False)
class _LabRow:
    values: dict
    source: dict
    owner: int | None = None


def _unique(index, identifier):
    if identifier:
        values = index.get(identifier, ())
        if len(values) == 1:
            return next(iter(values))
    return None


def _producer_index(entries):
    index = defaultdict(set)
    for entry in entries:
        for key in _row_ids(entry.values):
            index[key].add(entry)
    return index


def link_lab_tables(tables, records, warnings, unlinked):
    """Append only well-resolved input children; return changed object indexes.

    All potential duplicate producer identifiers remain visible to the join,
    including invalid or unresolved producers. A valid same-named record
    must not absorb dependent rows from another ambiguous producer.
    """
    incoming = {
        sheet: [_LabRow(dict(row), source) for row, source in tables.get(sheet, ())]
        for sheet in LAB_FIELDS
    }
    if not any(incoming.values()):
        return set()
    existing = {
        sheet: [_LabRow(row, {}, i) for i, record in enumerate(records)
                for row in (record.get("related") or {}).get(sheet, ())]
        for sheet in LAB_FIELDS
    }
    prior_fingerprints = defaultdict(set)
    for sheet, entries in existing.items():
        for entry in entries:
            prior_fingerprints[(sheet, entry.owner)].add(_fingerprint(sheet, entry.values))
    objects = defaultdict(set)
    for i, record in enumerate(records):
        for key in _object_ids(record):
            objects[key].add(i)
    indexes = {sheet: _producer_index(existing[sheet] + incoming[sheet])
               for sheet in (SAMPLE, SERIES, MEASUREMENT)}
    for sheet, index in indexes.items():
        ambiguous = {key for row in incoming[sheet] for key in _row_ids(row.values)
                     if len(index.get(key, ())) > 1}
        if ambiguous:
            examples = ", ".join(sorted(ambiguous)[:4])
            warnings.append(f"{sheet}: korduvad seose ID-d ({examples}). Olemasolevaid ridu ei "
                            "kirjutatud üle ning nende ID-dega seotud uusi ridu ei seostatud.")
    changed = set()
    skipped = defaultdict(int)
    local_ids = False

    def eligible(sheet, entry):
        ids = _row_ids(entry.values)
        return bool(lab_key(entry.values.get("ID_ajutine")) and ids
                    and all(_unique(indexes[sheet], key) is entry for key in ids))

    def accept(sheet, entry, owner):
        if owner is None:
            unlinked[sheet].append(entry.values)
            return False
        if _fingerprint(sheet, entry.values) in prior_fingerprints[(sheet, owner)]:
            skipped[sheet] += 1
            return False
        entry.owner = owner
        records[owner].setdefault("related", {}).setdefault(sheet, []).append(entry.values)
        changed.add(owner)
        return True

    for entry in incoming[SAMPLE]:
        key = lab_key(entry.values.get(OBJECT_REF))
        owner = _unique(objects, key) if eligible(SAMPLE, entry) else None
        if accept(SAMPLE, entry, owner):
            local_ids |= not is_guid(key)

    memberships = {}
    possible_series_owners = defaultdict(set)
    for entry in incoming[MEMBERSHIP]:
        series = _unique(indexes[SERIES], lab_key(entry.values.get("ID_ajutine")))
        sample = _unique(indexes[SAMPLE], lab_key(entry.values.get("algne_id")))
        memberships[entry] = (series, sample)
        if series is not None and sample is not None and sample.owner is not None:
            possible_series_owners[series].add(sample.owner)
    for entry in incoming[SERIES]:
        owners = possible_series_owners.get(entry, set())
        owner = next(iter(owners)) if len(owners) == 1 and eligible(SERIES, entry) else None
        accept(SERIES, entry, owner)
    for entry, (series, sample) in memberships.items():
        owner = (sample.owner if series and sample and sample.owner is not None
                 and series.owner == sample.owner else None)
        if accept(MEMBERSHIP, entry, owner):
            local_ids = True

    for entry in incoming[MEASUREMENT]:
        sample_key = lab_key(entry.values.get("proov_id"))
        object_key = lab_key(entry.values.get(OBJECT_REF))
        sample = _unique(indexes[SAMPLE], sample_key)
        owner = sample.owner if sample is not None and eligible(MEASUREMENT, entry) else None
        if object_key and (owner is None or _unique(objects, object_key) != owner):
            owner = None
        if accept(MEASUREMENT, entry, owner):
            local_ids |= not is_guid(sample_key) or bool(object_key and not is_guid(object_key))
            if not object_key:
                source = entry.source
                warnings.append(f"{source.get('file', MEASUREMENT)}/{MEASUREMENT}:{source.get('row', '?')}: "
                                "objekti viide puudus; omanik tuvastati täpse prooviviite kaudu.")
    for sheet in (CITATION, RESULT):
        for entry in incoming[sheet]:
            parent = _unique(indexes[MEASUREMENT], lab_key(entry.values.get("ID_ajutine")))
            if accept(sheet, entry, parent.owner if parent else None):
                local_ids = True
    if local_ids:
        warnings.append("ETL7/8: kasutati Qeoloogi kohalikke täpseid ID-seoseid. "
                        "Ajutised viited ei asenda välise andmebaasi GUID-e.")
    for sheet, count in skipped.items():
        warnings.append(f"{sheet}: {count} olemasolevat samasisulist rida jäeti muutmata.")
    return changed


def is_guid(value):
    if value:
        try:
            UUID(str(value))
            return True
        except ValueError:
            pass
    return False


def check_lab_links(records):
    """Check export joins by reusing the exact same logic as the importer."""
    targets = [{"attributes": dict(record.get("attributes") or {}), "related": {}} for record in records]
    tables = defaultdict(list)
    for i, record in enumerate(records):
        for sheet in LAB_FIELDS:
            for row_index, row in enumerate((record.get("related") or {}).get(sheet, ()), 1):
                tables[sheet].append(({field: row.get(field) for field in LAB_FIELDS[sheet]},
                                      {"row": row_index, "expected_owner": i}))
    warnings, unlinked = [], defaultdict(list)
    link_lab_tables(tables, targets, warnings, unlinked)
    # Compare multisets by object, allowing multiple results per measurement
    # and preserving repeated, identical published result rows.
    report = [f"{sheet}: {len(rows)} rida ei seostu töövihikute uuesti avamisel."
              for sheet, rows in unlinked.items() if rows]
    for i, (before, after) in enumerate(zip(records, targets), 1):
        for sheet in LAB_FIELDS:
            expected = [_fingerprint(sheet, row) for row in (before.get("related") or {}).get(sheet, ())]
            actual = [_fingerprint(sheet, row) for row in after["related"].get(sheet, ())]
            if sorted(expected) != sorted(actual):
                report.append(f"ETL6 rida {i + 1}/{sheet}: uuesti avamisel muutuks objektiga seotud ridade hulk või koosseis.")
    return report
