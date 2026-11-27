"""Typed, provenance-preserving local objects in the section workspace."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from math import isfinite
import sqlite3
from uuid import UUID, uuid4

from .section_workspace import SectionWorkspaceError


class LocalObjectConflict(SectionWorkspaceError):
    """A batch would replace an existing local record or duplicate an identity."""


SOURCES = frozenset({"EGT", "SARV", "VEKA"})
_SCHEMA = """
CREATE TABLE IF NOT EXISTS qeoloog_local_objects (
    fid INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    source TEXT,
    source_entity TEXT,
    source_id TEXT,
    import_key TEXT UNIQUE,
    x_3301 REAL,
    y_3301 REAL,
    elevation REAL,
    updated_at DATETIME NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE (source, source_entity, source_id)
)
"""
_MISSING = (None, "", "<NULL>", "NULL")


def _text(value):
    return "" if value in _MISSING else str(value).strip()


def _float(value, key):
    if _text(value):
        try:
            result = float(str(value).strip().replace(",", "."))
            if isfinite(result):
                return result
        except (TypeError, ValueError):
            pass
        raise SectionWorkspaceError(f"{key}: invalid numeric value.")
    return None


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _id(value):
    try:
        return UUID(str(value)).hex
    except (TypeError, ValueError, AttributeError) as error:
        raise SectionWorkspaceError("Invalid local object ID.") from error


def normalize_source_ref(value):
    """Return a supported provider/entity/ID, without matching display names."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SectionWorkspaceError("Invalid source reference.")
    source = _text(value.get("source")).upper()
    entity = _text(value.get("entity")).casefold()
    identifier = _text(value.get("id"))
    if source not in SOURCES or not entity or not identifier:
        raise SectionWorkspaceError("Source reference requires EGT, SARV or VEKA, an entity, and an ID.")
    # GUID spellings can differ in case, braces and hyphens between layers.
    try:
        identifier = UUID(identifier).hex
    except ValueError:
        pass
    return {"source": source, "entity": entity, "id": identifier}


def local_object_name(record):
    attributes = record.get("attributes", {})
    return _text(attributes.get("nimi")) or _text(attributes.get("alias")) or record.get("id", "")


def calculate_unit_geometry(record, *, absolute=False):
    """Return a draft with derived values; never mutate the observation snapshot.

    Absolute values are opt-in: their derivation requires relative Z intervals
    (depth positive down, not measured distance in a deviated hole), and a
    known vertical reference. Calculated numbers are rounded to millimetres.
    """
    result = deepcopy(record)
    attrs = result.get("attributes") or {}
    if absolute and not _text(attrs.get("vertical_datum")):
        raise SectionWorkspaceError("Set the vertical datum before calculating absolute elevations.")
    z = _float(attrs.get("geom_z"), "geom_z") if absolute else None
    if absolute and z is None:
        raise SectionWorkspaceError("Set the object's absolute elevation before calculating unit elevations.")
    related = result.get("related") or {}
    for rows in (result.get("units", []), related.get("nahtus_mall", [])):
        for row in rows:
            top = _float(row.get("z_suht_ylemine"), "z_suht_ylemine")
            bottom = _float(row.get("z_suht_alumine"), "z_suht_alumine")
            if top is not None and bottom is not None:
                if bottom < top:
                    raise SectionWorkspaceError("The lower depth must not be above the upper depth.")
                row["paksus"] = round(bottom - top, 3)
            if absolute:
                for depth, key in ((top, "z_abs_ylemine"), (bottom, "z_abs_alumine")):
                    if depth is not None:
                        row[key] = round(z - depth, 3)
    return result


