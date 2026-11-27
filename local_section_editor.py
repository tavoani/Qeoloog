"""Edit a measured local log without changing its linked database records."""

import csv
from copy import deepcopy
from math import isfinite
from pathlib import Path
from uuid import uuid4

from qgis.PyQt.QtCore import QEventLoop, Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .section_workspace import SectionWorkspaceError


TOP = "z_suht_ylemine"
BOTTOM = "z_suht_alumine"
COLLECTIONS = {
    "units": (
        (TOP, "Algus (m)", "top"),
        (BOTTOM, "Lõpp (m)", "bottom"),
        ("litoloogia", "Litoloogia", "lithology"),
        ("indeks", "Indeks", "index"),
        ("contact", "Kontakt", "contact"),
        ("grain_size", "Terasuurus", "grain_size"),
        ("note", "Märkus", "note"),
    ),
    "isotopes": (
        ("depth", "Asend (m)", "position"),
        ("analyte", "Isotoop / näitaja", "analyte"),
        ("value", "Väärtus", "value"),
        ("unit", "Ühik", "unit"),
        ("reference", "Võrdlusskaala", "reference"),
        ("uncertainty", "Määramatus (±)", "uncertainty"),
        ("sample_ref", "Proovi viide", "sample_ref"),
        ("source_ref", "Allikaviide", "source_ref"),
        ("gap_before", "Katkesta joon enne", "gap_before"),
    ),
    "biofinds": (
        ("depth", "Asend (m)", "position"),
        ("taxon", "Takson", "taxon"),
        ("zone", "Biotsoon", "zone"),
        ("sample_ref", "Proovi viide", "sample_ref"),
        ("source_ref", "Allikaviide", "source_ref"),
        ("note", "Märkus", "note"),
    ),
    "biozones": (
        (TOP, "Algus (m)", "top"), (BOTTOM, "Lõpp (m)", "bottom"),
        ("name", "Nimi", "name"), ("scheme", "Skeem", "scheme"),
        ("source_ref", "Allikaviide", "source_ref"),
    ),
}
COLLECTIONS["stages"] = COLLECTIONS["biozones"]
TAB_NAMES = {
    "units": "Kihid", "isotopes": "Isotoobid",
    "biofinds": "Biotsoonide leiupunktid", "biozones": "Tõlgendatud biotsoonide ulatus",
    "stages": "Lademed",
}
CSV_REQUIRED = {
    "units": {TOP, BOTTOM},
    "isotopes": {"depth", "analyte", "value", "unit"},
    "biofinds": {"depth"},
    "biozones": {TOP, BOTTOM, "name"},
    "stages": {TOP, BOTTOM, "name"},
}
ENGLISH = {
    "Kohalik tulp": "Local log",
    "Kohalik": "Local",
    "Paljand": "Outcrop",
    "Objekti tüüp": "Site type",
    "Mõõtetelg": "Measurement axis",
    "Sügavus ülalt alla": "Depth, positive down",
    "Mõõdetud kõrgus alt üles": "Measured height, positive up",
    "Idakoordinaat X (EPSG:3301)": "Easting X (EPSG:3301)",
    "Põhjakoordinaat Y (EPSG:3301)": "Northing Y (EPSG:3301)",
    "Nullpunkti absoluutkõrgus (m)": "Absolute elevation of zero (m)",
    "Vertikaaltegur (0–1)": "Vertical factor (0–1)",
    "Mõõdetud ulatus (m)": "Measured length (m)",
    "Vali kaardilt nullpunkt": "Pick zero point on map",
    "Joonista paljandi joon": "Draw outcrop trace",
    "Eemalda paljandi joon": "Remove outcrop trace",
    "Joonel punkte: {count}": "Trace vertices: {count}",
    "Allika kirje": "Source record",
    "Jäta tühjaks, et kasutada andmete suurimat asendit.": "Leave blank to use the greatest position in the data.",
    "Lähtekõrgus peab olema samas kõrgussüsteemis kui koondläbilõige. Mõõtmiste vertikaaltegur on 1 ainult siis, kui mõõtetelg on vertikaalne. Teadmata tegur jäta tühjaks.": "The anchor height must use the same vertical datum as the combined section. Set the factor to 1 only for a vertical measurement axis. Leave an unknown factor blank.",
    "Kõik asendid kasvavad nullist valitud mõõtesuunas.": "All positions increase from zero in the selected measurement direction.",
    "Algus (m)": "From (m)",
    "Lõpp (m)": "To (m)",
    "Asend (m)": "Position (m)",
    "Kontakt": "Contact",
    "Terasuurus": "Grain size",
    "Isotoobid": "Isotopes",
    "Isotoop / näitaja": "Isotope / analyte",
    "Võrdlusskaala": "Reference scale",
    "Määramatus (±)": "Uncertainty (±)",
    "Proovi viide": "Sample reference",
    "Allikaviide": "Source reference",
    "Katkesta joon enne": "Break line before",
    "Biotsoonid": "Biozones",
    "Biotsoonide leiupunktid": "Biozone occurrence points",
    "Tõlgendatud biotsoonide ulatus": "Interpreted biozone ranges",
    "Takson": "Taxon",
    "Biotsoon": "Biozone",
    "Lademed": "Stages",
    "Skeem": "Scheme",
    "Lisa rida": "Add row",
    "Eemalda valitud": "Remove selected",
    "Impordi CSV": "Import CSV",
    "CSV päis: {headers}": "CSV header: {headers}",
    "Sobivad terasuuruse nimetused või läbimõõt millimeetrites.": "Enter a grain-size class or a diameter in millimetres.",
    "Valikud: sharp, gradational, erosional, unconformity, uncertain.": "Values: sharp, gradational, erosional, unconformity, uncertain.",
    "Sisesta 1 või jah, et eelmist punkti sellega ei ühendataks.": "Enter 1 or yes to break the connection from the preceding point.",
    "Puuduv mõõtetulemus jäta tühjaks; joon katkeb selles kohas.": "Leave a missing measurement blank; the line breaks at that position.",
    "Lisa fail…": "Add file…",
    "Vali failid": "Select files",
    "Paranda enne salvestamist": "Correct before saving",
    "Import ebaõnnestus": "Import failed",
    "CSV päis puudub või selles on korduvad väljad.": "CSV header is missing or contains duplicate fields.",
    "CSV päisest puuduvad väljad: {fields}.": "Missing CSV columns: {fields}.",
    "CSV real on päisest rohkem välju.": "A CSV row has more values than the header.",
    "Sisesta tulba nimi.": "Enter a log name.",
    "Sisesta mõlemad koordinaadid või jäta mõlemad tühjaks.": "Enter both coordinates or leave both blank.",
    "{field}: see väärtus peab olema lõplik arv.": "{field}: this value must be a finite number.",
    "{field}: see väärtus ei tohi olla negatiivne.": "{field}: this value cannot be negative.",
    "Vertikaaltegur peab olema vahemikus 0–1.": "Vertical factor must be in the range 0–1.",
    "Paljandi joonel peab olema vähemalt kaks eri punkti.": "An outcrop trace needs at least two distinct points.",
    "Paljandi joon sisaldab vigast punkti.": "The outcrop trace contains an invalid vertex.",
    "Vahemiku lõpp peab olema algusest suurem.": "An interval must end after it starts.",
    "Vahemikud kattuvad.": "Intervals overlap.",
    "Puudub kohustuslik väärtus: {field}.": "Missing required value: {field}.",
    "Andmed ulatuvad määratud mõõdetud ulatusest kaugemale.": "Data exceed the stated measured length.",
    "Katkestuse väärtus peab olema 0 või 1, ei või jah.": "The break value must be 0 or 1, no or yes.",
    "{tab}, rida {line}: {detail}": "{tab}, row {line}: {detail}",
    "Kaardilt valimine ebaõnnestus": "Map selection failed",
}


