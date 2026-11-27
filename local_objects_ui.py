"""QGIS browser and editor for the portable local ETL object records."""

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from math import isfinite
from uuid import uuid4

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QStyle, QStyledItemDelegate, QTabWidget, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from .etl_domains import (
    domain_dependencies, domain_match, domain_options, has_domain,
)
from .local_objects import LocalObjectStore, calculate_unit_geometry, local_object_name
from .local_unit_rules import UNIT_RULE_FIELDS, UNIT_RULE_PARENTS, UNIT_SHEET, unit_field_options
from .section_workspace import SectionWorkspaceError
from .ui_utils import ClosedComboWheelGuard


_UNITS = UNIT_SHEET
_GENERAL = "Mall"
_TEMP_ID = "ID_ajutine"
_LAB_IDS = frozenset({"mall_seeria", "mall_proov", "mall_mootmine"})
_LAB_NAMES = (
    "nimi", "nimetus", "proov_tahis", "proov_tahis_alg", "proov_nr", "seeria_nimi",
    "analyys_kood", "mootmise_nimi", "kood", "kirjeldus", "markus",
)
_LAB_FIELD_LABELS = {
    _TEMP_ID: "Ajutine tunnus",
    "puurauk_vaatluspunkt_id": "Objekti viide",
    "proov_id": "Proovi viide",
    "algne_id": "Proovi viide",
    "aeg": "Proovivõtu aeg",
    "kuupaev": "Kuupäev",
    "tulem": "Tulemus",
    "tulemi_kordustapsus": "Kordustäpsus",
    "alumine_maaramispiir": "Alumine määramispiir",
    "ylemine_maaramispiir": "Ülemine määramispiir",
    "egf_nr": "EGF number",
    "kirjandus_viit": "Kirjanduse viide",
}
_LAB_HELP = (
    "Vali viite lahtris seeria, proov või mõõtmine. Seotud rea saab lisada ka "
    "valitud algkirje juurest. QEO-tunnused on kohalikud viited, mitte "
    "lähteandmebaasi GUID-id."
)
_GENERAL_FIRST = (
    "nimi", "alias", "objekti_tyyp", "yksus_kood", "geom_x", "geom_y", "geom_z",
    "vertical_datum", "pikkus", "vertikaalne_ulatus", "kande_alus", "kande_alus_nr",
    "asukoha_tapsusklass", "puurimisfirma", "valmimise_kuupaev", "markus", "lisainfo",
)
_UNIT_FIRST = (
    "ID_ajutine", "z_suht_ylemine", "z_suht_alumine", "yksus_kood",
    "indeks", "kihistik", "liityksus_indeks_ylemine", "liityksus_kihistik_ylemine",
    "liityksus_indeks_alumine", "liityksus_kihistik_alumine", "genees",
    "litoloogia", "kivim_nimetus", "paksus", "z_abs_ylemine", "z_abs_alumine", "markus",
)
_UNIT_RULE_HINT = (
    "Vali real üksus ja indeks. Hallid lahtrid ei kehti selle valiku korral; "
    "olemasolevaid väärtusi ei kustutata."
)
_UNIT_LOCKED = "Väli ei kehti selle rea üksuse või indeksi puhul."
_NEXT_UNIT_FIELDS = (
    ("z_suht_alumine", "z_suht_ylemine"),
    ("isik_nimi", "isik_nimi"),
    ("kande_alus", "kande_alus"),
    ("kande_alus_nr", "kande_alus_nr"),
    ("yksus_kood", "yksus_kood"),
)
_ABSOLUTE_PROMPT = (
    "Kasuta ainult vertikaalseid suhtelisi sügavusi samast nullpunktist, "
    "mille absoluutkõrgus on Z. Tulemus jääb Z kõrgussüsteemi; "
    "kõrgussüsteemi teisendust ei tehta. Kas arvutada absoluutkõrgused?"
)
_SHEET_LABELS = {
    _UNITS: "Geoloogiline kirjeldus",
    "geol_vahekiht_mall": "Vahekihid",
    "geol_mineraal_mall": "Mineraalid",
    "geol_fos_det_mall": "Fossiilid ja detriit",
    "nahtus_mall": "Nähtused",
    "mall_seeria": "Seeriad",
    "mall_proov": "Proovid",
    "mall_seos": "Seeria–proovi seosed",
    "mall_mootmine": "Mõõtmised",
    "mall_viitamine": "Viited",
    "mall_tulem": "Tulemused",
}
_FIELD_LABELS = {
    "nimi": "Nimi", "alias": "Alias", "objekti_tyyp": "Objekti tüüp",
    "yksus_kood": "Üksuse kood", "geom_x": "Idakoordinaat X (EPSG:3301)",
    "geom_y": "Põhjakoordinaat Y (EPSG:3301)", "geom_z": "Kõrgus Z (m)",
    "vertical_datum": "Kõrgussüsteem", "pikkus": "Pikkus (m)",
    "vertikaalne_ulatus": "Vertikaalne ulatus (m)",
    "valmimise_kuupaev": "Valmimise kuupäev", "markus": "Märkus",
    "lisainfo": "Lisainfo", "z_suht_ylemine": "Ülemine sügavus",
    "z_suht_alumine": "Alumine sügavus",
    "z_abs_ylemine": "Ülemine absoluutkõrgus", "z_abs_alumine": "Alumine absoluutkõrgus",
    "paksus": "Paksus", "indeks": "Indeks", "litoloogia": "Litoloogia",
    "genees": "Genees", "kivim_nimetus": "Litoloogia täiend", "kihistik": "Kihistik",
    "liityksus_indeks_ylemine": "LÜ ülemine indeks",
    "liityksus_kihistik_ylemine": "LÜ ülemine kihistik",
    "liityksus_indeks_alumine": "LÜ alumine indeks",
    "liityksus_kihistik_alumine": "LÜ alumine kihistik",
}
_ENGLISH = {
    _UNIT_RULE_HINT: (
        "Select the unit type and index in this row. Grey cells do not apply "
        "to the selection; existing values are not deleted."
    ),
    _UNIT_LOCKED: "This field does not apply to this row's unit type or index.",
    "Genees": "Genesis", "Litoloogia täiend": "Lithology qualifier", "Kihistik": "Member",
    "LÜ ülemine indeks": "Compound upper index",
    "LÜ ülemine kihistik": "Compound upper member",
    "LÜ alumine indeks": "Compound lower index",
    "LÜ alumine kihistik": "Compound lower member",
    "Kohalik objekt": "Local object",
    "Uus objekt…": "New object…",
    "Ava objekt": "Open object",
    "Redigeeri…": "Edit…",
    "Lisa läbilõikele": "Add to cross-section",
    "Otsi kohalikest objektidest": "Search local objects",
    "Kohalikke objekte: {count}": "Local objects: {count}",
    "Loo või ava läbilõigete töökaust, et kasutada kohalikke andmeid.": "Create or open a section workspace to use local data.",
    "Kohalikku objekti ei saanud avada või salvestada.": "Could not open or save the local object.",
    "Töökaust muutus redigeerimise ajal. Ava objekt uuesti õiges töökaustas.": "The workspace changed while editing. Reopen the object in the correct workspace.",
    "Objekt muutus redigeerimise ajal. Mustand jäi avatuks; enne uut salvestust kopeeri oma muudatused ja ava ajakohane kirje.": "The object changed while you were editing. Your draft is still open; copy your changes and reopen the current record before saving again.",
    "Geoloogiline kirjeldus": "Geological description",
    "Vahekihid": "Interbeds",
    "Mineraalid": "Minerals",
    "Fossiilid ja detriit": "Fossils and detritus",
    "Nähtused": "Phenomena",
    "Kõrgus Z (m)": "Elevation Z (m)",
    "Kõrgussüsteem": "Vertical datum",
    "Pikkus (m)": "Length (m)",
    "Vertikaalne ulatus (m)": "Vertical extent (m)",
    "Valmimise kuupäev": "Completion date",
    "Ülemine sügavus": "Upper depth",
    "Alumine sügavus": "Lower depth",
    "Ülemine absoluutkõrgus": "Upper absolute elevation",
    "Alumine absoluutkõrgus": "Lower absolute elevation",
    "Algallikas": "Original source",
    "Arvuta paksused": "Calculate thicknesses",
    "Arvuta absoluutkõrgused": "Calculate absolute elevations",
    _ABSOLUTE_PROMPT: (
        "Use only vertical depths measured from the same origin as elevation Z. "
        "The output stays in Z's vertical datum; no datum conversion is applied. "
        "Calculate absolute elevations?"
    ),
    "Lisa järgmine kiht": "Add next unit",
    "Vali koordinaadid kaardilt": "Pick coordinates on the map",
    "Sisesta kuupäev AAAA-KK-PP": "Enter date as YYYY-MM-DD",
    "Kohalik muutmine ei muuda algallikat.": "Local edits do not alter the original source.",
    "Töökausta andmed": "Workspace data",
    "Üksuse kood": "Unit code",
    "Idakoordinaat X (EPSG:3301)": "Easting X (EPSG:3301)",
    "Põhjakoordinaat Y (EPSG:3301)": "Northing Y (EPSG:3301)",
    "Loo töökaust…": "Create workspace…",
    "Ava töökaust…": "Open workspace…",
    "Kaardilt valimine ebaõnnestus": "Map selection failed",
    "ID_ajutine viitab geoloogilise üksuse ID_ajutine väärtusele.": "ID_ajutine refers to the geological unit's ID_ajutine value.",
    "Laboriandmed": "Laboratory data",
    "Litotulp…": "Lithology column…",
    "Seeriad": "Series",
    "Proovid": "Samples",
    "Seeria–proovi seosed": "Series–sample links",
    "Mõõtmised": "Measurements",
    "Viited": "References",
    "Tulemused": "Results",
    "Lisa seotud rida": "Add linked row",
    "Vali esmalt üks algkirje.": "Select one parent row first.",
    "Tunnus pole selles tabelis üheselt määratud: {id}.": "The ID is not unique in this table: {id}.",
    "Olemasolev viide: {id}": "Existing reference: {id}",
    "Vali viide": "Select reference",
    "Ajutine tunnus": "Temporary identifier",
    "Objekti viide": "Object reference",
    "Proovi viide": "Sample reference",
    "Viide: {table}": "Reference: {table}",
    "Kordustäpsus": "Repeatability",
    "Alumine määramispiir": "Lower determination limit",
    "Ülemine määramispiir": "Upper determination limit",
    "EGF number": "EGF number",
    "Kirjanduse viide": "Literature reference",
    "Täitmata": "Not set",
    "Säilita olemasolev: {value}": "Keep existing value: {value}",
    _LAB_HELP: (
        "Select a series, sample, or measurement in a reference cell. "
        "You may also add a linked row from its selected parent. "
        "QEO IDs are local references, not source database GUIDs."
    ),
}


