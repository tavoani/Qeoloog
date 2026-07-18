"""Local GeoPackage workspace, laboratory import and exchange converters."""

from __future__ import annotations

from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import uuid
import zipfile

from qgis.PyQt.QtCore import QBuffer, QIODevice, QXmlStreamReader


SCHEMA_VERSION = 1
def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value):
    return "" if value is None else str(value).strip()


def _number(value):
    text = _text(value).replace("\u00a0", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    return float(text)


def _uuid():
    return str(uuid.uuid4())


def _safe_name(value):
    return re.sub(r"[^a-z0-9]+", "_", _text(value).casefold()).strip("_")


def _xml_rows(data):
    """Read XML with Qt's streaming parser (no external XML entity expansion)."""
    def string(value):
        return value.toString() if hasattr(value, "toString") else str(value)

    device = QBuffer()
    device.setData(data)
    device.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QXmlStreamReader(device)
    stack = []
    events = []
    while not reader.atEnd():
        token = reader.readNext()
        if token == QXmlStreamReader.TokenType.StartElement:
            name = string(reader.name())
            stack.append(name)
            events.append(("start", name, {
                string(attribute.name()): string(attribute.value())
                for attribute in reader.attributes()
            }))
        elif token in (
            QXmlStreamReader.TokenType.Characters,
            QXmlStreamReader.TokenType.EntityReference,
        ):
            if stack and not reader.isWhitespace():
                events.append(("text", stack[-1], string(reader.text())))
        elif token == QXmlStreamReader.TokenType.EndElement:
            name = string(reader.name())
            events.append(("end", name, None))
            if stack:
                stack.pop()
    error = reader.errorString() if reader.hasError() else ""
    device.close()
    if error:
        raise ValueError(error)
    return events


def _xlsx_shared_strings(archive):
    try:
        data = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    strings = []
    current = None
    for event, name, value in _xml_rows(data):
        if event == "start" and name == "si":
            current = []
        elif event == "text" and name == "t" and current is not None:
            current.append(value)
        elif event == "end" and name == "si" and current is not None:
            strings.append("".join(current))
            current = None
    return strings


def _column_index(reference):
    letters = re.match(r"[A-Za-z]+", reference or "")
    result = 0
    for char in (letters.group(0).upper() if letters else ""):
        result = result * 26 + ord(char) - 64
    return max(0, result - 1)


def read_xlsx(path):
    """Read the first XLSX worksheet without optional third-party packages."""
    with zipfile.ZipFile(path) as archive:
        shared = _xlsx_shared_strings(archive)
        sheet_names = sorted(
            name for name in archive.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        )
        if not sheet_names:
            raise ValueError("XLSX does not contain a worksheet.")
        events = _xml_rows(archive.read(sheet_names[0]))

    rows = []
    row = None
    cell = None
    cell_type = ""
    value_parts = []
    inline_parts = []
    for event, name, value in events:
        if event == "start" and name == "row":
            row = {}
        elif event == "start" and name == "c":
            cell = value.get("r", "")
            cell_type = value.get("t", "")
            value_parts = []
            inline_parts = []
        elif event == "text" and name == "v" and cell is not None:
            value_parts.append(value)
        elif event == "text" and name == "t" and cell is not None:
            inline_parts.append(value)
        elif event == "end" and name == "c" and row is not None and cell is not None:
            raw = "".join(inline_parts if cell_type == "inlineStr" else value_parts)
            if cell_type == "s" and raw:
                try:
                    raw = shared[int(raw)]
                except (IndexError, ValueError):
                    pass
            elif cell_type == "b":
                raw = "true" if raw == "1" else "false"
            row[_column_index(cell)] = raw
            cell = None
        elif event == "end" and name == "row" and row is not None:
            width = max(row.keys(), default=-1) + 1
            rows.append([row.get(index, "") for index in range(width)])
            row = None

    if not rows:
        return [], []
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    headers = [
        _text(value) or f"column_{index + 1}"
        for index, value in enumerate(padded[0])
    ]
    return headers, [
        dict(zip(headers, values))
        for values in padded[1:]
        if any(_text(value) for value in values)
    ]


def read_csv(path):
    raw = Path(path).read_bytes()
    text = None
    for encoding in ("utf-8-sig", "utf-8", "cp1257", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Could not decode CSV file.")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
    rows = [
        {str(key or "").strip(): value for key, value in row.items()}
        for row in reader
        if any(_text(value) for value in row.values())
    ]
    return headers, rows


def read_tabular(path):
    suffix = Path(path).suffix.casefold()
    if suffix == ".xlsx":
        return read_xlsx(path)
    if suffix in {".csv", ".txt", ".tsv"}:
        return read_csv(path)
    raise ValueError("Supported formats are CSV, TSV and XLSX.")


FIELD_DEFINITIONS = (
    ("sample_number", "Sample number", True),
    ("parameter", "Parameter", True),
    ("value", "Result value", True),
    ("analysis_code", "Analysis code", False),
    ("specimen_number", "Specimen number", False),
    ("sample_type", "Sample type", False),
    ("purpose", "Sample purpose", False),
    ("status", "Sample status", False),
    ("depth_from", "Depth from", False),
    ("depth_to", "Depth to", False),
    ("unit", "Unit", False),
    ("method", "Analysis method", False),
    ("lab", "Laboratory", False),
    ("lab_number", "Laboratory number", False),
    ("date", "Analysis date", False),
    ("qualifier", "Qualifier", False),
    ("detection_limit", "Detection limit", False),
    ("uncertainty", "Uncertainty", False),
    ("remarks", "Remarks", False),
)


HEADER_ALIASES = {
    "sample_number": ("sample", "sample_no", "sample_number", "proov", "proovi_nr", "proov_nr", "proov_tahis"),
    "parameter": ("parameter", "analyte", "element", "näitaja", "naitaja", "analüüt", "analyyt"),
    "value": ("value", "result", "tulemus", "sisaldus"),
    "analysis_code": ("analysis", "analysis_code", "batch", "analüüs", "analyys", "analyys_kood"),
    "specimen_number": ("specimen", "specimen_number", "eksemplar", "pala"),
    "sample_type": ("sample_type", "proovi_tüüp", "proovi_tyyp"),
    "purpose": ("purpose", "eesmärk", "eesmark"),
    "status": ("status", "staatus"),
    "depth_from": ("depth_from", "depth", "sügavus", "sygavus", "from", "top", "algus", "ülemine", "ylemine", "sügavus_alates"),
    "depth_to": ("depth_to", "to", "bottom", "lõpp", "lopp", "alumine", "sügavus_kuni"),
    "unit": ("unit", "ühik", "yhik"),
    "method": ("method", "meetod", "analysis_method"),
    "lab": ("lab", "labor", "laboratory"),
    "lab_number": ("lab_number", "labori_nr", "laboratory_number"),
    "date": ("date", "kuupäev", "kuupaev"),
    "qualifier": ("qualifier", "tunnus", "tingimus"),
    "detection_limit": ("detection_limit", "lod", "loq", "määramispiir", "maaramispiir"),
    "uncertainty": ("uncertainty", "error", "viga", "määramatus", "maaramatus"),
    "remarks": ("remarks", "comment", "notes", "märkus", "markus"),
}


def suggested_mapping(headers):
    normalized = {_safe_name(header): header for header in headers}
    mapping = {}
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if _safe_name(alias) in normalized:
                mapping[field] = normalized[_safe_name(alias)]
                break
    return mapping


class PersonalStore:
    """Read and write Qeoloog personal data inside a GeoPackage."""

    ATTRIBUTE_TABLES = (
        "qeoloog_metadata",
        "qeoloog_datasets",
        "qeoloog_object_links",
        "qeoloog_samples",
        "qeoloog_specimens",
        "qeoloog_analyses",
        "qeoloog_analysis_results",
        "qeoloog_attachments",
        "qeoloog_import_batches",
    )

    def __init__(self, path=None):
        self.path = Path(path).expanduser().resolve() if path else None

    @property
    def is_open(self):
        return bool(self.path and self.path.exists())

    def create(self, path, name="My Qeoloog data"):
        candidate = Path(path).expanduser().resolve()
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if candidate.exists():
            raise FileExistsError(str(candidate))
        connection = sqlite3.connect(str(candidate))
        try:
            self._initialize(connection, name)
        except Exception:
            connection.close()
            candidate.unlink(missing_ok=True)
            raise
        connection.close()
        self.path = candidate
        return self.path

    def open(self, path):
        candidate = Path(path).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(str(candidate))
        connection = sqlite3.connect(str(candidate))
        try:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            missing = set(self.ATTRIBUTE_TABLES) - tables
            if missing:
                raise ValueError(
                    "Not a Qeoloog personal GeoPackage; missing: "
                    + ", ".join(sorted(missing))
                )
            version_row = connection.execute(
                "SELECT value FROM qeoloog_metadata WHERE key='schema_version'"
            ).fetchone()
            if not version_row or int(version_row[0]) > SCHEMA_VERSION:
                raise ValueError(
                    "The Qeoloog personal GeoPackage schema is missing or newer "
                    "than this plugin supports."
                )
        finally:
            connection.close()
        self.path = candidate
        return candidate

    def _connect(self):
        if not self.is_open:
            raise RuntimeError("Personal GeoPackage is not open.")
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _initialize(connection, dataset_name):
        now = _now()
        connection.executescript(
            """
            PRAGMA application_id = 1196444487;
            PRAGMA user_version = 10400;
            PRAGMA foreign_keys = ON;

            CREATE TABLE gpkg_spatial_ref_sys (
              srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY,
              organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
              definition TEXT NOT NULL, description TEXT
            );
            CREATE TABLE gpkg_contents (
              table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,
              identifier TEXT UNIQUE, description TEXT DEFAULT '',
              last_change DATETIME NOT NULL,
              min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
              srs_id INTEGER,
              CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id)
                REFERENCES gpkg_spatial_ref_sys(srs_id)
            );
            CREATE TABLE gpkg_geometry_columns (
              table_name TEXT NOT NULL, column_name TEXT NOT NULL,
              geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL,
              z TINYINT NOT NULL, m TINYINT NOT NULL,
              CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
              CONSTRAINT uk_gc_table_name UNIQUE (table_name),
              CONSTRAINT fk_gc_tn FOREIGN KEY (table_name)
                REFERENCES gpkg_contents(table_name),
              CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id)
                REFERENCES gpkg_spatial_ref_sys(srs_id)
            );
            CREATE TABLE gpkg_extensions (
              table_name TEXT, column_name TEXT, extension_name TEXT NOT NULL,
              definition TEXT NOT NULL, scope TEXT NOT NULL,
              UNIQUE (table_name, column_name, extension_name)
            );

            CREATE TABLE qeoloog_metadata (
              fid INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL UNIQUE,
              value TEXT NOT NULL
            );
            CREATE TABLE qeoloog_datasets (
              fid INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL, owner TEXT,
              description TEXT, licence TEXT, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE qeoloog_object_links (
              fid INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
              dataset_id TEXT NOT NULL,
              source_system TEXT NOT NULL, source_type TEXT NOT NULL,
              source_id TEXT NOT NULL, gea_id TEXT, sarv_id TEXT, name TEXT,
              notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              FOREIGN KEY (dataset_id) REFERENCES qeoloog_datasets(id) ON DELETE CASCADE
            );
            CREATE UNIQUE INDEX qeoloog_object_link_unique
              ON qeoloog_object_links(dataset_id, source_system, source_type, source_id);
            CREATE INDEX qeoloog_object_link_gea ON qeoloog_object_links(gea_id);
            CREATE INDEX qeoloog_object_link_sarv ON qeoloog_object_links(sarv_id);

            CREATE TABLE qeoloog_samples (
              fid INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
              dataset_id TEXT NOT NULL, link_id TEXT,
              number TEXT NOT NULL, sample_type TEXT, purpose TEXT, status TEXT,
              depth_from REAL, depth_to REAL, collected_date TEXT, mass REAL,
              unit TEXT, method TEXT, lithology TEXT, rock TEXT, stratigraphy TEXT,
              collector TEXT, remarks TEXT, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY (dataset_id) REFERENCES qeoloog_datasets(id) ON DELETE CASCADE,
              FOREIGN KEY (link_id) REFERENCES qeoloog_object_links(id) ON DELETE SET NULL
            );
            CREATE INDEX qeoloog_sample_link ON qeoloog_samples(link_id);
            CREATE INDEX qeoloog_sample_number ON qeoloog_samples(number);

            CREATE TABLE qeoloog_specimens (
              fid INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
              dataset_id TEXT NOT NULL, link_id TEXT,
              sample_id TEXT, number TEXT NOT NULL, specimen_type TEXT,
              depth_from REAL, depth_to REAL, rock TEXT, stratigraphy TEXT,
              storage TEXT, remarks TEXT, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY (dataset_id) REFERENCES qeoloog_datasets(id) ON DELETE CASCADE,
              FOREIGN KEY (link_id) REFERENCES qeoloog_object_links(id) ON DELETE SET NULL,
              FOREIGN KEY (sample_id) REFERENCES qeoloog_samples(id) ON DELETE SET NULL
            );
            CREATE INDEX qeoloog_specimen_link ON qeoloog_specimens(link_id);

            CREATE TABLE qeoloog_analyses (
              fid INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
              dataset_id TEXT NOT NULL, link_id TEXT,
              sample_id TEXT, specimen_id TEXT, code TEXT, lab_number TEXT,
              method TEXT, lab TEXT, instrument TEXT, analysis_date TEXT,
              remarks TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              FOREIGN KEY (dataset_id) REFERENCES qeoloog_datasets(id) ON DELETE CASCADE,
              FOREIGN KEY (link_id) REFERENCES qeoloog_object_links(id) ON DELETE SET NULL,
              FOREIGN KEY (sample_id) REFERENCES qeoloog_samples(id) ON DELETE SET NULL,
              FOREIGN KEY (specimen_id) REFERENCES qeoloog_specimens(id) ON DELETE SET NULL
            );
            CREATE INDEX qeoloog_analysis_link ON qeoloog_analyses(link_id);
            CREATE INDEX qeoloog_analysis_sample ON qeoloog_analyses(sample_id);

            CREATE TABLE qeoloog_analysis_results (
              fid INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
              analysis_id TEXT NOT NULL, parameter TEXT NOT NULL,
              value_num REAL, value_text TEXT, unit TEXT, qualifier TEXT,
              detection_limit REAL, uncertainty REAL, depth_from REAL,
              depth_to REAL, remarks TEXT, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY (analysis_id) REFERENCES qeoloog_analyses(id) ON DELETE CASCADE
            );
            CREATE INDEX qeoloog_result_analysis ON qeoloog_analysis_results(analysis_id);
            CREATE INDEX qeoloog_result_parameter ON qeoloog_analysis_results(parameter);

            CREATE TABLE qeoloog_attachments (
              fid INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
              entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
              relative_path TEXT, filename TEXT NOT NULL, mime_type TEXT,
              sha256 TEXT, caption TEXT, licence TEXT, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX qeoloog_attachment_entity
              ON qeoloog_attachments(entity_type, entity_id);

            CREATE TABLE qeoloog_import_batches (
              fid INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
              dataset_id TEXT NOT NULL, source_file TEXT NOT NULL,
              source_sha256 TEXT NOT NULL,
              imported_at TEXT NOT NULL, row_count INTEGER NOT NULL,
              mapping_json TEXT NOT NULL, warnings_json TEXT NOT NULL,
              FOREIGN KEY (dataset_id) REFERENCES qeoloog_datasets(id) ON DELETE CASCADE
            );
            """
        )
        connection.executemany(
            """INSERT INTO gpkg_spatial_ref_sys
               (srs_name, srs_id, organization, organization_coordsys_id,
                definition, description) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                ("Undefined Cartesian", -1, "NONE", -1, "undefined", "undefined Cartesian coordinate reference system"),
                ("Undefined geographic", 0, "NONE", 0, "undefined", "undefined geographic coordinate reference system"),
                ("WGS 84 geodetic", 4326, "EPSG", 4326, "GEOGCS[\"WGS 84\",DATUM[\"WGS_1984\",SPHEROID[\"WGS 84\",6378137,298.257223563]],PRIMEM[\"Greenwich\",0],UNIT[\"degree\",0.0174532925199433]]", "longitude/latitude coordinates in decimal degrees on the WGS 84 spheroid"),
            ),
        )
        for table in PersonalStore.ATTRIBUTE_TABLES:
            connection.execute(
                """INSERT INTO gpkg_contents
                   (table_name, data_type, identifier, description, last_change)
                   VALUES (?, 'attributes', ?, ?, ?)""",
                (table, table, "Qeoloog personal data", now),
            )
        connection.execute(
            "INSERT INTO qeoloog_metadata (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        connection.execute(
            """INSERT INTO qeoloog_datasets
               (id, name, owner, description, licence, created_at, updated_at)
               VALUES (?, ?, '', '', '', ?, ?)""",
            (_uuid(), dataset_name, now, now),
        )
        connection.commit()

    def default_dataset_id(self, connection=None):
        own = connection is None
        connection = connection or self._connect()
        try:
            row = connection.execute(
                "SELECT id FROM qeoloog_datasets ORDER BY created_at LIMIT 1"
            ).fetchone()
            return row["id"] if row else None
        finally:
            if own:
                connection.close()

    def ensure_link(self, source_system, source_type, source_id, gea_id="", sarv_id="", name=""):
        with closing(self._connect()) as connection, connection:
            dataset_id = self.default_dataset_id(connection)
            row = connection.execute(
                """SELECT id FROM qeoloog_object_links
                   WHERE dataset_id=? AND source_system=? AND source_type=? AND source_id=?""",
                (dataset_id, source_system, source_type, _text(source_id)),
            ).fetchone()
            now = _now()
            if row:
                connection.execute(
                    """UPDATE qeoloog_object_links SET gea_id=?, sarv_id=?, name=?,
                       updated_at=? WHERE id=?""",
                    (_text(gea_id), _text(sarv_id), _text(name), now, row["id"]),
                )
                return row["id"]
            link_id = _uuid()
            connection.execute(
                """INSERT INTO qeoloog_object_links
                   (id, dataset_id, source_system, source_type, source_id, gea_id,
                    sarv_id, name, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)""",
                (
                    link_id, dataset_id, source_system, source_type,
                    _text(source_id), _text(gea_id), _text(sarv_id), _text(name),
                    now, now,
                ),
            )
            return link_id

    def import_lab_rows(self, source_file, rows, mapping, link):
        source_mapping = dict(mapping)
        wide_columns = list(source_mapping.get("wide_parameters") or [])
        if wide_columns:
            expanded = []
            for row in rows:
                for column in wide_columns:
                    value = row.get(column)
                    if not _text(value):
                        continue
                    item = dict(row)
                    item["__qeoloog_parameter"] = column
                    item["__qeoloog_value"] = value
                    expanded.append(item)
            rows = expanded
            mapping = {
                key: value for key, value in source_mapping.items()
                if key != "wide_parameters"
            }
            mapping["parameter"] = "__qeoloog_parameter"
            mapping["value"] = "__qeoloog_value"
        else:
            mapping = source_mapping
        required = ("sample_number", "parameter", "value")
        missing = [field for field in required if not mapping.get(field)]
        if missing:
            raise ValueError("Required field mappings are missing: " + ", ".join(missing))
        warnings = []
        prepared = []
        for row_number, row in enumerate(rows, start=2):
            values = {
                field: _text(row.get(column))
                for field, column in mapping.items()
                if column
            }
            if not values.get("sample_number") or not values.get("parameter"):
                warnings.append(f"Row {row_number}: missing sample number or parameter")
                continue
            raw_value = values.get("value", "")
            if not raw_value:
                warnings.append(f"Row {row_number}: missing result value")
                continue
            try:
                numeric_value = _number(raw_value)
                text_value = ""
            except ValueError:
                numeric_value = None
                text_value = raw_value
            numeric = {}
            invalid = False
            for field in ("depth_from", "depth_to", "detection_limit", "uncertainty"):
                try:
                    numeric[field] = _number(values.get(field))
                except ValueError:
                    warnings.append(f"Row {row_number}: invalid {field} value")
                    invalid = True
            if invalid:
                continue
            prepared.append((values, numeric, numeric_value, text_value))
        if not prepared:
            raise ValueError("No valid data rows were found.")

        source_path = Path(source_file)
        if source_path.exists():
            source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        else:
            source_hash = hashlib.sha256(
                json.dumps(
                    {"rows": rows, "mapping": mapping},
                    ensure_ascii=False, sort_keys=True, default=str,
                ).encode("utf-8")
            ).hexdigest()
        link_id = self.ensure_link(**link)
        with closing(self._connect()) as connection, connection:
            dataset_id = self.default_dataset_id(connection)
            duplicate = connection.execute(
                """SELECT imported_at FROM qeoloog_import_batches
                   WHERE dataset_id=? AND source_sha256=?""",
                (dataset_id, source_hash),
            ).fetchone()
            if duplicate:
                raise ValueError(
                    "This exact source file was already imported on "
                    + str(duplicate["imported_at"])
                )
            now = _now()
            sample_cache = {}
            specimen_cache = {}
            analysis_cache = {}

            def get_sample(values, numeric):
                key = values["sample_number"]
                if key in sample_cache:
                    return sample_cache[key]
                existing = connection.execute(
                    """SELECT id FROM qeoloog_samples
                       WHERE dataset_id=? AND link_id=? AND number=?""",
                    (dataset_id, link_id, key),
                ).fetchone()
                if existing:
                    sample_cache[key] = existing["id"]
                    return existing["id"]
                sample_id = _uuid()
                connection.execute(
                    """INSERT INTO qeoloog_samples
                       (id, dataset_id, link_id, number, sample_type, purpose,
                        status, depth_from, depth_to, collected_date, unit,
                        remarks, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sample_id, dataset_id, link_id, key,
                        values.get("sample_type"), values.get("purpose"),
                        values.get("status"), numeric.get("depth_from"),
                        numeric.get("depth_to"), values.get("date"),
                        values.get("unit"), values.get("remarks"), now, now,
                    ),
                )
                sample_cache[key] = sample_id
                return sample_id

            def get_specimen(values, numeric, sample_id):
                number = values.get("specimen_number")
                if not number:
                    return None
                key = (number, sample_id)
                if key in specimen_cache:
                    return specimen_cache[key]
                existing = connection.execute(
                    """SELECT id FROM qeoloog_specimens
                       WHERE dataset_id=? AND link_id=? AND sample_id=? AND number=?""",
                    (dataset_id, link_id, sample_id, number),
                ).fetchone()
                if existing:
                    specimen_cache[key] = existing["id"]
                    return existing["id"]
                specimen_id = _uuid()
                connection.execute(
                    """INSERT INTO qeoloog_specimens
                       (id, dataset_id, link_id, sample_id, number, depth_from,
                        depth_to, remarks, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        specimen_id, dataset_id, link_id, sample_id, number,
                        numeric.get("depth_from"), numeric.get("depth_to"),
                        values.get("remarks"), now, now,
                    ),
                )
                specimen_cache[key] = specimen_id
                return specimen_id

            def get_analysis(values, sample_id, specimen_id):
                key = (
                    sample_id, specimen_id, values.get("analysis_code"),
                    values.get("method"), values.get("lab"),
                    values.get("lab_number"), values.get("date"),
                )
                if key in analysis_cache:
                    return analysis_cache[key]
                analysis_id = _uuid()
                connection.execute(
                    """INSERT INTO qeoloog_analyses
                       (id, dataset_id, link_id, sample_id, specimen_id, code,
                        lab_number, method, lab, analysis_date, remarks,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        analysis_id, dataset_id, link_id, sample_id, specimen_id,
                        values.get("analysis_code"), values.get("lab_number"),
                        values.get("method"), values.get("lab"), values.get("date"),
                        values.get("remarks"), now, now,
                    ),
                )
                analysis_cache[key] = analysis_id
                return analysis_id

            for values, numeric, value_num, value_text in prepared:
                sample_id = get_sample(values, numeric)
                specimen_id = get_specimen(values, numeric, sample_id)
                analysis_id = get_analysis(values, sample_id, specimen_id)
                connection.execute(
                    """INSERT INTO qeoloog_analysis_results
                       (id, analysis_id, parameter, value_num, value_text, unit,
                        qualifier, detection_limit, uncertainty, depth_from,
                        depth_to, remarks, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        _uuid(), analysis_id, values["parameter"], value_num,
                        value_text, values.get("unit"), values.get("qualifier"),
                        numeric.get("detection_limit"), numeric.get("uncertainty"),
                        numeric.get("depth_from"), numeric.get("depth_to"),
                        values.get("remarks"), now, now,
                    ),
                )
            connection.execute(
                """INSERT INTO qeoloog_import_batches
                   (id, dataset_id, source_file, imported_at, row_count,
                    source_sha256, mapping_json, warnings_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _uuid(), dataset_id, str(source_file), now, len(prepared),
                    source_hash,
                    json.dumps(source_mapping, ensure_ascii=False),
                    json.dumps(warnings, ensure_ascii=False),
                ),
            )
        return {"imported": len(prepared), "warnings": warnings}

    def counts(self):
        if not self.is_open:
            return {}
        queries = {
            "qeoloog_object_links": "SELECT COUNT(*) FROM qeoloog_object_links",
            "qeoloog_samples": "SELECT COUNT(*) FROM qeoloog_samples",
            "qeoloog_specimens": "SELECT COUNT(*) FROM qeoloog_specimens",
            "qeoloog_analyses": "SELECT COUNT(*) FROM qeoloog_analyses",
            "qeoloog_analysis_results": "SELECT COUNT(*) FROM qeoloog_analysis_results",
        }
        with closing(self._connect()) as connection, connection:
            return {
                table: connection.execute(query).fetchone()[0]
                for table, query in queries.items()
            }

    def records_for_object(self, source_system, source_type, source_id, gea_id="", sarv_id=""):
        if not self.is_open:
            return {"samples": [], "specimens": [], "analyses": []}
        values = (
            source_system, source_type, _text(source_id),
            source_type, _text(gea_id), source_type, _text(sarv_id),
        )
        with closing(self._connect()) as connection, connection:
            samples = [
                dict(row) for row in connection.execute(
                    """SELECT record.* FROM qeoloog_samples AS record
                       JOIN qeoloog_object_links AS link ON link.id=record.link_id
                       WHERE (
                         (link.source_system=? AND link.source_type=? AND link.source_id=?)
                         OR (link.source_system='GEA' AND link.source_type=? AND link.gea_id=?)
                         OR (link.source_system='SARV' AND link.source_type=? AND link.sarv_id=?)
                       )
                       ORDER BY record.depth_from, record.number""",
                    values,
                )
            ]
            specimens = [
                dict(row) for row in connection.execute(
                    """SELECT record.* FROM qeoloog_specimens AS record
                       JOIN qeoloog_object_links AS link ON link.id=record.link_id
                       WHERE (
                         (link.source_system=? AND link.source_type=? AND link.source_id=?)
                         OR (link.source_system='GEA' AND link.source_type=? AND link.gea_id=?)
                         OR (link.source_system='SARV' AND link.source_type=? AND link.sarv_id=?)
                       )
                       ORDER BY record.depth_from, record.number""",
                    values,
                )
            ]
            analyses = []
            for row in connection.execute(
                """SELECT record.* FROM qeoloog_analyses AS record
                   JOIN qeoloog_object_links AS link ON link.id=record.link_id
                   WHERE (
                     (link.source_system=? AND link.source_type=? AND link.source_id=?)
                     OR (link.source_system='GEA' AND link.source_type=? AND link.gea_id=?)
                     OR (link.source_system='SARV' AND link.source_type=? AND link.sarv_id=?)
                   )
                   ORDER BY record.analysis_date, record.code""",
                values,
            ):
                item = dict(row)
                item["results"] = [
                    dict(result) for result in connection.execute(
                        """SELECT * FROM qeoloog_analysis_results
                           WHERE analysis_id=? ORDER BY parameter""",
                        (row["id"],),
                    )
                ]
                analyses.append(item)
            return {
                "samples": samples,
                "specimens": specimens,
                "analyses": analyses,
            }

    def _all_rows(self, connection, table):
        queries = {
            "qeoloog_samples": "SELECT * FROM qeoloog_samples ORDER BY rowid",
            "qeoloog_specimens": "SELECT * FROM qeoloog_specimens ORDER BY rowid",
            "qeoloog_analyses": "SELECT * FROM qeoloog_analyses ORDER BY rowid",
            "qeoloog_analysis_results": "SELECT * FROM qeoloog_analysis_results ORDER BY rowid",
            "qeoloog_object_links": "SELECT * FROM qeoloog_object_links ORDER BY rowid",
        }
        if table not in queries:
            raise ValueError(f"Unsupported table: {table}")
        return [
            dict(row) for row in connection.execute(queries[table])
        ]

    @staticmethod
    def _write_csv(archive, name, fieldnames, rows):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        archive.writestr(name, "\ufeff" + stream.getvalue())

    def export(self, path, target):
        target = target.casefold()
        if target not in {"gea", "sarv"}:
            raise ValueError("Export target must be GEA or SARV.")
        output = Path(path)
        if output.suffix.casefold() != ".zip":
            output = output.with_suffix(".zip")
        with closing(self._connect()) as connection, connection:
            samples = self._all_rows(connection, "qeoloog_samples")
            specimens = self._all_rows(connection, "qeoloog_specimens")
            analyses = self._all_rows(connection, "qeoloog_analyses")
            results = self._all_rows(connection, "qeoloog_analysis_results")
            link_rows = self._all_rows(connection, "qeoloog_object_links")
            links = {row["id"]: row for row in link_rows}
        warnings = []
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            if target == "gea":
                sample_rows = []
                for row in samples:
                    link = links.get(row.get("link_id"), {})
                    if not link.get("source_id"):
                        warnings.append(f"Sample {row['number']}: missing source object ID")
                    sample_rows.append({
                        "esri_globalid": row["id"],
                        "proov_tahis_alg": row["number"],
                        "proov_tyyp": row.get("sample_type"),
                        "z_suht_ylemine": row.get("depth_from"),
                        "z_suht_alumine": row.get("depth_to"),
                        "eesmark": row.get("purpose"),
                        "staatus": row.get("status"),
                        "aeg": row.get("collected_date"),
                        "kogus": row.get("mass"),
                        "yhik": row.get("unit"),
                        "proov_meetod": row.get("method"),
                        "litoloogia": row.get("lithology"),
                        "kivim": row.get("rock"),
                        "stratigraafia": row.get("stratigraphy"),
                        "markus": row.get("remarks"),
                        "puurauk_vaatluspunkt_id": link.get("source_id"),
                    })
                analysis_rows = [{
                    "esri_globalid": row["id"],
                    "analyys_kood": row.get("code"),
                    "labor_analyys_nr": row.get("lab_number"),
                    "kuupaev": row.get("analysis_date"),
                    "analyys_meetod": row.get("method"),
                    "labor": row.get("lab"),
                    "seade": row.get("instrument"),
                    "markus": row.get("remarks"),
                    "puurauk_vaatluspunkt_id": links.get(row.get("link_id"), {}).get("source_id"),
                    "proov_id": row.get("sample_id"),
                } for row in analyses]
                result_rows = [{
                    "esri_globalid": row["id"],
                    "analyys_mootmine_id": row["analysis_id"],
                    "analyys_naitaja": row["parameter"],
                    "tulem": row.get("value_num") if row.get("value_num") is not None else row.get("value_text"),
                    "yhik": row.get("unit"),
                    "tunnus": row.get("qualifier"),
                    "maaramispiir_alumine": row.get("detection_limit"),
                    "z_suht_ylemine": row.get("depth_from"),
                    "z_suht_alumine": row.get("depth_to"),
                    "markus": row.get("remarks"),
                } for row in results]
                self._write_csv(archive, "proov.csv", tuple(sample_rows[0].keys()) if sample_rows else (
                    "esri_globalid", "proov_tahis_alg", "proov_tyyp", "z_suht_ylemine",
                    "z_suht_alumine", "eesmark", "staatus", "aeg", "kogus", "yhik",
                    "proov_meetod", "litoloogia", "kivim", "stratigraafia", "markus",
                    "puurauk_vaatluspunkt_id",
                ), sample_rows)
                self._write_csv(archive, "analyys_mootmine.csv", tuple(analysis_rows[0].keys()) if analysis_rows else (
                    "esri_globalid", "analyys_kood", "labor_analyys_nr", "kuupaev",
                    "analyys_meetod", "labor", "seade", "markus",
                    "puurauk_vaatluspunkt_id", "proov_id",
                ), analysis_rows)
                self._write_csv(archive, "analyys_tulem.csv", tuple(result_rows[0].keys()) if result_rows else (
                    "esri_globalid", "analyys_mootmine_id", "analyys_naitaja", "tulem",
                    "yhik", "tunnus", "maaramispiir_alumine", "z_suht_ylemine",
                    "z_suht_alumine", "markus",
                ), result_rows)
            else:
                sample_rows = [{
                    "id": row["id"],
                    "number": row["number"],
                    "locality": links.get(row.get("link_id"), {}).get("sarv_id")
                    or links.get(row.get("link_id"), {}).get("source_id"),
                    "depth": row.get("depth_from"),
                    "depth_interval": row.get("depth_to"),
                    "type": row.get("sample_type"),
                    "purpose": row.get("purpose"),
                    "stratigraphy": row.get("stratigraphy"),
                    "rock": row.get("rock"),
                    "collector": row.get("collector"),
                    "date": row.get("collected_date"),
                    "mass": row.get("mass"),
                    "storage": "",
                    "remarks": row.get("remarks"),
                } for row in samples]
                specimen_rows = [{
                    "id": row["id"],
                    "specimen_id": row["number"],
                    "locality": links.get(row.get("link_id"), {}).get("sarv_id")
                    or links.get(row.get("link_id"), {}).get("source_id"),
                    "depth": row.get("depth_from"),
                    "depth_interval": row.get("depth_to"),
                    "sample": row.get("sample_id"),
                    "type": row.get("specimen_type"),
                    "rock": row.get("rock"),
                    "stratigraphy": row.get("stratigraphy"),
                    "storage": row.get("storage"),
                    "remarks": row.get("remarks"),
                } for row in specimens]
                analysis_rows = [{
                    "id": row["id"],
                    "sample": row.get("sample_id"),
                    "specimen": row.get("specimen_id"),
                    "locality": links.get(row.get("link_id"), {}).get("sarv_id")
                    or links.get(row.get("link_id"), {}).get("source_id"),
                    "depth": next((
                        sample.get("depth_from") for sample in samples
                        if sample["id"] == row.get("sample_id")
                    ), None),
                    "analysis_method": row.get("method"),
                    "lab": row.get("lab"),
                    "instrument": row.get("instrument"),
                    "date": row.get("analysis_date"),
                    "remarks": row.get("remarks"),
                } for row in analyses]
                result_rows = [{
                    "id": row["id"],
                    "analysis": row["analysis_id"],
                    "parameter": row["parameter"],
                    "value": row.get("value_num"),
                    "value_text": row.get("value_text"),
                    "unit": row.get("unit"),
                    "error": row.get("uncertainty"),
                    "remarks": row.get("remarks"),
                } for row in results]
                self._write_csv(archive, "sample.csv", tuple(sample_rows[0].keys()) if sample_rows else (
                    "id", "number", "locality", "depth", "depth_interval", "type",
                    "purpose", "stratigraphy", "rock", "collector", "date", "mass",
                    "storage", "remarks",
                ), sample_rows)
                self._write_csv(archive, "specimen.csv", tuple(specimen_rows[0].keys()) if specimen_rows else (
                    "id", "specimen_id", "locality", "depth", "depth_interval",
                    "sample", "type", "rock", "stratigraphy", "storage", "remarks",
                ), specimen_rows)
                self._write_csv(archive, "analysis.csv", tuple(analysis_rows[0].keys()) if analysis_rows else (
                    "id", "sample", "specimen", "locality", "depth",
                    "analysis_method", "lab", "instrument", "date", "remarks",
                ), analysis_rows)
                self._write_csv(archive, "analysis_results.csv", tuple(result_rows[0].keys()) if result_rows else (
                    "id", "analysis", "parameter", "value", "value_text", "unit",
                    "error", "remarks",
                ), result_rows)

            self._write_csv(
                archive, "object_links.csv",
                (
                    "id", "source_system", "source_type", "source_id",
                    "gea_id", "sarv_id", "name", "notes",
                ),
                link_rows,
            )
            manifest = {
                "format": f"Qeoloog {target.upper()} converter package",
                "schema_version": SCHEMA_VERSION,
                "created_at": _now(),
                "source": str(self.path),
                "note": (
                    "Field-mapped staging export. Validate controlled vocabularies "
                    "and identifiers before importing into the target database."
                ),
                "counts": {
                    "samples": len(samples), "specimens": len(specimens),
                    "analyses": len(analyses), "results": len(results),
                },
            }
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            self._write_csv(
                archive, "validation.csv", ("severity", "message"),
                [{"severity": "warning", "message": value} for value in warnings],
            )
        return output, warnings
