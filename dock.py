"""Configuration, filtering and EGT detail dock widgets."""

from datetime import datetime
from html import escape as html_escape
from math import floor, log10
from urllib.parse import quote

from qgis.PyQt.QtCore import QSize, Qt, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor, QDesktopServices, QPainter, QPen
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMenu,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from .corrections import core_correction_key, core_values
from .i18n import field_label
from .models import GROUPS, LayerDefinition
from .stratigraphy import STRATIGRAPHIC_INDICES
from .cross_section_widget import CrossSectionLauncher, CrossSectionWindow
from .export_widget import ExportWidget


def _table_sort_key(value):
    """Return a stable key for numeric, date and textual table values."""
    if isinstance(value, bool):
        return (2, str(value).casefold())
    if isinstance(value, (int, float)):
        return (0, float(value))
    text = _display_value(value).strip()
    if not text:
        return (3, "")
    numeric = text.replace(" ", "").replace(",", ".")
    try:
        return (0, float(numeric))
    except ValueError:
        pass
    for pattern in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            source = text[:19] if "T" in pattern else text
            parsed = datetime.strptime(source, pattern)
            return (
                1, parsed.toordinal(), parsed.hour,
                parsed.minute, parsed.second, parsed.microsecond,
            )
        except (OSError, ValueError):
            continue
    return (2, text.casefold())


class SortableTableItem(QTableWidgetItem):
    """QTableWidget item that sorts numbers and dates by their real values."""

    def __init__(self, value):
        display = _display_value(value)
        super().__init__(display)
        self._qeoloog_sort_key = _table_sort_key(value)

    def __lt__(self, other):
        if isinstance(other, SortableTableItem):
            return self._qeoloog_sort_key < other._qeoloog_sort_key
        return super().__lt__(other)