def _t(plugin, key):
    if getattr(plugin, "language", "et") == "en" and key in _ENGLISH:
        return _ENGLISH[key]
    return plugin.t(key)


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _fields(*parts):
    return tuple(dict.fromkeys(field for group in parts for field in group))


def _in_field_set(fields, sheet, key):
    return key in (fields.get(sheet, ()) if isinstance(fields, dict) else fields)


def editable_value(sheet, key, value, previous):
    """Preserve unchanged raw provider representations; type changed ETL fields."""
    if value == _text(previous):
        return previous
    value = value.strip()
    if not value:
        return None
    # The field schema drives only the edited fields, never unrecognized data.
    from .etl_workbooks import ETL_DATE_FIELDS, ETL_INT_FIELDS, ETL_NUMERIC_FIELDS
    if _in_field_set(ETL_DATE_FIELDS, sheet, key):
        try:
            if len(value) == 10:
                try:
                    return date.fromisoformat(value).isoformat()
                except ValueError:
                    return datetime.strptime(value, "%d.%m.%Y").date().isoformat()
            return datetime.fromisoformat(value).isoformat()
        except ValueError as error:
            raise SectionWorkspaceError(f"{key}: YYYY-MM-DD") from error
    if _in_field_set(ETL_INT_FIELDS, sheet, key):
        try:
            number = Decimal(value)
            if number.is_finite() and number == number.to_integral_value() and abs(number) <= 2**63 - 1:
                return int(number)
        except InvalidOperation:
            pass
        raise SectionWorkspaceError(f"{key}: integer required.")
    if _in_field_set(ETL_NUMERIC_FIELDS, sheet, key):
        try:
            number = float(value.replace(",", "."))
            if isfinite(number):
                return number
        except ValueError:
            pass
        raise SectionWorkspaceError(f"{key}: finite number required.")
    return value


