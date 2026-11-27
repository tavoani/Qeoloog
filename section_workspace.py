"""Portable, local-only repository for Qeoloog cross-sections.

The GeoPackage can be opened in standard GIS software as an attribute table;
Qeoloog uses the JSON payload to retain the complete renderer-independent
section/log state. No application preferences or remote credentials live here.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tempfile
from uuid import uuid4


class SectionWorkspaceError(Exception):
    """The requested workspace operation could not be completed."""


_DATABASE = "qeoloog_sections.gpkg"
_ATTACHMENTS = "attachments"
_MANIFEST = "qeoloog-backup.json"
_APPLICATION_ID = 0x47504B47  # OGC GeoPackage "GPKG".
_SCHEMA_VERSION = 1
_UUID_RE = re.compile(r"^[0-9a-f]{32}$")

_SCHEMA = """
BEGIN IMMEDIATE;
PRAGMA application_id = 1196444487;
PRAGMA user_version = 10300;
CREATE TABLE gpkg_spatial_ref_sys (
    srs_name TEXT NOT NULL,
    srs_id INTEGER NOT NULL PRIMARY KEY,
    organization TEXT NOT NULL,
    organization_coordsys_id INTEGER NOT NULL,
    definition TEXT NOT NULL,
    description TEXT
);
INSERT INTO gpkg_spatial_ref_sys VALUES
    ('Undefined Cartesian', -1, 'NONE', -1, 'undefined', NULL),
    ('Undefined Geographic', 0, 'NONE', 0, 'undefined', NULL),
    ('WGS 84 geodetic', 4326, 'EPSG', 4326,
     'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]',
     NULL);
CREATE TABLE gpkg_contents (
    table_name TEXT NOT NULL PRIMARY KEY,
    data_type TEXT NOT NULL,
    identifier TEXT UNIQUE,
    description TEXT DEFAULT '',
    last_change DATETIME NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
    srs_id INTEGER,
    CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id)
        REFERENCES gpkg_spatial_ref_sys(srs_id)
);
-- Keep this catalog even with no geometry columns: GDAL expects it even
-- when the only user-facing GeoPackage layers are attribute tables.
CREATE TABLE gpkg_geometry_columns (
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    geometry_type_name TEXT NOT NULL,
    srs_id INTEGER NOT NULL,
    z TINYINT NOT NULL,
    m TINYINT NOT NULL,
    CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
    CONSTRAINT uk_gc_table_name UNIQUE (table_name),
    CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
    CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
);
CREATE TABLE qeoloog_workspace (
    version INTEGER NOT NULL,
    workspace_id TEXT NOT NULL
);
CREATE TABLE qeoloog_section_entries (
    fid INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('section', 'log')),
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    x_3301 REAL,
    y_3301 REAL,
    elevation REAL,
    updated_at DATETIME NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE (kind, id)
);
INSERT INTO gpkg_contents (table_name, data_type, identifier, description)
VALUES ('qeoloog_section_entries', 'attributes', 'Qeoloog – sections and logs',
        'Local Qeoloog records. X/Y coordinates, when recorded, are EPSG:3301.');
