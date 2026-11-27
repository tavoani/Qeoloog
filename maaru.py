"""Local searchable cache for MaRu's public historical core database.

The official download is a small ZIP containing four tab-separated CSV
tables.  Keeping a normalized SQLite copy avoids scraping the legacy HTML
search pages and makes Qeoloog searches and EGT link resolution immediate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
from math import hypot
import os
from pathlib import Path
import re
import sqlite3
from unicodedata import normalize
from zipfile import ZipFile


MAARU_ARCHIVE_URL = (
    "https://geoportaal.maaamet.ee/docs/geoloogia/andmed/puuraugud.zip"
)
MAARU_DETAIL_URL = (
    "https://geoportaal.maaamet.ee/index.php?lang_id=1&action=viewPA"
    "&pa_id={id}&fr=o&bk=1&page_id=382"
)
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
SCHEMA_VERSION = "2"


def _number(value):
    if value in (None, "", "NA", "NULL", "-9999"):
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _normalized(value):
    value = normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode("ascii")
    return " ".join(value.casefold().split())


def _identifier(value):
    """Return stable text for integer-like registry identifiers."""
    if value in (None, "", "NULL", "<NULL>"):
        return ""
    text = str(value).strip()
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        text = text.split(".", 1)[0]
    return text


def _index_category(value):
    """Classify one historical stratigraphic index into EGT domains."""
    text = str(value or "").strip()
    normalized = _normalized(text).replace(" ", "").upper()
    if normalized in {"", "-", "NA", "NULL", "TEADMATA"}:
        return 997
    if normalized.startswith(("AR", "PR", "PP", "MP", "NP")):
        return 3
    if normalized.startswith("Q") or re.match(
        r"^[A-ZÕÄÖÜ]+(?:I{1,3}|IV)(?:[A-ZÕÄÖÜ0-9-]*)$", normalized,
    ):
        return 1
    return 2


def point_category(parent, geology=()):
    """Return cover/bedrock/basement with the standard priority order."""
    categories = {
        _index_category(
            row.get("strat_indeks") or row.get("strat")
            or row.get("stratigraafia algus")
        )
        for row in geology or ()
    }
    if not categories.difference({997}):
        categories.update(
            _index_category((parent or {}).get(key))
            for key in (
                "südamiku lõpu indeks", "strat. lõpp", "strat. algus",
            )
        )
    for code in (3, 2, 1):
        if code in categories:
            return code
    return 997


def _public_url(value):
    """Upgrade legacy Maa-amet links to the working HTTPS endpoint."""
    text = str(value or "").strip()
    prefix = "http://geoportaal.maaamet.ee/"
    if text.startswith(prefix):
        return "https://geoportaal.maaamet.ee/" + text[len(prefix):]
    return text


def _archive_rows(archive, filename):
    """Yield dictionaries from MaRu's quoted tab-separated export."""
    with archive.open(filename) as handle:
        text = handle.read().decode("utf-8-sig", errors="replace")
    rows = []
    for raw_line in text.splitlines():
        line = raw_line.strip("\r\n")
        if not line:
            continue
        # The exporter wraps the whole TSV row in quotes and appends a
        # semicolon: ``"field\tfield";``.
        line = line.rstrip(";")
        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        rows.append(line.replace('""', '"').split("\t"))
    if not rows:
        return
    headers = [value.strip() for value in rows[0]]
    for values in rows[1:]:
        if len(values) < len(headers):
            values.extend([""] * (len(headers) - len(values)))
        yield {
            header: values[index].strip()
            for index, header in enumerate(headers)
        }


def _search_text(row):
    return _normalized(" ".join(
        str(value) for value in row.values() if value not in (None, "")
    ))