class SectionInputError(ValueError):
    """Short, localizable editor validation error."""

    def __init__(self, message, *, tab=None, line=None, **values):
        self.message = message
        self.values = values
        self.tab = tab
        self.line = line
        super().__init__(message.format(**values))


def _str(value):
    return "" if value is None else str(value).strip()


def _number(value, label, *, required=False, nonnegative=False):
    text = _str(value)
    if text.casefold() in {"", "null", "<null>", "none"}:
        if required:
            raise SectionInputError("Puudub kohustuslik väärtus: {field}.", field=label)
        return None
    try:
        parsed = float(text.replace(",", "."))
    except (TypeError, ValueError) as error:
        raise SectionInputError("{field}: see väärtus peab olema lõplik arv.", field=label) from error
    if not isfinite(parsed):
        raise SectionInputError("{field}: see väärtus peab olema lõplik arv.", field=label)
    if nonnegative and parsed < 0:
        raise SectionInputError("{field}: see väärtus ei tohi olla negatiivne.", field=label)
    return parsed


def _boolean(value):
    if _str(value).casefold() in {"", "0", "false", "no", "ei"}:
        return False
    if _str(value).casefold() in {"1", "true", "yes", "jah"}:
        return True
    raise SectionInputError("Katkestuse väärtus peab olema 0 või 1, ei või jah.")