def _source_text(record):
    ref = record.get("source_ref") or {}
    return " · ".join(_text(ref.get(key)) for key in ("source", "entity", "id") if ref.get(key))


def _search_text(record):
    return json.dumps([record.get("id"), record.get("attributes"), record.get("source_ref"),
                       record.get("units"), record.get("related")], ensure_ascii=False).casefold()


def _guarded_combo(combo):
    guard = ClosedComboWheelGuard(combo)
    combo.installEventFilter(guard)
    combo._qeoloog_wheel_guard = guard
    return combo


class _DomainComboBox(QComboBox):
    """Show a template label without coercing an existing saved value."""

    valueChanged = pyqtSignal()

    def __init__(self, dialog, sheet, field, parent=None):
        super().__init__(parent)
        self.dialog, self.sheet, self.field = dialog, sheet, field
        self._value = None
        self.touched = False
        self.setObjectName(f"qeoloogDomain_{sheet}_{field}")
        self.setMaxVisibleItems(24)
        self.setMinimumContentsLength(16)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        _guarded_combo(self)
        self.currentIndexChanged.connect(self._pick)
        # A user can explicitly choose the option already displayed for a
        # loaded label/code, asking to store its canonical template code.
        self.activated.connect(self._pick)

    def raw_value(self):
        return self._value

    def load(self, raw, *, row=None, attrs=None, choices=None):
        if choices is None:
            choices = domain_options(self.sheet, self.field, row=row, attrs=attrs)
        match = domain_match(self.sheet, self.field, raw, row=row, attrs=attrs)
        labels = {}
        for _, label in choices:
            key = label.casefold()
            labels[key] = labels.get(key, 0) + 1
        blocked = self.blockSignals(True)
        try:
            self._value = raw
            self.touched = False
            self.clear()
            self.addItem(self.dialog.t("Täitmata"), None)
            selected = 0
            for code, label in choices:
                caption = f"{label} ({_text(code)})" if labels[label.casefold()] > 1 else label
                self.addItem(caption, code)
                self.setItemData(self.count() - 1, _text(code), Qt.ItemDataRole.ToolTipRole)
                if match and type(match[0]) is type(code) and match[0] == code:
                    selected = self.count() - 1
            if selected == 0 and raw not in (None, ""):
                self.addItem(self.dialog.t("Säilita olemasolev: {value}").format(value=_text(raw)), raw)
                selected = self.count() - 1
            self.setCurrentIndex(selected)
        finally:
            self.blockSignals(blocked)

    def _pick(self, index):
        if index < 0:
            return
        value = self.itemData(index)
        changed = type(value) is not type(self._value) or value != self._value
        self._value = value
        self.touched = True
        if changed:
            self.valueChanged.emit()