def build_database(payload, target):
    """Build an atomic SQLite cache from official ZIP bytes."""
    if not payload or len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("Invalid or oversized MaRu archive")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".new")
    if temporary.exists():
        temporary.unlink()

    connection = sqlite3.connect(str(temporary))
    try:
        connection.executescript("""
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE pa (
                id TEXT PRIMARY KEY, data TEXT NOT NULL, search_text TEXT,
                x REAL, y REAL, z REAL, depth REAL,
                cleaned_id TEXT, sarv_id TEXT, gb_id TEXT,
                number TEXT, name TEXT, category INTEGER
            );
            CREATE TABLE geol (
                id TEXT NOT NULL, pa_id TEXT NOT NULL,
                data TEXT NOT NULL, search_text TEXT,
                top REAL, thickness REAL,
                PRIMARY KEY (pa_id, id)
            );
            CREATE TABLE core_box (
                id TEXT NOT NULL, pa_id TEXT NOT NULL,
                data TEXT NOT NULL, search_text TEXT,
                top REAL, bottom REAL,
                PRIMARY KEY (pa_id, id)
            );
            CREATE TABLE sample (
                id TEXT NOT NULL, pa_id TEXT NOT NULL,
                data TEXT NOT NULL, search_text TEXT, depth REAL,
                PRIMARY KEY (pa_id, id)
            );
        """)
        with ZipFile(BytesIO(payload)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Oversized uncompressed MaRu archive")
            required = {"pa.csv", "geol.csv", "kast.csv", "proov.csv"}
            if not required.issubset(set(archive.namelist())):
                raise ValueError("MaRu archive is missing required tables")

            connection.executemany(
                "INSERT INTO pa VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    (
                        row.get("id"),
                        json.dumps(row, ensure_ascii=False),
                        _search_text(row),
                        _number(row.get("y")),  # L-EST easting in this export
                        _number(row.get("x")),  # L-EST northing in this export
                        _number(row.get("z")),
                        _number(row.get("sygavus")),
                        row.get("uus_id"), row.get("sarv_loc_id"),
                        row.get("GB_id"), row.get("number"),
                        row.get("nimetus"), 997,
                    )
                    for row in _archive_rows(archive, "pa.csv")
                    if row.get("id")
                ),
            )
            connection.executemany(
                "INSERT INTO geol VALUES (?,?,?,?,?,?)",
                (
                    (
                        row.get("id"), row.get("pa_id"),
                        json.dumps(row, ensure_ascii=False),
                        _search_text(row), _number(row.get("sygavus")),
                        _number(row.get("d")),
                    )
                    for row in _archive_rows(archive, "geol.csv")
                    if row.get("id") and row.get("pa_id")
                ),
            )
            connection.executemany(
                "INSERT INTO core_box VALUES (?,?,?,?,?,?)",
                (
                    (
                        row.get("id"), row.get("pa_id"),
                        json.dumps(row, ensure_ascii=False),
                        _search_text(row), _number(row.get("algus")),
                        _number(row.get("lõpp")),
                    )
                    for row in _archive_rows(archive, "kast.csv")
                    if row.get("id") and row.get("pa_id")
                ),
            )
            connection.executemany(
                "INSERT INTO sample VALUES (?,?,?,?,?)",
                (
                    (
                        row.get("kasipala_id"), row.get("pa_id"),
                        json.dumps(row, ensure_ascii=False),
                        _search_text(row), _number(row.get("sygavus")),
                    )
                    for row in _archive_rows(archive, "proov.csv")
                    if row.get("kasipala_id") and row.get("pa_id")
                ),
            )
            geology_by_parent = {}
            for parent_id, raw in connection.execute(
                "SELECT pa_id,data FROM geol"
            ):
                geology_by_parent.setdefault(str(parent_id), []).append(
                    json.loads(raw)
                )
            category_updates = []
            for parent_id, raw in connection.execute("SELECT id,data FROM pa"):
                parent = json.loads(raw)
                category_updates.append((
                    point_category(
                        parent, geology_by_parent.get(str(parent_id), ()),
                    ),
                    str(parent_id),
                ))
            connection.executemany(
                "UPDATE pa SET category=? WHERE id=?", category_updates,
            )
            source_year = ""
            if "kaaskiri.txt" in archive.namelist():
                note = archive.read("kaaskiri.txt").decode(
                    "utf-8", errors="replace"
                )
                match = re.search(r"Maa-amet\s+(20\d{2})", note)
                source_year = match.group(1) if match else ""

        connection.executescript("""
            CREATE INDEX pa_cleaned_id ON pa(cleaned_id);
            CREATE INDEX pa_sarv_id ON pa(sarv_id);
            CREATE INDEX pa_gb_id ON pa(gb_id);
            CREATE INDEX pa_number ON pa(number);
            CREATE INDEX geol_parent ON geol(pa_id, top);
            CREATE INDEX core_box_parent ON core_box(pa_id, top);
            CREATE INDEX sample_parent ON sample(pa_id, depth);
        """)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source_year": source_year,
            "record_count": str(
                connection.execute("SELECT count(*) FROM pa").fetchone()[0]
            ),
        }
        connection.executemany(
            "INSERT INTO meta(key,value) VALUES (?,?)", metadata.items()
        )
        connection.commit()
    except Exception:
        connection.close()
        if temporary.exists():
            temporary.unlink()
        raise
    connection.close()
    os.replace(str(temporary), str(target))
    return str(target)