def normalized_rows(collection, rows):
    """Validate measured rows without guessing values or filling gaps."""
    converted = []
    previous = {}
    seen_ids = set()
    columns = COLLECTIONS[collection]
    for line, row in enumerate(rows, 1):
        if not any(_str(row.get(key)) for key, _label, _header in columns):
            continue
        cells = deepcopy(row)
        identifier = _str(cells.get("id"))
        if not identifier or identifier in seen_ids:
            identifier = str(uuid4())
        cells["id"] = identifier
        seen_ids.add(identifier)
        try:
            if collection == "isotopes":
                for key, label, required, natural in (
                    ("depth", "Asend (m)", True, True),
                    ("value", "Väärtus", False, False),
                    ("uncertainty", "Määramatus (±)", False, True),
                ):
                    cells[key] = _number(cells.get(key), label, required=required, nonnegative=natural)
                for key, label in (("analyte", "Isotoop / näitaja"), ("unit", "Ühik")):
                    cells[key] = _str(cells.get(key))
                    if not cells[key]:
                        raise SectionInputError("Puudub kohustuslik väärtus: {field}.", field=label)
                cells["gap_before"] = _boolean(cells.get("gap_before"))
            elif collection == "biofinds":
                cells["depth"] = _number(
                    cells.get("depth"), "Asend (m)", required=True, nonnegative=True,
                )
                for key in ("taxon", "zone", "sample_ref", "source_ref", "note"):
                    cells[key] = _str(cells.get(key))
            else:
                start = cells[TOP] = _number(
                    cells.get(TOP), "Algus (m)", required=True, nonnegative=True,
                )
                end = cells[BOTTOM] = _number(
                    cells.get(BOTTOM), "Lõpp (m)", required=True, nonnegative=True,
                )
                if end <= start:
                    raise SectionInputError("Vahemiku lõpp peab olema algusest suurem.")
                if collection != "units" and not _str(cells.get("name")):
                    raise SectionInputError("Puudub kohustuslik väärtus: {field}.", field="Nimi")
                scheme = _str(cells.get("scheme")).casefold() if collection != "units" else ""
                previous.setdefault(scheme, []).append((start, end, line))
        except SectionInputError as error:
            raise SectionInputError(error.message, tab=collection, line=line, **error.values) from error
        converted.append(cells)
    for positions in previous.values():
        ordered = sorted(positions)
        for first, second in zip(ordered, ordered[1:]):
            if second[0] < first[1] - 1e-9:
                raise SectionInputError("Vahemikud kattuvad.", tab=collection, line=second[2])
    key = "depth" if collection in {"isotopes", "biofinds"} else TOP
    return sorted(converted, key=lambda row: row[key])


def read_section_csv(path, collection):
    """Read UTF-8 CSV for one local track; import never writes the source file."""
    columns = COLLECTIONS[collection]
    lookup = {
        name.casefold(): key
        for key, label, english in columns
        for name in (key, english, label, label.removesuffix(" (m)"))
    }
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(32768)
        stream.seek(0)
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        except csv.Error:
            header = sample.splitlines()[0] if sample.splitlines() else ""
            delimiter = max((",", ";", "\t"), key=header.count)
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        names = next(reader, [])
        mapped = [lookup.get(value.strip().casefold()) for value in names]
        known = [key for key in mapped if key]
        if not names or not known or len(known) != len(set(known)):
            raise SectionInputError("CSV päis puudub või selles on korduvad väljad.")
        missing = CSV_REQUIRED[collection].difference(known)
        if missing:
            show_names = ", ".join(header for key, _title, header in columns if key in missing)
            raise SectionInputError("CSV päisest puuduvad väljad: {fields}.", fields=show_names)
        rows = []
        for values in reader:
            if len(values) > len(mapped):
                raise SectionInputError("CSV real on päisest rohkem välju.", tab=collection, line=reader.line_num)
            rows.append({key: value.strip() for key, value in zip(mapped, values) if key})
    return normalized_rows(collection, rows)


