"""Qeoloog - configurable Estonian geoscience layers and borehole explorer."""

from pathlib import Path
from unicodedata import normalize
from urllib.parse import quote

from qgis.PyQt.QtCore import Qt, QTimer, QVariant
from qgis.PyQt.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import QMenu, QToolButton
from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsDataSourceUri,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsExpressionContextUtils,
    QgsGeometry,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsPointXY,
    QgsRasterLayer,
    QgsRectangle,
    QgsRendererCategory,
    QgsRuleBasedRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsHighlight

from .dock import QeoloogDock
from .i18n import GROUP_LABELS, translate
from .identify import EgtIdentifyTool
from .models import DEFAULT_GROUP_STATE, GROUPS, PluginSettings
from .network import NetworkClient


class QeoloogPlugin:
    """Manage layer shortcuts, menus, filtering and EGT object data."""

    MENU = "&Qeoloog"
    SOURCE_PROPERTY = "qeoloog/source_id"
    LEGACY_SOURCE_PROPERTY = "eesti_wms_nupud/source_id"
    ROLE_PROPERTY = "qeoloog/role"
    LEGACY_ROLE_PROPERTY = "eesti_wms_nupud/role"
    CATEGORY_COLORS = {1: "#d7bd72", 2: "#7796c6", 3: "#b56b6b", 997: "#8f8f8f"}
    SARV_SAMPLE_PURPOSES = {
        0: ("määratlemata", "unspecified"),
        1: ("happeresistentsed mikrofossiilid", "acid-resistant microfossils"),
        2: ("karbonaatsed mikrofossiilid", "carbonate microfossils"),
        3: ("makrofossiilid", "macrofossils"),
        4: ("litoloogia", "lithology"),
        5: ("geokeemia", "geochemistry"),
        6: ("mineraloogia", "mineralogy"),
        7: ("kombineeritud", "combined"),
        8: ("mulla geokeemia", "soil geochemistry"),
        9: ("geokeemia ja petrofüüsika", "geochemistry and petrophysics"),
        10: ("stabiilsed isotoobid", "stable isotopes"),
        11: ("geokeemia ja mineraloogia", "geochemistry and mineralogy"),
        12: ("põhjavee geokeemia", "groundwater geochemistry"),
        13: ("mikrofossiilid", "microfossils"),
        14: ("geotehnika", "geotechnics"),
        15: ("mikropaleontoloogia ja geokeemia", "micropaleontology and geochemistry"),
        16: ("ehitusmaterjali uuringud", "building material testing"),
    }
    AK_CORRECTED_EXTENT = QgsRectangle(369548.1875, 6380032.5, 739208.1875, 6653113.0)

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self.definitions = PluginSettings.load_layers()
        self.toggle_mode = PluginSettings.load_toggle_mode()
        self.language = PluginSettings.load_language()
        self.group_enabled = PluginSettings.load_groups()
        self.network = NetworkClient()
        self.toolbar = None
        self.actions = []
        self.layer_actions = []
        self.dropdown_actions = {}
        self.active_dropdown_actions = {}
        self.utility_separator = None
        self.configure_action = None
        self.identify_action = None
        self.extra_menu = None
        self.extra_menu_action = None
        self.lk_button = None
        self.dock = None
        self.identify_tool = None
        self.previous_map_tool = None
        self.selection_highlight = None
        self._changing_map_tool = False
        self._detail_token = 0
        self._detail_warning_token = None
        self.related_index = {}
        self.related_index_loading = False
        self.egt_domains = {}
        self.egt_domain_options = {}
        self.egt_filter_rows = {"samples": [], "analyses": []}
        self._egt_catalog_loading = False
        self._egt_result_filter_cache = {}
        self._egt_result_filter_loading = set()
        self._sarv_points_loading = False
        self._sarv_point_cache = None
        self._sarv_point_waiters = []
        self.sarv_analysis_options = []
        self.sarv_sample_type_options = []
        self._sarv_filter_generation = 0
        self.sarv_matches = PluginSettings.load_sarv_matches()

    def t(self, text):
        return translate(text, self.language)

    def decode_egt(self, table_id, field, value):
        """Return an official EGT domain label while preserving unknown values."""
        if value in (None, ""):
            return ""
        return self.egt_domains.get(
            (int(table_id), str(field)), {}
        ).get(str(value), str(value))

    def egt_options(self, table_id, field):
        return list(self.egt_domain_options.get((int(table_id), str(field)), []))

    def sarv_purpose_options(self):
        language_index = 1 if self.language == "en" else 0
        return [
            (str(code), labels[language_index])
            for code, labels in self.SARV_SAMPLE_PURPOSES.items()
        ]

    def _load_egt_domains(self):
        """Load official coded-value domains used by details and filters."""
        pending = {18, 3, 4}

        def parse_domain(domain):
            values = {}
            if not isinstance(domain, dict):
                return values
            for item in domain.get("codedValues", []):
                code = item.get("code")
                name = item.get("name")
                if code not in (None, "") and name not in (None, ""):
                    values[str(code)] = str(name)
            return values

        def loaded(table_id):
            def handler(payload):
                found = {}
                for field in payload.get("fields", []):
                    values = parse_domain(field.get("domain"))
                    if values:
                        found.setdefault(field.get("name"), {}).update(values)
                for subtype in payload.get("types", []):
                    for field_name, domain in (subtype.get("domains") or {}).items():
                        values = parse_domain(domain)
                        if values:
                            found.setdefault(field_name, {}).update(values)
                for field_name, values in found.items():
                    key = (table_id, field_name)
                    self.egt_domains[key] = values
                    self.egt_domain_options[key] = sorted(
                        values.items(), key=lambda item: item[1].casefold()
                    )
                pending.discard(table_id)
                if not pending and self.dock:
                    self.dock.filters.reload_domain_options()
                    self.dock.search.reload_domain_options()
                    self.dock.details.refresh_decoded_values()
            return handler

        def failed(table_id):
            def handler(error):
                pending.discard(table_id)
                self.warning(
                    (f"Could not load EGT code descriptions (table {table_id}): {error}"
                     if self.language == "en" else
                     f"EGT koodikirjelduste laadimine ebaõnnestus (tabel {table_id}): {error}")
                )
            return handler

        for table_id in tuple(pending):
            self.network.query_auq_metadata(
                table_id, loaded(table_id), failed(table_id)
            )

    def _load_sarv_filter_options(self):
        def refresh():
            if self.dock:
                self.dock.sarv_filters.reload_options()
                self.dock.search.reload_domain_options()

        def methods_loaded(rows):
            options = []
            for row in rows:
                identifier = row.get("id")
                if identifier in (None, ""):
                    continue
                label = (
                    row.get("name_en") if self.language == "en"
                    else row.get("name")
                ) or row.get("name") or identifier
                options.append((str(identifier), str(label)))
            self.sarv_analysis_options = sorted(
                options, key=lambda item: item[1].casefold()
            )
            refresh()

        def types_loaded(rows):
            values = sorted({
                str(row.get("type")).strip()
                for row in rows if row.get("type") not in (None, "")
            }, key=str.casefold)
            self.sarv_sample_type_options = [(value, value) for value in values]
            refresh()

        def ignored(error):
            return None

        self.network.query_sarv_all(
            "analysis-methods", ("id", "name", "name_en"),
            methods_loaded, ignored, limit=1000,
        )
        self.network.query_sarv_pages(
            "samples", {"type__isnull": "false"}, ("id", "type"),
            types_loaded, ignored, limit=5000,
        )

    def display_name(self, definition):
        if self.language == "en" and definition.name_en:
            return definition.name_en
        return definition.name

    def group_name(self, group):
        return self.t(GROUP_LABELS.get(group, group))

    def initGui(self):
        self.toolbar = self.iface.addToolBar("Qeoloog")
        self.toolbar.setObjectName("Qeoloog_Toolbar")
        self._create_dock()
        self.identify_tool = EgtIdentifyTool(self.iface.mapCanvas(), self)
        project = QgsProject.instance()
        project.layersAdded.connect(self._project_layers_changed)
        project.layersRemoved.connect(self._project_layers_changed)
        self._build_actions()
        self._load_egt_domains()
        self._load_sarv_filter_options()
        QTimer.singleShot(0, self._refresh_loaded_plugin_layers)
        QTimer.singleShot(0, self.apply_egt_filters)

    def _create_dock(self, tab_index=0, visible=False):
        self.dock = QeoloogDock(self, self.iface.mainWindow())
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.tabs.setCurrentIndex(max(0, min(tab_index, self.dock.tabs.count() - 1)))
        if visible:
            self.dock.show()
        else:
            self.dock.hide()

    def unload(self):
        self._detail_token += 1
        self._clear_highlight()
        project = QgsProject.instance()
        for signal in (project.layersAdded, project.layersRemoved):
            try:
                signal.disconnect(self._project_layers_changed)
            except (TypeError, RuntimeError):
                pass
        if self.identify_tool and self.iface.mapCanvas().mapTool() is self.identify_tool:
            self._changing_map_tool = True
            self.iface.mapCanvas().unsetMapTool(self.identify_tool)
            self._changing_map_tool = False
        self._clear_actions()
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.toolbar:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        self.identify_tool = None

    # ---- Toolbar, additional-layer menu and configuration -------------------------

    def _build_actions(self):
        identify_was_active = bool(
            self.identify_tool and self.iface.mapCanvas().mapTool() is self.identify_tool
        )
        self._clear_actions()
        for definition in self.definitions:
            if definition.placement != "toolbar":
                continue
            action = QAction(
                self._code_icon(
                    definition.code, definition.color,
                    emphasized=definition.role == "boreholes",
                ),
                definition.code,
                self.iface.mainWindow(),
            )
            action.setObjectName(f"Qeoloog_{definition.code}")
            action.setToolTip(f"{self.t('Laadi')} {self.display_name(definition)}")
            action.setStatusTip(action.toolTip())
            action.triggered.connect(lambda checked=False, item=definition: self.add_layer(item))
            self._register_action(action)
            self.layer_actions.append(action)

        self._build_extra_menu()
        if self.toolbar:
            self.utility_separator = self.toolbar.addSeparator()
        self.identify_action = QAction(
            self._code_icon("i", "#4c6678"), self.t("Objekti andmed"), self.iface.mainWindow()
        )
        self.identify_action.setCheckable(True)
        self.identify_action.setToolTip(
            self.t("Klõpsa EGT või SARV punktil ja ava seotud andmed")
        )
        self.identify_action.toggled.connect(self.set_identify_active)
        self._register_action(self.identify_action)
        if identify_was_active:
            self._sync_identify_controls(True)

        self.configure_action = QAction(
            self._code_icon("⚙", "#555f69"), self.t("Seadista Qeoloogi"), self.iface.mainWindow()
        )
        self.configure_action.setToolTip(
            self.t("Lisa, muuda või eemalda WMS/WFS/SARV kihte")
        )
        self.configure_action.triggered.connect(self.show_configuration)
        self._register_action(self.configure_action)
        self.sync_dropdown_checks()

    def _build_extra_menu(self):
        parent = self.iface.mainWindow()
        self.extra_menu = QMenu(self.t("Lisakihid"), parent)
        for group in GROUPS:
            definitions = [
                item
                for item in self.definitions
                if item.placement == "dropdown" and item.home_group == group
            ]
            if not self.group_enabled.get(group, True) or not definitions:
                continue
            submenu = self.extra_menu.addMenu(self.group_name(group))
            for definition in definitions:
                action = submenu.addAction(
                    self._code_icon(
                        definition.code, definition.color,
                        emphasized=definition.role == "boreholes",
                    ),
                    self.display_name(definition),
                )
                action.setCheckable(True)
                action.setToolTip(f"{definition.protocol}: {definition.layer_name}")
                action.toggled.connect(
                    lambda checked, item=definition: self.set_layer_active(item, checked)
                )
                self.dropdown_actions[self._source_id(definition)] = action
        self.extra_menu.aboutToShow.connect(self.sync_dropdown_checks)
        self.extra_menu_action = self.extra_menu.menuAction()
        self.iface.addPluginToMenu(self.MENU, self.extra_menu_action)
        if self.toolbar:
            self.lk_button = QToolButton(self.toolbar)
            self.lk_button.setObjectName("Qeoloog_LK")
            self.lk_button.setIcon(self._code_icon("LK", "#3f6672"))
            self.lk_button.setToolTip(self.t("Lisakihid"))
            self.lk_button.setMenu(self.extra_menu)
            self.lk_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.toolbar.addWidget(self.lk_button)

    def _register_action(self, action):
        if self.toolbar:
            self.toolbar.addAction(action)
        self.iface.addPluginToMenu(self.MENU, action)
        self.actions.append(action)

    def _clear_actions(self):
        self._clear_active_dropdown_actions()
        for action in self.actions:
            self.iface.removePluginMenu(self.MENU, action)
            action.deleteLater()
        if self.extra_menu_action:
            self.iface.removePluginMenu(self.MENU, self.extra_menu_action)
        if self.toolbar:
            self.toolbar.clear()
        if self.lk_button:
            self.lk_button.deleteLater()
        if self.extra_menu:
            self.extra_menu.deleteLater()
        self.actions.clear()
        self.layer_actions.clear()
        self.dropdown_actions.clear()
        self.utility_separator = None
        self.extra_menu = None
        self.extra_menu_action = None
        self.lk_button = None

    def show_configuration(self):
        self.dock.tabs.setCurrentWidget(self.dock.layers)
        self.dock.show()
        self.dock.raise_()

    def upsert_definition(self, index, definition):
        if 0 <= index < len(self.definitions):
            definition.home_group = self.definitions[index].home_group
            self.definitions[index] = definition
            result = index
        else:
            self.definitions.append(definition)
            result = len(self.definitions) - 1
        self._save_definitions()
        return result

    def remove_definition(self, index):
        if 0 <= index < len(self.definitions):
            del self.definitions[index]
            self._save_definitions()

    def move_definition(self, index, delta):
        target = index + delta
        if 0 <= index < len(self.definitions) and 0 <= target < len(self.definitions):
            self.definitions[index], self.definitions[target] = (
                self.definitions[target], self.definitions[index]
            )
            self._save_definitions()
            return target
        return index

    def reset_definitions(self):
        self.definitions = PluginSettings.reset_layers()
        self.group_enabled = dict(DEFAULT_GROUP_STATE)
        PluginSettings.save_groups(self.group_enabled)
        self._build_actions()

    def set_toggle_mode(self, enabled):
        self.toggle_mode = bool(enabled)
        PluginSettings.save_toggle_mode(self.toggle_mode)

    def set_group_enabled(self, group, enabled):
        if group not in GROUPS:
            return
        self.group_enabled[group] = bool(enabled)
        PluginSettings.save_groups(self.group_enabled)
        self._build_actions()

    def set_language(self, language):
        if language not in {"et", "en"} or language == self.language:
            return
        self.language = language
        PluginSettings.save_language(language)
        self._rename_loaded_layers()
        QTimer.singleShot(0, self._rebuild_localized_ui)

    def _rebuild_localized_ui(self):
        if not self.dock:
            return
        visible = self.dock.isVisible()
        tab_index = self.dock.tabs.currentIndex()
        identify_checked = bool(self.identify_action and self.identify_action.isChecked())
        self.iface.removeDockWidget(self.dock)
        self.dock.deleteLater()
        self.dock = None
        self._create_dock(tab_index, visible)
        self._build_actions()
        self._sync_identify_controls(identify_checked)

    def _rename_loaded_layers(self):
        definitions = {self._source_id(item): item for item in self.definitions}
        for layer in QgsProject.instance().mapLayers().values():
            definition = definitions.get(self._layer_source_id(layer))
            if definition:
                role = self._layer_role(layer)
                if role == "sarv_localities":
                    layer.setName(self.t("SARV - lokaliteedid"))
                elif role == "sarv_sites":
                    layer.setName(self.t("SARV - uuringupunktid"))
                elif role == "sarv_drillcores":
                    layer.setName(self.t("SARV - puursüdamikud"))
                else:
                    layer.setName(self.display_name(definition))
                if role in {
                    "sarv_localities", "sarv_sites", "sarv_drillcores",
                }:
                    node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
                    if node and node.parent():
                        node.parent().setName(self.display_name(definition))

    def _save_definitions(self):
        PluginSettings.save_layers(self.definitions)
        self._build_actions()

    @staticmethod
    def _code_icon(code, color, emphasized=False):
        pixmap = QPixmap(36, 36)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(color) if QColor(color).isValid() else QColor("#356a8a")
        if emphasized:
            painter.setPen(QPen(QColor("#ffd34d"), 3))
            painter.setBrush(fill.lighter(122))
            painter.drawRoundedRect(2, 2, 32, 32, 8, 8)
            painter.setPen(QPen(QColor("#fff4c4"), 1))
            painter.drawRoundedRect(5, 5, 26, 26, 6, 6)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(1, 1, 34, 34, 7, 7)
        painter.setPen(QColor("white"))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(13 if len(code) <= 2 else 10)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, code)
        painter.end()
        return QIcon(pixmap)

    # ---- Layer loading and drop-down check state ----------------------------------

    def _project_layers_changed(self, *args):
        QTimer.singleShot(0, self._sync_project_layers)

    def _sync_project_layers(self):
        self.sync_dropdown_checks()
        self._ensure_egt_points_on_top()

    def sync_dropdown_checks(self):
        loaded = {self._layer_source_id(layer) for layer in QgsProject.instance().mapLayers().values()}
        for source_id, action in self.dropdown_actions.items():
            action.blockSignals(True)
            action.setChecked(source_id in loaded)
            action.blockSignals(False)
        self._sync_active_dropdown_actions(loaded)

    def _sync_active_dropdown_actions(self, loaded):
        """Keep loaded LK layers promoted on the toolbar until they are removed."""
        dropdown_definitions = {
            self._source_id(definition): definition
            for definition in self.definitions
            if definition.placement == "dropdown"
        }
        desired = set(dropdown_definitions).intersection(loaded)

        for source_id in set(self.active_dropdown_actions).difference(desired):
            action = self.active_dropdown_actions.pop(source_id)
            if self.toolbar:
                self.toolbar.removeAction(action)
            action.deleteLater()

        if not self.toolbar or not self.utility_separator:
            return
        for definition in self.definitions:
            source_id = self._source_id(definition)
            if (
                definition.placement != "dropdown"
                or source_id not in desired
                or source_id in self.active_dropdown_actions
            ):
                continue
            action = QAction(
                self._code_icon(
                    definition.code, definition.color,
                    emphasized=definition.role == "boreholes",
                ),
                definition.code,
                self.iface.mainWindow(),
            )
            action.setObjectName(f"Qeoloog_active_{definition.code}")
            action.setCheckable(True)
            action.setChecked(True)
            action.setToolTip(f"{self.display_name(definition)} — {self.t('Eemalda')}")
            action.setStatusTip(action.toolTip())
            action.triggered.connect(
                lambda checked=False, item=definition: self.set_layer_active(item, False)
            )
            self.toolbar.insertAction(self.utility_separator, action)
            self.active_dropdown_actions[source_id] = action

    def _clear_active_dropdown_actions(self):
        for action in self.active_dropdown_actions.values():
            if self.toolbar:
                self.toolbar.removeAction(action)
            action.deleteLater()
        self.active_dropdown_actions.clear()

    def set_layer_active(self, definition, checked):
        if checked:
            self.add_layer(definition, force_add=True)
        else:
            project = QgsProject.instance()
            ids = [
                layer.id()
                for layer in project.mapLayers().values()
                if self._layer_source_id(layer) == self._source_id(definition)
            ]
            if ids:
                self._remove_layers_and_empty_groups(ids)
                self.success(
                    f"{self.display_name(definition)} "
                    + ("removed." if self.language == "en" else "eemaldatud.")
                )
        self.sync_dropdown_checks()

    def add_layer(self, definition, force_add=False):
        if definition.role == "sarv_points":
            return self._add_sarv_point_layers(definition, force_add)

        source_id = self._source_id(definition)
        name = self.display_name(definition)
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if self._layer_source_id(layer) == source_id:
                if self.toggle_mode and not force_add:
                    project.removeMapLayer(layer.id())
                    self.success(f"{name} " + ("removed." if self.language == "en" else "eemaldatud."))
                    return False
                if (
                    isinstance(layer, QgsVectorLayer)
                    and definition.protocol.upper() == "WFS"
                    and definition.role in {"boreholes", "observations"}
                    and "forceinitialgetfeature" not in layer.source().casefold()
                ):
                    project.removeMapLayer(layer.id())
                    return self.add_layer(definition, force_add=True)
                node = project.layerTreeRoot().findLayer(layer.id())
                if node:
                    node.setItemVisibilityChecked(True)
                self._apply_layer_workarounds(layer, definition)
                self._ensure_egt_points_on_top(layer if definition.role else None)
                self.iface.setActiveLayer(layer)
                self.message(
                    f"{name} "
                    + ("is already in the project." if self.language == "en" else "on juba projektis.")
                )
                return True

        if definition.protocol.upper() == "WFS":
            layer = QgsVectorLayer(self._wfs_uri(definition), name, "WFS")
        else:
            layer = QgsRasterLayer(self._wms_uri(definition), name, "wms")
        if not layer.isValid():
            self.error(
                (f"Could not load {name}. Check the connection, service URL and layer name."
                 if self.language == "en" else
                 f"Kihi {name} laadimine ebaõnnestus. Kontrolli internetiühendust, teenuse URL-i ja kihinime.")
            )
            self.sync_dropdown_checks()
            return False
        layer.setCustomProperty(self.SOURCE_PROPERTY, source_id)
        layer.setCustomProperty(self.ROLE_PROPERTY, definition.role)
        self._apply_layer_workarounds(layer, definition)
        if definition.role and isinstance(layer, QgsVectorLayer):
            self._apply_category_renderer(layer)
            if definition.role == "boreholes":
                self._apply_borehole_labeling(layer)
        project.addMapLayer(layer, False)
        root = project.layerTreeRoot()
        if definition.base_map:
            root.addLayer(layer)
        else:
            root.insertLayer(0, layer)
        self._ensure_egt_points_on_top(layer if definition.role else None)
        self.iface.setActiveLayer(layer)
        if definition.role:
            self.apply_egt_filters()
        self.success(f"{name} " + ("added." if self.language == "en" else "lisatud."))
        self.sync_dropdown_checks()
        return True

    def _add_sarv_point_layers(self, definition, force_add=False):
        source_id = self._source_id(definition)
        project = QgsProject.instance()
        existing = [
            layer for layer in project.mapLayers().values()
            if self._layer_source_id(layer) == source_id
        ]
        if existing:
            if self.toggle_mode and not force_add:
                self._remove_layers_and_empty_groups(
                    [layer.id() for layer in existing]
                )
                self.success(
                    f"{self.display_name(definition)} "
                    + ("removed." if self.language == "en" else "eemaldatud.")
                )
                return False
            for layer in existing:
                node = project.layerTreeRoot().findLayer(layer.id())
                if node:
                    node.setItemVisibilityChecked(True)
            self.iface.setActiveLayer(existing[0])
            return True

        self.message(
            "Loading SARV localities, research sites and drill cores..."
            if self.language == "en" else
            "SARV-i lokaliteete, uuringupunkte ja puursüdamikke laaditakse..."
        )

        def load_failed(error):
            self.error(
                f"Could not load SARV locations: {error}" if self.language == "en"
                else f"SARV-i kohtade laadimine ebaõnnestus: {error}"
            )

        self._ensure_sarv_point_cache(
            lambda localities, sites, drillcores: self._create_sarv_point_layers(
                definition, localities, sites, drillcores,
            ),
            load_failed,
        )
        return True

    def _ensure_sarv_point_cache(self, success, failure):
        if self._sarv_point_cache is not None:
            success(*self._sarv_point_cache)
            return
        self._sarv_point_waiters.append((success, failure))
        if self._sarv_points_loading:
            return
        self._sarv_points_loading = True
        result = {}
        failed = {"value": False}

        def completed(kind):
            def handler(rows):
                result[kind] = rows
                if len(result) != 3 or failed["value"]:
                    return
                self._sarv_points_loading = False
                self._sarv_point_cache = (
                    result["localities"], result["sites"],
                    result["drillcores"],
                )
                waiters, self._sarv_point_waiters = self._sarv_point_waiters, []
                for callback, _ in waiters:
                    callback(*self._sarv_point_cache)
            return handler

        def load_failed(error):
            if failed["value"]:
                return
            failed["value"] = True
            self._sarv_points_loading = False
            waiters, self._sarv_point_waiters = self._sarv_point_waiters, []
            for _, callback in waiters:
                callback(error)

        common = (
            "id", "name", "name_en", "number", "latitude", "longitude",
            "depth", "type",
        )
        self.network.query_sarv_all(
            "localities",
            common + ("land_board_id",),
            completed("localities"),
            load_failed,
        )
        self.network.query_sarv_all(
            "sites",
            common + ("locality",),
            completed("sites"),
            load_failed,
        )
        self.network.query_sarv_all(
            "drillcores",
            (
                "id", "name", "name_en", "number", "locality", "depth",
                "depository", "location", "storage",
            ),
            completed("drillcores"),
            load_failed,
        )

    def _create_sarv_point_layers(
        self, definition, localities, sites, drillcores,
    ):
        project = QgsProject.instance()
        source_id = self._source_id(definition)
        if any(
            self._layer_source_id(layer) == source_id
            for layer in project.mapLayers().values()
        ):
            self.sync_dropdown_checks()
            return
        localities_by_id = {
            str(row.get("id")): row for row in localities if row.get("id")
        }
        drillcore_points = []
        for row in drillcores:
            locality = row.get("locality")
            locality_id = locality.get("id") if isinstance(locality, dict) else locality
            locality_row = localities_by_id.get(str(locality_id))
            if not locality_row:
                continue
            point = dict(row)
            point.update({
                "latitude": locality_row.get("latitude"),
                "longitude": locality_row.get("longitude"),
                "land_board_id": locality_row.get("land_board_id"),
                "locality": locality_id,
                "type": "drillcore",
                "depth": row.get("depth") or locality_row.get("depth"),
            })
            drillcore_points.append(point)

        layers = (
            self._sarv_memory_layer(
                self.t("SARV - lokaliteedid"), "sarv_localities",
                localities, "#2f7892", "circle",
            ),
            self._sarv_memory_layer(
                self.t("SARV - uuringupunktid"), "sarv_sites",
                sites, "#8b5aa3", "diamond",
            ),
            self._sarv_memory_layer(
                self.t("SARV - puursüdamikud"), "sarv_drillcores",
                drillcore_points, "#d57b2a", "hexagon",
            ),
        )
        for layer in layers:
            layer.setCustomProperty(self.SOURCE_PROPERTY, source_id)
            project.addMapLayer(layer, False)

        root = project.layerTreeRoot()
        group = root.findGroup(self.display_name(definition))
        if not group or group.children():
            group = root.insertGroup(0, self.display_name(definition))
        for layer in reversed(layers):
            group.addLayer(layer)
        self._ensure_egt_points_on_top()
        self.iface.setActiveLayer(layers[2])
        self.success(
            (
                f"Loaded {layers[0].featureCount()} SARV localities and "
                f"{layers[1].featureCount()} research sites and "
                f"{layers[2].featureCount()} drill cores."
                if self.language == "en" else
                f"Laaditi {layers[0].featureCount()} SARV-i lokaliteeti ja "
                f"{layers[1].featureCount()} uuringupunkti ning "
                f"{layers[2].featureCount()} puursüdamikku."
            )
        )
        self.apply_sarv_filters()
        self.sync_dropdown_checks()

    def _remove_layers_and_empty_groups(self, layer_ids):
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        parents = []
        for layer_id in layer_ids:
            node = root.findLayer(layer_id)
            parent = node.parent() if node else None
            if parent and parent != root and parent not in parents:
                parents.append(parent)
        project.removeMapLayers(layer_ids)
        for parent in parents:
            ancestor = parent.parent()
            if ancestor and not parent.children():
                ancestor.removeChildNode(parent)

    def _sarv_memory_layer(self, name, role, rows, color, symbol_name):
        layer = QgsVectorLayer("Point?crs=EPSG:4326", name, "memory")
        layer.setCustomProperty(self.ROLE_PROPERTY, role)
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("sarv_id", QVariant.Int),
            QgsField("source_type", QVariant.String),
            QgsField("name", QVariant.String),
            QgsField("name_en", QVariant.String),
            QgsField("number", QVariant.String),
            QgsField("depth", QVariant.Double),
            QgsField("type", QVariant.String),
            QgsField("locality_id", QVariant.Int),
            QgsField("land_board_id", QVariant.String),
            QgsField("latitude", QVariant.Double),
            QgsField("longitude", QVariant.Double),
        ])
        layer.updateFields()
        features = []
        for row in rows:
            try:
                latitude = float(row.get("latitude"))
                longitude = float(row.get("longitude"))
            except (TypeError, ValueError):
                continue
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            locality = row.get("locality")
            locality_id = locality.get("id") if isinstance(locality, dict) else locality
            type_value = row.get("type")
            if isinstance(type_value, dict):
                type_value = (
                    type_value.get("value_en") if self.language == "en"
                    else type_value.get("value")
                ) or type_value.get("name") or type_value.get("id")
            depth = row.get("depth")
            try:
                depth = float(depth) if depth not in (None, "") else None
            except (TypeError, ValueError):
                depth = None
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(longitude, latitude)))
            source_type = {
                "sarv_localities": "locality",
                "sarv_sites": "site",
                "sarv_drillcores": "drillcore",
            }.get(role, "")
            feature.setAttributes([
                row.get("id"),
                source_type,
                row.get("name"),
                row.get("name_en"),
                row.get("number"),
                depth,
                type_value,
                row.get("id") if role == "sarv_localities" else locality_id,
                row.get("land_board_id"),
                latitude,
                longitude,
            ])
            features.append(feature)
            if len(features) >= 2000:
                provider.addFeatures(features)
                features = []
        if features:
            provider.addFeatures(features)
        layer.updateExtents()
        symbol = QgsMarkerSymbol.createSimple({
            "name": symbol_name,
            "color": color,
            "outline_color": "#ffffff",
            "outline_width": "0.35",
            "size": "2.6",
        })
        layer.renderer().setSymbol(symbol)
        self._apply_name_labeling(layer)
        return layer

    @staticmethod
    def _source_id(definition):
        return "|".join((definition.protocol.upper(), definition.url, definition.layer_name, definition.style))

    @classmethod
    def _layer_source_id(cls, layer):
        return layer.customProperty(
            cls.SOURCE_PROPERTY,
            layer.customProperty(cls.LEGACY_SOURCE_PROPERTY, ""),
        )

    @classmethod
    def _layer_role(cls, layer):
        return layer.customProperty(
            cls.ROLE_PROPERTY,
            layer.customProperty(cls.LEGACY_ROLE_PROPERTY, ""),
        )

    @staticmethod
    def _wms_uri(definition):
        layer_names = [name.strip() for name in definition.layer_name.split(",") if name.strip()]
        styles = [style.strip() for style in definition.style.split(",")]
        layer_parameters = "".join(
            f"&layers={quote(name)}&styles={quote(styles[index] if index < len(styles) else '')}"
            for index, name in enumerate(layer_names)
        )
        return (
            "crs=EPSG:3301&format=image/png"
            f"{layer_parameters}"
            f"&url={definition.url}&version=1.3.0"
        )

    @staticmethod
    def _wfs_uri(definition):
        uri = QgsDataSourceUri()
        uri.setParam("url", definition.url)
        uri.setParam("typename", definition.layer_name)
        uri.setParam("version", "2.0.0")
        uri.setParam("srsname", "EPSG:3301")
        uri.setParam("pagingEnabled", "true")
        uri.setParam("restrictToRequestBBOX", "1")
        uri.setParam("forceInitialGetFeature", "true")
        return uri.uri(False)

    def _refresh_loaded_plugin_layers(self):
        definitions = {self._source_id(item): item for item in self.definitions}
        for layer in QgsProject.instance().mapLayers().values():
            definition = definitions.get(self._layer_source_id(layer))
            adopted = False
            if not definition:
                definition = self._definition_from_wfs_source(layer)
                adopted = definition is not None
            if not definition:
                continue
            if adopted:
                # Older projects can contain a Qeoloog WFS layer whose custom
                # properties were not persisted. Re-associate only an exact
                # service URL + typename match, then restore the plugin style.
                layer.setCustomProperty(
                    self.SOURCE_PROPERTY, self._source_id(definition)
                )
                layer.setCustomProperty(self.ROLE_PROPERTY, definition.role)
                if definition.role and isinstance(layer, QgsVectorLayer):
                    self._apply_category_renderer(layer)
                    if definition.role == "boreholes":
                        self._apply_borehole_labeling(layer)
            self._apply_layer_workarounds(layer, definition)
        self.sync_dropdown_checks()
        self._ensure_egt_points_on_top()

    def _definition_from_wfs_source(self, layer):
        """Return the exact configured WFS definition for an untagged layer."""
        if not isinstance(layer, QgsVectorLayer) or layer.providerType() != "WFS":
            return None
        try:
            uri = QgsDataSourceUri(layer.source())
            service_url = uri.param("url").strip().rstrip("/").casefold()
            typename = uri.param("typename").strip().casefold()
        except (AttributeError, TypeError, ValueError):
            return None
        if not service_url or not typename:
            return None
        for definition in self.definitions:
            if definition.protocol.upper() != "WFS":
                continue
            if (
                definition.url.strip().rstrip("/").casefold() == service_url
                and definition.layer_name.strip().casefold() == typename
            ):
                return definition
        return None

    def _apply_layer_workarounds(self, layer, definition):
        if (
            isinstance(layer, QgsRasterLayer)
            and definition.protocol.upper() == "WMS"
            and definition.layer_name == "ak_avamus_a_200t"
        ):
            # EGT GetMap contains western Saaremaa, but the layer-level
            # GetCapabilities bounding box is too narrow and QGIS clips to it.
            layer.setExtent(QgsRectangle(self.AK_CORRECTED_EXTENT))

    def _ensure_egt_points_on_top(self, preferred=None):
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        point_roles = {"boreholes", "observations"}
        point_layers = [
            layer for layer in project.mapLayers().values()
            if self._layer_role(layer) in point_roles
        ]
        for layer in point_layers:
            node = root.findLayer(layer.id())
            if node and node.parent() != root:
                node.parent().takeChild(node)
                root.insertChildNode(0, node)
        ordered = [
            child.layer() for child in root.children()
            if hasattr(child, "layer")
            and child.layer()
            and self._layer_role(child.layer()) in point_roles
        ]
        if preferred in ordered:
            ordered.remove(preferred)
            ordered.insert(0, preferred)
        if ordered:
            root.reorderGroupLayers(ordered)

    def _apply_category_renderer(self, layer, related_expression=""):
        QgsExpressionContextUtils.setLayerVariable(
            layer, "qeoloog_filter_expression",
            related_expression or "TRUE",
        )
        labels = {1: "Pinnakate", 2: "Aluspõhi", 3: "Aluskord", 997: "Muu / teadmata"}
        root_rule = QgsRuleBasedRenderer.Rule(None)
        for code in (1, 2, 3, 997):
            symbol = QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": self.CATEGORY_COLORS[code], "outline_color": "#3a3a3a", "outline_width": "0.25", "size": "2.7"}
            )
            category_expression = (
                f'"klassif_yksus_kood" = {code}' if code != 997 else
                '("klassif_yksus_kood" IS NULL OR "klassif_yksus_kood" NOT IN (1, 2, 3))'
            )
            expression = category_expression
            if related_expression:
                # eval(layer-variable) deliberately prevents WFS from expanding
                # large ID lists into a request URL; QGIS evaluates it locally.
                expression = (
                    f"({category_expression}) AND "
                    "eval(@qeoloog_filter_expression)"
                )
            rule = QgsRuleBasedRenderer.Rule(symbol)
            rule.setLabel(self.t(labels[code]))
            rule.setFilterExpression(expression)
            root_rule.appendChild(rule)
        layer.setRenderer(QgsRuleBasedRenderer(root_rule))
        layer.triggerRepaint()

    @staticmethod
    def _apply_borehole_labeling(layer):
        QeoloogPlugin._apply_name_labeling(layer, "nimi")

    @staticmethod
    def _apply_name_labeling(layer, field_name="name"):
        if layer.fields().indexOf(field_name) < 0:
            return
        text_format = QgsTextFormat()
        text_format.setSize(5.0)
        text_format.setSizeUnit(Qgis.RenderUnit.Points)
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(0.6)
        buffer.setSizeUnit(Qgis.RenderUnit.Millimeters)
        buffer.setColor(QColor("white"))
        text_format.setBuffer(buffer)
        settings = QgsPalLayerSettings()
        settings.fieldName = field_name
        settings.isExpression = False
        settings.setFormat(text_format)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()

    def apply_egt_filters(self):
        if not self.dock:
            return
        category_expression = self._category_subset(self.dock.filters.selected_codes())
        requirements = self.dock.filters.related_requirements()
        related_expression = ""
        if any(value != "any" for value in requirements.values()):
            if len(self.related_index) < 4:
                self._ensure_related_index()
            else:
                related_expression = " AND ".join(
                    f"({item})" for item in self._related_subset(requirements)
                )
        domain_requirements = self.dock.filters.egt_domain_requirements()
        if any(
            selected
            for groups in domain_requirements.values()
            for selected in groups.values()
        ):
            if not all(self.egt_filter_rows.values()):
                self._ensure_egt_filter_catalog()
            else:
                domain_clauses = self._egt_domain_filter_clauses(
                    domain_requirements
                )
                if domain_clauses is not None:
                    combined = [related_expression] if related_expression else []
                    combined.extend(domain_clauses)
                    related_expression = " AND ".join(
                        f"({clause})" for clause in combined if clause
                    )
        visibility = {
            "boreholes": self.dock.filters.boreholes.isChecked(),
            "observations": self.dock.filters.observations.isChecked(),
        }
        project = QgsProject.instance()
        for role, visible in visibility.items():
            for layer in self._role_layers(role):
                layer.setSubsetString(category_expression)
                self._apply_category_renderer(layer, related_expression)
                if role == "boreholes":
                    self._apply_borehole_labeling(layer)
                node = project.layerTreeRoot().findLayer(layer.id())
                if node:
                    node.setItemVisibilityChecked(visible)
                layer.triggerRepaint()

    def _ensure_egt_filter_catalog(self):
        if self._egt_catalog_loading:
            return
        self._egt_catalog_loading = True
        pending = {"samples", "analyses"}

        def loaded(key):
            def handler(rows):
                self.egt_filter_rows[key] = list(rows)
                pending.discard(key)
                if not pending:
                    self._egt_catalog_loading = False
                    self.apply_egt_filters()
            return handler

        def failed(key):
            def handler(error):
                pending.discard(key)
                self._egt_catalog_loading = False
                self.warning(
                    (f"Could not load EGT {key} filter data: {error}"
                     if self.language == "en" else
                     f"EGT filtriandmete {key} laadimine ebaõnnestus: {error}")
                )
            return handler

        self.network.query_auq_all(
            18, "puurauk_vaatluspunkt_id IS NOT NULL",
            (
                "objectid", "puurauk_vaatluspunkt_id", "proov_tyyp",
                "eesmark", "staatus",
            ),
            loaded("samples"), failed("samples"),
        )
        self.network.query_auq_all(
            3, "puurauk_vaatluspunkt_id IS NOT NULL",
            (
                "objectid", "globalid", "puurauk_vaatluspunkt_id",
                "analyys_meetod", "labor",
            ),
            loaded("analyses"), failed("analyses"),
        )

    @staticmethod
    def _row_matches_domains(row, selections):
        for field, selected in selections.items():
            if selected and str(row.get(field)) not in selected:
                return False
        return True

    @staticmethod
    def _id_membership_clause(values):
        values = sorted({str(value).upper() for value in values if value})
        if not values:
            return '"esri_globalid" = \'__none__\''
        quoted = ", ".join(
            f"'{value.replace(chr(39), chr(39) * 2)}'" for value in values
        )
        return f'"esri_globalid" IN ({quoted})'

    def _egt_domain_filter_clauses(self, requirements):
        clauses = []
        sample_filters = requirements["samples"]
        if any(sample_filters.values()):
            parents = {
                row.get("puurauk_vaatluspunkt_id")
                for row in self.egt_filter_rows["samples"]
                if self._row_matches_domains(row, sample_filters)
            }
            clauses.append(self._id_membership_clause(parents))

        analysis_filters = requirements["analyses"]
        direct = {
            field: selected
            for (table_id, field), selected in analysis_filters.items()
            if table_id == 3
        }
        result = {
            field: selected
            for (table_id, field), selected in analysis_filters.items()
            if table_id == 4
        }
        matching_result_ids = None
        if any(result.values()):
            cache_key = tuple(
                (field, tuple(sorted(selected)))
                for field, selected in sorted(result.items())
                if selected
            )
            if cache_key not in self._egt_result_filter_cache:
                self._load_egt_result_filter(cache_key, result)
                return None
            matching_result_ids = self._egt_result_filter_cache[cache_key]
        if any(direct.values()) or matching_result_ids is not None:
            parents = {
                row.get("puurauk_vaatluspunkt_id")
                for row in self.egt_filter_rows["analyses"]
                if self._row_matches_domains(row, direct)
                and (
                    matching_result_ids is None
                    or str(row.get("globalid")).upper() in matching_result_ids
                )
            }
            clauses.append(self._id_membership_clause(parents))
        return clauses

    def _load_egt_result_filter(self, cache_key, result_filters):
        if cache_key in self._egt_result_filter_loading:
            return
        self._egt_result_filter_loading.add(cache_key)
        parts = []
        for field, selected in result_filters.items():
            if not selected:
                continue
            quoted = ", ".join(
                f"'{str(value).replace(chr(39), chr(39) * 2)}'"
                for value in sorted(selected)
            )
            parts.append(f"{field} IN ({quoted})")
        where = " AND ".join(parts) or "1=1"

        def loaded(rows):
            self._egt_result_filter_loading.discard(cache_key)
            self._egt_result_filter_cache[cache_key] = {
                str(row.get("analyys_mootmine_id")).upper()
                for row in rows if row.get("analyys_mootmine_id")
            }
            self.apply_egt_filters()

        def failed(error):
            self._egt_result_filter_loading.discard(cache_key)
            self.warning(
                (f"Could not load EGT result filter: {error}"
                 if self.language == "en" else
                 f"EGT analüüsitulemuse filtri laadimine ebaõnnestus: {error}")
            )

        self.network.query_auq_all(
            4, where, ("objectid", "analyys_mootmine_id"),
            loaded, failed,
        )

    def _ensure_related_index(self):
        if self.related_index_loading:
            return
        self.related_index_loading = True
        self.message(
            "Loading related-data filter index..." if self.language == "en"
            else "Seotud andmete filtriindeksit laaditakse..."
        )
        tables = {"core": 22, "samples": 18, "analyses": 3, "attachments": 15}
        pending = list(tables.items())
        failed = {"value": False}

        def loaded(key):
            def handler(values):
                self.related_index[key] = {str(value).upper() for value in values}
                pending.pop(0)
                if not pending:
                    self.related_index_loading = False
                    if not failed["value"]:
                        self.success(
                            "Related-data filters are ready." if self.language == "en"
                            else "Seotud andmete filtrid on valmis."
                        )
                    self.apply_egt_filters()
                else:
                    load_next()
            return handler

        def load_failed(key):
            def handler(error):
                failed["value"] = True
                self.related_index[key] = set()
                pending.pop(0)
                self.warning(
                    (f"Could not load the {key} filter index: {error}"
                     if self.language == "en" else
                     f"Filtriindeksi {key} laadimine ebaõnnestus: {error}")
                )
                if not pending:
                    self.related_index_loading = False
                    self.apply_egt_filters()
                else:
                    load_next()
            return handler

        def load_next():
            key, table_id = pending[0]
            self.network.query_auq_parent_ids(
                table_id, loaded(key), load_failed(key)
            )

        load_next()

    def _related_subset(self, requirements):
        clauses = []
        for key, requirement in requirements.items():
            if requirement == "any":
                continue
            values = sorted(self.related_index.get(key, set()))
            if not values:
                if requirement == "yes":
                    clauses.append('"esri_globalid" = \'__none__\'')
                continue
            quoted = ", ".join(f"'{value.replace(chr(39), chr(39) * 2)}'" for value in values)
            operator = "IN" if requirement == "yes" else "NOT IN"
            clauses.append(f'"esri_globalid" {operator} ({quoted})')
        return clauses

    @staticmethod
    def _category_subset(selected):
        if selected == {1, 2, 3, 997}:
            return ""
        clauses = []
        ordinary = sorted(selected.intersection({1, 2, 3}))
        if ordinary:
            clauses.append(f'"klassif_yksus_kood" IN ({", ".join(str(v) for v in ordinary)})')
        if 997 in selected:
            clauses.append('("klassif_yksus_kood" IS NULL OR "klassif_yksus_kood" NOT IN (1, 2, 3))')
        return " OR ".join(clauses) or '"klassif_yksus_kood" = -999999'

    # ---- SARV filters -------------------------------------------------------------

    def apply_sarv_filters(self):
        if not self.dock:
            return
        requirements = self.dock.sarv_filters.requirements()
        self._sarv_filter_generation += 1
        generation = self._sarv_filter_generation
        project = QgsProject.instance()
        layers = {
            role: self._role_layers(role)
            for role in ("sarv_localities", "sarv_sites", "sarv_drillcores")
        }
        base_parts = []
        if requirements["depth_min"] is not None:
            base_parts.append(f'"depth" >= {requirements["depth_min"]:g}')
        if requirements["depth_max"] is not None:
            base_parts.append(f'"depth" <= {requirements["depth_max"]:g}')
        if requirements["current_extent"]:
            try:
                extent = self.iface.mapCanvas().extent()
                transform = QgsCoordinateTransform(
                    self.iface.mapCanvas().mapSettings().destinationCrs(),
                    QgsCoordinateReferenceSystem("EPSG:4326"),
                    project,
                )
                extent = transform.transformBoundingBox(extent)
                base_parts.extend((
                    f"$x >= {extent.xMinimum():.10f}",
                    f"$x <= {extent.xMaximum():.10f}",
                    f"$y >= {extent.yMinimum():.10f}",
                    f"$y <= {extent.yMaximum():.10f}",
                ))
            except QgsCsException:
                pass
        base_expression = " AND ".join(base_parts)
        for role, role_layers in layers.items():
            visible = role in requirements["kinds"]
            for layer in role_layers:
                layer.setSubsetString(base_expression)
                node = project.layerTreeRoot().findLayer(layer.id())
                if node:
                    node.setItemVisibilityChecked(visible)
                layer.triggerRepaint()

        related_active = any(
            value != "any" for value in requirements["related"].values()
        )
        advanced = (
            related_active or requirements["sample_purpose"]
            or requirements["sample_type"] or requirements["analysis_method"]
        )
        if advanced:
            self._load_sarv_filter_matches(
                generation, requirements, layers, base_expression
            )

    def _load_sarv_filter_matches(
        self, generation, requirements, layers, base_expression,
    ):
        candidate = {"locality": set(), "site": set()}
        for role, role_layers in layers.items():
            for layer in role_layers:
                for feature in layer.getFeatures():
                    locality_id = feature["locality_id"]
                    target = "site" if role == "sarv_sites" else "locality"
                    target_id = (
                        feature["sarv_id"] if target == "site" else locality_id
                    )
                    if target_id in (None, ""):
                        continue
                    candidate[target].add(str(target_id))
        if not any(candidate.values()):
            return

        conditions = []
        for key in ("samples", "analyses", "specimens"):
            requirement = requirements["related"].get(key, "any")
            selected = (
                key == "samples" and (
                    requirements["sample_purpose"] or requirements["sample_type"]
                )
            ) or (
                key == "analyses" and requirements["analysis_method"]
            )
            if requirement != "any" or selected:
                conditions.append((key, requirement if not selected else "yes"))
        core_requirement = requirements["related"].get("core", "any")
        matched = {}
        if core_requirement != "any":
            core_localities = set()
            for layer in layers.get("sarv_drillcores", []):
                for feature in layer.getFeatures():
                    locality_id = feature["locality_id"]
                    if locality_id not in (None, ""):
                        core_localities.add(str(locality_id))
            matched["core"] = {
                ("locality", identifier) for identifier in core_localities
            }

        def apply_finished():
            if generation != self._sarv_filter_generation:
                return
            def membership(field, target, matches, requirement):
                universe = candidate[target]
                present = {
                    identifier for match_target, identifier in matches
                    if match_target == target
                }.intersection(universe)
                desired = present if requirement == "yes" else universe - present
                excluded = universe - desired
                use_in = len(desired) <= len(excluded)
                values = desired if use_in else excluded
                if not values:
                    return f'"{field}" = -1' if use_in else "TRUE"
                literals = ", ".join(
                    value if str(value).lstrip("-").isdigit()
                    else f"'{str(value).replace(chr(39), chr(39) * 2)}'"
                    for value in sorted(values)
                )
                operator = "IN" if use_in else "NOT IN"
                return f'"{field}" {operator} ({literals})'

            for role, role_layers in layers.items():
                target = "site" if role == "sarv_sites" else "locality"
                field = (
                    "locality_id" if role == "sarv_drillcores"
                    else "sarv_id"
                )
                clauses = [base_expression] if base_expression else []
                for condition, requirement in conditions:
                    clauses.append(membership(
                        field, target, matched.get(condition, set()), requirement
                    ))
                if core_requirement != "any":
                    clauses.append(membership(
                        field, target, matched.get("core", set()),
                        core_requirement,
                    ))
                expression = " AND ".join(
                    f"({clause})" for clause in clauses if clause and clause != "TRUE"
                )
                for layer in role_layers:
                    layer.setSubsetString(expression)
                    layer.triggerRepaint()

        def load_condition(index):
            if generation != self._sarv_filter_generation:
                return
            if index >= len(conditions):
                apply_finished()
                return
            condition, _ = conditions[index]
            matched[condition] = set()
            requests = []
            for target in ("locality", "site"):
                ids = sorted(candidate[target])
                if condition == "specimens" and target == "site":
                    continue
                for offset in range(0, len(ids), 500):
                    chunk = ids[offset:offset + 500]
                    if condition == "samples":
                        purposes = (
                            sorted(requirements["sample_purpose"]) or [None]
                        )
                        sample_types = (
                            sorted(requirements["sample_type"]) or [None]
                        )
                        requests.extend(
                            (target, chunk, purpose, sample_type)
                            for purpose in purposes for sample_type in sample_types
                        )
                    else:
                        requests.append((target, chunk, None, None))
            if not requests:
                load_condition(index + 1)
                return
            remaining = {"count": len(requests)}

            def completed():
                remaining["count"] -= 1
                if remaining["count"] == 0:
                    load_condition(index + 1)

            for target, ids, purpose, sample_type in requests:
                if condition == "samples":
                    resource = "samples"
                    parameters = {
                        f"{target}__in": ",".join(ids),
                        "purpose": purpose,
                        "type": sample_type,
                    }
                    fields = ("id", target)
                elif condition == "analyses":
                    resource = "analyses"
                    parameters = {
                        f"sample__{target}__in": ",".join(ids),
                        "analysis_method__in": ",".join(
                            sorted(requirements["analysis_method"])
                        ),
                    }
                    fields = ("id", "sample")
                else:
                    resource = "specimens"
                    parameters = {"locality__in": ",".join(ids)}
                    fields = ("id", "locality")

                def loaded(rows, target=target, condition=condition):
                    if condition == "analyses":
                        sample_ids = {
                            str(row.get("sample"))
                            for row in rows
                            if row.get("sample") not in (None, "")
                        }
                        if not sample_ids:
                            completed()
                            return
                        chunks = [
                            sorted(sample_ids)[offset:offset + 500]
                            for offset in range(0, len(sample_ids), 500)
                        ]
                        parent_pending = {"count": len(chunks)}

                        def parents_loaded(samples):
                            for sample in samples:
                                value = sample.get(target)
                                if isinstance(value, dict):
                                    value = value.get("id")
                                if value not in (None, ""):
                                    matched[condition].add((target, str(value)))
                            parent_pending["count"] -= 1
                            if parent_pending["count"] == 0:
                                completed()

                        def parents_failed(error):
                            self.warning(
                                (f"Could not apply a SARV analysis filter: {error}"
                                 if self.language == "en" else
                                 f"SARV analüüsifiltri rakendamine ebaõnnestus: {error}")
                            )
                            parent_pending["count"] -= 1
                            if parent_pending["count"] == 0:
                                completed()

                        for chunk in chunks:
                            self.network.query_sarv_pages(
                                "samples", {"id__in": ",".join(chunk)},
                                ("id", target), parents_loaded, parents_failed,
                                limit=5000,
                            )
                        return
                    for row in rows:
                        value = row.get(target)
                        if isinstance(value, dict):
                            value = value.get("id")
                        if value not in (None, ""):
                            matched[condition].add((target, str(value)))
                    completed()

                def failed(error):
                    self.warning(
                        (f"Could not apply a SARV filter: {error}"
                         if self.language == "en" else
                         f"SARV filtri rakendamine ebaõnnestus: {error}")
                    )
                    completed()

                self.network.query_sarv_pages(
                    resource, parameters, fields, loaded, failed, limit=5000,
                )

        load_condition(0)

    # ---- Shared EGT/SARV search ---------------------------------------------------

    def run_search(self, criteria, callback):
        source = criteria.get("source", "both")
        wants_egt = source in {"both", "egt"}
        wants_sarv = source in {"both", "sarv"}
        related = criteria.get("related", {})
        sarv_choices = any(
            value.startswith("sarv:")
            for key in ("sample_type", "sample_purpose", "analysis_method")
            for value in criteria.get(key, set())
        ) or any(value != "any" for value in related.values())
        if wants_sarv and sarv_choices and "_sarv_allowed" not in criteria:
            self._resolve_sarv_search_allowed(
                criteria,
                lambda allowed: self.run_search(
                    {**criteria, "_sarv_allowed": allowed}, callback
                ),
                lambda error: callback(
                    [],
                    (f"SARV search failed: {error}" if self.language == "en"
                     else f"SARV otsing ebaõnnestus: {error}"),
                ),
            )
            return
        egt_choices = any(
            value.startswith("egt:")
            for key in ("sample_type", "sample_purpose", "analysis_method")
            for value in criteria.get(key, set())
        )
        if (
            wants_egt
            and any(value != "any" for value in related.values())
            and len(self.related_index) < 4
        ):
            self._ensure_related_index()
            callback(
                [],
                self.t("EGT seotud-andmete indeksit laaditakse. "
                       "Vajuta hetke pärast uuesti Otsi."),
            )
            return
        if wants_egt and egt_choices and not all(self.egt_filter_rows.values()):
            self._ensure_egt_filter_catalog()
            callback(
                [],
                self.t("EGT proovi- ja analüüsiindeksit laaditakse. "
                       "Vajuta hetke pärast uuesti Otsi."),
            )
            return

        allowed_egt = None
        if wants_egt and egt_choices:
            sample_filters = {
                "proov_tyyp": {
                    value[4:] for value in criteria.get("sample_type", set())
                    if value.startswith("egt:")
                },
                "eesmark": {
                    value[4:] for value in criteria.get("sample_purpose", set())
                    if value.startswith("egt:")
                },
            }
            analysis_filters = {
                "analyys_meetod": {
                    value[4:] for value in criteria.get("analysis_method", set())
                    if value.startswith("egt:")
                },
            }
            groups = []
            if any(sample_filters.values()):
                groups.append({
                    str(row.get("puurauk_vaatluspunkt_id")).upper()
                    for row in self.egt_filter_rows["samples"]
                    if self._row_matches_domains(row, sample_filters)
                })
            if any(analysis_filters.values()):
                groups.append({
                    str(row.get("puurauk_vaatluspunkt_id")).upper()
                    for row in self.egt_filter_rows["analyses"]
                    if self._row_matches_domains(row, analysis_filters)
                })
            allowed_egt = set.intersection(*groups) if groups else None

        text_query = str(criteria.get("text") or "").casefold()
        depth_min = criteria.get("depth_min")
        depth_max = criteria.get("depth_max")
        canvas_extent = self.iface.mapCanvas().extent()
        rows = []
        loaded_sources = set()
        roles = []
        if wants_egt:
            roles.extend(("boreholes", "observations"))
        if wants_sarv:
            roles.extend(("sarv_localities", "sarv_sites", "sarv_drillcores"))
        selected_roles = criteria.get("kinds")
        if selected_roles is not None:
            roles = [role for role in roles if role in selected_roles]
        for role in roles:
            for layer in self._role_layers(role):
                loaded_sources.add("SARV" if role.startswith("sarv_") else "EGT")
                request = QgsFeatureRequest()
                if criteria.get("current_extent"):
                    try:
                        extent = QgsCoordinateTransform(
                            self.iface.mapCanvas().mapSettings().destinationCrs(),
                            layer.crs(), QgsProject.instance(),
                        ).transformBoundingBox(canvas_extent)
                        request.setFilterRect(extent)
                    except QgsCsException:
                        pass
                for feature in layer.getFeatures(request):
                    attributes = {
                        field.name(): feature.attribute(field.name())
                        for field in layer.fields()
                    }
                    is_sarv = role.startswith("sarv_")
                    object_id = (
                        attributes.get("sarv_id") if is_sarv else
                        attributes.get("esri_globalid") or attributes.get("globalid")
                    )
                    if is_sarv and "_sarv_allowed" in criteria:
                        target = "site" if role == "sarv_sites" else "locality"
                        target_id = (
                            attributes.get("sarv_id") if target == "site"
                            else attributes.get("locality_id")
                        )
                        if (target, str(target_id)) not in criteria["_sarv_allowed"]:
                            continue
                    if not is_sarv and allowed_egt is not None:
                        if str(object_id).upper() not in allowed_egt:
                            continue
                    if not is_sarv:
                        object_key = str(object_id).upper()
                        rejected = False
                        for key, requirement in related.items():
                            if requirement == "any":
                                continue
                            present = object_key in self.related_index.get(key, set())
                            if (
                                (requirement == "yes" and not present)
                                or (requirement == "no" and present)
                            ):
                                rejected = True
                                break
                        if rejected:
                            continue
                    depth = (
                        attributes.get("depth") if is_sarv else
                        attributes.get("pikkus") or attributes.get("vertikaalne_ulatus")
                    )
                    try:
                        numeric_depth = float(depth) if depth not in (None, "") else None
                    except (TypeError, ValueError):
                        numeric_depth = None
                    if depth_min is not None and (
                        numeric_depth is None or numeric_depth < depth_min
                    ):
                        continue
                    if depth_max is not None and (
                        numeric_depth is None or numeric_depth > depth_max
                    ):
                        continue
                    name = (
                        attributes.get("name_en") if is_sarv and self.language == "en"
                        else attributes.get("name") if is_sarv
                        else attributes.get("nimi")
                    ) or attributes.get("name") or attributes.get("alias") or attributes.get("number") or object_id
                    searchable = " ".join(
                        str(value) for value in (
                            name, object_id, attributes.get("number"),
                            attributes.get("gea_id"), attributes.get("land_board_id"),
                        ) if value not in (None, "")
                    ).casefold()
                    if text_query and text_query not in searchable:
                        continue
                    rows.append({
                        "source": "SARV" if is_sarv else "EGT",
                        "type": self.t({
                            "boreholes": "Puurauk",
                            "observations": "Vaatluspunkt",
                            "sarv_localities": "Lokaliteet",
                            "sarv_sites": "Uuringupunkt",
                            "sarv_drillcores": "Puursüdamik",
                        }.get(role, role)),
                        "name": name,
                        "id": object_id,
                        "depth": numeric_depth,
                        "_layer_id": layer.id(),
                        "_feature_id": int(feature.id()),
                        "_role": role,
                    })
                    if len(rows) >= 500:
                        break
                if len(rows) >= 500:
                    break
            if len(rows) >= 500:
                break
        rows.sort(key=lambda row: (
            str(row.get("source")), str(row.get("name") or "").casefold()
        ))
        missing = []
        if wants_egt and "EGT" not in loaded_sources:
            missing.append("EGT")
        if wants_sarv and "SARV" not in loaded_sources:
            missing.append("SARV")
        message = (
            f"{len(rows)} {self.t('tulemust')}"
            + (
                ". " + self.t("Laadi otsimiseks esmalt kihid: ")
                + ", ".join(missing)
                if missing else ""
            )
            + (f". {self.t('Kuvatakse esimesed 500.')}" if len(rows) >= 500 else "")
        )
        callback(rows, message)

    def _resolve_sarv_search_allowed(self, criteria, success, failure):
        candidate = {"locality": set(), "site": set()}
        text_query = str(criteria.get("text") or "").casefold()
        depth_min = criteria.get("depth_min")
        depth_max = criteria.get("depth_max")
        for role in ("sarv_localities", "sarv_sites", "sarv_drillcores"):
            if criteria.get("kinds") is not None and role not in criteria["kinds"]:
                continue
            target = "site" if role == "sarv_sites" else "locality"
            for layer in self._role_layers(role):
                request = QgsFeatureRequest()
                if criteria.get("current_extent"):
                    try:
                        request.setFilterRect(QgsCoordinateTransform(
                            self.iface.mapCanvas().mapSettings().destinationCrs(),
                            layer.crs(), QgsProject.instance(),
                        ).transformBoundingBox(self.iface.mapCanvas().extent()))
                    except QgsCsException:
                        pass
                for feature in layer.getFeatures(request):
                    attributes = {
                        field.name(): feature.attribute(field.name())
                        for field in layer.fields()
                    }
                    name = (
                        attributes.get("name_en") if self.language == "en"
                        else attributes.get("name")
                    ) or attributes.get("name") or attributes.get("number")
                    searchable = " ".join(
                        str(value) for value in (
                            name, attributes.get("number"),
                            attributes.get("sarv_id"),
                            attributes.get("land_board_id"),
                        ) if value not in (None, "")
                    ).casefold()
                    if text_query and text_query not in searchable:
                        continue
                    depth = attributes.get("depth")
                    try:
                        depth = float(depth) if depth not in (None, "") else None
                    except (TypeError, ValueError):
                        depth = None
                    if depth_min is not None and (
                        depth is None or depth < depth_min
                    ):
                        continue
                    if depth_max is not None and (
                        depth is None or depth > depth_max
                    ):
                        continue
                    value = (
                        feature["sarv_id"] if target == "site"
                        else feature["locality_id"]
                    )
                    if value not in (None, ""):
                        candidate[target].add(str(value))
        if not any(candidate.values()):
            success(set())
            return

        conditions = []
        sample_types = {
            value[5:] for value in criteria.get("sample_type", set())
            if value.startswith("sarv:")
        }
        sample_purposes = {
            value[5:] for value in criteria.get("sample_purpose", set())
            if value.startswith("sarv:")
        }
        methods = {
            value[5:] for value in criteria.get("analysis_method", set())
            if value.startswith("sarv:")
        }
        related = criteria.get("related", {})
        sample_requirement = related.get("samples", "any")
        analysis_requirement = related.get("analyses", "any")
        if sample_types or sample_purposes or sample_requirement != "any":
            conditions.append((
                "samples", sample_types, sample_purposes,
                "yes" if sample_types or sample_purposes else sample_requirement,
            ))
        if methods or analysis_requirement != "any":
            conditions.append((
                "analyses", methods, set(),
                "yes" if methods else analysis_requirement,
            ))
        universe = {
            (target, identifier)
            for target, identifiers in candidate.items()
            for identifier in identifiers
        }
        condition_sets = []
        core_requirement = related.get("core", "any")
        if core_requirement != "any":
            core_matches = set()
            for layer in self._role_layers("sarv_drillcores"):
                for feature in layer.getFeatures():
                    locality_id = feature["locality_id"]
                    if locality_id not in (None, ""):
                        core_matches.add(("locality", str(locality_id)))
            core_matches.intersection_update(universe)
            condition_sets.append(
                core_matches if core_requirement == "yes"
                else universe - core_matches
            )
        if not conditions:
            success(set.intersection(*condition_sets) if condition_sets else universe)
            return

        def load_condition(index):
            if index >= len(conditions):
                success(set.intersection(*condition_sets))
                return
            kind, selected, purposes, requirement = conditions[index]
            matches = set()
            requests = []
            for target, values in candidate.items():
                ids = sorted(values)
                for offset in range(0, len(ids), 500):
                    chunk = ids[offset:offset + 500]
                    if kind == "samples":
                        purpose_values = sorted(purposes) or [None]
                        type_values = sorted(selected) or [None]
                        requests.extend(
                            (target, chunk, purpose, sample_type)
                            for purpose in purpose_values
                            for sample_type in type_values
                        )
                    else:
                        requests.append((target, chunk, None, None))
            remaining = {"count": len(requests), "failed": False}

            def completed():
                remaining["count"] -= 1
                if remaining["count"] == 0 and not remaining["failed"]:
                    condition_sets.append(
                        matches if requirement == "yes" else universe - matches
                    )
                    load_condition(index + 1)

            for target, ids, purpose, sample_type in requests:
                if kind == "samples":
                    resource = "samples"
                    parameters = {
                        f"{target}__in": ",".join(ids),
                        "type": sample_type,
                        "purpose": purpose,
                    }
                    fields = ("id", target)
                else:
                    resource = "analyses"
                    parameters = {
                        f"sample__{target}__in": ",".join(ids),
                        "analysis_method__in": ",".join(sorted(selected)),
                    }
                    fields = ("id", "sample")

                def loaded(rows, target=target, kind=kind):
                    if kind == "analyses":
                        sample_ids = {
                            str(row.get("sample"))
                            for row in rows
                            if row.get("sample") not in (None, "")
                        }
                        if not sample_ids:
                            completed()
                            return
                        chunks = [
                            sorted(sample_ids)[offset:offset + 500]
                            for offset in range(0, len(sample_ids), 500)
                        ]
                        parent_pending = {"count": len(chunks)}

                        def parents_loaded(samples):
                            for sample in samples:
                                value = sample.get(target)
                                if isinstance(value, dict):
                                    value = value.get("id")
                                if value not in (None, ""):
                                    matches.add((target, str(value)))
                            parent_pending["count"] -= 1
                            if parent_pending["count"] == 0:
                                completed()

                        def parents_failed(error):
                            if not remaining["failed"]:
                                remaining["failed"] = True
                                failure(error)

                        for chunk in chunks:
                            self.network.query_sarv_pages(
                                "samples", {"id__in": ",".join(chunk)},
                                ("id", target), parents_loaded, parents_failed,
                                limit=5000,
                            )
                        return
                    for row in rows:
                        value = row.get(target)
                        if isinstance(value, dict):
                            value = value.get("id")
                        if value not in (None, ""):
                            matches.add((target, str(value)))
                    completed()

                def failed(error):
                    if not remaining["failed"]:
                        remaining["failed"] = True
                        failure(error)

                self.network.query_sarv_pages(
                    resource, parameters, fields, loaded, failed, limit=5000,
                )

        load_condition(0)

    def open_search_result(self, item):
        layer = QgsProject.instance().mapLayer(item.get("_layer_id"))
        if not layer:
            self.warning(
                "The result layer is no longer loaded." if self.language == "en"
                else "Otsingutulemuse kiht ei ole enam laaditud."
            )
            return
        feature = next(
            layer.getFeatures(
                QgsFeatureRequest().setFilterFid(item.get("_feature_id"))
            ),
            None,
        )
        if feature is None:
            return
        canvas = self.iface.mapCanvas()
        try:
            geometry = QgsGeometry(feature.geometry())
            geometry.transform(QgsCoordinateTransform(
                layer.crs(), canvas.mapSettings().destinationCrs(),
                QgsProject.instance(),
            ))
            point = geometry.asPoint()
            extent = canvas.extent()
            extent.scale(0.25, point)
            canvas.setExtent(extent)
            canvas.refresh()
        except (QgsCsException, ValueError):
            pass
        attributes = {
            field.name(): feature.attribute(field.name())
            for field in layer.fields()
        }
        role = item.get("_role") or self._layer_role(layer)
        self._show_highlight(layer, feature)
        if role.startswith("sarv_"):
            self._load_sarv_point_details(
                role, str(item.get("name") or item.get("id")),
                attributes, layer, feature,
            )
        else:
            global_id = (
                attributes.get("esri_globalid") or attributes.get("globalid")
            )
            if global_id:
                self._load_details(
                    role, str(global_id),
                    str(item.get("name") or item.get("id")), attributes,
                )

    @classmethod
    def _role_layers(cls, role):
        return [
            layer for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
            and layer.customProperty(cls.ROLE_PROPERTY, layer.customProperty(cls.LEGACY_ROLE_PROPERTY, "")) == role
        ]

    # ---- Identify and related EGT data --------------------------------------------

    def set_identify_active(self, checked):
        if not self.identify_tool or self._changing_map_tool:
            return
        self._sync_identify_controls(checked)
        canvas = self.iface.mapCanvas()
        self._changing_map_tool = True
        if checked:
            if canvas.mapTool() is not self.identify_tool:
                self.previous_map_tool = canvas.mapTool()
                canvas.setMapTool(self.identify_tool)
            if self.dock:
                self.dock.tabs.setCurrentWidget(self.dock.filter_page)
                self.dock.show()
        elif canvas.mapTool() is self.identify_tool:
            canvas.setMapTool(self.previous_map_tool) if self.previous_map_tool else canvas.unsetMapTool(self.identify_tool)
        self._changing_map_tool = False

    def identify_tool_deactivated(self):
        if not self._changing_map_tool:
            self._sync_identify_controls(False)

    def _sync_identify_controls(self, checked):
        if self.identify_action:
            self.identify_action.blockSignals(True)
            self.identify_action.setChecked(checked)
            self.identify_action.blockSignals(False)
        if self.dock:
            self.dock.filters.set_identify_checked(checked)

    def identify_at(self, map_point):
        canvas = self.iface.mapCanvas()
        map_crs = canvas.mapSettings().destinationCrs()
        tolerance = canvas.mapUnitsPerPixel() * 8
        click_geometry = QgsGeometry.fromPointXY(map_point)
        best = None
        roles = [
            "boreholes", "observations", "sarv_drillcores",
            "sarv_sites", "sarv_localities",
        ]
        active_layer = self.iface.activeLayer()
        active_role = self._layer_role(active_layer) if active_layer else ""
        if active_role in roles:
            roles.remove(active_role)
            roles.insert(0, active_role)
        for role in roles:
            for layer in self._role_layers(role):
                node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
                if node and not node.isVisible():
                    continue
                try:
                    to_layer = QgsCoordinateTransform(map_crs, layer.crs(), QgsProject.instance())
                    layer_point = to_layer.transform(map_point)
                    layer_tolerance = max(
                        abs(to_layer.transform(map_point.x() + tolerance, map_point.y()).x() - layer_point.x()),
                        abs(to_layer.transform(map_point.x(), map_point.y() + tolerance).y() - layer_point.y()),
                    )
                    request = QgsFeatureRequest().setFilterRect(
                        QgsGeometry.fromPointXY(layer_point).buffer(layer_tolerance, 4).boundingBox()
                    )
                    request.setLimit(30)
                    to_map = QgsCoordinateTransform(layer.crs(), map_crs, QgsProject.instance())
                    for feature in layer.getFeatures(request):
                        feature_attributes = {
                            field.name(): feature.attribute(field.name())
                            for field in layer.fields()
                        }
                        if (
                            role in {"boreholes", "observations"}
                            and not self._passes_related_filter(feature_attributes)
                        ):
                            continue
                        geometry = QgsGeometry(feature.geometry())
                        geometry.transform(to_map)
                        distance = geometry.distance(click_geometry)
                        if best is None or distance < best[0]:
                            best = (distance, role, layer, feature)
                except (QgsCsException, ValueError):
                    continue
        if best is None or best[0] > tolerance:
            self.message(
                "No visible EGT or SARV point was found here." if self.language == "en"
                else "Selles kohas ei leitud nähtavat EGT ega SARV-i punkti."
            )
            return
        _, role, layer, feature = best
        attributes = {field.name(): feature.attribute(field.name()) for field in layer.fields()}
        if role in {
            "sarv_localities", "sarv_sites", "sarv_drillcores",
        }:
            name = (
                attributes.get("name_en") if self.language == "en"
                else attributes.get("name")
            ) or attributes.get("name") or attributes.get("number") or attributes.get("sarv_id")
            self._show_highlight(layer, feature)
            self._load_sarv_point_details(role, str(name), attributes, layer, feature)
            return

        try:
            geometry = QgsGeometry(feature.geometry())
            geometry.transform(QgsCoordinateTransform(
                layer.crs(),
                QgsCoordinateReferenceSystem("EPSG:4326"),
                QgsProject.instance(),
            ))
            point = geometry.asPoint()
            attributes["_qeoloog_longitude"] = point.x()
            attributes["_qeoloog_latitude"] = point.y()
        except (QgsCsException, ValueError):
            pass
        global_id = attributes.get("esri_globalid") or attributes.get("globalid")
        name = attributes.get("nimi") or attributes.get("alias") or attributes.get("gea_id") or ("Borehole" if role == "boreholes" and self.language == "en" else "Puurauk" if role == "boreholes" else "Observation point" if self.language == "en" else "Vaatluspunkt")
        if not global_id:
            self.error("The selected object has no global ID." if self.language == "en" else "Valitud objektil puudub seotud andmete päringuks vajalik globalid.")
            return
        self._show_highlight(layer, feature)
        self._load_details(role, str(global_id), str(name), attributes)

    def _passes_related_filter(self, attributes):
        if not self.dock or len(self.related_index) < 4:
            return True
        object_id = str(
            attributes.get("esri_globalid") or attributes.get("globalid") or ""
        ).upper()
        for key, requirement in self.dock.filters.related_requirements().items():
            if requirement == "any":
                continue
            present = object_id in self.related_index.get(key, set())
            if requirement == "yes" and not present:
                return False
            if requirement == "no" and present:
                return False
        return True

    def _show_highlight(self, layer, feature):
        self._clear_highlight()
        highlight = QgsHighlight(self.iface.mapCanvas(), feature, layer)
        outline = QColor("#e0a21a")
        outline.setAlpha(175)
        fill = QColor("#ffd75a")
        fill.setAlpha(42)
        highlight.setColor(outline)
        highlight.setFillColor(fill)
        highlight.setBuffer(1.8)
        highlight.setMinWidth(0.8)
        highlight.show()
        self.selection_highlight = highlight

    def _clear_highlight(self):
        if self.selection_highlight:
            self.selection_highlight.hide()
            self.selection_highlight = None

    def _load_sarv_point_details(self, role, name, attributes, layer, feature):
        self._detail_token += 1
        token = self._detail_token
        self._detail_warning_token = None
        details = self.dock.details
        self.dock.show_details()
        details.show_loading(name, attributes, role)

        def current(callback):
            return lambda payload: callback(payload) if token == self._detail_token else None

        def failed(label):
            def handler(error):
                if token == self._detail_token:
                    self.warning(
                        f"Could not load {label}: {error}" if self.language == "en"
                        else f"Andmete {label} laadimine ebaõnnestus: {error}"
                    )
            return handler

        sarv_id = attributes.get("sarv_id")
        endpoint = {
            "sarv_localities": "localities",
            "sarv_sites": "sites",
            "sarv_drillcores": "drillcores",
        }.get(role, "localities")

        def entity_loaded(entity):
            if not isinstance(entity, dict):
                failed("SARV")("Invalid response")
                return
            overview = {
                key: self._sarv_overview_value(value)
                for key, value in entity.items()
                if not isinstance(value, list)
            }
            overview["sarv_id"] = entity.get("id")
            overview["source_type"] = {
                "sarv_localities": "locality",
                "sarv_sites": "site",
                "sarv_drillcores": "drillcore",
            }.get(role, "locality")
            display_name = (
                entity.get("name_en") if self.language == "en"
                else entity.get("name")
            ) or entity.get("name") or entity.get("number") or name
            details.show_loading(str(display_name), overview, role)
            details.set_profile([])
            details.set_attachments([])
            details.set_ready(str(display_name))

            locality = (
                entity if role == "sarv_localities"
                else entity.get("locality")
            )
            match_entity = (
                locality if isinstance(locality, dict) else entity
            )
            candidates = self._egt_candidates_for_sarv_point(match_entity)
            confirmed = [item for item in candidates if item.get("confirmed")]
            if len(confirmed) == 1:
                details.add_match_candidates(
                    "Kinnitatud EGT vaste", confirmed, self._open_egt_candidate,
                )
            elif candidates:
                details.add_match_candidates(
                    "Võimalik EGT vaste", candidates[:5], self._open_egt_candidate,
                )

            locality_id = locality.get("id") if isinstance(locality, dict) else locality
            if locality_id:
                self._load_sarv_details(
                    token, {"sarv_id": locality_id}, details, failed,
                    trusted_sarv_id=True,
                    selected_drillcore_id=(
                        sarv_id if role == "sarv_drillcores" else None
                    ),
                )
            else:
                details.set_sarv_core([])
                details.set_sarv_core_images([])
                details.set_sarv_samples([], source="locality")
                details.set_sarv_analyses("sample", [])
                details.set_sarv_analyses("specimen", [])
                details.set_sarv_specimens([])
                details.set_sarv_literature([])
            if role == "sarv_sites":
                self._load_sarv_site_samples(token, sarv_id, details, failed)

        self.network.query_sarv(
            f"{endpoint}/{sarv_id}",
            {"expand": "*"},
            current(entity_loaded),
            failed("SARV"),
        )

    def _load_sarv_site_samples(self, token, site_id, details, failed):
        if not site_id:
            return

        def samples_loaded(payload):
            if token != self._detail_token:
                return
            rows = self._sarv_rows(payload)
            details.set_sarv_samples(rows, source="site")
            ids = [str(row.get("id")) for row in rows if row.get("id")]
            if not ids:
                details.set_sarv_analyses("site_sample", [])
                return
            self.network.query_sarv(
                "analyses",
                {"sample__in": ",".join(ids), "expand": "*", "limit": 1000},
                lambda data: (
                    details.set_sarv_analyses("site_sample", self._sarv_rows(data))
                    if token == self._detail_token else None
                ),
                failed("SARV analyses"),
            )

        self.network.query_sarv(
            "samples",
            {"site": site_id, "expand": "*", "limit": 1000},
            samples_loaded,
            failed("SARV samples"),
        )

    def _egt_candidates_for_sarv_point(self, entity):
        try:
            latitude = float(entity.get("latitude"))
            longitude = float(entity.get("longitude"))
        except (TypeError, ValueError):
            return []
        source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        metric_crs = QgsCoordinateReferenceSystem("EPSG:3301")
        project = QgsProject.instance()
        try:
            sarv_metric = QgsCoordinateTransform(
                source_crs, metric_crs, project,
            ).transform(QgsPointXY(longitude, latitude))
        except QgsCsException:
            return []

        sarv_number = self._normalized(entity.get("number"))
        sarv_name = self._normalized(entity.get("name"))
        sarv_depth = entity.get("depth")
        land_board_id = self._normalized(entity.get("land_board_id"))
        candidates = []
        for role in ("boreholes", "observations"):
            for layer in self._role_layers(role):
                try:
                    point = QgsCoordinateTransform(
                        metric_crs, layer.crs(), project,
                    ).transform(sarv_metric)
                    radius = 0.001 if layer.crs().isGeographic() else 100.0
                    request = QgsFeatureRequest().setFilterRect(QgsRectangle(
                        point.x() - radius, point.y() - radius,
                        point.x() + radius, point.y() + radius,
                    ))
                    features = {
                        feature.id(): feature
                        for feature in layer.getFeatures(request)
                    }
                    if (
                        land_board_id
                        and layer.fields().indexOf("ma_orig_id") >= 0
                    ):
                        literal = (
                            land_board_id
                            if land_board_id.replace(".", "", 1).isdigit()
                            else "'"
                            + land_board_id.replace("'", "''")
                            + "'"
                        )
                        direct_request = QgsFeatureRequest().setFilterExpression(
                            f'"ma_orig_id" = {literal}'
                        )
                        direct_request.setLimit(20)
                        for feature in layer.getFeatures(direct_request):
                            features[feature.id()] = feature
                    for feature in features.values():
                        geometry = QgsGeometry(feature.geometry())
                        geometry.transform(QgsCoordinateTransform(
                            layer.crs(), metric_crs, project,
                        ))
                        distance = geometry.distance(
                            QgsGeometry.fromPointXY(sarv_metric)
                        )
                        attrs = {
                            field.name(): feature.attribute(field.name())
                            for field in layer.fields()
                        }
                        try:
                            wgs_geometry = QgsGeometry(feature.geometry())
                            wgs_geometry.transform(QgsCoordinateTransform(
                                layer.crs(), source_crs, project,
                            ))
                            wgs_point = wgs_geometry.asPoint()
                            attrs["_qeoloog_longitude"] = wgs_point.x()
                            attrs["_qeoloog_latitude"] = wgs_point.y()
                        except (QgsCsException, ValueError):
                            pass
                        egt_numbers = {
                            self._normalized(attrs.get(key))
                            for key in (
                                "nimi", "korrastatud_nr",
                            )
                            if attrs.get(key) not in (None, "")
                        }
                        egt_names = {
                            self._normalized(attrs.get(key))
                            for key in ("nimi", "alias")
                            if attrs.get(key) not in (None, "")
                        }
                        direct = bool(
                            land_board_id
                            and land_board_id
                            == self._normalized(attrs.get("ma_orig_id"))
                        )
                        number_match = bool(
                            sarv_number and sarv_number in egt_numbers
                        )
                        name_match = bool(
                            sarv_name and any(
                                value and (
                                    value == sarv_name
                                    or value in sarv_name
                                    or sarv_name in value
                                )
                                for value in egt_names
                            )
                        )
                        depth_diff = None
                        if (
                            sarv_depth not in (None, "")
                            and attrs.get("pikkus") not in (None, "")
                        ):
                            try:
                                depth_diff = abs(
                                    float(sarv_depth) - float(attrs.get("pikkus"))
                                )
                            except (TypeError, ValueError):
                                pass
                        confirmed = (
                            direct
                            or distance <= 25 and number_match
                            or distance <= 10 and depth_diff is not None and depth_diff <= 1
                        )
                        if not (
                            confirmed or
                            distance <= 100 and (
                                number_match or name_match
                                or depth_diff is not None and depth_diff <= 2
                            )
                        ):
                            continue
                        gea_id = attrs.get("gea_id")
                        object_path = (
                            "puurauk" if role == "boreholes" else "vaatluspunkt"
                        )
                        evidence = [f"{distance:.0f} m"]
                        if direct:
                            evidence.append(self.t("ametlik ID kattub"))
                        if number_match:
                            evidence.append(self.t("number kattub"))
                        if depth_diff is not None:
                            evidence.append(f"Δh {depth_diff:g} m")
                        display = (
                            attrs.get("nimi") or attrs.get("alias")
                            or gea_id or attrs.get("esri_globalid")
                        )
                        candidates.append({
                            "id": attrs.get("esri_globalid") or attrs.get("globalid"),
                            "role": role,
                            "attributes": attrs,
                            "text": str(display),
                            "url": (
                                f"https://gis.egt.ee/auk/{object_path}/{gea_id}/vaade"
                                if gea_id else ""
                            ),
                            "evidence": " · ".join(evidence),
                            "confirmed": confirmed,
                            "score": (
                                1000 if direct else 0
                            ) + (200 if number_match else 0) + (
                                100 if name_match else 0
                            ) + max(0, 100 - distance),
                        })
                except (QgsCsException, ValueError):
                    continue
        candidates.sort(key=lambda item: item["score"], reverse=True)
        confirmed = [item for item in candidates if item["confirmed"]]
        if len(confirmed) != 1:
            for item in candidates:
                item["confirmed"] = False
        return candidates

    def _open_egt_candidate(self, candidate):
        attributes = candidate.get("attributes") or {}
        global_id = candidate.get("id")
        role = candidate.get("role")
        if not global_id or role not in {"boreholes", "observations"}:
            return
        name = (
            attributes.get("nimi") or attributes.get("alias")
            or attributes.get("gea_id") or global_id
        )
        self._load_details(role, str(global_id), str(name), attributes)

    def _sarv_overview_value(self, value):
        if not isinstance(value, dict):
            return value
        if self.language == "en":
            return (
                value.get("name_en") or value.get("value_en")
                or value.get("name") or value.get("value") or value.get("id")
            )
        return (
            value.get("name") or value.get("value")
            or value.get("name_en") or value.get("value_en") or value.get("id")
        )

    def _load_details(self, role, global_id, name, attributes):
        self._detail_token += 1
        token = self._detail_token
        self._detail_warning_token = None
        details = self.dock.details
        self.dock.show_details()
        details.show_loading(name, attributes, role)
        safe_id = global_id.replace("'", "''")
        parent_where = f"puurauk_vaatluspunkt_id = '{safe_id}'"

        def current(callback):
            return lambda payload: callback(payload) if token == self._detail_token else None

        def failed(label):
            def handler(error):
                if token == self._detail_token and self._detail_warning_token != token:
                    self._detail_warning_token = token
                    self.warning((f"Some related data could not be loaded ({label}): {error}" if self.language == "en" else f"Osa seotud andmeid jäi laadimata ({label}): {error}"))
            return handler

        def profile_from_gea(wfs_error):
            if token != self._detail_token:
                return
            if role != "boreholes":
                failed(self.t("Läbilõige"))(wfs_error)
                return

            def gea_failed(gea_error):
                failed(self.t("Läbilõige"))(f"{wfs_error}; {gea_error}")

            self.network.query_borehole_profile(
                global_id,
                current(details.set_profile),
                gea_failed,
            )

        self.network.query_geological_units(
            role,
            global_id,
            current(details.set_profile),
            profile_from_gea,
        )

        self._load_sarv_details(
            token, attributes, details, failed, egt_role=role,
        )

        def core_loaded(payload):
            rows = self._arcgis_rows(payload)
            details.set_core(rows)
            core_ids = [row.get("globalid") for row in rows if row.get("globalid")][:100]
            attachment_where = parent_where
            if core_ids:
                quoted = ", ".join(f"'{str(value).replace(chr(39), chr(39) * 2)}'" for value in core_ids)
                attachment_where += f" OR puursydamik_kastis_id IN ({quoted})"
            self.network.query_auq(15, attachment_where, current(lambda data: self._set_attachments_and_core_images(details, self._arcgis_rows(data))), failed(self.t("Manused")))

        self.network.query_auq(22, parent_where, current(core_loaded), failed(self.t("Puursüdamik")))
        self.network.query_auq(18, parent_where, current(lambda data: details.set_samples(self._arcgis_rows(data))), failed(self.t("Proovid")))

        def analyses_loaded(payload):
            analyses = self._arcgis_rows(payload)
            if not analyses:
                details.set_analyses([])
                return
            ids = [row.get("globalid") for row in analyses if row.get("globalid")]
            if not ids:
                details.set_analyses(analyses)
                return
            quoted = ", ".join(f"'{str(value).replace(chr(39), chr(39) * 2)}'" for value in ids[:500])
            def results_loaded(results_payload):
                grouped = {}
                for result in self._arcgis_rows(results_payload):
                    grouped.setdefault(result.get("analyys_mootmine_id"), []).append(result)
                details.set_analyses(analyses, grouped)
            self.network.query_auq(4, f"analyys_mootmine_id IN ({quoted})", current(results_loaded), failed("analysis results" if self.language == "en" else "analüüsitulemused"))
        self.network.query_auq(3, parent_where, current(analyses_loaded), failed(self.t("Analüüsid")))
        details.set_ready(name)

    def _load_sarv_details(
        self, token, attributes, details, failed, trusted_sarv_id=False,
        egt_role="", selected_drillcore_id=None,
    ):
        def current(callback):
            return lambda payload: callback(payload) if token == self._detail_token else None

        def clear_sarv():
            details.set_sarv_core([])
            details.set_sarv_core_images([])
            details.set_sarv_samples([], source="locality")
            details.set_sarv_analyses("sample", [])
            details.set_sarv_analyses("specimen", [])
            details.set_sarv_specimens([])
            details.set_sarv_literature([])

        def request_failed(label, clear_callback):
            def handler(error):
                if token != self._detail_token:
                    return
                clear_callback()
                failed(label)(error)
            return handler

        def load_locality(locality):
            locality_id = locality.get("id")
            if not locality_id:
                clear_sarv()
                return
            details.set_sarv_locality(locality)

            def drillcores_loaded(payload):
                cores = self._sarv_rows(payload)
                if selected_drillcore_id not in (None, ""):
                    cores = [
                        core for core in cores
                        if str(core.get("id")) == str(selected_drillcore_id)
                    ]
                if not cores:
                    details.set_sarv_core([])
                    details.set_sarv_core_images([])
                    return
                queue = list(cores)
                boxes = []

                def finish_boxes():
                    details.set_sarv_core(boxes)
                    box_ids = [str(row.get("id")) for row in boxes if row.get("id")]
                    if not box_ids:
                        details.set_sarv_core_images([])
                        return
                    self.network.query_sarv(
                        "attachments",
                        {
                            "drillcore_boxes__in": ",".join(box_ids),
                            "expand": "*",
                            "limit": 2000,
                        },
                        current(lambda data: details.set_sarv_core_images(self._sarv_rows(data))),
                        request_failed(
                            "SARV drill core images",
                            lambda: details.set_sarv_core_images([]),
                        ),
                    )

                def load_next_core():
                    if not queue:
                        finish_boxes()
                        return
                    core = queue.pop(0)
                    core_id = core.get("id")
                    if not core_id:
                        load_next_core()
                        return

                    def boxes_loaded(box_payload):
                        for row in self._sarv_rows(box_payload):
                            row = dict(row)
                            row["_drillcore_name"] = (
                                core.get("name_en") if self.language == "en"
                                else core.get("name")
                            ) or core.get("name") or core.get("id")
                            row["_drillcore_storage"] = (
                                core.get("location") or core.get("depository")
                                or core.get("storage")
                            )
                            boxes.append(row)
                        load_next_core()

                    def boxes_failed(error):
                        if token != self._detail_token:
                            return
                        failed("SARV drill core boxes")(error)
                        load_next_core()

                    self.network.query_sarv(
                        f"drillcores/{core_id}/drillcore-boxes",
                        {"expand": "*", "limit": 2000, "ordering": "depth_start"},
                        current(boxes_loaded),
                        boxes_failed,
                    )

                load_next_core()

            def samples_loaded(payload):
                rows = self._sarv_rows(payload)
                details.set_sarv_samples(rows, source="locality")
                ids = [str(row.get("id")) for row in rows if row.get("id")]
                if not ids:
                    details.set_sarv_analyses("sample", [])
                    return
                self.network.query_sarv(
                    "analyses",
                    {"sample__in": ",".join(ids), "expand": "*", "limit": 1000},
                    current(lambda data: details.set_sarv_analyses("sample", self._sarv_rows(data))),
                    request_failed("SARV samples", lambda: details.set_sarv_analyses("sample", [])),
                )

            def specimens_loaded(payload):
                rows = self._sarv_rows(payload)
                details.set_sarv_specimens(rows)
                ids = [str(row.get("id")) for row in rows if row.get("id")]
                if not ids:
                    details.set_sarv_analyses("specimen", [])
                    return
                self.network.query_sarv(
                    "analyses",
                    {"specimen__in": ",".join(ids), "expand": "*", "limit": 1000},
                    current(lambda data: details.set_sarv_analyses("specimen", self._sarv_rows(data))),
                    request_failed("SARV specimens", lambda: details.set_sarv_analyses("specimen", [])),
                )

            self.network.query_sarv(
                "drillcores", {"locality": locality_id, "expand": "*", "limit": 100},
                current(drillcores_loaded),
                request_failed(
                    "SARV drill cores",
                    lambda: (details.set_sarv_core([]), details.set_sarv_core_images([])),
                ),
            )
            self.network.query_sarv(
                "samples", {"locality": locality_id, "expand": "*", "limit": 1000},
                current(samples_loaded),
                request_failed(
                    "SARV samples",
                    lambda: details.set_sarv_samples([], source="locality"),
                ),
            )
            self.network.query_sarv(
                "specimens", {"locality": locality_id, "expand": "*", "limit": 1000},
                current(specimens_loaded),
                request_failed("SARV specimens", lambda: details.set_sarv_specimens([])),
            )
            self.network.query_sarv(
                f"localities/{locality_id}/locality-references",
                {"expand": "*", "limit": 1000},
                current(lambda data: details.set_sarv_literature(self._sarv_rows(data))),
                request_failed("SARV literature", lambda: details.set_sarv_literature([])),
            )

        sarv_id = str(attributes.get("sarv_id") or "").strip()
        if trusted_sarv_id and sarv_id.isdigit():
            self.network.query_sarv(
                f"localities/{sarv_id}", {}, current(load_locality),
                request_failed("SARV locality", clear_sarv),
            )
            return

        match_key = self._egt_match_key(egt_role, attributes)

        def open_candidate(candidate):
            source_type = candidate.get("source_type")
            role = (
                "sarv_sites" if source_type == "site" else "sarv_localities"
            )
            row = dict(candidate.get("row") or {})
            row["sarv_id"] = candidate.get("sarv_id")
            self._load_sarv_point_details(
                role, str(candidate.get("text") or candidate.get("sarv_id")),
                row, None, None,
            )

        def load_candidate(candidate):
            source_type = candidate.get("source_type")
            source_id = candidate.get("sarv_id")
            if source_type == "site":
                def site_loaded(site):
                    if token != self._detail_token or not isinstance(site, dict):
                        return
                    locality = site.get("locality")
                    locality_id = (
                        locality.get("id") if isinstance(locality, dict)
                        else locality
                    )
                    if locality_id:
                        self.network.query_sarv(
                            f"localities/{locality_id}", {"expand": "*"},
                            current(load_locality),
                            request_failed("SARV locality", clear_sarv),
                        )
                    self._load_sarv_site_samples(
                        token, source_id, details, failed,
                    )

                self.network.query_sarv(
                    f"sites/{source_id}", {"expand": "*"},
                    current(site_loaded),
                    request_failed("SARV site", clear_sarv),
                )
            else:
                self.network.query_sarv(
                    f"localities/{source_id}", {"expand": "*"},
                    current(load_locality),
                    request_failed("SARV locality", clear_sarv),
                )

        def remove_manual(candidate):
            if match_key:
                self.sarv_matches.pop(match_key, None)
                PluginSettings.save_sarv_matches(self.sarv_matches)
            self.success(
                "Manual SARV match removed. Reopen the EGT point to find candidates."
                if self.language == "en" else
                "Käsitsi kinnitatud SARV vaste eemaldati. Kandidaatide leidmiseks ava EGT punkt uuesti."
            )

        def confirm_candidate(candidate):
            if not match_key:
                return
            self.sarv_matches[match_key] = {
                "source_type": candidate.get("source_type"),
                "sarv_id": candidate.get("sarv_id"),
            }
            PluginSettings.save_sarv_matches(self.sarv_matches)
            candidate["confirmed"] = True
            candidate["manual"] = True
            candidate["evidence"] = self.t("Käsitsi kinnitatud")
            self.success(
                "SARV match saved." if self.language == "en"
                else "SARV vaste salvestati."
            )
            load_candidate(candidate)

        def cache_loaded(localities, sites, drillcores):
            if token != self._detail_token:
                return
            candidates = self._sarv_candidates_for_egt(
                localities, sites, attributes,
            )
            saved = self.sarv_matches.get(match_key) if match_key else None
            if isinstance(saved, dict):
                manual = next((
                    item for item in candidates
                    if item.get("source_type") == saved.get("source_type")
                    and str(item.get("sarv_id")) == str(saved.get("sarv_id"))
                ), None)
                if manual is None:
                    source_rows = (
                        sites if saved.get("source_type") == "site"
                        else localities
                    )
                    row = next((
                        item for item in source_rows
                        if str(item.get("id")) == str(saved.get("sarv_id"))
                    ), None)
                    if row:
                        manual = self._sarv_candidate(
                            row, saved.get("source_type"), attributes,
                            allow_weak=True,
                        )
                if manual:
                    manual["confirmed"] = True
                    manual["manual"] = True
                    manual["evidence"] = self.t("Käsitsi kinnitatud")
                    details.add_match_candidates(
                        "Kinnitatud SARV vaste", [manual],
                        open_candidate, remove_callback=remove_manual,
                    )
                    load_candidate(manual)
                    return
                self.sarv_matches.pop(match_key, None)
                PluginSettings.save_sarv_matches(self.sarv_matches)

            confirmed = [
                candidate for candidate in candidates
                if candidate.get("confirmed")
            ]
            if len(confirmed) == 1:
                details.add_match_candidates(
                    "Kinnitatud SARV vaste", confirmed, open_candidate,
                )
                load_candidate(confirmed[0])
                return
            clear_sarv()
            if candidates:
                details.add_match_candidates(
                    "Võimalik SARV vaste", candidates[:5], open_candidate,
                    confirm_callback=confirm_candidate,
                )

        self._ensure_sarv_point_cache(
            cache_loaded,
            request_failed("SARV locations", clear_sarv),
        )

    def _sarv_candidates_for_egt(self, localities, sites, attributes):
        candidates = []
        for source_type, rows in (
            ("locality", localities), ("site", sites),
        ):
            for row in rows:
                candidate = self._sarv_candidate(
                    row, source_type, attributes,
                )
                if candidate:
                    candidates.append(candidate)
        candidates.sort(key=lambda item: item["score"], reverse=True)
        confirmed = [item for item in candidates if item["confirmed"]]
        if len(confirmed) != 1:
            for item in candidates:
                item["confirmed"] = False
        return candidates

    def _sarv_candidate(
        self, row, source_type, attributes, allow_weak=False,
    ):
        candidate_id = row.get("id")
        if candidate_id in (None, ""):
            return None
        egt_numbers = {
            self._normalized(attributes.get(key))
            for key in ("nimi", "korrastatud_nr")
            if attributes.get(key) not in (None, "")
        }
        egt_names = {
            self._normalized(attributes.get(key))
            for key in ("nimi", "alias")
            if attributes.get(key) not in (None, "")
        }
        row_number = self._normalized(row.get("number"))
        row_name = self._normalized(row.get("name"))
        generic_name_tokens = {
            "auk", "borehole", "drillhole", "kaev", "locality",
            "puurauk", "site", "uuringupunkt",
        }
        meaningful_name_tokens = {
            token.strip(".,;:()[]")
            for token in row_name.split()
            if len(token.strip(".,;:()[]")) >= 3
            and any(
                character.isalpha()
                for character in token.strip(".,;:()[]")
            )
            and token.strip(".,;:()[]") not in generic_name_tokens
        }
        descriptive_name_match = bool(
            meaningful_name_tokens
            and any(
                token in value
                for token in meaningful_name_tokens
                for value in egt_names
            )
        )
        number_match = bool(row_number and row_number in egt_numbers)
        name_match = descriptive_name_match or bool(
            row_name
            and any(character.isalpha() for character in row_name)
            and row_name in egt_names
        )
        official_id = self._normalized(row.get("land_board_id"))
        official_match = bool(
            official_id
            and official_id == self._normalized(attributes.get("ma_orig_id"))
        )
        explicit_match = (
            str(attributes.get("sarv_id") or "").strip() == str(candidate_id)
        )
        distance = self._point_distance_m(
            attributes.get("_qeoloog_latitude"),
            attributes.get("_qeoloog_longitude"),
            row.get("latitude"),
            row.get("longitude"),
        )
        depth_diff = None
        egt_depth = (
            attributes.get("pikkus") or attributes.get("vertikaalne_ulatus")
        )
        if egt_depth not in (None, "") and row.get("depth") not in (None, ""):
            try:
                depth_diff = abs(float(egt_depth) - float(row.get("depth")))
            except (TypeError, ValueError):
                pass

        confirmed = bool(
            official_match
            or distance is not None and distance <= 25 and number_match
            or distance is not None and distance <= 10
            and depth_diff is not None and depth_diff <= 1
            or explicit_match and distance is not None and distance <= 50
        )
        possible = bool(
            confirmed
            or distance is not None and distance <= 250 and (
                number_match or name_match
                or depth_diff is not None and depth_diff <= 5
            )
            or explicit_match and (
                distance is not None and distance <= 250
                or distance is None and (number_match or name_match)
            )
            or distance is None and number_match
            and descriptive_name_match
        )
        if not possible and not allow_weak:
            return None
        evidence = []
        if distance is not None:
            evidence.append(f"{distance:.0f} m")
        if official_match:
            evidence.append(self.t("ametlik ID kattub"))
        elif explicit_match:
            evidence.append(self.t("SARV ID kattub"))
        if number_match:
            evidence.append(self.t("number kattub"))
        if name_match:
            evidence.append(self.t("nimi kattub"))
        if depth_diff is not None:
            evidence.append(f"Δh {depth_diff:g} m")
        display = (
            row.get("name_en") if self.language == "en" else row.get("name")
        ) or row.get("name") or row.get("number") or candidate_id
        source_label = self.t(
            "uuringupunkt" if source_type == "site" else "lokaliteet"
        )
        locality = row.get("locality")
        locality_id = (
            locality.get("id") if isinstance(locality, dict) else locality
        )
        return {
            "source_type": source_type,
            "sarv_id": candidate_id,
            "locality_id": (
                candidate_id if source_type == "locality" else locality_id
            ),
            "row": row,
            "text": f"{display} ({source_label}, ID {candidate_id})",
            "url": f"https://geoloogia.info/{source_type}/{candidate_id}",
            "evidence": " · ".join(evidence),
            "confirmed": confirmed,
            "score": (
                2000 if official_match else 0
            ) + (500 if explicit_match else 0) + (
                250 if number_match else 0
            ) + (120 if name_match else 0) + (
                max(0, 250 - distance) if distance is not None else 0
            ) + (
                max(0, 50 - 10 * depth_diff)
                if depth_diff is not None else 0
            ),
        }

    @staticmethod
    def _point_distance_m(latitude_1, longitude_1, latitude_2, longitude_2):
        try:
            point_1 = QgsPointXY(float(longitude_1), float(latitude_1))
            point_2 = QgsPointXY(float(longitude_2), float(latitude_2))
        except (TypeError, ValueError):
            return None
        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        metric = QgsCoordinateReferenceSystem("EPSG:3301")
        try:
            transform = QgsCoordinateTransform(
                crs, metric, QgsProject.instance(),
            )
            return transform.transform(point_1).distance(
                transform.transform(point_2)
            )
        except QgsCsException:
            return None

    @staticmethod
    def _egt_match_key(role, attributes):
        gea_id = str(attributes.get("gea_id") or "").strip()
        if gea_id:
            return f"{role}:gea:{gea_id}"
        global_id = str(
            attributes.get("esri_globalid")
            or attributes.get("globalid") or ""
        ).strip().upper()
        return f"{role}:global:{global_id}" if global_id else ""

    @staticmethod
    def _normalized(value):
        text = normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
        return " ".join(text.casefold().split())

    @staticmethod
    def _arcgis_rows(payload):
        if not isinstance(payload, dict) or payload.get("error"):
            return []
        return [feature.get("attributes", {}) for feature in payload.get("features", [])]

    @staticmethod
    def _sarv_rows(payload):
        return payload.get("results", []) if isinstance(payload, dict) else []

    @staticmethod
    def _set_attachments_and_core_images(details, rows):
        details.set_attachments(rows)
        details.set_core_images(rows)

    # ---- Messages -----------------------------------------------------------------

    def message(self, text): self._push_message(text, Qgis.MessageLevel.Info)
    def success(self, text): self._push_message(text, Qgis.MessageLevel.Success)
    def warning(self, text): self._push_message(text, Qgis.MessageLevel.Warning, 8)
    def error(self, text): self._push_message(text, Qgis.MessageLevel.Critical, 8)

    def _push_message(self, text, level, duration=4):
        self.iface.messageBar().pushMessage("Qeoloog", text, level=level, duration=duration)