"""


def _utc_now():
    return datetime.now(timezone.utc)


def _iso_timestamp():
    return _utc_now().isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _finite_or_none(value):
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _is_link(path):
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


@contextmanager
def _connect(path, *, write=False):
    mode = "rw" if write else "ro"
    connection = sqlite3.connect(path.as_uri() + "?mode=" + mode, uri=True)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        # The context manages transaction commit/rollback; close explicitly.
        with connection:
            yield connection
    finally:
        connection.close()


def _workspace_database(folder):
    db = folder / _DATABASE
    if _is_link(db) or not db.is_file():
        raise SectionWorkspaceError(f"Workspace GeoPackage not found: {db}")
    return db


def _identity(path):
    with _connect(path) as connection:
        (application_id,) = connection.execute("PRAGMA application_id").fetchone()
        if application_id != _APPLICATION_ID:
            raise SectionWorkspaceError(f"Not a Qeoloog workspace GeoPackage: {path}")
        rows = connection.execute(
            "SELECT version, workspace_id FROM qeoloog_workspace LIMIT 2"
        ).fetchall()
        if len(rows) != 1 or rows[0][0] != _SCHEMA_VERSION:
            raise SectionWorkspaceError(f"Unsupported Qeoloog workspace schema: {path}")
        workspace_id = rows[0][1]
        if not isinstance(workspace_id, str) or not _UUID_RE.fullmatch(workspace_id):
            raise SectionWorkspaceError(f"Invalid Qeoloog workspace identifier: {path}")
        # Also check the required data table, not just the workspace signature.
        connection.execute(
            "SELECT fid, kind, id, name, x_3301, y_3301, elevation, updated_at, payload_json "
            "FROM qeoloog_section_entries LIMIT 0"
        )
        return workspace_id


def _artifact_files(folder):
    """Yield only managed data, rejecting links, sockets and other special files."""
    yield _workspace_database(folder)
    attachments = folder / _ATTACHMENTS
    if _is_link(attachments) or (attachments.exists() and not attachments.is_dir()):
        raise SectionWorkspaceError(f"Invalid attachments directory: {attachments}")
    if not attachments.exists():
        return

    def walk(directory):
        for path in sorted(directory.iterdir()):
            if _is_link(path):
                raise SectionWorkspaceError(f"Symbolic links are not supported: {path}")
            if path.name.startswith(".upload-") and path.is_file():
                continue  # Not referenced until the atomic attachment rename.
            if path.is_dir():
                yield from walk(path)
            elif path.is_file():
                yield path
            else:
                raise SectionWorkspaceError(f"Invalid attachment: {path}")

    yield from walk(attachments)


def _fingerprints(folder):
    result = {}
    for path in _artifact_files(folder):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        result[path.relative_to(folder).as_posix()] = digest.hexdigest()
    return result


def _load_manifest(folder):
    path = folder / _MANIFEST
    if _is_link(path) or not path.is_file():
        raise SectionWorkspaceError(f"Not a complete Qeoloog backup: {folder}")
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = folder / (_DATABASE + suffix)
        if sidecar.exists() or _is_link(sidecar):
            raise SectionWorkspaceError(f"Backup is not a standalone database: {folder}")
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict) or manifest.get("version") != _SCHEMA_VERSION:
        raise SectionWorkspaceError(f"Unsupported Qeoloog backup format: {path}")
    return manifest


def _copy_workspace(source, target):
    """Use SQLite's online backup rather than copying a live database file."""
    db = _workspace_database(source)
    with _connect(db) as original:
        clone = sqlite3.connect(target / _DATABASE)
        try:
            original.backup(clone)
            # A WAL-mode source can leave the copied header in WAL mode.
            # Make the backup independently readable even on read-only media.
            if clone.execute("PRAGMA journal_mode = DELETE").fetchone() != ("delete",):
                raise SectionWorkspaceError(f"GeoPackage copy is not standalone: {db}")
            if clone.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise SectionWorkspaceError(f"GeoPackage copy failed integrity check: {db}")
        finally:
            clone.close()
    for attachment in _artifact_files(source):
        rel = attachment.relative_to(source)
        if rel == Path(_DATABASE):
            continue
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(attachment, destination, follow_symlinks=False)