def _trace_points(points):
    result = []
    for point in points or ():
        try:
            x, y = point
            xy = [_number(x, "X", required=True), _number(y, "Y", required=True)]
        except (TypeError, ValueError) as error:
            raise SectionInputError("Paljandi joon sisaldab vigast punkti.") from error
        if not result or xy != result[-1]:
            result.append(xy)
    if result and len(result) < 2:
        raise SectionInputError("Paljandi joonel peab olema vähemalt kaks eri punkti.")
    return result


def normalized_section(draft):
    """Normalize editable fields, retaining provenance and unrelated tracks."""
    record = deepcopy(draft)
    local_id = _str(draft.get("id")) if draft.get("role") == "local_section" else ""
    local_id = local_id or str(uuid4())
    name = _str(record.get("name"))
    if not name:
        raise SectionInputError("Sisesta tulba nimi.")
    x = _number(record.get("x"), "Idakoordinaat X (EPSG:3301)")
    y = _number(record.get("y"), "Põhjakoordinaat Y (EPSG:3301)")
    if (x is None) != (y is None):
        raise SectionInputError("Sisesta mõlemad koordinaadid või jäta mõlemad tühjaks.")
    elevation = _number(record.get("elevation"), "Nullpunkti absoluutkõrgus (m)")
    factor = _number(record.get("vertical_factor"), "Vertikaaltegur (0–1)", nonnegative=True)
    if factor is not None and factor > 1:
        raise SectionInputError("Vertikaaltegur peab olema vahemikus 0–1.")
    depth = _number(record.get("depth"), "Mõõdetud ulatus (m)", nonnegative=True)
    extent = 0
    for collection in COLLECTIONS:
        rows = record[collection] = normalized_rows(collection, record.get(collection) or [])
        extent_key = "depth" if collection in {"isotopes", "biofinds"} else BOTTOM
        extent = max(extent, max((r[extent_key] for r in rows), default=0))
    if depth is not None and depth < extent - 1e-9:
        raise SectionInputError("Andmed ulatuvad määratud mõõdetud ulatusest kaugemale.")
    record.update(
        name=name, role="local_section", source="Kohalik", id=local_id,
        key=f"local:{local_id}", kind="outcrop" if record.get("kind") == "outcrop" else "borehole",
        axis="height" if record.get("axis") == "height" else "depth", x=x, y=y,
        elevation=elevation, vertical_factor=factor, depth=extent if depth is None else depth,
        trace=_trace_points(record.get("trace")),
    )
    return record


