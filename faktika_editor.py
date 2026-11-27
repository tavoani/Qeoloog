"""Resizable, schema-driven editor for the authenticated Faktika service."""

from datetime import datetime
from math import hypot

from qgis.PyQt.QtCore import QDate, QDateTime, QTime, Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsProject

from .elevation_check import BK77, EH2000, ELLIPSOIDAL, UNKNOWN

from .faktika import (
    COMPOUND_INDEX,
    OBJECT_TYPES,
    PARENT_CORE_FIELDS,
    SEA_ONLY_PARENT_FIELDS,
    UNIT_CORE_FIELDS,
    UNIT_TYPES,
    allowed_unit_type_codes,
    coded_values,
    domain_for,
    editable_fields,
    field_map,
    finite_number,
    hierarchical_coded_values,
    new_guid,
    normalize_guid,
    template_defaults,
    unit_category_code,
    unit_defaults,
    validate_parent,
    validate_units,
)
from .models import PluginSettings


def _label(field):
    return str(field.get("alias") or field.get("name") or "")


def _format_value(field, value):
    if value in (None, ""):
        return ""
    if str(field.get("type")) == "esriFieldTypeDate":
        if isinstance(value, QDateTime):
            return value.toString("yyyy-MM-dd HH:mm")
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M")
        try:
            return datetime.fromtimestamp(float(value) / 1000).strftime(
                "%Y-%m-%d %H:%M"
            )
        except (OSError, OverflowError, TypeError, ValueError):
            return str(value)
    return str(value)


def _coerce(field, value):
    if value in (None, ""):
        return None
    field_type = str(field.get("type") or "")
    if field_type in {"esriFieldTypeInteger", "esriFieldTypeSmallInteger", "esriFieldTypeOID"}:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return value
    if field_type in {"esriFieldTypeDouble", "esriFieldTypeSingle"}:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if field_type == "esriFieldTypeDate":
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return int(datetime.strptime(text, pattern).timestamp() * 1000)
            except (OSError, ValueError):
                continue
    return value


def _set_combo_value(combo, value):
    for index in range(combo.count()):
        if str(combo.itemData(index)) == str(value):
            combo.setCurrentIndex(index)
            return
    if value not in (None, ""):
        combo.addItem(str(value), value)
        combo.setCurrentIndex(combo.count() - 1)


class WheelSafeComboBox(QComboBox):
    """Do not change a coded value while the surrounding form is scrolled."""

    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
            return
        event.ignore()


class WheelSafeDoubleSpinBox(QDoubleSpinBox):
    """Keep coordinates unchanged when the editor page is wheel-scrolled."""

    def wheelEvent(self, event):
        event.ignore()


class CompoundUnitSelector(QWidget):
    """Compact index + formation pair for one compound-unit boundary."""

    def __init__(
        self, index_options, index_value, formation_options, formation_value,
        translate=None, parent=None,
    ):
        super().__init__(parent)
        t = translate or (lambda text: text)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.index_combo = WheelSafeComboBox()
        self.index_combo.setToolTip(t("Indeks"))
        self.index_combo.addItem("", None)
        for code, label in index_options:
            self.index_combo.addItem(str(label), code)
        _set_combo_value(self.index_combo, index_value)
        self.formation_combo = WheelSafeComboBox()
        self.formation_combo.setToolTip(t("Kihistik"))
        self.formation_combo.addItem("", None)
        for code, label in formation_options:
            self.formation_combo.addItem(str(label), code)
        _set_combo_value(self.formation_combo, formation_value)
        for combo in (self.index_combo, self.formation_combo):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(8)
            layout.addWidget(combo, 1)

    def values(self):
        return self.index_combo.currentData(), self.formation_combo.currentData()


class NullableDateTimeEdit(QDateTimeEdit):
    """Readable ArcGIS milliseconds editor with an explicit empty state."""

    EMPTY = QDateTime(QDate(1900, 1, 1), QTime(0, 0))

    def __init__(self, value=None, parent=None):
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.setMinimumDateTime(self.EMPTY)
        self.setSpecialValueText("—")
        self.set_arcgis_value(value)

    def set_arcgis_value(self, value):
        if value in (None, ""):
            self.setDateTime(self.minimumDateTime())
            return
        if isinstance(value, QDateTime):
            parsed = QDateTime(value)
        elif isinstance(value, datetime):
            parsed = QDateTime.fromMSecsSinceEpoch(int(value.timestamp() * 1000))
        else:
            try:
                parsed = QDateTime.fromMSecsSinceEpoch(int(float(value)))
            except (TypeError, ValueError, OverflowError):
                parsed = QDateTime()
        self.setDateTime(parsed if parsed.isValid() else self.minimumDateTime())

    def arcgis_value(self):
        if self.dateTime() == self.minimumDateTime():
            return None
        return self.dateTime().toMSecsSinceEpoch()

    def wheelEvent(self, event):
        event.ignore()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.setDateTime(self.minimumDateTime())
            return
        super().keyPressEvent(event)


def _geological_length(rows):
    bottoms = [
        finite_number((row or {}).get("z_suht_alumine"))
        for row in rows or ()
    ]
    bottoms = [value for value in bottoms if value is not None]
    return max(bottoms) if bottoms else None