class MaaruDatabase:
    """Small read-only facade over the local MaRu SQLite cache."""

    def __init__(self, path):
        self.path = str(path)

    @property
    def available(self):
        try:
            with self._connect() as connection:
                value = connection.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()
            return bool(value and value[0] == SCHEMA_VERSION)
        except (OSError, sqlite3.Error):
            return False

    def _connect(self):
        connection = sqlite3.connect(
            f"file:{Path(self.path).resolve()}?mode=ro", uri=True
        )
        connection.row_factory = sqlite3.Row
        connection.create_function(
            "qeoloog_norm", 1, _normalized, deterministic=True
        )
        return connection

    def metadata(self):
        with self._connect() as connection:
            return dict(connection.execute("SELECT key,value FROM meta"))

    @staticmethod
    def _decoded(row):
        if row is None:
            return None
        value = json.loads(row["data"])
        value["_maaru_x"] = row["x"] if "x" in row.keys() else None
        value["_maaru_y"] = row["y"] if "y" in row.keys() else None
        if "category" in row.keys():
            value["klassif_yksus_kood"] = row["category"]
        return value

    def point(self, identifier):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pa WHERE id=?", (_identifier(identifier),)
            ).fetchone()
        return self._decoded(row)

    def points(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,data,x,y,z,depth,cleaned_id,sarv_id,gb_id,number,name "
                ",category FROM pa WHERE x IS NOT NULL AND y IS NOT NULL"
            ).fetchall()
        return [self._decoded(row) for row in rows]

    def _related(self, table, identifier):
        order = {
            "geol": "top, id", "core_box": "top, id",
            "sample": "depth, id",
        }[table]
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT data FROM {table} WHERE pa_id=? ORDER BY {order}",
                (str(identifier),),
            ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def related(self, identifier):
        parent = self.point(identifier) or {}
        sample_rows = self._related("sample", identifier)
        for row in sample_rows:
            # Older MaRu exports only carry ``pa_id`` in the sample table.
            # Keep the location reference useful by inheriting its public
            # collar number/name from the related parent record.
            row.setdefault("pa_nr", parent.get("number"))
            row.setdefault("pa_nimetus", parent.get("nimetus"))
        return {
            "geology": self._related("geol", identifier),
            "core_boxes": self._related("core_box", identifier),
            "samples": sample_rows,
        }

    def exact_matches(self, attributes):
        """Return strong EGT→MaRu candidates without guessing by name."""
        clauses = []
        values = []
        for column, key in (
            ("id", "ma_orig_id"), ("cleaned_id", "korrastatud_nr"),
            ("sarv_id", "sarv_id"), ("gb_id", "gb_id"),
        ):
            value = _identifier(attributes.get(key))
            if value and value not in {"0", "None", "NULL"}:
                clauses.append(f"{column}=?")
                values.append(value)
        if not clauses:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pa WHERE " + " OR ".join(clauses), values
            ).fetchall()
        return [self._decoded(row) for row in rows]

    def candidates(self, attributes, invalid_source_id=False, limit=5):
        exact = self.exact_matches(attributes)
        result = {}
        source_id = _identifier(attributes.get("ma_orig_id"))
        cleaned_id = _identifier(attributes.get("korrastatud_nr"))
        sarv_id = _identifier(attributes.get("sarv_id"))
        gb_id = _normalized(attributes.get("gb_id"))
        numbers = {
            _normalized(attributes.get(key))
            for key in ("nimi", "korrastatud_nr")
            if attributes.get(key)
        }
        names = {
            _normalized(attributes.get(key))
            for key in ("alias", "nimi")
            if attributes.get(key)
            and any(character.isalpha() for character in str(attributes.get(key)))
        }
        depth = _number(
            attributes.get("pikkus") or attributes.get("vertikaalne_ulatus")
        )
        x = _number(attributes.get("_qeoloog_x_3301"))
        y = _number(attributes.get("_qeoloog_y_3301"))

        def add(row):
            identifier = str(row.get("id") or "")
            if not identifier:
                return
            score = 0
            evidence = []
            if not invalid_source_id and source_id and identifier == source_id:
                score += 5000
                evidence.append("EGT ma_orig_id")
            if cleaned_id and str(row.get("uus_id") or "") == cleaned_id:
                score += 2000
                evidence.append("korrastatud ID")
            if sarv_id and str(row.get("sarv_loc_id") or "") == sarv_id:
                score += 800
                evidence.append("SARV ID")
            if gb_id and _normalized(row.get("GB_id")) == gb_id:
                score += 1200
                evidence.append("GB ID")
            row_number = _normalized(row.get("number"))
            row_name = _normalized(row.get("nimetus"))
            number_match = bool(row_number and row_number in numbers)
            name_match = bool(
                row_name and any(
                    row_name == name or row_name in name or name in row_name
                    for name in names
                )
            )
            if number_match:
                score += 500
                evidence.append("number")
            if name_match:
                score += 550
                evidence.append("nimi")
            row_depth = _number(row.get("sygavus"))
            if depth is not None and row_depth is not None:
                difference = abs(depth - row_depth)
                if difference <= 1:
                    score += 250
                    evidence.append(f"Δh {difference:g} m")
            row_x = _number(row.get("y"))
            row_y = _number(row.get("x"))
            if None not in (x, y, row_x, row_y):
                distance = hypot(x - row_x, y - row_y)
                if distance <= 500:
                    score += max(0, 350 - distance * 0.4)
                    evidence.append(f"{distance:.0f} m")
            if score >= 500:
                row = dict(row)
                row["_score"] = score
                row["_evidence"] = " · ".join(evidence)
                result[identifier] = row

        for row in exact:
            add(row)
        # Strong identifiers usually settle the link without a broad scan.
        if not result and (names or (x is not None and y is not None)):
            terms = sorted(names)
            with self._connect() as connection:
                if terms:
                    clauses = " OR ".join("search_text LIKE ?" for _ in terms)
                    rows = connection.execute(
                        f"SELECT * FROM pa WHERE {clauses} LIMIT 200",
                        [f"%{term}%" for term in terms],
                    ).fetchall()
                elif x is not None and y is not None:
                    rows = connection.execute(
                        "SELECT * FROM pa WHERE x BETWEEN ? AND ? "
                        "AND y BETWEEN ? AND ? LIMIT 200",
                        (x - 250, x + 250, y - 250, y + 250),
                    ).fetchall()
            for row in rows:
                add(self._decoded(row))
        return sorted(
            result.values(), key=lambda row: -float(row.get("_score") or 0)
        )[:limit]

    def search(
        self, text="", depth_min=None, depth_max=None,
        stratigraphic_indices=(), require_core=None, require_samples=None,
        maaru_filters=None,
        limit=500,
    ):
        tokens = [token for token in _normalized(text).split() if token]
        clauses = []
        values = []
        for token in tokens:
            clauses.append(
                "(p.search_text LIKE ? OR EXISTS ("
                "SELECT 1 FROM geol g WHERE g.pa_id=p.id AND g.search_text LIKE ?"
                ") OR EXISTS (SELECT 1 FROM core_box c WHERE c.pa_id=p.id "
                "AND c.search_text LIKE ?) OR EXISTS (SELECT 1 FROM sample s "
                "WHERE s.pa_id=p.id AND s.search_text LIKE ?))"
            )
            values.extend([f"%{token}%"] * 4)
        if depth_min is not None:
            clauses.append("p.depth>=?")
            values.append(float(depth_min))
        if depth_max is not None:
            clauses.append("p.depth<=?")
            values.append(float(depth_max))
        indices = [
            _normalized(value) for value in stratigraphic_indices if value
        ]
        if indices:
            index_clauses = []
            for index in indices:
                index_clauses.append(
                    "lower(json_extract(g.data, '$.strat_indeks')) LIKE ?"
                )
                values.append(f"%{index}%")
            clauses.append(
                "EXISTS (SELECT 1 FROM geol g WHERE g.pa_id=p.id AND ("
                + " OR ".join(index_clauses) + "))"
            )
        if require_core is not None:
            clauses.append(
                ("EXISTS" if require_core else "NOT EXISTS")
                + " (SELECT 1 FROM core_box c WHERE c.pa_id=p.id)"
            )
        if require_samples is not None:
            clauses.append(
                ("EXISTS" if require_samples else "NOT EXISTS")
                + " (SELECT 1 FROM sample s WHERE s.pa_id=p.id)"
            )
        filters = dict(maaru_filters or {})

        def parent_text_filter(json_key, value):
            value = _normalized(value)
            if value:
                clauses.append(
                    f"qeoloog_norm(json_extract(p.data, '$.{json_key}')) LIKE ?"
                )
                values.append(f"%{value}%")

        def sample_text_filter(json_key, value):
            value = _normalized(value)
            if value:
                clauses.append(
                    "EXISTS (SELECT 1 FROM sample s WHERE s.pa_id=p.id AND "
                    f"qeoloog_norm(json_extract(s.data, '$.{json_key}')) LIKE ?)"
                )
                values.append(f"%{value}%")

        identifier = _identifier(filters.get("maaru_id"))
        if identifier:
            clauses.append("p.id=?")
            values.append(identifier)
        parent_text_filter("GB_id", filters.get("gb_id"))
        parent_text_filter("fond", filters.get("fund"))
        sample_text_filter("kivim", filters.get("rock"))
        sample_text_filter("hoidla", filters.get("storage"))
        sample_text_filter("kast", filters.get("box"))
        sample_text_filter("koguja", filters.get("collector"))
        sample_location = _normalized(filters.get("sample_location"))
        if sample_location:
            location_keys = (
                "pa_id", "pa_GB_id", "pa_nimetus", "pa_nr",
                "pa_sarv_loc_id", "pa_uus_id",
            )
            clauses.append(
                "(qeoloog_norm(p.number) LIKE ? OR "
                "qeoloog_norm(p.name) LIKE ? OR "
                "EXISTS (SELECT 1 FROM sample s WHERE s.pa_id=p.id AND ("
                + " OR ".join(
                    "qeoloog_norm(json_extract(s.data, '$.%s')) LIKE ?" % key
                    for key in location_keys
                )
                + ")))"
            )
            values.extend(
                [f"%{sample_location}%"] * (len(location_keys) + 2)
            )

        year_min = _number(filters.get("year_min"))
        year_max = _number(filters.get("year_max"))
        if year_min is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM sample s WHERE s.pa_id=p.id AND "
                "CAST(json_extract(s.data, '$.aeg') AS REAL)>=?)"
            )
            values.append(year_min)
        if year_max is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM sample s WHERE s.pa_id=p.id AND "
                "CAST(json_extract(s.data, '$.aeg') AS REAL)<=?)"
            )
            values.append(year_max)

        def presence_clause(expression, requirement):
            if requirement not in {"yes", "no"}:
                return
            clauses.append(
                ("(" if requirement == "yes" else "NOT (")
                + expression + ")"
            )

        presence_clause(
            "p.cleaned_id IS NOT NULL AND trim(p.cleaned_id)<>''",
            filters.get("egt_link"),
        )
        presence_clause(
            "p.sarv_id IS NOT NULL AND trim(p.sarv_id)<>''",
            filters.get("sarv_link"),
        )
        presence_clause(
            "EXISTS (SELECT 1 FROM core_box c WHERE c.pa_id=p.id AND "
            "trim(coalesce(json_extract(c.data, '$.viit_geoportaali'), ''))<>'')",
            filters.get("core_photo"),
        )
        presence_clause(
            "EXISTS (SELECT 1 FROM sample s WHERE s.pa_id=p.id AND ("
            "trim(coalesce(json_extract(s.data, '$.viit_geoportaali_foto1'), ''))<>'' "
            "OR trim(coalesce(json_extract(s.data, '$.viit_geoportaali_foto2'), ''))<>'' "
            "OR trim(coalesce(json_extract(s.data, '$.viit_geoportaali_foto3'), ''))<>''))",
            filters.get("sample_photo"),
        )
        for key, json_key in (
            ("thin_section", "ohik"),
            ("chemistry", "keemia"),
            ("mineralogy", "mineral"),
            ("granulometry", "granul"),
            ("spectral", "spektr"),
            ("carbonate", "karbon"),
        ):
            presence_clause(
                "EXISTS (SELECT 1 FROM sample s WHERE s.pa_id=p.id AND "
                f"trim(coalesce(json_extract(s.data, '$.{json_key}'), '')) "
                "NOT IN ('', '0'))",
                filters.get(key),
            )
        where = " AND ".join(clauses) if clauses else "1=1"
        # A short numeric query commonly matches hundreds of parent and child
        # records (box numbers, depths, years, etc.).  Rank exact public
        # identifiers and collar names before the general substring matches so
        # that the requested collar cannot disappear behind the result limit.
        query_text = _normalized(text)
        order_values = []
        if query_text:
            order = (
                " ORDER BY CASE "
                "WHEN qeoloog_norm(p.id)=? THEN 0 "
                "WHEN qeoloog_norm(p.number)=? THEN 1 "
                "WHEN qeoloog_norm(p.gb_id)=? THEN 2 "
                "WHEN qeoloog_norm(p.cleaned_id)=? THEN 3 "
                "WHEN qeoloog_norm(p.name)=? THEN 4 "
                "WHEN qeoloog_norm(trim(coalesce(p.name,'') || ' ' || "
                "coalesce(p.number,'')))=? THEN 5 ELSE 6 END, "
                "coalesce(p.name,p.number,p.id)"
            )
            order_values = [query_text] * 6
        else:
            order = " ORDER BY coalesce(p.name,p.number,p.id)"
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT p.* FROM pa p WHERE " + where
                + order + " LIMIT ?",
                (*values, *order_values, max(1, int(limit))),
            ).fetchall()
        result = []
        for row in rows:
            decoded = self._decoded(row)
            if tokens:
                parent_text = str(row["search_text"] or "")
                decoded["_maaru_search_scope"] = (
                    "overview"
                    if all(token in parent_text for token in tokens)
                    else "related"
                )
            result.append(decoded)
        return result