def _record(value):
    if not isinstance(value, dict):
        raise SectionWorkspaceError("Invalid local object record.")
    record = deepcopy(value)
    identifier = record.get("id")
    record["id"] = _id(identifier) if identifier else uuid4().hex
    if not isinstance(record.get("attributes"), dict):
        raise SectionWorkspaceError("Local object attributes must be a dictionary.")
    if not local_object_name(record) or local_object_name(record) == record["id"]:
        raise SectionWorkspaceError("Enter a name or alias for the local object.")
    units = record.setdefault("units", [])
    related = record.setdefault("related", {})
    if not isinstance(related, dict) or not all(isinstance(key, str) for key in related):
        raise SectionWorkspaceError("Invalid local object child tables.")
    for rows in [units, *related.values()]:
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise SectionWorkspaceError("Each local object child table must contain a list of rows.")
    provenance = record.setdefault("provenance", {})
    if not isinstance(provenance, dict):
        raise SectionWorkspaceError("Invalid local object provenance.")
    reference = normalize_source_ref(record.get("source_ref"))
    if reference is not None:
        record["source_ref"] = reference
        record.setdefault("captured_at", _timestamp())
        record.setdefault("source_original", deepcopy({
            key: record[key] for key in ("attributes", "units", "related")
        }))
    else:
        record.pop("source_ref", None)
    if "source_original" in record and not isinstance(record["source_original"], dict):
        raise SectionWorkspaceError("Invalid original source snapshot.")
    return record


def _decode(row):
    try:
        value = json.loads(row[0])
    except (TypeError, ValueError) as error:
        raise SectionWorkspaceError("A local object record is unreadable.") from error
    if not isinstance(value, dict) or not value.get("id") or not isinstance(value.get("attributes"), dict):
        raise SectionWorkspaceError("A local object record has invalid data.")
    return value


def _data_exists(database):
    return bool(database.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'qeoloog_local_objects'"
    ).fetchone())


def _get(database, identifier):
    return database.execute(
        "SELECT payload_json FROM qeoloog_local_objects WHERE id = ?", (identifier,)
    ).fetchone()


def _source_tuple(record):
    ref = record.get("source_ref")
    return (ref["source"], ref["entity"], ref["id"]) if ref else (None, None, None)


def _lookup_source(database, ref):
    return database.execute(
        "SELECT payload_json FROM qeoloog_local_objects "
        "WHERE source = ? AND source_entity = ? AND source_id = ?",
        (ref["source"], ref["entity"], ref["id"]),
    ).fetchone()