class CoreCorrectionDialog(QDialog):
    """Edit one drill-core box using standardized local fields."""

    def __init__(self, plugin, source, record_id, values, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.setWindowTitle(plugin.t("Muuda puursüdamiku kasti"))
        layout = QVBoxLayout(self)
        note = QLabel(plugin.t(
            "Muudatus salvestatakse ainult sellesse arvutisse; EGT ega "
            "SARV algandmeid ei muudeta."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        source_label = QLabel(str(source))
        source_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        identifier_label = QLabel(str(record_id))
        identifier_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        form.addRow(plugin.t("Allikas"), source_label)
        form.addRow(plugin.t("Kirje ID"), identifier_label)
        self.edits = {}
        for key, label in (
            ("number", "Kasti number"),
            ("top", "Ülemine sügavus, m"),
            ("bottom", "Alumine sügavus, m"),
            ("diameter", "Diameeter"),
            ("status", "Staatus / hoiukoht"),
        ):
            edit = QLineEdit()
            value = (values or {}).get(key)
            edit.setText("" if value in (None, "") else str(value))
            if key in {"top", "bottom", "diameter"}:
                edit.setPlaceholderText(plugin.t("Jäta tühjaks, kui puudub"))
            self.edits[key] = edit
            form.addRow(plugin.t(label), edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._values = None

    def _validate_and_accept(self):
        values = {}
        for key, edit in self.edits.items():
            text = edit.text().strip()
            if key not in {"top", "bottom", "diameter"}:
                values[key] = text or None
                continue
            if not text:
                values[key] = None
                continue
            try:
                value = float(text.replace(",", "."))
            except ValueError:
                QMessageBox.warning(
                    self, self.plugin.t("Vigane väärtus"),
                    self.plugin.t("Sügavus ja diameeter peavad olema arvud."),
                )
                return
            if value < 0:
                QMessageBox.warning(
                    self, self.plugin.t("Vigane väärtus"),
                    self.plugin.t("Sügavus ja diameeter ei saa olla negatiivsed."),
                )
                return
            values[key] = value
        top, bottom = values.get("top"), values.get("bottom")
        if top is not None and bottom is not None and bottom <= top:
            QMessageBox.warning(
                self, self.plugin.t("Vigane väärtus"),
                self.plugin.t(
                    "Alumine sügavus peab olema ülemisest sügavusest suurem."
                ),
            )
            return
        self._values = values
        self.accept()

    def values(self):
        return dict(self._values or {})


class MultiSelectButton(QToolButton):
    """Scrollable multi-select that remains open while options are checked."""

    selectionChanged = pyqtSignal()

    def __init__(self, all_text, parent=None):
        super().__init__(parent)
        self.all_text = all_text
        self._items = {}
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        host = QWidget(menu)
        host.setMinimumWidth(320)
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(6, 6, 6, 6)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter…")
        self._search.textChanged.connect(self._filter)
        host_layout.addWidget(self._search)
        self._list = QListWidget()
        self._list.setMinimumHeight(120)
        self._list.setMaximumHeight(300)
        self._list.itemChanged.connect(self._changed)
        host_layout.addWidget(self._list)
        clear_button = QPushButton("×")
        clear_button.setToolTip(all_text)
        clear_button.clicked.connect(self.clear_selection)
        host_layout.addWidget(clear_button)
        action = QWidgetAction(menu)
        action.setDefaultWidget(host)
        menu.addAction(action)
        self.setMenu(menu)
        self._update_text()

    def set_options(self, options):
        selected = self.selected_values()
        self._list.blockSignals(True)
        self._list.clear()
        self._items = {}
        for value, label in options:
            item = QListWidgetItem(str(label), self._list)
            item.setData(Qt.ItemDataRole.UserRole, str(value))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if str(value) in selected else Qt.CheckState.Unchecked
            )
            self._items[str(value)] = item
        self._list.blockSignals(False)
        self._filter(self._search.text())
        self._update_text()

    def selected_values(self):
        return {
            value for value, item in self._items.items()
            if item.checkState() == Qt.CheckState.Checked
        }

    def clear_selection(self):
        self._list.blockSignals(True)
        for item in self._items.values():
            item.setCheckState(Qt.CheckState.Unchecked)
        self._list.blockSignals(False)
        self._update_text()
        self.selectionChanged.emit()

    def set_selected_values(self, values):
        selected = {str(value) for value in values}
        self._list.blockSignals(True)
        for value, item in self._items.items():
            item.setCheckState(
                Qt.CheckState.Checked
                if value in selected else Qt.CheckState.Unchecked
            )
        self._list.blockSignals(False)
        self._update_text()
        self.selectionChanged.emit()

    def _changed(self, _item=None):
        self._update_text()
        self.selectionChanged.emit()

    def _filter(self, text):
        needle = str(text or "").casefold()
        for item in self._items.values():
            item.setHidden(needle not in item.text().casefold())

    def _update_text(self):
        selected = [
            item.text() for item in self._items.values()
            if item.checkState() == Qt.CheckState.Checked
        ]
        if not selected:
            text = self.all_text
        elif len(selected) <= 2:
            text = ", ".join(selected)
        else:
            text = f"{len(selected)}"
        self.setText(text)
        self.setToolTip(", ".join(selected) if selected else self.all_text)


class LayerConfigWidget(QWidget):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self._editing_index = -1
        self._build_ui()
        self.reload_list()

    def _build_ui(self):
        t = self.plugin.t
        layout = QVBoxLayout(self)

        preferences = QGroupBox(t("Rippmenüüde nähtavus"))
        preferences_layout = QVBoxLayout(preferences)
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel(t("Kasutajaliidese keel")))
        self.language = QComboBox()
        self.language.addItem(t("Eesti"), "et")
        self.language.addItem(t("Inglise"), "en")
        self.language.setCurrentIndex(self.language.findData(self.plugin.language))
        self.language.currentIndexChanged.connect(
            lambda: self.plugin.set_language(self.language.currentData())
        )
        language_row.addWidget(self.language)
        preferences_layout.addLayout(language_row)
        self.group_checks = {}
        group_row = QHBoxLayout()
        for group in GROUPS:
            checkbox = QCheckBox(self.plugin.group_name(group))
            checkbox.setChecked(self.plugin.group_enabled.get(group, True))
            checkbox.toggled.connect(
                lambda checked, key=group: self.plugin.set_group_enabled(key, checked)
            )
            self.group_checks[group] = checkbox
            group_row.addWidget(checkbox)
        preferences_layout.addLayout(group_row)
        layout.addWidget(preferences)

        egt_source = QGroupBox(t("EGT detailandmete allikas"))
        egt_source_layout = QFormLayout(egt_source)
        self.egt_data_source = QComboBox()
        self.egt_data_source.addItem(t("WFS – kiirem laadimine"), "wfs")
        self.egt_data_source.addItem(t("API – kiiremini uuenevad andmed"), "api")
        self.egt_data_source.setCurrentIndex(
            self.egt_data_source.findData(self.plugin.egt_data_source)
        )
        self.egt_data_source.currentIndexChanged.connect(
            lambda: self.plugin.set_egt_data_source(
                self.egt_data_source.currentData()
            )
        )
        egt_source_layout.addRow(t("Puuraugud ja vaatluspunktid"), self.egt_data_source)
        egt_note = QLabel(t(
            "API valik kasutab puuraukudel GEA API-t. Vaatluspunktide "
            "detailandmeid avalik GEA API praegu ei paku, seega kasutatakse "
            "nende puhul WFS-i."
        ))
        egt_note.setWordWrap(True)
        egt_source_layout.addRow(egt_note)
        layout.addWidget(egt_source)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.currentRowChanged.connect(self._select_row)
        self.list_widget.itemChanged.connect(self._item_checked)
        top_layout.addWidget(self.list_widget)
        order_row = QHBoxLayout()
        for text, slot in (
            (t("Üles"), lambda: self._move(-1)),
            (t("Alla"), lambda: self._move(1)),
            (t("Eemalda"), self._remove),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            order_row.addWidget(button)
        top_layout.addLayout(order_row)
        splitter.addWidget(top)

        form_host = QWidget()
        form_host_layout = QVBoxLayout(form_host)
        form = QFormLayout()
        self.protocol = QComboBox()
        self.protocol.addItems(["WMS", "WFS", "SARV", "VEKA"])
        self.code = QLineEdit()
        self.code.setMaxLength(4)
        self.name = QLineEdit()
        self.name_en = QLineEdit()
        self.url = QLineEdit()
        self.layer_name = QComboBox()
        self.layer_name.setEditable(True)
        self.style = QLineEdit()
        self.base_map = QCheckBox(t("Paiguta kihipuu alla"))
        self.home_group = QComboBox()
        for group in GROUPS:
            self.home_group.addItem(self.plugin.group_name(group), group)
        self.placement = QComboBox()
        for title, value in (
            (t("Põhiriba"), "toolbar"),
            (t("Rippmenüü"), "dropdown"),
            (t("Keelatud"), "disabled"),
        ):
            self.placement.addItem(title, value)
        self.color = QLineEdit("#356a8a")
        color_button = QPushButton(t("Vali..."))
        color_button.clicked.connect(self._choose_color)
        color_row = QWidget()
        color_layout = QHBoxLayout(color_row)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.addWidget(self.color)
        color_layout.addWidget(color_button)
        form.addRow(t("Teenus"), self.protocol)
        form.addRow(t("Nupu tähis"), self.code)
        form.addRow(t("Kihi nimi"), self.name)
        form.addRow(t("Ingliskeelne nimi"), self.name_en)
        form.addRow(t("Teenuse URL"), self.url)
        form.addRow(t("Teenuse kiht"), self.layer_name)
        form.addRow(t("WMS stiil"), self.style)
        form.addRow(t("Ikooni värv"), color_row)
        form.addRow(t("Kodu"), self.home_group)
        form.addRow(t("Paigutus"), self.placement)
        form.addRow(t("Kihipuu asukoht"), self.base_map)
        form_host_layout.addLayout(form)

        button_row = QHBoxLayout()
        read_button = QPushButton(t("Loe kihid"))
        read_button.clicked.connect(self._read_capabilities)
        new_button = QPushButton(t("Uus"))
        new_button.clicked.connect(self.clear_form)
        self.save_button = QPushButton(t("Lisa"))
        self.save_button.clicked.connect(self._save)
        button_row.addWidget(read_button)
        button_row.addWidget(new_button)
        button_row.addWidget(self.save_button)
        form_host_layout.addLayout(button_row)

        reset_button = QPushButton(t("Taasta algne kihikataloog"))
        reset_button.clicked.connect(self._reset)
        form_host_layout.addWidget(reset_button)
        self.toggle_mode = QCheckBox(t(
            "Sisse/välja režiim: korduv nupuvajutus eemaldab olemasoleva kihi projektist"
        ))
        self.toggle_mode.setChecked(self.plugin.toggle_mode)
        self.toggle_mode.toggled.connect(self.plugin.set_toggle_mode)
        form_host_layout.addWidget(self.toggle_mode)
        export_button = QPushButton(t("Ekspordi SARV seosed…"))
        export_button.clicked.connect(self._export_sarv_matches)
        form_host_layout.addWidget(export_button)
        splitter.addWidget(form_host)
        splitter.setSizes([220, 360])

    def _export_sarv_matches(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.plugin.t("Ekspordi SARV seosed"),
            "qeoloog_sarv_seosed.csv",
            "CSV (*.csv);;JSON (*.json)",
        )
        if path:
            self.plugin.export_sarv_matches(path)

    def reload_list(self, select=None):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for definition in self.plugin.definitions:
            placement = {
                "toolbar": self.plugin.t("Põhiriba"),
                "dropdown": self.plugin.t("Rippmenüü"),
                "disabled": self.plugin.t("Keelatud"),
            }.get(definition.placement, definition.placement)
            self.list_widget.addItem(
                f"{definition.code} - {self.plugin.display_name(definition)} "
                f"[{self.plugin.group_name(definition.home_group)} / {placement}]"
            )
            item = self.list_widget.item(self.list_widget.count() - 1)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Unchecked
                if definition.placement == "disabled" else Qt.CheckState.Checked
            )
        self.list_widget.blockSignals(False)
        if select is not None and 0 <= select < self.list_widget.count():
            self.list_widget.setCurrentRow(select)

    def clear_form(self):
        self._editing_index = -1
        self.list_widget.clearSelection()
        self.protocol.setCurrentText("WMS")
        self.code.clear()
        self.name.clear()
        self.name_en.clear()
        self.url.clear()
        self.layer_name.clear()
        self.style.clear()
        self.color.setText("#356a8a")
        self.base_map.setChecked(False)
        self.home_group.setEnabled(True)
        self.home_group.setCurrentIndex(self.home_group.findData("helpers"))
        self.placement.setCurrentIndex(self.placement.findData("dropdown"))
        self.save_button.setText(self.plugin.t("Lisa"))

    def _item_checked(self, item):
        row = self.list_widget.row(item)
        if row < 0 or row >= len(self.plugin.definitions):
            return
        definition = self.plugin.definitions[row]
        checked = item.checkState() == Qt.CheckState.Checked
        new_placement = (
            definition.previous_placement
            if checked and definition.placement == "disabled"
            else "disabled" if not checked
            else definition.placement
        )
        if new_placement == definition.placement:
            return
        if definition.placement in {"toolbar", "dropdown"}:
            definition.previous_placement = definition.placement
        definition.placement = new_placement
        self.plugin._save_definitions()
        self.reload_list(row)

    def _select_row(self, row):
        if row < 0 or row >= len(self.plugin.definitions):
            return
        self._editing_index = row
        definition = self.plugin.definitions[row]
        self.protocol.setCurrentText(definition.protocol)
        self.code.setText(definition.code)
        self.name.setText(definition.name)
        self.name_en.setText(definition.name_en)
        self.url.setText(definition.url)
        self.layer_name.setEditText(definition.layer_name)
        self.style.setText(definition.style)
        self.color.setText(definition.color)
        self.base_map.setChecked(definition.base_map)
        self.home_group.setCurrentIndex(self.home_group.findData(definition.home_group))
        self.home_group.setEnabled(False)
        self.placement.setCurrentIndex(self.placement.findData(definition.placement))
        self.save_button.setText(self.plugin.t("Uuenda"))

    def _choose_color(self):
        color = QColorDialog.getColor(
            QColor(self.color.text()), self, self.plugin.t("Vali ikooni värv")
        )
        if color.isValid():
            self.color.setText(color.name())

    def _read_capabilities(self):
        url = self.url.text().strip()
        if not url:
            QMessageBox.warning(
                self, "Qeoloog",
                "Enter the service URL." if self.plugin.language == "en" else "Sisesta teenuse URL."
            )
            return
        if self.protocol.currentText().upper() in {"SARV", "VEKA"}:
            self.plugin.message(
                "This point catalog is fixed and does not use GetCapabilities."
                if self.plugin.language == "en"
                else "See punktikataloog on fikseeritud ega kasuta GetCapabilities päringut."
            )
            return
        self.plugin.message(
            "Loading the service layer list..." if self.plugin.language == "en"
            else "Teenuse kihtide loendit laaditakse..."
        )
        self.plugin.network.get_capabilities(
            self.protocol.currentText(),
            url,
            self._capabilities_loaded,
            lambda error: self.plugin.error(
                (f"GetCapabilities failed: {error}" if self.plugin.language == "en"
                 else f"GetCapabilities ebaõnnestus: {error}")
            ),
        )

    def _capabilities_loaded(self, layers):
        current = self.layer_name.currentText()
        self.layer_name.clear()
        for layer_name, title in layers:
            self.layer_name.addItem(f"{title} — {layer_name}", layer_name)
        if current:
            index = self.layer_name.findData(current)
            if index >= 0:
                self.layer_name.setCurrentIndex(index)
            else:
                self.layer_name.setEditText(current)
        self.plugin.success(
            f"Found {len(layers)} layers." if self.plugin.language == "en"
            else f"Leiti {len(layers)} kihti."
        )

    def _save(self):
        protocol = self.protocol.currentText().upper()
        code = self.code.text().strip().upper()
        name = self.name.text().strip()
        url = self.url.text().strip()
        layer_name = self.layer_name.currentData() or self.layer_name.currentText().strip()
        if " — " in layer_name and self.layer_name.currentData() is None:
            layer_name = layer_name.rsplit(" — ", 1)[-1]
        if not all((code, name, url, layer_name)):
            QMessageBox.warning(
                self, "Qeoloog",
                ("Code, name, URL and service layer are required."
                 if self.plugin.language == "en" else
                 "Tähis, nimi, URL ja teenuse kiht on kohustuslikud.")
            )
            return
        lower_name = layer_name.lower()
        role = ""
        if protocol == "SARV":
            role = "sarv_points"
        elif protocol == "VEKA":
            role = "veka_boreholes"
        elif lower_name.endswith(":puurauk") or lower_name == "puurauk":
            role = "boreholes"
        elif lower_name.endswith(":vaatluspunkt") or lower_name == "vaatluspunkt":
            role = "observations"
        placement = self.placement.currentData() or "dropdown"
        previous_placement = placement if placement != "disabled" else "dropdown"
        if 0 <= self._editing_index < len(self.plugin.definitions):
            current = self.plugin.definitions[self._editing_index]
            if placement == "disabled":
                previous_placement = (
                    current.placement
                    if current.placement in {"toolbar", "dropdown"}
                    else current.previous_placement
                )
        definition = LayerDefinition(
            code=code,
            name=name,
            protocol=protocol,
            url=url,
            layer_name=layer_name,
            style=self.style.text().strip(),
            base_map=self.base_map.isChecked(),
            color=self.color.text().strip() or "#356a8a",
            role=role,
            name_en=self.name_en.text().strip(),
            home_group=self.home_group.currentData() or "helpers",
            placement=placement,
            previous_placement=previous_placement,
        )
        index = self.plugin.upsert_definition(self._editing_index, definition)
        self.reload_list(index)

    def _remove(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.plugin.remove_definition(row)
            self.reload_list()
            self.clear_form()

    def _move(self, delta):
        row = self.list_widget.currentRow()
        target = self.plugin.move_definition(row, delta)
        self.reload_list(target)

    def _reset(self):
        answer = QMessageBox.question(
            self,
            "Qeoloog",
            ("Replace the current catalog with the default Qeoloog catalog?"
             if self.plugin.language == "en" else
             "Kas asendada praegune kataloog Qeoloogi algse kihikataloogiga?"),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.plugin.reset_definitions()
            self.reload_list(0)


class FilterWidget(QWidget):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self._resetting = False
        self._pending_analysis_code = ""
        self._pending_analysis_code = ""
        t = plugin.t
        layout = QVBoxLayout(self)

        layer_group = QGroupBox(t("EGT kihid"))
        layer_layout = QVBoxLayout(layer_group)
        self.boreholes = QCheckBox(t("Puuraugud"))
        self.observations = QCheckBox(t("Vaatluspunktid"))
        self.boreholes.setChecked(True)
        self.observations.setChecked(True)
        layer_layout.addWidget(self.boreholes)
        layer_layout.addWidget(self.observations)
        layout.addWidget(layer_group)

        category_group = QGroupBox(t("Ulatus"))
        category_layout = QVBoxLayout(category_group)
        self.categories = {}
        for code, title in ((1, "Pinnakate"), (2, "Aluspõhi"), (3, "Aluskord"), (997, "Muu / teadmata")):
            checkbox = QCheckBox(t(title))
            checkbox.setChecked(True)
            self.categories[code] = checkbox
            category_layout.addWidget(checkbox)
        layout.addWidget(category_group)

        index_group = QGroupBox(t("Indeksi filtrid"))
        index_layout = QFormLayout(index_group)
        self.stratigraphic_index = MultiSelectButton(t("Kõik"))
        self.stratigraphic_index.set_options(
            (index, index) for index in STRATIGRAPHIC_INDICES
        )
        self.stratigraphic_index.selectionChanged.connect(self._changed)
        self.stratigraphic_contains = QLineEdit()
        self.stratigraphic_contains.setPlaceholderText(t("Sisaldab"))
        self.stratigraphic_contains.editingFinished.connect(self._changed)
        index_layout.addRow(t("Indeks"), self.stratigraphic_index)
        index_layout.addRow(t("Sisaldab"), self.stratigraphic_contains)
        layout.addWidget(index_group)

        related_group = QGroupBox(t("Seotud andmed"))
        related_layout = QFormLayout(related_group)
        self.related = {}
        for key, title in (
            ("core", "Puursüdamik olemas"),
            ("samples", "Proovid olemas"),
            ("analyses", "Analüüsid olemas"),
            ("attachments", "Manused olemas"),
        ):
            choice = QComboBox()
            choice.addItem(t("Kõik"), "any")
            choice.addItem(t("Jah"), "yes")
            choice.addItem(t("Ei"), "no")
            choice.currentIndexChanged.connect(self._changed)
            self.related[key] = choice
            related_layout.addRow(t(title), choice)
        layout.addWidget(related_group)

        sample_group = QGroupBox(t("Proovide filtrid"))
        sample_layout = QFormLayout(sample_group)
        self.sample_filters = {}
        for field, title in (
            ("proov_tyyp", "Proovi tüüp"),
            ("eesmark", "Proovi eesmärk"),
            ("staatus", "Proovi staatus"),
        ):
            choice = MultiSelectButton(t("Kõik"))
            choice.selectionChanged.connect(self._changed)
            self.sample_filters[field] = choice
            sample_layout.addRow(t(title), choice)
        layout.addWidget(sample_group)

        analysis_group = QGroupBox(t("Analüüside filtrid"))
        analysis_layout = QFormLayout(analysis_group)
        self.analysis_filters = {}
        for table_id, field, title in (
            (3, "analyys_meetod", "Analüüsi meetod"),
            (3, "labor", "Analüüsi labor"),
            (4, "analyys_tulem_tyyp", "Tulemuse tüüp"),
            (4, "analyys_naitaja", "Analüüsi näitaja"),
        ):
            choice = MultiSelectButton(t("Kõik"))
            choice.selectionChanged.connect(self._changed)
            self.analysis_filters[(table_id, field)] = choice
            analysis_layout.addRow(t(title), choice)
        layout.addWidget(analysis_group)

        self.identify_button = QPushButton(t("Klõpsa objektil ja ava andmed"))
        self.identify_button.setCheckable(True)
        self.identify_button.toggled.connect(self.plugin.set_identify_active)
        layout.addWidget(self.identify_button)
        reset_button = QPushButton(t("Lähtesta"))
        reset_button.clicked.connect(self.reset)
        layout.addWidget(reset_button)
        note = QLabel(
            ("Borehole and observation-point filters apply to WFS vector layers. "
             "The observation-point dataset currently contains no basement records."
             if plugin.language == "en" else
             "Puuraukude ja vaatluspunktide filtrid rakenduvad WFS-vektorkihtidele. "
             "Vaatluspunktide andmestikus aluskorda praegu ei esine.")
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

        self.boreholes.stateChanged.connect(self._changed)
        self.observations.stateChanged.connect(self._changed)
        for checkbox in self.categories.values():
            checkbox.stateChanged.connect(self._changed)
        self.reload_domain_options()

    def _changed(self):
        if not self._resetting:
            self.plugin.apply_egt_filters()

    def reset(self):
        self._resetting = True
        try:
            self.boreholes.setChecked(True)
            self.observations.setChecked(True)
            for checkbox in self.categories.values():
                checkbox.setChecked(True)
            self.stratigraphic_index.clear_selection()
            self.stratigraphic_contains.clear()
            for choice in self.related.values():
                choice.setCurrentIndex(0)
            for choice in self.sample_filters.values():
                choice.clear_selection()
            for choice in self.analysis_filters.values():
                choice.clear_selection()
        finally:
            self._resetting = False
        self.plugin.apply_egt_filters()

    def selected_codes(self):
        return {code for code, checkbox in self.categories.items() if checkbox.isChecked()}

    def related_requirements(self):
        return {key: choice.currentData() for key, choice in self.related.items()}

    def stratigraphic_requirements(self):
        return {
            "indices": self.stratigraphic_index.selected_values(),
            "contains": self.stratigraphic_contains.text().strip(),
        }

    def egt_domain_requirements(self):
        return {
            "samples": {
                field: choice.selected_values()
                for field, choice in self.sample_filters.items()
            },
            "analyses": {
                key: choice.selected_values()
                for key, choice in self.analysis_filters.items()
            },
        }

    def reload_domain_options(self):
        for field, choice in self.sample_filters.items():
            choice.set_options(self.plugin.egt_options(18, field))
        for (table_id, field), choice in self.analysis_filters.items():
            choice.set_options(self.plugin.egt_options(table_id, field))

    def set_identify_checked(self, checked):
        self.identify_button.blockSignals(True)
        self.identify_button.setChecked(checked)
        self.identify_button.blockSignals(False)


class SarvFilterWidget(QWidget):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self._resetting = False
        t = plugin.t
        layout = QVBoxLayout(self)

        kinds = QGroupBox(t("Objekti liigid"))
        kinds_layout = QVBoxLayout(kinds)
        self.kinds = {}
        for role, title in (
            ("sarv_localities", "Lokaliteedid"),
            ("sarv_sites", "Uuringupunktid"),
            ("sarv_drillcores", "Puursüdamikud"),
        ):
            checkbox = QCheckBox(t(title))
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._changed)
            self.kinds[role] = checkbox
            kinds_layout.addWidget(checkbox)
        layout.addWidget(kinds)

        extent_group = QGroupBox(t("Asukoht ja sügavus"))
        extent_layout = QFormLayout(extent_group)
        self.current_extent = QCheckBox(t("Ainult kaardi praegune ulatus"))
        self.current_extent.toggled.connect(self._changed)
        extent_layout.addRow(self.current_extent)
        self.depth_min = QLineEdit()
        self.depth_max = QLineEdit()
        self.depth_min.setPlaceholderText("0")
        self.depth_max.setPlaceholderText("m")
        self.depth_min.editingFinished.connect(self._changed)
        self.depth_max.editingFinished.connect(self._changed)
        extent_layout.addRow(t("Min sügavus"), self.depth_min)
        extent_layout.addRow(t("Max sügavus"), self.depth_max)
        layout.addWidget(extent_group)

        related_group = QGroupBox(t("Seotud andmed"))
        related_layout = QFormLayout(related_group)
        self.related = {}
        for key, title in (
            ("core", "Puursüdamik olemas"),
            ("samples", "Proovid olemas"),
            ("analyses", "Analüüsid olemas"),
            ("specimens", "Eksemplarid olemas"),
        ):
            choice = QComboBox()
            choice.addItem(t("Kõik"), "any")
            choice.addItem(t("Jah"), "yes")
            choice.addItem(t("Ei"), "no")
            choice.currentIndexChanged.connect(self._changed)
            self.related[key] = choice
            related_layout.addRow(t(title), choice)
        layout.addWidget(related_group)

        sample_group = QGroupBox(t("Proovide filtrid"))
        sample_layout = QFormLayout(sample_group)
        self.sample_purpose = MultiSelectButton(t("Kõik"))
        self.sample_type = MultiSelectButton(t("Kõik"))
        self.sample_purpose.set_options(plugin.sarv_purpose_options())
        self.sample_purpose.selectionChanged.connect(self._changed)
        self.sample_type.selectionChanged.connect(self._changed)
        sample_layout.addRow(t("Proovi eesmärk"), self.sample_purpose)
        sample_layout.addRow(t("Proovi tüüp"), self.sample_type)
        layout.addWidget(sample_group)

        analysis_group = QGroupBox(t("Analüüside filtrid"))
        analysis_layout = QFormLayout(analysis_group)
        self.analysis_method = MultiSelectButton(t("Kõik"))
        self.analysis_method.selectionChanged.connect(self._changed)
        analysis_layout.addRow(t("Analüüsi meetod"), self.analysis_method)
        layout.addWidget(analysis_group)

        specimen_group = QGroupBox(t("Eksemplaride filtrid"))
        specimen_layout = QFormLayout(specimen_group)
        self.specimen_type = MultiSelectButton(t("Kõik"))
        self.specimen_type.selectionChanged.connect(self._changed)
        specimen_layout.addRow(t("Eksemplari tüüp"), self.specimen_type)
        layout.addWidget(specimen_group)

        note = QLabel(
            t("SARV seotud andmete filtrid päritakse vajadusel serverist. "
              "Tühi valik tähendab kõiki väärtusi.")
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        reset_button = QPushButton(t("Lähtesta"))
        reset_button.clicked.connect(self.reset)
        layout.addWidget(reset_button)
        layout.addStretch(1)
        self.reload_options()

    def reload_options(self):
        self.analysis_method.set_options(self.plugin.sarv_analysis_options)
        self.sample_type.set_options(self.plugin.sarv_sample_type_options)
        self.specimen_type.set_options(
            self.plugin.sarv_specimen_type_options
        )

    def requirements(self):
        def number(widget):
            try:
                return float(widget.text().strip()) if widget.text().strip() else None
            except ValueError:
                return None

        return {
            "kinds": {
                role for role, checkbox in self.kinds.items()
                if checkbox.isChecked()
            },
            "current_extent": self.current_extent.isChecked(),
            "depth_min": number(self.depth_min),
            "depth_max": number(self.depth_max),
            "related": {
                key: choice.currentData() for key, choice in self.related.items()
            },
            "sample_purpose": self.sample_purpose.selected_values(),
            "sample_type": self.sample_type.selected_values(),
            "analysis_method": self.analysis_method.selected_values(),
            "specimen_type": self.specimen_type.selected_values(),
        }

    def _changed(self):
        if not self._resetting:
            self.plugin.apply_sarv_filters()

    def reset(self):
        self._resetting = True
        try:
            for checkbox in self.kinds.values():
                checkbox.setChecked(True)
            self.current_extent.setChecked(False)
            self.depth_min.clear()
            self.depth_max.clear()
            for choice in self.related.values():
                choice.setCurrentIndex(0)
            self.sample_purpose.clear_selection()
            self.sample_type.clear_selection()
            self.analysis_method.clear_selection()
            self.specimen_type.clear_selection()
        finally:
            self._resetting = False
        self.plugin.apply_sarv_filters()


class VekaWidget(QWidget):
    """VEKA well filters and a focused graduated-symbology designer."""

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self._resetting = False
        t = plugin.t
        layout = QVBoxLayout(self)

        search_group = QGroupBox(t("VEKA otsing ja filtrid"))
        form = QFormLayout(search_group)
        self.text = QLineEdit()
        self.text.setPlaceholderText(t("Nimi, aadress või ID"))
        self.text.editingFinished.connect(self._changed)
        form.addRow(t("Otsing"), self.text)
        self.purpose = MultiSelectButton(t("Kõik"))
        self.groundwater = MultiSelectButton(t("Kõik"))
        self.purpose.selectionChanged.connect(self._changed)
        self.groundwater.selectionChanged.connect(self._changed)
        form.addRow(t("Otstarve"), self.purpose)
        form.addRow(t("Põhjaveekogum"), self.groundwater)
        self.year_min, self.year_max, year_row = self._range_row(
            t("Alates"), t("Kuni")
        )
        form.addRow(t("Puurimise aasta"), year_row)
        self.filter_min, self.filter_max, filter_row = self._range_row(
            f"{t('Min')} (m)", f"{t('Max')} (m)"
        )
        form.addRow(t("Filtri paigutussügavus"), filter_row)
        self.hydro_mode = self._mode_combo(include_any=True)
        self.hydro_mode.currentIndexChanged.connect(self._changed)
        form.addRow(t("Mitme pumpamiskatse käsitlus"), self.hydro_mode)
        self.debit_min, self.debit_max, debit_row = self._range_row(
            f"{t('Min')} (l/s)", f"{t('Max')} (l/s)"
        )
        form.addRow(f"{t('Deebit')} (l/s)", debit_row)
        self.specific_min, self.specific_max, specific_row = self._range_row(
            f"{t('Min')} (l/(s·m))", f"{t('Max')} (l/(s·m))"
        )
        form.addRow(f"{t('Eritootlikkus')} (l/(s·m))", specific_row)
        hydro_help = QLabel(t(
            "Deebit on katsepumpamisel mõõdetud veehulk. Eritootlikkus = "
            "deebit / veetaseme alandus. Valik määrab, kuidas sama puurkaevu "
            "mitut pumpamiskatset käsitletakse."
        ))
        hydro_help.setWordWrap(True)
        hydro_help.setStyleSheet("color: #6b6b6b;")
        form.addRow(hydro_help)
        for widget in (
            self.year_min, self.year_max, self.filter_min, self.filter_max,
            self.debit_min, self.debit_max, self.specific_min,
            self.specific_max,
        ):
            widget.editingFinished.connect(self._changed)
        layout.addWidget(search_group)

        analysis_group = QGroupBox(t("Veeproovi tulemused"))
        analysis_form = QFormLayout(analysis_group)
        self.analysis = QComboBox()
        self.analysis.setEditable(True)
        self.analysis.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.analysis.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.analysis.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.analysis.setMaxVisibleItems(25)
        self.analysis.addItem(t("Kõik"), "")
        self.analysis.currentIndexChanged.connect(self._changed)
        analysis_form.addRow(t("Näitaja"), self.analysis)
        self.load_analysis = QPushButton(t("Laadi veeproovi näitajad"))
        self.load_analysis.clicked.connect(plugin.ensure_veka_analysis_options)
        analysis_form.addRow(self.load_analysis)
        self.analysis_mode = self._mode_combo(include_any=True)
        self.analysis_mode.currentIndexChanged.connect(self._changed)
        analysis_form.addRow(t("Mitme veeproovi käsitlus"), self.analysis_mode)
        self.analysis_min, self.analysis_max, analysis_row = self._range_row("Min", "Max")
        self.analysis_min.editingFinished.connect(self._changed)
        self.analysis_max.editingFinished.connect(self._changed)
        analysis_form.addRow(t("Tulemuse vahemik"), analysis_row)
        self.analysis_year_min, self.analysis_year_max, analysis_year_row = self._range_row(
            "Min", "Max"
        )
        self.analysis_year_min.editingFinished.connect(self._changed)
        self.analysis_year_max.editingFinished.connect(self._changed)
        analysis_form.addRow(t("Proovivõtu aasta"), analysis_year_row)
        analysis_help = QLabel(t(
            "Sama näitaja teisendatavad ühikud ühendatakse ja tulemused "
            "kuvatakse valikus näidatud ühtsesse ühikusse."
        ))
        analysis_help.setWordWrap(True)
        analysis_help.setStyleSheet("color: #6b6b6b;")
        analysis_form.addRow(analysis_help)
        layout.addWidget(analysis_group)

        reset_button = QPushButton(t("Lähtesta filtrid"))
        reset_button.clicked.connect(self.reset_filters)
        layout.addWidget(reset_button)

        style_group = QGroupBox(t("VEKA sümboloogia"))
        style_form = QFormLayout(style_group)
        self.style_metric = QComboBox()
        for label, value in (
            (t("Puurimise aasta"), "year"),
            (t("Puuraugu sügavus"), "depth"),
            (t("Filtri algussügavus"), "filter_top"),
            (t("Filtri lõppsügavus"), "filter_bottom"),
            (t("Deebit"), "debit"),
            (t("Eritootlikkus"), "specific"),
            (t("Valitud veeproovi näitaja"), "analysis"),
        ):
            self.style_metric.addItem(label, value)
        style_form.addRow(t("Näitaja"), self.style_metric)
        self.style_aggregation = self._mode_combo(include_any=False)
        style_form.addRow(t("Koondamine"), self.style_aggregation)
        self.style_method = QComboBox()
        self.style_method.addItem(t("Värv"), "color")
        self.style_method.addItem(t("Ikooni suurus"), "size")
        self.style_method.addItem(t("Värv ja suurus"), "both")
        style_form.addRow(t("Kujutusviis"), self.style_method)
        self.style_classification = QComboBox()
        self.style_classification.addItem(t("Kvantiilid"), "quantile")
        self.style_classification.addItem(t("Võrdsed vahemikud"), "equal")
        style_form.addRow(t("Klassifikatsioon"), self.style_classification)
        self.style_palette = QComboBox()
        self.style_palette.addItem("Viridis", "#440154|#fde725")
        self.style_palette.addItem("Sinine–punane", "#2c7bb6|#d7191c")
        self.style_palette.addItem("Hele–tumesinine", "#deebf7|#08519c")
        self.style_palette.addItem("Kollane–punane", "#ffffb2|#bd0026")
        style_form.addRow(t("Värviskaala"), self.style_palette)
        self.style_classes = QLineEdit("5")
        style_form.addRow(t("Klasside arv"), self.style_classes)
        self.size_min, self.size_max, size_row = self._range_row("1.5", "7")
        style_form.addRow(t("Ikooni suurus, mm"), size_row)
        self.style_missing = QCheckBox(t("Kuva puuduvad andmed hallina"))
        self.style_missing.setChecked(True)
        style_form.addRow(self.style_missing)
        style_buttons = QWidget()
        style_buttons_layout = QHBoxLayout(style_buttons)
        style_buttons_layout.setContentsMargins(0, 0, 0, 0)
        apply_style = QPushButton(t("Rakenda kujundus"))
        apply_style.clicked.connect(
            lambda: plugin.apply_veka_symbology(self.style_settings())
        )
        reset_style = QPushButton(t("Taasta algkujundus"))
        reset_style.clicked.connect(plugin.reset_veka_symbology)
        style_buttons_layout.addWidget(apply_style)
        style_buttons_layout.addWidget(reset_style)
        style_form.addRow(style_buttons)
        layout.addWidget(style_group)

        self.status = QLabel(t("Laadi VK kiht, et VEKA filtreid kasutada."))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch(1)
        self.restore_style(plugin.veka_style)

    @staticmethod
    def _range_row(left_placeholder, right_placeholder):
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        left = QLineEdit()
        right = QLineEdit()
        left.setPlaceholderText(str(left_placeholder))
        right.setPlaceholderText(str(right_placeholder))
        row.addWidget(left)
        row.addWidget(right)
        return left, right, host

    def _mode_combo(self, include_any):
        combo = QComboBox()
        if include_any:
            combo.addItem(self.plugin.t("Vähemalt üks tulemus sobib"), "any")
        combo.addItem(self.plugin.t("Uusim tulemus"), "latest")
        combo.addItem(self.plugin.t("Suurim tulemus"), "max")
        combo.addItem(self.plugin.t("Väikseim tulemus"), "min")
        combo.addItem(self.plugin.t("Keskmine tulemus"), "mean")
        return combo

    @staticmethod
    def _number(widget, integer=False):
        text = widget.text().strip()
        if not text:
            return None
        try:
            numeric = float(text.replace(",", "."))
            return int(numeric) if integer else numeric
        except ValueError:
            return None

    def requirements(self):
        return {
            "text": self.text.text().strip(),
            "purposes": self.purpose.selected_values(),
            "groundwater": self.groundwater.selected_values(),
            "year_min": self._number(self.year_min, True),
            "year_max": self._number(self.year_max, True),
            "filter_min": self._number(self.filter_min),
            "filter_max": self._number(self.filter_max),
            "hydro_mode": self.hydro_mode.currentData(),
            "debit_min": self._number(self.debit_min),
            "debit_max": self._number(self.debit_max),
            "specific_min": self._number(self.specific_min),
            "specific_max": self._number(self.specific_max),
            "analysis_code": self.analysis.currentData() or "",
            "analysis_mode": self.analysis_mode.currentData(),
            "analysis_min": self._number(self.analysis_min),
            "analysis_max": self._number(self.analysis_max),
            "analysis_year_min": self._number(self.analysis_year_min, True),
            "analysis_year_max": self._number(self.analysis_year_max, True),
        }

    def style_settings(self):
        try:
            classes = max(1, min(12, int(self.style_classes.text())))
        except ValueError:
            classes = 5
        return {
            "metric": self.style_metric.currentData(),
            "aggregation": self.style_aggregation.currentData(),
            "method": self.style_method.currentData(),
            "classification": self.style_classification.currentData(),
            "palette": self.style_palette.currentData(),
            "classes": classes,
            "size_min": self._number(self.size_min) or 1.5,
            "size_max": self._number(self.size_max) or 7.0,
            "show_missing": self.style_missing.isChecked(),
            "analysis_code": self.analysis.currentData() or "",
        }

    def restore_style(self, settings):
        if not isinstance(settings, dict):
            return
        self._pending_analysis_code = str(settings.get("analysis_code") or "")
        for combo, key in (
            (self.style_metric, "metric"),
            (self.style_aggregation, "aggregation"),
            (self.style_method, "method"),
            (self.style_classification, "classification"),
            (self.style_palette, "palette"),
        ):
            index = combo.findData(settings.get(key))
            if index >= 0:
                combo.setCurrentIndex(index)
        if settings.get("classes"):
            self.style_classes.setText(str(settings["classes"]))
        if settings.get("size_min") is not None:
            self.size_min.setText(str(settings["size_min"]))
        if settings.get("size_max") is not None:
            self.size_max.setText(str(settings["size_max"]))
        if "show_missing" in settings:
            self.style_missing.setChecked(bool(settings["show_missing"]))

    def set_main_options(self, purposes, groundwater):
        self.purpose.set_options(purposes)
        self.groundwater.set_options(groundwater)

    def set_analysis_options(self, options):
        selected = self.analysis.currentData() or self._pending_analysis_code
        self.analysis.blockSignals(True)
        self.analysis.clear()
        self.analysis.addItem(self.plugin.t("Kõik"), "")
        for code, label in options:
            self.analysis.addItem(label, code)
        index = self.analysis.findData(selected)
        if index < 0 and selected:
            # Migrate a unit-specific selection from the initial 3.14.0 build
            # to the new unified option when the indicator has one clear row.
            source_code = str(selected).split("\x1f", 1)[0]
            candidates = [
                item_index for item_index in range(1, self.analysis.count())
                if source_code in str(
                    self.analysis.itemData(item_index)
                ).split("\x1f", 1)[0].split("\x1e")
            ]
            if len(candidates) == 1:
                index = candidates[0]
                selected = self.analysis.itemData(index)
        self.analysis.setCurrentIndex(max(0, index))
        if index >= 0:
            self._pending_analysis_code = str(selected)
        self.analysis.blockSignals(False)
        self.load_analysis.setEnabled(False)

    def reset_filters(self):
        self._resetting = True
        try:
            self.text.clear()
            self.purpose.clear_selection()
            self.groundwater.clear_selection()
            for widget in (
                self.year_min, self.year_max, self.filter_min, self.filter_max,
                self.debit_min, self.debit_max, self.specific_min,
                self.specific_max, self.analysis_min, self.analysis_max,
                self.analysis_year_min, self.analysis_year_max,
            ):
                widget.clear()
            self.hydro_mode.setCurrentIndex(0)
            self.analysis_mode.setCurrentIndex(0)
            self.analysis.setCurrentIndex(0)
        finally:
            self._resetting = False
        self.plugin.apply_veka_filters()

    def _changed(self):
        if not self._resetting:
            self.plugin.apply_veka_filters()


class SearchWidget(QWidget):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        t = plugin.t
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.source = QComboBox()
        self.source.addItem(t("EGT, SARV ja VEKA"), "all")
        self.source.addItem(t("EGT ja SARV"), "both")
        self.source.addItem("EGT", "egt")
        self.source.addItem("SARV", "sarv")
        self.source.addItem("VEKA", "veka")
        # Preserve the established EGT + SARV default; VEKA is an opt-in
        # dropdown layer and should not create a missing-layer warning in
        # every existing search.
        self.source.setCurrentIndex(self.source.findData("both"))
        form.addRow(t("Allikas"), self.source)
        kind_host = QWidget()
        kind_layout = QHBoxLayout(kind_host)
        kind_layout.setContentsMargins(0, 0, 0, 0)
        self.kinds = {}
        for role, label in (
            ("boreholes", "PA"),
            ("observations", "VP"),
            ("sarv_localities", "SL"),
            ("sarv_sites", "SU"),
            ("sarv_drillcores", "SK"),
            ("veka_boreholes", "VK"),
        ):
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.setToolTip(t({
                "boreholes": "Puuraugud",
                "observations": "Vaatluspunktid",
                "sarv_localities": "Lokaliteedid",
                "sarv_sites": "Uuringupunktid",
                "sarv_drillcores": "Puursüdamikud",
                "veka_boreholes": "VEKA puurkaevud",
            }[role]))
            self.kinds[role] = checkbox
            kind_layout.addWidget(checkbox)
        form.addRow(t("Objekti liigid"), kind_host)
        self.text = QLineEdit()
        self.text.setPlaceholderText(t("Nimi, number või ID"))
        self.text.returnPressed.connect(self.run)
        form.addRow(t("Otsing"), self.text)
        self.current_extent = QCheckBox(t("Ainult kaardi praegune ulatus"))
        form.addRow(self.current_extent)
        depth_host = QWidget()
        depth_layout = QHBoxLayout(depth_host)
        depth_layout.setContentsMargins(0, 0, 0, 0)
        self.depth_min = QLineEdit()
        self.depth_max = QLineEdit()
        self.depth_min.setPlaceholderText(t("Min"))
        self.depth_max.setPlaceholderText(t("Max"))
        depth_layout.addWidget(self.depth_min)
        depth_layout.addWidget(self.depth_max)
        form.addRow(t("Sügavus"), depth_host)
        self.stratigraphic_index = MultiSelectButton(t("Kõik"))
        self.stratigraphic_index.set_options(
            (index, index) for index in STRATIGRAPHIC_INDICES
        )
        form.addRow(t("Indeks"), self.stratigraphic_index)
        self.sample_type = MultiSelectButton(t("Kõik"))
        self.sample_purpose = MultiSelectButton(t("Kõik"))
        self.analysis_method = MultiSelectButton(t("Kõik"))
        self.related = {}
        related_host = QWidget()
        related_layout = QHBoxLayout(related_host)
        related_layout.setContentsMargins(0, 0, 0, 0)
        for key, label in (
            ("core", "Puursüdamik"),
            ("samples", "Proovid"),
            ("analyses", "Analüüsid"),
        ):
            choice = QComboBox()
            choice.addItem(f"{t(label)}: {t('Kõik')}", "any")
            choice.addItem(f"{t(label)}: {t('Jah')}", "yes")
            choice.addItem(f"{t(label)}: {t('Ei')}", "no")
            choice.setToolTip(t(label))
            self.related[key] = choice
            related_layout.addWidget(choice)
        form.addRow(t("Seotud andmed"), related_host)
        form.addRow(t("Proovi tüüp"), self.sample_type)
        form.addRow(t("Proovi eesmärk"), self.sample_purpose)
        form.addRow(t("Analüüsi meetod"), self.analysis_method)
        layout.addLayout(form)
        self.search_button = QPushButton(t("Otsi"))
        self.search_button.clicked.connect(self.run)
        layout.addWidget(self.search_button)
        filter_actions = QWidget()
        filter_actions_layout = QHBoxLayout(filter_actions)
        filter_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.apply_filter_button = QPushButton(t("Rakenda filtrina"))
        self.apply_filter_button.clicked.connect(self.apply_as_filter)
        self.reset_button = QPushButton(t("Lähtesta"))
        self.reset_button.clicked.connect(self.reset)
        filter_actions_layout.addWidget(self.apply_filter_button)
        filter_actions_layout.addWidget(self.reset_button)
        layout.addWidget(filter_actions)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.results = QTableWidget(0, 6)
        self.results.setHorizontalHeaderLabels(
            (t("Allikas"), t("Tüüp"), t("Nimi"), t("ID"),
             t("Sügavus"), t("Toiming"))
        )
        self.results.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        layout.addWidget(self.results)
        self.source.currentIndexChanged.connect(self._source_changed)
        self._source_changed()
        self.reload_domain_options()

    def _source_changed(self):
        self.stratigraphic_index.setEnabled(
            self.source.currentData() in {"all", "both", "egt"}
        )

    def reload_domain_options(self):
        egt_types = self.plugin.egt_options(18, "proov_tyyp")
        egt_purposes = self.plugin.egt_options(18, "eesmark")
        self.sample_type.set_options(
            [(f"egt:{code}", f"EGT · {name}") for code, name in egt_types]
            + [(f"sarv:{code}", f"SARV · {name}")
               for code, name in self.plugin.sarv_sample_type_options]
        )
        self.sample_purpose.set_options(
            [(f"egt:{code}", f"EGT · {name}") for code, name in egt_purposes]
            + [(f"sarv:{code}", f"SARV · {name}")
               for code, name in self.plugin.sarv_purpose_options()]
        )
        self.analysis_method.set_options(
            [(f"egt:{code}", f"EGT · {name}")
             for code, name in self.plugin.egt_options(3, "analyys_meetod")]
            + [(f"sarv:{code}", f"SARV · {name}")
               for code, name in self.plugin.sarv_analysis_options]
        )

    def criteria(self):
        def number(widget):
            try:
                return float(widget.text().strip()) if widget.text().strip() else None
            except ValueError:
                return None

        return {
            "source": self.source.currentData(),
            "kinds": {
                role for role, checkbox in self.kinds.items()
                if checkbox.isChecked()
            },
            "text": self.text.text().strip(),
            "current_extent": self.current_extent.isChecked(),
            "depth_min": number(self.depth_min),
            "depth_max": number(self.depth_max),
            "stratigraphic_indices": (
                self.stratigraphic_index.selected_values()
                if self.stratigraphic_index.isEnabled() else set()
            ),
            "sample_type": self.sample_type.selected_values(),
            "sample_purpose": self.sample_purpose.selected_values(),
            "analysis_method": self.analysis_method.selected_values(),
            "related": {
                key: choice.currentData() for key, choice in self.related.items()
            },
        }

    def run(self):
        self._start_search(False)

    def apply_as_filter(self):
        self._start_search(True)

    def _start_search(self, apply_filter):
        self.search_button.setEnabled(False)
        self.apply_filter_button.setEnabled(False)
        self.status.setText(self.plugin.t("Otsitakse…"))
        criteria = self.criteria()
        if apply_filter:
            criteria["_return_all"] = True
            self.plugin.run_search(
                criteria,
                lambda rows, message="": self._set_filtered_results(
                    rows, message, criteria
                ),
            )
        else:
            self.plugin.run_search(criteria, self.set_results)

    def _set_filtered_results(self, rows, message, criteria):
        self.set_results(rows[:500], message)
        self.plugin.apply_search_filter(rows, criteria)
        suffix = self.plugin.t("Otsingutulemused rakendati filtrina.")
        self.status.setText(
            f"{self.status.text()} {suffix}".strip()
        )

    def reset(self):
        self.source.setCurrentIndex(self.source.findData("both"))
        for checkbox in self.kinds.values():
            checkbox.setChecked(True)
        self.text.clear()
        self.current_extent.setChecked(False)
        self.depth_min.clear()
        self.depth_max.clear()
        self.stratigraphic_index.clear_selection()
        self.sample_type.clear_selection()
        self.sample_purpose.clear_selection()
        self.analysis_method.clear_selection()
        for choice in self.related.values():
            choice.setCurrentIndex(0)
        self.results.clearContents()
        self.results.setRowCount(0)
        self.status.clear()
        self.search_button.setEnabled(True)
        self.apply_filter_button.setEnabled(True)
        self.plugin.clear_search_filter()

    def set_results(self, rows, message=""):
        self.search_button.setEnabled(True)
        self.apply_filter_button.setEnabled(True)
        self.status.setText(message or f"{len(rows)} {self.plugin.t('tulemust')}")
        self.results.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, key in enumerate(
                ("source", "type", "name", "id", "depth")
            ):
                self.results.setItem(
                    row_index, column,
                    QTableWidgetItem(_display_value(row.get(key))),
                )
            button = QPushButton(self.plugin.t("Ava"))
            button.clicked.connect(
                lambda checked=False, item=row: self.plugin.open_search_result(item)
            )
            self.results.setCellWidget(row_index, 5, button)
        self.results.resizeColumnsToContents()


class _LegacyProfileWidget(QWidget):
    COLORS = {
        1: QColor("#d7bd72"),
        2: QColor("#7796c6"),
        3: QColor("#b56b6b"),
        997: QColor("#a7a7a7"),
    }

    def __init__(self):
        super().__init__()
        self.units = []
        self.core_boxes = []
        self.sarv_core_boxes = []
        self.samples = []
        self.analyses = []
        self.sarv_samples = []
        self.sarv_analyses = []
        self.sarv_specimens = []
        self.core_images = {}
        self.sarv_core_images = {}
        self._click_targets = []
        self.total_depth = 0.0
        self.show_lithology = True
        self.show_core_boxes = True
        self.show_sarv_core_boxes = True
        self.show_samples = True
        self.show_analyses = True
        self.show_sarv_samples = True
        self.show_sarv_analyses = True
        self.show_sarv_specimens = True
        self.setMinimumHeight(720)

    def set_units(self, units):
        self.units = sorted(units, key=lambda item: _number(item.get("z_suht_ylemine")))
        self.update()

    def set_core_boxes(self, rows):
        self.core_boxes = rows
        self.update()

    def set_samples(self, rows):
        self.samples = rows
        self.update()

    def set_analyses(self, rows):
        self.analyses = rows
        self.update()

    def set_options(self, lithology=None, core_boxes=None, samples=None, analyses=None):
        if lithology is not None:
            self.show_lithology = lithology
        if core_boxes is not None:
            self.show_core_boxes = core_boxes
        if samples is not None:
            self.show_samples = samples
        if analyses is not None:
            self.show_analyses = analyses
        self.update()

    def paintEvent(self, event):
        self._click_targets = []
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("white"))
        visible_intervals = list(self.units)
        if self.show_core_boxes:
            visible_intervals.extend(self.core_boxes)
        if self.show_samples:
            visible_intervals.extend(self.samples)
        if self.show_analyses:
            visible_intervals.extend(self.analyses)
        if not visible_intervals:
            painter.setPen(QColor("#555555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Läbilõike andmed puuduvad")
            return
        top_margin = 52
        bottom_margin = 30
        max_depth = max(_number(item.get("z_suht_alumine")) for item in visible_intervals) or 1.0
        draw_height = max(1, self.height() - top_margin - bottom_margin)
        bar_left = 58
        bar_width = min(125, max(70, self.width() // 3))
        sample_left = bar_left + bar_width + 7
        analysis_left = sample_left + 17
        label_left = analysis_left + 23

        painter.setPen(QColor("#355e3b"))
        if self.show_samples:
            painter.drawText(sample_left - 1, 34, "P")
        painter.setPen(QColor("#7b3f8c"))
        if self.show_analyses:
            painter.drawText(analysis_left - 1, 34, "A")
        painter.setPen(QColor("#555555"))
        if self.show_core_boxes:
            painter.drawText(bar_left, 20, "Kastipiirid")

        painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawLine(bar_left - 8, top_margin, bar_left - 8, top_margin + draw_height)
        for index in range(6):
            depth = max_depth * index / 5
            y = top_margin + draw_height * depth / max_depth
            painter.drawLine(bar_left - 13, int(y), bar_left - 3, int(y))
            painter.drawText(2, int(y) + 5, f"{depth:.1f} m")
        for unit in self.units:
            start = _number(unit.get("z_suht_ylemine"))
            end = _number(unit.get("z_suht_alumine"))
            y1 = top_margin + draw_height * start / max_depth
            y2 = top_margin + draw_height * end / max_depth
            code = int(_number(unit.get("klassif_yksus_kood") or unit.get("yksus_kood")))
            color = self.COLORS.get(code, self.COLORS[997])
            painter.fillRect(bar_left, int(y1), bar_width, max(2, int(y2 - y1)), color)
            painter.setPen(QPen(QColor("#444444"), 1))
            painter.drawRect(bar_left, int(y1), bar_width, max(2, int(y2 - y1)))
            label = _unit_index(unit)
            lithology = unit.get("litoloogia") or unit.get("litoloogia_orig") or ""
            if self.show_lithology and lithology:
                label = f"{label} · {lithology}" if label else str(lithology)
            if label and y2 - y1 >= 8:
                painter.drawText(label_left, int(y1) + 12, str(label))

        if self.show_core_boxes:
            boundary_pen = QPen(QColor("#2d2d2d"), 1, Qt.PenStyle.DashLine)
            painter.setPen(boundary_pen)
            for box in self.core_boxes:
                start = _number(box.get("z_suht_ylemine"))
                end = _number(box.get("z_suht_alumine"))
                y1 = top_margin + draw_height * start / max_depth
                y2 = top_margin + draw_height * end / max_depth
                painter.drawLine(bar_left, int(y1), bar_left + bar_width, int(y1))
                painter.drawLine(bar_left, int(y2), bar_left + bar_width, int(y2))
                number = box.get("kast_nr")
                if number not in (None, ""):
                    painter.drawText(bar_left + 3, int(y1) + 11, f"K{number}")

        if self.show_samples:
            self._draw_intervals(
                painter,
                self.samples,
                sample_left,
                QColor("#4f9b61"),
                top_margin,
                draw_height,
                max_depth,
            )
        if self.show_analyses:
            self._draw_intervals(
                painter,
                self.analyses,
                analysis_left,
                QColor("#8b4a9b"),
                top_margin,
                draw_height,
                max_depth,
            )

    @staticmethod
    def _draw_intervals(painter, rows, left, color, top_margin, draw_height, max_depth):
        fill = QColor(color)
        fill.setAlpha(185)
        painter.setPen(QPen(color.darker(130), 1))
        painter.setBrush(fill)
        for row in rows:
            start = _number(row.get("z_suht_ylemine"))
            end = _number(row.get("z_suht_alumine"))
            y1 = top_margin + draw_height * start / max_depth
            y2 = top_margin + draw_height * end / max_depth
            painter.drawRect(left, int(y1), 11, max(3, int(y2 - y1)))
        painter.setBrush(Qt.BrushStyle.NoBrush)


class ProfileWidget(QWidget):
    """Vertically zoomable geological column with core/sample overlays."""

    BAR_WIDTH = 125
    BASE_PIXELS_PER_METER = 3.0
    TOP_MARGIN = 58
    BOTTOM_MARGIN = 30
    SARV_LANES = 4
    SARV_LANE_WIDTH = 10
    SARV_LANE_GAP = 2
    SARV_TRACK_WIDTH = SARV_LANES * SARV_LANE_WIDTH + (SARV_LANES - 1) * SARV_LANE_GAP
    SARV_CLUSTER_PIXELS = 12
    VEKA_CONSTRUCTION_WIDTH = 110
    VEKA_DRAW_WIDTH = 56

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.units = []
        self.core_boxes = []
        self.sarv_core_boxes = []
        self.samples = []
        self.analyses = []
        self.sarv_samples = []
        self.sarv_analyses = []
        self.sarv_specimens = []
        self.veka_construction = []
        self.veka_static_water_level = None
        self.core_images = {}
        self.sarv_core_images = {}
        self._click_targets = []
        self.total_depth = 0.0
        self.show_lithology = True
        self.show_boundary_depths = True
        self.show_core_boxes = True
        self.show_sarv_core_boxes = True
        self.show_samples = True
        self.show_analyses = True
        self.show_sarv_samples = True
        self.show_sarv_analyses = True
        self.show_sarv_specimens = True
        self.show_veka_construction = False
        self.show_veka_static_water_level = False
        self.group_sarv_overlaps = True
        self.core_applicable = False
        self.zoom_factor = 1.0
        self.setMouseTracking(True)
        self._update_minimum_width()
        self._update_minimum_height()

    def sizeHint(self):
        return QSize(self.minimumWidth(), self.minimumHeight())

    def set_units(self, units):
        self.units = sorted(units, key=lambda item: _number(item.get("z_suht_ylemine")))
        self._update_minimum_width()
        self._update_minimum_height()

    def set_core_boxes(self, rows):
        self.core_boxes = list(rows)
        self._update_minimum_height()

    def set_sarv_core_boxes(self, rows):
        self.sarv_core_boxes = list(rows)
        self._update_minimum_height()

    def set_samples(self, rows):
        self.samples = list(rows)
        self._update_minimum_height()

    def set_analyses(self, rows):
        self.analyses = list(rows)
        self._update_minimum_height()

    def set_sarv_samples(self, rows):
        self.sarv_samples = list(rows)
        self._update_minimum_height()

    def set_sarv_analyses(self, rows):
        self.sarv_analyses = list(rows)
        self._update_minimum_height()

    def set_sarv_specimens(self, rows):
        self.sarv_specimens = list(rows)
        self._update_minimum_height()

    def set_veka_construction(self, rows):
        prepared = []
        seen = set()
        for row in rows:
            start = _number(row.get("alg"))
            end = _number(row.get("lopp"))
            category = self.plugin.veka_construction_category(
                row.get("konstr_tyyp")
            )
            key = (category, start, end, _number(row.get("diam")))
            if key in seen:
                continue
            seen.add(key)
            prepared.append({
                **row,
                "_category": category,
                "z_suht_ylemine": start,
                "z_suht_alumine": end,
            })
        self.veka_construction = prepared
        self._update_minimum_width()
        self._update_minimum_height()

    def set_veka_static_water_level(self, row):
        self.veka_static_water_level = dict(row) if row else None
        self.update()

    def set_core_images(self, images_by_core):
        self.core_images = {
            str(key).upper(): list(value) for key, value in images_by_core.items()
        }
        self.update()

    def set_sarv_core_images(self, images_by_core):
        self.sarv_core_images = {
            str(key): list(value) for key, value in images_by_core.items()
        }
        self.update()

    def set_core_applicable(self, applicable):
        self.core_applicable = bool(applicable)
        self.update()

    def set_total_depth(self, depth):
        self.total_depth = max(0.0, _number(depth))
        self._update_minimum_height()

    def set_options(
        self,
        lithology=None,
        boundary_depths=None,
        core_boxes=None,
        samples=None,
        analyses=None,
        sarv_core_boxes=None,
        sarv_samples=None,
        sarv_analyses=None,
        sarv_specimens=None,
        sarv_grouping=None,
        veka_construction=None,
        veka_static_water_level=None,
    ):
        if lithology is not None:
            self.show_lithology = lithology
        if boundary_depths is not None:
            self.show_boundary_depths = boundary_depths
        if core_boxes is not None:
            self.show_core_boxes = core_boxes
        if sarv_core_boxes is not None:
            self.show_sarv_core_boxes = sarv_core_boxes
        if samples is not None:
            self.show_samples = samples
        if analyses is not None:
            self.show_analyses = analyses
        if sarv_samples is not None:
            self.show_sarv_samples = sarv_samples
        if sarv_analyses is not None:
            self.show_sarv_analyses = sarv_analyses
        if sarv_specimens is not None:
            self.show_sarv_specimens = sarv_specimens
        if sarv_grouping is not None:
            self.group_sarv_overlaps = sarv_grouping
        if veka_construction is not None:
            self.show_veka_construction = veka_construction
        if veka_static_water_level is not None:
            self.show_veka_static_water_level = veka_static_water_level
        self._update_minimum_width()
        self._update_minimum_height()

    def _column_layout(self, metrics):
        """Return compact column positions for the currently visible tracks."""
        bar_left = 68
        boundary_width = 64 if self.show_boundary_depths else 0
        index_left = bar_left + self.BAR_WIDTH + boundary_width + 8
        index_width = max(
            76,
            min(
                140,
                max(
                    (
                        metrics.horizontalAdvance(str(_unit_index(unit)))
                        for unit in self.units
                        if _unit_index(unit)
                    ),
                    default=66,
                ) + 12,
            ),
        )
        cursor = index_left + index_width
        tracks = {}
        for key, visible, width, gap in (
            ("samples", self.show_samples, 11, 7),
            ("analyses", self.show_analyses, 11, 9),
            ("sarv_samples", self.show_sarv_samples, self.SARV_TRACK_WIDTH, 8),
            ("sarv_analyses", self.show_sarv_analyses, self.SARV_TRACK_WIDTH, 8),
            ("sarv_specimens", self.show_sarv_specimens, self.SARV_TRACK_WIDTH, 14),
        ):
            if not visible:
                continue
            tracks[key] = cursor
            cursor += width + gap

        construction_left = None
        if self.show_veka_construction:
            construction_left = cursor
            cursor += self.VEKA_CONSTRUCTION_WIDTH + 14

        lithology_left = cursor if tracks else cursor + 14
        lithology_width = 0
        if self.show_lithology:
            lithology_width = max(
                150,
                min(
                    320,
                    max(
                        (
                            metrics.horizontalAdvance(str(
                                unit.get("litoloogia")
                                or unit.get("litoloogia_orig") or ""
                            ))
                            for unit in self.units
                        ),
                        default=138,
                    ) + 12,
                ),
            )
        content_right = (
            lithology_left + lithology_width
            if self.show_lithology else cursor
        )
        return {
            "bar_left": bar_left,
            "index_left": index_left,
            "index_width": index_width,
            "tracks": tracks,
            "construction_left": construction_left,
            "lithology_left": lithology_left,
            "content_right": content_right,
        }

    def _update_minimum_width(self):
        layout = self._column_layout(self.fontMetrics())
        self.setMinimumWidth(max(360, round(layout["content_right"] + 20)))
        self.updateGeometry()

    def wheelEvent(self, event):
        modifiers = event.modifiers()
        zoom_modifier = (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        )
        if modifiers & zoom_modifier:
            delta = event.angleDelta().y()
            if delta:
                self._apply_zoom(1.2 if delta > 0 else 1 / 1.2)
                event.accept()
                return
        event.ignore()

    def _apply_zoom(self, multiplier):
        self.zoom_factor = max(0.35, min(12.0, self.zoom_factor * multiplier))
        self._update_minimum_height()

    def _visible_intervals(self):
        rows = list(self.units)
        if self.show_core_boxes:
            rows.extend(self.core_boxes)
        if self.show_sarv_core_boxes:
            rows.extend(self.sarv_core_boxes)
        if self.show_samples:
            rows.extend(self.samples)
        if self.show_analyses:
            rows.extend(self.analyses)
        if self.show_sarv_samples:
            rows.extend(self.sarv_samples)
        if self.show_sarv_analyses:
            rows.extend(self.sarv_analyses)
        if self.show_sarv_specimens:
            rows.extend(self.sarv_specimens)
        if self.show_veka_construction:
            rows.extend(self.veka_construction)
        return rows

    def _top_margin(self):
        return 86 if self.show_veka_construction else self.TOP_MARGIN

    def _max_depth(self):
        rows = self._visible_intervals()
        valid_bottoms = []
        for row in rows:
            start = _number(row.get("z_suht_ylemine"))
            end = _number(row.get("z_suht_alumine"))
            if end < start:
                continue
            if self.total_depth > 0 and end > self.total_depth:
                continue
            valid_bottoms.append(end)
        return max(
            self.total_depth,
            max(valid_bottoms, default=0.0),
        )

    def _update_minimum_height(self):
        depth = max(1.0, self._max_depth())
        content = depth * self.BASE_PIXELS_PER_METER * self.zoom_factor
        self.setMinimumHeight(max(
            240,
            round(360 * self.zoom_factor),
            round(self._top_margin() + content + self.BOTTOM_MARGIN),
        ))
        self.updateGeometry()
        self.update()

    def paintEvent(self, event):
        self._click_targets = []
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("white"))
        intervals = self._visible_intervals()
        if not intervals and not (self.core_applicable and self.total_depth > 0):
            painter.setPen(QColor("#555555"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                self.plugin.t("Läbilõike andmed puuduvad"),
            )
            return

        max_depth = max(1.0, self._max_depth())
        top_margin = self._top_margin()
        draw_height = max(
            1.0,
            max_depth * self.BASE_PIXELS_PER_METER * self.zoom_factor,
            self.height() - top_margin - self.BOTTOM_MARGIN,
        )
        layout = self._column_layout(painter.fontMetrics())
        bar_left = layout["bar_left"]
        index_left = layout["index_left"]
        tracks = layout["tracks"]
        construction_left = layout["construction_left"]
        lithology_left = layout["lithology_left"]

        def depth_y(depth):
            return top_margin + draw_height * depth / max_depth

        heading_y = 66 if self.show_veka_construction else 34
        painter.setPen(QColor("#555555"))
        painter.drawText(index_left, heading_y, self.plugin.t("Indeks"))
        if self.show_lithology:
            painter.drawText(
                lithology_left, heading_y, self.plugin.t("Litoloogia")
            )
        if self.show_veka_construction and construction_left is not None:
            painter.drawText(
                construction_left, heading_y,
                self.plugin.t("Konstruktsioon"),
            )
            self._draw_veka_legend(painter, bar_left)
        painter.setPen(QColor("#355e3b"))
        if self.show_samples:
            painter.drawText(tracks["samples"] - 1, heading_y, "P")
        painter.setPen(QColor("#7b3f8c"))
        if self.show_analyses:
            painter.drawText(tracks["analyses"] - 1, heading_y, "A")
        painter.setPen(QColor("#267d92"))
        if self.show_sarv_samples:
            painter.drawText(tracks["sarv_samples"] + 14, heading_y, "SP")
        painter.setPen(QColor("#c06b25"))
        if self.show_sarv_analyses:
            painter.drawText(tracks["sarv_analyses"] + 14, heading_y, "SA")
        painter.setPen(QColor("#b23a62"))
        if self.show_sarv_specimens:
            painter.drawText(tracks["sarv_specimens"] + 14, heading_y, "SE")
        painter.setPen(QColor("#555555"))
        if self.show_core_boxes:
            painter.drawText(bar_left, 20, self.plugin.t("Kastipiirid"))

        painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawLine(
            bar_left - 9, top_margin,
            bar_left - 9, round(top_margin + draw_height),
        )
        step = _nice_depth_step(max_depth, draw_height)
        depth = 0.0
        while depth <= max_depth + step / 100:
            y = round(depth_y(depth))
            painter.drawLine(bar_left - 14, y, bar_left - 4, y)
            painter.drawText(2, y + 5, f"{depth:g} m")
            depth += step

        unit_geometry = []
        for unit in self.units:
            start = _number(unit.get("z_suht_ylemine"))
            end = _number(unit.get("z_suht_alumine"))
            y1, y2 = depth_y(start), depth_y(end)
            height = max(2, round(y2 - y1))
            color = _stratigraphic_color(unit)
            painter.fillRect(bar_left, round(y1), self.BAR_WIDTH, height, color)
            painter.setPen(QPen(QColor("#454545"), 1))
            painter.drawRect(bar_left, round(y1), self.BAR_WIDTH, height)
            unit_geometry.append((unit, y1, height))

        if self.show_boundary_depths:
            guide_end = (
                lithology_left - 6
                if self.show_lithology
                else layout["content_right"]
            )
            guide_pen = QPen(QColor(82, 91, 99, 62), 1)
            painter.setPen(guide_pen)
            for depth in self._unit_boundary_depths(max_depth):
                y = round(depth_y(depth))
                depth_text = f"{depth:g} m"
                guide_start = (
                    bar_left + self.BAR_WIDTH + 8
                    + painter.fontMetrics().horizontalAdvance(depth_text) + 5
                )
                painter.drawLine(round(guide_start), y, round(guide_end), y)

        for unit, y1, height in unit_geometry:
            painter.setPen(QColor("#454545"))
            index = _unit_index(unit)
            lithology = unit.get("litoloogia") or unit.get("litoloogia_orig") or ""
            if index and height >= 8:
                painter.drawText(index_left, round(y1) + 12, str(index))
            if self.show_lithology and lithology and height >= 8:
                painter.drawText(lithology_left, round(y1) + 12, str(lithology))

        if self.show_boundary_depths:
            self._draw_boundary_depth_labels(
                painter, depth_y, max_depth, bar_left, draw_height,
                top_margin,
            )

        if self.show_core_boxes and self.core_applicable:
            hatch_color = QColor("#4f5963")
            hatch_color.setAlpha(95)
            hatch = QBrush(hatch_color, Qt.BrushStyle.BDiagPattern)
            core_coverage = list(self.core_boxes) + list(self.sarv_core_boxes)
            for start, end in _interval_gaps(core_coverage, max_depth):
                y1, y2 = depth_y(start), depth_y(end)
                painter.fillRect(
                    bar_left, round(y1), self.BAR_WIDTH,
                    max(1, round(y2 - y1)), hatch,
                )
            painter.setPen(QColor("#555555"))
            painter.drawText(
                bar_left, 50,
                self.plugin.t("Viirutus: puursüdamiku kast puudub"),
            )

            painter.setPen(QPen(QColor("#2d2d2d"), 1, Qt.PenStyle.DashLine))
            for box in self.core_boxes:
                start = max(0.0, _number(box.get("z_suht_ylemine")))
                end = min(max_depth, _number(box.get("z_suht_alumine")))
                y1, y2 = depth_y(start), depth_y(end)
                painter.drawLine(bar_left, round(y1), bar_left + self.BAR_WIDTH, round(y1))
                painter.drawLine(bar_left, round(y2), bar_left + self.BAR_WIDTH, round(y2))
                number = box.get("kast_nr")
                if number not in (None, ""):
                    painter.drawText(bar_left + 3, round(y1) + 11, f"K{number}")
                urls = self.core_images.get(str(box.get("globalid") or "").upper(), [])
                if urls:
                    self._click_targets.append({
                        "rect": (
                            bar_left, round(y1), bar_left + self.BAR_WIDTH,
                            max(round(y1) + 3, round(y2)),
                        ),
                        "urls": urls,
                        "label": f"K{number}" if number not in (None, "") else "",
                        "kind": "images",
                    })

        if self.show_sarv_core_boxes:
            sarv_box_color = QColor("#176f8a")
            painter.setPen(QPen(sarv_box_color, 1, Qt.PenStyle.DotLine))
            for box in self.sarv_core_boxes:
                start = max(0.0, _number(box.get("z_suht_ylemine")))
                end = min(max_depth, _number(box.get("z_suht_alumine")))
                if end < start or start > max_depth:
                    continue
                y1, y2 = depth_y(start), depth_y(end)
                painter.drawLine(bar_left, round(y1), bar_left + self.BAR_WIDTH, round(y1))
                painter.drawLine(bar_left, round(y2), bar_left + self.BAR_WIDTH, round(y2))
                number = box.get("kast_nr")
                if number not in (None, ""):
                    painter.drawText(
                        bar_left + self.BAR_WIDTH - 33, round(y1) + 11,
                        f"S{number}",
                    )
                urls = self.sarv_core_images.get(str(box.get("id") or ""), [])
                if urls:
                    self._click_targets.append({
                        "rect": (
                            bar_left, round(y1), bar_left + self.BAR_WIDTH,
                            max(round(y1) + 3, round(y2)),
                        ),
                        "urls": urls,
                        "label": f"SARV {self.plugin.t('Kast')} {number}",
                        "kind": "images",
                    })

        if self.show_samples:
            self._draw_intervals(
                painter, self.samples, tracks["samples"], QColor("#4f9b61"),
                top_margin, draw_height, max_depth,
            )
        if self.show_analyses:
            self._draw_intervals(
                painter, self.analyses, tracks["analyses"], QColor("#8b4a9b"),
                top_margin, draw_height, max_depth,
            )
        if self.show_sarv_samples:
            self._draw_intervals(
                painter, self.sarv_samples, tracks["sarv_samples"], QColor("#267d92"),
                top_margin, draw_height, max_depth, sarv=True,
            )
        if self.show_sarv_analyses:
            self._draw_intervals(
                painter, self.sarv_analyses, tracks["sarv_analyses"], QColor("#c06b25"),
                top_margin, draw_height, max_depth, sarv=True,
            )
        if self.show_sarv_specimens:
            self._draw_intervals(
                painter, self.sarv_specimens, tracks["sarv_specimens"], QColor("#b23a62"),
                top_margin, draw_height, max_depth, sarv=True,
            )
        if self.show_veka_construction and construction_left is not None:
            self._draw_veka_construction(
                painter, construction_left, depth_y, max_depth,
            )
        if (
            self.show_veka_static_water_level
            and self.veka_static_water_level
        ):
            self._draw_veka_static_water_level(
                painter, depth_y, max_depth, bar_left,
                layout["content_right"],
            )

    def _draw_veka_legend(self, painter, left):
        """Draw the compact legend used by the VEKA construction track."""
        painter.save()
        items = (
            ("drill", self.plugin.t("Puuri diameeter")),
            ("casing", self.plugin.t("Manteltoru")),
            ("filter", self.plugin.t("Filter")),
            ("open", self.plugin.t("Avatud / filtrita osa")),
        )
        x = left
        for category, label in items:
            self._draw_veka_swatch(painter, category, x, 10, 14, 11)
            painter.setPen(QColor("#454545"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawText(x + 19, 20, label)
            x += painter.fontMetrics().horizontalAdvance(label) + 35
        painter.setPen(QColor("#666666"))
        painter.drawText(left, 40, self.plugin.t("Laius ja Ø näitavad diameetrit millimeetrites"))
        painter.restore()

    @staticmethod
    def _draw_veka_swatch(painter, category, left, top, width, height):
        if category == "drill":
            painter.setPen(QPen(QColor("#737b82"), 1))
            painter.setBrush(QColor(184, 191, 197, 115))
            painter.drawRect(left, top, width, height)
        elif category == "casing":
            painter.setPen(QPen(QColor("#3f474d"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(left + 2, top, left + 2, top + height)
            painter.drawLine(left + width - 2, top, left + width - 2, top + height)
        elif category == "filter":
            painter.setPen(QPen(QColor("#237a9b"), 1))
            painter.setBrush(QBrush(QColor("#7cc8df"), Qt.BrushStyle.BDiagPattern))
            painter.drawRect(left, top, width, height)
        else:
            painter.setPen(QPen(
                QColor("#d07a22"), 1.5, Qt.PenStyle.DashLine
            ))
            painter.setBrush(QColor(244, 172, 91, 45))
            painter.drawRect(left, top, width, height)

    def _draw_veka_construction(
        self, painter, construction_left, depth_y, max_depth,
    ):
        rows = []
        for row in self.veka_construction:
            start = max(0.0, _number(row.get("z_suht_ylemine")))
            end = min(max_depth, _number(row.get("z_suht_alumine")))
            if end < start or start > max_depth:
                continue
            rows.append((row, start, end, _number(row.get("diam"))))
        if not rows:
            return
        maximum_diameter = max(
            (diameter for _, _, _, diameter in rows if diameter > 0),
            default=1.0,
        )
        order = {"drill": 0, "open": 1, "casing": 2, "filter": 3}
        rows.sort(key=lambda item: (
            order.get(item[0].get("_category"), 4),
            -item[3],
            item[1],
        ))
        painter.save()
        labels = []
        for row, start, end, diameter in rows:
            category = row.get("_category", "other")
            if category == "other":
                continue
            width = (
                max(10, round(self.VEKA_DRAW_WIDTH * diameter / maximum_diameter))
                if diameter > 0 else 22
            )
            left = construction_left + round(
                (self.VEKA_DRAW_WIDTH - width) / 2
            )
            y1, y2 = round(depth_y(start)), round(depth_y(end))
            height = max(2, y2 - y1)
            self._draw_veka_swatch(
                painter, category, left, y1, width, height
            )
            if diameter > 0 and height >= 10:
                labels.append({
                    "target": y1,
                    "right": left + width,
                    "text": f"Ø{diameter:g}",
                })
        labels.sort(key=lambda item: item["target"])
        positions = []
        for item in labels:
            target = item["target"] + 10
            positions.append(
                max(target, positions[-1] + 12) if positions else target
            )
        bottom = round(depth_y(max_depth)) + 4
        if positions and positions[-1] > bottom:
            positions[-1] = bottom
            for index in range(len(positions) - 2, -1, -1):
                positions[index] = min(
                    positions[index], positions[index + 1] - 12
                )
        label_left = construction_left + self.VEKA_DRAW_WIDTH + 5
        painter.setPen(QPen(QColor("#6a7075"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for item, label_y in zip(labels, positions):
            painter.drawLine(
                item["right"] + 1, item["target"],
                label_left - 2, label_y - 4,
            )
            painter.drawText(label_left, label_y, item["text"])
        painter.restore()

    def _draw_veka_static_water_level(
        self, painter, depth_y, max_depth, left, right,
    ):
        row = self.veka_static_water_level or {}
        depth = _number(row.get("st_veetase"))
        if depth < 0 or depth > max_depth:
            return
        y = round(depth_y(depth))
        color = QColor("#1677b8")
        painter.save()
        painter.setPen(QPen(color, 1.6, Qt.PenStyle.DashDotLine))
        painter.drawLine(left - 3, y, round(right), y)
        date = str(row.get("katse_kp") or "")[:10]
        text = f"{self.plugin.t('Staatiline veetase')}: {depth:g} m"
        if date:
            text += f" · {date}"
        metrics = painter.fontMetrics()
        text_x = left + self.BAR_WIDTH + 8
        text_y = y - 4
        painter.fillRect(
            text_x - 3, text_y - metrics.ascent() - 2,
            metrics.horizontalAdvance(text) + 6, metrics.height() + 3,
            QColor(255, 255, 255, 225),
        )
        painter.setPen(color.darker(115))
        painter.drawText(text_x, text_y, text)
        painter.restore()

    def _unit_boundary_depths(self, max_depth):
        depths = []
        for unit in self.units:
            for key in ("z_suht_ylemine", "z_suht_alumine"):
                raw = unit.get(key)
                if raw in (None, ""):
                    continue
                depth = _number(raw)
                if 0 <= depth <= max_depth:
                    depths.append(round(depth, 4))
        return sorted(set(depths))

    def _draw_boundary_depth_labels(
        self, painter, depth_y, max_depth, bar_left, draw_height, top_margin,
    ):
        depths = self._unit_boundary_depths(max_depth)
        if not depths:
            return

        top = float(top_margin)
        bottom = top + float(draw_height)
        targets = [float(depth_y(depth)) for depth in depths]
        if len(targets) == 1:
            positions = targets
        else:
            gap = min(12.0, (bottom - top) / (len(targets) - 1))
            positions = [max(top, targets[0])]
            for target in targets[1:]:
                positions.append(max(target, positions[-1] + gap))
            if positions[-1] > bottom:
                positions[-1] = bottom
                for index in range(len(positions) - 2, -1, -1):
                    positions[index] = min(positions[index], positions[index + 1] - gap)

        old_font = painter.font()
        label_font = painter.font()
        label_font.setPixelSize(10)
        painter.setFont(label_font)
        painter.setPen(QPen(QColor("#4a4a4a"), 1))
        bar_right = bar_left + self.BAR_WIDTH
        text_left = bar_right + 8
        for depth, target, position in zip(depths, targets, positions):
            target_y = round(target)
            label_y = round(position)
            painter.drawLine(bar_right, target_y, bar_right + 4, target_y)
            if abs(position - target) > 1:
                painter.drawLine(bar_right + 4, target_y, bar_right + 6, label_y)
            painter.drawText(text_left, label_y + 4, f"{depth:g} m")
        painter.setFont(old_font)

    def _draw_intervals(
        self, painter, rows, left, color, top_margin, draw_height, max_depth,
        sarv=False,
    ):
        fill = QColor(color)
        fill.setAlpha(185)
        painter.setPen(QPen(color.darker(130), 1))
        painter.setBrush(fill)
        items = []
        for order, row in enumerate(rows):
            start = _number(row.get("z_suht_ylemine"))
            end = _number(row.get("z_suht_alumine"))
            if start < 0 or start > max_depth:
                continue
            invalid_end = end < start or end > max_depth
            if invalid_end:
                end = start
            y1 = top_margin + draw_height * start / max_depth
            y2 = top_margin + draw_height * end / max_depth
            height = max(3, round(y2 - y1))
            depth_text = _depth_text(start, end)
            if invalid_end:
                depth_text += f" — {self.plugin.t('Vigane alumine sügavus')}"
            items.append({
                "row": row,
                "order": order,
                "top": round(y1),
                "bottom": round(y1) + height,
                "center": round((y1 + y2) / 2),
                "depth": depth_text,
                "invalid": invalid_end,
            })

        if not sarv:
            for item in items:
                self._draw_interval_item(painter, item, left, 11)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            return

        buckets = {}
        for item in items:
            bucket = item["center"] // self.SARV_CLUSTER_PIXELS
            buckets.setdefault(bucket, []).append(item)
        for bucket_items in buckets.values():
            bucket_items.sort(key=lambda item: (item["center"], item["order"]))
            if self.group_sarv_overlaps and len(bucket_items) > self.SARV_LANES:
                self._draw_interval_cluster(painter, bucket_items, left, color)
                continue
            painter.setPen(QPen(color.darker(130), 1))
            painter.setBrush(fill)
            for lane, item in enumerate(bucket_items):
                lane %= self.SARV_LANES
                item_left = left + lane * (self.SARV_LANE_WIDTH + self.SARV_LANE_GAP)
                self._draw_interval_item(
                    painter, item, item_left, self.SARV_LANE_WIDTH,
                )
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_interval_item(self, painter, item, left, width):
        top = item["top"]
        height = max(3, item["bottom"] - top)
        painter.drawRect(left, top, width, height)
        row = item["row"]
        if row.get("_url"):
            label = str(row.get("_label") or "")
            tooltip = " · ".join(value for value in (label, item["depth"]) if value)
            self._click_targets.append({
                "rect": (left, top, left + width, top + height),
                "urls": [row["_url"]],
                "items": [{
                    "url": row["_url"], "label": label, "depth": item["depth"],
                }],
                "label": tooltip,
                "kind": "records",
            })

    def _draw_interval_cluster(self, painter, items, left, color):
        center = round(sum(item["center"] for item in items) / len(items))
        height = 10
        top = center - height // 2
        width = self.SARV_TRACK_WIDTH
        cluster_fill = QColor(color)
        cluster_fill.setAlpha(220)
        painter.setBrush(cluster_fill)
        painter.setPen(QPen(color.darker(150), 1))
        painter.drawRoundedRect(left, top, width, height, 3, 3)
        painter.setPen(QColor("white"))
        painter.drawText(
            left, top, width, height,
            Qt.AlignmentFlag.AlignCenter,
            f"×{len(items)}",
        )
        painter.setPen(QPen(color.darker(130), 1))
        urls = []
        menu_items = []
        for item in items:
            row = item["row"]
            if not row.get("_url"):
                continue
            urls.append(row["_url"])
            menu_items.append({
                "url": row["_url"],
                "label": str(row.get("_label") or ""),
                "depth": item["depth"],
            })
        if urls:
            preview = [
                " · ".join(value for value in (item["label"], item["depth"]) if value)
                for item in menu_items[:4]
            ]
            if len(menu_items) > 4:
                preview.append(f"… +{len(menu_items) - 4}")
            invalid_count = sum(1 for item in items if item.get("invalid"))
            if invalid_count:
                preview.append(
                    f"⚠ {invalid_count} × {self.plugin.t('Vigane alumine sügavus')}"
                )
            self._click_targets.append({
                "rect": (left, top, left + width, top + height),
                "urls": urls,
                "items": menu_items,
                "label": "\n".join(preview),
                "kind": "records",
            })

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            target = self._target_at(event.position().x(), event.position().y())
            if target:
                urls = target["urls"]
                if len(urls) == 1:
                    QDesktopServices.openUrl(QUrl(urls[0]))
                else:
                    menu = QMenu(self)
                    items = target.get("items", [])
                    for index, url in enumerate(urls, start=1):
                        if target.get("kind") == "images":
                            text = f"{self.plugin.t('Pilt')} {index}"
                        else:
                            item = items[index - 1] if index <= len(items) else {}
                            text = " · ".join(
                                value for value in (
                                    str(item.get("label") or ""),
                                    str(item.get("depth") or ""),
                                ) if value
                            ) or str(url)
                        action = menu.addAction(text)
                        action.triggered.connect(
                            lambda checked=False, link=url: QDesktopServices.openUrl(QUrl(link))
                        )
                    menu.exec(event.globalPosition().toPoint())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        target = self._target_at(event.position().x(), event.position().y())
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if target else Qt.CursorShape.ArrowCursor
        )
        self.setToolTip(target.get("label", "") if target else "")
        super().mouseMoveEvent(event)

    def _target_at(self, x, y):
        for target in reversed(self._click_targets):
            left, top, right, bottom = target["rect"]
            if left <= x <= right and top <= y <= bottom:
                return target
        return None


class DetailWidget(QWidget):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        t = plugin.t
        layout = QVBoxLayout(self)
        self.header = QLabel(t("Klõpsa kaardil puuraugul või vaatluspunktil."))
        self.header.setWordWrap(True)
        self.header.setStyleSheet("font-size: 15px; font-weight: 600; padding: 6px;")
        header_host = QWidget()
        header_layout = QHBoxLayout(header_host)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.header, 1)
        self.add_to_cross_section = QCheckBox(t("Lisa läbilõikele"))
        self.add_to_cross_section.setVisible(False)
        self.add_to_cross_section.toggled.connect(
            self._toggle_cross_section
        )
        header_layout.addWidget(self.add_to_cross_section)
        layout.addWidget(header_host)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.overview = self._table((t("Väli"), t("Väärtus")))
        self.tabs.addTab(self.overview, t("Üldandmed"))
        self.profile = ProfileWidget(plugin)
        profile_page = QWidget()
        profile_layout = QVBoxLayout(profile_page)
        profile_controls = QHBoxLayout()
        self.profile_apply_filters = QCheckBox(t("Rakenda filtrid"))
        self.profile_apply_filters.setChecked(False)
        profile_controls.addWidget(self.profile_apply_filters)
        profile_controls.addSpacing(12)
        self.profile_egt_label = QLabel("EGT:")
        profile_controls.addWidget(self.profile_egt_label)
        self.profile_veka_construction = QCheckBox(t("Konstruktsioon"))
        self.profile_veka_construction.setChecked(True)
        self.profile_veka_construction.setVisible(False)
        profile_controls.addWidget(self.profile_veka_construction)
        self.profile_veka_static_water_level = QCheckBox(
            t("Staatiline veetase")
        )
        self.profile_veka_static_water_level.setChecked(True)
        self.profile_veka_static_water_level.setVisible(False)
        profile_controls.addWidget(self.profile_veka_static_water_level)
        self.profile_lithology = QCheckBox(t("Litoloogia"))
        self.profile_boundary_depths = QCheckBox(t("Piiride sügavused"))
        self.profile_boxes = QCheckBox(t("Kastipiirid"))
        self.profile_samples = QCheckBox(t("Proovid"))
        self.profile_analyses = QCheckBox(t("Analüüsid"))
        for checkbox in (
            self.profile_lithology,
            self.profile_boundary_depths,
            self.profile_boxes,
            self.profile_samples,
            self.profile_analyses,
        ):
            checkbox.setChecked(True)
            profile_controls.addWidget(checkbox)
        profile_controls.addStretch(1)
        profile_layout.addLayout(profile_controls)
        sarv_controls = QHBoxLayout()
        self.profile_sarv_label = QLabel("SARV:")
        sarv_controls.addWidget(self.profile_sarv_label)
        self.profile_sarv_boxes = QCheckBox(t("Kastipiirid"))
        self.profile_sarv_samples = QCheckBox(t("Proovid"))
        self.profile_sarv_analyses = QCheckBox(t("Analüüsid"))
        self.profile_sarv_specimens = QCheckBox(t("Eksemplarid"))
        self.profile_sarv_grouping = QCheckBox(t("Koonda kattuvad"))
        for checkbox in (
            self.profile_sarv_boxes,
            self.profile_sarv_samples,
            self.profile_sarv_analyses,
            self.profile_sarv_specimens,
            self.profile_sarv_grouping,
        ):
            checkbox.setChecked(True)
            sarv_controls.addWidget(checkbox)
        sarv_controls.addStretch(1)
        profile_layout.addLayout(sarv_controls)
        profile_scroll = QScrollArea()
        profile_scroll.setWidgetResizable(True)
        profile_scroll.setWidget(self.profile)
        profile_layout.addWidget(profile_scroll)
        self.tabs.addTab(profile_page, t("Läbilõige"))
        self.profile_apply_filters.toggled.connect(
            self.refresh_profile_filters
        )
        self.profile_lithology.toggled.connect(
            lambda checked: self.profile.set_options(lithology=checked)
        )
        self.profile_boundary_depths.toggled.connect(
            lambda checked: self.profile.set_options(boundary_depths=checked)
        )
        self.profile_veka_construction.toggled.connect(
            lambda checked: self.profile.set_options(
                veka_construction=checked and self._veka_mode
            )
        )
        self.profile_veka_static_water_level.toggled.connect(
            lambda checked: self.profile.set_options(
                veka_static_water_level=checked and self._veka_mode
            )
        )
        self.profile_boxes.toggled.connect(
            lambda checked: self.profile.set_options(core_boxes=checked)
        )
        self.profile_samples.toggled.connect(
            lambda checked: self.profile.set_options(samples=checked)
        )
        self.profile_analyses.toggled.connect(
            lambda checked: self.profile.set_options(analyses=checked)
        )
        self.profile_sarv_samples.toggled.connect(
            lambda checked: self.profile.set_options(sarv_samples=checked)
        )
        self.profile_sarv_boxes.toggled.connect(
            lambda checked: self.profile.set_options(sarv_core_boxes=checked)
        )
        self.profile_sarv_analyses.toggled.connect(
            lambda checked: self.profile.set_options(sarv_analyses=checked)
        )
        self.profile_sarv_specimens.toggled.connect(
            lambda checked: self.profile.set_options(sarv_specimens=checked)
        )
        self.profile_sarv_grouping.toggled.connect(
            lambda checked: self.profile.set_options(sarv_grouping=checked)
        )
        core_page, self.core, self.core_sources = self._source_page(
            (
                t("Allikas"), t("Kast"), t("Ülemine"), t("Alumine"),
                t("Diameeter"), t("Staatus / hoiukoht"), t("Pildid"),
                t("Muudetud"),
            ),
            ("EGT", "SARV"),
        )
        core_edit_controls = QHBoxLayout()
        self.core_edit_mode = QPushButton(t("Redigeerimisrežiim"))
        self.core_edit_mode.setCheckable(True)
        self.core_edit_mode.setStyleSheet(
            "QPushButton:checked {"
            " background-color: #8b5a2b; color: white; font-weight: 600;"
            "}"
        )
        self.core_edit_mode.toggled.connect(self._set_core_edit_mode)
        self.core_edit_button = QPushButton(t("Muuda valitud kasti…"))
        self.core_edit_button.clicked.connect(self._edit_selected_core)
        self.core_reset_button = QPushButton(t("Taasta algandmed"))
        self.core_reset_button.clicked.connect(self._reset_selected_core)
        self.core_edit_hint = QLabel(t(
            "Muudatused salvestuvad ainult selles arvutis."
        ))
        self.core_edit_hint.setWordWrap(True)
        core_edit_controls.addWidget(self.core_edit_mode)
        core_edit_controls.addWidget(self.core_edit_button)
        core_edit_controls.addWidget(self.core_reset_button)
        core_edit_controls.addWidget(self.core_edit_hint, 1)
        core_page.layout().insertLayout(1, core_edit_controls)
        self.core.itemSelectionChanged.connect(
            self._update_core_edit_actions
        )
        self.tabs.addTab(core_page, t("Puursüdamik"))
        samples_page, self.samples, self.sample_sources = self._source_page(
            (t("Allikas"), t("Tähis"), t("Tüüp"), t("Ülemine"), t("Alumine"), t("Eesmärk"), t("Staatus")),
            ("EGT", "SARV"),
        )
        self.tabs.addTab(samples_page, t("Proovid"))
        analyses_page, self.analyses, self.analysis_sources = self._source_page(
            (
                t("Allikas"), t("Kood"), t("Sügavus"), t("Kuupäev"),
                t("Meetod"), t("Labor"), t("Näitajad"),
            ),
            ("EGT", "SARV"),
        )
        self.tabs.addTab(analyses_page, t("Analüüsid"))
        specimens_page, self.specimens, self.specimen_sources = self._source_page(
            (t("Allikas"), t("Tähis"), t("Tüüp"), t("Sügavus"), t("Intervall"), t("Kivim")),
            ("SARV",),
        )
        self.tabs.addTab(specimens_page, t("Eksemplarid"))
        self.attachments = self._table(
            (t("Tüüp"), t("Fail"), t("Link")), sortable=True,
        )
        self.attachments.cellDoubleClicked.connect(self._open_attachment)
        self.tabs.addTab(self.attachments, t("Manused"))
        literature_page, self.literature, self.literature_sources = self._source_page(
            (t("Allikas"), t("Autor"), t("Aasta"), t("Pealkiri"), t("Tüüp"), t("Link")),
            ("SARV",),
        )
        self.tabs.addTab(literature_page, t("Kirjandus"))
        self.veka_construction = self._table((
            t("Liik"), t("Tüüp"), t("Algus, m"), t("Lõpp, m"),
            t("Diameeter, mm"), t("Ehitustooted"), t("Isolatsioon"),
            t("Kirjeldus"),
        ), sortable=True)
        self.veka_construction_index = self.tabs.addTab(
            self.veka_construction, t("Konstruktsioon")
        )
        self.veka_pumping = self._table((
            t("Kuupäev"), t("Tüüp"), t("Veekompleks"), t("Sügavus, m"),
            t("Staatiline veetase, m"), t("Dünaamiline veetase, m"),
            t("Alandus, m"), t("Deebit, l/s"),
            t("Eritootlikkus, l/(s·m)"), t("Kestus"), t("Tehnoloogia"),
        ), sortable=True)
        self.veka_pumping_index = self.tabs.addTab(
            self.veka_pumping, t("Pumpamiskatsed")
        )
        self.veka_chemistry = self._table((
            t("Analüüs"), t("Proovivõtu aeg"), t("Näitaja"),
            t("Tulemus"), t("Ühik"),
            t("Ühtlustatud tulemus"), t("Ühtlustatud ühik"),
            t("Proovi liik"), t("Protokoll"),
        ), sortable=True)
        self.veka_chemistry_index = self.tabs.addTab(
            self.veka_chemistry, t("Veekeemia")
        )
        self._veka_mode = False
        self._last_standard_tab = 0
        self._last_veka_tab = 0
        self._core_rows = []
        self._egt_core_images = {}
        self._sarv_core_rows = []
        self._sarv_core_images = {}
        self._core_display_records = {}
        self._egt_samples = []
        self._sarv_samples = []
        self._sarv_samples_by_source = {"locality": [], "site": []}
        self._egt_analyses = ([], {})
        self._sarv_analyses_by_source = {"sample": [], "specimen": []}
        self._sarv_specimens = []
        self._sarv_literature = []
        self._sarv_analysis_refs = {"sample": [], "specimen": []}
        self._overview_has_sarv_id = False
        self._overview_sarv_locality_id = None
        self._overview_base_rows = 0
        self._current_detail_name = ""
        self._current_detail_role = ""
        self._current_detail_attributes = {}
        for checkbox in self.core_sources.values():
            checkbox.toggled.connect(self._refresh_core)
        for checkbox in self.sample_sources.values():
            checkbox.toggled.connect(self._refresh_samples)
        for checkbox in self.analysis_sources.values():
            checkbox.toggled.connect(self._refresh_analyses)
        for checkbox in self.specimen_sources.values():
            checkbox.toggled.connect(self._refresh_specimens)
        for checkbox in self.literature_sources.values():
            checkbox.toggled.connect(self._refresh_literature)
        self._update_core_edit_actions()
        self._set_veka_mode(False)

    @staticmethod
    def _table(headers, sortable=False):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        if sortable:
            # Keep the source order until the user actually clicks a header.
            table.horizontalHeader().setSortIndicator(
                -1, Qt.SortOrder.AscendingOrder
            )
            table.setSortingEnabled(True)
        return table

    @classmethod
    def _source_page(cls, headers, sources):
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        checks = {}
        for source in sources:
            checkbox = QCheckBox(source)
            checkbox.setChecked(True)
            checks[source] = checkbox
            controls.addWidget(checkbox)
        controls.addStretch(1)
        layout.addLayout(controls)
        table = cls._table(headers, sortable=True)
        layout.addWidget(table)
        return page, table, checks

    def _set_veka_mode(self, enabled):
        """Show only data tabs that are meaningful for the active source."""
        enabled = bool(enabled)
        current = self.tabs.currentIndex()
        mode_changed = enabled != self._veka_mode
        if mode_changed:
            if self._veka_mode:
                self._last_veka_tab = current
            else:
                self._last_standard_tab = current
        standard_indices = range(2, 8)
        veka_indices = (
            self.veka_construction_index,
            self.veka_pumping_index,
            self.veka_chemistry_index,
        )
        for index in standard_indices:
            self.tabs.setTabVisible(index, not enabled)
        for index in veka_indices:
            self.tabs.setTabVisible(index, enabled)
        self.profile_egt_label.setText("VEKA:" if enabled else "EGT:")
        self.profile_veka_construction.setVisible(enabled)
        self.profile_veka_static_water_level.setVisible(enabled)
        self.profile_apply_filters.setVisible(not enabled)
        for widget in (
            self.profile_boxes, self.profile_samples, self.profile_analyses,
            self.profile_sarv_label, self.profile_sarv_boxes,
            self.profile_sarv_samples, self.profile_sarv_analyses,
            self.profile_sarv_specimens, self.profile_sarv_grouping,
        ):
            widget.setVisible(not enabled)
        self.profile.set_options(
            core_boxes=(
                False if enabled else self.profile_boxes.isChecked()
            ),
            sarv_core_boxes=(
                False if enabled else self.profile_sarv_boxes.isChecked()
            ),
            samples=(
                False if enabled else self.profile_samples.isChecked()
            ),
            analyses=(
                False if enabled else self.profile_analyses.isChecked()
            ),
            sarv_samples=(
                False if enabled else self.profile_sarv_samples.isChecked()
            ),
            sarv_analyses=(
                False if enabled else self.profile_sarv_analyses.isChecked()
            ),
            sarv_specimens=(
                False if enabled else self.profile_sarv_specimens.isChecked()
            ),
            veka_construction=(
                enabled and self.profile_veka_construction.isChecked()
            ),
            veka_static_water_level=(
                enabled and self.profile_veka_static_water_level.isChecked()
            ),
        )
        self._veka_mode = enabled
        if not mode_changed:
            target = current
        elif enabled:
            target = current if current in {0, 1} else self._last_veka_tab
            if target not in {0, 1, *veka_indices}:
                target = 0
        else:
            target = current if current in {0, 1} else self._last_standard_tab
            if target not in set(range(0, 8)):
                target = 0
        self.tabs.setCurrentIndex(target)

    def show_loading(self, name, attributes, role):
        self._current_detail_name = str(name)
        self._current_detail_role = str(role)
        self._current_detail_attributes = dict(attributes or {})
        supported = role in {
            "boreholes", "observations", "veka_boreholes",
            "sarv_drillcores",
        }
        key = self.current_cross_section_key()
        self.add_to_cross_section.blockSignals(True)
        self.add_to_cross_section.setVisible(supported)
        self.add_to_cross_section.setChecked(
            bool(
                supported and key
                and self.plugin.cross_section_contains(key)
            )
        )
        self.add_to_cross_section.blockSignals(False)
        self._set_veka_mode(role == "veka_boreholes")
        self.header.setText(f"{name} — {self.plugin.t('seotud andmeid laaditakse…')}")
        sarv_id = str(attributes.get("sarv_id") or "").strip()
        self._overview_has_sarv_id = (
            sarv_id.isdigit() and int(sarv_id) > 0
        )
        self._overview_sarv_locality_id = None
        self._fill_pairs(self.overview, attributes, role)
        self._overview_base_rows = self.overview.rowCount()
        self.profile.set_core_applicable(
            role in {"boreholes", "sarv_drillcores"}
        )
        self.profile.set_total_depth(
            attributes.get("pikkus") or attributes.get("vertikaalne_ulatus")
            or attributes.get("depth") or attributes.get("sygavus")
        )
        self.profile.set_units([])
        self.profile.set_core_boxes([])
        self.profile.set_core_images({})
        self.profile.set_sarv_core_boxes([])
        self.profile.set_sarv_core_images({})
        self.profile.set_samples([])
        self.profile.set_analyses([])
        self.profile.set_sarv_samples([])
        self.profile.set_sarv_analyses([])
        self.profile.set_sarv_specimens([])
        self.profile.set_veka_construction([])
        self.profile.set_veka_static_water_level(None)
        self._core_rows = []
        self._egt_core_images = {}
        self._sarv_core_rows = []
        self._sarv_core_images = {}
        self._egt_samples = []
        self._sarv_samples = []
        self._sarv_samples_by_source = {"locality": [], "site": []}
        self._egt_analyses = ([], {})
        self._sarv_analyses_by_source = {"sample": [], "specimen": []}
        self._sarv_specimens = []
        self._sarv_literature = []
        self._sarv_analysis_refs = {"sample": [], "specimen": []}
        for table in (
            self.core, self.samples, self.analyses, self.specimens,
            self.attachments, self.literature, self.veka_construction,
            self.veka_pumping, self.veka_chemistry,
        ):
            table.setRowCount(0)
        for index, title in enumerate(
            (
                "Läbilõige", "Puursüdamik", "Proovid", "Analüüsid",
                "Eksemplarid", "Manused", "Kirjandus",
            ), start=1
        ):
            self.tabs.setTabText(index, f"{self.plugin.t(title)} (…)")
        for index, title in (
            (self.veka_construction_index, "Konstruktsioon"),
            (self.veka_pumping_index, "Pumpamiskatsed"),
            (self.veka_chemistry_index, "Veekeemia"),
        ):
            self.tabs.setTabText(index, f"{self.plugin.t(title)} (…)")

    def current_cross_section_key(self):
        attributes = self._current_detail_attributes
        identifier = next((
            attributes.get(key) for key in (
                "esri_globalid", "globalid", "eelis_id", "sarv_id",
                "gea_id", "kkr_kood", "number",
            ) if attributes.get(key) not in (None, "")
        ), "")
        return (
            f"{self._current_detail_role}:{identifier}"
            if identifier else ""
        )

    def cross_section_snapshot(self):
        key = self.current_cross_section_key()
        if not key:
            return None
        attributes = self._current_detail_attributes

        def optional_number(*keys):
            for name in keys:
                value = attributes.get(name)
                if value not in (None, "", "NULL", "<NULL>"):
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        continue
            return None

        source = {
            "boreholes": "EGT PA",
            "observations": "EGT VP",
            "veka_boreholes": "VEKA",
            "sarv_drillcores": "SARV",
        }.get(self._current_detail_role, self._current_detail_role)
        return {
            "key": key,
            "role": self._current_detail_role,
            "source": source,
            "id": key.split(":", 1)[-1],
            "name": self._current_detail_name,
            "x": optional_number("_qeoloog_x_3301", "kesk_x"),
            "y": optional_number("_qeoloog_y_3301", "kesk_y"),
            "elevation": optional_number(
                "z_abs", "elevation", "altitude", "height"
            ),
            "elevation_source": (
                "z_abs" if attributes.get("z_abs") not in (None, "")
                else "SARV" if self._current_detail_role.startswith("sarv_")
                else ""
            ),
            "depth": self.profile.total_depth,
            "units": self.profile.units,
            "core_boxes": self.profile.core_boxes,
            "sarv_core_boxes": self.profile.sarv_core_boxes,
            "samples": self.profile.samples,
            "analyses": self.profile.analyses,
            "sarv_samples": self.profile.sarv_samples,
            "sarv_analyses": self.profile.sarv_analyses,
            "sarv_specimens": self.profile.sarv_specimens,
            "veka_construction": self.profile.veka_construction,
            "static_water": self.profile.veka_static_water_level,
        }

    def _toggle_cross_section(self, checked):
        key = self.current_cross_section_key()
        if not key:
            return
        if checked:
            self.plugin.add_current_detail_to_cross_section()
        else:
            self.plugin.remove_cross_section_item(key)

    def _notify_cross_section_update(self):
        if self.add_to_cross_section.isChecked():
            self.plugin.add_current_detail_to_cross_section()

    def set_ready(self, name):
        self.header.setText(name)

    def set_sarv_locality(self, locality):
        """Add an inferred SARV locality link without duplicating an explicit sarv_id."""
        locality_id = locality.get("id") if isinstance(locality, dict) else None
        if not locality_id or self._overview_has_sarv_id:
            return
        if str(locality_id) == str(self._overview_sarv_locality_id):
            return
        self._overview_sarv_locality_id = locality_id
        number = locality.get("number") or ""
        name = locality.get("name_en") if self.plugin.language == "en" else locality.get("name")
        display = " — ".join(str(value) for value in (number, name) if value) or str(locality_id)
        row = self.overview.rowCount()
        self.overview.insertRow(row)
        self.overview.setItem(row, 0, QTableWidgetItem("SARV"))
        self._set_link_widget(
            self.overview, row, 1, display,
            f"https://geoloogia.info/locality/{locality_id}",
        )
        self.overview.resizeColumnsToContents()

    def add_match_candidates(
        self, label, candidates, open_callback=None,
        confirm_callback=None, remove_callback=None, edit_callback=None,
    ):
        for candidate in candidates:
            row = self.overview.rowCount()
            self.overview.insertRow(row)
            self.overview.setItem(row, 0, QTableWidgetItem(self.plugin.t(label)))
            host = QWidget()
            layout = QHBoxLayout(host)
            layout.setContentsMargins(4, 0, 4, 0)
            text = html_escape(str(candidate.get("text") or candidate.get("id") or ""))
            url = html_escape(str(candidate.get("url") or ""))
            value = QLabel(f'<a href="{url}">{text}</a>' if url else text)
            value.setOpenExternalLinks(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            layout.addWidget(value)
            evidence = candidate.get("evidence")
            if evidence:
                evidence_label = QLabel(str(evidence))
                evidence_label.setStyleSheet("color: #666666;")
                layout.addWidget(evidence_label)
            if open_callback:
                button = QPushButton(self.plugin.t("Ava rakenduses"))
                button.clicked.connect(
                    lambda checked=False, item=candidate: open_callback(item)
                )
                layout.addWidget(button)
            if edit_callback:
                button = QPushButton(self.plugin.t("Muuda SARV seost"))
                button.clicked.connect(
                    lambda checked=False, item=candidate: edit_callback(item)
                )
                layout.addWidget(button)
            if confirm_callback and not candidate.get("confirmed"):
                button = QPushButton(self.plugin.t("Kinnita vaste"))
                button.clicked.connect(
                    lambda checked=False, item=candidate: confirm_callback(item)
                )
                layout.addWidget(button)
            if remove_callback and candidate.get("manual"):
                button = QPushButton(self.plugin.t("Eemalda vaste"))
                button.clicked.connect(
                    lambda checked=False, item=candidate: remove_callback(item)
                )
                layout.addWidget(button)
            layout.addStretch(1)
            self.overview.setCellWidget(row, 1, host)
        self.overview.resizeColumnsToContents()

    def reset_match_rows(self):
        """Remove inferred/match rows while retaining source attributes."""
        self.overview.setRowCount(self._overview_base_rows)

    def add_sarv_match_editor(
        self, current_type, current_id, manual, edit_callback,
        reset_callback=None, source_sarv_id="", source_ma_id="",
        invalid_sarv_id=False, invalid_ma_id=False,
        invalid_callback=None,
    ):
        row = self.overview.rowCount()
        self.overview.insertRow(row)
        self.overview.setItem(
            row, 0, QTableWidgetItem(self.plugin.t("SARV seose haldus")),
        )
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(4, 0, 4, 0)
        if current_id:
            prefix = (
                self.plugin.t("Kohalik parandus")
                if manual else self.plugin.t("GEA SARV ID")
            )
            type_label = self.plugin.t({
                "locality": "lokaliteet",
                "site": "uuringupunkt",
            }.get(current_type, "puursüdamik"))
            layout.addWidget(
                QLabel(f"{prefix}: {type_label} {current_id}"),
            )
        else:
            layout.addWidget(QLabel(self.plugin.t("SARV objekt pole seotud")))

        def ask_for_id():
            object_types = (
                (self.plugin.t("puursüdamik"), "drillcore"),
                (self.plugin.t("lokaliteet"), "locality"),
                (self.plugin.t("uuringupunkt"), "site"),
            )
            labels = [label for label, value in object_types]
            initial_type = next((
                index for index, (_, value) in enumerate(object_types)
                if value == current_type
            ), 0)
            type_label, accepted = QInputDialog.getItem(
                self,
                self.plugin.t("Määra SARV seos"),
                self.plugin.t("SARV objekti tüüp"),
                labels, initial_type, False,
            )
            if not accepted:
                return
            source_type = next(
                value for label, value in object_types
                if label == type_label
            )
            try:
                initial = max(1, int(current_id or 1))
            except (TypeError, ValueError):
                initial = 1
            value, accepted = QInputDialog.getInt(
                self,
                self.plugin.t("Määra SARV seos"),
                self.plugin.t("SARV objekti ID"),
                initial, 1, 2147483647, 1,
            )
            if accepted:
                edit_callback(source_type, value)

        button = QPushButton(
            self.plugin.t("Muuda SARV seost")
            if current_id else self.plugin.t("Lisa SARV seos")
        )
        button.clicked.connect(ask_for_id)
        layout.addWidget(button)
        if manual and reset_callback:
            button = QPushButton(self.plugin.t("Taasta GEA seos"))
            button.clicked.connect(reset_callback)
            layout.addWidget(button)
        if source_sarv_id not in (None, ""):
            invalid_sarv = QCheckBox(
                f"{self.plugin.t('Vigane GEA sarv_id seos')}: "
                f"{source_sarv_id}"
            )
            invalid_sarv.setChecked(bool(invalid_sarv_id))
            if invalid_callback:
                invalid_sarv.toggled.connect(
                    lambda checked: invalid_callback(
                        "invalid_sarv_id", checked
                    )
                )
            layout.addWidget(invalid_sarv)
        if source_ma_id not in (None, ""):
            invalid_ma = QCheckBox(
                f"{self.plugin.t('Vigane Maa-ameti ID seos')}: "
                f"{source_ma_id}"
            )
            invalid_ma.setChecked(bool(invalid_ma_id))
            if invalid_callback:
                invalid_ma.toggled.connect(
                    lambda checked: invalid_callback(
                        "invalid_ma_id", checked
                    )
                )
            layout.addWidget(invalid_ma)
        layout.addStretch(1)
        self.overview.setCellWidget(row, 1, host)
        self.overview.resizeColumnsToContents()

    def set_profile(self, units):
        self.profile.set_units(units)
        self.tabs.setTabText(1, f"{self.plugin.t('Läbilõige')} ({len(units)})")
        self._notify_cross_section_update()

    def set_veka_construction(self, rows):
        self.profile.set_veka_construction(rows)
        values = []
        for row in rows:
            code = str(row.get("konstr_tyyp") or "")
            category = self.plugin.t({
                "filter": "Filter",
                "casing": "Manteltoru / toru",
                "open": "Avatud / filtrita osa",
                "drill": "Puuri diameeter",
                "other": "Muu",
            }[self.plugin.veka_construction_category(code)])
            values.append((
                category,
                row.get("konstr_tyyp_selg") or code,
                row.get("alg"), row.get("lopp"), row.get("diam"),
                row.get("tx_ehitustooted"),
                row.get("tx_manteltoru_isolats"), row.get("tx_kirjeldus"),
            ))
        self._fill_rows(self.veka_construction, values)
        self.tabs.setTabText(
            self.veka_construction_index,
            f"{self.plugin.t('Konstruktsioon')} ({len(values)})",
        )
        self._notify_cross_section_update()

    def set_veka_pumping_tests(self, rows):
        self.profile.set_veka_static_water_level(
            self.plugin.veka_static_water_level(rows)
        )
        values = [(
            row.get("katse_kp"),
            row.get("puurauk_param_tyyp_selg")
            or row.get("puurauk_param_tyyp"),
            row.get("veekompleks_selg") or row.get("veekompleks"),
            row.get("sygavus"), row.get("st_veetase"),
            row.get("dyn_veetase"), row.get("alandus"), row.get("deebit"),
            self.plugin.veka_specific_capacity(row), row.get("kestus"),
            row.get("tx_tehnoloogia"),
        ) for row in rows]
        self._fill_rows(self.veka_pumping, values)
        self.tabs.setTabText(
            self.veka_pumping_index,
            f"{self.plugin.t('Pumpamiskatsed')} ({len(values)})",
        )
        self._notify_cross_section_update()

    def set_veka_chemistry(self, rows):
        values = []
        for row in rows:
            normalized_value, normalized_unit = self.plugin.veka_analysis_result(
                row
            )
            values.append((
                row.get("analyys_number"), row.get("proov_algus"),
                row.get("naitaja_nimi") or row.get("naitaja_kood"),
                row.get("naitaja_tulem"),
                row.get("naitaja_yhik"), normalized_value, normalized_unit,
                row.get("proov_liik"),
                _link_cell(
                    row.get("_protocol_label") or self.plugin.t("Ava"),
                    row.get("_protocol_url"),
                ) if row.get("_protocol_url") else "",
            ))
        self._fill_rows(self.veka_chemistry, values)
        title = (
            f"{self.plugin.t('Veekeemia')} ({len(values)})"
            if values else self.plugin.t("Veekeemia (andmed puuduvad)")
        )
        self.tabs.setTabText(self.veka_chemistry_index, title)

    def set_veka_overview_fields(self, values):
        """Add or update selected VEKA detail fields in the overview."""
        for key, value in values.items():
            if value in (None, ""):
                continue
            label = field_label(str(key), self.plugin.language)
            target_row = None
            for row in range(self.overview.rowCount()):
                item = self.overview.item(row, 0)
                if item and item.text() == label:
                    target_row = row
                    break
            if target_row is None:
                target_row = self.overview.rowCount()
                self.overview.insertRow(target_row)
                self.overview.setItem(
                    target_row, 0, QTableWidgetItem(label)
                )
            self.overview.setItem(
                target_row, 1, QTableWidgetItem(_display_value(value))
            )
        self._overview_base_rows = self.overview.rowCount()
        self.overview.resizeColumnsToContents()

    def set_core(self, rows):
        self._core_rows = list(rows)
        self._refresh_core()
        self._notify_cross_section_update()

    def set_core_images(self, attachments):
        images_by_core = {}
        for attachment in attachments:
            core_id = str(attachment.get("puursydamik_kastis_id") or "").upper()
            link = attachment.get("link") or ""
            if not core_id or not _is_image_attachment(attachment):
                continue
            images_by_core.setdefault(core_id, []).append(_attachment_url(link))
        self._egt_core_images = images_by_core
        self.profile.set_core_images(images_by_core)
        self._refresh_core()

    def set_sarv_core(self, rows):
        self._sarv_core_rows = list(rows)
        self._refresh_core()
        self._notify_cross_section_update()

    def set_sarv_core_images(self, attachments):
        by_filename = {}
        for attachment in attachments:
            filename = str(
                attachment.get("uuid_filename") or attachment.get("filename") or ""
            ).lower()
            url = _sarv_attachment_url(
                attachment.get("original_file_url") or attachment.get("preview_large_url")
            )
            if filename and url:
                by_filename.setdefault(filename, []).append(str(url))
        images_by_core = {}
        for row in self._sarv_core_rows:
            filename = str(row.get("image") or "").lower()
            urls = by_filename.get(filename, [])
            if not urls and filename:
                urls = [_sarv_image_url(filename)]
            if urls:
                images_by_core[str(row.get("id"))] = urls
        self._sarv_core_images = images_by_core
        self.profile.set_sarv_core_images(images_by_core)
        self._refresh_core()

    def _refresh_core(self):
        entries = []
        values = []
        self._core_display_records = {}
        corrected_egt = [
            (
                row,
                self.plugin.corrected_core_box("EGT", row),
            )
            for row in self._core_rows
        ]
        prepared_sarv = []
        for row in self._sarv_core_rows:
            source_row = dict(row)
            source_row["_qeoloog_status"] = (
                _nested_text(row.get("storage"), self.plugin.language)
                or _nested_text(row.get("location"), self.plugin.language)
                or _nested_text(
                    row.get("_drillcore_storage"), self.plugin.language
                )
                or row.get("_drillcore_name")
            )
            prepared_sarv.append((
                source_row,
                self.plugin.corrected_core_box("SARV", source_row),
            ))
        self.profile.set_core_boxes([
            corrected for _, corrected in corrected_egt
        ])
        self.profile.set_sarv_core_boxes([
            track for _, corrected in prepared_sarv
            if (track := _sarv_core_track(corrected)) is not None
        ])
        if self.core_sources["EGT"].isChecked():
            for source_row, row in corrected_egt:
                urls = self._egt_core_images.get(
                    str(source_row.get("globalid") or "").upper(), []
                )
                key = core_correction_key("EGT", source_row)
                correction = self.plugin.core_corrections.get(key, {})
                self._core_display_records[key] = {
                    "source": "EGT",
                    "raw": source_row,
                    "corrected": row,
                }
                entries.append(urls)
                values.append((
                    "EGT", row.get("kast_nr"), row.get("z_suht_ylemine"),
                    row.get("z_suht_alumine"), row.get("diameeter"),
                    row.get("staatus"), "",
                    str(correction.get("updated_at") or "")[:19],
                ))
        if self.core_sources["SARV"].isChecked():
            for source_row, row in prepared_sarv:
                urls = self._sarv_core_images.get(
                    str(source_row.get("id")), []
                )
                key = core_correction_key("SARV", source_row)
                correction = self.plugin.core_corrections.get(key, {})
                self._core_display_records[key] = {
                    "source": "SARV",
                    "raw": source_row,
                    "corrected": row,
                }
                entries.append(urls)
                values.append((
                    "SARV", row.get("number"), row.get("depth_start"),
                    row.get("depth_end"), row.get("diameter"),
                    row.get("_qeoloog_status"), "",
                    str(correction.get("updated_at") or "")[:19],
                ))
        sorting_state = self._fill_rows(
            self.core, values, restore_sorting=False
        )
        for row_index, (key, record) in enumerate(
            self._core_display_records.items()
        ):
            item = self.core.item(row_index, 0)
            if item:
                item.setData(Qt.ItemDataRole.UserRole, key)
            urls = entries[row_index]
            if not urls:
                continue
            anchors = " · ".join(
                f'<a href="{html_escape(url)}">{self.plugin.t("Pilt")} {index}</a>'
                for index, url in enumerate(urls, start=1)
            )
            label = QLabel(anchors)
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            label.setContentsMargins(4, 0, 4, 0)
            label.setToolTip(self.plugin.t("Ava puursüdamiku kasti pilt"))
            self.core.setCellWidget(row_index, 6, label)
        self._restore_table_sorting(self.core, sorting_state)
        self.tabs.setTabText(
            2,
            f"{self.plugin.t('Puursüdamik')} "
            f"({len(self._core_rows) + len(self._sarv_core_rows)})",
        )
        self.core.resizeColumnsToContents()
        self._update_core_edit_actions()

    def _selected_core_record(self):
        row = self.core.currentRow()
        item = self.core.item(row, 0) if row >= 0 else None
        key = item.data(Qt.ItemDataRole.UserRole) if item else ""
        return self._core_display_records.get(str(key or ""))

    def _set_core_edit_mode(self, enabled):
        self.core_edit_hint.setText(
            self.plugin.t(
                "Vali kast ja vajuta „Muuda valitud kasti…“."
                if enabled else
                "Muudatused salvestuvad ainult selles arvutis."
            )
        )
        self._update_core_edit_actions()

    def _update_core_edit_actions(self):
        if not hasattr(self, "core_edit_mode"):
            return
        record = self._selected_core_record()
        enabled = self.core_edit_mode.isChecked() and record is not None
        self.core_edit_button.setEnabled(enabled)
        key = (
            core_correction_key(record["source"], record["raw"])
            if record else ""
        )
        self.core_reset_button.setEnabled(
            bool(enabled and key in self.plugin.core_corrections)
        )

    def _edit_selected_core(self):
        record = self._selected_core_record()
        if not self.core_edit_mode.isChecked() or not record:
            return
        key = core_correction_key(record["source"], record["raw"])
        if not key:
            QMessageBox.warning(
                self, self.plugin.t("Kohalik redigeerimine"),
                self.plugin.t(
                    "Sellel kastil puudub püsiv kirje ID ja seda ei saa "
                    "turvaliselt salvestada."
                ),
            )
            return
        dialog = CoreCorrectionDialog(
            self.plugin, record["source"], key.split(":", 1)[-1],
            core_values(record["source"], record["corrected"]), self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.plugin.save_core_box_correction(
            record["source"], record["raw"], dialog.values(), {
                "parent_role": self._current_detail_role,
                "parent_id": self.current_cross_section_key(),
                "parent_name": self._current_detail_name,
            },
        )
        self._refresh_core()
        self._notify_cross_section_update()

    def _reset_selected_core(self):
        record = self._selected_core_record()
        if not self.core_edit_mode.isChecked() or not record:
            return
        if QMessageBox.question(
            self, self.plugin.t("Taasta algandmed"),
            self.plugin.t(
                "Kas eemaldada selle kasti kohalikud parandused?"
            ),
        ) != QMessageBox.StandardButton.Yes:
            return
        if self.plugin.reset_core_box_correction(
            record["source"], record["raw"]
        ):
            self._refresh_core()
            self._notify_cross_section_update()

    def set_samples(self, rows):
        self._egt_samples = list(rows)
        self.refresh_profile_filters()
        self._refresh_samples()
        self._notify_cross_section_update()

    def set_sarv_samples(self, rows, source="locality"):
        self._sarv_samples_by_source[source] = list(rows)
        unique = {}
        anonymous = []
        for values in self._sarv_samples_by_source.values():
            for row in values:
                row_id = row.get("id") if isinstance(row, dict) else None
                if row_id in (None, ""):
                    anonymous.append(row)
                else:
                    unique[str(row_id)] = row
        self._sarv_samples = list(unique.values()) + anonymous
        self.refresh_profile_filters()
        self._refresh_samples()
        self._notify_cross_section_update()

    def _refresh_samples(self):
        values = []
        if self.sample_sources["EGT"].isChecked():
            values.extend(
                (
                    "EGT",
                    row.get("proov_tahis_alg"),
                    self.plugin.decode_egt(18, "proov_tyyp", row.get("proov_tyyp")),
                    row.get("z_suht_ylemine"),
                    row.get("z_suht_alumine"),
                    self.plugin.decode_egt(18, "eesmark", row.get("eesmark")),
                    self.plugin.decode_egt(18, "staatus", row.get("staatus")),
                )
                for row in self._egt_samples
            )
        if self.sample_sources["SARV"].isChecked():
            values.extend(
                (
                    "SARV",
                    _link_cell(
                        row.get("number") or row.get("id"),
                        f"https://geoloogia.info/sample/{row.get('id')}",
                    ),
                    _nested_text(row.get("type"), self.plugin.language),
                    row.get("depth"),
                    _sarv_interval_end(row),
                    _nested_text(row.get("purpose"), self.plugin.language),
                    _nested_text(row.get("database"), self.plugin.language),
                )
                for row in self._sarv_samples
            )
        self._fill_rows(self.samples, values)
        self.tabs.setTabText(
            3,
            f"{self.plugin.t('Proovid')} "
            f"({len(self._egt_samples) + len(self._sarv_samples)})",
        )

    def set_analyses(self, rows, results_by_analysis=None):
        self._egt_analyses = (list(rows), results_by_analysis or {})
        self.refresh_profile_filters()
        self._refresh_analyses()
        self._notify_cross_section_update()

    def set_sarv_analyses(self, source, rows):
        self._sarv_analyses_by_source[source] = list(rows)
        self.refresh_profile_filters()
        self._sarv_analysis_refs[source] = [
            {"reference": row.get("reference")} for row in rows if row.get("reference")
        ]
        self._refresh_analyses()
        self._refresh_literature()
        self._notify_cross_section_update()

    def _refresh_analyses(self):
        values = []
        egt_rows, results_by_analysis = self._egt_analyses
        if self.analysis_sources["EGT"].isChecked():
            for row in egt_rows:
                results = results_by_analysis.get(row.get("globalid"), [])
                indicators = ", ".join(
                    _analysis_result(
                        item, self.plugin.t("Näitaja"), self.plugin
                    ) for item in results[:8]
                )
                values.append((
                    "EGT", row.get("analyys_kood"), _egt_depth_text(row),
                    _date_value(row.get("kuupaev")),
                    self.plugin.decode_egt(
                        3, "analyys_meetod", row.get("analyys_meetod")
                    ),
                    self.plugin.decode_egt(3, "labor", row.get("labor")),
                    indicators,
                ))
        sarv_rows = sum(self._sarv_analyses_by_source.values(), [])
        if self.analysis_sources["SARV"].isChecked():
            for row in sarv_rows:
                method = _nested_text(row.get("analysis_method"), self.plugin.language)
                lab = _nested_text(row.get("lab"), self.plugin.language) or row.get("lab_text")
                values.append((
                    "SARV",
                    _link_cell(row.get("id"), f"https://geoloogia.info/analysis/{row.get('id')}"),
                    _sarv_analysis_depth_text(row),
                    row.get("date") or row.get("date_text"),
                    method or row.get("analysis_method_detail"),
                    lab,
                    row.get("material") or row.get("remarks"),
                ))
        self._fill_rows(self.analyses, values)
        self.tabs.setTabText(
            4,
            f"{self.plugin.t('Analüüsid')} "
            f"({len(egt_rows) + len(sarv_rows)})",
        )

    def refresh_decoded_values(self):
        """Refresh already-open tables after asynchronous domains arrive."""
        self._refresh_samples()
        self._refresh_analyses()

    def set_sarv_specimens(self, rows):
        self._sarv_specimens = list(rows)
        self.refresh_profile_filters()
        self._refresh_specimens()
        self._notify_cross_section_update()

    @staticmethod
    def _profile_filter_values(value):
        values = set()
        if isinstance(value, dict):
            for key in (
                "id", "code", "value", "value_en", "name", "name_en",
                "type",
            ):
                if value.get(key) not in (None, ""):
                    values.add(str(value[key]))
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                values.update(DetailWidget._profile_filter_values(item))
        elif value not in (None, ""):
            values.add(str(value))
        return values

    @classmethod
    def _profile_value_matches(cls, value, selected):
        return not selected or bool(
            cls._profile_filter_values(value).intersection(selected)
        )

    def refresh_profile_filters(self, checked=None):
        """Apply active EGT/SARV type filters only to profile markers."""
        apply_filters = bool(
            self.profile_apply_filters.isChecked() and self.plugin.dock
        )
        egt_samples = list(self._egt_samples)
        egt_analyses, results_by_analysis = self._egt_analyses
        egt_analyses = list(egt_analyses)
        sarv_samples = list(self._sarv_samples)
        sarv_analyses = sum(self._sarv_analyses_by_source.values(), [])
        sarv_specimens = list(self._sarv_specimens)

        if apply_filters:
            egt_requirements = (
                self.plugin.dock.filters.egt_domain_requirements()
            )
            sample_requirements = egt_requirements["samples"]
            egt_samples = [
                row for row in egt_samples
                if self.plugin._row_matches_domains(
                    row, sample_requirements
                )
            ]

            analysis_requirements = egt_requirements["analyses"]
            direct_requirements = {
                field: selected
                for (table_id, field), selected
                in analysis_requirements.items()
                if table_id == 3
            }
            result_requirements = {
                field: selected
                for (table_id, field), selected
                in analysis_requirements.items()
                if table_id == 4
            }
            filtered_analyses = []
            for row in egt_analyses:
                if not self.plugin._row_matches_domains(
                    row, direct_requirements
                ):
                    continue
                if any(result_requirements.values()):
                    results = results_by_analysis.get(
                        row.get("globalid"), []
                    )
                    if not any(
                        self.plugin._row_matches_domains(
                            result, result_requirements
                        )
                        for result in results
                    ):
                        continue
                filtered_analyses.append(row)
            egt_analyses = filtered_analyses

            sarv_requirements = self.plugin.dock.sarv_filters.requirements()
            sarv_samples = [
                row for row in sarv_samples
                if self._profile_value_matches(
                    row.get("purpose"),
                    sarv_requirements["sample_purpose"],
                )
                and self._profile_value_matches(
                    row.get("type"), sarv_requirements["sample_type"],
                )
            ]
            sarv_analyses = [
                row for row in sarv_analyses
                if self._profile_value_matches(
                    row.get("analysis_method"),
                    sarv_requirements["analysis_method"],
                )
            ]
            sarv_specimens = [
                row for row in sarv_specimens
                if self._profile_value_matches(
                    row.get("type"),
                    sarv_requirements["specimen_type"],
                )
            ]

        self.profile.set_samples(egt_samples)
        self.profile.set_analyses(egt_analyses)
        self.profile.set_sarv_samples([
            track for row in sarv_samples
            if (track := _sarv_track(row, "sample")) is not None
        ])
        self.profile.set_sarv_analyses([
            track for row in sarv_analyses
            if (track := _sarv_analysis_track(row)) is not None
        ])
        self.profile.set_sarv_specimens([
            track for row in sarv_specimens
            if (track := _sarv_track(row, "specimen")) is not None
        ])

    def _refresh_specimens(self):
        values = []
        if self.specimen_sources["SARV"].isChecked():
            values = [
                (
                    "SARV",
                    _link_cell(
                        row.get("specimen_id") or row.get("specimen_full_number") or row.get("id"),
                        f"https://geoloogia.info/specimen/{row.get('id')}",
                    ),
                    _nested_text(row.get("type"), self.plugin.language),
                    row.get("depth"),
                    row.get("depth_interval"),
                    _nested_text(row.get("classification"), self.plugin.language)
                    or row.get("part") or row.get("stratigraphy_free"),
                )
                for row in self._sarv_specimens
            ]
        self._fill_rows(self.specimens, values)
        self.tabs.setTabText(
            5,
            f"{self.plugin.t('Eksemplarid')} ({len(self._sarv_specimens)})",
        )

    def set_attachments(self, rows):
        values = []
        for row in rows:
            link = row.get("link") or ""
            url = _attachment_url(link)
            values.append((row.get("manus_tyyp"), str(link).split("/")[-1], url))
        self._fill_rows(self.attachments, values)
        self.tabs.setTabText(6, f"{self.plugin.t('Manused')} ({len(rows)})")

    def set_sarv_literature(self, rows):
        self._sarv_literature = list(rows)
        self._refresh_literature()

    def _refresh_literature(self):
        relations = list(self._sarv_literature)
        relations.extend(sum(self._sarv_analysis_refs.values(), []))
        unique = {}
        for relation in relations:
            reference = relation.get("reference") or {}
            if isinstance(reference, dict) and reference.get("id"):
                unique[reference["id"]] = (relation, reference)
        values = []
        if self.literature_sources["SARV"].isChecked():
            for reference_id, (relation, reference) in unique.items():
                title = (
                    reference.get("title") or reference.get("title_original")
                    or reference.get("reference")
                )
                values.append((
                    "SARV", reference.get("author"), reference.get("year"), title,
                    relation.get("type", {}).get("value")
                    if isinstance(relation.get("type"), dict) else "",
                    _link_cell(
                        reference.get("reference") or reference_id,
                        f"https://kirjandus.geoloogia.info/reference/{reference_id}",
                    ),
                ))
        self._fill_rows(self.literature, values)
        self.tabs.setTabText(7, f"{self.plugin.t('Kirjandus')} ({len(unique)})")

    def _open_attachment(self, row, column):
        item = self.attachments.item(row, 2)
        if item and item.text():
            QDesktopServices.openUrl(QUrl(item.text()))

    def _fill_pairs(self, table, attributes, role):
        rows = [
            (key, value) for key, value in attributes.items()
            if value not in (None, "")
            and not str(key).startswith(("_qeoloog_", "vk_"))
        ]
        # Dropping all rows also removes cell widgets left by the previous object.
        table.setRowCount(0)
        table.setRowCount(len(rows))
        object_path = "puurauk" if role == "boreholes" else "vaatluspunkt"
        for row_index, (key, value) in enumerate(rows):
            table.setItem(
                row_index, 0,
                QTableWidgetItem(field_label(str(key), self.plugin.language)),
            )
            key_lower = key.lower()
            display = _display_value(value)
            url = ""
            if key_lower == "gea_id":
                url = f"https://gis.egt.ee/auk/{object_path}/{display}/vaade"
            elif key_lower == "kkr_kood" and role == "veka_boreholes":
                url = f"https://veka.eelis.ee/puurauk/{display}"
            elif key_lower == "kande_alus_nr":
                url = f"https://fond.egt.ee/fond/egf/{display}"
            elif key_lower == "sarv_id":
                sarv_path = (
                    "site" if role == "sarv_sites"
                    else "locality" if role == "sarv_localities"
                    else "drillcore"
                )
                try:
                    valid_sarv_id = int(str(display)) > 0
                except (TypeError, ValueError):
                    valid_sarv_id = False
                if valid_sarv_id:
                    url = f"https://geoloogia.info/{sarv_path}/{display}"
            if url:
                self._set_link_widget(table, row_index, 1, display, url)
            else:
                table.setItem(row_index, 1, QTableWidgetItem(display))
        table.resizeColumnsToContents()

    @staticmethod
    def _set_link_widget(table, row, column, text, url):
        safe_text = html_escape(_display_value(text))
        safe_url = html_escape(str(url))
        link = QLabel(f'<a href="{safe_url}">{safe_text}</a>')
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        link.setContentsMargins(4, 0, 4, 0)
        link.setToolTip(str(url))
        table.setCellWidget(row, column, link)

    @staticmethod
    def _begin_table_update(table):
        header = table.horizontalHeader()
        state = (
            table.isSortingEnabled(),
            header.sortIndicatorSection(),
            header.sortIndicatorOrder(),
        )
        if state[0]:
            table.setSortingEnabled(False)
        return state

    @staticmethod
    def _restore_table_sorting(table, state):
        enabled, section, order = state
        if not enabled:
            return
        table.setSortingEnabled(True)
        if 0 <= section < table.columnCount():
            table.sortItems(section, order)

    @classmethod
    def _fill_rows(cls, table, rows, restore_sorting=True):
        sorting_state = cls._begin_table_update(table)
        table.clearContents()
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                if isinstance(value, dict) and value.get("url"):
                    raw_text = value.get("text")
                    table.setItem(
                        row_index, column, SortableTableItem(raw_text)
                    )
                    text = html_escape(_display_value(raw_text))
                    url = html_escape(str(value["url"]))
                    link = QLabel(f'<a href="{url}">{text}</a>')
                    link.setOpenExternalLinks(True)
                    link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                    link.setContentsMargins(4, 0, 4, 0)
                    link.setToolTip(str(value["url"]))
                    table.setCellWidget(row_index, column, link)
                else:
                    table.setItem(
                        row_index, column, SortableTableItem(value)
                    )
        if restore_sorting:
            cls._restore_table_sorting(table, sorting_state)
        table.resizeColumnsToContents()
        return sorting_state


class QeoloogDock(QDockWidget):
    def __init__(self, plugin, parent=None):
        super().__init__("Qeoloog", parent)
        self.setObjectName("Qeoloog_Dock")
        self.tabs = QTabWidget()
        self.layers = LayerConfigWidget(plugin)
        self.filters = FilterWidget(plugin)
        self.sarv_filters = SarvFilterWidget(plugin)
        self.veka = VekaWidget(plugin)
        self.search = SearchWidget(plugin)
        self.export = ExportWidget(plugin)
        self.cross_section_window = CrossSectionWindow(plugin, parent)
        self.cross_sections = self.cross_section_window.content
        self.cross_section_launcher = CrossSectionLauncher(
            plugin, self.cross_section_window
        )
        self.details = DetailWidget(plugin)
        self.tabs.addTab(self.layers, plugin.t("Kihid"))
        self.filter_page = self._scroll(self.filters)
        self.sarv_filter_page = self._scroll(self.sarv_filters)
        self.search_page = self._scroll(self.search)
        self.tabs.addTab(self.filter_page, plugin.t("EGT filtrid"))
        self.tabs.addTab(self.sarv_filter_page, plugin.t("SARV filtrid"))
        self.veka_page = self._scroll(self.veka)
        self.tabs.addTab(self.veka_page, plugin.t("VEKA"))
        self.tabs.addTab(self.search_page, plugin.t("Otsing"))
        self.export_page = self._scroll(self.export)
        self.tabs.addTab(self.export_page, plugin.t("Ekspordi"))
        self.tabs.addTab(
            self.cross_section_launcher, plugin.t("Läbilõiked")
        )
        self.tabs.addTab(self.details, plugin.t("Objekti andmed"))
        self.setWidget(self.tabs)

    @staticmethod
    def _scroll(widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def show_details(self):
        self.tabs.setCurrentWidget(self.details)
        self.show()
        self.raise_()

    def show_cross_sections(self):
        self.cross_section_window.show()
        self.cross_section_window.raise_()
        self.cross_section_window.activateWindow()

    def close_cross_sections(self):
        if self.cross_section_window:
            self.cross_section_window.hide()
            self.cross_section_window.deleteLater()
            self.cross_section_window = None


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _link_cell(text, url):
    return {"text": text, "url": url}


def _nested_text(value, language="et"):
    if not isinstance(value, dict):
        return _display_value(value)
    if language == "en":
        return str(
            value.get("name_en") or value.get("value_en") or value.get("label_en")
            or value.get("name") or value.get("value") or value.get("label") or ""
        )
    return str(
        value.get("name") or value.get("value") or value.get("label")
        or value.get("name_en") or value.get("value_en") or ""
    )


def _sarv_interval_end(row):
    depth = _number(row.get("depth"))
    bottom = row.get("depth_interval")
    return _number(bottom) if bottom not in (None, "") else depth


def _sarv_core_track(row):
    start = row.get("depth_start")
    end = row.get("depth_end")
    if start in (None, "") or end in (None, ""):
        return None
    return {
        "id": row.get("id"),
        "kast_nr": row.get("number"),
        "z_suht_ylemine": _number(start),
        "z_suht_alumine": _number(end),
    }


def _sarv_image_url(filename):
    safe_name = quote(str(filename).strip(), safe="-_.")
    return f"https://files.geocollections.info/{safe_name[:2]}/{safe_name[2:4]}/{safe_name}"


def _sarv_attachment_url(url):
    """Replace the obsolete SARV file host still returned by the public API."""
    text = str(url or "").strip()
    for prefix in (
        "https://files.geoloogia.info/",
        "http://files.geoloogia.info/",
    ):
        if text.startswith(prefix):
            return "https://files.geocollections.info/" + text[len(prefix):]
    return text


def _sarv_track(row, kind):
    if row.get("depth") in (None, ""):
        return None
    identifier = (
        row.get("number") if kind == "sample" else
        row.get("specimen_id") or row.get("specimen_full_number")
    ) or row.get("id")
    return {
        "z_suht_ylemine": _number(row.get("depth")),
        "z_suht_alumine": _sarv_interval_end(row),
        "_url": f"https://geoloogia.info/{kind}/{row.get('id')}",
        "_label": f"SARV {identifier}",
    }


def _sarv_analysis_track(row):
    parent = row.get("sample") or row.get("specimen") or {}
    if not isinstance(parent, dict):
        parent = {}
    raw_depth = parent.get("depth") if parent else row.get("depth")
    if raw_depth in (None, ""):
        return None
    depth = _number(raw_depth)
    raw_bottom = parent.get("depth_interval") if parent else row.get("depth_interval")
    bottom = _number(raw_bottom) if raw_bottom not in (None, "") else depth
    return {
        "z_suht_ylemine": depth,
        "z_suht_alumine": bottom,
        "_url": f"https://geoloogia.info/analysis/{row.get('id')}",
        "_label": f"SARV {row.get('id')}",
    }


def _depth_text(start, end=None):
    if start in (None, ""):
        return ""
    start_number = _number(start)
    if end in (None, "") or abs(_number(end) - start_number) < 1e-9:
        return f"{start_number:g} m"
    return f"{start_number:g}–{_number(end):g} m"


def _egt_depth_text(row):
    start = next((
        row.get(key) for key in (
            "z_suht_ylemine", "sygavus", "proov_sygavus", "depth",
        ) if row.get(key) not in (None, "")
    ), None)
    end = next((
        row.get(key) for key in (
            "z_suht_alumine", "sygavus_alumine", "depth_interval",
        ) if row.get(key) not in (None, "")
    ), None)
    return _depth_text(start, end)


def _sarv_analysis_depth_text(row):
    parent = row.get("sample") or row.get("specimen") or {}
    if not isinstance(parent, dict):
        parent = {}
    start = parent.get("depth") if parent else row.get("depth")
    end = parent.get("depth_interval") if parent else row.get("depth_interval")
    return _depth_text(start, end)


def _date_value(value):
    if isinstance(value, (int, float)) and value > 1000000000:
        return datetime.fromtimestamp(value / 1000).strftime("%Y-%m-%d")
    return value


def _display_value(value):
    value = _date_value(value)
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _analysis_result(item, fallback="Näitaja", plugin=None):
    indicator = item.get("analyys_naitaja") or fallback
    value = item.get("tulem")
    unit = item.get("yhik") or ""
    prefix = item.get("erimark") or ""
    if plugin:
        indicator = plugin.decode_egt(4, "analyys_naitaja", indicator)
        unit = plugin.decode_egt(4, "yhik", unit)
        prefix = plugin.decode_egt(4, "erimark", prefix)
    result_type = item.get("analyys_tulem_tyyp")
    type_text = (
        plugin.decode_egt(4, "analyys_tulem_tyyp", result_type)
        if plugin and result_type not in (None, "") else ""
    )
    measured = " ".join(
        part for part in (str(prefix).strip(), _display_value(value), str(unit).strip())
        if part
    )
    label = f"{indicator}: {measured}".strip()
    return f"{label} ({type_text})" if type_text else label


def _nice_depth_step(max_depth, draw_height):
    """Choose a readable metre interval for the depth axis."""
    target_marks = max(2, min(24, round(draw_height / 80)))
    raw = max_depth / target_marks
    magnitude = 10 ** floor(log10(max(raw, 0.001)))
    normalized = raw / magnitude
    if normalized <= 1:
        nice = 1
    elif normalized <= 2:
        nice = 2
    elif normalized <= 5:
        nice = 5
    else:
        nice = 10
    return max(0.1, nice * magnitude)


def _interval_gaps(rows, max_depth):
    """Return uncovered depth intervals after merging valid core-box ranges."""
    intervals = []
    for row in rows:
        start = max(0.0, _number(row.get("z_suht_ylemine")))
        end = min(max_depth, _number(row.get("z_suht_alumine")))
        if end > start:
            intervals.append((start, end))
    intervals.sort()
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    gaps = []
    cursor = 0.0
    for start, end in merged:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < max_depth:
        gaps.append((cursor, max_depth))
    return gaps


def _stratigraphic_color(unit):
    """Match unit indices to the official EGT 2023 stratigraphic scheme."""
    index = _unit_index(unit).replace(" ", "")
    upper = index.upper()
    first = upper.split("-", 1)[0]
    mappings = (
        (("Q2",), "#fff2cc"),
        (("Q1",), "#fff2ae"),
        (("Q",), "#fcfc8b"),
        (("D3",), "#f1e19d"),
        (("D2-3", "D2–3"), "#f1d583"),
        (("D2",), "#f1c868"),
        (("D1-2", "D1–2"), "#ebba5b"),
        (("D1",), "#e5ac4d"),
        (("D",), "#cb8c37"),
        (("S4",), "#e6f5e1"),
        (("S3-4", "S3–4"), "#d3eed8"),
        (("S3",), "#bfe6cf"),
        (("S2-3", "S2–3"), "#b3e1c2"),
        (("S2",), "#a6dcbb"),
        (("S1-2", "S1–2"), "#99d7b3"),
        (("S1",), "#8cd1a3"),
        (("S",), "#b3e1b6"),
        (("O3",), "#7fca93"),
        (("O2",), "#4db47e"),
        (("O1-2", "O1–2"), "#34a977"),
        (("O1",), "#1a9d6f"),
        (("O",), "#009270"),
        (("CM4",), "#b3e095"),
        (("CM3",), "#a6cf86"),
        (("CM2",), "#99c078"),
        (("CM1",), "#8cb06c"),
        (("CM",), "#7fa056"),
        (("E",), "#ffdc88"),
        (("MP",), "#fac180"),
        (("PP",), "#ec607e"),
    )
    for prefixes, color in mappings:
        if any(first.startswith(prefix) for prefix in prefixes):
            return QColor(color)
    category = int(_number(unit.get("klassif_yksus_kood") or unit.get("yksus_kood")))
    fallback = {1: "#fcfc8b", 2: "#a7a7a7", 3: "#ec607e", 997: "#a7a7a7"}
    return QColor(fallback.get(category, "#a7a7a7"))


def _unit_index(unit):
    index = unit.get("indeks") or unit.get("indeks_orig") or ""
    if str(index).strip().casefold() != "liitüksus":
        return str(index)
    # EGT stores the desired stratigraphic range in lower-to-upper display order.
    lower = _valid_unit_value(unit.get("liityksus_indeks_alumine"))
    upper = _valid_unit_value(unit.get("liityksus_indeks_ylemine"))
    if lower and upper and lower != upper:
        return f"{lower}-{upper}"
    return lower or upper or str(index)


def _valid_unit_value(value):
    text = str(value or "").strip()
    return "" if text.casefold() in {"", "ei kohaldu", "teadmata"} else text


def _attachment_url(link):
    text = str(link or "")
    if text.startswith(("http://", "https://")):
        return text
    return f"https://gis.egt.ee/auk/proxy/{quote(text, safe='/')}"


def _is_image_attachment(attachment):
    if attachment.get("manus_tyyp") == 11:
        return True
    link = str(attachment.get("link") or "").lower()
    return link.endswith((".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"))