class _DomainDelegate(QStyledItemDelegate):
    """Render friendly labels, edit domain codes in the Qt model."""

    def __init__(self, editor, field):
        super().__init__(editor.table)
        self.editor, self.field = editor, field

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        governed = self.field in self.editor.unit_rule_columns
        inactive = governed and not (index.flags() & Qt.ItemFlag.ItemIsEditable)
        if inactive:
            option.state &= ~QStyle.StateFlag.State_Enabled
        raw = index.data(Qt.ItemDataRole.EditRole)
        if raw not in (None, ""):
            match = domain_match(
                self.editor.sheet, self.field, raw,
                **self.editor.domain_context(index.row(), self.field),
            )
            if governed and match is None:
                match = domain_match(self.editor.sheet, self.field, raw)
            option.text = match[1] if match else _text(raw)
        elif inactive:
            option.text = "—"

    def createEditor(self, parent, option, index):
        if not (index.flags() & Qt.ItemFlag.ItemIsEditable):
            return None
        combo = _DomainComboBox(self.editor.dialog, self.editor.sheet, self.field, parent)
        combo.activated.connect(lambda _index: self._finish(combo))
        return combo

    def _finish(self, combo):
        self.commitData.emit(combo)
        self.closeEditor.emit(combo)

    def setEditorData(self, combo, index):
        combo.load(
            index.data(Qt.ItemDataRole.EditRole),
            choices=self.editor.unit_choices(index.row(), self.field),
            **self.editor.domain_context(index.row(), self.field),
        )

    def setModelData(self, combo, model, index):
        if combo.touched and (index.flags() & Qt.ItemFlag.ItemIsEditable):
            model.setData(index, combo.raw_value(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, combo, option, index):
        combo.setGeometry(option.rect)


class _LabReferenceDelegate(QStyledItemDelegate):
    """Display readable in-draft identities while storing only their exact ID."""

    def __init__(self, editor, target):
        super().__init__(editor.table)
        self.sheet_editor = editor
        self.target = target

    def createEditor(self, parent, option, index):
        combo = _guarded_combo(QComboBox(parent))
        combo.setObjectName("qeoloogLabReference")
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo.addItem(self.sheet_editor.dialog.t("Vali viide"), "")
        for identifier, label in self.sheet_editor.dialog.lab_references(self.target):
            combo.addItem(label, identifier)
        active = _text(index.data(Qt.ItemDataRole.EditRole)).strip()
        if active and combo.findData(active) < 0:
            combo.addItem(
                self.sheet_editor.dialog.t("Olemasolev viide: {id}").format(id=active),
                active,
            )
        combo.activated.connect(lambda _index: self._finish(combo))
        return combo

    def _finish(self, editor):
        self.commitData.emit(editor)
        self.closeEditor.emit(editor)

    def setEditorData(self, editor, index):
        identifier = _text(index.data(Qt.ItemDataRole.EditRole)).strip()
        editor.setCurrentIndex(max(0, editor.findData(identifier)))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentData() or "", Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class _SheetEditor(QWidget):
    def __init__(self, dialog, sheet, fields, rows):
        super().__init__(dialog)
        self.dialog = dialog
        self.sheet = sheet
        self.fields = tuple(fields)
        layout = QVBoxLayout(self)
        if sheet == _UNITS:
            note = QLabel(dialog.t(_UNIT_RULE_HINT))
            note.setWordWrap(True)
            layout.addWidget(note)
        if sheet in {"geol_vahekiht_mall", "geol_mineraal_mall", "geol_fos_det_mall"}:
            note = QLabel(dialog.t("ID_ajutine viitab geoloogilise üksuse ID_ajutine väärtusele."))
            note.setWordWrap(True)
            layout.addWidget(note)
        self.table = QTableWidget(0, len(self.fields))
        self.table.setWordWrap(False)
        references = dialog.lab_links.get(sheet, {})
        self.domain_fields = frozenset(
            key for key in self.fields if key not in references and has_domain(sheet, key)
        )
        self.domain_parents = frozenset(
            parent for key in self.domain_fields for parent in domain_dependencies(sheet, key)
        )
        self.unit_rule_columns = {
            key: column for column, key in enumerate(self.fields)
            if sheet == _UNITS and key in UNIT_RULE_FIELDS
        }
        titles = {**_FIELD_LABELS, **_LAB_FIELD_LABELS} if sheet in dialog.lab_fields else _FIELD_LABELS

        def header(key):
            target = references.get(key)
            if key == _TEMP_ID and target:
                name = dialog.t("Viide: {table}").format(table=dialog.t(_SHEET_LABELS[target]))
            elif key in titles:
                name = dialog.t(titles[key])
            else:
                return key
            return f"{name}\n{key}"

        self.table.setHorizontalHeaderLabels([header(key) for key in self.fields])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for column, key in enumerate(self.fields):
            self.table.setColumnWidth(column, 180 if key in references or key in self.domain_fields else 125)
            if key in references:
                self.table.setItemDelegateForColumn(
                    column, _LabReferenceDelegate(self, references[key]),
                )
            elif key in self.domain_fields:
                self.table.setItemDelegateForColumn(column, _DomainDelegate(self, key))
        self.table.cellChanged.connect(self._refresh_domain_labels)
        controls = QHBoxLayout()
        actions = [(
            "Lisa rida",
            (lambda: dialog.add_lab_row(sheet))
            if sheet in dialog.lab_fields else (lambda: self.add_row({})),
        )]
        if sheet == _UNITS:
            actions.append(("Lisa järgmine kiht", self.add_next_unit))
        actions.append(("Eemalda valitud", self.delete_rows))
        for label, callback in actions:
            button = QPushButton(dialog.t(label))
            controls.addWidget(button)
            button.clicked.connect(callback)
        related = [
            (child, field) for child, links in dialog.lab_links.items()
            for field, target in links.items() if target == sheet
        ]
        if related:
            self.linked_row = QToolButton()
            self.linked_row.setText(dialog.t("Lisa seotud rida"))
            self.linked_row.setObjectName(f"qeoloogAddLinked_{sheet}")
            self.linked_row.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.linked_row.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            menu = QMenu(self.linked_row)
            for child, field in related:
                action = menu.addAction(dialog.t(_SHEET_LABELS[child]))
                action.triggered.connect(
                    lambda _=False, target=child, ref=field: dialog.add_linked_lab_row(sheet, target, ref)
                )
            self.linked_row.setMenu(menu)
            self.linked_row.setEnabled(False)
            self.table.itemSelectionChanged.connect(lambda: self.linked_row.setEnabled(
                len(self.table.selectionModel().selectedRows()) == 1
            ))
            controls.addWidget(self.linked_row)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(self.table)
        self.set_rows(rows)

    def _refresh_domain_labels(self, row, column):
        if not 0 <= column < len(self.fields):
            return
        field = self.fields[column]
        if self.unit_rule_columns and field in UNIT_RULE_PARENTS:
            self._refresh_unit_row(row)
        if field in self.domain_parents:
            self.table.viewport().update()

    def _unit_context(self, row):
        return {key: self.field_value(row, key) for key in UNIT_RULE_PARENTS}

    def unit_choices(self, row, field):
        if field not in self.unit_rule_columns:
            return None
        return unit_field_options(field, self._unit_context(row))

    def _refresh_unit_row(self, row):
        context = self._unit_context(row)
        blocked = self.table.blockSignals(True)
        try:
            for field, column in self.unit_rule_columns.items():
                item = self.table.item(row, column)
                if item is None:
                    continue
                flags = item.flags()
                active = bool(unit_field_options(field, context))
                editable = Qt.ItemFlag.ItemIsEditable
                next_flags = flags | editable if active else flags & ~editable
                if next_flags != flags:
                    item.setFlags(next_flags)
                item.setToolTip("" if active else self.dialog.t(_UNIT_LOCKED))
        finally:
            self.table.blockSignals(blocked)
        self.table.viewport().update()

    def add_row(self, record):
        row = self.table.rowCount()
        self.table.insertRow(row)
        blocked = self.table.blockSignals(True)
        try:
            for col, key in enumerate(self.fields):
                raw = record.get(key)
                item = QTableWidgetItem()
                if key in self.domain_fields:
                    item.setData(Qt.ItemDataRole.EditRole, raw)
                else:
                    item.setText(_text(raw))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record)
                self.table.setItem(row, col, item)
        finally:
            self.table.blockSignals(blocked)
        if self.unit_rule_columns:
            self._refresh_unit_row(row)
        return row

    def field_value(self, row, field):
        if field not in self.fields:
            return None
        item = self.table.item(row, self.fields.index(field))
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.EditRole) if field in self.domain_fields else item.text()

    def domain_context(self, row, field):
        dependencies = domain_dependencies(self.sheet, field)
        return {
            "row": {key: self.field_value(row, key) for key in dependencies if key in self.fields},
            "attrs": self.dialog.domain_attrs(dependencies),
        }

    def field_text(self, row, field):
        if field not in self.fields:
            return ""
        item = self.table.item(row, self.fields.index(field))
        return item.text().strip() if item else ""

    def select_new(self, row):
        columns = self.dialog.lab_links.get(self.sheet, {})
        column = next(
            (col for col, key in enumerate(self.fields) if key != _TEMP_ID and key not in columns),
            0,
        )
        item = self.table.item(row, column)
        self.table.setCurrentItem(item)
        self.table.scrollToItem(item)

    def add_next_unit(self):
        """Append an editable interval, inheriting only continuity and provenance."""
        row = self.table.rowCount() - 1
        inherited = {}
        if row >= 0:
            first = self.table.item(row, 0)
            original = (first.data(Qt.ItemDataRole.UserRole) if first else {}) or {}
            try:
                for source, target in _NEXT_UNIT_FIELDS:
                    column = self.fields.index(source)
                    item = self.table.item(row, column)
                    raw = item.text() if item else ""
                    if raw.strip().casefold() in {"", "null", "<null>", "none"}:
                        continue
                    if source in self.domain_fields:
                        inherited[target] = self.field_value(row, source)
                    else:
                        inherited[target] = editable_value(
                            self.sheet, source, raw,
                            original.get(source) if source == target else None,
                        )
            except SectionWorkspaceError as error:
                self.dialog._warning(error)
                return
        self.add_row(inherited)
        first = self.table.item(self.table.rowCount() - 1, 0)
        self.table.setCurrentItem(first)
        self.table.scrollToItem(first)

    def delete_rows(self):
        for index in sorted(self.table.selectionModel().selectedRows(), key=lambda value: value.row(), reverse=True):
            self.table.removeRow(index.row())

    def set_rows(self, rows):
        self.table.setRowCount(0)
        for row in rows:
            self.add_row(row)

    def rows(self):
        result = []
        for row in range(self.table.rowCount()):
            first = self.table.item(row, 0)
            original = first.data(Qt.ItemDataRole.UserRole) if first else {}
            original = original or {}
            record = dict(original)
            try:
                for col, field in enumerate(self.fields):
                    item = self.table.item(row, col)
                    if field in self.domain_fields:
                        value = item.data(Qt.ItemDataRole.EditRole) if item else original.get(field)
                    else:
                        value = editable_value(self.sheet, field, item.text() if item else "",
                                               original.get(field))
                    if value is not None or field in original:
                        record[field] = value
            except SectionWorkspaceError as error:
                raise SectionWorkspaceError(f"{self.sheet}, {row + 1}: {error}") from error
            if any(value not in (None, "") for value in record.values()):
                result.append(record)
        return result