class LocalObjectStore:
    """Local records share the portable section workspace and its backups."""

    def __init__(self, workspace):
        if workspace is None:
            raise SectionWorkspaceError("Open a Qeoloog workspace first.")
        self.workspace = workspace

    def list_objects(self):
        try:
            with self.workspace.connection() as database:
                if not _data_exists(database):
                    return []
                return [_decode(row) for row in database.execute(
                    "SELECT payload_json FROM qeoloog_local_objects ORDER BY name COLLATE NOCASE, id"
                )]
        except (OSError, sqlite3.Error) as error:
            raise SectionWorkspaceError(f"Cannot list local objects: {error}") from error

    def load(self, identifier):
        try:
            with self.workspace.connection() as database:
                row = _get(database, _id(identifier)) if _data_exists(database) else None
        except (OSError, sqlite3.Error) as error:
            raise SectionWorkspaceError(f"Cannot read local object: {error}") from error
        if row is None:
            raise SectionWorkspaceError(f"Local object not found: {identifier}")
        return _decode(row)

    def find_source(self, source_ref):
        ref = normalize_source_ref(source_ref)
        if ref is None:
            return None
        try:
            with self.workspace.connection() as database:
                row = _lookup_source(database, ref) if _data_exists(database) else None
            return _decode(row) if row else None
        except (OSError, sqlite3.Error) as error:
            raise SectionWorkspaceError(f"Cannot look up local source reference: {error}") from error

    def save(self, record):
        """Save a new record or explicitly update a matching local ID."""
        return self._save_batch([record], update=True)[0]

    def save_if_unchanged(self, record, baseline):
        """Update an existing record without overwriting a change made while editing."""
        if not isinstance(baseline, dict) or not baseline.get("id") or baseline["id"] != record.get("id"):
            raise LocalObjectConflict("Local object draft does not match its original record.")
        return self._save_batch([record], update=True, baseline=baseline)[0]

    def save_many(self, records):
        """Import atomically. Existing IDs, original sources and import keys collide."""
        return self._save_batch(records, update=False)

    def commit_etl(self, records, updates, expected):
        """Apply staged lab additions only if the preview's existing records still match."""
        return self._save_batch(records, update=False, updates=updates, expected=expected)

    def _save_batch(self, records, *, update, updates=(), expected=None, baseline=None):
        prepared = [_record(record) for record in records]
        additions = [_record(record) for record in updates]
        if not (prepared or additions):
            return []
        if additions and (
            not expected or len({record['id'] for record in additions}) != len(additions)
        ):
            raise LocalObjectConflict('Invalid import preview; prepare the import again.')
        try:
            with self.workspace.connection(write=True) as database:
                database.execute(_SCHEMA)
                database.execute(
                    "INSERT OR IGNORE INTO gpkg_contents (table_name, data_type, identifier, description) "
                    "VALUES ('qeoloog_local_objects', 'attributes', 'Qeoloog – local objects', "
                    "'Local records, with EPSG:3301 X/Y coordinates when known.')"
                )
                for record in prepared:
                    if baseline is not None:
                        existing = _get(database, record["id"])
                        if existing is None or _decode(existing) != baseline:
                            raise LocalObjectConflict("The local object changed while editing.")
                    self._write(database, record, update=update)
                for record in additions:
                    identifier = record['id']
                    existing = _get(database, identifier)
                    previous = _decode(existing) if existing is not None else None
                    if previous is None or previous != expected.get(identifier):
                        raise LocalObjectConflict('A local object changed after preview; prepare the import again.')
                    self._check_lab_append(previous, record)
                    self._write(database, record, update=True)
                database.execute(
                    "UPDATE gpkg_contents SET last_change = ? WHERE table_name = 'qeoloog_local_objects'",
                    (_timestamp(),),
                )
            return prepared + additions
        except sqlite3.IntegrityError as error:
            raise LocalObjectConflict("Duplicate local object, source reference or import key; the batch was not saved.") from error
        except (OSError, sqlite3.Error, ValueError, TypeError) as error:
            raise SectionWorkspaceError(f"Cannot save local objects: {error}") from error

    @staticmethod
    def _check_lab_append(previous, revised):
        from .etl_lab import LAB_FIELDS

        if any(revised.get(k) != previous.get(k) for k in ('attributes', 'units', 'source_ref', 'source_original')):
            raise LocalObjectConflict('ETL7/8 cannot change existing object details or original data.')
        before, after = previous.get('related') or {}, revised.get('related') or {}
        for sheet in before.keys() | after.keys():
            old, new = before.get(sheet, []), after.get(sheet, [])
            if (sheet in LAB_FIELDS and new[:len(old)] != old) or (sheet not in LAB_FIELDS and new != old):
                raise LocalObjectConflict('ETL7/8 cannot replace existing rows.')

    @staticmethod
    def _write(database, record, *, update):
        existing = _get(database, record["id"])
        if existing:
            if not update:
                raise LocalObjectConflict(f"Local object already exists: {local_object_name(record)}")
            previous = _decode(existing)
            if previous.get("source_ref") and previous["source_ref"] != record.get("source_ref"):
                raise LocalObjectConflict("Cannot replace the source reference of an existing local object.")
            for key in ("source_original", "captured_at"):
                if key in previous:
                    record[key] = previous[key]
            # An editor change to what is being interpreted cannot invalidate
            # the stable workbook-reimport identity assigned at first import.
            previous_import = previous.get("provenance", {}).get("import_key")
            if previous_import:
                record["provenance"]["import_key"] = previous_import
        attrs = record["attributes"]
        x, y = (_float(attrs.get(key), key) for key in ("geom_x", "geom_y"))
        z = _float(attrs.get("geom_z"), "geom_z")
        if (x is None) != (y is None):
            raise SectionWorkspaceError("Enter both coordinates or leave both blank.")
        import_key = _text(record["provenance"].get("import_key")) or None
        database.execute(
            "INSERT INTO qeoloog_local_objects (id,name,source,source_entity,source_id,import_key,"
            "x_3301,y_3301,elevation,updated_at,payload_json) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, source=excluded.source, "
            "source_entity=excluded.source_entity, source_id=excluded.source_id, "
            "import_key=excluded.import_key, x_3301=excluded.x_3301, y_3301=excluded.y_3301, "
            "elevation=excluded.elevation, updated_at=excluded.updated_at, payload_json=excluded.payload_json",
            (record["id"], local_object_name(record), *_source_tuple(record), import_key, x, y, z,
             _timestamp(), json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))),
        )