class SectionWorkspace:
    """A directory selected by the user, independent of the QGIS profile."""

    def __init__(self, folder, workspace_id):
        self.folder = folder
        self.path = folder / _DATABASE
        self.workspace_id = workspace_id

    @classmethod
    def open(cls, path, *, create=False):
        """Open a directory, optionally creating a workspace when not present."""
        try:
            folder = Path(path).expanduser().resolve()
            if create:
                folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not folder.is_dir():
                raise SectionWorkspaceError(f"Workspace directory not found: {folder}")
            marker = folder / _MANIFEST
            if marker.exists() or _is_link(marker):
                raise SectionWorkspaceError("Restore the backup to a new directory before editing it.")
            db = folder / _DATABASE
            if create and not db.exists() and not _is_link(db):
                # Exclusive creation prevents accidentally replacing another
                # application/workspace file. Remove only files made here.
                with db.open("xb"):
                    pass
                try:
                    with _connect(db, write=True) as connection:
                        connection.executescript(_SCHEMA)
                        connection.execute(
                            "INSERT INTO qeoloog_workspace VALUES (?, ?)",
                            (_SCHEMA_VERSION, uuid4().hex),
                        )
                except BaseException:
                    db.unlink(missing_ok=True)
                    raise
            return cls(folder, _identity(_workspace_database(folder)))
        except (OSError, TypeError, ValueError, sqlite3.Error) as error:
            raise SectionWorkspaceError(f"Cannot open workspace: {error}") from error

    @contextmanager
    def connection(self, *, write=False):
        """Provide a checked transaction for another Qeoloog workspace table."""
        with _connect(_workspace_database(self.folder), write=write) as connection:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            stored = connection.execute(
                "SELECT workspace_id FROM qeoloog_workspace LIMIT 1"
            ).fetchone()
            if stored != (self.workspace_id,):
                raise SectionWorkspaceError("Workspace changed since it was opened.")
            yield connection

    def _list(self, kind):
        try:
            with _connect(_workspace_database(self.folder)) as connection:
                rows = connection.execute(
                    "SELECT id, name, updated_at FROM qeoloog_section_entries "
                    "WHERE kind = ? ORDER BY updated_at DESC, fid DESC",
                    (kind,),
                ).fetchall()
            return [{"id": key, "name": name, "updated_at": modified} for key, name, modified in rows]
        except (OSError, sqlite3.Error) as error:
            raise SectionWorkspaceError(f"Cannot list workspace {kind} records: {error}") from error

    @staticmethod
    def _prepare_entry(kind, data, key, timestamp):
        if not isinstance(data, dict):
            raise SectionWorkspaceError(f"Expected a dictionary for {kind} data.")
        key = uuid4().hex if key is None else str(key)
        if not key:
            raise SectionWorkspaceError(f"Missing {kind} identifier.")
        name = str(data.get("name") or "").strip() or key
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return (kind, key, name, _finite_or_none(data.get("x")),
                _finite_or_none(data.get("y")), _finite_or_none(data.get("elevation")),
                timestamp, payload)

    def _save_entries(self, entries):
        try:
            timestamp = _iso_timestamp()
            prepared = [self._prepare_entry(kind, payload, key, timestamp)
                        for kind, payload, key in entries]
            with _connect(_workspace_database(self.folder), write=True) as connection:
                connection.executemany(
                    "INSERT INTO qeoloog_section_entries "
                    "(kind, id, name, x_3301, y_3301, elevation, updated_at, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(kind,id) DO UPDATE SET "
                    "name=excluded.name, x_3301=excluded.x_3301, y_3301=excluded.y_3301, "
                    "elevation=excluded.elevation, updated_at=excluded.updated_at, "
                    "payload_json=excluded.payload_json", prepared,
                )
                connection.execute(
                    "UPDATE gpkg_contents SET last_change = ? "
                    "WHERE table_name = 'qeoloog_section_entries'",
                    (timestamp,),
                )
            return tuple(entry[1] for entry in prepared)
        except (ValueError, TypeError, OSError, sqlite3.Error) as error:
            raise SectionWorkspaceError(f"Cannot save workspace record: {error}") from error

    def _save(self, kind, data, key=None):
        return self._save_entries(((kind, data, key),))[0]

    def save_log_and_section(self, log, log_id, section, section_id):
        """Commit the reusable log and its current placement in one transaction."""
        return self._save_entries((
            ("log", log, log_id), ("section", section, section_id),
        ))

    def _load(self, kind, key):
        try:
            with _connect(_workspace_database(self.folder)) as connection:
                record = connection.execute(
                    "SELECT payload_json FROM qeoloog_section_entries WHERE kind = ? AND id = ?",
                    (kind, str(key)),
                ).fetchone()
            if record is None:
                raise SectionWorkspaceError(f"Workspace {kind} not found: {key}")
            result = json.loads(record[0])
            if not isinstance(result, dict):
                raise SectionWorkspaceError(f"Invalid {kind} record: {key}")
            return result
        except (TypeError, ValueError, OSError, sqlite3.Error) as error:
            raise SectionWorkspaceError(f"Cannot read workspace {kind} record: {error}") from error

    def list_sections(self):
        return self._list("section")

    def save_section(self, state, section_id=None):
        return self._save("section", state, section_id)

    def load_section(self, section_id):
        return self._load("section", section_id)

    def list_logs(self):
        return self._list("log")

    def save_log(self, snapshot, log_id=None):
        return self._save("log", snapshot, log_id)

    def load_log(self, log_id):
        return self._load("log", log_id)

    def add_attachment(self, source):
        """Copy a regular file and return its portable workspace-relative path."""
        try:
            source = Path(source).expanduser()
            if _is_link(source) or not source.is_file():
                raise SectionWorkspaceError(f"Attachment is not a regular file: {source}")
            root = self.folder / _ATTACHMENTS
            if _is_link(root):
                raise SectionWorkspaceError(f"Invalid attachments directory: {root}")
            root.mkdir(mode=0o700, exist_ok=True)
            # UUID prefix prevents collisions, and avoids platform-reserved names.
            name = re.sub(r"[^\w.-]", "_", source.name, flags=re.ASCII)
            target = root / (uuid4().hex + "-" + name[-110:])
            with tempfile.NamedTemporaryFile(dir=root, delete=False, prefix=".upload-") as handle:
                staged = Path(handle.name)
                try:
                    with source.open("rb") as original:
                        shutil.copyfileobj(original, handle)
                    handle.flush()
                    # Close first (needed for renames on Windows).
                    handle.close()
                    staged.rename(target)
                finally:
                    staged.unlink(missing_ok=True)
            return target.relative_to(self.folder).as_posix()
        except (OSError, TypeError, ValueError) as error:
            raise SectionWorkspaceError(f"Cannot import attachment: {error}") from error

    def attachment_path(self, relative):
        """Resolve one managed attachment without following directory links."""
        if not isinstance(relative, str) or "\\" in relative:
            raise SectionWorkspaceError("Invalid workspace attachment reference.")
        path = PurePosixPath(relative)
        if (len(path.parts) < 2 or path.parts[0] != _ATTACHMENTS
                or any(part in {"..", "."} or ":" in part for part in path.parts)):
            raise SectionWorkspaceError(f"Invalid workspace attachment reference: {relative}")
        resolved = self.folder
        for part in path.parts:
            resolved /= part
            if _is_link(resolved):
                raise SectionWorkspaceError(f"Symbolic links are not supported: {resolved}")
        if not resolved.is_file():
            raise SectionWorkspaceError(f"Attachment not found: {resolved}")
        return resolved

    def backup(self, destination, *, keep=None):
        """Create and verify a complete, timestamped backup before publishing it."""
        try:
            if keep is not None and (type(keep) is not int or keep < 1):
                raise SectionWorkspaceError("Keep at least one verified backup.")
            base = Path(destination).expanduser().resolve()
            if base == self.folder or self.folder in base.parents:
                raise SectionWorkspaceError("Choose a backup directory outside the working directory.")
            base.mkdir(mode=0o700, parents=True, exist_ok=True)
            prefix = f"qeoloog-sections-{self.workspace_id}-"
            stamp = _utc_now().strftime("%Y%m%dT%H%M%S%fZ")
            backup_path = base / (prefix + stamp + "-" + uuid4().hex[:8])
            stage = Path(tempfile.mkdtemp(prefix=".qeoloog-copy-", dir=base))
            try:
                _copy_workspace(self.folder, stage)
                workspace_id = _identity(_workspace_database(stage))
                if workspace_id != self.workspace_id:
                    raise SectionWorkspaceError("Workspace changed since it was opened.")
                manifest = {
                    "version": _SCHEMA_VERSION,
                    "workspace_id": workspace_id,
                    "created_at": _iso_timestamp(),
                    "sha256": _fingerprints(stage),
                }
                (stage / _MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                stage.rename(backup_path)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
            if keep is not None:
                self._prune_backups(base, prefix, keep)
            return backup_path
        except (OSError, TypeError, ValueError, sqlite3.Error) as error:
            raise SectionWorkspaceError(f"Cannot back up workspace: {error}") from error

    def _prune_backups(self, base, prefix, keep):
        candidates = []
        date_name = re.compile(re.escape(prefix) + r"\d{8}T\d{12}Z-[0-9a-f]{8}$")
        for child in base.iterdir():
            if not date_name.fullmatch(child.name) or _is_link(child) or not child.is_dir():
                continue
            try:
                manifest = _load_manifest(child)
                only_expected = {entry.name for entry in child.iterdir()} <= {
                    _DATABASE, _MANIFEST, _ATTACHMENTS,
                }
                if only_expected and manifest.get("workspace_id") == self.workspace_id:
                    candidates.append((child, manifest.get("sha256")))
            except (OSError, ValueError, SectionWorkspaceError):
                # Never delete unrelated or damaged directories.
                continue
        # Only rehash backups that actually fall outside the retention limit.
        for old, expected in sorted(candidates, reverse=True)[keep:]:
            try:
                if expected == _fingerprints(old):
                    shutil.rmtree(old)
            except (OSError, SectionWorkspaceError):
                # A backup was published successfully; retention is best-effort.
                continue

    @classmethod
    def restore(cls, backup_folder, new_folder):
        """Verify the copy and restore it into a new, separately editable workspace."""
        try:
            source = Path(backup_folder).expanduser().resolve()
            requested = Path(new_folder).expanduser()
            if _is_link(requested):
                raise SectionWorkspaceError("Choose a new restore directory, not a symbolic link.")
            target = requested.resolve()
            if target == source or source in target.parents:
                raise SectionWorkspaceError("Choose a restore location outside the backup directory.")
            manifest = _load_manifest(source)
            if manifest.get("sha256") != _fingerprints(source):
                raise SectionWorkspaceError(f"Backup contents do not match the manifest: {source}")
            if manifest.get("workspace_id") != _identity(_workspace_database(source)):
                raise SectionWorkspaceError(f"Backup workspace identifier does not match: {source}")
            # mkdir with exist_ok=False never replaces a user's directory.
            target.mkdir(mode=0o700)
            try:
                _copy_workspace(source, target)
                expected_attachments = dict(manifest["sha256"])
                expected_attachments.pop(_DATABASE, None)
                copied_attachments = _fingerprints(target)
                copied_attachments.pop(_DATABASE, None)
                if copied_attachments != expected_attachments:
                    raise SectionWorkspaceError("Backup attachments changed during restore.")
                # Restores are new workspaces for backup retention, but all
                # record identifiers (and section-to-log links) are preserved.
                with _connect(target / _DATABASE, write=True) as connection:
                    connection.execute(
                        "UPDATE qeoloog_workspace SET workspace_id = ?", (uuid4().hex,)
                    )
                return cls.open(target)
            except BaseException:
                shutil.rmtree(target)
                raise
        except (OSError, TypeError, ValueError, sqlite3.Error) as error:
            raise SectionWorkspaceError(f"Cannot restore workspace: {error}") from error