def _validation_text(plugin, message):
    if getattr(plugin, "language", "et") != "en":
        return str(message)
    text = str(message)
    replacements = (
        ("X, Y ja Z peavad olema lõplikud arvud.", "X, Y and Z must be finite numbers."),
        ("Objekti tüüp on kohustuslik.", "Object type is required."),
        ("Asukoha täpsusklass on kohustuslik.", "Location accuracy class is required."),
        ("Kande alus on kohustuslik.", "Source basis is required."),
        ("Rida ", "Row "),
        ("Read ", "Rows "),
        ("Z1 suht ja Z2 suht on kohustuslikud.", "relative Z1 and Z2 are required."),
        ("sügavusvahemik peab olema kasvav ja algama 0 m-st või sügavamalt.", "the depth interval must increase and start at or below 0 m."),
        ("alumine sügavus ületab objekti sügavuse.", "the lower depth exceeds the object depth."),
        ("geoloogilise üksuse tüüp on kohustuslik.", "geological-unit type is required."),
        ("indeks on kohustuslik.", "index is required."),
        ("indeks 0 pole lubatud.", "index 0 is not allowed."),
        ("pinnakatte genees on kohustuslik.", "cover genesis is required."),
        ("autor on kohustuslik.", "author is required."),
        ("alus on kohustuslik.", "source basis is required."),
        ("intervall kattub eelmise intervalliga.", "the interval overlaps the previous interval."),
        (" vahel on kirjeldamata vahemik.", " have an undescribed gap between them."),
        (" on identsed naaberüksused.", " are identical adjacent units."),
        ("stratigraafiline järjestus võib olla vastupidine.", "the stratigraphic order may be reversed."),
        ("üksuse kategooria liigub sügavusega tagasi ülespoole.", "the unit category moves backwards with depth."),
        (
            "üksuse kategooria ei tohi sügavusega tagasi ülespoole liikuda.",
            "the unit category must not move backwards with depth.",
        ),
        ("liitüksuse ülemine ja alumine indeks tuleb määrata koos.", "compound upper and lower indices must be set together."),
        ("liitüksuse ülemine ja alumine indeks on vales järjekorras.", "compound upper and lower indices are in the wrong order."),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    return text


class AttributeForm(QWidget):
    """Metadata-driven ArcGIS attribute form."""

    def __init__(
        self, metadata, values, *, field_names=None, subtype_code=None,
        excluded=(), option_overrides=None, multiline_fields=None, parent=None,
    ):
        super().__init__(parent)
        self.metadata = metadata or {}
        self.base = dict(values or {})
        self.subtype_code = subtype_code
        self.widgets = {}
        self.fields = {}
        self.option_overrides = option_overrides or {}
        self.multiline_fields = dict(multiline_fields or {})
        wanted = set(field_names or ()) if field_names is not None else None
        excluded = {str(value).casefold() for value in excluded}
        layout = QFormLayout(self)
        self.form_layout = layout
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for field in editable_fields(self.metadata):
            name = str(field.get("name"))
            if wanted is not None and name not in wanted:
                continue
            if name.casefold() in excluded:
                continue
            widget = self._widget(field, self.base.get(name))
            self.fields[name] = field
            self.widgets[name] = widget
            caption = _label(field)
            if not field.get("nullable", True):
                caption += " *"
            layout.addRow(caption, widget)

    def _widget(self, field, value):
        name = str(field.get("name"))
        options = self.option_overrides.get(name)
        if options is None:
            options = coded_values(domain_for(
                self.metadata, name, self.subtype_code,
            ))
        if options:
            widget = WheelSafeComboBox()
            if field.get("nullable", True):
                widget.addItem("", None)
            for code, label in options:
                widget.addItem(str(label), code)
            _set_combo_value(widget, value)
            return widget
        if str(field.get("type") or "") == "esriFieldTypeDate":
            return NullableDateTimeEdit(value)
        if name in self.multiline_fields:
            widget = QPlainTextEdit(_format_value(field, value))
            widget.setMinimumHeight(int(self.multiline_fields[name]))
            widget.setTabChangesFocus(True)
            return widget
        widget = QLineEdit(_format_value(field, value))
        length = field.get("length")
        if isinstance(length, int) and length > 0:
            widget.setMaxLength(length)
        return widget

    def values(self):
        result = dict(self.base)
        for name, widget in self.widgets.items():
            if isinstance(widget, QComboBox):
                value = widget.currentData()
            elif isinstance(widget, NullableDateTimeEdit):
                value = widget.arcgis_value()
            elif isinstance(widget, QPlainTextEdit):
                value = widget.toPlainText().strip()
            else:
                value = widget.text().strip()
            result[name] = _coerce(self.fields[name], value)
        return result


class RecordDialog(QDialog):
    def __init__(
        self, title, metadata, values, *, subtype_code=None, excluded=(),
        option_overrides=None, parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 720)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.form = AttributeForm(
            metadata, values, subtype_code=subtype_code,
            excluded=excluded, option_overrides=option_overrides,
        )
        scroll.setWidget(self.form)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return self.form.values()


class RelatedRecordsWidget(QWidget):
    """Add/edit/delete rows from one object-owned Faktika table."""

    def __init__(
        self, title, metadata, rows, columns, *, excluded=(),
        option_overrides=None, translate=None, parent=None,
    ):
        super().__init__(parent)
        self.title = title
        self.metadata = metadata or {}
        self.columns = tuple(columns)
        self.excluded = tuple(excluded)
        self.option_overrides = option_overrides or {}
        self.t = translate or (lambda text: text)
        self.rows = [dict(row, _existing=True, _dirty=False) for row in rows or []]
        self.deleted = []
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, len(self.columns))
        fields = field_map(self.metadata)
        self.table.setHorizontalHeaderLabels([
            _label(fields.get(name, {"name": name})) for name in self.columns
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda _index: self.edit_selected())
        layout.addWidget(self.table)
        controls = QHBoxLayout()
        for text, callback in (
            (self.t("Lisa"), self.add_record),
            (self.t("Muuda"), self.edit_selected),
            (self.t("Kustuta"), self.delete_selected),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.refresh()

    def refresh(self):
        self.table.setRowCount(len(self.rows))
        fields = field_map(self.metadata)
        for row_index, row in enumerate(self.rows):
            subtype_code = row.get(self.metadata.get("typeIdField") or "")
            for column, name in enumerate(self.columns):
                value = row.get(name)
                options = self.option_overrides.get(name)
                if options is None:
                    options = coded_values(domain_for(
                        self.metadata, name, subtype_code,
                    ))
                labels = {str(code): label for code, label in options}
                display = labels.get(str(value), _format_value(
                    fields.get(name, {}), value,
                ))
                self.table.setItem(row_index, column, QTableWidgetItem(str(display)))
        self.table.resizeColumnsToContents()

    def _dialog(self, values):
        return RecordDialog(
            self.title, self.metadata, values,
            subtype_code=values.get(self.metadata.get("typeIdField") or ""),
            excluded=self.excluded,
            option_overrides=self.option_overrides,
            parent=self,
        )

    def add_record(self):
        values = template_defaults(self.metadata)
        values["globalid"] = new_guid()
        dialog = self._dialog(values)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            row = dialog.values()
            row["_existing"] = False
            row["_dirty"] = True
            self.rows.append(row)
            self.refresh()
            self.table.selectRow(len(self.rows) - 1)

    def edit_selected(self):
        row_index = self.table.currentRow()
        if row_index < 0 or row_index >= len(self.rows):
            return
        dialog = self._dialog(self.rows[row_index])
        if dialog.exec() == QDialog.DialogCode.Accepted:
            existing = self.rows[row_index].get("_existing", False)
            self.rows[row_index] = dialog.values()
            self.rows[row_index]["_existing"] = existing
            self.rows[row_index]["_dirty"] = True
            self.refresh()
            self.table.selectRow(row_index)

    def delete_selected(self):
        row_index = self.table.currentRow()
        if row_index < 0 or row_index >= len(self.rows):
            return
        row = self.rows.pop(row_index)
        if row.get("_existing") and row.get("globalid"):
            self.deleted.append(row["globalid"])
        self.refresh()

    def changed_rows(self):
        return [row for row in self.rows if row.get("_dirty")]


class GeologicalUnitsWidget(QWidget):
    """Depth-first interval grid with derived values and subtype domains."""

    COLUMNS = UNIT_CORE_FIELDS
    COMPOUND_INDEX_FIELDS = (
        "liityksus_indeks_ylemine", "liityksus_indeks_alumine",
    )
    COMPOUND_FORMATION_PARENTS = {
        "liityksus_kihistik_ylemine": "liityksus_indeks_ylemine",
        "liityksus_kihistik_alumine": "liityksus_indeks_alumine",
    }
    COMPOUND_INDEX_FORMATIONS = {
        parent: formation
        for formation, parent in COMPOUND_FORMATION_PARENTS.items()
    }
    COMPOUND_FIELDS = (
        "liityksus_indeks_ylemine", "liityksus_kihistik_ylemine",
        "liityksus_indeks_alumine", "liityksus_kihistik_alumine",
    )

    def __init__(
        self, plugin, metadata, rows, people, elevation_getter,
        current_person_id="", parent=None,
    ):
        super().__init__(parent)
        self.metadata = metadata or {}
        self.plugin = plugin
        self.rows = [dict(row, _existing=True) for row in rows or []]
        self.deleted = []
        self.people = list(people or [])
        self.elevation_getter = elevation_getter
        self.current_person_id = normalize_guid(current_person_id)
        layout = QVBoxLayout(self)
        note = QLabel(plugin.t(
            "Z1 abs, Z2 abs ja paksus arvutatakse automaatselt objekti Z ning "
            "suhteliste sügavuste põhjal. Ridade järjekorra määravad sügavused."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, len(self.COLUMNS))
        fields = field_map(self.metadata)
        self.table.setHorizontalHeaderLabels([
            _label(fields.get(name, {"name": name})) for name in self.COLUMNS
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        controls = QHBoxLayout()
        for text, callback in (
            (plugin.t("Lisa alla"), self.add_below),
            (plugin.t("Poolita"), self.split_selected),
            (plugin.t("Dubleeri"), self.duplicate_selected),
            (plugin.t("Täpsemad väljad…"), self.edit_advanced),
            (plugin.t("Kustuta"), self.delete_selected),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.refresh()

    def _person_options(self):
        return [
            (
                normalize_guid(row.get("globalid")),
                str(row.get("isik_nimi") or row.get("portali_kasutaja") or row.get("globalid")),
            )
            for row in self.people if row.get("globalid")
        ]

    @staticmethod
    def _is_compound(row):
        return str((row or {}).get("indeks")) == str(COMPOUND_INDEX)

    def _options(self, field_name, unit_type, row=None, row_index=None):
        if field_name == "yksus_kood":
            allowed = set(allowed_unit_type_codes(self.rows, row_index or 0))
            return [
                (code, label) for code, label in UNIT_TYPES.items()
                if code in allowed
            ]
        if field_name == "isik_id":
            return self._person_options()
        options = coded_values(domain_for(
            self.metadata, field_name, unit_type,
        ))
        special_labels = {"997": "Teadmata", "998": "Ei kohaldu"}
        options = [
            (code, self.plugin.t(special_labels.get(str(code), label)))
            for code, label in options
        ]
        if field_name == "kihistik":
            return hierarchical_coded_values(
                options, (row or {}).get("indeks")
            )
        if field_name in self.COMPOUND_INDEX_FIELDS:
            return [
                (code, label) for code, label in options
                if str(code) != str(COMPOUND_INDEX)
            ]
        if field_name in self.COMPOUND_FORMATION_PARENTS:
            return hierarchical_coded_values(
                options,
                (row or {}).get(self.COMPOUND_FORMATION_PARENTS[field_name]),
            )
        return options

    def _field_applicable(self, field_name, unit_type, row):
        try:
            code = int(unit_type)
        except (TypeError, ValueError):
            code = 997
        if field_name == "genees":
            return code == 1
        if field_name == "kivim_nimetus":
            return code == 2
        if field_name == "kihistik":
            return (
                not self._is_compound(row)
                and bool(self._options(field_name, code, row))
            )
        if field_name in self.COMPOUND_INDEX_FIELDS:
            return self._is_compound(row)
        if field_name in self.COMPOUND_FORMATION_PARENTS:
            return (
                self._is_compound(row)
                and bool(self._options(field_name, code, row))
            )
        return True

    @staticmethod
    def _fallback(options, *preferred):
        for wanted in preferred:
            for code, _label in options:
                if str(code) == str(wanted):
                    return code
        return None

    def _normalize_type_fields(self, row, unit_type):
        """Clear inapplicable fields and replace invalid template zeroes."""
        result = dict(row or {})
        try:
            code = int(unit_type)
        except (TypeError, ValueError):
            code = 997
        result["yksus_kood"] = code
        index_options = self._options("indeks", code, result)
        if not any(
            str(value) == str(result.get("indeks"))
            for value, _label in index_options
        ):
            result["indeks"] = self._fallback(index_options, 997, 998)

        if code != 1:
            result["genees"] = self._fallback(
                coded_values(domain_for(self.metadata, "genees", code)),
                998, 997,
            )
        if code != 2:
            result["kivim_nimetus"] = self._fallback(
                coded_values(domain_for(
                    self.metadata, "kivim_nimetus", code,
                )), 998, 997,
            )

        if self._is_compound(result):
            result["kihistik"] = self._fallback(
                coded_values(domain_for(self.metadata, "kihistik", code)),
                998, 997,
            )
            for name in self.COMPOUND_INDEX_FIELDS:
                options = self._options(name, code, result)
                if not any(
                    str(value) == str(result.get(name))
                    for value, _label in options
                ):
                    result[name] = self._fallback(options, 997, 998)
            for name in self.COMPOUND_FORMATION_PARENTS:
                options = self._options(name, code, result)
                if not any(
                    str(value) == str(result.get(name))
                    for value, _label in options
                ):
                    result[name] = self._fallback(options, 997, 998)
        else:
            options = self._options("kihistik", code, result)
            if not any(
                str(value) == str(result.get("kihistik"))
                for value, _label in options
            ):
                result["kihistik"] = self._fallback(options, 997, 998)
            for name in self.COMPOUND_FIELDS:
                result[name] = self._fallback(
                    coded_values(domain_for(self.metadata, name, code)),
                    998, 997,
                )
        return result

    def refresh(self):
        self.table.setRowCount(len(self.rows))
        fields = field_map(self.metadata)
        for row_index, row in enumerate(self.rows):
            unit_type = row.get("yksus_kood", 997)
            for column, name in enumerate(self.COLUMNS):
                # QTableWidget keeps an old cell widget alive when only an
                # item is assigned to the same cell. Clear both representations
                # first so subtype/index changes genuinely hide obsolete inputs.
                self.table.removeCellWidget(row_index, column)
                self.table.takeItem(row_index, column)
                value = row.get(name)
                if name == "paksus":
                    top = finite_number(row.get("z_suht_ylemine"))
                    bottom = finite_number(row.get("z_suht_alumine"))
                    display = "" if top is None or bottom is None else f"{bottom - top:g}"
                    item = QTableWidgetItem(display)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row_index, column, item)
                    continue
                if not self._field_applicable(name, unit_type, row):
                    item = QTableWidgetItem("")
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row_index, column, item)
                    continue
                if name in self.COMPOUND_FORMATION_PARENTS:
                    # The formation is shown beside its upper/lower index in
                    # the compact selector occupying the corresponding index
                    # column. Keep the backing column data-only.
                    item = QTableWidgetItem("")
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row_index, column, item)
                    continue
                if name in self.COMPOUND_INDEX_FIELDS:
                    formation_name = self.COMPOUND_INDEX_FORMATIONS[name]
                    selector = CompoundUnitSelector(
                        self._options(name, unit_type, row, row_index),
                        value,
                        self._options(
                            formation_name, unit_type, row, row_index,
                        ),
                        row.get(formation_name),
                        self.plugin.t,
                    )
                    selector.index_combo.currentIndexChanged.connect(
                        lambda _index, target_row=row_index, field=name:
                        self._index_changed(target_row, field)
                    )
                    self.table.setCellWidget(row_index, column, selector)
                    continue
                options = self._options(name, unit_type, row, row_index)
                if options:
                    combo = WheelSafeComboBox()
                    combo.addItem("", None)
                    for code, label in options:
                        combo.addItem(str(label), code)
                    _set_combo_value(combo, value)
                    if name == "yksus_kood":
                        combo.currentIndexChanged.connect(
                            lambda _index, row=row_index: self._unit_type_changed(row)
                        )
                    elif name == "indeks":
                        combo.currentIndexChanged.connect(
                            lambda _index, row=row_index, field=name:
                            self._index_changed(row, field)
                        )
                    self.table.setCellWidget(row_index, column, combo)
                else:
                    self.table.setItem(
                        row_index, column,
                        QTableWidgetItem(_format_value(fields.get(name, {}), value)),
                    )
        self.table.resizeColumnsToContents()
        has_compound = any(self._is_compound(row) for row in self.rows)
        for name in self.COMPOUND_INDEX_FIELDS:
            self.table.setColumnHidden(
                self.COLUMNS.index(name), not has_compound
            )
        for name in self.COMPOUND_FORMATION_PARENTS:
            self.table.setColumnHidden(self.COLUMNS.index(name), True)

    def _unit_type_changed(self, row_index):
        if row_index < 0 or row_index >= len(self.rows):
            return
        current = self._row_values(row_index)
        old_type = self.rows[row_index].get("yksus_kood")
        new_type = current.get("yksus_kood")
        if str(old_type) != str(new_type):
            defaults = unit_defaults(self.metadata, new_type or 997)
            defaults.update({
                key: value for key, value in current.items()
                if key in {
                    "globalid", "z_suht_ylemine", "z_suht_alumine",
                    "isik_id", "kande_alus",
                    "kande_alus_nr", "markus", "_existing",
                }
            })
            # Genesis and lithology supplement are subtype-specific. Reset
            # them from the new subtype template instead of carrying a hidden
            # Not-applicable value from the old subtype into an applicable
            # control. Index and ordinary lithology may survive only when the
            # new subtype explicitly accepts the same code.
            for name in ("indeks", "litoloogia"):
                value = current.get(name)
                options = self._options(name, new_type, current)
                if (
                    self._field_applicable(name, new_type, current)
                    and any(str(code) == str(value) for code, _label in options)
                ):
                    defaults[name] = value
            current_for_kihistik = dict(current)
            current_for_kihistik["indeks"] = defaults.get("indeks")
            value = current.get("kihistik")
            if any(
                str(code) == str(value) for code, _label in self._options(
                    "kihistik", new_type, current_for_kihistik,
                )
            ):
                defaults["kihistik"] = value
            for name in self.COMPOUND_INDEX_FIELDS:
                value = current.get(name)
                options = self._options(name, new_type, current)
                if any(str(code) == str(value) for code, _label in options):
                    defaults[name] = value
            for name in self.COMPOUND_FORMATION_PARENTS:
                value = current.get(name)
                candidate = dict(defaults)
                candidate.update({
                    key: current.get(key) for key in self.COMPOUND_INDEX_FIELDS
                })
                options = self._options(name, new_type, candidate)
                if any(str(code) == str(value) for code, _label in options):
                    defaults[name] = value
            self.rows[row_index] = self._normalize_type_fields(
                defaults, new_type
            )
        self.refresh()
        self.table.selectRow(row_index)

    def _index_changed(self, row_index, field_name="indeks"):
        if row_index < 0 or row_index >= len(self.rows):
            return
        current = self._row_values(row_index)
        current = self._normalize_type_fields(
            current, current.get("yksus_kood")
        )
        self.rows[row_index] = current
        self.refresh()
        self.table.selectRow(row_index)

    def _row_values(self, row_index):
        row = dict(self.rows[row_index])
        fields = field_map(self.metadata)
        for column, name in enumerate(self.COLUMNS):
            if name == "paksus":
                continue
            widget = self.table.cellWidget(row_index, column)
            if isinstance(widget, CompoundUnitSelector):
                index_value, formation_value = widget.values()
                row[name] = _coerce(fields.get(name, {}), index_value)
                formation_name = self.COMPOUND_INDEX_FORMATIONS[name]
                row[formation_name] = _coerce(
                    fields.get(formation_name, {}), formation_value,
                )
                continue
            if name in self.COMPOUND_FORMATION_PARENTS:
                continue
            if isinstance(widget, QComboBox):
                value = widget.currentData()
            else:
                item = self.table.item(row_index, column)
                value = item.text().strip() if item else ""
            row[name] = _coerce(fields.get(name, {}), value)
        return row

    def values(self):
        return [self._row_values(index) for index in range(len(self.rows))]

    def _sync_rows(self):
        self.rows = self.values()

    def add_below(self):
        self._sync_rows()
        selected = self.table.currentRow()
        top = 0.0
        unit_type = 1
        inherited = {}
        insert_at = len(self.rows)
        if 0 <= selected < len(self.rows):
            top = finite_number(self.rows[selected].get("z_suht_alumine")) or 0.0
            unit_type = self.rows[selected].get("yksus_kood") or 997
            inherited = self.rows[selected]
            insert_at = selected + 1
        elif self.rows:
            top = finite_number(self.rows[-1].get("z_suht_alumine")) or 0.0
            unit_type = self.rows[-1].get("yksus_kood") or 997
            inherited = self.rows[-1]
        row = unit_defaults(self.metadata, unit_type)
        row.update({
            "globalid": new_guid(), "_existing": False,
            "z_suht_ylemine": top, "z_suht_alumine": top + 1.0,
        })
        for name in ("isik_id", "kande_alus", "kande_alus_nr"):
            if inherited.get(name) not in (None, ""):
                row[name] = inherited.get(name)
        if self.current_person_id and row.get("isik_id") in (
            None, "", "{00000000-0000-0000-0000-000000000000}",
        ):
            row["isik_id"] = self.current_person_id
        row = self._normalize_type_fields(row, unit_type)
        self.rows.insert(insert_at, row)
        self.refresh()
        self.table.selectRow(insert_at)

    def split_selected(self):
        self._sync_rows()
        index = self.table.currentRow()
        if index < 0 or index >= len(self.rows):
            return
        top = finite_number(self.rows[index].get("z_suht_ylemine"))
        bottom = finite_number(self.rows[index].get("z_suht_alumine"))
        if top is None or bottom is None or bottom <= top:
            return
        middle = (top + bottom) / 2
        duplicate = dict(self.rows[index])
        duplicate.update({"globalid": new_guid(), "_existing": False})
        self.rows[index]["z_suht_alumine"] = middle
        duplicate["z_suht_ylemine"] = middle
        self.rows.insert(index + 1, duplicate)
        self.refresh()
        self.table.selectRow(index + 1)

    def duplicate_selected(self):
        self._sync_rows()
        index = self.table.currentRow()
        if index < 0 or index >= len(self.rows):
            return
        duplicate = dict(self.rows[index])
        duplicate.update({"globalid": new_guid(), "_existing": False})
        self.rows.insert(index + 1, duplicate)
        self.refresh()
        self.table.selectRow(index + 1)

    def edit_advanced(self):
        self._sync_rows()
        index = self.table.currentRow()
        if index < 0 or index >= len(self.rows):
            return
        row = self.rows[index]
        unit_type = row.get("yksus_kood") or 997
        dialog = RecordDialog(
            self.plugin.t("Geoloogilise üksuse täpsemad andmed"),
            self.metadata,
            row,
            subtype_code=unit_type,
            excluded=UNIT_CORE_FIELDS + (
                "puurauk_vaatluspunkt_id", "z_abs_ylemine", "z_abs_alumine",
            ),
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            existing = row.get("_existing", False)
            updated = dialog.values()
            updated.update({key: row.get(key) for key in UNIT_CORE_FIELDS})
            updated["_existing"] = existing
            self.rows[index] = updated
            self.refresh()
            self.table.selectRow(index)

    def delete_selected(self):
        self._sync_rows()
        index = self.table.currentRow()
        if index < 0 or index >= len(self.rows):
            return
        row = self.rows.pop(index)
        if row.get("_existing") and row.get("globalid"):
            self.deleted.append(row["globalid"])
        self.refresh()


class ElevationCheckWidget(QGroupBox):
    """Portal-only raster check for a possibly misplaced legacy object."""

    SYSTEMS = (
        (UNKNOWN, "Teadmata"),
        (EH2000, "EH2000"),
        (BK77, "BK77"),
        (ELLIPSOIDAL, "EUREF-EST97 ellipsoidaalne"),
    )

    def __init__(self, plugin, coordinate_widgets, workspace_key, parent=None):
        super().__init__(plugin.t("Asukoha kõrguskontroll"), parent)
        self.plugin = plugin
        self.coordinate_widgets = coordinate_widgets
        self.workspace_key = workspace_key or "faktika"
        self.match_layer_id = ""
        self.candidate = None
        self._request_token = 0
        self._raster_settings = PluginSettings.load_elevation_raster_settings()

        outer_layout = QVBoxLayout(self)
        self.content = QWidget(self)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.content)
        form = QFormLayout()
        raster_row = QHBoxLayout()
        self.raster = WheelSafeComboBox()
        self.raster.currentIndexChanged.connect(self._raster_changed)
        raster_row.addWidget(self.raster, 1)
        refresh = QPushButton(plugin.t("Värskenda rasterkihte"))
        refresh.clicked.connect(self.reload_rasters)
        raster_row.addWidget(refresh)
        form.addRow(plugin.t("Kõrgusraster"), raster_row)

        system_row = QHBoxLayout()
        self.object_system = WheelSafeComboBox()
        self.dem_system = WheelSafeComboBox()
        for code, text in self.SYSTEMS:
            self.object_system.addItem(plugin.t(text), code)
        # A modern Estonian terrain model is normally EH2000. Keep the
        # object's legacy datum explicit instead of guessing it.
        for code, text in self.SYSTEMS[1:] + self.SYSTEMS[:1]:
            self.dem_system.addItem(plugin.t(text), code)
        system_row.addWidget(QLabel(plugin.t("Objekti Z")))
        system_row.addWidget(self.object_system, 1)
        system_row.addWidget(QLabel(plugin.t("Raster")))
        system_row.addWidget(self.dem_system, 1)
        form.addRow(plugin.t("Kõrgussüsteem"), system_row)

        tolerance_row = QHBoxLayout()
        self.tolerance = WheelSafeDoubleSpinBox()
        self.tolerance.setRange(0.1, 20.0)
        self.tolerance.setDecimals(1)
        self.tolerance.setSingleStep(0.5)
        self.tolerance.setValue(0.5)
        self.tolerance.setSuffix(" m")
        tolerance_row.addWidget(self.tolerance)
        self.advanced = QCheckBox(plugin.t("Täpsemad"))
        tolerance_row.addWidget(self.advanced)
        self.band_label = QLabel(plugin.t("Kõrguskanal"))
        self.band = QSpinBox()
        self.band.setRange(1, 1)
        tolerance_row.addWidget(self.band_label)
        tolerance_row.addWidget(self.band)
        tolerance_row.addStretch(1)
        form.addRow(plugin.t("Sobivusvahemik"), tolerance_row)
        layout.addLayout(form)

        self.comparison = QLabel(plugin.t(
            "Vali raster ning objekti kõrgussüsteem. Z-väärtust ei muudeta."
        ))
        self.comparison.setWordWrap(True)
        layout.addWidget(self.comparison)
        self.current_result = QLabel("")
        self.current_result.setWordWrap(True)
        layout.addWidget(self.current_result)
        self.candidate_result = QLabel("")
        self.candidate_result.setWordWrap(True)
        layout.addWidget(self.candidate_result)

        controls = QHBoxLayout()
        for text, callback in (
            (plugin.t("Kontrolli praegust asukohta"), self.check_current),
            (plugin.t("Kuva sobivusala"), self.show_matching_area),
            (plugin.t("Peida sobivusala"), self.hide_matching_area),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)
        candidate_controls = QHBoxLayout()
        pick = QPushButton(plugin.t("Vali kandidaat kaardilt"))
        pick.clicked.connect(self.pick_candidate)
        candidate_controls.addWidget(pick)
        self.use_candidate = QPushButton(plugin.t("Määra kandidaadi X/Y"))
        self.use_candidate.setEnabled(False)
        self.use_candidate.clicked.connect(self.apply_candidate)
        candidate_controls.addWidget(self.use_candidate)
        candidate_controls.addStretch(1)
        layout.addLayout(candidate_controls)

        self.advanced.toggled.connect(self._update_advanced_visibility)
        self.object_system.currentIndexChanged.connect(self._configuration_changed)
        self.dem_system.currentIndexChanged.connect(self._configuration_changed)
        self.tolerance.valueChanged.connect(self._configuration_changed)
        self.band.valueChanged.connect(self._configuration_changed)
        self.reload_rasters()
        self._update_advanced_visibility()
        self.setCheckable(True)
        self.setChecked(False)
        self.content.setVisible(False)
        self.toggled.connect(self.content.setVisible)

    def _geometry(self):
        return {
            key: widget.value() for key, widget in self.coordinate_widgets.items()
        }

    def reload_rasters(self):
        previous = self.raster.currentData() if self.raster.count() else ""
        self.raster.blockSignals(True)
        self.raster.clear()
        self.raster.addItem(self.plugin.t("Vali rasterkiht"), "")
        for layer in self.plugin.elevation_rasters():
            self.raster.addItem(layer.name(), layer.id())
        index = self.raster.findData(previous)
        self.raster.setCurrentIndex(max(0, index))
        self.raster.blockSignals(False)
        self._raster_changed()

    def _selected_raster(self):
        return QgsProject.instance().mapLayer(str(self.raster.currentData() or ""))

    def _raster_key(self, layer):
        return str(layer.source() or layer.id()) if layer is not None else ""

    def _raster_changed(self):
        layer = self._selected_raster()
        band_count = max(1, layer.bandCount()) if layer is not None else 1
        self.band.setRange(1, band_count)
        values = self._raster_settings.get(self._raster_key(layer), {})
        self.band.setValue(min(band_count, max(1, int(values.get("band", 1)))))
        datum = str(values.get("datum") or EH2000)
        index = self.dem_system.findData(datum)
        self.dem_system.setCurrentIndex(max(0, index))
        self.advanced.setVisible(band_count > 1)
        if band_count <= 1:
            self.advanced.setChecked(False)
        self._update_advanced_visibility()
        self._configuration_changed()

    def _update_advanced_visibility(self):
        visible = bool(self.advanced.isVisible() and self.advanced.isChecked())
        self.band_label.setVisible(visible)
        self.band.setVisible(visible)

    def _save_raster_settings(self):
        layer = self._selected_raster()
        key = self._raster_key(layer)
        if not key:
            return
        self._raster_settings[key] = {
            "band": self.band.value(),
            "datum": self.dem_system.currentData() or EH2000,
        }
        PluginSettings.save_elevation_raster_settings(self._raster_settings)

    def _configuration_changed(self, *_args):
        self._request_token += 1
        self._save_raster_settings()
        if self.match_layer_id:
            self.hide_matching_area()
        self.candidate = None
        self.use_candidate.setEnabled(False)
        self.candidate_result.clear()

    def _with_target(self, easting, northing, callback):
        geometry = self._geometry()
        token = self._request_token = self._request_token + 1
        self.comparison.setText(self.plugin.t("Kõrgust teisendatakse…"))

        def converted(target, warning):
            if token != self._request_token:
                return
            source = self.object_system.currentText()
            destination = self.dem_system.currentText()
            correction = target - geometry["z"]
            text = (
                f"{self.plugin.t('Võrdluskõrgus')}: {target:.3f} m "
                f"({source} → {destination}; Δ {correction:+.3f} m)"
            )
            if warning:
                text += f" · {warning}"
            self.comparison.setText(text)
            callback(float(target), warning)

        def failed(error):
            if token == self._request_token:
                self.comparison.setText(
                    self.plugin.t("Kõrguse teisendamine ebaõnnestus")
                    + f": {error}"
                )

        self.plugin.convert_portal_height(
            easting, northing, geometry["z"],
            self.object_system.currentData() or UNKNOWN,
            self.dem_system.currentData() or UNKNOWN,
            converted, failed,
        )

    def _sample_result(self, easting, northing, target):
        layer = self._selected_raster()
        summary = self.plugin.sample_elevation_raster(
            layer, easting, northing, self.band.value()
        )
        if not summary:
            return None, self.plugin.t("Selles punktis puudub rasterväärtus.")
        delta = summary["median"] - target
        text = (
            f"E {easting:.3f}, N {northing:.3f} · "
            f"{self.plugin.t('DEM mediaan')} {summary['median']:.3f} m · "
            f"Δ {delta:+.3f} m · "
            f"3×3: {summary['minimum']:.3f}…{summary['maximum']:.3f} m "
            f"({summary['count']} px)"
        )
        return summary, text

    def check_current(self):
        if self._selected_raster() is None:
            self.current_result.setText(self.plugin.t("Vali sobiv rasterkiht."))
            return
        geometry = self._geometry()
        self._with_target(
            geometry["x"], geometry["y"],
            lambda target, _warning: self.current_result.setText(
                self._sample_result(geometry["x"], geometry["y"], target)[1]
            ),
        )

    def show_matching_area(self):
        layer = self._selected_raster()
        if layer is None:
            self.current_result.setText(self.plugin.t("Vali sobiv rasterkiht."))
            return
        geometry = self._geometry()

        def show(target, _warning):
            try:
                self.match_layer_id = self.plugin.show_elevation_match_layer(
                    layer, self.band.value(), target, self.tolerance.value(),
                    self.workspace_key, self.match_layer_id,
                )
                self.current_result.setText(
                    self.plugin.t("Sobivusala kuvab ainult sihtkõrguse vahemikku.")
                )
            except (TypeError, ValueError, RuntimeError) as error:
                self.current_result.setText(str(error))

        self._with_target(geometry["x"], geometry["y"], show)

    def hide_matching_area(self):
        self.plugin.remove_elevation_match_layer(self.match_layer_id)
        self.match_layer_id = ""

    def pick_candidate(self):
        if self._selected_raster() is None:
            self.candidate_result.setText(self.plugin.t("Vali sobiv rasterkiht."))
            return
        self.plugin.start_elevation_candidate_pick(self.window())

    def elevation_candidate_selected(self, easting, northing):
        geometry = self._geometry()
        distance = hypot(easting - geometry["x"], northing - geometry["y"])

        def checked(target, _warning):
            summary, text = self._sample_result(easting, northing, target)
            if summary is None:
                self.candidate = None
                self.use_candidate.setEnabled(False)
            else:
                self.candidate = {
                    "x": float(easting), "y": float(northing),
                    "target": target, "summary": summary,
                }
                self.use_candidate.setEnabled(True)
            self.candidate_result.setText(
                self.plugin.t("Kandidaat") + f" ({distance:.1f} m) · " + text
            )

        self._with_target(easting, northing, checked)

    def apply_candidate(self):
        if not self.candidate:
            return
        self.hide_matching_area()
        self.coordinate_widgets["x"].setValue(self.candidate["x"])
        self.coordinate_widgets["y"].setValue(self.candidate["y"])
        self.current_result.setText(self.plugin.t(
            "Kandidaadi X/Y lisati vormile. Z jäi muutmata; muudatus "
            "salvestub alles koos kogu objektiga."
        ))
        self.candidate = None
        self.use_candidate.setEnabled(False)

    def close(self):
        self.hide_matching_area()
        super().close()


class FaktikaEditorDialog(QDialog):
    """Edit one Faktika parent and its object-owned related records."""

    def __init__(self, plugin, metadata, context, save_callback, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.metadata = metadata or {}
        self.context = context or {}
        self.save_callback = save_callback
        self.parent_values = dict(self.context.get("parent") or {})
        calculated_length = _geological_length(
            self.context.get("geological_units") or []
        )
        if calculated_length is not None:
            self.parent_values["pikkus"] = calculated_length
        self.is_new = bool(self.context.get("is_new"))
        self.setWindowTitle(
            plugin.t("Lisa Faktika objekt") if self.is_new
            else plugin.t("Redigeeri Faktika objekti")
        )
        self.resize(1180, 820)
        layout = QVBoxLayout(self)
        workspace_title = {
            "cleanup": "EGT korrastatavad puuraugud v2",
        }.get(self.context.get("workspace_key"), "Faktika töökiht")
        badge = QLabel(
            f"EGT Portal · {workspace_title} · "
            + (plugin.t("uus objekt") if self.is_new else plugin.t("sisemine kirje"))
        )
        badge.setStyleSheet(
            "background:#1f6f54;color:white;border-radius:4px;"
            "padding:6px 10px;font-weight:600;"
        )
        layout.addWidget(badge)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_general_tab()
        self._build_units_tab()
        self._build_related_tabs()
        self.tabs.currentChanged.connect(
            lambda _index: self._sync_derived_parent_length()
        )

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            plugin.t("Kontrolli ja salvesta")
        )
        self.buttons.accepted.connect(self._submit)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _build_general_tab(self):
        metadata = self.metadata.get(1, {})
        object_type = self.parent_values.get("objekti_tyyp") or 1
        try:
            is_offshore = int(object_type) == 3
        except (TypeError, ValueError):
            is_offshore = False
        core_fields = tuple(
            name for name in PARENT_CORE_FIELDS
            if is_offshore or name not in SEA_ONLY_PARENT_FIELDS
        )
        page = QWidget()
        layout = QVBoxLayout(page)
        coordinates = QGroupBox(self.plugin.t("Koordinaadid (L-EST97)"))
        coordinate_form = QFormLayout(coordinates)
        geometry = self.context.get("geometry") or {}
        self.coordinate_widgets = {}
        for key, label, minimum, maximum, decimals in (
            ("x", "X *", -1000000.0, 2000000.0, 3),
            ("y", "Y *", 0.0, 10000000.0, 3),
            ("z", "Z *", -10000.0, 10000.0, 3),
        ):
            widget = WheelSafeDoubleSpinBox()
            widget.setRange(minimum, maximum)
            widget.setDecimals(decimals)
            widget.setValue(finite_number(geometry.get(key)) or 0.0)
            self.coordinate_widgets[key] = widget
            coordinate_form.addRow(label, widget)
        layout.addWidget(coordinates)
        self.elevation_check = ElevationCheckWidget(
            self.plugin, self.coordinate_widgets,
            self.context.get("workspace_key", "faktika"), page,
        )
        for widget in self.coordinate_widgets.values():
            widget.editingFinished.connect(
                self.elevation_check._configuration_changed
            )
        layout.addWidget(self.elevation_check)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        core_scroll = QScrollArea()
        core_scroll.setWidgetResizable(True)
        self.parent_core = AttributeForm(
            metadata, self.parent_values,
            field_names=core_fields,
            subtype_code=object_type,
            option_overrides={
                "objekti_tyyp": list(OBJECT_TYPES.items()),
                "yksus_kood": list(UNIT_TYPES.items()),
            },
        )
        for automatic in ("objekti_tyyp", "yksus_kood"):
            if automatic in self.parent_core.widgets:
                self.parent_core.widgets[automatic].setEnabled(False)
        if "pikkus" in self.parent_core.widgets:
            self.parent_core.widgets["pikkus"].setEnabled(False)
        self._install_sarv_match_control(object_type)
        core_scroll.setWidget(self.parent_core)
        advanced_scroll = QScrollArea()
        advanced_scroll.setWidgetResizable(True)
        self.parent_advanced = AttributeForm(
            metadata, self.parent_values,
            subtype_code=object_type,
            excluded=PARENT_CORE_FIELDS,
            multiline_fields={"markus": 120, "lisainfo": 80},
            option_overrides={
                "objekti_tyyp": list(OBJECT_TYPES.items()),
                "yksus_kood": list(UNIT_TYPES.items()),
                "klassif_yksus_kood": list(UNIT_TYPES.items()),
            },
        )
        advanced_scroll.setWidget(self.parent_advanced)
        splitter.addWidget(core_scroll)
        splitter.addWidget(advanced_scroll)
        splitter.setSizes([590, 390])
        layout.addWidget(splitter, 1)
        self.tabs.addTab(page, self.plugin.t("Üldandmed"))

    def _install_sarv_match_control(self, object_type):
        """Place the optional local match compactly beside Portal SARV ID."""
        self.sarv_match_combo = None
        try:
            is_borehole = int(object_type) == 1
        except (TypeError, ValueError):
            is_borehole = False
        suggestions = list(self.context.get("sarv_suggestions") or ())
        if not is_borehole or not suggestions:
            return
        combo = WheelSafeComboBox()
        combo.addItem(self.plugin.t("Ära lisa seost"), None)
        selected = 0
        for candidate in suggestions:
            text = str(candidate.get("text") or candidate.get("sarv_id") or "")
            evidence = str(candidate.get("evidence") or "").strip()
            if evidence:
                text += f" — {evidence}"
            combo.addItem(text, dict(candidate))
            if candidate.get("manual"):
                selected = combo.count() - 1
        combo.setCurrentIndex(selected)
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(18)
        combo.setToolTip(self.plugin.t(
            "Kinnitatud seos valitakse ette. Uus kandidaat salvestub "
            "Qeoloogi kohaliku seosena alles koos objekti salvestamisega."
        ))
        self.sarv_match_combo = combo
        value_widget = self.parent_core.widgets.get("sarv_id")
        if value_widget is None:
            self.parent_core.form_layout.addRow(
                self.plugin.t("SARV vaste"), combo,
            )
            return
        row, _role = self.parent_core.form_layout.getWidgetPosition(value_widget)
        if row < 0:
            self.parent_core.form_layout.addRow(
                self.plugin.t("SARV vaste"), combo,
            )
            return
        self.parent_core.form_layout.removeWidget(value_widget)
        host = QWidget(self.parent_core)
        compact = QHBoxLayout(host)
        compact.setContentsMargins(0, 0, 0, 0)
        compact.setSpacing(6)
        compact.addWidget(value_widget, 1)
        compact.addWidget(QLabel(self.plugin.t("Vaste")))
        compact.addWidget(combo, 2)
        self.parent_core.form_layout.setWidget(
            row, QFormLayout.ItemRole.FieldRole, host,
        )

    def _selected_sarv_match(self):
        if not isinstance(self.sarv_match_combo, QComboBox):
            return None
        value = self.sarv_match_combo.currentData()
        return dict(value) if isinstance(value, dict) else None

    def _build_units_tab(self):
        self.units = GeologicalUnitsWidget(
            self.plugin,
            self.metadata.get(6, {}),
            self.context.get("geological_units") or [],
            self.context.get("people") or [],
            lambda: self.coordinate_widgets["z"].value(),
            self.context.get("current_person_id") or "",
        )
        self.tabs.addTab(self.units, self.plugin.t("Geoloogilised üksused"))

    def _build_related_tabs(self):
        attachments = self.context.get("attachments") or []
        attachment_options = [
            (normalize_guid(row.get("globalid")), str(row.get("link") or row.get("globalid")))
            for row in attachments if row.get("globalid")
        ]
        self.attachments = RelatedRecordsWidget(
            self.plugin.t("Manus"), self.metadata.get(4, {}), attachments,
            ("link", "manus_tyyp", "institutsioon", "avalik", "markus"),
            excluded=("puurauk_vaatluspunkt_id", "isik_id", "juurdepaasu_alus_id"),
            translate=self.plugin.t,
        )
        self.tabs.addTab(self.attachments, self.plugin.t("Manused"))
        self.keywords = RelatedRecordsWidget(
            self.plugin.t("Manuse märksõna"), self.metadata.get(3, {}),
            self.context.get("attachment_keywords") or [],
            ("manus_id", "marksona", "markus"),
            option_overrides={"manus_id": attachment_options},
            translate=self.plugin.t,
        )
        self.tabs.addTab(self.keywords, self.plugin.t("Manuse märksõnad"))
        self.access = RelatedRecordsWidget(
            self.plugin.t("Juurdepääsu alus"), self.metadata.get(5, {}),
            self.context.get("access_basis") or [],
            ("juurdepaasu_alus", "kehtiv_kuni", "markus"),
            excluded=("puurauk_vaatluspunkt_id", "manus_id"),
            translate=self.plugin.t,
        )
        self.tabs.addTab(self.access, self.plugin.t("Juurdepääs"))

    def _sync_derived_parent_length(self):
        if not hasattr(self, "units"):
            return
        length = _geological_length(self.units.values())
        widget = self.parent_core.widgets.get("pikkus")
        if isinstance(widget, QLineEdit):
            widget.setText("" if length is None else f"{length:g}")

    def _parent_attributes(self):
        values = dict(self.parent_values)
        values.update(self.parent_advanced.values())
        values.update(self.parent_core.values())
        return values

    def _geometry(self):
        return {
            key: widget.value() for key, widget in self.coordinate_widgets.items()
        }

    def elevation_candidate_selected(self, easting, northing):
        if hasattr(self, "elevation_check"):
            self.elevation_check.elevation_candidate_selected(easting, northing)

    def closeEvent(self, event):
        if hasattr(self, "elevation_check"):
            self.elevation_check.hide_matching_area()
        self.plugin.stop_elevation_candidate_pick(self)
        super().closeEvent(event)

    def _submit(self):
        geometry = self._geometry()
        parent_preview = self._parent_attributes()
        units, unit_errors, warnings = validate_units(
            self.units.values(), geometry["z"],
            parent_preview.get("vertikaalne_ulatus") or None,
        )
        self._sync_derived_parent_length()
        parent = self._parent_attributes()
        parent["pikkus"] = _geological_length(units)
        errors = validate_parent(parent, geometry)
        errors.extend(unit_errors)
        # The parent code is a summary of its geological intervals.  Do not
        # let a stale/manual value disagree with the units being saved.
        parent["yksus_kood"] = unit_category_code(units)
        if errors:
            QMessageBox.warning(
                self, self.plugin.t("Andmed vajavad parandamist"),
                "\n".join(
                    f"• {_validation_text(self.plugin, message)}"
                    for message in errors
                ),
            )
            return
        if warnings:
            answer = QMessageBox.question(
                self, self.plugin.t("Kontrolli hoiatusi"),
                "\n".join(
                    f"• {_validation_text(self.plugin, message)}"
                    for message in warnings
                )
                + "\n\n" + self.plugin.t("Kas salvestada siiski?"),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        payload = {
            "parent": parent,
            "geometry": geometry,
            "geological_units": units,
            "deleted_unit_ids": tuple(self.units.deleted),
            "attachments": tuple(self.attachments.changed_rows()),
            "deleted_attachment_ids": tuple(self.attachments.deleted),
            "attachment_keywords": tuple(self.keywords.changed_rows()),
            "deleted_keyword_ids": tuple(self.keywords.deleted),
            "access_basis": tuple(self.access.changed_rows()),
            "deleted_access_ids": tuple(self.access.deleted),
            "people": (),
            "deleted_person_ids": (),
            "is_new": self.is_new,
            "edit_moment": self.context.get("edit_moment"),
            "workspace_key": self.context.get("workspace_key", "faktika"),
            "sarv_match": self._selected_sarv_match(),
            "sarv_match_key": self.context.get("sarv_match_key", ""),
            "sarv_match_attributes": dict(
                self.context.get("match_attributes") or {}
            ),
        }
        self.set_busy(True, self.plugin.t("Muudatusi salvestatakse…"))
        self.save_callback(payload, self)

    def set_busy(self, busy, text=""):
        self.tabs.setEnabled(not busy)
        self.buttons.setEnabled(not busy)
        self.status.setText(text)

    def save_failed(self, message):
        self.set_busy(False, str(message))
        QMessageBox.critical(
            self, self.plugin.t("Salvestamine ebaõnnestus"), str(message),
        )

    def save_succeeded(self):
        self.set_busy(False, self.plugin.t("Muudatused salvestati."))
        self.accept()