def detail_url(identifier):
    return MAARU_DETAIL_URL.format(id=str(identifier))


def geological_units(rows):
    """Convert MaRu geological descriptions to Qeoloog profile fields."""
    result = []
    for row in rows or ():
        top = _number(row.get("sygavus"))
        thickness = _number(row.get("d"))
        if top is None or thickness is None:
            continue
        # The historical database uses a negative D value for the deepest
        # unit when drilling ended inside that unit.  Its absolute value is
        # still the described interval thickness; the sign means that the
        # lower stratigraphic boundary was not reached.
        unpenetrated = thickness < 0
        thickness = abs(thickness)
        index = row.get("strat_indeks") or ""
        category = _index_category(index)
        result.append({
            **row,
            "z_suht_ylemine": top,
            "z_suht_alumine": top + thickness,
            "indeks": index,
            "stratigraafia_indeks": index,
            "litoloogia": row.get("litoloogia") or "",
            "kirjeldus": row.get("strat_kirjeldus") or "",
            "klassif_yksus_kood": category,
            "_qeoloog_unpenetrated": unpenetrated,
            "_qeoloog_source": "MaRu",
        })
    return result


def core_boxes(rows):
    result = []
    ordered = list(rows or ())
    for index, row in enumerate(ordered):
        top = _number(row.get("algus"))
        bottom = _number(row.get("lõpp"))
        if bottom is None and index + 1 < len(ordered):
            bottom = _number(ordered[index + 1].get("algus"))
        invalid_bottom = (
            top is not None and bottom is not None and bottom < top
        )
        raw_bottom = bottom if invalid_bottom else None
        if invalid_bottom:
            # Do not draw an inverted box interval.  Preserve the upstream
            # value for the detail/correction UI and collapse the rendered
            # interval to its known top until the local correction is made.
            bottom = top
        image_url = _public_url(row.get("viit_geoportaali"))
        result.append({
            **row,
            "globalid": f"MAARU-{row.get('pa_id')}-{row.get('id')}",
            "kast_nr": row.get("nr"),
            "z_suht_ylemine": top,
            "z_suht_alumine": bottom,
            "diameeter": _number(row.get("südamiku diameeter")),
            "staatus": row.get("seisukord") or row.get("hoidla"),
            "kirjeldus": row.get("märkused") or "",
            "_qeoloog_invalid_bottom": invalid_bottom,
            "_qeoloog_invalid_bottom_raw": raw_bottom,
            "_url": image_url,
            "_urls": [image_url] if image_url else [],
            "_qeoloog_source": "MaRu",
        })
    return result