class LocalObjectDialog(QDialog):
    """A draft is persisted only when the user confirms the complete form."""

    def __init__(self, plugin, parent, record, persist, map_pick=None):
        # A normal top-level window, not a modal sheet attached to QGIS.
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self._map_pick_pending = False
        self.finished.connect(self._end_map_pick)
        from .etl_workbooks import ETL6_FIELDS, ETL10_FIELDS, LAB_FIELDS, LAB_REFERENCES
        self.plugin, self.persist = plugin, persist
        self.lab_fields, self.lab_links = LAB_FIELDS, LAB_REFERENCES
        self.original = deepcopy(record or {"attributes": {}, "units": [], "related": {}})
        self.map_pick = map_pick
        self.result_record = None
        self.setWindowTitle(self.t("Kohalik objekt"))
        self.resize(960, 655)
        layout = QVBoxLayout(self)
        hint = QLabel(self.t("Kohalik muutmine ei muuda algallikat."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        source = _source_text(self.original)
        if source:
            label = QLabel(f"{self.t('Algallikas')}: {source}")
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            layout.addWidget(label)

        tabs = self.tabs = QTabWidget()
        layout.addWidget(tabs)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        general = QWidget()
        form = QFormLayout(general)
        fields = self.original["attributes"]
        self.inputs = {}
        self.domain_inputs = {}
        if self.map_pick:
            pick = QPushButton(self.t("Vali koordinaadid kaardilt"))
            pick.clicked.connect(self._pick_on_map)
            form.addRow(pick)
        for field in _fields(_GENERAL_FIRST, ETL6_FIELDS, fields):
            if has_domain(_GENERAL, field):
                control = _DomainComboBox(self, _GENERAL, field)
                self.domain_inputs[field] = control
            elif field in {"markus", "lisainfo"}:
                control = QPlainTextEdit(_text(fields.get(field)))
                control.setMaximumHeight(74)
            else:
                control = QLineEdit(_text(fields.get(field)))
                if field == "valmimise_kuupaev":
                    control.setPlaceholderText(self.t("Sisesta kuupäev AAAA-KK-PP"))
                elif field == "vertical_datum":
                    control.setPlaceholderText("EH2000 / BK77")
            title = self.t(_FIELD_LABELS.get(field, field))
            label = QLabel(title)
            label.setBuddy(control)
            label.setToolTip(field)
            form.addRow(label, control)
            self.inputs[field] = control
        for field, control in self.domain_inputs.items():
            attrs = self.domain_attrs(domain_dependencies(_GENERAL, field))
            control.load(fields.get(field), row=attrs, attrs=attrs)
        scroll.setWidget(general)
        tabs.addTab(scroll, self.t("Üldandmed"))
        self.sheets = {}
        related = self.original.get("related") or {}
        for sheet in _fields((_UNITS,), ETL10_FIELDS, related):
            if sheet in self.lab_fields:
                continue
            rows = self.original.get("units", []) if sheet == _UNITS else related.get(sheet, [])
            columns = _fields(_UNIT_FIRST if sheet == _UNITS else (),
                              ETL10_FIELDS.get(sheet, ()),
                              (field for row in rows for field in row))
            editor = _SheetEditor(self, sheet, columns or ("ID_ajutine",), rows)
            tabs.addTab(editor, self.t(_SHEET_LABELS.get(sheet, sheet)))
            self.sheets[sheet] = editor
        lab_page = self.lab_page = QWidget()
        lab_page.setObjectName("qeoloogLaboratory")
        lab_layout = QVBoxLayout(lab_page)
        lab_note = QLabel(self.t(_LAB_HELP))
        lab_note.setWordWrap(True)
        lab_layout.addWidget(lab_note)
        self.lab_tabs = QTabWidget()
        lab_layout.addWidget(self.lab_tabs, 1)
        for sheet, lab_columns in self.lab_fields.items():
            rows = related.get(sheet, [])
            first = (_TEMP_ID, *self.lab_links.get(sheet, ()))
            columns = _fields(
                (field for field in first if field in lab_columns), lab_columns,
                (field for row in rows for field in row),
            )
            editor = _SheetEditor(self, sheet, columns, rows)
            self.lab_tabs.addTab(editor, self.t(_SHEET_LABELS.get(sheet, sheet)))
            self.sheets[sheet] = editor
        tabs.addTab(lab_page, self.t("Laboriandmed"))
        parents = {
            parent for field in self.domain_inputs for parent in domain_dependencies(_GENERAL, field)
        }.union(*(editor.domain_parents for editor in self.sheets.values()))
        for field in parents.intersection(self.inputs):
            control = self.inputs[field]
            signal = control.valueChanged if isinstance(control, _DomainComboBox) else control.textChanged
            signal.connect(lambda *_args, key=field: self._refresh_dependants(key))

        actions = QHBoxLayout()
        for key, absolute in (("Arvuta paksused", False), ("Arvuta absoluutkõrgused", True)):
            button = QPushButton(self.t(key))
            button.clicked.connect(lambda _=False, value=absolute: self._calculate(value))
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def t(self, key):
        return _t(self.plugin, key)

    def domain_attrs(self, fields):
        values = {}
        for field in fields:
            control = self.inputs.get(field)
            if isinstance(control, _DomainComboBox):
                values[field] = control.raw_value()
            elif isinstance(control, QPlainTextEdit):
                values[field] = control.toPlainText()
            elif control is not None:
                values[field] = control.text()
        return values

    def _refresh_dependants(self, parent):
        for field, control in self.domain_inputs.items():
            dependencies = domain_dependencies(_GENERAL, field)
            if parent in dependencies:
                attrs = self.domain_attrs(dependencies)
                control.load(control.raw_value(), row=attrs, attrs=attrs)
        for editor in self.sheets.values():
            if parent in editor.domain_parents:
                editor.table.viewport().update()

    @staticmethod
    def _new_temp_id():
        # Deliberately not a bare UUID: it must not be mistaken for a database
        # GlobalID in the workbook or in a copied field.
        return f"QEO-{uuid4().hex}"

    def _object_temp_id(self):
        entry = self.inputs[_TEMP_ID]
        if not entry.text().strip():
            entry.setText(self._new_temp_id())
        return entry.text().strip()

    def lab_references(self, target):
        """Return existing explicit IDs plus human-readable combo captions."""
        from .etl_workbooks import lab_key

        if target is None:
            identifier = self.inputs[_TEMP_ID].text().strip()
            name = self.inputs["nimi"].text().strip() or self.inputs["alias"].text().strip()
            return [(identifier, f"{name} · {identifier}" if name else identifier)] if identifier else []
        editor = self.sheets.get(target)
        if editor is None:
            return []
        candidates = {}
        counts = {}
        for row in range(editor.table.rowCount()):
            for key in {
                lab_key(editor.field_text(row, field))
                for field in (_TEMP_ID, "globalid", "esri_globalid")
            } - {""}:
                counts[key] = counts.get(key, 0) + 1
            identifier = editor.field_text(row, _TEMP_ID)
            if not identifier:
                continue
            name = next((
                value for field in _LAB_NAMES if (value := editor.field_text(row, field))
            ), "")
            candidates[lab_key(identifier)] = (identifier, f"{name} · {identifier}" if name else identifier)
        return sorted(
            (item for key, item in candidates.items() if counts[key] == 1),
            key=lambda pair: pair[1].casefold(),
        )

    def add_lab_row(self, sheet, linked=None):
        """Create a local draft row; never edit upstream records or IDs."""
        if sheet not in self.lab_fields:
            return None
        values = dict(linked or {})
        if sheet in _LAB_IDS:
            values.setdefault(_TEMP_ID, self._new_temp_id())
        for field, target in self.lab_links.get(sheet, {}).items():
            if target is None and field not in values:
                values[field] = self._object_temp_id()
        editor = self.sheets[sheet]
        row = editor.add_row(values)
        self.tabs.setCurrentWidget(self.lab_page)
        self.lab_tabs.setCurrentWidget(editor)
        editor.select_new(row)
        return row

    def add_linked_lab_row(self, parent, target, reference):
        """Copy an unambiguous, explicitly selected parent ID into a child."""
        editor = self.sheets[parent]
        selected = editor.table.selectionModel().selectedRows()
        if len(selected) != 1:
            self._warning(self.t("Vali esmalt üks algkirje."))
            return None
        row = selected[0].row()
        identifier = editor.field_text(row, _TEMP_ID)
        if not identifier:
            identifier = self._new_temp_id()
            editor.table.item(row, editor.fields.index(_TEMP_ID)).setText(identifier)
        if identifier not in {value for value, _label in self.lab_references(parent)}:
            self._warning(self.t("Tunnus pole selles tabelis üheselt määratud: {id}.").format(id=identifier))
            return None
        return self.add_lab_row(target, {reference: identifier})

    def draft(self):
        result = deepcopy(self.original)
        attrs = result["attributes"]
        for field, control in self.inputs.items():
            previous = attrs.get(field)
            if isinstance(control, _DomainComboBox):
                value = control.raw_value()
            else:
                raw = control.toPlainText() if isinstance(control, QPlainTextEdit) else control.text()
                value = editable_value(_GENERAL, field, raw, previous)
            if value is not None or field in attrs:
                attrs[field] = value
        result["units"] = self.sheets[_UNITS].rows()
        result["related"] = {}
        for sheet, editor in self.sheets.items():
            if sheet != _UNITS:
                rows = editor.rows()
                if rows:
                    result["related"][sheet] = rows
        return result

    def _warning(self, error):
        QMessageBox.warning(self, self.t("Kohalikku objekti ei saanud avada või salvestada."), str(error))

    def _save(self):
        try:
            self.result_record = self.persist(self.draft())
        except SectionWorkspaceError as error:
            self._warning(error)
            return
        self.accept()

    def _calculate(self, absolute):
        if absolute and QMessageBox.question(
            self, self.t("Arvuta absoluutkõrgused"),
            self.t(_ABSOLUTE_PROMPT),
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            calculated = calculate_unit_geometry(self.draft(), absolute=absolute)
            for sheet in (_UNITS, "nahtus_mall"):
                if sheet in self.sheets:
                    self.sheets[sheet].set_rows(
                        calculated.get("units", []) if sheet == _UNITS else calculated["related"].get(sheet, [])
                    )
        except SectionWorkspaceError as error:
            self._warning(error)

    def _end_map_pick(self, *_):
        self._map_pick_pending = False

    def _pick_on_map(self):
        from qgis.PyQt import sip

        if self.map_pick is None or self._map_pick_pending:
            return
        self._map_pick_pending = True
        self.hide()

        def finished(*values):
            if sip.isdeleted(self) or not self._map_pick_pending:
                return
            self._end_map_pick()
            if len(values) == 2:
                for key, value in zip(("geom_x", "geom_y"), values):
                    self.inputs[key].setText(f"{float(value):.3f}")
            self.show()
            self.raise_()
            self.activateWindow()

        try:
            self.map_pick(finished)
        except (RuntimeError, ValueError, TypeError) as error:
            finished()
            QMessageBox.warning(self, self.t("Kaardilt valimine ebaõnnestus"), str(error))


class LocalObjectsWidget(QWidget):
    """Browse, find, create and edit records stored outside the QGIS project."""

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self._records = {}
        self._searchable = {}
        self._editor = None
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        paths = QHBoxLayout()
        for label, create in (("Loo töökaust…", True), ("Ava töökaust…", False)):
            choose = QPushButton(self.t(label))
            choose.clicked.connect(lambda _=False, option=create: self._choose_workspace(option))
            paths.addWidget(choose)
        paths.addStretch()
        layout.addLayout(paths)
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.t("Otsi kohalikest objektidest"))
        self.search.textChanged.connect(lambda: self._fill())
        layout.addWidget(self.search)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([self.t(key) for key in (
            "Nimi", "Objekti tüüp", "Algallikas", "ID",
        )])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda *_: self._open())
        self.table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.new = QPushButton(self.t("Uus objekt…"))
        self.new.clicked.connect(lambda: self._edit(None))
        self.open = QPushButton(self.t("Ava objekt"))
        self.open.clicked.connect(self._open)
        self.edit = QPushButton(self.t("Redigeeri…"))
        self.edit.clicked.connect(self.edit_selected)
        self.add_section = QPushButton(self.t("Lisa läbilõikele"))
        self.add_section.clicked.connect(self._add_to_section)
        self.lithology_report = QPushButton(self.t("Litotulp…"))
        self.lithology_report.setObjectName("qeoloogLocalLithologyReport")
        self.lithology_report.clicked.connect(self._open_lithology_report)
        for button in (self.new, self.open, self.edit, self.add_section, self.lithology_report):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.reload()

    def t(self, key):
        return _t(self.plugin, key)

    def _sections(self):
        return getattr(getattr(self.plugin, "dock", None), "cross_sections", None)

    def workspace(self):
        return getattr(self._sections(), "workspace", None)

    def _choose_workspace(self, create):
        sections = self._sections()
        if sections:
            sections._choose_workspace(create)
        self.reload()

    def _selected(self):
        items = self.table.selectedItems()
        item = items[0] if items else None
        key = item.data(Qt.ItemDataRole.UserRole) if item else None
        return self._records.get(key)

    def _selection_changed(self):
        selected = self._selected() is not None
        self.open.setEnabled(selected)
        self.edit.setEnabled(selected and self._editor is None)
        self.add_section.setEnabled(selected and callable(getattr(self.plugin, "add_local_object_to_section", None)))
        self.lithology_report.setEnabled(
            selected and callable(getattr(self.plugin, "open_local_lithology_report", None))
        )

    def reload(self, select_id=None):
        current = self._selected()
        select_id = select_id or (current.get("id") if current else None)
        workspace = self.workspace()
        self._records = {}
        self._searchable = {}
        self.new.setEnabled(workspace is not None and self._editor is None)
        if workspace is None:
            self.status.setText(self.t("Loo või ava läbilõigete töökaust, et kasutada kohalikke andmeid."))
        else:
            try:
                records = LocalObjectStore(workspace).list_objects()
                self._records = {record["id"]: record for record in records}
                self._searchable = {record["id"]: _search_text(record) for record in records}
                count = self.t("Kohalikke objekte: {count}").format(count=len(records))
                self.status.setText(f"{count}\n{workspace.folder}")
            except SectionWorkspaceError as error:
                self.status.setText(str(error))
        self._fill(select_id)

    def _fill(self, select_id=None):
        if select_id is None and self._selected():
            select_id = self._selected()["id"]
        query = self.search.text().casefold().split()
        self.table.setRowCount(0)
        for record_id, record in self._records.items():
            if not all(token in self._searchable[record_id] for token in query):
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (local_object_name(record), _text(record["attributes"].get("objekti_tyyp")),
                      _source_text(record), record_id)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record_id)
                self.table.setItem(row, column, item)
            if select_id == record_id:
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, 0))
        self._selection_changed()

    def _open(self):
        record = self._selected()
        callback = getattr(self.plugin, "show_local_object", None)
        if record and callable(callback):
            callback(deepcopy(record))

    def _add_to_section(self):
        record = self._selected()
        callback = getattr(self.plugin, "add_local_object_to_section", None)
        if record and callable(callback):
            callback(deepcopy(record))

    def _open_lithology_report(self):
        record = self._selected()
        callback = getattr(self.plugin, "open_local_lithology_report", None)
        if record and callable(callback):
            callback(deepcopy(record))

    def edit_selected(self):
        record = self._selected()
        if record is not None:
            self._edit(record)

    def _edit(self, record):
        workspace = self.workspace()
        if workspace is None or self._editor is not None:
            return
        baseline = deepcopy(record)

        def persist(draft):
            from .local_objects import LocalObjectConflict

            active = self.workspace()
            if (active is None or active.folder != workspace.folder
                    or active.workspace_id != workspace.workspace_id):
                raise SectionWorkspaceError(self.t(
                    "Töökaust muutus redigeerimise ajal. Ava objekt uuesti õiges töökaustas."
                ))
            store = LocalObjectStore(workspace)
            if baseline is None:
                return store.save(draft)
            try:
                return store.save_if_unchanged(draft, baseline)
            except LocalObjectConflict as error:
                raise SectionWorkspaceError(self.t(
                    "Objekt muutus redigeerimise ajal. Mustand jäi avatuks; "
                    "enne uut salvestust kopeeri oma muudatused ja ava ajakohane kirje."
                )) from error

        editor = self._editor = LocalObjectDialog(
            self.plugin, self, record, persist,
            map_pick=getattr(self._sections(), "_pick_local_anchor", None),
        )

        def closed(_code):
            self._editor = None
            saved = editor.result_record
            if saved:
                callback = getattr(self.plugin, "local_objects_changed", None)
                if callable(callback):
                    callback()
            self.reload(select_id=saved["id"] if saved else None)
            editor.deleteLater()

        editor.finished.connect(closed)
        editor.show()
        self.new.setEnabled(False)
        self._selection_changed()
