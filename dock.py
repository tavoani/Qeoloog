"""Configuration, filtering and EGT detail dock widgets."""

from datetime import datetime
from html import escape as html_escape
from html import unescape as html_unescape
import json
from math import floor, log10
from pathlib import Path
import re
from urllib.parse import quote

from qgis.PyQt.QtCore import QDate, QSize, Qt, QUrl, pyqtSignal
from qgis.PyQt.QtGui import (
    QBrush, QColor, QDesktopServices, QKeySequence, QPainter, QPen, QShortcut,
)
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDateEdit,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QGridLayout,
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
from qgis.core import QgsCoordinateReferenceSystem
from qgis.core import QgsSettings
from qgis.gui import QgsProjectionSelectionWidget

from .corrections import (
    core_correction_key, core_intervals_overlap, core_values,
)
from .detail_view import (
    DETAIL_COLUMNS_SETTINGS, cell_text, default_detail_columns,
    detail_column_candidates, detail_column_preferences, project_detail_columns,
    table_to_tsv, tables_to_tsv,
)
from .archive_reports import report_number
from .faktika import (
    OBJECT_TYPES, UNIT_TYPES, coded_value_label, new_guid, subtype_label,
)
from .i18n import field_label
from .local_object_detail import LocalObjectDetailMixin
from .local_object_sources import local_cross_section
from .local_objects_ui import LocalObjectsWidget
from .etl_widgets import EtlImportWidget
from .models import (
    EGT_LABEL_FIELD_KEYS,
    GROUPS,
    LayerDefinition,
    MAP_LABEL_KEYS_BY_ROLE,
    normalize_map_label_fields,
)
from .observations import observation_index
from .portal import (
    ARCGIS_FEATURE_PROTOCOL,
    ARCGIS_MAP_PROTOCOL,
    feature_layer_id,
    is_arcgis_feature_protocol,
    is_arcgis_map_protocol,
    map_layer_id,
)
from .stratigraphy import STRATIGRAPHIC_INDICES
from .cross_section_widget import CrossSectionLauncher, CrossSectionWindow
from .section_workspace_ui import section_source_ref
from .export_widget import ExportWidget
from .fieldwork import compatible_device_options
from .ui_utils import guard_closed_combo_wheels


DETAIL_RECORD_ROLE = int(Qt.ItemDataRole.UserRole) + 37


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