def samples(rows):
    result = []
    for row in rows or ():
        depth = _number(row.get("sygavus"))
        photo_urls = [
            _public_url(row.get(f"viit_geoportaali_foto{number}"))
            for number in range(1, 4)
            if str(row.get(f"viit_geoportaali_foto{number}") or "").strip()
        ]
        result.append({
            **row,
            "proov_tahis_alg": row.get("number") or row.get("kasipala_id"),
            "proov_tyyp": row.get("kivim"),
            "z_suht_ylemine": depth,
            "z_suht_alumine": depth,
            "eesmark": row.get("strat"),
            "staatus": row.get("hoidla"),
            "_url": photo_urls[0] if photo_urls else "",
            "_urls": photo_urls,
            "_label": str(row.get("number") or row.get("kasipala_id") or ""),
            "_location_label": " — ".join(
                str(value) for value in (
                    row.get("pa_nr"), row.get("pa_nimetus"),
                ) if value not in (None, "", "-")
            ) or str(row.get("pa_id") or ""),
            "_location_url": (
                detail_url(row.get("pa_id")) if row.get("pa_id") else ""
            ),
            "_qeoloog_source": "MaRu",
        })
    return result


def image_attachments(core_rows, sample_rows, parent=None):
    """Return richly described MaRu image rows for the attachments view."""
    result = []
    parent = dict(parent or {})
    collar_z = _number(parent.get("z"))
    for row in core_rows or ():
        url = _public_url(row.get("viit_geoportaali"))
        if url:
            result.append({
                **row,
                "source": "MaRu",
                "kind": "core_photo",
                "type": "Puursüdamikukasti foto",
                "name": f"Kast {row.get('nr') or row.get('id')}",
                "url": url,
                "source_id": row.get("id"),
                "depth": row.get("algus"),
                "depth_end": row.get("lõpp"),
                "absolute_z": (
                    collar_z - _number(row.get("algus"))
                    if collar_z is not None and _number(row.get("algus")) is not None
                    else None
                ),
                "height_reference": "MaRu lähteandmete kõrgussüsteem (määramata)",
            })
    for row in sample_rows or ():
        for number in range(1, 4):
            url = _public_url(row.get(f"viit_geoportaali_foto{number}"))
            if url:
                result.append({
                    **row,
                    "source": "MaRu",
                    "kind": "sample_photo",
                    "type": "Proovi foto",
                    "name": str(row.get("number") or row.get("kasipala_id")),
                    "url": url,
                    "source_id": row.get("kasipala_id"),
                    "photo_number": number,
                    "depth": row.get("sygavus"),
                    "absolute_z": (
                        collar_z - _number(row.get("sygavus"))
                        if collar_z is not None and _number(row.get("sygavus")) is not None
                        else None
                    ),
                    "height_reference": "MaRu lähteandmete kõrgussüsteem (määramata)",
                    "index": row.get("strat"),
                    "lithology": row.get("kivim"),
                })
    return result
