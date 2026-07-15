"""Qeoloog - configurable Estonian geoscience layers and borehole explorer."""

from pathlib import Path
from unicodedata import normalize
from urllib.parse import quote

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from qgis.PyQt.QtWidgets import QMenu, QToolButton
from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateTransform,
    QgsCsException,
    QgsDataSourceUri,
    QgsFeatureRequest,
    QgsGeometry,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsRasterLayer,
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

    def t(self, text):
        return translate(text, self.language)

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
                self._code_icon(definition.code, definition.color),
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
            self._code_icon("i", "#4c6678"), self.t("EGT objekti andmed"), self.iface.mainWindow()
        )
        self.identify_action.setCheckable(True)
        self.identify_action.setToolTip(
            self.t("Klõpsa puuraugul või vaatluspunktil ja ava seotud andmed")
        )
        self.identify_action.toggled.connect(self.set_identify_active)
        self._register_action(self.identify_action)
        if identify_was_active:
            self._sync_identify_controls(True)

        self.configure_action = QAction(
            self._code_icon("⚙", "#555f69"), self.t("Seadista Qeoloogi"), self.iface.mainWindow()
        )
        self.configure_action.setToolTip(self.t("Lisa, muuda või eemalda WMS/WFS kihte"))
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
                    self._code_icon(definition.code, definition.color),
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
                layer.setName(self.display_name(definition))

    def _save_definitions(self):
        PluginSettings.save_layers(self.definitions)
        self._build_actions()

    @staticmethod
    def _code_icon(code, color):
        pixmap = QPixmap(36, 36)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color) if QColor(color).isValid() else QColor("#356a8a"))
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
        QTimer.singleShot(0, self.sync_dropdown_checks)

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
                self._code_icon(definition.code, definition.color),
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
                project.removeMapLayers(ids)
                self.success(
                    f"{self.display_name(definition)} "
                    + ("removed." if self.language == "en" else "eemaldatud.")
                )
        self.sync_dropdown_checks()

    def add_layer(self, definition, force_add=False):
        source_id = self._source_id(definition)
        name = self.display_name(definition)
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if self._layer_source_id(layer) == source_id:
                if self.toggle_mode and not force_add:
                    project.removeMapLayer(layer.id())
                    self.success(f"{name} " + ("removed." if self.language == "en" else "eemaldatud."))
                    return False
                node = project.layerTreeRoot().findLayer(layer.id())
                if node:
                    node.setItemVisibilityChecked(True)
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
        self.iface.setActiveLayer(layer)
        if definition.role:
            self.apply_egt_filters()
        self.success(f"{name} " + ("added." if self.language == "en" else "lisatud."))
        self.sync_dropdown_checks()
        return True

    @staticmethod
    def _source_id(definition):
        return "|".join((definition.protocol.upper(), definition.url, definition.layer_name, definition.style))

    @classmethod
    def _layer_source_id(cls, layer):
        return layer.customProperty(
            cls.SOURCE_PROPERTY,
            layer.customProperty(cls.LEGACY_SOURCE_PROPERTY, ""),
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
        return uri.uri(False)

    def _apply_category_renderer(self, layer, related_expression=""):
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
                expression = f"({category_expression}) AND ({related_expression})"
            rule = QgsRuleBasedRenderer.Rule(symbol)
            rule.setLabel(self.t(labels[code]))
            rule.setFilterExpression(expression)
            root_rule.appendChild(rule)
        layer.setRenderer(QgsRuleBasedRenderer(root_rule))
        layer.triggerRepaint()

    @staticmethod
    def _apply_borehole_labeling(layer):
        if layer.fields().indexOf("nimi") < 0:
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
        settings.fieldName = "nimi"
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
                self.dock.tabs.setCurrentWidget(self.dock.filters)
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
        for role in ("boreholes", "observations"):
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
                        if not self._passes_related_filter(feature_attributes):
                            continue
                        geometry = QgsGeometry(feature.geometry())
                        geometry.transform(to_map)
                        distance = geometry.distance(click_geometry)
                        if best is None or distance < best[0]:
                            best = (distance, role, layer, feature)
                except (QgsCsException, ValueError):
                    continue
        if best is None or best[0] > tolerance:
            self.message("No visible borehole or observation point was found here." if self.language == "en" else "Selles kohas ei leitud nähtavat puurauku ega vaatluspunkti.")
            return
        _, role, layer, feature = best
        attributes = {field.name(): feature.attribute(field.name()) for field in layer.fields()}
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

        def profile_from_wfs(api_error=None):
            def wfs_failed(wfs_error):
                failed(self.t("Läbilõige"))(wfs_error if api_error is None else f"{api_error}; {wfs_error}")
            self.network.query_geological_units(role, global_id, current(details.set_profile), wfs_failed)

        if role == "boreholes":
            self.network.query_borehole_profile(global_id, current(details.set_profile), profile_from_wfs)
        else:
            profile_from_wfs()

        self._load_sarv_details(token, attributes, details, failed)

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

    def _load_sarv_details(self, token, attributes, details, failed):
        def current(callback):
            return lambda payload: callback(payload) if token == self._detail_token else None

        def clear_sarv():
            details.set_sarv_core([])
            details.set_sarv_core_images([])
            details.set_sarv_samples([])
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
                details.set_sarv_samples(rows)
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
                request_failed("SARV samples", lambda: details.set_sarv_samples([])),
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

        def candidates_loaded(payload, allow_name_fallback=True):
            rows = self._sarv_rows(payload)
            locality = self._match_sarv_locality(rows, attributes)
            if locality:
                load_locality(locality)
                return
            alias = str(attributes.get("alias") or "").strip()
            if allow_name_fallback and alias:
                self.network.query_sarv(
                    "localities", {"name__icontains": alias, "limit": 50},
                    current(lambda data: candidates_loaded(data, False)),
                    request_failed("SARV locality", clear_sarv),
                )
            else:
                clear_sarv()

        sarv_id = str(attributes.get("sarv_id") or "").strip()
        if sarv_id.isdigit():
            self.network.query_sarv(
                f"localities/{sarv_id}", {}, current(load_locality),
                request_failed("SARV locality", clear_sarv),
            )
            return
        number = str(
            attributes.get("nimi") or attributes.get("korrastatud_nr")
            or attributes.get("ma_orig_id") or ""
        ).strip()
        alias = str(attributes.get("alias") or "").strip()
        parameters = {"limit": 50}
        if number:
            parameters["number__iexact"] = number
        if alias and self._normalized(alias) != self._normalized(number):
            parameters["name__icontains"] = alias
        if len(parameters) == 1:
            clear_sarv()
            return
        self.network.query_sarv(
            "localities", parameters, current(candidates_loaded),
            request_failed("SARV locality", clear_sarv),
        )

    @classmethod
    def _match_sarv_locality(cls, rows, attributes):
        if len(rows) == 1:
            return rows[0]
        number = cls._normalized(
            attributes.get("nimi") or attributes.get("korrastatud_nr")
            or attributes.get("ma_orig_id")
        )
        alias = cls._normalized(attributes.get("alias"))
        matches = []
        for row in rows:
            candidate_number = cls._normalized(row.get("number"))
            candidate_name = cls._normalized(row.get("name"))
            number_ok = not number or candidate_number == number
            name_ok = not alias or alias in candidate_name
            if number_ok and name_ok:
                matches.append(row)
        return matches[0] if len(matches) == 1 else None

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