class EgtPortalSetupDialog(QDialog):
    """Minimal first-run setup; Qeoloog fills every non-secret OAuth field."""

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.setWindowTitle(plugin.t("EGT Portaliga ühendamine"))
        self.setModal(True)
        layout = QVBoxLayout(self)
        note = QLabel(plugin.t(
            "Sisesta üks kord EGT sisejuhendis näidatud Client ID ja Client "
            "secret. Kõik muud OAuthi seaded täidab Qeoloog automaatselt ning "
            "väärtused salvestatakse QGIS-i krüpteeritud autentimishoidlasse."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.client_id = QLineEdit()
        self.client_id.setPlaceholderText("Client ID")
        self.client_secret = QLineEdit()
        self.client_secret.setPlaceholderText("Client secret")
        self.client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Client ID", self.client_id)
        form.addRow("Client secret", self.client_secret)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(
            QDialogButtonBox.StandardButton.Save
        ).setText(plugin.t("Loo ühendus ja logi sisse"))
        self.buttons.accepted.connect(self._accept_if_complete)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _accept_if_complete(self):
        if not self.client_id.text().strip() or not self.client_secret.text().strip():
            QMessageBox.warning(
                self, "Qeoloog",
                self.plugin.t("Client ID and Client secret are required."),
            )
            return
        self.accept()

    def credentials(self):
        return self.client_id.text().strip(), self.client_secret.text().strip()


class GeophysicsFieldworkDialog(QDialog):
    """Collect validated attributes for one multipart fieldwork line."""

    def __init__(
        self, plugin, path, point_count, domains, account="", parent=None,
    ):
        super().__init__(parent)
        self.plugin = plugin
        self.domains = domains
        self.setWindowTitle(plugin.t("Geofüüsika välitööd"))
        self.setModal(True)
        layout = QVBoxLayout(self)
        note = QLabel(plugin.t(
            "CSV punktid ühendatakse failis olevas järjekorras üheks "
            "multipart-jooneks. Joon katkeb, kui järjestikuste punktide "
            "vahe on üle 50 m."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)

        summary = QLabel(
            f"{Path(path).name} — {point_count} " + plugin.t("punkti")
        )
        summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(summary)

        form = QFormLayout()
        self.name = QLineEdit()
        default_name = Path(path).stem
        if default_name.casefold().endswith("_collar"):
            default_name = default_name[:-7]
        self.name.setText(default_name)
        self.name.setMaxLength(255)
        form.addRow(plugin.t("Nimi"), self.name)

        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        form.addRow(plugin.t("Aeg"), self.date)

        self.method = QComboBox()
        self.method.addItem(plugin.t("Vali…"), None)
        for code, label in domains.get("method", []):
            self.method.addItem(label, code)
        self.method.currentIndexChanged.connect(self._refresh_devices)
        form.addRow(plugin.t("Meetod"), self.method)

        self.device = QComboBox()
        form.addRow(plugin.t("Seade"), self.device)

        self.responsible = QComboBox()
        self.responsible.addItem(plugin.t("Vali…"), None)
        for code, label in domains.get("responsible", []):
            self.responsible.addItem(label, code)
        account_name = str(account or "").split("(", 1)[0].strip().casefold()
        if account_name:
            for index in range(1, self.responsible.count()):
                if self.responsible.itemText(index).casefold() == account_name:
                    self.responsible.setCurrentIndex(index)
                    break
        form.addRow(plugin.t("Vastutaja"), self.responsible)

        self.notes = QLineEdit()
        self.notes.setMaxLength(255)
        form.addRow(plugin.t("Märkus"), self.notes)

        self.crs = QgsProjectionSelectionWidget()
        self.crs.setCrs(QgsCoordinateReferenceSystem("EPSG:3301"))
        form.addRow(plugin.t("CSV koordinaatsüsteem"), self.crs)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(
            QDialogButtonBox.StandardButton.Save
        ).setText(plugin.t("Laadi Portalisse"))
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._refresh_devices()

    def _refresh_devices(self, *args):
        selected = self.device.currentData() if self.device.count() else None
        options = compatible_device_options(
            self.method.currentData(),
            self.domains.get("method", []),
            self.domains.get("device", []),
        )
        self.device.blockSignals(True)
        self.device.clear()
        self.device.addItem(self.plugin.t("Vali…"), None)
        for code, label in options:
            self.device.addItem(label, code)
        index = self.device.findData(selected)
        self.device.setCurrentIndex(index if index >= 0 else 0)
        self.device.blockSignals(False)

    def _validate_and_accept(self):
        missing = []
        if not self.name.text().strip():
            missing.append(self.plugin.t("Nimi"))
        if self.method.currentData() is None:
            missing.append(self.plugin.t("Meetod"))
        if self.device.currentData() is None:
            missing.append(self.plugin.t("Seade"))
        if self.responsible.currentData() is None:
            missing.append(self.plugin.t("Vastutaja"))
        if not self.crs.crs().isValid():
            missing.append(self.plugin.t("CSV koordinaatsüsteem"))
        if missing:
            QMessageBox.warning(
                self, "Qeoloog",
                self.plugin.t("Täida kohustuslikud väljad") + ": "
                + ", ".join(missing),
            )
            return
        self.accept()

    def values(self):
        return {
            "name": self.name.text().strip(),
            "date": self.date.date(),
            "method": self.method.currentData(),
            "device": self.device.currentData(),
            "responsible": self.responsible.currentData(),
            "notes": self.notes.text().strip(),
            "crs": self.crs.crs(),
        }


class CoreCorrectionDialog(QDialog):
    """Edit one drill-core box using standardized local fields."""

    def __init__(
        self, plugin, source, record_id, values, is_new=False,
        status_options=None, parent=None,
    ):
        super().__init__(parent)
        self.plugin = plugin
        self.setWindowTitle(
            plugin.t("Lisa puursüdamiku kast") if is_new
            else plugin.t("Muuda puursüdamiku kasti")
        )
        layout = QVBoxLayout(self)
        note = QLabel(plugin.t(
            "Kohalik kast salvestatakse ainult sellesse arvutisse; EGT ega "
            "SARV algandmeid ei muudeta."
            if is_new else
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
            ("description", "Kirjeldus"),
        ):
            value = (values or {}).get(key)
            if key == "status" and status_options is not None:
                edit = QComboBox()
                edit.addItem("", None)
                for code, option_label in status_options:
                    edit.addItem(str(option_label), str(code))
                current = "" if value in (None, "") else str(value)
                index = edit.findData(current)
                if index < 0 and current:
                    # Preserve an upstream value which disappeared between
                    # reads, but never silently replace it with another code.
                    edit.addItem(current, current)
                    index = edit.count() - 1
                edit.setCurrentIndex(max(0, index))
            else:
                edit = QLineEdit()
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
            if isinstance(edit, QComboBox):
                value = edit.currentData()
                values[key] = None if value in (None, "") else value
                continue
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
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.scroll_area.setWidget(content)
        outer_layout.addWidget(self.scroll_area)

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

        portal = QGroupBox(t("EGT Portal"))
        portal_layout = QVBoxLayout(portal)
        portal_note = QLabel(t(
            "Ühenda EGT Portaliga ühe nupuvajutusega. Esimesel korral küsib "
            "Qeoloog ainult sisejuhendis olevaid Client ID ja Client secret "
            "väärtusi; edaspidi kasutatakse QGIS-i turvalist autentimishoidlat."
        ))
        portal_note.setWordWrap(True)
        portal_layout.addWidget(portal_note)
        connect_button = QPushButton(t("Ühenda EGT Portaliga"))
        connect_button.clicked.connect(self._connect_egt_portal)
        portal_layout.addWidget(connect_button)
        self.portal_status = QLabel(t("EGT Portali ühendust pole kontrollitud."))
        self.portal_status.setWordWrap(True)
        portal_layout.addWidget(self.portal_status)

        self.portal_advanced_toggle = QToolButton()
        self.portal_advanced_toggle.setText(t("Täpsemad sätted"))
        self.portal_advanced_toggle.setCheckable(True)
        self.portal_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.portal_advanced_toggle.toggled.connect(
            self._toggle_portal_advanced
        )
        portal_layout.addWidget(self.portal_advanced_toggle)
        self.portal_advanced = QWidget()
        portal_advanced_layout = QVBoxLayout(self.portal_advanced)
        portal_advanced_layout.setContentsMargins(0, 0, 0, 0)
        auth_row = QHBoxLayout()
        self.portal_auth = QComboBox()
        self.portal_auth.currentIndexChanged.connect(
            self._portal_auth_changed
        )
        auth_row.addWidget(self.portal_auth, 1)
        refresh_auth = QPushButton(t("Värskenda"))
        refresh_auth.clicked.connect(self.refresh_portal_auth_configs)
        auth_row.addWidget(refresh_auth)
        portal_advanced_layout.addLayout(auth_row)
        portal_buttons = QHBoxLayout()
        new_login = QPushButton(t("Seadista uus ühendus…"))
        new_login.clicked.connect(self._setup_new_egt_portal)
        portal_buttons.addWidget(new_login)
        auth_settings = QPushButton(t("Ava QGIS-i autentimisseaded…"))
        auth_settings.clicked.connect(
            lambda: getattr(
                self.plugin, "open_authentication_settings", lambda: None
            )()
        )
        portal_buttons.addWidget(auth_settings)
        portal_advanced_layout.addLayout(portal_buttons)
        self.portal_test_server = QCheckBox(t(
            "Kuva Faktika testserver EGT menüüs"
        ))
        self.portal_test_server.setChecked(bool(getattr(
            self.plugin, "egt_test_server_enabled", False
        )))
        self.portal_test_server.setToolTip(t(
            "Testserver on tootmisandmetest eraldatud ja ilmub EGT menüüsse "
            "ainult selle valiku sisselülitamisel."
        ))
        self.portal_test_server.toggled.connect(
            lambda checked: getattr(
                self.plugin, "set_egt_test_server_enabled", lambda _value: None
            )(checked)
        )
        portal_advanced_layout.addWidget(self.portal_test_server)
        self.portal_advanced.setVisible(False)
        portal_layout.addWidget(self.portal_advanced)
        layout.addWidget(portal)

        self.portal_edit_group = QGroupBox(t("Aktiivse Portali kihi redigeerimine"))
        portal_edit_layout = QVBoxLayout(self.portal_edit_group)
        self.portal_edit_status = QLabel()
        self.portal_edit_status.setWordWrap(True)
        portal_edit_layout.addWidget(self.portal_edit_status)
        self.portal_edit_buttons = QWidget()
        edit_buttons_layout = QHBoxLayout(self.portal_edit_buttons)
        edit_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.portal_edit_start = QPushButton(t("Alusta redigeerimist"))
        self.portal_edit_start.clicked.connect(lambda: getattr(
            self.plugin, "start_portal_editing", lambda: None
        )())
        self.portal_edit_save = QPushButton(t("Salvesta Portalisse"))
        self.portal_edit_save.clicked.connect(lambda: getattr(
            self.plugin, "save_portal_edits", lambda: None
        )())
        self.portal_edit_discard = QPushButton(t("Loobu muudatustest"))
        self.portal_edit_discard.clicked.connect(lambda: getattr(
            self.plugin, "discard_portal_edits", lambda: None
        )())
        for button in (
            self.portal_edit_start, self.portal_edit_save,
            self.portal_edit_discard,
        ):
            edit_buttons_layout.addWidget(button)
        portal_edit_layout.addWidget(self.portal_edit_buttons)
        self.portal_fieldwork = QWidget()
        fieldwork_layout = QVBoxLayout(self.portal_fieldwork)
        fieldwork_layout.setContentsMargins(0, 6, 0, 0)
        fieldwork_title = QLabel(t("Välitööde import"))
        fieldwork_title.setStyleSheet("font-weight: 600;")
        fieldwork_layout.addWidget(fieldwork_title)
        self.geophysics_fieldwork = QPushButton(t("Geofüüsika välitööd"))
        self.geophysics_fieldwork.clicked.connect(lambda: getattr(
            self.plugin, "import_geophysics_fieldwork", lambda: None
        )())
        fieldwork_layout.addWidget(self.geophysics_fieldwork)
        self.portal_fieldwork.setVisible(False)
        portal_edit_layout.addWidget(self.portal_fieldwork)
        self.portal_edit_group.setVisible(False)
        layout.addWidget(self.portal_edit_group)

        labels = QGroupBox(t("Kaardisildid"))
        labels_layout = QFormLayout(labels)
        self.label_text_size = QDoubleSpinBox()
        self.label_text_size.setRange(1.0, 72.0)
        self.label_text_size.setDecimals(1)
        self.label_text_size.setSingleStep(0.5)
        self.label_text_size.setSuffix(" pt")
        self.label_text_size.setValue(self.plugin.label_text_size)
        self.label_text_size.valueChanged.connect(
            self.plugin.set_label_text_size
        )
        labels_layout.addRow(t("Punktikihtide teksti suurus"), self.label_text_size)
        field_labels = {
            "name": "Nimi",
            "alias": "Alias",
            "borehole_depth": "Sügavus",
            "cover_thickness": "Pinnakatte paksus",
            "bedrock_elevation": "Aluspõhja reljeefi absoluutkõrgus",
            "depth_0_5": "Indeks 0,5 m sügavusel (koos litoloogiaga)",
            "bedrock_outcrop": "AP avamus (esimene aluspõhja indeks)",
            "kkr_kood": "VEKA registrikood",
            "number": "SARV number",
        }
        configured = normalize_map_label_fields(getattr(
            self.plugin, "egt_label_fields", None,
        ))
        self.egt_label_field_checks = {}

        def label_grid(title, columns, keys):
            group = QGroupBox(t(title))
            grid = QGridLayout(group)
            grid.setColumnStretch(0, 1)
            for index, (_role, source_title) in enumerate(columns, 1):
                source = QLabel(t(source_title))
                source.setWordWrap(True)
                grid.addWidget(source, 0, index, Qt.AlignmentFlag.AlignCenter)
            for row, key in enumerate(keys, 1):
                text = t(field_labels[key])
                caption = QLabel(text)
                caption.setWordWrap(True)
                grid.addWidget(caption, row, 0)
                for index, (role, source_title) in enumerate(columns, 1):
                    if key not in MAP_LABEL_KEYS_BY_ROLE[role]:
                        continue
                    checkbox = QCheckBox()
                    checkbox.setObjectName(f"qeoloogLabel_{role}_{key}")
                    checkbox.setAccessibleName(f"{t(source_title)}: {text}")
                    checkbox.setChecked(key in configured[role])
                    checkbox.toggled.connect(self._egt_label_fields_changed)
                    self.egt_label_field_checks[(role, key)] = checkbox
                    grid.addWidget(checkbox, row, index, Qt.AlignmentFlag.AlignCenter)
            return group

        labels_layout.addRow(label_grid(
            "EGT sildi sisu",
            (("boreholes", "Puuraugud (PA)"), ("observations", "Vaatluspunktid (VP)")),
            EGT_LABEL_FIELD_KEYS,
        ))
        labels_layout.addRow(label_grid(
            "VEKA ja SARV sildi sisu",
            (("veka_boreholes", "VEKA"), ("sarv", "SARV")),
            ("name", "borehole_depth", "kkr_kood", "number"),
        ))
        labels_note = QLabel(t(
            "Vali kuvatavad sildiread iga andmeallika jaoks eraldi. "
            "Puuduva väärtusega ridu ei kuvata."
        ))
        labels_note.setWordWrap(True)
        labels_layout.addRow(labels_note)
        layout.addWidget(labels)

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

        maaru_source = QGroupBox(t("MaRu puursüdamike andmekogu"))
        maaru_source_layout = QVBoxLayout(maaru_source)
        self.maaru_status = QLabel(t(
            "Kohalikku MaRu otsinguindeksit pole veel laaditud."
        ))
        self.maaru_status.setWordWrap(True)
        maaru_source_layout.addWidget(self.maaru_status)
        refresh_maaru = QPushButton(t("Laadi / uuenda MaRu andmekogu"))
        refresh_maaru.clicked.connect(
            lambda: getattr(
                self.plugin, "refresh_maaru_database", lambda: None
            )()
        )
        maaru_source_layout.addWidget(refresh_maaru)
        layout.addWidget(maaru_source)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        catalog_search = QGroupBox(t("Kihikataloog"))
        catalog_search_layout = QGridLayout(catalog_search)
        self.catalog_query = QLineEdit()
        self.catalog_query.setPlaceholderText(t(
            "Otsi koodi, nime, teenuse või URL-i järgi"
        ))
        self.catalog_protocol = QComboBox()
        self.catalog_protocol.addItem(t("Kõik teenused"), "")
        for title, value in (
            ("WMS", "WMS"), ("WFS", "WFS"),
            ("ArcGIS FeatureServer", ARCGIS_FEATURE_PROTOCOL),
            ("ArcGIS MapServer", ARCGIS_MAP_PROTOCOL),
            ("SARV", "SARV"), ("VEKA", "VEKA"), ("MaRu", "MAARU"),
        ):
            self.catalog_protocol.addItem(title, value)
        self.catalog_group = QComboBox()
        self.catalog_group.addItem(t("Kõik rühmad"), "")
        for group in GROUPS:
            self.catalog_group.addItem(self.plugin.group_name(group), group)
        self.catalog_status = QComboBox()
        self.catalog_status.addItem(t("Kõik olekud"), "")
        self.catalog_status.addItem(t("Lubatud"), "enabled")
        self.catalog_status.addItem(t("Keelatud"), "disabled")
        catalog_search_layout.addWidget(self.catalog_query, 0, 0, 1, 3)
        catalog_search_layout.addWidget(self.catalog_protocol, 1, 0)
        catalog_search_layout.addWidget(self.catalog_group, 1, 1)
        catalog_search_layout.addWidget(self.catalog_status, 1, 2)
        self.catalog_query.textChanged.connect(lambda: self.reload_list())
        self.catalog_protocol.currentIndexChanged.connect(
            lambda: self.reload_list()
        )
        self.catalog_group.currentIndexChanged.connect(
            lambda: self.reload_list()
        )
        self.catalog_status.currentIndexChanged.connect(
            lambda: self.reload_list()
        )
        top_layout.addWidget(catalog_search)
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
        for title, value in (
            ("WMS", "WMS"),
            ("WFS", "WFS"),
            ("ArcGIS FeatureServer", ARCGIS_FEATURE_PROTOCOL),
            ("ArcGIS MapServer", ARCGIS_MAP_PROTOCOL),
            ("SARV", "SARV"),
            ("VEKA", "VEKA"),
            ("MaRu", "MAARU"),
        ):
            self.protocol.addItem(title, value)
        self.protocol.currentIndexChanged.connect(self._protocol_changed)
        self.code = QLineEdit()
        self.code.setMaxLength(4)
        self.name = QLineEdit()
        self.name_en = QLineEdit()
        self.url = QLineEdit()
        self.layer_name = QComboBox()
        self.layer_name.setEditable(True)
        self.style = QLineEdit()
        self.service_crs = QLineEdit("EPSG:3301")
        self.menu_group = QLineEdit()
        self.use_portal_auth = QCheckBox(t("Kasuta valitud EGT Portali autentimist"))
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
        form.addRow(t("Teenuse CRS"), self.service_crs)
        form.addRow(t("Autentimine"), self.use_portal_auth)
        form.addRow(t("WMS stiil"), self.style)
        form.addRow(t("Ikooni värv"), color_row)
        form.addRow(t("Kodu"), self.home_group)
        form.addRow(t("Alammenüü"), self.menu_group)
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
        export_button = QPushButton(t("Ekspordi SARV ja MaRu seosed…"))
        export_button.clicked.connect(self._export_sarv_matches)
        form_host_layout.addWidget(export_button)
        splitter.addWidget(form_host)
        splitter.setSizes([220, 360])
        self.refresh_portal_auth_configs()
        self._protocol_changed()
        iface = getattr(self.plugin, "iface", None)
        self.update_portal_edit_state(
            iface.activeLayer() if iface and hasattr(iface, "activeLayer") else None
        )
        database = getattr(self.plugin, "_maaru_db", None)
        if database is not None and getattr(database, "available", False):
            try:
                self.set_maaru_status(database.metadata())
            except Exception:
                pass

    def refresh_portal_auth_configs(self):
        current = getattr(self.plugin, "egt_portal_authcfg", "")
        self.portal_auth.blockSignals(True)
        self.portal_auth.clear()
        self.portal_auth.addItem(
            self.plugin.t("Autentimiseta (avalik kiht)"), ""
        )
        configs = getattr(self.plugin, "portal_auth_configs", lambda: [])()
        for authcfg, name, method in configs:
            self.portal_auth.addItem(f"{name} ({method})", authcfg)
        index = self.portal_auth.findData(current)
        if current and index < 0:
            self.portal_auth.addItem(
                self.plugin.t("Puuduv autentimiskonfiguratsioon")
                + f" ({current})",
                current,
            )
            index = self.portal_auth.count() - 1
        self.portal_auth.setCurrentIndex(max(0, index))
        self.portal_auth.blockSignals(False)

    def _toggle_portal_advanced(self, visible):
        self.portal_advanced.setVisible(bool(visible))
        self.portal_advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
        )

    def _connect_egt_portal(self):
        preferred = getattr(
            self.plugin, "preferred_egt_portal_authcfg", lambda: ""
        )()
        if not preferred:
            preferred = self._setup_new_egt_portal(login=False)
        if not preferred:
            return
        setter = getattr(self.plugin, "set_egt_portal_authcfg", None)
        if setter:
            setter(preferred)
        self.refresh_portal_auth_configs()
        index = self.portal_auth.findData(preferred)
        if index >= 0:
            self.portal_auth.setCurrentIndex(index)
        if is_arcgis_feature_protocol(self._protocol_value()):
            self.use_portal_auth.setChecked(True)
        getattr(self.plugin, "test_egt_portal_login", lambda: None)()

    def _setup_new_egt_portal(self, *args, login=True):
        dialog = EgtPortalSetupDialog(self.plugin, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return ""
        creator = getattr(
            self.plugin, "create_egt_portal_authentication", lambda *values: ""
        )
        authcfg = creator(*dialog.credentials())
        # Remove the secret from the widget as soon as QGIS has accepted it.
        dialog.client_secret.clear()
        if not authcfg:
            return ""
        self.refresh_portal_auth_configs()
        index = self.portal_auth.findData(authcfg)
        if index >= 0:
            self.portal_auth.setCurrentIndex(index)
        if is_arcgis_feature_protocol(self._protocol_value()):
            self.use_portal_auth.setChecked(True)
        if login:
            getattr(self.plugin, "test_egt_portal_login", lambda: None)()
        return authcfg

    def _portal_auth_changed(self):
        setter = getattr(self.plugin, "set_egt_portal_authcfg", None)
        if setter:
            setter(self.portal_auth.currentData() or "")
        self.set_portal_status(
            self.plugin.t("EGT Portali ühendust pole kontrollitud."),
            success=False,
        )

    def set_portal_status(self, text, success=False):
        self.portal_status.setText(str(text))
        self.portal_status.setStyleSheet(
            "color: #2f8f55;" if success else ""
        )
        self.update_portal_edit_state(
            self.plugin.iface.activeLayer()
            if getattr(self.plugin, "iface", None) else None
        )

    def set_maaru_status(self, metadata=None, error=""):
        if error:
            self.maaru_status.setText(
                self.plugin.t("MaRu andmekogu laadimine ebaõnnestus")
                + f": {error}"
            )
            return
        metadata = metadata or {}
        count = metadata.get("record_count")
        year = metadata.get("source_year")
        imported = str(metadata.get("imported_at") or "").replace("T", " ")[:19]
        if count:
            parts = [f"{count} {self.plugin.t('puursüdamikku')}"]
            if year:
                parts.append(f"{self.plugin.t('allikas')} {year}")
            if imported:
                parts.append(f"{self.plugin.t('uuendatud')} {imported}")
            self.maaru_status.setText(" · ".join(parts))
        else:
            self.maaru_status.setText(self.plugin.t(
                "Kohalikku MaRu otsinguindeksit pole veel laaditud."
            ))

    def update_portal_edit_state(self, layer=None):
        if not bool(getattr(self.plugin, "portal_editing_enabled", False)):
            self.portal_edit_group.setVisible(False)
            self.portal_fieldwork.setVisible(False)
            self.portal_edit_buttons.setVisible(False)
            return
        is_portal = getattr(
            self.plugin, "is_portal_feature_layer", lambda candidate: False
        )
        signed_in = bool(getattr(
            self.plugin, "egt_portal_catalog_account", ""
        ))
        portal_layer = bool(is_portal(layer))
        self.portal_edit_group.setVisible(signed_in or portal_layer)
        self.portal_fieldwork.setVisible(signed_in)
        self.portal_edit_status.setVisible(portal_layer)
        if not portal_layer:
            self.portal_edit_buttons.setVisible(False)
            return
        operations = getattr(
            self.plugin, "portal_edit_operations", lambda candidate: []
        )(layer)
        editing = bool(layer.isEditable())
        labels = {
            "add": self.plugin.t("lisamine"),
            "update": self.plugin.t("muutmine"),
            "delete": self.plugin.t("kustutamine"),
        }
        if operations:
            self.portal_edit_status.setText(
                self.plugin.t("Lubatud toimingud") + ": "
                + ", ".join(labels[item] for item in operations)
            )
        else:
            self.portal_edit_status.setText(self.plugin.t(
                "Kiht on selle Portali kasutaja jaoks kirjutuskaitstud."
            ))
        # A read-only user's interface contains no inactive editing controls.
        self.portal_edit_buttons.setVisible(bool(operations))
        self.portal_edit_start.setEnabled(bool(operations) and not editing)
        self.portal_edit_save.setEnabled(editing)
        self.portal_edit_discard.setEnabled(editing)

    def _protocol_value(self):
        return self.protocol.currentData() or self.protocol.currentText().upper()

    def _set_protocol(self, value):
        normalized = str(value or "").upper()
        if is_arcgis_feature_protocol(value):
            normalized = ARCGIS_FEATURE_PROTOCOL
        elif is_arcgis_map_protocol(value):
            normalized = ARCGIS_MAP_PROTOCOL
        index = self.protocol.findData(normalized)
        self.protocol.setCurrentIndex(index if index >= 0 else 0)

    def _protocol_changed(self, *args):
        portal_layer = is_arcgis_feature_protocol(self._protocol_value())
        arcgis_layer = portal_layer or is_arcgis_map_protocol(
            self._protocol_value()
        )
        self.use_portal_auth.setVisible(portal_layer)
        self.style.setEnabled(not arcgis_layer)
        if arcgis_layer:
            self.base_map.setChecked(False)
        if portal_layer:
            if (
                self._editing_index < 0
                and getattr(self.plugin, "egt_portal_authcfg", "")
            ):
                self.use_portal_auth.setChecked(True)
        self.base_map.setEnabled(not arcgis_layer)

    def _egt_label_fields_changed(self, *args):
        values = {
            role: [
                key for key in keys
                if self.egt_label_field_checks[(role, key)].isChecked()
            ]
            for role, keys in MAP_LABEL_KEYS_BY_ROLE.items()
        }
        self.plugin.set_egt_label_fields(values)

    def _export_sarv_matches(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.plugin.t("Ekspordi SARV ja MaRu seosed"),
            "qeoloog_seosed.csv",
            "CSV (*.csv);;JSON (*.json)",
        )
        if path:
            self.plugin.export_sarv_matches(path)

    def _definition_index_for_item(self, item):
        try:
            return int(item.data(Qt.ItemDataRole.UserRole))
        except (AttributeError, TypeError, ValueError):
            return -1

    def reload_list(self, select=None, *args):
        selected_definition = (
            self._editing_index if select is None else select
        )
        query = " ".join(
            self.catalog_query.text().casefold().split()
        ) if hasattr(self, "catalog_query") else ""
        protocol_filter = (
            self.catalog_protocol.currentData() or ""
        ) if hasattr(self, "catalog_protocol") else ""
        group_filter = (
            self.catalog_group.currentData() or ""
        ) if hasattr(self, "catalog_group") else ""
        status_filter = (
            self.catalog_status.currentData() or ""
        ) if hasattr(self, "catalog_status") else ""
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        selected_row = -1
        for definition_index, definition in enumerate(self.plugin.definitions):
            haystack = " ".join((
                definition.code, definition.name, definition.name_en,
                definition.protocol, definition.url, definition.layer_name,
                definition.service_crs, definition.menu_group,
                self.plugin.group_name(definition.home_group),
            )).casefold()
            if query and query not in haystack:
                continue
            if protocol_filter and definition.protocol != protocol_filter:
                continue
            if group_filter and definition.home_group != group_filter:
                continue
            if status_filter == "enabled" and definition.placement == "disabled":
                continue
            if status_filter == "disabled" and definition.placement != "disabled":
                continue
            placement = {
                "toolbar": self.plugin.t("Põhiriba"),
                "dropdown": self.plugin.t("Rippmenüü"),
                "disabled": self.plugin.t("Keelatud"),
            }.get(definition.placement, definition.placement)
            location = self.plugin.group_name(definition.home_group)
            if definition.menu_group:
                location += f" / {self.plugin.t(definition.menu_group)}"
            self.list_widget.addItem(
                f"{definition.code} - {self.plugin.display_name(definition)} "
                f"[{location} / {placement}]"
            )
            item = self.list_widget.item(self.list_widget.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, definition_index)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Unchecked
                if definition.placement == "disabled" else Qt.CheckState.Checked
            )
            if definition_index == selected_definition:
                selected_row = self.list_widget.count() - 1
        self.list_widget.blockSignals(False)
        if selected_row >= 0:
            self.list_widget.setCurrentRow(selected_row)

    def clear_form(self):
        self._editing_index = -1
        self.list_widget.clearSelection()
        self._set_protocol("WMS")
        self.code.clear()
        self.name.clear()
        self.name_en.clear()
        self.url.clear()
        self.layer_name.clear()
        self.style.clear()
        self.service_crs.setText("EPSG:3301")
        self.menu_group.clear()
        self.use_portal_auth.setChecked(False)
        self.color.setText("#356a8a")
        self.base_map.setChecked(False)
        self.home_group.setEnabled(True)
        self.home_group.setCurrentIndex(self.home_group.findData("helpers"))
        self.placement.setCurrentIndex(self.placement.findData("dropdown"))
        self.save_button.setText(self.plugin.t("Lisa"))
        self._protocol_changed()

    def _item_checked(self, item):
        definition_index = self._definition_index_for_item(item)
        if definition_index < 0 or definition_index >= len(self.plugin.definitions):
            return
        definition = self.plugin.definitions[definition_index]
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
        self.reload_list(definition_index)

    def _select_row(self, row):
        item = self.list_widget.item(row)
        definition_index = self._definition_index_for_item(item)
        if definition_index < 0 or definition_index >= len(self.plugin.definitions):
            return
        self._editing_index = definition_index
        definition = self.plugin.definitions[definition_index]
        self._set_protocol(definition.protocol)
        self.code.setText(definition.code)
        self.name.setText(definition.name)
        self.name_en.setText(definition.name_en)
        self.url.setText(definition.url)
        self.layer_name.setEditText(definition.layer_name)
        self.style.setText(definition.style)
        self.service_crs.setText(definition.service_crs)
        self.menu_group.setText(definition.menu_group)
        self.use_portal_auth.setChecked(bool(definition.use_portal_auth))
        self.color.setText(definition.color)
        self.base_map.setChecked(definition.base_map)
        self.home_group.setCurrentIndex(self.home_group.findData(definition.home_group))
        self.home_group.setEnabled(False)
        self.placement.setCurrentIndex(self.placement.findData(definition.placement))
        self.save_button.setText(self.plugin.t("Uuenda"))
        self._protocol_changed()

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
        protocol = self._protocol_value()
        if protocol in {"SARV", "VEKA", "MAARU"}:
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
        if is_arcgis_feature_protocol(protocol):
            authcfg = (
                self.plugin.egt_portal_authcfg
                if self.use_portal_auth.isChecked() else ""
            )
            if self.use_portal_auth.isChecked() and not authcfg:
                self.plugin.warning(self.plugin.t(
                    "Vali esmalt juhendi järgi loodud EGT Portali autentimine."
                ))
                return
            self.plugin.network.query_arcgis_feature_layers(
                url, authcfg, self._capabilities_loaded,
                lambda error: self.plugin.error(
                    self.plugin.t("FeatureServeri kihtide lugemine ebaõnnestus")
                    + f": {error}"
                ),
            )
        elif is_arcgis_map_protocol(protocol):
            self.plugin.network.query_arcgis_map_layers(
                url, self._capabilities_loaded,
                lambda error: self.plugin.error(
                    self.plugin.t("MapServeri kihtide lugemine ebaõnnestus")
                    + f": {error}"
                ),
            )
        else:
            self.plugin.network.get_capabilities(
                protocol,
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
        protocol = self._protocol_value()
        code = self.code.text().strip().upper()
        name = self.name.text().strip()
        url = self.url.text().strip()
        layer_name = self.layer_name.currentData() or self.layer_name.currentText().strip()
        if " — " in layer_name and self.layer_name.currentData() is None:
            layer_name = layer_name.rsplit(" — ", 1)[-1]
        if is_arcgis_feature_protocol(protocol) and not layer_name:
            try:
                layer_name = feature_layer_id(url)
            except ValueError:
                pass
        if is_arcgis_map_protocol(protocol) and not layer_name:
            try:
                layer_name = map_layer_id(url)
            except ValueError:
                pass
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
        elif protocol == "MAARU":
            role = "maaru_cores"
        elif lower_name.endswith(":puurauk") or lower_name == "puurauk":
            role = "boreholes"
        elif lower_name.endswith(":vaatluspunkt") or lower_name == "vaatluspunkt":
            role = "observations"
        elif lower_name.endswith(":maardla_piir") or lower_name == "maardla_piir":
            role = "mineral_deposits"
        elif (
            lower_name.endswith(":aktiivne_maeeraldis")
            or lower_name == "aktiivne_maeeraldis"
        ):
            role = "mining_claims"
        elif (
            lower_name.endswith(":aktiivne_uuringuala")
            or lower_name == "aktiivne_uuringuala"
        ):
            role = "exploration_areas"
        elif (
            lower_name.endswith(":wfs_ehitusgeoloogilised_punktid")
            or lower_name == "wfs_ehitusgeoloogilised_punktid"
        ):
            role = "engineering_geology_points"
        elif (
            lower_name.endswith(":wfs_koik_uuringualad")
            or lower_name == "wfs_koik_uuringualad"
        ):
            role = "archive_survey_areas"
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
            use_portal_auth=(
                self.use_portal_auth.isChecked()
                if is_arcgis_feature_protocol(protocol) else False
            ),
            service_crs=self.service_crs.text().strip() or "EPSG:3301",
            menu_group=self.menu_group.text().strip(),
        )
        index = self.plugin.upsert_definition(self._editing_index, definition)
        self.reload_list(index)

    def _remove(self):
        item = self.list_widget.currentItem()
        definition_index = self._definition_index_for_item(item)
        if definition_index >= 0:
            self.plugin.remove_definition(definition_index)
            self.reload_list()
            self.clear_form()

    def _move(self, delta):
        definition_index = self._definition_index_for_item(
            self.list_widget.currentItem()
        )
        target = self.plugin.move_definition(definition_index, delta)
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
        self.show_index_thickness = QCheckBox(
            t("Kuva valitud üksuste koondpaksus")
        )
        self.show_index_thickness.setToolTip(t(
            "Puuraugu nime all kuvatakse kõigi valitud üksuste üks "
            "koondpaksus. Iga intervall arvestatakse üks kord; liitüksuste "
            "intervallide summa kuvatakse sulgudes. Puuraugu põhjani "
            "ulatuva üksuse paksuse järel kuvatakse +."
        ))
        self.show_index_thickness.stateChanged.connect(self._changed)
        index_layout.addRow(t("Indeks"), self.stratigraphic_index)
        index_layout.addRow(t("Sisaldab"), self.stratigraphic_contains)
        index_layout.addRow(self.show_index_thickness)
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
        guard_closed_combo_wheels(self)

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
            self.show_index_thickness.setChecked(False)
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
            "show_thickness": self.show_index_thickness.isChecked(),
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
        guard_closed_combo_wheels(self)

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
        self.usage = MultiSelectButton(t("Kõik"))
        self.groundwater = MultiSelectButton(t("Kõik"))
        self.purpose.selectionChanged.connect(self._changed)
        self.usage.selectionChanged.connect(self._changed)
        self.groundwater.selectionChanged.connect(self._changed)
        form.addRow(t("Otstarve"), self.purpose)
        form.addRow(t("Kasutus"), self.usage)
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
        guard_closed_combo_wheels(self)

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
            "usages": self.usage.selected_values(),
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

    def set_main_options(self, purposes, groundwater, usages=()):
        self.purpose.set_options(purposes)
        self.usage.set_options(usages)
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
            self.usage.clear_selection()
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


class MaaruFilterWidget(QWidget):
    """Source-specific fields for the local MaRu search index."""

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        t = plugin.t
        layout = QVBoxLayout(self)

        identifiers = QGroupBox(t("MaRu tunnused"))
        identifier_form = QFormLayout(identifiers)
        self.maaru_id = QLineEdit()
        self.gb_id = QLineEdit()
        self.fund = QLineEdit()
        identifier_form.addRow(t("MaRu ID"), self.maaru_id)
        identifier_form.addRow(t("GB ID"), self.gb_id)
        identifier_form.addRow(t("Fond"), self.fund)
        layout.addWidget(identifiers)

        samples = QGroupBox(t("MaRu proovid"))
        sample_form = QFormLayout(samples)
        self.rock = QLineEdit()
        self.storage = QLineEdit()
        self.box = QLineEdit()
        self.collector = QLineEdit()
        self.sample_location = QLineEdit()
        self.year_min = QLineEdit()
        self.year_max = QLineEdit()
        year_host = QWidget()
        year_layout = QHBoxLayout(year_host)
        year_layout.setContentsMargins(0, 0, 0, 0)
        self.year_min.setPlaceholderText(t("Min"))
        self.year_max.setPlaceholderText(t("Max"))
        year_layout.addWidget(self.year_min)
        year_layout.addWidget(self.year_max)
        sample_form.addRow(t("Kivim"), self.rock)
        sample_form.addRow(t("Hoiukoht"), self.storage)
        sample_form.addRow(t("Kast"), self.box)
        sample_form.addRow(t("Koguja"), self.collector)
        sample_form.addRow(t("Asukohaviit"), self.sample_location)
        sample_form.addRow(t("Kogumise aasta"), year_host)
        layout.addWidget(samples)

        presence = QGroupBox(t("MaRu seotud andmed"))
        presence_form = QFormLayout(presence)
        self.presence = {}
        for key, label in (
            ("egt_link", "EGT seos"),
            ("sarv_link", "SARV seos"),
            ("core_photo", "Kastifoto"),
            ("sample_photo", "Proovifoto"),
            ("thin_section", "Õhik"),
            ("chemistry", "Keemiline analüüs"),
            ("mineralogy", "Mineraloogia"),
            ("granulometry", "Granulomeetria"),
            ("spectral", "Spektraalanalüüs"),
            ("carbonate", "Karbonaatsus"),
        ):
            choice = QComboBox()
            choice.addItem(t("Kõik"), "any")
            choice.addItem(t("Jah"), "yes")
            choice.addItem(t("Ei"), "no")
            self.presence[key] = choice
            presence_form.addRow(t(label), choice)
        layout.addWidget(presence)

        reset_button = QPushButton(t("Lähtesta"))
        reset_button.clicked.connect(self.reset)
        layout.addWidget(reset_button)
        note = QLabel(t(
            "MaRu filtrid rakenduvad Otsingu vaates siis, kui allikaks on "
            "valitud MaRu või kõigi allikate otsing."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        guard_closed_combo_wheels(self)

    def requirements(self):
        return {
            "maaru_id": self.maaru_id.text().strip(),
            "gb_id": self.gb_id.text().strip(),
            "fund": self.fund.text().strip(),
            "rock": self.rock.text().strip(),
            "storage": self.storage.text().strip(),
            "box": self.box.text().strip(),
            "collector": self.collector.text().strip(),
            "sample_location": self.sample_location.text().strip(),
            "year_min": self.year_min.text().strip(),
            "year_max": self.year_max.text().strip(),
            **{
                key: choice.currentData()
                for key, choice in self.presence.items()
            },
        }

    def reset(self):
        for widget in (
            self.maaru_id, self.gb_id, self.fund, self.rock, self.storage,
            self.box, self.collector, self.year_min, self.year_max,
            self.sample_location,
        ):
            widget.clear()
        for choice in self.presence.values():
            choice.setCurrentIndex(0)


class SearchWidget(QWidget):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        t = plugin.t
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.source = QComboBox()
        self.source.addItem(t("EGT, SARV, MaRu ja VEKA"), "all")
        self.source.addItem(t("EGT ja SARV"), "both")
        self.source.addItem("EGT", "egt")
        self.source.addItem("SARV", "sarv")
        self.source.addItem("MaRu", "maaru")
        self.source.addItem("VEKA", "veka")
        self.source.addItem(t("Läti LVĢMC"), "latvia")
        self.source.addItem(t("Maavarade register"), "minerals")
        self.source.addItem(t("Geoloogiafond"), "archive")
        self.source.setCurrentIndex(self.source.findData("egt"))
        form.addRow(t("Allikas"), self.source)
        kind_host = QWidget()
        kind_layout = QGridLayout(kind_host)
        kind_layout.setContentsMargins(0, 0, 0, 0)
        kind_layout.setHorizontalSpacing(10)
        kind_layout.setVerticalSpacing(2)
        self.kinds = {}
        for role, label in (
            ("boreholes", "PA"),
            ("observations", "VP"),
            ("sarv_localities", "SL"),
            ("sarv_sites", "SU"),
            ("sarv_drillcores", "SK"),
            ("maaru_cores", "MP"),
            ("veka_boreholes", "VK"),
            ("latvia_boreholes", "LPU"),
            ("mineral_deposits", "MR"),
            ("mining_claims", "ME"),
            ("exploration_areas", "UA"),
            ("archive_survey_areas", "EGF"),
        ):
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.setToolTip(t({
                "boreholes": "Puuraugud",
                "observations": "Vaatluspunktid",
                "sarv_localities": "Lokaliteedid",
                "sarv_sites": "Uuringupunktid",
                "sarv_drillcores": "Puursüdamikud",
                "maaru_cores": "MaRu puursüdamikud",
                "veka_boreholes": "VEKA puurkaevud",
                "latvia_boreholes": "Läti geoloogilised puuraugud",
                "mineral_deposits": "Maardlad",
                "mining_claims": "Aktiivsed mäeeraldised",
                "exploration_areas": "Aktiivsed uuringualad",
                "archive_survey_areas": "Geoloogiafondi uuringualad",
            }[role]))
            self.kinds[role] = checkbox
            index = len(self.kinds) - 1
            kind_layout.addWidget(checkbox, index // 5, index % 5)
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
        self._point_filter_widgets = (
            depth_host, self.stratigraphic_index, related_host,
            self.sample_type, self.sample_purpose, self.analysis_method,
        )
        layout.addLayout(form)
        self.search_button = QPushButton(t("Otsi"))
        self.search_button.clicked.connect(self.run)
        layout.addWidget(self.search_button)
        filter_actions = QWidget()
        filter_actions_layout = QHBoxLayout(filter_actions)
        filter_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.apply_filter_button = QPushButton(t("Rakenda filtrina"))
        self.apply_filter_button.clicked.connect(self.apply_as_filter)
        self.apply_section_button = QPushButton(t("Rakenda läbilõikele"))
        self.apply_section_button.setToolTip(t(
            "Lisa tulemuste tabelis valitud puuraugud või puurkaevud "
            "koondläbilõikele."
        ))
        self.apply_section_button.clicked.connect(self.apply_to_cross_section)
        self.reset_button = QPushButton(t("Lähtesta"))
        self.reset_button.clicked.connect(self.reset)
        filter_actions_layout.addWidget(self.apply_filter_button)
        filter_actions_layout.addWidget(self.apply_section_button)
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
        self.results.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._result_rows = []
        layout.addWidget(self.results)
        self.source.currentIndexChanged.connect(self._source_changed)
        self._source_changed()
        self.reload_domain_options()
        guard_closed_combo_wheels(self)

    def _source_changed(self):
        source = self.source.currentData()
        allowed = {
            "all": {
                "boreholes", "observations", "sarv_localities",
                "sarv_sites", "sarv_drillcores", "veka_boreholes",
                "maaru_cores",
            },
            "both": {
                "boreholes", "observations", "sarv_localities",
                "sarv_sites", "sarv_drillcores",
            },
            "egt": {"boreholes", "observations"},
            "sarv": {"sarv_localities", "sarv_sites", "sarv_drillcores"},
            "maaru": {"maaru_cores"},
            "veka": {"veka_boreholes"},
            "latvia": {"latvia_boreholes"},
            "minerals": {
                "mineral_deposits", "mining_claims", "exploration_areas",
            },
            "archive": {"archive_survey_areas"},
        }.get(source, set())
        for role, checkbox in self.kinds.items():
            checkbox.setEnabled(role in allowed)
        registry_source = source in {"minerals", "archive"}
        simple_source = registry_source or source == "latvia"
        for widget in self._point_filter_widgets:
            widget.setEnabled(not simple_source)
        self.stratigraphic_index.setEnabled(
            source in {"all", "both", "egt", "maaru"}
        )
        source_specific_filters = source in {"all", "both", "egt", "sarv"}
        for widget in (
            self.sample_type, self.sample_purpose, self.analysis_method,
        ):
            widget.setEnabled(source_specific_filters)
        for key, choice in self.related.items():
            choice.setEnabled(
                not registry_source
                and source != "veka"
                and not (source == "maaru" and key == "analyses")
            )
        self.apply_filter_button.setEnabled(not registry_source)
        self.apply_section_button.setEnabled(not simple_source)

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
            "sample_type": (
                self.sample_type.selected_values()
                if self.sample_type.isEnabled() else set()
            ),
            "sample_purpose": (
                self.sample_purpose.selected_values()
                if self.sample_purpose.isEnabled() else set()
            ),
            "analysis_method": (
                self.analysis_method.selected_values()
                if self.analysis_method.isEnabled() else set()
            ),
            "related": {
                key: choice.currentData() if choice.isEnabled() else "any"
                for key, choice in self.related.items()
            },
            "maaru_filters": (
                self.plugin.dock.maaru_filters.requirements()
                if self.plugin.dock is not None
                and self.source.currentData() in {"all", "maaru"}
                else {}
            ),
        }

    def run(self):
        self._start_search(False)

    def apply_as_filter(self):
        self._start_search(True)

    def apply_to_cross_section(self):
        selected = sorted({
            index.row() for index in self.results.selectionModel().selectedRows()
        })
        rows = [
            self._result_rows[index] for index in selected
            if 0 <= index < len(self._result_rows)
        ]
        if not rows:
            self.status.setText(self.plugin.t(
                "Vali esmalt tulemuste tabelist vähemalt üks rida."
            ))
            return
        count = self.plugin.add_search_results_to_cross_section(rows)
        self.status.setText(self.plugin.t(
            "Läbilõikele lisati {count} objekti."
        ).format(count=count))

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
        self.source.setCurrentIndex(self.source.findData("egt"))
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
        self._result_rows = []
        self.search_button.setEnabled(True)
        self._source_changed()
        self.plugin.clear_search_filter()

    def set_results(self, rows, message=""):
        self._result_rows = list(rows)
        self.search_button.setEnabled(True)
        self.apply_filter_button.setEnabled(
            self.source.currentData() not in {"minerals", "archive"}
        )
        self.apply_section_button.setEnabled(
            self.source.currentData() not in {"minerals", "archive", "latvia"}
        )
        count = len(self._result_rows)
        self.status.setText(message or f"{count} {self.plugin.t('tulemust')}")
        self.results.setRowCount(count)
        for row_index, row in enumerate(self._result_rows):
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


class SearchAndFiltersWidget(QWidget):
    """One compact home for shared search and source-specific filters."""

    def __init__(self, plugin, search, egt_filters, sarv_filters, maaru_filters):
        super().__init__()
        self.tabs = QTabWidget()
        self.search = search
        self.egt_filters = egt_filters
        self.sarv_filters = sarv_filters
        self.maaru_filters = maaru_filters
        self.tabs.addTab(search, plugin.t("Otsing"))
        self.tabs.addTab(self._scroll(egt_filters), plugin.t("EGT"))
        self.tabs.addTab(self._scroll(sarv_filters), plugin.t("SARV"))
        self.tabs.addTab(self._scroll(maaru_filters), plugin.t("MaRu"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

    @staticmethod
    def _scroll(widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def show_section(self, section):
        index = {"search": 0, "egt": 1, "sarv": 2, "maaru": 3}.get(
            section, 0
        )
        self.tabs.setCurrentIndex(index)


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


class RecordLinksDialog(QDialog):
    """Bounded, searchable alternative to an overflowing native menu."""

    def __init__(self, plugin, entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle(plugin.t("Vali kirje"))
        self.resize(640, 480)
        layout = QVBoxLayout(self)
        search = QLineEdit()
        search.setPlaceholderText(plugin.t("Otsing"))
        layout.addWidget(search)
        self.records = QListWidget()
        for text, url in entries:
            item = QListWidgetItem(text, self.records)
            item.setData(Qt.ItemDataRole.UserRole, url)
            item.setToolTip(url)
        layout.addWidget(self.records, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Close)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.open_current)
        buttons.rejected.connect(self.reject)
        self.records.itemDoubleClicked.connect(lambda item: self.open_current())
        search.textChanged.connect(self.filter_rows)
        if self.records.count():
            self.records.setCurrentRow(0)

    def filter_rows(self, text):
        for index in range(self.records.count()):
            item = self.records.item(index)
            item.setHidden(text.casefold() not in item.text().casefold())

    def open_current(self):
        item = self.records.currentItem()
        if item is not None and not item.isHidden():
            QDesktopServices.openUrl(QUrl(item.data(Qt.ItemDataRole.UserRole)))
            self.accept()


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
        self.observation_mode = False
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

    def set_observation_mode(self, enabled):
        self.observation_mode = bool(enabled)
        self._update_minimum_width()
        self.update()

    def _index_text(self, unit):
        index = _unit_index(unit)
        value = observation_index(unit, index) if self.observation_mode else index
        if value and unit.get("_qeoloog_show_source"):
            return f"{unit.get('_qeoloog_source')} · {value}"
        return value

    def set_core_boxes(self, rows):
        self.core_boxes = list(rows)
        self._update_minimum_height()

    def set_sarv_core_boxes(self, rows):
        self.sarv_core_boxes = list(rows)
        self._update_minimum_height()

    def set_samples(self, rows):
        self.samples = list(rows)
        self._update_minimum_width()
        self._update_minimum_height()

    def set_analyses(self, rows):
        self.analyses = list(rows)
        self._update_minimum_width()
        self._update_minimum_height()

    def set_sarv_samples(self, rows):
        self.sarv_samples = list(rows)
        self._update_minimum_width()
        self._update_minimum_height()

    def set_sarv_analyses(self, rows):
        self.sarv_analyses = list(rows)
        self._update_minimum_width()
        self._update_minimum_height()

    def set_sarv_specimens(self, rows):
        self.sarv_specimens = list(rows)
        self._update_minimum_width()
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
            metrics.horizontalAdvance(self.plugin.t(
                "Indeks / genees" if self.observation_mode else "Indeks"
            )) + 12,
            min(
                220 if self.observation_mode else 140,
                max(
                    (
                        metrics.horizontalAdvance(self._index_text(unit))
                        for unit in self.units
                        if self._index_text(unit)
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
            if not visible or not getattr(self, key):
                continue
            tracks[key] = cursor
            cursor += width + gap

        construction_left = None
        if self.show_veka_construction and self.veka_construction:
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

    def _core_box_tracks(self, bar_left):
        """Return visible source-specific lanes over the lithology column."""
        primary = {"EGT": [], "MARU": []}
        if self.show_core_boxes:
            for box in self.core_boxes:
                source = str(
                    box.get("_qeoloog_source") or "EGT"
                ).strip().upper()
                primary["MARU" if source == "MARU" else "EGT"].append(box)
        sources = []
        if primary["EGT"]:
            sources.append({
                "source": "EGT", "prefix": "K", "boxes": primary["EGT"],
                "images": self.core_images, "id_field": "globalid",
                "color": QColor("#2d2d2d"),
                "style": Qt.PenStyle.DashLine,
            })
        if self.show_sarv_core_boxes and self.sarv_core_boxes:
            sources.append({
                "source": "SARV", "prefix": "S",
                "boxes": self.sarv_core_boxes,
                "images": self.sarv_core_images, "id_field": "id",
                "color": QColor("#176f8a"),
                "style": Qt.PenStyle.DotLine,
            })
        if primary["MARU"]:
            sources.append({
                "source": "MaRu", "prefix": "M",
                "boxes": primary["MARU"],
                "images": self.core_images, "id_field": "globalid",
                "color": QColor("#9a5a18"),
                "style": Qt.PenStyle.DashDotLine,
            })
        count = len(sources)
        for index, source in enumerate(sources):
            left = bar_left + round(self.BAR_WIDTH * index / count)
            right = bar_left + round(self.BAR_WIDTH * (index + 1) / count)
            source.update({
                "left": left,
                "right": right,
                "width": max(1, right - left),
            })
        return sources

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
        painter.drawText(index_left, heading_y, self.plugin.t(
            "Indeks / genees" if self.observation_mode else "Indeks"
        ))
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
        if "samples" in tracks:
            painter.drawText(tracks["samples"] - 1, heading_y, "P")
        painter.setPen(QColor("#7b3f8c"))
        if "analyses" in tracks:
            painter.drawText(tracks["analyses"] - 1, heading_y, "A")
        painter.setPen(QColor("#267d92"))
        if "sarv_samples" in tracks:
            painter.drawText(tracks["sarv_samples"] + 14, heading_y, "SP")
        painter.setPen(QColor("#c06b25"))
        if "sarv_analyses" in tracks:
            painter.drawText(tracks["sarv_analyses"] + 14, heading_y, "SA")
        painter.setPen(QColor("#b23a62"))
        if "sarv_specimens" in tracks:
            painter.drawText(tracks["sarv_specimens"] + 14, heading_y, "SE")
        painter.setPen(QColor("#555555"))
        if self.show_core_boxes or self.show_sarv_core_boxes:
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
            index = self._index_text(unit)
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

        core_tracks = self._core_box_tracks(bar_left)
        if self.core_applicable and (core_tracks or self.show_core_boxes):
            hatch_color = QColor("#4f5963")
            hatch_color.setAlpha(95)
            hatch = QBrush(hatch_color, Qt.BrushStyle.BDiagPattern)
            hatch_tracks = core_tracks or [{
                "left": bar_left, "width": self.BAR_WIDTH, "boxes": [],
            }]
            for track in hatch_tracks:
                for start, end in _interval_gaps(track["boxes"], max_depth):
                    y1, y2 = depth_y(start), depth_y(end)
                    painter.fillRect(
                        track["left"], round(y1), track["width"],
                        max(1, round(y2 - y1)), hatch,
                    )
            painter.setPen(QColor("#555555"))
            painter.drawText(
                bar_left, 50,
                self.plugin.t("Viirutus: puursüdamiku kast puudub"),
            )
            if len(core_tracks) > 1:
                painter.setPen(QPen(QColor(70, 70, 70, 90), 1))
                for track in core_tracks[:-1]:
                    painter.drawLine(
                        track["right"], round(top_margin),
                        track["right"], round(top_margin + draw_height),
                    )

            for track in core_tracks:
                painter.setPen(QPen(
                    track["color"], 1, track["style"],
                ))
                for box in track["boxes"]:
                    start = max(0.0, _number(box.get("z_suht_ylemine")))
                    end = min(max_depth, _number(box.get("z_suht_alumine")))
                    if end < start or start > max_depth:
                        continue
                    y1, y2 = depth_y(start), depth_y(end)
                    painter.drawLine(
                        track["left"], round(y1), track["right"], round(y1),
                    )
                    painter.drawLine(
                        track["left"], round(y2), track["right"], round(y2),
                    )
                    number = box.get("kast_nr")
                    short_label = (
                        f"{track['prefix']}{number}"
                        if number not in (None, "") else track["prefix"]
                    )
                    if number not in (None, ""):
                        painter.drawText(
                            track["left"] + 3, round(y1) + 11, short_label,
                        )
                    identifier = str(
                        box.get(track["id_field"]) or ""
                    )
                    if track["id_field"] == "globalid":
                        identifier = identifier.upper()
                    urls = track["images"].get(identifier, [])
                    if urls:
                        self._click_targets.append({
                            "rect": (
                                track["left"], round(y1),
                                max(track["left"], track["right"] - 1),
                                max(round(y1) + 3, round(y2)),
                            ),
                            "urls": urls,
                            "label": f"{track['source']} {short_label}",
                            "kind": "images",
                            "source": track["source"],
                        })

        if "samples" in tracks:
            self._draw_intervals(
                painter, self.samples, tracks["samples"], QColor("#4f9b61"),
                top_margin, draw_height, max_depth,
            )
        if "analyses" in tracks:
            self._draw_intervals(
                painter, self.analyses, tracks["analyses"], QColor("#8b4a9b"),
                top_margin, draw_height, max_depth,
            )
        if "sarv_samples" in tracks:
            self._draw_intervals(
                painter, self.sarv_samples, tracks["sarv_samples"], QColor("#267d92"),
                top_margin, draw_height, max_depth, sarv=True,
            )
        if "sarv_analyses" in tracks:
            self._draw_intervals(
                painter, self.sarv_analyses, tracks["sarv_analyses"], QColor("#c06b25"),
                top_margin, draw_height, max_depth, sarv=True,
            )
        if "sarv_specimens" in tracks:
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
        urls = [
            str(url) for url in (row.get("_urls") or ()) if str(url).strip()
        ]
        if not urls and row.get("_url"):
            urls = [str(row["_url"])]
        if urls:
            label = str(row.get("_label") or "")
            tooltip = " · ".join(value for value in (label, item["depth"]) if value)
            self._click_targets.append({
                "rect": (left, top, left + width, top + height),
                "urls": urls,
                "items": [
                    {"url": url, "label": label, "depth": item["depth"]}
                    for url in urls
                ],
                "label": tooltip,
                "kind": "images" if len(urls) > 1 else "records",
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
            row_urls = [
                str(url) for url in (row.get("_urls") or ())
                if str(url).strip()
            ]
            if not row_urls and row.get("_url"):
                row_urls = [str(row["_url"])]
            if not row_urls:
                continue
            for url in row_urls:
                urls.append(url)
                menu_items.append({
                    "url": url,
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
                    menu = QMenu(self) if len(urls) <= 30 else None
                    entries = []
                    items = target.get("items", [])
                    for index, url in enumerate(urls, start=1):
                        if target.get("kind") == "images":
                            image_label = str(target.get("label") or "")
                            text = " · ".join(value for value in (
                                image_label,
                                f"{self.plugin.t('Pilt')} {index}",
                            ) if value)
                        else:
                            item = items[index - 1] if index <= len(items) else {}
                            text = " · ".join(
                                value for value in (
                                    str(item.get("label") or ""),
                                    str(item.get("depth") or ""),
                                ) if value
                            ) or str(url)
                        entries.append((text, url))
                        if menu is not None:
                            action = menu.addAction(text)
                            action.triggered.connect(
                                lambda checked=False, link=url: QDesktopServices.openUrl(QUrl(link))
                            )
                    if len(entries) > 30:
                        dialog = RecordLinksDialog(self.plugin, entries, self)
                        dialog.exec()
                        dialog.deleteLater()
                    else:
                        menu.exec(event.globalPosition().toPoint())
                        menu.deleteLater()
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


class ReadOnlyDetailDialog(QDialog):
    """Large, searchable and copyable snapshot of one selected object."""

    def __init__(self, plugin, snapshot_provider, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.snapshot_provider = snapshot_provider
        self._datasets = []
        self._original_datasets = []
        self._record_dialogs = []
        self.setWindowTitle(plugin.t("Detailvaade"))
        self.setModal(False)
        self.setMinimumSize(820, 560)
        self.resize(1120, 760)

        layout = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setWordWrap(True)
        self.heading.setStyleSheet(
            "font-size:16px;font-weight:600;padding:4px 2px;"
        )
        layout.addWidget(self.heading)
        self.note = QLabel(plugin.t(
            "Kirjutuskaitstud vaade. Algväärtus näitab lähteandmetes olevat "
            "koodi, kui kuvatav väärtus on domeenisildiks tõlgitud. "
            "Kirje kõigi täidetud lähteväljade nägemiseks tee tabelireal "
            "topeltklõps."
        ))
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        tools = QHBoxLayout()
        tools.addWidget(QLabel(plugin.t("Otsi aktiivsest tabelist")))
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText(plugin.t("Sisesta otsingutekst…"))
        self.search.textChanged.connect(self._apply_filter)
        tools.addWidget(self.search, 1)
        self.columns_button = QPushButton(self._columns_text("Veerud…"))
        self.columns_button.setObjectName("qeoloogDetailColumns")
        self.columns_button.clicked.connect(self._choose_columns)
        tools.addWidget(self.columns_button)
        self.refresh_button = QPushButton(plugin.t("Värskenda"))
        self.refresh_button.clicked.connect(self.refresh_data)
        tools.addWidget(self.refresh_button)
        layout.addLayout(tools)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        self.status = QLabel()
        footer.addWidget(self.status, 1)
        self.copy_selected_button = QPushButton(plugin.t("Kopeeri valitud read"))
        self.copy_selected_button.clicked.connect(self.copy_selected)
        footer.addWidget(self.copy_selected_button)
        self.copy_table_button = QPushButton(plugin.t("Kopeeri aktiivne tabel"))
        self.copy_table_button.clicked.connect(self.copy_active_table)
        footer.addWidget(self.copy_table_button)
        self.copy_all_button = QPushButton(plugin.t("Kopeeri kõik"))
        self.copy_all_button.clicked.connect(self.copy_all)
        footer.addWidget(self.copy_all_button)
        close_button = QPushButton(plugin.t("Sulge"))
        close_button.clicked.connect(self.close)
        footer.addWidget(close_button)
        layout.addLayout(footer)

        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self.copy_shortcut.activated.connect(self.copy_selected)
        self.refresh_data()

    def refresh_data(self):
        """Rebuild tabs from the latest fully decoded detail-widget values."""
        snapshot = self.snapshot_provider() or {}
        old_title = self.tabs.tabText(self.tabs.currentIndex()) if self.tabs.count() else ""
        current = self._active_table()
        old_key = getattr(current, "_qeoloog_table_key", "") if current else ""
        self._original_datasets = list(snapshot.get("tables") or [])
        preferences = self._column_preferences()
        self._datasets = [
            project_detail_columns(
                dataset, preferences.get(dataset.get("key")),
                self._column_label, self._technical_cell,
            )
            for dataset in self._original_datasets
        ]
        while self.tabs.count():
            page = self.tabs.widget(0)
            self.tabs.removeTab(0)
            page.deleteLater()
        self.heading.setText(str(snapshot.get("heading") or self.plugin.t("Detailvaade")))
        self.setWindowTitle(
            f"{self.plugin.t('Detailvaade')} — {snapshot.get('name', '')}".rstrip(" —")
        )
        restore_index = 0
        for index, dataset in enumerate(self._datasets):
            table = QTableWidget()
            headers = [str(value) for value in dataset.get("headers") or ()]
            rows = list(dataset.get("rows") or ())
            table.setColumnCount(len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.setRowCount(len(rows))
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            table.setAlternatingRowColors(True)
            table.setWordWrap(True)
            table.setSortingEnabled(False)
            table._qeoloog_headers = headers
            table._qeoloog_rows = rows
            table._qeoloog_table_key = dataset.get("key", "")
            records = list(dataset.get("records") or ())
            for row_index, row in enumerate(rows):
                for column, value in enumerate(row):
                    item = QTableWidgetItem(cell_text(value))
                    if isinstance(value, dict) and value.get("url"):
                        url = str(value["url"])
                        item.setData(Qt.ItemDataRole.UserRole, url)
                        item.setToolTip(url)
                        item.setForeground(QBrush(QColor("#1676c2")))
                    if row_index < len(records) and records[row_index]:
                        item.setData(DETAIL_RECORD_ROLE, records[row_index])
                    table.setItem(row_index, column, item)
            table.setSortingEnabled(True)
            table.horizontalHeader().setStretchLastSection(True)
            table.resizeColumnsToContents()
            original_count = len(headers) - dataset.get("extra_column_count", 0)
            for column in range(original_count, len(headers)):
                if table.columnWidth(column) > 360:
                    table.setColumnWidth(column, 360)
            table.resizeRowsToContents()
            table.cellDoubleClicked.connect(self._open_link)
            title = str(dataset.get("title") or self.plugin.t("Andmed"))
            self.tabs.addTab(table, f"{title} ({len(rows)})")
            if (old_key and old_key == dataset.get("key")) or (
                not old_key and old_title and old_title.startswith(title)
            ):
                restore_index = index
        if self.tabs.count():
            self.tabs.setCurrentIndex(min(restore_index, self.tabs.count() - 1))
        self._apply_filter(self.search.text())
        self._update_columns_button()

    def _columns_text(self, text):
        if getattr(self.plugin, "language", "et") == "en":
            return {
                "Veerud…": "Columns…",
                "Otsi lähtevälja…": "Find a source field…",
                "Veergude valik": "Choose columns",
                "Märgi veerud ja lähteväljad, mida selles tabelis näha soovid.": (
                    "Tick the columns and source fields to show in this table."
                ),
                "Vaikeveerg": "Default column",
                "Taasta vaikeveerud": "Restore default columns",
            }.get(text, text)
        return text

    @staticmethod
    def _column_preferences():
        return detail_column_preferences(QgsSettings().value(DETAIL_COLUMNS_SETTINGS, ""))

    @staticmethod
    def _write_column_preferences(preferences):
        QgsSettings().setValue(
            DETAIL_COLUMNS_SETTINGS, json.dumps(preferences, ensure_ascii=False)
        )

    def _column_label(self, field):
        label = field_label(field, getattr(self.plugin, "language", "et"))
        return label if label.casefold() == field.casefold() else f"{label} ({field})"

    def _technical_cell(self, record, field):
        value = record.get(field)
        if value is None or value == "" or value == [] or value == {}:
            return ""
        raw = self._record_value(value)
        table_id = record.get("_qeoloog_table_id")
        if record.get("_qeoloog_source") == "EGT" and table_id not in (None, ""):
            try:
                raw = _display_value(
                    self.plugin.decode_egt(int(table_id), field, value)
                )
            except (AttributeError, TypeError, ValueError):
                pass
        url = str(value) if isinstance(value, str) else ""
        if QUrl(url).isValid() and QUrl(url).scheme().casefold() in {"http", "https"}:
            return {"text": raw, "url": url}
        return raw

    def _active_original_dataset(self):
        index = self.tabs.currentIndex()
        if 0 <= index < len(self._original_datasets):
            return self._original_datasets[index]
        return {}

    def _update_columns_button(self):
        dataset = self._active_original_dataset()
        key = dataset.get("key")
        self.columns_button.setEnabled(bool(
            key and (default_detail_columns(dataset) or detail_column_candidates(dataset))
        ))

    def _choose_columns(self):
        dataset = self._active_original_dataset()
        key = dataset.get("key")
        if not key:
            return
        preferences = self._column_preferences()
        saved = preferences.get(key, {})
        saved_extra = saved.get("extra", [])
        saved_hidden = saved.get("hidden", [])
        defaults = default_detail_columns(dataset)
        candidates = detail_column_candidates(dataset)
        dialog = QDialog(self)
        dialog.setObjectName("qeoloogDetailColumnChooser")
        dialog.setWindowTitle(self._columns_text("Veergude valik"))
        dialog.resize(520, 450)
        layout = QVBoxLayout(dialog)
        message = QLabel(self._columns_text(
            "Märgi veerud ja lähteväljad, mida selles tabelis näha soovid."
        ))
        message.setWordWrap(True)
        layout.addWidget(message)
        search = QLineEdit()
        search.setClearButtonEnabled(True)
        search.setPlaceholderText(self._columns_text("Otsi lähtevälja…"))
        layout.addWidget(search)
        choices = QListWidget()
        choices.setObjectName("qeoloogDetailColumnChoices")
        layout.addWidget(choices, 1)
        def add_choice(text, kind, field, shown):
            option = QListWidgetItem(text)
            option.setFlags(option.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            option.setData(Qt.ItemDataRole.UserRole, (kind, field))
            option.setCheckState(
                Qt.CheckState.Checked if shown else Qt.CheckState.Unchecked
            )
            choices.addItem(option)

        for field, label in defaults:
            add_choice(
                f"{label} ({self._columns_text('Vaikeveerg')})", "default",
                field, field not in saved_hidden,
            )
        for field in sorted(candidates, key=lambda value: self._column_label(value).casefold()):
            add_choice(self._column_label(field), "extra", field, field in saved_extra)

        def filter_choices(text):
            needle = text.strip().casefold()
            for index in range(choices.count()):
                option = choices.item(index)
                option.setHidden(needle not in option.text().casefold())

        search.textChanged.connect(filter_choices)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        reset_button = buttons.addButton(
            self._columns_text("Taasta vaikeveerud"), QDialogButtonBox.ButtonRole.ResetRole
        )
        reset_requested = False

        def reset():
            nonlocal reset_requested
            reset_requested = True
            for index in range(choices.count()):
                option = choices.item(index)
                kind, _ = option.data(Qt.ItemDataRole.UserRole)
                option.setCheckState(
                    Qt.CheckState.Checked if kind == "default" else Qt.CheckState.Unchecked
                )

        reset_button.clicked.connect(reset)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        search.setFocus()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            checked = []
            hidden = []
            for index in range(choices.count()):
                option = choices.item(index)
                kind, field = option.data(Qt.ItemDataRole.UserRole)
                shown = option.checkState() == Qt.CheckState.Checked
                if kind == "extra" and shown:
                    checked.append(field)
                elif kind == "default" and not shown:
                    hidden.append(field)
            # Keep preferences that cannot be represented by this object's
            # fields, unless the user explicitly restores the defaults.
            retained = [
                field for field in saved_extra
                if field in checked or (field not in candidates and not reset_requested)
            ]
            selected = retained + [field for field in checked if field not in retained]
            if not reset_requested:
                default_keys = {field for field, _ in defaults}
                hidden.extend(field for field in saved_hidden if field not in default_keys)
            if selected or hidden:
                preferences[key] = {"extra": selected, "hidden": hidden}
            else:
                preferences.pop(key, None)
            self._write_column_preferences(preferences)
            self.refresh_data()
        dialog.deleteLater()

    def _active_table(self):
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, QTableWidget) else None

    def _tab_changed(self, _index):
        self._apply_filter(self.search.text())
        self._update_columns_button()

    def _apply_filter(self, text):
        table = self._active_table()
        if table is None:
            self.status.setText("")
            return
        needle = str(text or "").strip().casefold()
        visible = 0
        for row in range(table.rowCount()):
            matches = not needle or any(
                needle in (table.item(row, column).text() if table.item(row, column) else "").casefold()
                for column in range(table.columnCount())
            )
            table.setRowHidden(row, not matches)
            visible += int(matches)
        self.status.setText(self.plugin.t("Kuvatud read: {visible}/{total}").format(
            visible=visible, total=table.rowCount(),
        ))

    def _selected_payload(self, table):
        rows = sorted({item.row() for item in table.selectedItems()})
        if not rows:
            return None
        selected = [
            tuple(
                table.item(row, column).text()
                if table.item(row, column) is not None else ""
                for column in range(table.columnCount())
            )
            for row in rows
        ]
        return table_to_tsv(getattr(table, "_qeoloog_headers", []), selected)

    def _copy(self, text):
        QApplication.clipboard().setText(str(text or ""))
        self.status.setText(self.plugin.t("Andmed kopeeriti lõikelauale."))

    def copy_selected(self):
        table = self._active_table()
        if table is None:
            return
        payload = self._selected_payload(table)
        if payload is None:
            self.copy_active_table()
            return
        self._copy(payload)

    def copy_active_table(self):
        table = self._active_table()
        if table is None:
            return
        rows = [
            tuple(
                table.item(row, column).text()
                if table.item(row, column) is not None else ""
                for column in range(table.columnCount())
            )
            for row in range(table.rowCount())
            if not table.isRowHidden(row)
        ]
        self._copy(table_to_tsv(
            getattr(table, "_qeoloog_headers", []),
            rows,
        ))

    def copy_all(self):
        self._copy(tables_to_tsv(self._datasets))

    def _open_link(self, row, column):
        table = self._active_table()
        item = table.item(row, column) if table is not None else None
        url = item.data(Qt.ItemDataRole.UserRole) if item is not None else ""
        if url:
            QDesktopServices.openUrl(QUrl(str(url)))
            return
        record = item.data(DETAIL_RECORD_ROLE) if item is not None else None
        if not isinstance(record, dict):
            return
        dataset_title = self.tabs.tabText(self.tabs.currentIndex()).rsplit(" (", 1)[0]
        dialog = ReadOnlyDetailDialog(
            self.plugin,
            lambda values=dict(record), title=dataset_title: self._record_snapshot(
                title, values
            ),
            self,
        )
        self._record_dialogs.append(dialog)
        dialog.finished.connect(
            lambda _result, target=dialog: self._forget_record_dialog(target)
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _forget_record_dialog(self, dialog):
        if dialog in self._record_dialogs:
            self._record_dialogs.remove(dialog)

    def _record_snapshot(self, title, record):
        source = str(record.get("_qeoloog_source") or "")
        table_id = record.get("_qeoloog_table_id")
        rows = []
        for key, raw_value in record.items():
            if str(key).startswith("_qeoloog_") or self._empty_value(raw_value):
                continue
            raw = self._record_value(raw_value)
            display = raw
            if source == "EGT" and table_id not in (None, ""):
                try:
                    display = _display_value(
                        self.plugin.decode_egt(int(table_id), str(key), raw_value)
                    )
                except (TypeError, ValueError):
                    display = raw
            value = (
                {"text": display, "url": raw}
                if raw.startswith(("https://", "http://")) else display
            )
            rows.append((
                field_label(str(key), self.plugin.language),
                value,
                raw if raw != display else "",
                str(key),
                source,
            ))
        identifier = next((
            record.get(key) for key in (
                "number", "proov_tahis_alg", "analyys_kood", "name",
                "id", "globalid", "objectid",
            ) if record.get(key) not in (None, "")
        ), "")
        name = " — ".join(
            value for value in (title, _display_value(identifier)) if value
        )
        return {
            "name": name,
            "heading": f"{name} · {self.plugin.t('kirjutuskaitstud')}",
            "tables": ({
                "key": "record_fields",
                "title": self.plugin.t("Täidetud väljad"),
                "column_keys": ("field", "value", "raw_value", "technical_field", "source"),
                "headers": (
                    self.plugin.t("Väli"), self.plugin.t("Väärtus"),
                    self.plugin.t("Algväärtus"),
                    self.plugin.t("Tehniline väli"),
                    self.plugin.t("Allikas"),
                ),
                "rows": rows,
            },),
        }

    @staticmethod
    def _empty_value(value):
        return value is None or value == "" or value == [] or value == {}

    @staticmethod
    def _record_value(value):
        if isinstance(value, (dict, list, tuple)):
            try:
                return json.dumps(value, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                return str(value)
        return _display_value(value)


class DetailWidget(QWidget, LocalObjectDetailMixin):
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
        self.faktika_badge = QLabel("")
        self.faktika_badge.setVisible(False)
        self.faktika_badge.setStyleSheet(
            "background:#1f6f54;color:white;border-radius:3px;"
            "padding:3px 7px;font-weight:600;"
        )
        header_layout.addWidget(self.faktika_badge)
        self.faktika_add = QPushButton(t("Lisa objekt"))
        self.faktika_add.setVisible(False)
        self.faktika_add.clicked.connect(plugin.add_faktika_object)
        header_layout.addWidget(self.faktika_add)
        self.faktika_edit = QPushButton(t("Redigeeri"))
        self.faktika_edit.setVisible(False)
        self.faktika_edit.clicked.connect(plugin.edit_current_faktika_object)
        header_layout.addWidget(self.faktika_edit)
        self.detail_view_button = QPushButton(t("Detailvaade"))
        self.detail_view_button.setVisible(False)
        self.detail_view_button.setToolTip(t(
            "Ava täidetud väljad ja seotud tabelid eraldi kirjutuskaitstud aknas"
        ))
        self.detail_view_button.clicked.connect(self.open_detail_view)
        header_layout.addWidget(self.detail_view_button)
        self.go_to_location_button = QPushButton(t("Mine asukohta"))
        self.go_to_location_button.setVisible(False)
        self.go_to_location_button.setToolTip(t(
            "Liiguta kaart objekti asukohta, säilitades mõõtkava"
        ))
        self.go_to_location_button.clicked.connect(self.go_to_location)
        header_layout.addWidget(self.go_to_location_button)
        self.add_to_cross_section = QCheckBox(t("Lisa läbilõikele"))
        self.add_to_cross_section.setVisible(False)
        self.add_to_cross_section.toggled.connect(
            self._toggle_cross_section
        )
        header_layout.addWidget(self.add_to_cross_section)
        layout.addWidget(header_host)
        self.header.setTextFormat(Qt.TextFormat.PlainText)
        self._init_local_detail_controls(layout)
        self.tabs = QTabWidget()
        self.local_detail_stack.addWidget(self.tabs)
        self.local_detail_stack.addWidget(self.local_detail_tabs)
        self._local_detail_profile = ProfileWidget(plugin)
        self._local_detail_profile.setParent(self.local_detail_tabs)
        self._local_detail_profile.hide()

        self.overview = self._table((t("Väli"), t("Väärtus")))
        self.overview.setWordWrap(True)
        # Detail values must wrap inside the dock instead of forcing a
        # horizontal scrollbar.  Combo-box/drop-down lists are separate
        # widgets and retain their own scrolling behaviour.
        self.overview.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.overview.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents,
        )
        self.overview.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch,
        )
        self.overview.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents,
        )
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
        self.profile_egt_units = QCheckBox(t("Läbilõige"))
        self.profile_egt_units.setChecked(True)
        profile_controls.addWidget(self.profile_egt_units)
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
        maaru_controls = QHBoxLayout()
        self.profile_maaru_label = QLabel("MaRu:")
        maaru_controls.addWidget(self.profile_maaru_label)
        self.profile_maaru_units = QCheckBox(t("Läbilõige"))
        self.profile_maaru_boxes = QCheckBox(t("Kastipiirid"))
        self.profile_maaru_samples = QCheckBox(t("Proovid"))
        for checkbox in (
            self.profile_maaru_units,
            self.profile_maaru_boxes,
            self.profile_maaru_samples,
        ):
            checkbox.setChecked(True)
            maaru_controls.addWidget(checkbox)
        maaru_controls.addStretch(1)
        profile_layout.addLayout(maaru_controls)
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
        self.profile_egt_units.toggled.connect(self._refresh_profile_units)
        self.profile_maaru_units.toggled.connect(self._refresh_profile_units)
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
        self.profile_boxes.toggled.connect(self._set_profile_egt_boxes)
        self.profile_maaru_boxes.toggled.connect(self._set_profile_maaru_boxes)
        self.profile_samples.toggled.connect(self._set_profile_egt_samples)
        self.profile_maaru_samples.toggled.connect(
            self._set_profile_maaru_samples
        )
        self.profile_analyses.toggled.connect(
            lambda checked: self.profile.set_options(analyses=checked)
        )
        self.profile_sarv_samples.toggled.connect(
            lambda checked: self.profile.set_options(sarv_samples=checked)
        )
        self.profile_sarv_boxes.toggled.connect(self._set_profile_sarv_boxes)
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
                t("Diameeter"), t("Staatus / hoiukoht"), t("Kirjeldus"),
                t("Pildid"),
                t("Muudetud"),
            ),
            ("EGT", "MaRu", "SARV"),
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
        self.core_add_button = QPushButton(t("Lisa kast…"))
        self.core_add_button.clicked.connect(self._add_core_box)
        self.core_reset_button = QPushButton(t("Taasta algandmed"))
        self.core_reset_button.clicked.connect(self._reset_selected_core)
        self.core_edit_hint = QLabel(t(
            "Muudatused salvestuvad ainult selles arvutis."
        ))
        self.core_edit_hint.setWordWrap(True)
        core_edit_controls.addWidget(self.core_edit_mode)
        core_edit_controls.addWidget(self.core_add_button)
        core_edit_controls.addWidget(self.core_edit_button)
        core_edit_controls.addWidget(self.core_reset_button)
        core_edit_controls.addWidget(self.core_edit_hint, 1)
        core_page.layout().insertLayout(1, core_edit_controls)
        self.core.itemSelectionChanged.connect(
            self._update_core_edit_actions
        )
        self.tabs.addTab(core_page, t("Puursüdamik"))
        samples_page, self.samples, self.sample_sources = self._source_page(
            (
                t("Allikas"), t("Tähis"), t("Tüüp"), t("Ülemine"),
                t("Alumine"), t("Eesmärk"), t("Asukoht"), t("Staatus"),
            ),
            ("EGT", "MaRu", "SARV"),
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
        attachments_page, self.attachments, self.attachment_sources = self._source_page(
            (
                t("Allikas"), t("Tüüp"), t("Nimetus"), t("Sügavus"),
                t("Abs Z"), t("Indeks"), t("Litoloogia"), t("Link"),
            ),
            ("EGT", "MaRu", "SARV", t("EGT Portal")),
        )
        self.show_maaru_core_attachments = QCheckBox(
            t("Kuva MaRu kastifotod ka manustes")
        )
        self.show_maaru_core_attachments.setChecked(False)
        attachment_controls = attachments_page.layout().itemAt(0).layout()
        attachment_controls.insertWidget(
            max(0, attachment_controls.count() - 1),
            self.show_maaru_core_attachments,
        )
        self.attachments.cellDoubleClicked.connect(self._open_attachment)
        self.tabs.addTab(attachments_page, t("Manused"))
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
        self._simple_feature_mode = False
        self._last_standard_tab = 0
        self._last_veka_tab = 0
        self._core_rows = []
        self._egt_core_images = {}
        self._maaru_core_rows = []
        self._maaru_core_images = {}
        self._sarv_core_rows = []
        self._sarv_core_images = {}
        self._core_display_records = {}
        self._egt_samples = []
        self._maaru_samples = []
        self._sarv_samples = []
        self._sarv_samples_by_source = {"locality": [], "site": []}
        self._egt_analyses = ([], {})
        self._sarv_analyses_by_source = {"sample": [], "specimen": []}
        self._sarv_specimens = []
        self._sarv_literature = []
        self._sarv_analysis_refs = {"sample": [], "specimen": []}
        self._portal_attachments = []
        self._egt_attachments = []
        self._maaru_attachments = []
        self._sarv_attachments = []
        self._egt_profile_units = []
        self._maaru_profile_units = []
        self._maaru_overview = {}
        self._overview_has_sarv_id = False
        self._overview_sarv_locality_id = None
        self._overview_base_rows = 0
        self._current_detail_name = ""
        self._current_detail_role = ""
        self._current_detail_attributes = {}
        self._detail_dialog = None
        self._faktika_signed_in = False
        self._faktika_context = None
        self._overview_row_keys = {}
        for checkbox in self.core_sources.values():
            checkbox.toggled.connect(self._refresh_core)
            checkbox.toggled.connect(self._notify_cross_section_update)
        self.core_sources["EGT"].toggled.connect(
            self.profile_boxes.setChecked
        )
        self.core_sources["MaRu"].toggled.connect(
            self.profile_maaru_boxes.setChecked
        )
        self.core_sources["SARV"].toggled.connect(
            self.profile_sarv_boxes.setChecked
        )
        for checkbox in self.sample_sources.values():
            checkbox.toggled.connect(self._refresh_samples)
        self.sample_sources["EGT"].toggled.connect(
            self.profile_samples.setChecked
        )
        self.sample_sources["MaRu"].toggled.connect(
            self.profile_maaru_samples.setChecked
        )
        for checkbox in self.analysis_sources.values():
            checkbox.toggled.connect(self._refresh_analyses)
        for checkbox in self.specimen_sources.values():
            checkbox.toggled.connect(self._refresh_specimens)
        for checkbox in self.attachment_sources.values():
            checkbox.toggled.connect(self._refresh_attachments)
        self.show_maaru_core_attachments.toggled.connect(
            self._refresh_attachments
        )
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
        observation = self._current_detail_role in {
            "observations", "field_mapping",
        }
        show_sarv_tracks = not enabled and not observation
        self.profile.set_observation_mode(observation)
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
            self.profile_boxes,
            self.profile_sarv_label, self.profile_sarv_boxes,
            self.profile_maaru_label, self.profile_maaru_units,
            self.profile_maaru_boxes, self.profile_maaru_samples,
        ):
            widget.setVisible(not enabled)
        self.profile_sarv_grouping.setVisible(show_sarv_tracks)
        self.profile.set_options(
            core_boxes=(
                False if enabled else (
                    self.profile_boxes.isChecked()
                    or self.profile_maaru_boxes.isChecked()
                )
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
                show_sarv_tracks and self.profile_sarv_samples.isChecked()
            ),
            sarv_analyses=(
                show_sarv_tracks and self.profile_sarv_analyses.isChecked()
            ),
            sarv_specimens=(
                show_sarv_tracks and self.profile_sarv_specimens.isChecked()
            ),
            veka_construction=(
                enabled and self.profile_veka_construction.isChecked()
            ),
            veka_static_water_level=(
                enabled and self.profile_veka_static_water_level.isChecked()
            ),
        )
        self._veka_mode = enabled
        self._update_profile_related_controls()
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

    def _set_profile_egt_boxes(self, checked):
        self.core_sources["EGT"].setChecked(bool(checked))

    def _set_profile_maaru_boxes(self, checked):
        self.core_sources["MaRu"].setChecked(bool(checked))

    def _set_profile_sarv_boxes(self, checked):
        self.core_sources["SARV"].setChecked(bool(checked))

    def _set_profile_egt_samples(self, checked):
        self.sample_sources["EGT"].setChecked(bool(checked))

    def _set_profile_maaru_samples(self, checked):
        self.sample_sources["MaRu"].setChecked(bool(checked))

    def _update_profile_related_controls(self):
        """Show profile data switches only when their source has records."""
        standard = not self._veka_mode
        show_sarv = standard and self._current_detail_role not in {
            "observations", "field_mapping",
        }
        self.profile_egt_units.setVisible(
            standard and bool(self._egt_profile_units)
        )
        self.profile_boxes.setVisible(
            standard and bool(self._core_rows)
        )
        self.profile_samples.setVisible(
            standard and bool(self._egt_samples)
        )
        self.profile_analyses.setVisible(
            standard and bool(self._egt_analyses[0])
        )
        has_maaru = bool(
            self._maaru_profile_units
            or self._maaru_core_rows or self._maaru_samples
        )
        has_egt = bool(
            self._egt_profile_units or self._core_rows or self._egt_samples
            or self._egt_analyses[0]
        )
        if standard:
            self.profile_egt_label.setText(
                "EGT:" if has_egt else f"{self.plugin.t('Kuvamine')}:"
            )
        self.profile_egt_label.setVisible(True)
        self.profile_maaru_label.setVisible(standard and has_maaru)
        self.profile_maaru_units.setVisible(
            standard and bool(self._maaru_profile_units)
        )
        self.profile_maaru_boxes.setVisible(
            standard and bool(self._maaru_core_rows)
        )
        self.profile_maaru_samples.setVisible(
            standard and bool(self._maaru_samples)
        )
        self.profile_sarv_samples.setVisible(
            show_sarv and bool(self._sarv_samples)
        )
        self.profile_sarv_analyses.setVisible(
            show_sarv and any(self._sarv_analyses_by_source.values())
        )
        self.profile_sarv_specimens.setVisible(
            show_sarv and bool(self._sarv_specimens)
        )

    def _set_simple_feature_mode(self, enabled):
        """Use an overview-only detail view for polygon registry objects."""
        enabled = bool(enabled)
        if enabled:
            if not self._simple_feature_mode:
                # Normalize a possible VEKA view before hiding every related
                # data tab, so the next point object can restore its own mode.
                self._set_veka_mode(False)
            self._simple_feature_mode = True
            for index in range(1, self.tabs.count()):
                self.tabs.setTabVisible(index, False)
            self.tabs.setCurrentIndex(0)
            return
        if not self._simple_feature_mode:
            return
        self._simple_feature_mode = False
        self.tabs.setTabVisible(1, True)

    def show_loading(self, name, attributes, role):
        if self._detail_dialog is not None and self._detail_dialog.isVisible():
            self._detail_dialog.close()
        self._current_detail_name = str(name)
        self._current_detail_role = str(role)
        self._current_detail_attributes = dict(attributes or {})
        self._original_detail_title = f"{name} — {self.plugin.t('seotud andmeid laaditakse…')}"
        self.local_detail_stack.show()
        self._begin_original_detail(role, self._current_detail_attributes)
        self.detail_view_button.setVisible(bool(name or attributes))
        self.go_to_location_button.setVisible(bool(name or attributes))
        self.set_faktika_context(None)
        self.sync_cross_section_button()
        simple_feature = role in {
            "mineral_deposits", "mining_claims", "exploration_areas",
            "engineering_geology_points", "archive_survey_areas",
        } or str(role).startswith(("gtk_", "latvia_"))
        self._set_simple_feature_mode(simple_feature)
        if not simple_feature:
            self._set_veka_mode(role == "veka_boreholes")
            if role == "field_mapping":
                # These points have an overview and geological descriptions,
                # plus authenticated ArcGIS feature attachments.
                for index in range(2, self.tabs.count()):
                    self.tabs.setTabVisible(index, False)
                self.tabs.setTabVisible(6, True)
        sarv_id = str(attributes.get("sarv_id") or "").strip()
        self._overview_has_sarv_id = (
            sarv_id.isdigit() and int(sarv_id) > 0
        )
        self._overview_sarv_locality_id = None
        self._fill_pairs(self.overview, attributes, role)
        self._overview_base_rows = self.overview.rowCount()
        self.profile.set_core_applicable(
            role in {"boreholes", "sarv_drillcores", "maaru_cores"}
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
        self._maaru_core_rows = []
        self._maaru_core_images = {}
        self._sarv_core_rows = []
        self._sarv_core_images = {}
        self._egt_samples = []
        self._maaru_samples = []
        self._sarv_samples = []
        self._sarv_samples_by_source = {"locality": [], "site": []}
        self._egt_analyses = ([], {})
        self._sarv_analyses_by_source = {"sample": [], "specimen": []}
        self._sarv_specimens = []
        self._sarv_literature = []
        self._sarv_analysis_refs = {"sample": [], "specimen": []}
        self._portal_attachments = []
        self._egt_attachments = []
        self._maaru_attachments = []
        self._sarv_attachments = []
        self._egt_profile_units = []
        self._maaru_profile_units = []
        self._maaru_overview = {}
        self._update_profile_related_controls()
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
        if self._local_detail_is_active():
            return '' if self._showing_captured_original() else local_cross_section(self._local_detail_record)['key']
        attributes = self._current_detail_attributes
        identifier = next((
            attributes.get(key) for key in (
                "esri_globalid", "globalid", "eelis_id", "sarv_id",
                "maaru_id", "gea_id", "kkr_kood", "number",
            ) if attributes.get(key) not in (None, "")
        ), "")
        return (
            f"{self._current_detail_role}:{identifier}"
            if identifier else ""
        )

    def cross_section_snapshot(self):
        if self._local_detail_is_active():
            return None if self._showing_captured_original() else local_cross_section(self._local_detail_record)
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
            "field_mapping": "EGT välitöö",
            "veka_boreholes": "VEKA",
            "sarv_drillcores": "SARV",
            "sarv_localities": "SARV",
            "sarv_sites": "SARV",
            "maaru_cores": "MaRu",
        }.get(self._current_detail_role, self._current_detail_role)
        snapshot = {
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
        if attributes.get("_qeoloog_section_private_source"):
            snapshot["faktika"] = True
            snapshot["faktika_workspace"] = attributes.get("_qeoloog_section_workspace")
        ref = section_source_ref(snapshot, attributes)
        if ref:
            snapshot["source_ref"] = ref
        return snapshot

    def sync_cross_section_button(self, *_):
        role = self._current_detail_role
        supported = role in {
            "boreholes", "observations", "veka_boreholes", "sarv_localities",
            "sarv_drillcores", "sarv_sites", "maaru_cores", "field_mapping",
        }
        sections = getattr(getattr(self.plugin, "dock", None), "cross_sections", None)
        if getattr(sections, "workspace", None) and (
            role in {"maaru_cores", "field_mapping"}
            or self._current_detail_attributes.get("_qeoloog_section_private_source")
        ):
            supported = False
        if self._local_detail_is_active():
            supported = not self._showing_captured_original()
        key = self.current_cross_section_key()
        self.add_to_cross_section.blockSignals(True)
        self.add_to_cross_section.setVisible(supported)
        self.add_to_cross_section.setChecked(
            bool(supported and key and self.plugin.cross_section_contains(key))
        )
        self.add_to_cross_section.blockSignals(False)

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
        self._original_detail_title = str(name)
        if not self._local_detail_is_active():
            self.header.setText(name)

    def open_detail_view(self):
        """Open a modeless read-only table view of the selected object."""
        if not (self._local_detail_is_active() or self._current_detail_name or self._current_detail_attributes):
            return
        if self._detail_dialog is None:
            self._detail_dialog = ReadOnlyDetailDialog(
                self.plugin, self._displayed_detail_snapshot, self.window(),
            )
        else:
            self._detail_dialog.refresh_data()
        self._detail_dialog.show()
        self._detail_dialog.raise_()
        self._detail_dialog.activateWindow()

    def go_to_location(self):
        position = self._local_location_attributes() if self._local_detail_is_active() else self._current_detail_attributes
        self.plugin.go_to_detail_location(position)

    def detail_view_snapshot(self):
        """Return decoded, non-empty table data for the read-only popup."""
        source = self._detail_source_label()
        overview_rows = []
        for row in range(self.overview.rowCount()):
            label = self._snapshot_cell(self.overview, row, 0)
            value = self._snapshot_cell(self.overview, row, 1)
            key = self._overview_row_keys.get(row, "")
            raw = _display_value(self._current_detail_attributes.get(key)) if key else ""
            visible_text = cell_text(value)
            if raw == visible_text:
                raw = ""
            if visible_text or raw:
                row_source = (
                    "SARV" if cell_text(label).strip().upper() == "SARV"
                    else source
                )
                overview_rows.append((label, value, raw, key, row_source))

        tables = [{
            "key": "overview",
            "title": self.plugin.t("Üldandmed"),
            "column_keys": ("field", "value", "raw_value", "technical_field", "source"),
            "headers": (
                self.plugin.t("Väli"), self.plugin.t("Väärtus"),
                self.plugin.t("Algväärtus"), self.plugin.t("Tehniline väli"),
                self.plugin.t("Allikas"),
            ),
            "rows": overview_rows,
        }]
        if self._maaru_overview:
            maaru_rows = [
                (
                    field_label(str(key), self.plugin.language),
                    _display_value(value), "", str(key), "MaRu",
                )
                for key, value in self._maaru_overview.items()
                if value not in (None, "")
                and not str(key).startswith("_")
            ]
            tables.append({
                "key": "maaru_overview",
                "title": self.plugin.t("MaRu üldandmed"),
                "column_keys": ("field", "value", "raw_value", "technical_field", "source"),
                "headers": (
                    self.plugin.t("Väli"), self.plugin.t("Väärtus"),
                    self.plugin.t("Algväärtus"),
                    self.plugin.t("Tehniline väli"),
                    self.plugin.t("Allikas"),
                ),
                "rows": maaru_rows,
            })
        units = list(getattr(self.profile, "units", ()) or ())
        if units:
            unit_rows = []
            unit_records = []
            for unit in units:
                unit_rows.append((
                    self._first_detail_value(
                        unit, "z_suht_ylemine", "depth_top", "top",
                    ),
                    self._first_detail_value(
                        unit, "z_suht_alumine", "depth_bottom", "bottom",
                    ),
                    self._first_detail_value(
                        unit, "stratigraafia_indeks", "indeks", "index",
                    ),
                    self._first_detail_value(
                        unit, "kihistik", "formation",
                    ),
                    self._first_detail_value(
                        unit, "genees", "genesis",
                    ),
                    self._first_detail_value(
                        unit, "litoloogia", "lithology",
                    ),
                ))
                unit_records.append(self._detail_record(
                    unit,
                    self.plugin.t("EGT Portal")
                    if self._current_detail_role == "field_mapping" else "EGT",
                    2,
                ))
            tables.append({
                "key": "geological_units",
                "title": self.plugin.t("Geoloogilised üksused"),
                "column_keys": ("top", "bottom", "index", "formation", "genesis", "lithology"),
                "headers": (
                    self.plugin.t("Ülemine"), self.plugin.t("Alumine"),
                    self.plugin.t("Indeks"), self.plugin.t("Kihistik"),
                    self.plugin.t("Genees"), self.plugin.t("Litoloogia"),
                ),
                "rows": unit_rows,
                "records": unit_records,
            })
        if self._maaru_profile_units:
            rows = []
            records = []
            for unit in self._maaru_profile_units:
                rows.append((
                    self._first_detail_value(unit, "z_suht_ylemine"),
                    self._first_detail_value(unit, "z_suht_alumine"),
                    _unit_index(unit),
                    self._first_detail_value(unit, "strat_kirjeldus"),
                    self._first_detail_value(unit, "litoloogia"),
                    self._first_detail_value(unit, "autor"),
                ))
                records.append(self._detail_record(unit, "MaRu"))
            tables.append({
                "key": "maaru_geological_units",
                "title": self.plugin.t("MaRu geoloogiline kirjeldus"),
                "column_keys": ("top", "bottom", "index", "description", "lithology", "author"),
                "headers": (
                    self.plugin.t("Ülemine"), self.plugin.t("Alumine"),
                    self.plugin.t("Indeks"), self.plugin.t("Kirjeldus"),
                    self.plugin.t("Litoloogia"), self.plugin.t("Autor"),
                ),
                "rows": rows,
                "records": records,
            })
        related = (
            ("core", "Puursüdamik", self.core,
             ("source", "number", "top", "bottom", "diameter", "status", "description", "images", "modified")),
            ("samples", "Proovid", self.samples,
             ("source", "label", "type", "top", "bottom", "purpose", "location", "status")),
            ("analyses", "Analüüsid", self.analyses,
             ("source", "code", "depth", "date", "method", "lab", "indicators")),
            ("specimens", "Eksemplarid", self.specimens,
             ("source", "label", "type", "depth", "interval", "rock")),
            ("attachments", "Manused", self.attachments,
             ("source", "type", "name", "depth", "elevation", "index", "lithology", "link")),
            ("literature", "Kirjandus", self.literature,
             ("source", "author", "year", "title", "type", "link")),
            ("veka_construction", "Konstruktsioon", self.veka_construction,
             ("category", "type", "top", "bottom", "diameter", "products", "insulation", "description")),
            ("veka_pumping", "Pumpamiskatsed", self.veka_pumping,
             ("date", "type", "aquifer", "depth", "static", "dynamic", "drawdown",
              "flow", "specific_capacity", "duration", "technology")),
            ("veka_chemistry", "Veekeemia", self.veka_chemistry,
             ("analysis", "date", "indicator", "result", "unit", "normalized_result",
              "normalized_unit", "sample_type", "protocol")),
        )
        for table_key, title, table, column_keys in related:
            headers = tuple(
                table.horizontalHeaderItem(column).text()
                if table.horizontalHeaderItem(column) is not None else ""
                for column in range(table.columnCount())
            )
            rows = []
            records = []
            for row in range(table.rowCount()):
                values = tuple(
                    self._snapshot_cell(table, row, column)
                    for column in range(table.columnCount())
                )
                if any(cell_text(value).strip() for value in values):
                    rows.append(values)
                    first = table.item(row, 0)
                    records.append(
                        first.data(DETAIL_RECORD_ROLE)
                        if first is not None else None
                    )
            if rows:
                tables.append({
                    "key": table_key,
                    "title": self.plugin.t(title),
                    "column_keys": column_keys,
                    "headers": headers,
                    "rows": rows,
                    "records": records,
                })
        return {
            "name": self._current_detail_name,
            "heading": (
                f"{self._current_detail_name} · {source} · "
                f"{self.plugin.t('kirjutuskaitstud')}"
            ),
            "tables": tables,
        }

    def _detail_source_label(self):
        role = self._current_detail_role
        if role == "veka_boreholes":
            return "VEKA"
        if role.startswith("sarv_"):
            return "SARV"
        if role == "maaru_cores":
            return "MaRu"
        if role == "field_mapping":
            return self.plugin.t("EGT Portal")
        if role in {"boreholes", "observations"}:
            return "EGT"
        return self.plugin.t(role.replace("_", " ").strip().title()) if role else ""

    @staticmethod
    def _first_detail_value(row, *keys):
        for key in keys:
            value = row.get(key) if isinstance(row, dict) else None
            if value not in (None, ""):
                if isinstance(value, dict):
                    return (
                        value.get("value") or value.get("name")
                        or value.get("name_en") or value.get("code") or ""
                    )
                return value
        return ""

    @staticmethod
    def _snapshot_cell(table, row, column):
        widget = table.cellWidget(row, column)
        item = table.item(row, column)
        if widget is not None:
            tooltip = str(widget.toolTip() or "").strip()
            url = tooltip if QUrl(tooltip).scheme().lower() in {"http", "https"} else ""
            explicit = widget.property("qeoloog_display_text")
            if explicit not in (None, ""):
                text = str(explicit)
            elif item is not None and item.text():
                text = item.text()
            else:
                labels = []
                candidates = [widget] if isinstance(widget, QLabel) else widget.findChildren(QLabel)
                for label in candidates:
                    anchor = re.search(r'href=[\"\x27]([^\"\x27]+)', label.text() or "", re.I)
                    if anchor and not url:
                        target = html_unescape(anchor.group(1))
                        if QUrl(target).scheme().lower() in {"http", "https"}:
                            url = target
                    value = re.sub(r"<[^>]+>", "", label.text() or "")
                    value = html_unescape(value).strip()
                    if value and value not in labels:
                        labels.append(value)
                text = " · ".join(labels)
            return {"text": text, "url": url} if url else text
        return item.text() if item is not None else ""

    def refresh_overview_labels(self):
        """Refresh overview labels after asynchronous Portal metadata loads."""
        self._refresh_overview_value_labels()

    def set_faktika_access(self, signed_in):
        """Expose write controls only after an authenticated Portal session."""
        self._faktika_signed_in = bool(signed_in)
        editing_enabled = bool(getattr(
            self.plugin, "portal_editing_enabled", False
        ))
        self.faktika_add.setVisible(
            editing_enabled and self._faktika_signed_in
        )
        self.faktika_edit.setVisible(
            editing_enabled and self._faktika_signed_in
            and self._faktika_context is not None
        )

    def set_faktika_context(self, context, status=""):
        self._faktika_context = context if isinstance(context, dict) else None
        editing_enabled = bool(getattr(
            self.plugin, "portal_editing_enabled", False
        ))
        self.faktika_edit.setVisible(
            editing_enabled and self._faktika_signed_in
            and self._faktika_context is not None
        )
        text = str(status or "")
        self.faktika_badge.setText(text)
        self.faktika_badge.setVisible(bool(text))
        if self._faktika_context is not None:
            self._refresh_overview_value_labels()

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
        """Remove SARV match rows without discarding independent MaRu rows."""
        for row in range(self.overview.rowCount() - 1, self._overview_base_rows - 1, -1):
            item = self.overview.item(row, 0)
            if "MaRu" not in (item.text() if item else ""):
                self.overview.removeRow(row)

    def reset_maaru_match_rows(self):
        for row in range(self.overview.rowCount() - 1, self._overview_base_rows - 1, -1):
            item = self.overview.item(row, 0)
            if "MaRu" in (item.text() if item else ""):
                self.overview.removeRow(row)

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

    def add_maaru_match_editor(
        self, current_id, manual, edit_callback, reset_callback=None,
        source_ma_id="", invalid_ma_id=False, invalid_callback=None,
    ):
        row = self.overview.rowCount()
        self.overview.insertRow(row)
        self.overview.setItem(
            row, 0, QTableWidgetItem(self.plugin.t("MaRu seose haldus")),
        )
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(4, 0, 4, 0)
        if current_id:
            prefix = self.plugin.t(
                "Kohalik parandus" if manual else "EGT MaRu ID"
            )
            layout.addWidget(QLabel(f"{prefix}: {current_id}"))
        else:
            layout.addWidget(QLabel(self.plugin.t("MaRu objekt pole seotud")))

        def ask_for_id():
            try:
                initial = max(1, int(current_id or source_ma_id or 1))
            except (TypeError, ValueError):
                initial = 1
            value, accepted = QInputDialog.getInt(
                self, self.plugin.t("Määra MaRu seos"),
                self.plugin.t("MaRu puursüdamiku ID"),
                initial, 1, 2147483647, 1,
            )
            if accepted:
                edit_callback(value)

        button = QPushButton(self.plugin.t(
            "Muuda MaRu seost" if current_id else "Lisa MaRu seos"
        ))
        button.clicked.connect(ask_for_id)
        layout.addWidget(button)
        if manual and reset_callback:
            reset = QPushButton(self.plugin.t("Taasta EGT MaRu seos"))
            reset.clicked.connect(reset_callback)
            layout.addWidget(reset)
        if source_ma_id not in (None, ""):
            invalid = QCheckBox(
                f"{self.plugin.t('Vigane Maa-ameti ID seos')}: {source_ma_id}"
            )
            invalid.setChecked(bool(invalid_ma_id))
            if invalid_callback:
                invalid.toggled.connect(invalid_callback)
            layout.addWidget(invalid)
        layout.addStretch(1)
        self.overview.setCellWidget(row, 1, host)
        self.overview.resizeRowsToContents()

    def set_profile(self, units):
        self._local_profile_status = 'loaded'
        self._egt_profile_units = [
            {**unit, "_qeoloog_source": "EGT"} for unit in units
        ]
        self._refresh_profile_units()

    def set_maaru_profile(self, units):
        self._maaru_profile_units = list(units)
        self._refresh_profile_units()

    @staticmethod
    def _merge_profile_units(primary, supplemental):
        """Fill gaps in the authoritative profile with another source."""
        result = [dict(unit) for unit in primary]
        occupied = []
        for unit in primary:
            start = _number(unit.get("z_suht_ylemine"))
            end = _number(unit.get("z_suht_alumine"))
            if end > start:
                occupied.append((start, end))
        for unit in supplemental:
            start = _number(unit.get("z_suht_ylemine"))
            end = _number(unit.get("z_suht_alumine"))
            if end <= start:
                continue
            segments = [(start, end)]
            for used_start, used_end in occupied:
                remaining = []
                for segment_start, segment_end in segments:
                    if used_end <= segment_start or used_start >= segment_end:
                        remaining.append((segment_start, segment_end))
                        continue
                    if used_start > segment_start:
                        remaining.append((segment_start, used_start))
                    if used_end < segment_end:
                        remaining.append((used_end, segment_end))
                segments = remaining
                if not segments:
                    break
            for segment_start, segment_end in segments:
                result.append({
                    **unit,
                    "z_suht_ylemine": segment_start,
                    "z_suht_alumine": segment_end,
                    "_qeoloog_show_source": True,
                })
        return sorted(
            result, key=lambda item: _number(item.get("z_suht_ylemine"))
        )

    def _refresh_profile_units(self):
        show_egt = self.profile_egt_units.isChecked()
        show_maaru = self.profile_maaru_units.isChecked()
        egt_units = self._egt_profile_units if show_egt else []
        maaru_units = self._maaru_profile_units if show_maaru else []
        if egt_units and maaru_units:
            units = self._merge_profile_units(egt_units, maaru_units)
        else:
            units = list(egt_units or maaru_units)
        self.profile.set_units(units)
        self.tabs.setTabText(
            1, f"{self.plugin.t('Läbilõige')} ({len(units)})"
        )
        self._update_profile_related_controls()
        self._notify_cross_section_update()

    def set_maaru_samples(self, rows):
        self._maaru_samples = list(rows)
        self._refresh_samples()
        self.refresh_profile_filters()
        self._notify_cross_section_update()

    def set_maaru_overview(self, row):
        self._maaru_overview = dict(row or {})
        identifier = str(self._maaru_overview.get("id") or "").strip()
        for current in range(self.overview.rowCount()):
            item = self.overview.item(current, 0)
            if item and item.text() == "MaRu":
                self.overview.removeRow(current)
                break
        if not identifier:
            return
        display = " — ".join(
            str(value) for value in (
                self._maaru_overview.get("number"),
                self._maaru_overview.get("nimetus"),
            ) if value not in (None, "")
        ) or identifier
        row_index = self.overview.rowCount()
        self.overview.insertRow(row_index)
        self.overview.setItem(row_index, 0, QTableWidgetItem("MaRu"))
        self._set_link_widget(
            self.overview, row_index, 1, display,
            "https://geoportaal.maaamet.ee/index.php?lang_id=1"
            f"&action=viewPA&pa_id={identifier}&fr=o&bk=1&page_id=382",
        )
        self.overview.resizeRowsToContents()

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
        self._fill_rows(
            self.veka_construction, values,
            records=[self._detail_record(row, "VEKA") for row in rows],
        )
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
        self._fill_rows(
            self.veka_pumping, values,
            records=[self._detail_record(row, "VEKA") for row in rows],
        )
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
        self._fill_rows(
            self.veka_chemistry, values,
            records=[self._detail_record(row, "VEKA") for row in rows],
        )
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
            self._overview_row_keys[target_row] = key
            self.overview.setItem(
                target_row, 1, QTableWidgetItem(_display_value(value))
            )
        self._overview_base_rows = self.overview.rowCount()
        self.overview.resizeColumnsToContents()

    def set_core(self, rows):
        self._core_rows = list(rows)
        self._refresh_core()
        self._update_profile_related_controls()
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

    def set_maaru_core(self, rows, images_by_core=None):
        self._maaru_core_rows = list(rows)
        self._maaru_core_images = {
            str(key).upper(): list(value)
            for key, value in (images_by_core or {}).items()
        }
        self._refresh_core()
        self._update_profile_related_controls()
        self._notify_cross_section_update()

    def set_sarv_core(self, rows):
        self._sarv_core_rows = list(rows)
        self._refresh_core()
        self._update_profile_related_controls()
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
        self._core_all_records = {"EGT": {}, "MARU": {}, "SARV": {}}
        parent_id = self.current_cross_section_key()
        corrected_egt = [
            (
                row,
                self.plugin.corrected_core_box("EGT", row),
            )
            for row in (
                list(self._core_rows)
                + self.plugin.local_core_boxes(
                    "EGT", self._current_detail_role, parent_id,
                )
            )
        ]
        corrected_maaru = [
            (row, self.plugin.corrected_core_box("MARU", row))
            for row in (
                list(self._maaru_core_rows)
                + self.plugin.local_core_boxes(
                    "MARU", self._current_detail_role, parent_id,
                )
            )
        ]
        prepared_sarv = []
        for row in (
            list(self._sarv_core_rows)
            + self.plugin.local_core_boxes(
                "SARV", self._current_detail_role, parent_id,
            )
        ):
            source_row = dict(row)
            source_row["_qeoloog_status"] = (
                _nested_text(row.get("storage"), self.plugin.language)
                or _nested_text(row.get("location"), self.plugin.language)
                or _nested_text(
                    row.get("_drillcore_storage"), self.plugin.language
                )
                or row.get("_drillcore_name")
            )
            source_row["_qeoloog_description"] = (
                row.get("description")
                or row.get("description_et")
                or row.get("notes")
                or row.get("markus")
                or ""
            )
            prepared_sarv.append((
                source_row,
                self.plugin.corrected_core_box("SARV", source_row),
            ))
        visible_primary_boxes = []
        visible_primary_images = {}
        if self.core_sources["EGT"].isChecked():
            visible_primary_boxes.extend(
                {**corrected, "_qeoloog_source": "EGT"}
                for _, corrected in corrected_egt
            )
            visible_primary_images.update(self._egt_core_images)
        if self.core_sources["MaRu"].isChecked():
            visible_primary_boxes.extend(
                {**corrected, "_qeoloog_source": "MaRu"}
                for _, corrected in corrected_maaru
            )
            visible_primary_images.update(self._maaru_core_images)
        self.profile.set_core_boxes(visible_primary_boxes)
        self.profile.set_core_images(visible_primary_images)
        self.profile.set_sarv_core_boxes([
            track for _, corrected in prepared_sarv
            if self.core_sources["SARV"].isChecked()
            and (track := _sarv_core_track(corrected)) is not None
        ])
        self.profile.set_options(
            core_boxes=bool(
                self.core_sources["EGT"].isChecked()
                or self.core_sources["MaRu"].isChecked()
            ),
            sarv_core_boxes=self.core_sources["SARV"].isChecked(),
        )
        for source_row, corrected in corrected_egt:
            key = core_correction_key("EGT", source_row)
            if key:
                self._core_all_records["EGT"][key] = {
                    "source": "EGT", "raw": source_row,
                    "corrected": corrected,
                }
        for source_row, corrected in corrected_maaru:
            key = core_correction_key("MARU", source_row)
            if key:
                self._core_all_records["MARU"][key] = {
                    "source": "MARU", "raw": source_row,
                    "corrected": corrected,
                }
        for source_row, corrected in prepared_sarv:
            key = core_correction_key("SARV", source_row)
            if key:
                self._core_all_records["SARV"][key] = {
                    "source": "SARV", "raw": source_row,
                    "corrected": corrected,
                }
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
                    self.plugin.decode_egt(22, "staatus", row.get("staatus")),
                    row.get("kirjeldus")
                    or row.get("tx_kirjeldus") or row.get("markus") or "",
                    "",
                    str(correction.get("updated_at") or "")[:19],
                ))
        if self.core_sources["MaRu"].isChecked():
            for source_row, row in corrected_maaru:
                urls = self._maaru_core_images.get(
                    str(source_row.get("globalid") or "").upper(), []
                )
                key = core_correction_key("MARU", source_row)
                correction = self.plugin.core_corrections.get(key, {})
                self._core_display_records[key] = {
                    "source": "MARU",
                    "raw": source_row,
                    "corrected": row,
                }
                entries.append(urls)
                description = row.get("kirjeldus") or ""
                if row.get("_qeoloog_invalid_bottom"):
                    raw_bottom = row.get("_qeoloog_invalid_bottom_raw")
                    warning = self.plugin.t("Vigane alumine sügavus")
                    if raw_bottom not in (None, ""):
                        warning += f": {_display_value(raw_bottom)} m"
                    description = " · ".join(
                        value for value in (warning, description) if value
                    )
                values.append((
                    "MaRu", row.get("kast_nr"), row.get("z_suht_ylemine"),
                    row.get("z_suht_alumine"), row.get("diameeter"),
                    row.get("staatus"), description, "",
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
                    row.get("_qeoloog_status"),
                    row.get("_qeoloog_description") or "", "",
                    str(correction.get("updated_at") or "")[:19],
                ))
        detail_records = [
            self._detail_record(
                {
                    **dict(record.get("raw") or {}),
                    **dict(record.get("corrected") or {}),
                },
                record.get("source") or "",
                22 if record.get("source") == "EGT" else None,
            )
            for record in self._core_display_records.values()
        ]
        sorting_state = self._fill_rows(
            self.core, values, restore_sorting=False,
            records=detail_records,
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
            self.core.setCellWidget(row_index, 7, label)
        self._restore_table_sorting(self.core, sorting_state)
        self.tabs.setTabText(
            2,
            f"{self.plugin.t('Puursüdamik')} "
            f"({len(self._core_display_records)})",
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
        self.core_add_button.setEnabled(self.core_edit_mode.isChecked())
        key = (
            core_correction_key(record["source"], record["raw"])
            if record else ""
        )
        self.core_reset_button.setEnabled(
            bool(enabled and key in self.plugin.core_corrections)
        )

    def _core_status_options(self, source):
        """Return current REST-backed status/storage choices for one source."""
        source = str(source or "").upper()
        if source == "EGT":
            return self.plugin.egt_options(22, "staatus")
        options = {}
        source_key = "MARU" if source == "MARU" else "SARV"
        for record in getattr(self, "_core_all_records", {}).get(source_key, {}).values():
            status = core_values(source_key, record.get("corrected")).get("status")
            if status not in (None, ""):
                options[str(status)] = str(status)
        return sorted(options.items(), key=lambda item: item[1].casefold())

    def _with_core_status_options(self, source, callback):
        """Open an editor only after refreshing the live EGT REST domain."""
        source = str(source or "").upper()
        if source != "EGT":
            callback(self._core_status_options(source))
            return
        self.core_edit_hint.setText(
            self.plugin.t("Puursüdamiku staatuste valikuid laaditakse…")
        )
        self.core_add_button.setEnabled(False)
        self.core_edit_button.setEnabled(False)

        def done():
            self._set_core_edit_mode(self.core_edit_mode.isChecked())
            callback(self._core_status_options(source))

        def failed(error):
            self._set_core_edit_mode(self.core_edit_mode.isChecked())
            QMessageBox.warning(
                self,
                self.plugin.t("Puursüdamiku staatuste laadimine ebaõnnestus"),
                str(error),
            )
            # Cached values still originated from REST and are safer than a
            # hard-coded or editable classifier.
            callback(self._core_status_options(source))

        self.plugin.refresh_egt_domain(22, done, failed)

    def _core_interval_label(self, record, values):
        number = values.get("number")
        identifier = core_correction_key(
            record.get("source"), record.get("raw")
        ).split(":", 1)[-1]
        name = str(number or identifier or "?")
        return f"{name} ({values.get('top')}–{values.get('bottom')} m)"

    def _find_pending_core_overlap(self, source, pending, added_record):
        records = dict(
            getattr(self, "_core_all_records", {}).get(source, {})
        )
        added_key = core_correction_key(source, added_record.get("raw"))
        if added_key:
            records[added_key] = added_record
        effective = {}
        for key, record in records.items():
            values = core_values(source, record.get("corrected"))
            if key in pending:
                values.update(pending[key]["values"])
            effective[key] = values
        keys = list(records)
        for index, first_key in enumerate(keys):
            for second_key in keys[index + 1:]:
                if first_key not in pending and second_key not in pending:
                    continue
                if core_intervals_overlap(
                    effective[first_key], effective[second_key]
                ):
                    return (
                        first_key, records[first_key], effective[first_key],
                        second_key, records[second_key], effective[second_key],
                    )
        return None

    def _save_core_with_overlap_check(
        self, source, raw, values, is_new, status_options,
    ):
        """Resolve every affected box overlap before persisting any change."""
        key = core_correction_key(source, raw)
        corrected = self.plugin.corrected_core_box(source, raw)
        if is_new:
            corrected = dict(raw)
            corrected["_qeoloog_local"] = True
        current = {"source": source, "raw": raw, "corrected": corrected}
        pending = {
            key: {"record": current, "values": dict(values), "is_new": is_new}
        }
        while True:
            overlap = self._find_pending_core_overlap(source, pending, current)
            if not overlap:
                break
            first_key, first_record, first_values, second_key, second_record, second_values = overlap
            conflict_key = second_key if first_key in pending else first_key
            conflict_record = second_record if conflict_key == second_key else first_record
            conflict_values = second_values if conflict_key == second_key else first_values
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle(self.plugin.t("Kastide sügavused kattuvad"))
            box.setText(
                self.plugin.t("Puursüdamiku kastide sügavusvahemikud kattuvad:")
                + "\n"
                + self._core_interval_label(first_record, first_values)
                + "\n"
                + self._core_interval_label(second_record, second_values)
            )
            edit_button = box.addButton(
                self.plugin.t("Muuda ka kattuvat kasti…"),
                QMessageBox.ButtonRole.ActionRole,
            )
            box.addButton(
                self.plugin.t("Katkesta"), QMessageBox.ButtonRole.RejectRole
            )
            box.exec()
            if box.clickedButton() is not edit_button:
                return False
            dialog = CoreCorrectionDialog(
                self.plugin, source, conflict_key.split(":", 1)[-1],
                conflict_values,
                is_new=bool(
                    conflict_record.get("corrected", {}).get("_qeoloog_local")
                ),
                status_options=status_options, parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False
            pending[conflict_key] = {
                "record": conflict_record,
                "values": dialog.values(),
                "is_new": bool(
                    conflict_record.get("corrected", {}).get("_qeoloog_local")
                ),
            }
        context = {
            "parent_role": self._current_detail_role,
            "parent_id": self.current_cross_section_key(),
            "parent_name": self._current_detail_name,
        }
        for change in pending.values():
            self.plugin.save_core_box_correction(
                source, change["record"]["raw"], change["values"], context,
                is_new=change["is_new"],
            )
        self._refresh_core()
        self._notify_cross_section_update()
        return True

    def _add_core_box(self):
        if not self.core_edit_mode.isChecked():
            return
        choices = [
            source for source, checkbox in self.core_sources.items()
            if checkbox.isChecked()
        ]
        if len(choices) > 1:
            labels = [
                "MaRu" if source == "MARU" else source
                for source in choices
            ]
            selected, accepted = QInputDialog.getItem(
                self,
                self.plugin.t("Lisa puursüdamiku kast"),
                self.plugin.t("Allikas"), labels, 0, False,
            )
            if not accepted:
                return
            source = choices[labels.index(selected)]
        elif choices:
            source = choices[0]
        else:
            source = (
                "SARV" if self._current_detail_role == "sarv_drillcores"
                else "MARU" if self._current_detail_role == "maaru_cores"
                else "EGT"
            )
        source = str(source).upper()
        record_id = (
            new_guid() if source == "EGT"
            else "local-" + new_guid().strip("{}").lower()
        )
        raw = (
            {"globalid": record_id} if source in {"EGT", "MARU"}
            else {"id": record_id}
        )
        def open_editor(status_options):
            dialog = CoreCorrectionDialog(
                self.plugin, source, record_id,
                core_values(source, raw), is_new=True,
                status_options=status_options, parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self._save_core_with_overlap_check(
                source, raw, dialog.values(), True, status_options,
            )

        self._with_core_status_options(source, open_editor)

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
        source = record["source"]

        def open_editor(status_options):
            dialog = CoreCorrectionDialog(
                self.plugin, source, key.split(":", 1)[-1],
                core_values(source, record["corrected"]),
                is_new=bool(record.get("corrected", {}).get("_qeoloog_local")),
                status_options=status_options, parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self._save_core_with_overlap_check(
                source, record["raw"], dialog.values(),
                bool(record.get("corrected", {}).get("_qeoloog_local")),
                status_options,
            )

        self._with_core_status_options(source, open_editor)

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
        records = []
        gea_id = self._current_detail_attributes.get("gea_id")
        object_path = (
            "vaatluspunkt" if self._current_detail_role == "observations"
            else "puurauk"
        )
        egt_location = (
            _link_cell(
                self._current_detail_name or gea_id,
                f"https://gis.egt.ee/auk/{object_path}/{gea_id}/vaade",
            )
            if gea_id not in (None, "") else ""
        )
        if self.sample_sources["EGT"].isChecked():
            for row in self._egt_samples:
                values.append((
                    "EGT",
                    row.get("proov_tahis_alg"),
                    self.plugin.decode_egt(18, "proov_tyyp", row.get("proov_tyyp")),
                    row.get("z_suht_ylemine"),
                    row.get("z_suht_alumine"),
                    self.plugin.decode_egt(18, "eesmark", row.get("eesmark")),
                    egt_location,
                    self.plugin.decode_egt(18, "staatus", row.get("staatus")),
                ))
                records.append(self._detail_record(row, "EGT", 18))
        if self.sample_sources["MaRu"].isChecked():
            for row in self._maaru_samples:
                flags = ", ".join(
                    label for key, label in (
                        ("ohik", self.plugin.t("Õhik")),
                        ("keemia", self.plugin.t("Keemiline analüüs")),
                        ("mineral", self.plugin.t("Mineraloogia")),
                        ("granul", self.plugin.t("Granulomeetria")),
                    ) if str(row.get(key) or "") not in {"", "0"}
                )
                values.append((
                    "MaRu", row.get("number") or row.get("kasipala_id"),
                    row.get("kivim"), row.get("z_suht_ylemine"),
                    row.get("z_suht_alumine"), row.get("strat"),
                    _link_cell(
                        row.get("_location_label") or row.get("pa_id"),
                        row.get("_location_url"),
                    ) if row.get("_location_url") else "",
                    flags or row.get("hoidla"),
                ))
                records.append(self._detail_record(row, "MaRu"))
        if self.sample_sources["SARV"].isChecked():
            for row in self._sarv_samples:
                location_value = row.get("locality") or row.get("site")
                location_id = (
                    location_value.get("id")
                    if isinstance(location_value, dict) else location_value
                )
                location_name = (
                    _nested_text(location_value, self.plugin.language)
                    if isinstance(location_value, dict) else location_id
                )
                location_path = (
                    "locality" if row.get("locality") else "site"
                )
                location_cell = (
                    _link_cell(
                        location_name or location_id,
                        f"https://geoloogia.info/{location_path}/{location_id}",
                    )
                    if location_id not in (None, "") else ""
                )
                values.append((
                    "SARV",
                    _link_cell(
                        row.get("number") or row.get("id"),
                        f"https://geoloogia.info/sample/{row.get('id')}",
                    ),
                    _nested_text(row.get("type"), self.plugin.language),
                    row.get("depth"),
                    _sarv_interval_end(row),
                    _nested_text(row.get("purpose"), self.plugin.language),
                    location_cell,
                    _nested_text(row.get("database"), self.plugin.language),
                ))
                records.append(self._detail_record(row, "SARV"))
        self._fill_rows(self.samples, values, records=records)
        self.tabs.setTabText(
            3,
            f"{self.plugin.t('Proovid')} "
            f"({len(self._egt_samples) + len(self._maaru_samples) + len(self._sarv_samples)})",
        )
        self.refresh_profile_filters()

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
        records = []
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
                records.append(self._detail_record(
                    {**row, "tulemused": results}, "EGT", 3,
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
                records.append(self._detail_record(row, "SARV"))
        self._fill_rows(self.analyses, values, records=records)
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
        self._update_profile_related_controls()
        apply_filters = bool(
            self.profile_apply_filters.isChecked() and self.plugin.dock
        )
        egt_samples = list(self._egt_samples)
        maaru_samples = list(self._maaru_samples)
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

        profile_samples = (
            egt_samples if self.sample_sources["EGT"].isChecked() else []
        )
        if self.sample_sources["MaRu"].isChecked():
            profile_samples += maaru_samples
        self.profile.set_samples(profile_samples)
        self.profile.set_options(samples=bool(profile_samples))
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
        self._notify_cross_section_update()

    def _refresh_specimens(self):
        values = []
        records = []
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
            records = [
                self._detail_record(row, "SARV")
                for row in self._sarv_specimens
            ]
        self._fill_rows(self.specimens, values, records=records)
        self.tabs.setTabText(
            5,
            f"{self.plugin.t('Eksemplarid')} ({len(self._sarv_specimens)})",
        )

    def set_attachments(self, rows):
        self._portal_attachments = []
        self._egt_attachments = list(rows)
        self._refresh_attachments()

    def set_maaru_attachments(self, rows):
        self._maaru_attachments = list(rows)
        self._refresh_attachments()

    def set_sarv_attachments(self, rows):
        self._sarv_attachments = list(rows)
        self._refresh_attachments()

    @staticmethod
    def _attachment_depth(row):
        start = next((
            row.get(key) for key in (
                "depth", "sygavus", "z_suht_ylemine", "algus",
            ) if row.get(key) not in (None, "")
        ), "")
        end = next((
            row.get(key) for key in (
                "depth_end", "z_suht_alumine", "lõpp",
            ) if row.get(key) not in (None, "")
        ), "")
        return _depth_text(start, end) if start not in (None, "") else ""

    def _refresh_attachments(self):
        values = []
        records = []
        if self.attachment_sources["EGT"].isChecked():
            for row in self._egt_attachments:
                link = row.get("link") or ""
                url = _attachment_url(link)
                record = self._detail_record(row, "EGT", 21)
                record["_qeoloog_url"] = url
                values.append((
                    "EGT", self.plugin.decode_egt(
                        15, "manus_tyyp", row.get("manus_tyyp")
                    ),
                    row.get("nimetus") or str(link).split("/")[-1],
                    self._attachment_depth(row),
                    (
                        row.get("z_abs")
                        if row.get("z_abs") not in (None, "")
                        else row.get("absolute_z")
                    ),
                    row.get("indeks") or row.get("stratigraafia_indeks"),
                    row.get("litoloogia"),
                    _link_cell(self.plugin.t("Ava"), url),
                ))
                records.append(record)
        if self.attachment_sources["MaRu"].isChecked():
            for row in self._maaru_attachments:
                if (
                    row.get("kind") == "core_photo"
                    and not self.show_maaru_core_attachments.isChecked()
                ):
                    continue
                record = self._detail_record(row, "MaRu")
                record["_qeoloog_url"] = row.get("url")
                values.append((
                    "MaRu", row.get("type"), row.get("name"),
                    self._attachment_depth(row), row.get("absolute_z"),
                    row.get("index") or row.get("strat"),
                    row.get("lithology") or row.get("kivim"),
                    _link_cell(self.plugin.t("Ava"), row.get("url")),
                ))
                records.append(record)
        if self.attachment_sources["SARV"].isChecked():
            for row in self._sarv_attachments:
                url = _sarv_attachment_url(
                    row.get("original_file_url")
                    or row.get("preview_large_url") or row.get("url")
                )
                record = self._detail_record(row, "SARV")
                record["_qeoloog_url"] = url
                values.append((
                    "SARV", _nested_text(row.get("type"), self.plugin.language),
                    row.get("filename") or row.get("name") or row.get("id"),
                    self._attachment_depth(row), row.get("absolute_z"),
                    row.get("stratigraphy") or row.get("index"),
                    row.get("lithology"),
                    _link_cell(self.plugin.t("Ava"), url),
                ))
                records.append(record)
        portal_label = self.plugin.t("EGT Portal")
        if self.attachment_sources[portal_label].isChecked():
            for row in self._portal_attachments:
                record = self._detail_record(row, portal_label)
                record["_qeoloog_portal_attachment"] = True
                values.append((
                    portal_label,
                    row.get("contentType") or self.plugin.t("Fail"),
                    row.get("name") or row.get("id"), "", "", "", "",
                    self.plugin.t("Ava"),
                ))
                records.append(record)
        self._fill_rows(
            self.attachments, values,
            records=records,
        )
        self.tabs.setTabText(
            6, f"{self.plugin.t('Manused')} ({len(values)})"
        )

    def set_portal_attachments(self, rows):
        """Show authenticated ArcGIS feature attachments in the usual tab."""
        self._portal_attachments = list(rows or ())
        self._egt_attachments = []
        self._maaru_attachments = []
        self._sarv_attachments = []
        self._refresh_attachments()

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
        detail_records = []
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
                detail_records.append(self._detail_record(
                    {**relation, "reference": reference}, "SARV",
                ))
        self._fill_rows(
            self.literature, values, records=detail_records,
        )
        self.tabs.setTabText(7, f"{self.plugin.t('Kirjandus')} ({len(unique)})")

    def _open_attachment(self, row, column):
        first = self.attachments.item(row, 0)
        record = (
            first.data(DETAIL_RECORD_ROLE) if first is not None else None
        )
        if isinstance(record, dict) and record.get(
            "_qeoloog_portal_attachment"
        ):
            self.plugin.open_portal_attachment(record)
            return
        url = record.get("_qeoloog_url") if isinstance(record, dict) else ""
        if url:
            QDesktopServices.openUrl(QUrl(str(url)))

    def _fill_pairs(self, table, attributes, role):
        rows = [
            (key, value) for key, value in attributes.items()
            if value not in (None, "")
            and not str(key).startswith(("_qeoloog_", "vk_"))
        ]
        # Dropping all rows also removes cell widgets left by the previous object.
        table.setRowCount(0)
        table.setRowCount(len(rows))
        if table is self.overview:
            self._overview_row_keys = {
                row_index: key
                for row_index, (key, _value) in enumerate(rows)
            }
        object_path = "puurauk" if role == "boreholes" else "vaatluspunkt"
        for row_index, (key, value) in enumerate(rows):
            table.setItem(
                row_index, 0,
                QTableWidgetItem(field_label(str(key), self.plugin.language)),
            )
            key_lower = key.lower()
            display = self._detail_code_label(key, value)
            url = ""
            if key_lower == "gea_id":
                url = f"https://gis.egt.ee/auk/{object_path}/{display}/vaade"
            elif key_lower in {"id", "maaru_id"} and role == "maaru_cores":
                url = (
                    "https://geoportaal.maaamet.ee/index.php?lang_id=1"
                    f"&action=viewPA&pa_id={display}&fr=o&bk=1&page_id=382"
                )
            elif key_lower == "sarv_loc_id" and role == "maaru_cores":
                try:
                    valid_locality_id = int(str(display)) > 0
                except (TypeError, ValueError):
                    valid_locality_id = False
                if valid_locality_id:
                    url = f"https://geoloogia.info/locality/{display}"
            elif (
                key_lower in {"viit geoportaali", "viit_geoportaali"}
                and str(display).startswith(("https://", "http://"))
            ):
                url = str(display).replace(
                    "http://geoportaal.maaamet.ee/",
                    "https://geoportaal.maaamet.ee/",
                )
            elif key_lower == "kkr_kood" and role == "veka_boreholes":
                url = f"https://veka.eelis.ee/puurauk/{display}"
            elif key_lower == "kande_alus_nr":
                url = f"https://fond.egt.ee/fond/egf/{display}"
            elif key_lower == "egf_nr" and role == "mineral_deposits":
                url = f"https://fond.egt.ee/fond/egf/{display}"
            elif (
                key_lower == "egf_id"
                and role in {
                    "engineering_geology_points", "archive_survey_areas",
                }
            ):
                url = f"https://fond.egt.ee/fond/egf/{display}"
            elif (
                key_lower == "pysilink"
                and role in {
                    "engineering_geology_points", "archive_survey_areas",
                }
                and str(display).startswith(("https://", "http://"))
            ):
                url = str(display)
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
            if key_lower == "kande_alus_nr" and report_number(display):
                self._set_archive_report_widget(table, row_index, display, url)
            elif url:
                self._set_link_widget(table, row_index, 1, display, url)
            else:
                table.setItem(row_index, 1, QTableWidgetItem(display))
        table.resizeColumnsToContents()
        if table is self.overview:
            header = table.horizontalHeader()
            header.setSectionResizeMode(
                0, QHeaderView.ResizeMode.ResizeToContents,
            )
            header.setSectionResizeMode(
                1, QHeaderView.ResizeMode.Stretch,
            )
            table.resizeRowsToContents()

    def _set_archive_report_widget(self, table, row, display, url):
        number = report_number(display)
        host = QWidget()
        host.setProperty("qeoloog_display_text", str(display))
        host.setToolTip(url)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(4, 0, 4, 0)
        link = QLabel(f'<a href="{html_escape(url)}">{html_escape(str(display))}</a>')
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(link)
        for kind, text, tooltip in (
            ("area", "Aruande ala", "Kuva või eemalda selle fondiaruande ruumikuju. Filter töötab sellest sõltumatult."),
            ("filter", "PA filter", "Kuva ainult fondiaruande ala sisse jäävad avalikud EGT puuraugud. Teised filtrid säilivad."),
            ("clear", "×", "Eemalda fondiala filter; säilita teised filtrid ja ruumikujud."),
        ):
            button = QToolButton(host)
            button.setText(self.plugin.t(text))
            button.setToolTip(self.plugin.t(tooltip))
            button.setProperty("qeoloog_archive_report", number)
            button.setProperty("qeoloog_archive_action", kind)
            button.setCheckable(kind != "clear")
            if kind == "area":
                button.clicked.connect(lambda checked, n=number: self.plugin.set_archive_report_visible(n, checked))
            elif kind == "filter":
                button.clicked.connect(lambda checked, n=number: self.plugin.set_archive_report_filter(n, checked))
            else:
                button.clicked.connect(lambda _checked: self.plugin.clear_archive_report_filter())
            layout.addWidget(button)
        layout.addStretch(1)
        table.setCellWidget(row, 1, host)
        self.refresh_archive_report_controls()

    def refresh_archive_report_controls(self):
        for button in self.overview.findChildren(QToolButton):
            number = button.property("qeoloog_archive_report")
            if not number:
                continue
            kind = button.property("qeoloog_archive_action")
            state = self.plugin.archive_report_status(str(number))
            button.blockSignals(True)
            if kind == "clear":
                button.setEnabled(state["any_filter"])
            else:
                button.setChecked(state[kind])
            button.blockSignals(False)

    def _refresh_overview_value_labels(self):
        """Decode loaded overview codes after Faktika metadata becomes ready."""
        for row, key in self._overview_row_keys.items():
            if row >= self.overview.rowCount():
                continue
            if self.overview.cellWidget(row, 1) is not None:
                continue
            item = self.overview.item(row, 1)
            if item is not None and key in self._current_detail_attributes:
                item.setText(self._detail_code_label(
                    key, self._current_detail_attributes.get(key)
                ))
        self.overview.resizeRowsToContents()

    def _detail_code_label(self, key, value):
        """Show human labels for the compact Faktika/EGT classifier codes."""
        name = str(key or "").casefold()
        if self._current_detail_role == "field_mapping":
            metadata_getter = getattr(
                self.plugin, "portal_bundle_metadata", None
            )
            metadata = (
                metadata_getter("field_mapping")
                if callable(metadata_getter) else {}
            ).get(0, {})
            subtype = self._current_detail_attributes.get("objekti_tyyp")
            if name in {"objekti_tyyp", "object_type"}:
                return _display_value(subtype_label(metadata, value))
            decoded = coded_value_label(
                metadata, str(key), value, subtype,
            )
            return _display_value(decoded)
        if name in {"objekti_tyyp", "object_type"}:
            try:
                code = int(value)
            except (TypeError, ValueError):
                code = None
            if code in OBJECT_TYPES:
                return self.plugin.t(OBJECT_TYPES[code])
        if name in {"yksus_kood", "klassif_yksus_kood"}:
            try:
                code = int(value)
            except (TypeError, ValueError):
                code = None
            if code in UNIT_TYPES:
                return self.plugin.t(UNIT_TYPES[code])
            text = str(value or "").strip().casefold()
            for unit_code, label in UNIT_TYPES.items():
                if text == str(label).casefold():
                    return self.plugin.t(label)
        metadata_getter = getattr(self.plugin, "faktika_metadata", None)
        metadata = (
            metadata_getter() if callable(metadata_getter)
            else getattr(self.plugin, "_faktika_metadata", {}) or {}
        ).get(1, {})
        subtype = self._current_detail_attributes.get("objekti_tyyp")
        decoded = coded_value_label(metadata, str(key), value, subtype)
        if decoded != value:
            return self.plugin.t(str(decoded))
        return _display_value(value)

    @staticmethod
    def _detail_record(row, source, table_id=None):
        """Copy a source row and annotate it for the read-only field viewer."""
        record = dict(row or {})
        record["_qeoloog_source"] = str(source or "")
        if table_id is not None:
            record["_qeoloog_table_id"] = table_id
        return record

    @staticmethod
    def _set_link_widget(table, row, column, text, url):
        safe_text = html_escape(_display_value(text))
        safe_url = html_escape(str(url))
        link = QLabel(f'<a href="{safe_url}">{safe_text}</a>')
        link.setOpenExternalLinks(True)
        link.setWordWrap(True)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        link.setContentsMargins(4, 0, 4, 0)
        link.setToolTip(str(url))
        link.setProperty("qeoloog_display_text", _display_value(text))
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
    def _fill_rows(
        cls, table, rows, restore_sorting=True, records=None,
    ):
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
                    link.setProperty("qeoloog_display_text", _display_value(raw_text))
                    table.setCellWidget(row_index, column, link)
                else:
                    table.setItem(
                        row_index, column, SortableTableItem(value)
                    )
            if records is not None and row_index < len(records):
                first = table.item(row_index, 0)
                if first is not None:
                    first.setData(DETAIL_RECORD_ROLE, records[row_index])
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
        self.maaru_filters = MaaruFilterWidget(plugin)
        self.veka = VekaWidget(plugin)
        self.search = SearchWidget(plugin)
        self.search_filters = SearchAndFiltersWidget(
            plugin, self.search, self.filters, self.sarv_filters,
            self.maaru_filters,
        )
        self.export = ExportWidget(plugin)
        self.cross_section_window = CrossSectionWindow(plugin, parent)
        self.cross_sections = self.cross_section_window.content
        self.cross_section_launcher = CrossSectionLauncher(
            plugin, self.cross_section_window
        )
        self.details = DetailWidget(plugin)
        self.local_objects = LocalObjectsWidget(plugin)
        self.etl_import = EtlImportWidget(plugin)
        self.cross_sections.modelChanged.connect(self.details.sync_cross_section_button)
        self.tabs.addTab(self.layers, plugin.t("Kihid"))
        self.filter_page = self.search_filters
        self.sarv_filter_page = self.search_filters
        self.search_page = self.search_filters
        self.tabs.addTab(
            self.search_filters, plugin.t("Otsing ja filtrid")
        )
        self.veka_page = self._scroll(self.veka)
        self.tabs.addTab(self.veka_page, plugin.t("VEKA"))
        self.export_page = self._scroll(self.export)
        self.tabs.addTab(self.export_page, plugin.t("Ekspordi"))
        self.tabs.addTab(
            self.cross_section_launcher, plugin.t("Läbilõiked")
        )
        self.tabs.addTab(self.details, plugin.t("Objekti andmed"))
        self.tabs.addTab(self.local_objects, plugin.t("Kohalikud andmed"))
        self.tabs.addTab(self.etl_import, plugin.t("Impordi"))
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

    def show_search_filters(self, section="search"):
        self.search_filters.show_section(section)
        self.tabs.setCurrentWidget(self.search_filters)
        self.show()
        self.raise_()

    def show_cross_sections(self):
        self.cross_section_window.show()
        self.cross_section_window.raise_()
        self.cross_section_window.activateWindow()

    def close_cross_sections(self):
        if self.cross_section_window:
            cancel = self.cross_section_window.content._cancel_section_pick
            if cancel:
                cancel()
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
        try:
            return datetime.fromtimestamp(value / 1000).strftime("%Y-%m-%d")
        except (OSError, OverflowError, ValueError):
            return value
    return value


def _display_value(value):
    # Numeric magnitude is not date metadata: IDs and measurements must stay
    # numeric. Date columns call _date_value explicitly.
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
    first = upper.replace("–", "-")
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
        (("S2-3", "S2–3"), "#b9e4c9"),
        (("S2",), "#a6dcbb"),
        (("S1-2", "S1–2"), "#a6dcbb"),
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
        result = str(index)
        if (
            unit.get("_qeoloog_unpenetrated")
            and result and not result.endswith("+")
        ):
            result += "+"
        return result
    # EGT stores the desired stratigraphic range in lower-to-upper display order.
    lower = _valid_unit_value(unit.get("liityksus_indeks_alumine"))
    upper = _valid_unit_value(unit.get("liityksus_indeks_ylemine"))
    if lower and upper and lower != upper:
        result = f"{lower}-{upper}"
    else:
        result = lower or upper or str(index)
    if (
        unit.get("_qeoloog_unpenetrated")
        and result and not result.endswith("+")
    ):
        result += "+"
    return result


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