class LocalSectionEditor(QDialog):
    def __init__(self, parent, plugin, draft=None, map_pick=None, add_attachment=None, map_pick_line=None):
        super().__init__(parent)
        self.plugin = plugin
        self.original = deepcopy(draft or {})
        self.map_pick = map_pick
        self.map_pick_line = map_pick_line
        self.add_attachment = add_attachment
        self.trace = self.original.get("trace") or []
        self.result_record = None
        self._make_ui()

    def t(self, text):
        if getattr(self.plugin, "language", "et") == "en":
            return ENGLISH[text] if text in ENGLISH else self.plugin.t(text)
        return self.plugin.t(text)

    def _make_ui(self):
        self.setWindowTitle(self.t("Kohalik tulp"))
        self.resize(900, 660)
        layout = QVBoxLayout(self)
        tabs = self.tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        general = QWidget()
        form = QFormLayout(general)
        tabs.addTab(general, self.t("Üldandmed"))
        self.inputs = {}
        self.kind = QComboBox()
        self.kind.addItem(self.t("Puurauk"), "borehole")
        self.kind.addItem(self.t("Paljand"), "outcrop")
        self.kind.setCurrentIndex(1 if self.original.get("kind") == "outcrop" else 0)
        self.axis = QComboBox()
        self.axis.addItem(self.t("Sügavus ülalt alla"), "depth")
        self.axis.addItem(self.t("Mõõdetud kõrgus alt üles"), "height")
        self.axis.setCurrentIndex(1 if self.original.get("axis") == "height" else 0)
        for key, label in (
            ("name", "Nimi"), ("x", "Idakoordinaat X (EPSG:3301)"),
            ("y", "Põhjakoordinaat Y (EPSG:3301)"),
            ("elevation", "Nullpunkti absoluutkõrgus (m)"),
            ("vertical_factor", "Vertikaaltegur (0–1)"), ("depth", "Mõõdetud ulatus (m)"),
        ):
            default = 1 if key == "vertical_factor" and self.axis.currentData() == "depth" else None
            field = self.inputs[key] = QLineEdit(_str(self.original.get(key, default)))
            form.addRow(self.t(label), field)
            if key == "name":
                form.addRow(self.t("Objekti tüüp"), self.kind)
                form.addRow(self.t("Mõõtetelg"), self.axis)
        self.inputs["depth"].setToolTip(self.t("Jäta tühjaks, et kasutada andmete suurimat asendit."))
        note = QLabel(self.t(
            "Lähtekõrgus peab olema samas kõrgussüsteemis kui koondläbilõige. "
            "Mõõtmiste vertikaaltegur on 1 ainult siis, kui mõõtetelg on vertikaalne. "
            "Teadmata tegur jäta tühjaks."
        ))
        note.setWordWrap(True)
        form.addRow(note)
        if self.map_pick:
            button = QPushButton(self.t("Vali kaardilt nullpunkt"))
            button.clicked.connect(lambda: self._pick(self.map_pick, self._picked_point))
            form.addRow(button)
        self.trace_label = QLabel()
        form.addRow(self.trace_label)
        trace_buttons = QHBoxLayout()
        if self.map_pick_line:
            self.trace_pick = QPushButton(self.t("Joonista paljandi joon"))
            self.trace_pick.clicked.connect(lambda: self._pick(self.map_pick_line, self._picked_trace))
            trace_buttons.addWidget(self.trace_pick)
        else:
            self.trace_pick = None
        self.trace_remove = QPushButton(self.t("Eemalda paljandi joon"))
        self.trace_remove.clicked.connect(lambda: self._picked_trace([]))
        trace_buttons.addWidget(self.trace_remove)
        trace_buttons.addStretch()
        form.addRow(trace_buttons)
        self._update_trace_controls()
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.axis.currentIndexChanged.connect(self._axis_changed)

        reference = self.original.get("source_ref")
        if isinstance(reference, dict):
            reference = " · ".join(_str(value) for value in reference.values() if isinstance(value, (str, int)))
        if reference:
            source_label = QLabel(_str(reference))
            source_label.setTextFormat(Qt.TextFormat.PlainText)
            source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            source_label.setWordWrap(True)
            form.addRow(self.t("Allika kirje"), source_label)

        self.tables = {}
        self.track_pages = {}
        for collection, spec in COLLECTIONS.items():
            page = self.track_pages[collection] = QWidget()
            tabs.addTab(page, self.t(TAB_NAMES[collection]))
            page_layout = QVBoxLayout(page)
            track_hint = QLabel(self.t("Kõik asendid kasvavad nullist valitud mõõtesuunas."))
            track_hint.setWordWrap(True)
            page_layout.addWidget(track_hint)
            grid = self.tables[collection] = QTableWidget(0, len(spec))
            grid.setHorizontalHeaderLabels([self.t(label) for _, label, _ in spec])
            grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            grid.horizontalHeader().setStretchLastSection(True)
            grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            page_layout.addWidget(grid, 1)
            for key, hint in (
                ("contact", "Valikud: sharp, gradational, erosional, unconformity, uncertain."),
                ("grain_size", "Sobivad terasuuruse nimetused või läbimõõt millimeetrites."),
                ("gap_before", "Sisesta 1 või jah, et eelmist punkti sellega ei ühendataks."),
                ("value", "Puuduv mõõtetulemus jäta tühjaks; joon katkeb selles kohas."),
            ):
                column = next((i for i, (field, *_rest) in enumerate(spec) if field == key), None)
                if column is not None:
                    grid.horizontalHeaderItem(column).setToolTip(self.t(hint))
            for record in self.original.get(collection) or []:
                self._append(collection, record)
            buttons = QHBoxLayout()
            for label, handler in (
                ("Lisa rida", self._add_blank),
                ("Eemalda valitud", self._remove_rows),
                ("Impordi CSV", self._import_csv),
            ):
                button = QPushButton(self.t(label))
                button.clicked.connect(lambda _, key=collection, call=handler: call(key))
                if label == "Impordi CSV":
                    button.setToolTip(self.t("CSV päis: {headers}").format(headers=", ".join(csv_key for _, _, csv_key in spec)))
                buttons.addWidget(button)
            buttons.addStretch()
            page_layout.addLayout(buttons)

        self.attachments = QListWidget()
        self.attachments.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        attachment_page = QWidget()
        tabs.addTab(attachment_page, self.t("Manused"))
        attachment_layout = QVBoxLayout(attachment_page)
        attachment_layout.addWidget(self.attachments)
        attachment_buttons = QHBoxLayout()
        attachment_layout.addLayout(attachment_buttons)
        for entry in self.original.get("attachments") or []:
            if isinstance(entry, str):
                entry = {"path": entry, "name": Path(entry).name}
            if isinstance(entry, dict) and entry.get("path"):
                self._append_attachment(entry)
        if self.add_attachment:
            add = QPushButton(self.t("Lisa fail…"))
            add.clicked.connect(self._choose_attachments)
            attachment_buttons.addWidget(add)
        remove = QPushButton(self.t("Eemalda valitud"))
        remove.clicked.connect(self._remove_attachments)
        attachment_buttons.addWidget(remove)
        attachment_buttons.addStretch()
        save_cancel = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_cancel.accepted.connect(self._accept)
        save_cancel.rejected.connect(self.reject)
        layout.addWidget(save_cancel)

    def _update_trace_controls(self):
        self.trace_label.setText(self.t("Joonel punkte: {count}").format(count=len(self.trace)))
        self.trace_remove.setEnabled(bool(self.trace))
        if self.trace_pick:
            self.trace_pick.setEnabled(self.kind.currentData() == "outcrop")

    def _kind_changed(self):
        self.axis.setCurrentIndex(1 if self.kind.currentData() == "outcrop" else 0)
        self._update_trace_controls()

    def _axis_changed(self):
        # Never assume a measured paljand height has vertical projection 1.
        self.inputs["vertical_factor"].clear()

    def _pick(self, picker, handler):
        # QDialog.exec() ends its loop on hide(); the wrapper keeps a separate
        # loop so the user can temporarily interact with the QGIS map.
        self.hide()
        self.setWindowModality(Qt.WindowModality.NonModal)

        def completed(*values):
            self.setWindowModality(Qt.WindowModality.WindowModal)
            self.show()
            self.raise_()
            self.activateWindow()
            if values:
                try:
                    handler(*values)
                except (TypeError, ValueError) as error:
                    QMessageBox.warning(self, self.t("Kaardilt valimine ebaõnnestus"), self._error_text(error))

        try:
            picker(completed)
        except (RuntimeError, TypeError, ValueError) as error:
            completed()
            QMessageBox.warning(self, self.t("Kaardilt valimine ebaõnnestus"), self._error_text(error))

    def _picked_point(self, x, y):
        self.inputs["x"].setText(f"{float(x):.3f}")
        self.inputs["y"].setText(f"{float(y):.3f}")

    def _picked_trace(self, points):
        self.trace = _trace_points(points)
        self._update_trace_controls()

    def _append(self, collection, record):
        if not isinstance(record, dict):
            return
        grid = self.tables[collection]
        i = grid.rowCount()
        grid.insertRow(i)
        for j, (key, _label, _header) in enumerate(COLLECTIONS[collection]):
            value = record.get(key)
            if key == "gap_before" and isinstance(value, bool):
                value = "1" if value else ""
            cell = QTableWidgetItem(_str(value))
            if j == 0:
                cell.setData(Qt.ItemDataRole.UserRole, record)
            grid.setItem(i, j, cell)

    def _add_blank(self, collection):
        self._append(collection, {})
        grid = self.tables[collection]
        grid.setCurrentCell(grid.rowCount() - 1, 0)
        grid.editItem(grid.currentItem())

    def _remove_rows(self, collection):
        grid = self.tables[collection]
        for row in sorted((index.row() for index in grid.selectionModel().selectedRows()), reverse=True):
            grid.removeRow(row)

    def _table_rows(self, collection):
        grid = self.tables[collection]
        for i in range(grid.rowCount()):
            first = grid.item(i, 0)
            item = dict(first.data(Qt.ItemDataRole.UserRole) or {}) if first else {}
            for j, (key, _label, _csv) in enumerate(COLLECTIONS[collection]):
                cell = grid.item(i, j)
                item[key] = cell.text().strip() if cell else ""
            yield item

    def _error_text(self, error):
        if not isinstance(error, SectionInputError):
            return str(error)
        values = dict(error.values)
        if "field" in values:
            values["field"] = self.t(values["field"])
        detail = self.t(error.message).format(**values)
        if error.line and error.tab:
            return self.t("{tab}, rida {line}: {detail}").format(
                tab=self.t(TAB_NAMES[error.tab]), line=error.line, detail=detail,
            )
        return detail

    def _import_csv(self, collection):
        path, _ = QFileDialog.getOpenFileName(self, self.t("Impordi CSV"), "", "CSV (*.csv *.tsv *.txt)")
        if not path:
            return
        try:
            incoming = read_section_csv(path, collection)
            # Test the merged table, but do not discard existing IDs or redraw
            # any of the user's table when validation fails.
            normalized_rows(collection, [*self._table_rows(collection), *incoming])
        except (csv.Error, OSError, UnicodeError, SectionInputError) as error:
            QMessageBox.warning(self, self.t("Import ebaõnnestus"), self._error_text(error))
            return
        for record in incoming:
            self._append(collection, record)

    def _append_attachment(self, entry):
        item = QListWidgetItem(_str(entry.get("name") or Path(entry.get("path", "")).name))
        item.setData(Qt.ItemDataRole.UserRole, entry)
        self.attachments.addItem(item)

    def _choose_attachments(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self.t("Vali failid"))
        existing = {self.attachments.item(i).data(Qt.ItemDataRole.UserRole).get("_pending") for i in range(self.attachments.count())}
        for value in paths:
            if value not in existing:
                self._append_attachment({"name": Path(value).name, "_pending": value})

    def _remove_attachments(self):
        for item in self.attachments.selectedItems():
            self.attachments.takeItem(self.attachments.row(item))

    def _accept(self):
        draft = {**self.original, **{key: edit.text() for key, edit in self.inputs.items()}}
        draft.update(kind=self.kind.currentData(), axis=self.axis.currentData(), trace=self.trace)
        for collection in COLLECTIONS:
            draft[collection] = list(self._table_rows(collection))
        try:
            record = normalized_section(draft)
            attachments = []
            for i in range(self.attachments.count()):
                item = self.attachments.item(i)
                entry = dict(item.data(Qt.ItemDataRole.UserRole))
                pending = entry.pop("_pending", None)
                if pending:
                    entry["path"] = str(self.add_attachment(Path(pending)))
                    item.setData(Qt.ItemDataRole.UserRole, entry)
                attachments.append(entry)
            record["attachments"] = attachments
        except (OSError, RuntimeError, ValueError, SectionWorkspaceError) as error:
            if getattr(error, "tab", None):
                self.tabs.setCurrentWidget(self.track_pages[error.tab])
                self.tables[error.tab].selectRow(error.line - 1)
            QMessageBox.warning(self, self.t("Paranda enne salvestamist"), self._error_text(error))
            return
        self.result_record = record
        self.accept()


def edit_local_section(parent, plugin, draft=None, map_pick=None, add_attachment=None, map_pick_line=None):
    """Return a new/edited local log, or None on cancel."""
    editor = LocalSectionEditor(parent, plugin, draft, map_pick, add_attachment, map_pick_line)
    loop = QEventLoop()
    editor.finished.connect(loop.quit)
    editor.destroyed.connect(loop.quit)
    editor.setWindowModality(Qt.WindowModality.WindowModal)
    editor.show()
    loop.exec()
    result = editor.result_record
    try:
        editor.deleteLater()
    except RuntimeError:
        # The workspace window can be destroyed during a map selection.
        pass
    return result
