"""Qeoloog - configurable Estonian geoscience layers and borehole explorer."""

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from unicodedata import normalize
from urllib.parse import quote

from qgis.PyQt.QtCore import Qt, QTimer, QVariant
from qgis.PyQt.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import QMenu, QToolButton
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsDataSourceUri,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGraduatedSymbolRenderer,
    QgsExpressionContextUtils,
    QgsGeometry,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsPointXY,
    QgsRasterLayer,
    QgsRectangle,
    QgsRendererRange,
    QgsRuleBasedRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsHighlight, QgsRubberBand

from .corrections import (
    apply_core_values,
    changed_core_values,
    core_correction_key,
    core_record_id,
    core_values,
)
from .dock import QeoloogDock
from .i18n import GROUP_LABELS, translate
from .identify import CrossSectionLineTool, EgtIdentifyTool, ExportAreaTool
from .models import DEFAULT_GROUP_STATE, GROUPS, PluginSettings
from .network import NetworkClient
from .veka import (
    FILTER_CONSTRUCTION_TYPES,
    aggregate as veka_aggregate,
    analysis_codes,
    analysis_matches as veka_analysis_matches,
    analysis_options as veka_analysis_options,
    analysis_row_value,
    cadastral_number as veka_cadastral_number,
    construction_category,
    converted_result as veka_converted_result,
    split_analysis_key,
    equal_breaks,
    group_rows,
    hydro_matches as veka_hydro_matches,
    interval_intersects,
    kotkas_registry_url,
    latest_static_water_level,
    merge_water_analyses,
    number as veka_number,
    normalized_analysis_number,
    parse_kotkas_protocols,
    parse_kotkas_report_registry,
    parse_veka_water_analyses,
    quantile_breaks,
    specific_capacity,
)


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
    SARV_SPECIMEN_TYPES = {
        1: ("tervik", "single specimen"),
        2: ("tervik osadena", "specimen in parts"),
        3: ("terviku osa", "part of specimen"),
        4: ("õhik / piil", "thin section / peel"),
        5: ("mikrof. kaameras", "microfossil"),
        6: ("mikrof. SEM alusel", "microfossil on SEM stub"),
        7: ("mitu eksemplari", "multiple specimens"),
        9: ("poleerlihv", "polished slab"),
    }
    AK_CORRECTED_EXTENT = QgsRectangle(369548.1875, 6380032.5, 739208.1875, 6653113.0)
    VEKA_MAIN_FIELDS = (
        "id", "tyyp", "tyyp_selg", "nimi", "keht_staatus", "kkr_kood",
        "maayksus", "maayksus_nimi", "katastri_nr", "pass_nr", "seire_nr",
        "pohjaveekogum_id", "pohjaveekogum_nimi", "veekiht",
        "veekiht_nimi", "aadress", "z_abs", "sygavus", "kasutus_selg",
        "puur_aasta", "kesk_x", "kesk_y", "muut_aeg",
    )

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self.definitions = PluginSettings.load_layers()
        self.toggle_mode = PluginSettings.load_toggle_mode()
        self.language = PluginSettings.load_language()
        self.egt_data_source = PluginSettings.load_egt_data_source()
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
        self.cross_section_line_tool = None
        self.cross_section_map_band = None
        self.cross_section_previous_tool = None
        self.export_area_tool = None
        self.export_area_band = None
        self.export_area_previous_tool = None
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
        self._egt_stratigraphic_filter_key = None
        self._egt_stratigraphic_filter_allowed = None
        self._egt_stratigraphic_filter_loading = None
        self._egt_stratigraphic_filter_generation = 0
        self._sarv_points_loading = False
        self._sarv_point_cache = None
        self._sarv_point_waiters = []
        self.sarv_analysis_options = []
        self.sarv_sample_type_options = []
        language_index = 1 if self.language == "en" else 0
        self.sarv_specimen_type_options = [
            (str(code), labels[language_index])
            for code, labels in self.SARV_SPECIMEN_TYPES.items()
        ]
        self._sarv_filter_generation = 0
        self.sarv_matches = PluginSettings.load_sarv_matches()
        self.core_corrections = PluginSettings.load_core_corrections()
        self.veka_style = PluginSettings.load_veka_style()
        self._veka_rows = {}
        self._veka_fids = {}
        self._veka_loading = False
        self._veka_aux = {
            "construction": None,
            "hydro": None,
            "analysis_catalog": None,
        }
        self._veka_aux_loading = set()
        self._veka_grouped = {}
        self._veka_aux_waiters = {
            "construction": [],
            "hydro": [],
            "analysis_catalog": [],
        }
        self._veka_analysis_rows = {}
        self._veka_analysis_loading = set()
        self._veka_analysis_waiters = {}
        self._veka_analysis_grouped = {}
        self._veka_filter_generation = 0
        self._search_filter = None

    def t(self, text):
        return translate(text, self.language)

    def export_sarv_matches(self, path):
        """Export all locally persisted EGT–SARV corrections as CSV or JSON."""
        rows = []
        for match_key, value in sorted(self.sarv_matches.items()):
            if not isinstance(value, dict):
                continue
            key_parts = str(match_key).split(":", 2)
            role = key_parts[0] if key_parts else ""
            key_type = key_parts[1] if len(key_parts) > 1 else ""
            egt_id = key_parts[2] if len(key_parts) > 2 else ""
            object_type = value.get("source_type") or ""
            object_id = value.get("sarv_id") or ""
            rows.append({
                "egt_role": role,
                "egt_key_type": key_type,
                "egt_id": egt_id,
                "gea_id": value.get("gea_id") or (
                    egt_id if key_type == "gea" else ""
                ),
                "original_gea_sarv_id": value.get("original_sarv_id") or "",
                "original_ma_orig_id": value.get("original_ma_id") or "",
                "invalid_original_sarv_id": bool(
                    value.get("invalid_sarv_id")
                ),
                "invalid_land_board_id": bool(value.get("invalid_ma_id")),
                "sarv_object_type": object_type,
                "sarv_object_id": object_id,
                "sarv_drillcore_id": (
                    object_id if object_type == "drillcore" else ""
                ),
                "source": value.get("source") or "local_override",
                "updated_at": value.get("updated_at") or "",
            })
        target = Path(path)
        if target.suffix.casefold() == ".json":
            target.write_text(
                json.dumps({
                    "format": "Qeoloog EGT–SARV link corrections",
                    "version": 2,
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "links": rows,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            if target.suffix.casefold() != ".csv":
                target = target.with_suffix(".csv")
            fieldnames = (
                "egt_role", "egt_key_type", "egt_id", "gea_id",
                "original_gea_sarv_id", "original_ma_orig_id",
                "invalid_original_sarv_id", "invalid_land_board_id",
                "sarv_object_type",
                "sarv_object_id", "sarv_drillcore_id", "source",
                "updated_at",
            )
            with target.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        self.success(
            f"Exported {len(rows)} SARV links to {target}."
            if self.language == "en" else
            f"Eksporditi {len(rows)} SARV seost faili {target}."
        )
        return target

    def corrected_core_box(self, source, row):
        """Apply a locally persisted correction to an upstream core-box row."""
        key = core_correction_key(source, row)
        correction = self.core_corrections.get(key, {})
        changes = (
            correction.get("changes", {})
            if isinstance(correction, dict) else {}
        )
        return apply_core_values(source, row, changes)

    def save_core_box_correction(
        self, source, row, corrected, context=None,
    ):
        """Persist changed core-box values locally without touching upstream."""
        key = core_correction_key(source, row)
        if not key:
            return False
        original = core_values(source, row)
        changes = changed_core_values(original, corrected or {})
        if not changes:
            self.core_corrections.pop(key, None)
        else:
            context = context or {}
            self.core_corrections[key] = {
                "source": str(source).upper(),
                "record_id": core_record_id(source, row),
                "parent_role": context.get("parent_role") or "",
                "parent_id": context.get("parent_id") or "",
                "parent_name": context.get("parent_name") or "",
                "original": original,
                "changes": changes,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        PluginSettings.save_core_corrections(self.core_corrections)
        if self.dock and hasattr(self.dock, "export"):
            self.dock.export.refresh_corrections_count()
        return bool(changes)

    def reset_core_box_correction(self, source, row):
        key = core_correction_key(source, row)
        if not key or key not in self.core_corrections:
            return False
        self.core_corrections.pop(key, None)
        PluginSettings.save_core_corrections(self.core_corrections)
        if self.dock and hasattr(self.dock, "export"):
            self.dock.export.refresh_corrections_count()
        return True

    def export_core_corrections(self, path):
        """Export all local drill-core box corrections as JSON or CSV."""
        records = [
            value for _, value in sorted(self.core_corrections.items())
            if isinstance(value, dict)
        ]
        target = Path(path)
        if target.suffix.casefold() == ".json":
            target.write_text(
                json.dumps({
                    "format": "Qeoloog local drill-core box corrections",
                    "version": 1,
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "corrections": records,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            if target.suffix.casefold() != ".csv":
                target = target.with_suffix(".csv")
            rows = []
            for record in records:
                original = record.get("original", {})
                for field, corrected in record.get("changes", {}).items():
                    rows.append({
                        "source": record.get("source") or "",
                        "record_id": record.get("record_id") or "",
                        "parent_role": record.get("parent_role") or "",
                        "parent_id": record.get("parent_id") or "",
                        "parent_name": record.get("parent_name") or "",
                        "field": field,
                        "original_value": original.get(field),
                        "corrected_value": corrected,
                        "updated_at": record.get("updated_at") or "",
                    })
            fieldnames = (
                "source", "record_id", "parent_role", "parent_id",
                "parent_name", "field", "original_value",
                "corrected_value", "updated_at",
            )
            with target.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        self.success(
            f"Exported {len(records)} core-box corrections to {target}."
            if self.language == "en" else
            f"Eksporditi {len(records)} puursüdamiku parandust faili {target}."
        )
        return target

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
        self.cross_section_line_tool = CrossSectionLineTool(
            self.iface.mapCanvas()
        )
        self.cross_section_line_tool.lineFinished.connect(
            self._cross_section_line_finished
        )
        self.cross_section_line_tool.cancelled.connect(
            self._cross_section_line_cancelled
        )
        self.cross_section_map_band = QgsRubberBand(
            self.iface.mapCanvas(), Qgis.GeometryType.Line
        )
        self.cross_section_map_band.setColor(QColor("#d04432"))
        self.cross_section_map_band.setWidth(3)
        self.cross_section_map_band.setZValue(9999)
        self.cross_section_map_band.hide()
        self.export_area_tool = ExportAreaTool(self.iface.mapCanvas())
        self.export_area_tool.areaFinished.connect(
            self._export_area_finished
        )
        self.export_area_tool.cancelled.connect(
            self._export_area_cancelled
        )
        self.export_area_band = QgsRubberBand(
            self.iface.mapCanvas(), Qgis.GeometryType.Polygon
        )
        self.export_area_band.setColor(QColor(53, 132, 228, 45))
        self.export_area_band.setStrokeColor(QColor("#3584e4"))
        self.export_area_band.setWidth(2)
        self.export_area_band.setZValue(9998)
        self.export_area_band.hide()
        QTimer.singleShot(0, self.dock.cross_sections.refresh)
        QTimer.singleShot(
            0, self.dock.cross_sections.backfill_egt_elevations
        )
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
        if (
            self.cross_section_line_tool
            and self.iface.mapCanvas().mapTool()
            is self.cross_section_line_tool
        ):
            self.iface.mapCanvas().unsetMapTool(self.cross_section_line_tool)
        if (
            self.export_area_tool
            and self.iface.mapCanvas().mapTool() is self.export_area_tool
        ):
            self.iface.mapCanvas().unsetMapTool(self.export_area_tool)
        if self.cross_section_map_band:
            self.cross_section_map_band.reset(Qgis.GeometryType.Line)
            self.cross_section_map_band.hide()
        if self.export_area_band:
            self.export_area_band.reset(Qgis.GeometryType.Polygon)
            self.export_area_band.hide()
        self._clear_actions()
        if self.dock:
            self.dock.export.cancel_pending()
            self.dock.close_cross_sections()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.toolbar:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        self.identify_tool = None
        self.cross_section_line_tool = None
        self.cross_section_map_band = None
        self.cross_section_previous_tool = None
        self.export_area_tool = None
        self.export_area_band = None
        self.export_area_previous_tool = None

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
            self.t("Klõpsa EGT, SARV või VEKA punktil ja ava seotud andmed")
        )
        self.identify_action.toggled.connect(self.set_identify_active)
        self._register_action(self.identify_action)
        if identify_was_active:
            self._sync_identify_controls(True)

        self.configure_action = QAction(
            self._code_icon("⚙", "#555f69"), self.t("Seadista Qeoloogi"), self.iface.mainWindow()
        )
        self.configure_action.setToolTip(
            self.t("Lisa, muuda või eemalda WMS/WFS/SARV/VEKA kihte")
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

    def set_egt_data_source(self, source):
        if source not in {"wfs", "api"}:
            return
        self.egt_data_source = source
        PluginSettings.save_egt_data_source(source)

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
        if self.dock:
            self.dock.cross_sections.reload_rasters()
            self.dock.cross_sections.backfill_egt_elevations()

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
        if definition.role == "veka_boreholes":
            return self._add_veka_layer(definition, force_add)

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
        if (
            existing and not self._veka_rows
            and all(layer.dataProvider().featureCount() == 0 for layer in existing)
        ):
            self._remove_layers_and_empty_groups(
                [layer.id() for layer in existing]
            )
            existing = []
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
                "number": row.get("number") or locality_row.get("number"),
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

    def _add_veka_layer(self, definition, force_add=False):
        """Load EELIS/VEKA wells as a locally filterable memory layer."""
        source_id = self._source_id(definition)
        project = QgsProject.instance()
        existing = [
            layer for layer in project.mapLayers().values()
            if self._layer_source_id(layer) == source_id
        ]
        if existing:
            if self.toggle_mode and not force_add:
                project.removeMapLayers([layer.id() for layer in existing])
                self._veka_fids = {}
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
        if self._veka_loading:
            self.message(
                "VEKA wells are already loading..." if self.language == "en"
                else "VEKA puurkaevud juba laadivad..."
            )
            return True
        if self._veka_rows:
            self._create_veka_layer(definition, list(self._veka_rows.values()))
            return True

        self._veka_loading = True
        if self.dock:
            self.dock.veka.status.setText(
                self.t("VEKA puurkaeve laaditakse…")
            )
        self.message(self.t("VEKA puurkaeve laaditakse…"))

        def loaded(rows):
            self._veka_loading = False
            self._create_veka_layer(definition, rows)

        def failed(error):
            self._veka_loading = False
            if self.dock:
                self.dock.veka.status.setText(str(error))
            self.error(
                f"Could not load VEKA wells: {error}" if self.language == "en"
                else f"VEKA puurkaevude laadimine ebaõnnestus: {error}"
            )

        self.network.query_eelis_pages(
            "f_puuraugud", {}, self.VEKA_MAIN_FIELDS, loaded, failed,
        )
        return True

    def _create_veka_layer(self, definition, rows):
        source_id = self._source_id(definition)
        if any(
            self._layer_source_id(layer) == source_id
            for layer in QgsProject.instance().mapLayers().values()
        ):
            return
        layer = QgsVectorLayer(
            "Point?crs=EPSG:3301", self.display_name(definition), "memory"
        )
        layer.setCustomProperty(self.SOURCE_PROPERTY, source_id)
        layer.setCustomProperty(self.ROLE_PROPERTY, "veka_boreholes")
        provider = layer.dataProvider()
        fields = (
            ("eelis_id", QVariant.LongLong), ("tyyp", QVariant.String),
            ("otstarve", QVariant.String), ("nimi", QVariant.String),
            ("staatus", QVariant.String), ("kkr_kood", QVariant.String),
            ("maayksus", QVariant.String), ("maa_nimi", QVariant.String),
            ("katastri_nr", QVariant.String), ("pass_nr", QVariant.String),
            ("seire_nr", QVariant.String), ("pvk_id", QVariant.LongLong),
            ("pvk_nimi", QVariant.String), ("veekiht", QVariant.String),
            ("veekiht_nimi", QVariant.String), ("aadress", QVariant.String),
            ("z_abs", QVariant.Double), ("sygavus", QVariant.Double),
            ("kasutus", QVariant.String), ("puur_aasta", QVariant.Int),
            ("muut_aeg", QVariant.String), ("vk_match", QVariant.Int),
            ("vk_style", QVariant.Double),
        )
        provider.addAttributes([QgsField(name, field_type) for name, field_type in fields])
        layer.updateFields()
        usable_rows = {}
        features = []
        for row in rows:
            identifier = row.get("id")
            x, y = veka_number(row.get("kesk_x")), veka_number(row.get("kesk_y"))
            if identifier in (None, "") or x is None or y is None:
                continue
            if not (300000 <= x <= 850000 and 6300000 <= y <= 6700000):
                continue
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            feature.setAttributes([
                identifier, row.get("tyyp"), row.get("tyyp_selg"),
                row.get("nimi"), row.get("keht_staatus"), row.get("kkr_kood"),
                row.get("maayksus"), row.get("maayksus_nimi"),
                row.get("katastri_nr"), row.get("pass_nr"), row.get("seire_nr"),
                row.get("pohjaveekogum_id"), row.get("pohjaveekogum_nimi"),
                row.get("veekiht"), row.get("veekiht_nimi"), row.get("aadress"),
                veka_number(row.get("z_abs")), veka_number(row.get("sygavus")),
                row.get("kasutus_selg"), row.get("puur_aasta"),
                row.get("muut_aeg"), 1, None,
            ])
            features.append(feature)
            usable_rows[str(identifier)] = dict(row)
            if len(features) >= 4000:
                provider.addFeatures(features)
                features = []
        if features:
            provider.addFeatures(features)
        layer.updateExtents()
        self._veka_rows = usable_rows
        self._veka_fids = {
            str(feature["eelis_id"]): int(feature.id())
            for feature in layer.getFeatures()
        }
        self._apply_veka_default_renderer(layer)
        self._apply_name_labeling(layer, "nimi")
        project = QgsProject.instance()
        project.addMapLayer(layer, False)
        project.layerTreeRoot().insertLayer(0, layer)
        self._ensure_egt_points_on_top(layer)
        self.iface.setActiveLayer(layer)
        purposes = sorted({
            (str(row.get("tyyp")), str(row.get("tyyp_selg") or row.get("tyyp")))
            for row in usable_rows.values() if row.get("tyyp") not in (None, "")
        }, key=lambda item: item[1].casefold())
        groundwater = sorted({
            (str(row.get("pohjaveekogum_id")), str(row.get("pohjaveekogum_nimi")))
            for row in usable_rows.values()
            if row.get("pohjaveekogum_id") not in (None, "")
            and row.get("pohjaveekogum_nimi") not in (None, "")
        }, key=lambda item: item[1].casefold())
        if self.dock:
            self.dock.veka.set_main_options(purposes, groundwater)
            self.dock.veka.status.setText(
                f"{len(usable_rows)} {self.t('VEKA puurkaevu valmis')}"
            )
        self.apply_veka_filters()
        if self.veka_style:
            QTimer.singleShot(
                0,
                lambda settings=dict(self.veka_style):
                self.apply_veka_symbology(settings),
            )
        self.sync_dropdown_checks()
        self.success(
            f"Loaded {len(usable_rows)} VEKA wells."
            if self.language == "en" else
            f"Laaditi {len(usable_rows)} VEKA puurkaevu."
        )

    @staticmethod
    def _apply_veka_default_renderer(layer):
        symbol = QgsMarkerSymbol.createSimple({
            "name": "circle", "color": "#2876a8",
            "outline_color": "#ffffff", "outline_width": "0.35",
            "size": "2.7",
        })
        renderer = layer.renderer()
        if hasattr(renderer, "setSymbol"):
            renderer.setSymbol(symbol)
        else:
            root = QgsRuleBasedRenderer.Rule(None)
            root.appendChild(QgsRuleBasedRenderer.Rule(symbol))
            layer.setRenderer(QgsRuleBasedRenderer(root))
        layer.triggerRepaint()

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
        reload_veka = {}
        project = QgsProject.instance()
        for layer in list(project.mapLayers().values()):
            definition = definitions.get(self._layer_source_id(layer))
            adopted = False
            if not definition:
                definition = self._definition_from_wfs_source(layer)
                adopted = definition is not None
            if not definition:
                continue
            if definition.role == "veka_boreholes" and not self._veka_rows:
                # A memory layer restored from a project does not rebuild the
                # related-data indexes needed by VEKA filters and styling.
                # Replace it with a fresh API-backed layer once per source.
                reload_veka[self._source_id(definition)] = definition
                project.removeMapLayer(layer.id())
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
        for definition in reload_veka.values():
            QTimer.singleShot(
                0, lambda item=definition: self._add_veka_layer(item, True)
            )
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
        point_roles = {"boreholes", "observations", "veka_boreholes"}
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
        self.dock.details.refresh_profile_filters()
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
        stratigraphic = self.dock.filters.stratigraphic_requirements()
        stratigraphic_key = (
            tuple(sorted(stratigraphic["indices"])),
            stratigraphic["contains"].casefold(),
        )
        stratigraphic_active = bool(
            stratigraphic["indices"] or stratigraphic["contains"]
        )
        stratigraphic_expression = ""
        if stratigraphic_active:
            if self._egt_stratigraphic_filter_key == stratigraphic_key:
                stratigraphic_expression = self._id_membership_clause(
                    self._egt_stratigraphic_filter_allowed or set()
                )
            elif self._egt_stratigraphic_filter_loading != stratigraphic_key:
                self._egt_stratigraphic_filter_generation += 1
                generation = self._egt_stratigraphic_filter_generation
                self._egt_stratigraphic_filter_loading = stratigraphic_key

                def loaded_stratigraphy(values):
                    if generation != self._egt_stratigraphic_filter_generation:
                        return
                    self._egt_stratigraphic_filter_loading = None
                    self._egt_stratigraphic_filter_key = stratigraphic_key
                    self._egt_stratigraphic_filter_allowed = set(values)
                    self.apply_egt_filters()

                def failed_stratigraphy(error):
                    if generation != self._egt_stratigraphic_filter_generation:
                        return
                    self._egt_stratigraphic_filter_loading = None
                    self.warning(
                        (f"Could not apply the EGT index filter: {error}"
                         if self.language == "en" else
                         f"EGT indeksifiltri rakendamine ebaõnnestus: {error}")
                    )

                self.network.query_stratigraphic_parent_ids(
                    stratigraphic["indices"], loaded_stratigraphy,
                    failed_stratigraphy,
                    contains=stratigraphic["contains"],
                )
        else:
            if self._egt_stratigraphic_filter_loading is not None:
                self._egt_stratigraphic_filter_generation += 1
            self._egt_stratigraphic_filter_loading = None
            self._egt_stratigraphic_filter_key = None
            self._egt_stratigraphic_filter_allowed = None

        combined_expressions = [
            expression for expression in (
                related_expression, stratigraphic_expression,
            ) if expression
        ]
        related_expression = " AND ".join(
            f"({expression})" for expression in combined_expressions
        )
        visibility = {
            "boreholes": self.dock.filters.boreholes.isChecked(),
            "observations": self.dock.filters.observations.isChecked(),
        }
        project = QgsProject.instance()
        for role, visible in visibility.items():
            for layer in self._role_layers(role):
                # EGT point layers are remote WFS layers.  Applying a search
                # result as an ``IN`` subset can create a many-kilobyte WFS
                # request (even a single broad index may match hundreds of
                # boreholes), which the server rejects as excessive load.
                # Keep only the compact category predicate server-side and
                # evaluate related-data and search-result membership locally
                # through the rule renderer's layer variable.
                search_expression = self._search_filter_clause(layer, role)
                local_expressions = [
                    expression for expression in (
                        related_expression, search_expression,
                    ) if expression
                ]
                local_expression = " AND ".join(
                    f"({expression})" for expression in local_expressions
                )
                layer.setSubsetString(category_expression)
                self._apply_category_renderer(layer, local_expression)
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
        self.dock.details.refresh_profile_filters()
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
                layer.setSubsetString(
                    self._with_search_filter(
                        layer, role, base_expression
                    )
                )
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
            or requirements["specimen_type"]
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
            ) or (
                key == "specimens" and requirements["specimen_type"]
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
                    layer.setSubsetString(
                        self._with_search_filter(layer, role, expression)
                    )
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
                    elif condition == "specimens":
                        specimen_types = (
                            sorted(requirements["specimen_type"]) or [None]
                        )
                        requests.extend(
                            (target, chunk, None, specimen_type)
                            for specimen_type in specimen_types
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
                    parameters = {
                        "locality__in": ",".join(ids),
                        "type": sample_type,
                    }
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

    # ---- VEKA filters and symbology ----------------------------------------------

    def _ensure_veka_aux(self, kind, callback):
        if self._veka_aux.get(kind) is not None:
            callback(self._veka_aux[kind])
            return
        self._veka_aux_waiters[kind].append(callback)
        if kind in self._veka_aux_loading:
            return
        self._veka_aux_loading.add(kind)
        config = {
            "construction": (
                "f_puuraugud_konstruktsioon",
                {"konstr_tyyp": "in.(" + ",".join(sorted(FILTER_CONSTRUCTION_TYPES)) + ")"},
                ("konstr_puurauk_id", "konstr_tyyp", "alg", "lopp"),
            ),
            "hydro": (
                "f_puuraugud_puurauk_param", {"deebit": "not.is.null"},
                ("param_puurauk_id", "deebit", "alandus", "katse_kp"),
            ),
            "analysis_catalog": (
                "f_veenaitajad_W10_W1_public",
                {"katastri_number": "not.is.null", "naitaja_tulem": "not.is.null"},
                ("naitaja_kood", "naitaja_nimi", "naitaja_yhik"),
            ),
        }[kind]
        if self.dock:
            self.dock.veka.status.setText(
                self.t("VEKA seotud andmeid laaditakse…")
            )

        def loaded(rows):
            self._veka_aux_loading.discard(kind)
            self._veka_aux[kind] = list(rows)
            self._veka_grouped.pop(kind, None)
            waiters, self._veka_aux_waiters[kind] = self._veka_aux_waiters[kind], []
            for waiter in waiters:
                waiter(self._veka_aux[kind])

        def failed(error):
            self._veka_aux_loading.discard(kind)
            self._veka_aux[kind] = []
            self._veka_grouped.pop(kind, None)
            waiters, self._veka_aux_waiters[kind] = self._veka_aux_waiters[kind], []
            self.warning(
                f"Could not load VEKA {kind} data: {error}"
                if self.language == "en" else
                f"VEKA andmete {kind} laadimine ebaõnnestus: {error}"
            )
            for waiter in waiters:
                waiter([])

        self.network.query_eelis_pages(
            config[0], config[1], config[2], loaded, failed,
        )

    def _ensure_veka_analysis(self, code, callback):
        """Load only the selected water-quality parameter and cache it."""
        key = str(code or "")
        parameter_codes = analysis_codes(key)
        _, _, target_unit = split_analysis_key(key)
        if not parameter_codes:
            callback([])
            return
        if key in self._veka_analysis_rows:
            callback(self._veka_analysis_rows[key])
            return
        self._veka_analysis_waiters.setdefault(key, []).append(callback)
        if key in self._veka_analysis_loading:
            return
        self._veka_analysis_loading.add(key)
        if self.dock:
            self.dock.veka.status.setText(
                self.t("VEKA seotud andmeid laaditakse…")
            )

        def completed(rows, error=None):
            matching_rows = []
            for row in rows:
                value = analysis_row_value(row, key)
                if value is None:
                    continue
                prepared = dict(row)
                prepared["_qeoloog_value"] = value
                prepared["_qeoloog_unit"] = target_unit
                matching_rows.append(prepared)
            self._veka_analysis_loading.discard(key)
            self._veka_analysis_rows[key] = matching_rows
            self._veka_analysis_grouped.pop(key, None)
            waiters = self._veka_analysis_waiters.pop(key, [])
            if error:
                self.warning(
                    f"Could not load VEKA analysis data: {error}"
                    if self.language == "en" else
                    f"VEKA analüüsiandmete laadimine ebaõnnestus: {error}"
                )
            for waiter in waiters:
                waiter(self._veka_analysis_rows[key])

        fields = (
            "katastri_number", "analyys_number", "proov_algus",
            "proov_sygavus", "naitaja_kood", "naitaja_tulem",
            "naitaja_nimi", "naitaja_yhik",
        )

        def load_code(index, collected):
            if index >= len(parameter_codes):
                completed(collected)
                return
            self.network.query_eelis_pages(
                "f_veenaitajad_W10_W1_public",
                {
                    "katastri_number": "not.is.null",
                    "naitaja_tulem": "not.is.null",
                    "naitaja_kood": f"eq.{parameter_codes[index]}",
                },
                fields,
                lambda rows: load_code(index + 1, collected + list(rows)),
                lambda error: completed([], error),
            )

        load_code(0, [])

    def _veka_analysis_group(self, code):
        code = str(code or "")
        if code not in self._veka_analysis_grouped:
            self._veka_analysis_grouped[code] = group_rows(
                self._veka_analysis_rows.get(code, []), "katastri_number",
            )
        return self._veka_analysis_grouped[code]

    def _veka_group(self, kind):
        if kind not in self._veka_grouped:
            key = {
                "construction": "konstr_puurauk_id",
                "hydro": "param_puurauk_id",
                "analyses": "katastri_number",
            }[kind]
            self._veka_grouped[kind] = group_rows(
                self._veka_aux.get(kind) or [], key,
            )
        return self._veka_grouped[kind]

    def ensure_veka_analysis_options(self):
        if self.dock:
            self.dock.veka.load_analysis.setEnabled(False)
            self.dock.veka.status.setText(
                self.t("Veeproovi näitajaid laaditakse…")
            )

        def ready(rows):
            if self.dock:
                options = veka_analysis_options(rows)
                self.dock.veka.set_analysis_options(options)
                self.dock.export.set_veka_analysis_options(options)
                self.dock.veka.status.setText(
                    self.t("Veeproovi näitajad on valmis.")
                )

        self._ensure_veka_aux("analysis_catalog", ready)

    def apply_veka_filters(self):
        if not self.dock:
            return
        layers = self._role_layers("veka_boreholes")
        if not layers or not self._veka_rows:
            self.dock.veka.status.setText(
                self.t("Laadi VK kiht, et VEKA filtreid kasutada.")
            )
            return
        requirements = self.dock.veka.requirements()
        needed = []
        if requirements["filter_min"] is not None or requirements["filter_max"] is not None:
            needed.append("construction")
        if any(
            requirements[key] is not None
            for key in ("debit_min", "debit_max", "specific_min", "specific_max")
        ):
            needed.append("hydro")
        if requirements["analysis_code"]:
            needed.append("analyses")
        self._veka_filter_generation += 1
        generation = self._veka_filter_generation

        def ensure(index):
            if generation != self._veka_filter_generation:
                return
            if index >= len(needed):
                self._apply_veka_filters_ready(requirements, layers, generation)
                return
            kind = needed[index]
            if kind == "analyses":
                self._ensure_veka_analysis(
                    requirements["analysis_code"], lambda rows: ensure(index + 1)
                )
            else:
                self._ensure_veka_aux(kind, lambda rows: ensure(index + 1))

        ensure(0)

    def _apply_veka_filters_ready(self, requirements, layers, generation):
        if generation != self._veka_filter_generation:
            return
        purpose = requirements["purposes"]
        groundwater = requirements["groundwater"]
        text = self._normalized(requirements["text"])
        construction_active = (
            requirements["filter_min"] is not None
            or requirements["filter_max"] is not None
        )
        construction = self._veka_group("construction") if construction_active else {}
        hydro_active = any(
            requirements[key] is not None
            for key in ("debit_min", "debit_max", "specific_min", "specific_max")
        )
        hydro = self._veka_group("hydro") if hydro_active else {}
        analysis_active = bool(requirements["analysis_code"])
        analyses = (
            self._veka_analysis_group(requirements["analysis_code"])
            if analysis_active else {}
        )
        matching = set()
        for identifier, row in self._veka_rows.items():
            if purpose and str(row.get("tyyp")) not in purpose:
                continue
            if groundwater and str(row.get("pohjaveekogum_id")) not in groundwater:
                continue
            year = veka_number(row.get("puur_aasta"))
            if requirements["year_min"] is not None and (
                year is None or year < requirements["year_min"]
            ):
                continue
            if requirements["year_max"] is not None and (
                year is None or year > requirements["year_max"]
            ):
                continue
            if text:
                haystack = self._normalized(" ".join(
                    str(row.get(key) or "") for key in (
                        "nimi", "kkr_kood", "katastri_nr", "pass_nr",
                        "seire_nr", "aadress", "maayksus", "maayksus_nimi",
                    )
                ))
                if text not in haystack:
                    continue
            if construction_active and not any(
                interval_intersects(
                    item.get("alg"), item.get("lopp"),
                    requirements["filter_min"], requirements["filter_max"],
                )
                for item in construction.get(identifier, ())
            ):
                continue
            if hydro_active and not veka_hydro_matches(
                hydro.get(identifier, ()), requirements,
            ):
                continue
            if analysis_active and not veka_analysis_matches(
                analyses.get(str(row.get("katastri_nr") or "").strip(), ()),
                requirements,
            ):
                continue
            matching.add(identifier)
        for layer in layers:
            index = layer.fields().indexOf("vk_match")
            if index < 0:
                continue
            changes = {
                fid: {index: 1 if identifier in matching else 0}
                for identifier, fid in self._veka_fids.items()
            }
            layer.dataProvider().changeAttributeValues(changes)
            layer.setSubsetString(
                self._with_search_filter(
                    layer, "veka_boreholes", '"vk_match" = 1'
                )
            )
            layer.triggerRepaint()
        self.dock.veka.status.setText(
            f"{len(matching)} / {len(self._veka_rows)} "
            + self.t("VEKA puurkaevu nähtaval")
        )

    def _veka_metric_values(self, settings):
        metric = settings.get("metric", "year")
        mode = settings.get("aggregation", "latest")
        values = {}
        if metric in {"year", "depth"}:
            field = "puur_aasta" if metric == "year" else "sygavus"
            return {
                identifier: veka_number(row.get(field))
                for identifier, row in self._veka_rows.items()
            }
        if metric in {"filter_top", "filter_bottom"}:
            grouped = self._veka_group("construction")
            field = "alg" if metric == "filter_top" else "lopp"
            effective_mode = (
                "min" if metric == "filter_top" else "max"
            ) if mode == "latest" else mode
            for identifier in self._veka_rows:
                values[identifier] = veka_aggregate(
                    grouped.get(identifier, ()), lambda row: row.get(field),
                    effective_mode,
                )
            return values
        if metric in {"debit", "specific"}:
            grouped = self._veka_group("hydro")
            getter = (
                (lambda row: row.get("deebit"))
                if metric == "debit" else specific_capacity
            )
            for identifier in self._veka_rows:
                values[identifier] = veka_aggregate(
                    grouped.get(identifier, ()), getter, mode,
                )
            return values
        key = str(settings.get("analysis_code") or "")
        grouped = self._veka_analysis_group(key)
        for identifier, row in self._veka_rows.items():
            values[identifier] = veka_aggregate(
                grouped.get(str(row.get("katastri_nr") or ""), ()),
                lambda item: item.get("_qeoloog_value"), mode,
                date_field="proov_algus",
            )
        return values

    def apply_veka_symbology(self, settings):
        layers = self._role_layers("veka_boreholes")
        if not layers:
            self.warning(
                "Load the VK layer first." if self.language == "en"
                else "Laadi esmalt VK kiht."
            )
            return
        metric = settings.get("metric", "year")
        if metric == "analysis" and not settings.get("analysis_code"):
            self.warning(
                "Select a water-quality parameter first."
                if self.language == "en" else
                "Vali esmalt veeproovi näitaja."
            )
            return
        required = {
            "filter_top": "construction", "filter_bottom": "construction",
            "debit": "hydro", "specific": "hydro", "analysis": "analyses",
        }.get(metric)
        if required == "analyses":
            code = str(settings.get("analysis_code") or "")
            if code not in self._veka_analysis_rows:
                self._ensure_veka_analysis(
                    code, lambda rows: self.apply_veka_symbology(settings)
                )
                return
        elif required and self._veka_aux.get(required) is None:
            self._ensure_veka_aux(
                required, lambda rows: self.apply_veka_symbology(settings)
            )
            return
        values = self._veka_metric_values(settings)
        usable = [value for value in values.values() if value is not None]
        if not usable:
            self.warning(
                "No numeric values are available for this style."
                if self.language == "en" else
                "Selle kujunduse jaoks ei leitud arvulisi väärtusi."
            )
            return
        minimum, maximum = min(usable), max(usable)
        span = max(1.0, maximum - minimum)
        sentinel = minimum - span * 0.05 - 1.0
        for layer in layers:
            index = layer.fields().indexOf("vk_style")
            changes = {
                fid: {index: values.get(identifier) if values.get(identifier) is not None else sentinel}
                for identifier, fid in self._veka_fids.items()
            }
            layer.dataProvider().changeAttributeValues(changes)
            renderer = self._veka_graduated_renderer(
                usable, sentinel, settings,
            )
            layer.setRenderer(renderer)
            layer.triggerRepaint()
        self.veka_style = dict(settings)
        PluginSettings.save_veka_style(self.veka_style)
        if self.dock:
            self.dock.veka.status.setText(
                self.t("VEKA kujundus rakendati.")
            )

    def _veka_graduated_renderer(self, values, sentinel, settings):
        try:
            classes = max(1, min(12, int(settings.get("classes", 5))))
        except (TypeError, ValueError):
            classes = 5
        breaks = (
            quantile_breaks(values, classes)
            if settings.get("classification") == "quantile"
            else equal_breaks(values, classes)
        )
        minimum = min(values)
        try:
            size_min = max(0.1, float(settings.get("size_min", 1.5)))
            size_max = max(size_min, float(settings.get("size_max", 7.0)))
        except (TypeError, ValueError):
            size_min, size_max = 1.5, 7.0
        palette = str(settings.get("palette") or "#440154|#fde725")
        if "|" not in palette:
            palette = "#440154|#fde725"
        start_text, end_text = palette.split("|", 1)
        start_color, end_color = QColor(start_text), QColor(end_text)
        if not start_color.isValid() or not end_color.isValid():
            start_color, end_color = QColor("#440154"), QColor("#fde725")
        method = settings.get("method", "color")
        ranges = []
        missing_symbol = QgsMarkerSymbol.createSimple({
            "name": "circle", "color": "#a9a9a9",
            "outline_color": "#ffffff", "outline_width": "0.25",
            "size": str(size_min if settings.get("show_missing", True) else 0.0),
        })
        ranges.append(QgsRendererRange(
            sentinel, sentinel, missing_symbol, self.t("Andmed puuduvad"),
        ))
        lower = minimum
        denominator = max(1, len(breaks) - 1)
        for index, upper in enumerate(breaks):
            fraction = index / denominator
            color = QColor.fromRgbF(
                start_color.redF() + (end_color.redF() - start_color.redF()) * fraction,
                start_color.greenF() + (end_color.greenF() - start_color.greenF()) * fraction,
                start_color.blueF() + (end_color.blueF() - start_color.blueF()) * fraction,
                1.0,
            )
            size = size_min + (size_max - size_min) * fraction
            symbol = QgsMarkerSymbol.createSimple({
                "name": "circle",
                "color": color.name() if method in {"color", "both"} else "#2876a8",
                "outline_color": "#ffffff", "outline_width": "0.3",
                "size": str(size if method in {"size", "both"} else 2.7),
            })
            label = f"{lower:.4g} – {upper:.4g}"
            ranges.append(QgsRendererRange(lower, upper, symbol, label))
            lower = upper
        return QgsGraduatedSymbolRenderer("vk_style", ranges)

    def reset_veka_symbology(self):
        for layer in self._role_layers("veka_boreholes"):
            self._apply_veka_default_renderer(layer)
            self._apply_name_labeling(layer, "nimi")
        self.veka_style = {}
        PluginSettings.save_veka_style({})
        if self.dock:
            self.dock.veka.status.setText(self.t("VEKA algkujundus taastati."))

    @staticmethod
    def veka_construction_category(code):
        return construction_category(code)

    @staticmethod
    def veka_specific_capacity(row):
        return specific_capacity(row)

    @staticmethod
    def veka_static_water_level(rows):
        return latest_static_water_level(rows)

    @staticmethod
    def veka_analysis_result(row):
        return veka_converted_result(
            row.get("naitaja_tulem"),
            row.get("naitaja_yhik"),
            row.get("naitaja_nimi"),
        )

    # ---- Multi-well cross-sections -----------------------------------------------

    def cross_section_contains(self, key):
        return bool(
            self.dock
            and self.dock.cross_sections.contains(str(key))
        )

    def add_current_detail_to_cross_section(self):
        if not self.dock:
            return
        snapshot = self.dock.details.cross_section_snapshot()
        if snapshot:
            self.dock.cross_sections.add_snapshot(snapshot)

    def remove_cross_section_item(self, key):
        if self.dock:
            self.dock.cross_sections.remove_key(key)

    def start_cross_section_line(self):
        if not self.cross_section_line_tool:
            return
        canvas = self.iface.mapCanvas()
        self.cross_section_previous_tool = canvas.mapTool()
        canvas.setMapTool(self.cross_section_line_tool)
        self.message(
            "Click line vertices; right-click or Enter finishes."
            if self.language == "en" else
            "Klõpsa joone tipud; paremklõps või Enter lõpetab."
        )

    def _cross_section_line_finished(self, points):
        canvas = self.iface.mapCanvas()
        transformed = []
        try:
            transform = QgsCoordinateTransform(
                canvas.mapSettings().destinationCrs(),
                QgsCoordinateReferenceSystem("EPSG:3301"),
                QgsProject.instance(),
            )
            for x, y in points:
                point = transform.transform(QgsPointXY(float(x), float(y)))
                transformed.append((point.x(), point.y()))
        except (QgsCsException, TypeError, ValueError):
            transformed = []
        if transformed and self.dock:
            self.dock.cross_sections.set_line(transformed)
            self.dock.show_cross_sections()
        self._restore_cross_section_map_tool()

    def _cross_section_line_cancelled(self):
        self._restore_cross_section_map_tool()

    def _restore_cross_section_map_tool(self):
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self.cross_section_line_tool:
            if (
                self.cross_section_previous_tool
                and self.cross_section_previous_tool
                is not self.cross_section_line_tool
            ):
                canvas.setMapTool(self.cross_section_previous_tool)
            else:
                canvas.unsetMapTool(self.cross_section_line_tool)
        self.cross_section_previous_tool = None

    def update_cross_section_map_line(self, points, visible=True):
        if not self.cross_section_map_band:
            return
        self.cross_section_map_band.reset(Qgis.GeometryType.Line)
        if not visible or len(points or ()) < 2:
            self.cross_section_map_band.hide()
            self.iface.mapCanvas().update()
            return
        try:
            transform = QgsCoordinateTransform(
                QgsCoordinateReferenceSystem("EPSG:3301"),
                self.iface.mapCanvas().mapSettings().destinationCrs(),
                QgsProject.instance(),
            )
            for x, y in points:
                point = transform.transform(QgsPointXY(float(x), float(y)))
                self.cross_section_map_band.addPoint(point, False)
            self.cross_section_map_band.updatePosition()
            self.cross_section_map_band.show()
            self.cross_section_map_band.update()
            self.iface.mapCanvas().update()
        except (QgsCsException, TypeError, ValueError):
            self.cross_section_map_band.reset(Qgis.GeometryType.Line)
            self.cross_section_map_band.hide()

    # ---- Leapfrog export area ----------------------------------------------------

    def start_export_area(self):
        if not self.export_area_tool:
            return
        canvas = self.iface.mapCanvas()
        self.export_area_previous_tool = canvas.mapTool()
        canvas.setMapTool(self.export_area_tool)
        self.message(
            "Click polygon vertices; right-click or Enter finishes."
            if self.language == "en" else
            "Klõpsa ala tipud; paremklõps või Enter lõpetab."
        )

    def _export_area_finished(self, points):
        canvas = self.iface.mapCanvas()
        transformed = []
        try:
            transform = QgsCoordinateTransform(
                canvas.mapSettings().destinationCrs(),
                QgsCoordinateReferenceSystem("EPSG:3301"),
                QgsProject.instance(),
            )
            for x, y in points:
                point = transform.transform(QgsPointXY(float(x), float(y)))
                transformed.append(QgsPointXY(point))
        except (QgsCsException, TypeError, ValueError):
            transformed = []
        if len(transformed) >= 3 and self.dock:
            if transformed[0] != transformed[-1]:
                transformed.append(QgsPointXY(transformed[0]))
            geometry = QgsGeometry.fromPolygonXY([transformed])
            self.dock.export.set_area(
                geometry, self.t("Kaardile joonistatud ala")
            )
            self.dock.tabs.setCurrentWidget(self.dock.export_page)
            self.dock.show()
            self.dock.raise_()
        self._restore_export_area_map_tool()

    def _export_area_cancelled(self):
        self._restore_export_area_map_tool()

    def _restore_export_area_map_tool(self):
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self.export_area_tool:
            if (
                self.export_area_previous_tool
                and self.export_area_previous_tool is not self.export_area_tool
            ):
                canvas.setMapTool(self.export_area_previous_tool)
            else:
                canvas.unsetMapTool(self.export_area_tool)
        self.export_area_previous_tool = None

    def update_export_area_band(self, geometry):
        if not self.export_area_band:
            return
        self.export_area_band.reset(Qgis.GeometryType.Polygon)
        if not geometry or geometry.isEmpty():
            self.export_area_band.hide()
            self.iface.mapCanvas().update()
            return
        display = QgsGeometry(geometry)
        try:
            display.transform(QgsCoordinateTransform(
                QgsCoordinateReferenceSystem("EPSG:3301"),
                self.iface.mapCanvas().mapSettings().destinationCrs(),
                QgsProject.instance(),
            ))
            self.export_area_band.setToGeometry(display, None)
            self.export_area_band.show()
            self.export_area_band.update()
            self.iface.mapCanvas().update()
        except QgsCsException:
            self.export_area_band.reset(Qgis.GeometryType.Polygon)
            self.export_area_band.hide()

    @staticmethod
    def _detail_attributes_with_location(
        attributes, layer=None, feature=None,
    ):
        values = dict(attributes or {})
        if layer is not None and feature is not None:
            try:
                source_point = feature.geometry().constGet()
                elevation = veka_number(
                    source_point.z()
                    if source_point is not None
                    and hasattr(source_point, "z") else None
                )
                if (
                    elevation is not None
                    and not any(
                        values.get(key) not in (None, "", "NULL", "<NULL>")
                        for key in ("z_abs", "elevation", "altitude", "height")
                    )
                ):
                    # EGT publishes ground elevation as the Z coordinate of
                    # its PointZ WFS geometry rather than as an attribute.
                    values["z_abs"] = elevation
            except (AttributeError, TypeError, ValueError):
                pass
        if (
            values.get("_qeoloog_x_3301") not in (None, "")
            and values.get("_qeoloog_y_3301") not in (None, "")
        ):
            return values
        if layer is not None and feature is not None:
            try:
                geometry = QgsGeometry(feature.geometry())
                geometry.transform(QgsCoordinateTransform(
                    layer.crs(),
                    QgsCoordinateReferenceSystem("EPSG:3301"),
                    QgsProject.instance(),
                ))
                point = geometry.asPoint()
                values["_qeoloog_x_3301"] = point.x()
                values["_qeoloog_y_3301"] = point.y()
                return values
            except (QgsCsException, TypeError, ValueError):
                pass
        longitude = values.get("_qeoloog_longitude")
        latitude = values.get("_qeoloog_latitude")
        if longitude not in (None, "") and latitude not in (None, ""):
            try:
                point = QgsCoordinateTransform(
                    QgsCoordinateReferenceSystem("EPSG:4326"),
                    QgsCoordinateReferenceSystem("EPSG:3301"),
                    QgsProject.instance(),
                ).transform(QgsPointXY(float(longitude), float(latitude)))
                values["_qeoloog_x_3301"] = point.x()
                values["_qeoloog_y_3301"] = point.y()
            except (QgsCsException, TypeError, ValueError):
                pass
        return values

    # ---- Shared EGT/SARV/VEKA search --------------------------------------------

    @staticmethod
    def _search_roles(criteria):
        source = criteria.get("source", "both")
        roles = set()
        if source in {"all", "both", "egt"}:
            roles.update(("boreholes", "observations"))
        if source in {"all", "both", "sarv"}:
            roles.update((
                "sarv_localities", "sarv_sites", "sarv_drillcores",
            ))
        if source in {"all", "veka"}:
            roles.add("veka_boreholes")
        selected = criteria.get("kinds")
        return roles if selected is None else roles.intersection(selected)

    def apply_search_filter(self, rows, criteria):
        """Limit searched layer roles to the current result identifiers."""
        roles = self._search_roles(criteria)
        values = {role: set() for role in roles}
        for row in rows:
            role = row.get("_role")
            value = row.get("_filter_id")
            if role in values and value not in (None, ""):
                values[role].add(str(value))
        self._search_filter = {"roles": roles, "values": values}
        self.apply_egt_filters()
        self.apply_sarv_filters()
        self.apply_veka_filters()

    def clear_search_filter(self):
        """Remove the transient search-result filter from all point layers."""
        self._search_filter = None
        self.apply_egt_filters()
        self.apply_sarv_filters()
        self.apply_veka_filters()

    def _search_filter_clause(self, layer, role):
        active = self._search_filter
        if not active or role not in active["roles"]:
            return ""
        candidates = {
            "boreholes": ("esri_globalid", "globalid"),
            "observations": ("esri_globalid", "globalid"),
            "sarv_localities": ("sarv_id",),
            "sarv_sites": ("sarv_id",),
            "sarv_drillcores": ("sarv_id",),
            "veka_boreholes": ("eelis_id",),
        }.get(role, ())
        field = next(
            (name for name in candidates if layer.fields().indexOf(name) >= 0),
            "",
        )
        if not field:
            return ""
        values = sorted(active["values"].get(role, set()))
        if not values:
            return f'"{field}" IS NULL AND "{field}" IS NOT NULL'
        literals = ", ".join(
            value if value.lstrip("-").isdigit()
            else f"'{value.replace(chr(39), chr(39) * 2)}'"
            for value in values
        )
        return f'"{field}" IN ({literals})'

    def _with_search_filter(self, layer, role, base_expression=""):
        clauses = [
            clause for clause in (
                base_expression,
                self._search_filter_clause(layer, role),
            ) if clause
        ]
        return " AND ".join(f"({clause})" for clause in clauses)

    def run_search(self, criteria, callback):
        source = criteria.get("source", "both")
        wants_egt = source in {"all", "both", "egt"}
        wants_sarv = source in {"all", "both", "sarv"}
        wants_veka = source in {"all", "veka"}
        related = criteria.get("related", {})
        stratigraphic_indices = criteria.get("stratigraphic_indices", set())
        if (
            wants_egt
            and stratigraphic_indices
            and "_egt_stratigraphic_allowed" not in criteria
        ):
            self.network.query_stratigraphic_parent_ids(
                stratigraphic_indices,
                lambda allowed: self.run_search(
                    {
                        **criteria,
                        "_egt_stratigraphic_allowed": allowed,
                    },
                    callback,
                ),
                lambda error: callback(
                    [],
                    (
                        f"EGT stratigraphic search failed: {error}"
                        if self.language == "en" else
                        f"EGT stratigraafiaotsing ebaõnnestus: {error}"
                    ),
                ),
            )
            return
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
        stratigraphic_allowed = criteria.get("_egt_stratigraphic_allowed")
        if stratigraphic_allowed is not None:
            allowed_egt = (
                set(stratigraphic_allowed)
                if allowed_egt is None
                else allowed_egt & set(stratigraphic_allowed)
            )

        text_query = str(criteria.get("text") or "")
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
        if wants_veka:
            roles.append("veka_boreholes")
        selected_roles = criteria.get("kinds")
        if selected_roles is not None:
            roles = [role for role in roles if role in selected_roles]
        for role in roles:
            for layer in self._role_layers(role):
                loaded_sources.add(
                    "SARV" if role.startswith("sarv_")
                    else "VEKA" if role == "veka_boreholes" else "EGT"
                )
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
                    is_veka = role == "veka_boreholes"
                    object_id = (
                        attributes.get("sarv_id") if is_sarv else
                        (attributes.get("kkr_kood") or attributes.get("eelis_id"))
                        if is_veka else
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
                    if not is_sarv and not is_veka and allowed_egt is not None:
                        if str(object_id).upper() not in allowed_egt:
                            continue
                    if not is_sarv and not is_veka:
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
                        attributes.get("sygavus") if is_veka else
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
                    if is_sarv:
                        name = (
                            attributes.get("name_en") if self.language == "en"
                            else attributes.get("name")
                        ) or attributes.get("name") or attributes.get("number")
                    elif is_veka:
                        name = attributes.get("nimi") or attributes.get("kkr_kood")
                    else:
                        name = attributes.get("nimi") or attributes.get("alias")
                    name = name or attributes.get("number") or object_id
                    relevance = self._search_relevance(
                        text_query,
                        primary_values=(
                            name, attributes.get("alias"),
                        ),
                        identifier_values=(
                            object_id, attributes.get("number"),
                            attributes.get("korrastatud_nr"),
                            attributes.get("gea_id"),
                            attributes.get("ma_orig_id"),
                            attributes.get("land_board_id"),
                            attributes.get("kande_alus_nr"),
                            attributes.get("kkr_kood"),
                            attributes.get("katastri_nr"),
                            attributes.get("pass_nr"),
                            attributes.get("seire_nr"),
                        ),
                        other_values=(
                            attributes.get("name"),
                            attributes.get("name_en"),
                            attributes.get("type"),
                            attributes.get("aadress"),
                            attributes.get("maayksus"),
                            attributes.get("maa_nimi"),
                            attributes.get("otstarve"),
                            attributes.get("pvk_nimi"),
                        ),
                    )
                    if relevance is None:
                        continue
                    rows.append({
                        "source": "SARV" if is_sarv else "VEKA" if is_veka else "EGT",
                        "type": self.t({
                            "boreholes": "Puurauk",
                            "observations": "Vaatluspunkt",
                            "sarv_localities": "Lokaliteet",
                            "sarv_sites": "Uuringupunkt",
                            "sarv_drillcores": "Puursüdamik",
                            "veka_boreholes": "VEKA puurkaev",
                        }.get(role, role)),
                        "name": name,
                        "id": object_id,
                        "depth": numeric_depth,
                        "_layer_id": layer.id(),
                        "_feature_id": int(feature.id()),
                        "_role": role,
                        "_filter_id": (
                            attributes.get("eelis_id") if is_veka
                            else attributes.get("sarv_id") if is_sarv
                            else object_id
                        ),
                        "_search_score": relevance,
                    })
        rows.sort(key=lambda row: (
            -int(row.get("_search_score") or 0),
            str(row.get("source")),
            str(row.get("name") or "").casefold(),
        ))
        total_count = len(rows)
        if not criteria.get("_return_all"):
            rows = rows[:500]
        missing = []
        if wants_egt and "EGT" not in loaded_sources:
            missing.append("EGT")
        if wants_sarv and "SARV" not in loaded_sources:
            missing.append("SARV")
        if wants_veka and "VEKA" not in loaded_sources:
            missing.append("VEKA")
        message = (
            f"{total_count} {self.t('tulemust')}"
            + (
                ". " + self.t("Laadi otsimiseks esmalt kihid: ")
                + ", ".join(missing)
                if missing else ""
            )
            + (
                f". {self.t('Kuvatakse esimesed 500.')}"
                if total_count > 500 else ""
            )
        )
        callback(rows, message)

    def _resolve_sarv_search_allowed(self, criteria, success, failure):
        candidate = {"locality": set(), "site": set()}
        text_query = str(criteria.get("text") or "")
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
                    if self._search_relevance(
                        text_query,
                        primary_values=(name,),
                        identifier_values=(
                            attributes.get("number"),
                            attributes.get("sarv_id"),
                            attributes.get("land_board_id"),
                        ),
                        other_values=(
                            attributes.get("name"),
                            attributes.get("name_en"),
                            attributes.get("type"),
                        ),
                    ) is None:
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
            canvas.setCenter(QgsPointXY(point))
            canvas.refresh()
        except (QgsCsException, ValueError):
            pass
        attributes = {
            field.name(): feature.attribute(field.name())
            for field in layer.fields()
        }
        attributes = self._detail_attributes_with_location(
            attributes, layer, feature
        )
        role = item.get("_role") or self._layer_role(layer)
        self._show_highlight(layer, feature)
        if role.startswith("sarv_"):
            self._load_sarv_point_details(
                role, str(item.get("name") or item.get("id")),
                attributes, layer, feature,
            )
        elif role == "veka_boreholes":
            self._load_veka_details(
                str(item.get("name") or item.get("id")), attributes,
                layer, feature,
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
            "boreholes", "observations", "veka_boreholes", "sarv_drillcores",
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
                            and not self._passes_related_filter(
                                feature_attributes, role
                            )
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
                "No visible EGT, SARV or VEKA point was found here." if self.language == "en"
                else "Selles kohas ei leitud nähtavat EGT, SARV-i ega VEKA punkti."
            )
            return
        _, role, layer, feature = best
        attributes = {
            field.name(): feature.attribute(field.name())
            for field in layer.fields()
        }
        attributes = self._detail_attributes_with_location(
            attributes, layer, feature
        )
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
        if role == "veka_boreholes":
            name = attributes.get("nimi") or attributes.get("kkr_kood") or "VEKA"
            self._show_highlight(layer, feature)
            self._load_veka_details(str(name), attributes, layer, feature)
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

    def _passes_related_filter(self, attributes, role="boreholes"):
        """Match EGT filters that are intentionally evaluated client-side."""
        object_id = str(
            attributes.get("esri_globalid") or attributes.get("globalid") or ""
        ).upper()
        active_search = self._search_filter
        if active_search and role in active_search["roles"]:
            allowed = {
                str(value).upper()
                for value in active_search["values"].get(role, set())
            }
            if object_id not in allowed:
                return False
        if (
            self._egt_stratigraphic_filter_key is not None
            and object_id not in (self._egt_stratigraphic_filter_allowed or set())
        ):
            return False
        if self.dock and len(self.related_index) >= 4:
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

    def _load_veka_details(self, name, attributes, layer, feature):
        """Show VEKA overview and load only this well's related datasets."""
        attributes = self._detail_attributes_with_location(
            attributes, layer, feature
        )
        self._detail_token += 1
        token = self._detail_token
        details = self.dock.details
        self.dock.show_details()
        details.show_loading(name, attributes, "veka_boreholes")
        details.set_ready(name)
        identifier = attributes.get("eelis_id")
        if identifier in (None, ""):
            return
        source_row = self._veka_rows.get(str(identifier), {})

        def current(callback):
            return lambda rows: (
                callback(rows) if token == self._detail_token else None
            )

        def failed(label, clear_callback=None):
            def handler(error):
                if token == self._detail_token:
                    if clear_callback:
                        clear_callback([])
                    self.warning(
                        f"Could not load VEKA {label}: {error}"
                        if self.language == "en" else
                        f"VEKA andmete {label} laadimine ebaõnnestus: {error}"
                    )
            return handler

        def profile_loaded(rows):
            if token != self._detail_token:
                return
            units = [{
                "z_suht_ylemine": row.get("lasum"),
                "z_suht_alumine": row.get("lamam"),
                "indeks": row.get("geol_vanus"),
                "litoloogia": row.get("kivim_nimetus"),
                "litoloogia_orig": row.get("kivim_nimetus"),
            } for row in rows]
            details.set_profile(units)

        self.network.query_eelis_pages(
            "f_puuraugud_labiloige",
            {"labil_puurauk_id": f"eq.{identifier}", "order": "jrk_nr.asc"},
            (
                "labiloige_id", "jrk_nr", "geol_vanus",
                "kivim_nimetus", "lasum", "lamam", "paksus",
            ),
            profile_loaded, failed("log", details.set_profile), limit=2000,
        )
        self.network.query_eelis_pages(
            "f_puuraugud_konstruktsioon",
            {
                "konstr_puurauk_id": f"eq.{identifier}",
                "order": "alg.asc",
            },
            (
                "konstr_id", "konstr_tyyp", "konstr_tyyp_selg",
                "konstr_staatus_selg", "diam", "alg", "lopp",
                "tx_manteltoru_isolats", "tx_kirjeldus",
                "tx_ehitustooted",
            ),
            current(details.set_veka_construction),
            failed("construction", details.set_veka_construction), limit=2000,
        )
        self.network.query_eelis_pages(
            "f_puuraugud_puurauk_param",
            {
                "param_puurauk_id": f"eq.{identifier}",
                "order": "katse_kp.desc",
            },
            (
                "puurauk_param_id", "puurauk_param_tyyp",
                "puurauk_param_tyyp_selg", "veekompleks",
                "veekompleks_selg", "sygavus", "st_veetase",
                "dyn_veetase", "alandus", "deebit", "kestus",
                "tx_tehnoloogia", "katse_kp",
            ),
            current(details.set_veka_pumping_tests),
            failed("pumping tests", details.set_veka_pumping_tests), limit=2000,
        )
        self.network.query_eelis_pages(
            "f_puuraugud",
            {"id": f"eq.{identifier}"},
            (
                "puurija_nimi", "puurija_kood", "puur_org",
                "puur_viis_selg", "puur_mark",
            ),
            current(
                lambda rows: details.set_veka_overview_fields(
                    rows[0] if rows else {}
                )
            ),
            failed("driller information"), limit=1,
        )
        cadastral_number = veka_cadastral_number(
            attributes.get("katastri_nr"),
            source_row.get("katastri_nr"),
            attributes.get("kkr_kood"),
            source_row.get("kkr_kood"),
        )
        registry_code = str(
            attributes.get("kkr_kood")
            or source_row.get("kkr_kood")
            or (
                f"PRK{int(cadastral_number):07d}"
                if cadastral_number else ""
            )
        ).strip()

        chemistry = {"primary": None, "legacy": None}
        protocol_started = {"value": False}

        def show_chemistry():
            if (
                token != self._detail_token
                or chemistry["primary"] is None
                or chemistry["legacy"] is None
            ):
                return
            rows = merge_water_analyses(
                chemistry["primary"], chemistry["legacy"]
            )
            details.set_veka_chemistry(rows)
            if not protocol_started["value"]:
                protocol_started["value"] = True
                resolve_protocols(rows)

        def chemistry_failed(source, label):
            def handler(error):
                if token != self._detail_token:
                    return
                chemistry[source] = []
                show_chemistry()
                self.warning(
                    f"Could not load VEKA {label}: {error}"
                    if self.language == "en" else
                    f"VEKA andmete {label} laadimine ebaõnnestus: {error}"
                )
            return handler

        def primary_loaded(rows):
            if token != self._detail_token:
                return
            for row in rows:
                permit = row.get("loa_nr")
                if permit:
                    row["_protocol_url"] = kotkas_registry_url(permit)
                    row["_protocol_label"] = "KOTKAS"
                row["_source"] = "KOTKAS"
            chemistry["primary"] = rows
            show_chemistry()

        def legacy_loaded(payload, source_url):
            if token != self._detail_token:
                return
            chemistry["legacy"] = parse_veka_water_analyses(
                payload, source_url
            )
            show_chemistry()

        def resolve_protocols(rows):
            """Resolve KOTKAS report periods and direct protocol files."""
            by_permit = {}
            for row in rows:
                permit = str(row.get("loa_nr") or "").strip()
                if permit:
                    by_permit.setdefault(permit, []).append(row)
            if not by_permit:
                return
            pending = {"count": len(by_permit)}
            reports = {}

            def registries_finished():
                pending["count"] -= 1
                if pending["count"] or token != self._detail_token:
                    return
                if not reports:
                    details.set_veka_chemistry(rows)
                    return
                report_pending = {"count": len(reports)}

                def report_finished():
                    report_pending["count"] -= 1
                    if (
                        not report_pending["count"]
                        and token == self._detail_token
                    ):
                        details.set_veka_chemistry(rows)

                for report_url, report_rows in reports.items():
                    def report_loaded(
                        payload, report_rows=report_rows,
                        report_url=report_url,
                    ):
                        if token == self._detail_token:
                            protocols = parse_kotkas_protocols(payload)
                            for row in report_rows:
                                files = protocols.get(
                                    normalized_analysis_number(
                                        row.get("analyys_number")
                                    ),
                                    [],
                                )
                                if files:
                                    row["_protocol_url"] = files[0]["url"]
                                    row["_protocol_label"] = (
                                        files[0].get("label") or
                                        self.t("Protokoll")
                                    )
                                else:
                                    row["_protocol_url"] = report_url
                                    row["_protocol_label"] = "KOTKAS"
                        report_finished()

                    self.network.get_text(
                        report_url,
                        report_loaded,
                        lambda _error: report_finished(),
                    )

            for permit, permit_rows in by_permit.items():
                def registry_loaded(payload, permit_rows=permit_rows):
                    if token == self._detail_token:
                        period_urls = parse_kotkas_report_registry(payload)
                        for row in permit_rows:
                            period = (
                                str(
                                    row.get("aruandlusperiood_algus_as")
                                    or ""
                                )[:10],
                                str(
                                    row.get("aruandlusperiood_lopp_as")
                                    or ""
                                )[:10],
                            )
                            report_url = period_urls.get(period)
                            if report_url:
                                reports.setdefault(report_url, []).append(row)
                    registries_finished()

                self.network.get_text(
                    kotkas_registry_url(permit),
                    registry_loaded,
                    lambda _error: registries_finished(),
                )

        if cadastral_number:
            self.network.query_eelis_pages(
                "f_veenaitajad_W10_W1_public",
                {"katastri_number": f"eq.{cadastral_number}"},
                (
                    "loa_nr", "aruandlusperiood_algus_as",
                    "aruandlusperiood_lopp_as", "analyys_number",
                    "proov_algus",
                    "naitaja_kood", "naitaja_nimi", "naitaja_tulem",
                    "naitaja_yhik", "proov_liik",
                ),
                primary_loaded,
                chemistry_failed("primary", "water chemistry"),
                limit=5000,
            )
        else:
            chemistry["primary"] = []

        if registry_code:
            veka_url = (
                "https://veka.eelis.ee/puurauk/"
                f"{quote(registry_code, safe='')}"
            )
            self.network.get_text(
                veka_url,
                lambda payload: legacy_loaded(payload, veka_url),
                chemistry_failed("legacy", "legacy water chemistry"),
            )
        else:
            chemistry["legacy"] = []
        show_chemistry()

    def _load_sarv_point_details(self, role, name, attributes, layer, feature):
        attributes = self._detail_attributes_with_location(
            attributes, layer, feature
        )
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
            for key in (
                "_qeoloog_x_3301", "_qeoloog_y_3301",
                "_qeoloog_longitude", "_qeoloog_latitude",
            ):
                if attributes.get(key) not in (None, ""):
                    overview[key] = attributes[key]
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
            source_type = overview["source_type"]
            manual_links = self._manual_egt_links_for_sarv(
                source_type, entity.get("id"),
            )
            if len(manual_links) == 1:
                self._open_manual_egt_link(
                    manual_links[0], token, failed("EGT"),
                )
                return
            candidates = self._egt_candidates_for_sarv_point(
                match_entity, source_type, entity.get("id"),
            )
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

    def _manual_egt_links_for_sarv(self, source_type, source_id):
        links = []
        for match_key, value in self.sarv_matches.items():
            if not isinstance(value, dict):
                continue
            if (
                value.get("source_type") != source_type
                or str(value.get("sarv_id") or "") != str(source_id)
            ):
                continue
            key_parts = str(match_key).split(":", 2)
            if (
                len(key_parts) != 3
                or key_parts[0] not in {"boreholes", "observations"}
                or key_parts[1] not in {"gea", "global"}
            ):
                continue
            links.append({
                "role": key_parts[0],
                "key_type": key_parts[1],
                "key_value": key_parts[2],
                "record": value,
            })
        return links

    def _egt_candidate_from_attributes(self, role, attributes, manual=False):
        global_id = (
            attributes.get("esri_globalid") or attributes.get("globalid")
        )
        if not global_id:
            return None
        gea_id = attributes.get("gea_id")
        object_path = (
            "puurauk" if role == "boreholes" else "vaatluspunkt"
        )
        display = (
            attributes.get("nimi") or attributes.get("alias")
            or gea_id or global_id
        )
        return {
            "id": global_id,
            "role": role,
            "attributes": attributes,
            "text": str(display),
            "url": (
                f"https://gis.egt.ee/auk/{object_path}/{gea_id}/vaade"
                if gea_id else ""
            ),
            "evidence": self.t(
                "Kohalik parandus" if manual else "Käsitsi kinnitatud"
            ),
            "confirmed": True,
            "manual": bool(manual),
            "score": 5000 if manual else 2000,
        }

    def _loaded_egt_candidate(self, link):
        role = link.get("role")
        key_type = link.get("key_type")
        value = str(link.get("key_value") or "")
        for layer in self._role_layers(role):
            if key_type == "gea" and value.isdigit():
                expression = f'"gea_id" = {value}'
            else:
                field = next((
                    name for name in ("esri_globalid", "globalid")
                    if layer.fields().indexOf(name) >= 0
                ), "")
                if not field:
                    continue
                safe = value.replace("'", "''")
                expression = f'"{field}" = \'{safe}\''
            request = QgsFeatureRequest().setFilterExpression(expression)
            request.setLimit(1)
            for feature in layer.getFeatures(request):
                attributes = {
                    field.name(): feature.attribute(field.name())
                    for field in layer.fields()
                }
                return self._egt_candidate_from_attributes(
                    role, attributes, manual=True,
                )
        return None

    def _open_manual_egt_link(self, link, token, failure):
        candidate = self._loaded_egt_candidate(link)
        if candidate:
            self._open_egt_candidate(candidate)
            return

        def loaded(attributes):
            if token != self._detail_token:
                return
            candidate = self._egt_candidate_from_attributes(
                link.get("role"), attributes, manual=True,
            )
            if candidate:
                self._open_egt_candidate(candidate)
            else:
                failure("Invalid EGT response")

        self.network.query_egt_object(
            link.get("role"), link.get("key_type"),
            link.get("key_value"), loaded, failure,
        )

    def _egt_candidates_for_sarv_point(
        self, entity, source_type="", source_id="",
    ):
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
                    if (
                        source_type == "drillcore"
                        and str(source_id).isdigit()
                        and layer.fields().indexOf("sarv_id") >= 0
                    ):
                        sarv_request = QgsFeatureRequest().setFilterExpression(
                            f'"sarv_id" = {int(source_id)}'
                        )
                        sarv_request.setLimit(20)
                        for feature in layer.getFeatures(sarv_request):
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
                        record = self.sarv_matches.get(
                            self._egt_match_key(role, attrs), {}
                        )
                        if not isinstance(record, dict):
                            record = {}
                        invalid_sarv_id = bool(
                            record.get("invalid_sarv_id")
                        )
                        invalid_ma_id = bool(record.get("invalid_ma_id"))
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
                            not invalid_ma_id and land_board_id
                            == self._normalized(attrs.get("ma_orig_id"))
                        )
                        explicit = bool(
                            not invalid_sarv_id
                            and source_type == "drillcore"
                            and str(attrs.get("sarv_id") or "").strip()
                            == str(source_id)
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
                            direct or explicit
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
                        if explicit:
                            evidence.append(self.t("SARV ID kattub"))
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
                            ) + (800 if explicit else 0
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
        attributes = self._detail_attributes_with_location(attributes)
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

        def load_profile_from_api(wfs_error):
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

        def load_profile_from_wfs(api_error):
            if token != self._detail_token:
                return

            def wfs_failed(wfs_error):
                failed(self.t("Läbilõige"))(f"{api_error}; {wfs_error}")

            self.network.query_geological_units(
                role,
                global_id,
                current(details.set_profile),
                wfs_failed,
            )

        if self.egt_data_source == "api" and role == "boreholes":
            self.network.query_borehole_profile(
                global_id,
                current(details.set_profile),
                load_profile_from_wfs,
            )
        else:
            self.network.query_geological_units(
                role,
                global_id,
                current(details.set_profile),
                load_profile_from_api,
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

        def load_locality(locality, drillcore_id=None):
            locality_id = locality.get("id")
            if not locality_id:
                clear_sarv()
                return
            details.set_sarv_locality(locality)

            def drillcores_loaded(payload):
                cores = self._sarv_rows(payload)
                effective_drillcore_id = (
                    drillcore_id
                    if drillcore_id not in (None, "")
                    else selected_drillcore_id
                )
                if effective_drillcore_id not in (None, ""):
                    cores = [
                        core for core in cores
                        if str(core.get("id")) == str(effective_drillcore_id)
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
            role = {
                "site": "sarv_sites",
                "drillcore": "sarv_drillcores",
            }.get(source_type, "sarv_localities")
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
            elif source_type == "drillcore":
                def drillcore_loaded(core):
                    if token != self._detail_token or not isinstance(core, dict):
                        return
                    locality = core.get("locality")
                    locality_id = (
                        locality.get("id") if isinstance(locality, dict)
                        else locality
                    )
                    if not locality_id:
                        clear_sarv()
                        return
                    self.network.query_sarv(
                        f"localities/{locality_id}", {"expand": "*"},
                        current(
                            lambda row: load_locality(row, source_id)
                        ),
                        request_failed("SARV locality", clear_sarv),
                    )

                cached_core = candidate.get("row")
                cached_locality = (
                    cached_core.get("locality")
                    if isinstance(cached_core, dict) else None
                )
                if cached_locality:
                    drillcore_loaded(cached_core)
                else:
                    self.network.query_sarv(
                        f"drillcores/{source_id}", {"expand": "*"},
                        current(drillcore_loaded),
                        request_failed("SARV drill core", clear_sarv),
                    )
            else:
                self.network.query_sarv(
                    f"localities/{source_id}", {"expand": "*"},
                    current(load_locality),
                    request_failed("SARV locality", clear_sarv),
                )

        def saved_match():
            value = self.sarv_matches.get(match_key) if match_key else None
            return value if isinstance(value, dict) else None

        def has_manual_match(value=None):
            value = saved_match() if value is None else value
            if not isinstance(value, dict):
                return False
            source_type = value.get("source_type")
            source_id = str(value.get("sarv_id") or "").strip()
            return (
                source_type in {"drillcore", "locality", "site"}
                and source_id.isdigit() and int(source_id) > 0
            )

        def save_record(value):
            if not match_key:
                return
            keep = (
                has_manual_match(value)
                or bool(value.get("invalid_sarv_id"))
                or bool(value.get("invalid_ma_id"))
            )
            if keep:
                self.sarv_matches[match_key] = value
            else:
                self.sarv_matches.pop(match_key, None)
            PluginSettings.save_sarv_matches(self.sarv_matches)

        def persist_match(source_type, source_id):
            if not match_key:
                return
            value = dict(saved_match() or {})
            value.update({
                "source_type": source_type,
                "sarv_id": source_id,
                "gea_id": str(attributes.get("gea_id") or ""),
                "original_sarv_id": sarv_id,
                "original_ma_id": str(attributes.get("ma_orig_id") or ""),
                "source": "local_override",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            save_record(value)

        def persist_invalid(field, checked):
            if field not in {"invalid_sarv_id", "invalid_ma_id"}:
                return
            value = dict(saved_match() or {})
            value[field] = bool(checked)
            value.update({
                "gea_id": str(attributes.get("gea_id") or ""),
                "original_sarv_id": sarv_id,
                "original_ma_id": str(attributes.get("ma_orig_id") or ""),
                "source": (
                    (value.get("source") or "local_override")
                    if has_manual_match(value)
                    else "invalid_source_id"
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            save_record(value)
            self.success(self.t("Vigase ID märge salvestati"))
            refresh_resolution()

        def remove_manual(candidate=None):
            value = dict(saved_match() or {})
            for field in ("source_type", "sarv_id"):
                value.pop(field, None)
            value["source"] = "invalid_source_id"
            value["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_record(value)
            self.success(
                "Local SARV correction removed; the GEA link is active again."
                if self.language == "en" else
                "Kohalik SARV parandus eemaldati; GEA seos on taas aktiivne."
            )
            refresh_resolution()

        def confirm_candidate(candidate):
            if not match_key:
                return
            persist_match(
                candidate.get("source_type"), candidate.get("sarv_id"),
            )
            candidate["confirmed"] = True
            candidate["manual"] = True
            candidate["evidence"] = self.t("Käsitsi kinnitatud")
            self.success(
                "SARV match saved locally." if self.language == "en"
                else "SARV vaste salvestati kohalikult."
            )
            refresh_resolution(candidate.get("row"))

        def cache_loaded(localities, sites, drillcores, generation):
            if (
                token != self._detail_token
                or generation != resolution_state["generation"]
            ):
                return
            candidates = self._sarv_candidates_for_egt(
                localities, sites, attributes, drillcores,
                invalid_sarv_id=bool(
                    saved_match() and saved_match().get("invalid_sarv_id")
                ),
                invalid_ma_id=bool(
                    saved_match() and saved_match().get("invalid_ma_id")
                ),
            )
            saved = saved_match()
            if (
                has_manual_match(saved)
                and saved.get("source_type") != "drillcore"
            ):
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
                            invalid_sarv_id=bool(
                                saved.get("invalid_sarv_id")
                            ),
                            invalid_ma_id=bool(saved.get("invalid_ma_id")),
                        )
                if manual:
                    manual["confirmed"] = True
                    manual["manual"] = True
                    manual["evidence"] = self.t("Kohalik parandus")
                    details.add_match_candidates(
                        "Kinnitatud SARV vaste", [manual],
                        open_candidate, remove_callback=remove_manual,
                    )
                    load_candidate(manual)
                    return

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

        def render_editor():
            if not match_key:
                return
            saved = saved_match()
            manual = has_manual_match(saved)
            current_id = (
                saved.get("sarv_id") if manual else sarv_id
            )
            current_type = (
                saved.get("source_type") if manual else "drillcore"
            )
            details.add_sarv_match_editor(
                current_type, current_id, manual, set_manual_sarv_object,
                remove_manual if manual else None,
                source_sarv_id=sarv_id,
                source_ma_id=attributes.get("ma_orig_id"),
                invalid_sarv_id=bool(
                    saved and saved.get("invalid_sarv_id")
                ),
                invalid_ma_id=bool(saved and saved.get("invalid_ma_id")),
                invalid_callback=persist_invalid,
            )

        def display_direct_entity(
            entity, source_type, manual, generation,
        ):
            if (
                token != self._detail_token
                or generation != resolution_state["generation"]
            ):
                return
            if not isinstance(entity, dict) or not entity.get("id"):
                clear_sarv()
                return
            candidate = self._sarv_candidate(
                entity, source_type, attributes, allow_weak=True,
                invalid_sarv_id=bool(
                    saved_match() and saved_match().get("invalid_sarv_id")
                ),
                invalid_ma_id=bool(
                    saved_match() and saved_match().get("invalid_ma_id")
                ),
            )
            if not candidate:
                clear_sarv()
                return
            candidate["confirmed"] = True
            candidate["manual"] = manual
            candidate["score"] = max(candidate.get("score", 0), 5000)
            candidate["evidence"] = self.t(
                "Kohalik parandus" if manual else "GEA SARV ID"
            )
            details.add_match_candidates(
                "Kinnitatud SARV vaste", [candidate], open_candidate,
            )
            load_candidate(candidate)

        def refresh_resolution(prefetched_core=None):
            resolution_state["generation"] += 1
            generation = resolution_state["generation"]
            details.reset_match_rows()
            clear_sarv()
            render_editor()
            saved = saved_match()
            manual = has_manual_match(saved)
            saved_type = (
                saved.get("source_type") if manual else ""
            )
            valid_saved_type = saved_type in {
                "drillcore", "locality", "site",
            }
            source_type = (
                saved_type if valid_saved_type else "drillcore"
            )
            effective_id = str(
                saved.get("sarv_id") if valid_saved_type
                else "" if saved and saved.get("invalid_sarv_id") else sarv_id
            ).strip()
            valid_id = effective_id.isdigit() and int(effective_id) > 0
            if valid_id:
                if (
                    isinstance(prefetched_core, dict)
                    and str(prefetched_core.get("id")) == effective_id
                ):
                    display_direct_entity(
                        prefetched_core, source_type, manual, generation,
                    )
                    return

                def direct_loaded(entity):
                    display_direct_entity(
                        entity, source_type, manual, generation,
                    )

                def direct_failed(error):
                    if (
                        token == self._detail_token
                        and generation == resolution_state["generation"]
                    ):
                        clear_sarv()
                        failed("SARV")(error)

                endpoint = {
                    "drillcore": "drillcores",
                    "locality": "localities",
                    "site": "sites",
                }[source_type]
                self.network.query_sarv(
                    f"{endpoint}/{effective_id}", {"expand": "*"},
                    direct_loaded, direct_failed,
                )
                return

            self._ensure_sarv_point_cache(
                lambda localities, sites, drillcores: cache_loaded(
                    localities, sites, drillcores, generation,
                ),
                request_failed("SARV locations", clear_sarv),
            )

        def set_manual_sarv_object(source_type, source_id):
            if not match_key:
                return
            source_id = int(source_id)
            source_label = self.t({
                "locality": "lokaliteet",
                "site": "uuringupunkt",
            }.get(source_type, "puursüdamik"))
            self.message(
                f"Checking SARV {source_label} {source_id}..."
                if self.language == "en" else
                f"Kontrollitakse SARV objekti {source_label} {source_id}..."
            )

            def verified(entity):
                if token != self._detail_token:
                    return
                if not isinstance(entity, dict) or not entity.get("id"):
                    invalid("Invalid response")
                    return
                persist_match(source_type, entity.get("id"))
                self.success(
                    f"Local SARV correction saved: {source_label} {entity.get('id')}."
                    if self.language == "en" else
                    f"Kohalik SARV parandus salvestati: {source_label} {entity.get('id')}."
                )
                refresh_resolution(entity)

            def invalid(error):
                if token == self._detail_token:
                    self.warning(
                        f"SARV {source_label} {source_id} was not found; the correction was not saved."
                        if self.language == "en" else
                        f"SARV objekti {source_label} {source_id} ei leitud; parandust ei salvestatud."
                    )

            endpoint = {
                "drillcore": "drillcores",
                "locality": "localities",
                "site": "sites",
            }.get(source_type)
            if not endpoint:
                invalid("Unsupported SARV object type")
                return
            self.network.query_sarv(
                f"{endpoint}/{source_id}", {"expand": "*"},
                verified, invalid,
            )

        resolution_state = {"generation": 0}
        refresh_resolution()

    def _sarv_candidates_for_egt(
        self, localities, sites, attributes, drillcores=(),
        invalid_sarv_id=False, invalid_ma_id=False,
    ):
        candidates = []
        direct_core_candidate = None
        for source_type, rows in (
            ("locality", localities), ("site", sites),
        ):
            for row in rows:
                candidate = self._sarv_candidate(
                    row, source_type, attributes,
                    invalid_sarv_id=invalid_sarv_id,
                    invalid_ma_id=invalid_ma_id,
                )
                if candidate:
                    candidates.append(candidate)
        sarv_id = str(attributes.get("sarv_id") or "").strip()
        valid_sarv_id = (
            not invalid_sarv_id
            and sarv_id.isdigit() and int(sarv_id) > 0
        )
        if valid_sarv_id:
            core = next((
                row for row in drillcores
                if str(row.get("id")) == sarv_id
            ), None)
            if core:
                candidate = self._sarv_candidate(
                    core, "drillcore", attributes, allow_weak=True,
                    invalid_sarv_id=invalid_sarv_id,
                    invalid_ma_id=invalid_ma_id,
                )
                if candidate:
                    candidate["confirmed"] = True
                    candidate["score"] = max(candidate.get("score", 0), 5000)
                    candidate["evidence"] = self.t("GEA SARV ID")
                    candidates.append(candidate)
                    direct_core_candidate = candidate
        candidates.sort(key=lambda item: item["score"], reverse=True)
        if direct_core_candidate:
            for item in candidates:
                item["confirmed"] = item is direct_core_candidate
            return candidates
        if valid_sarv_id:
            # A GEA sarv_id belongs exclusively to the SARV drillcore
            # namespace. Never offer a same-numbered locality or research site
            # when that drillcore is absent.
            return []
        confirmed = [item for item in candidates if item["confirmed"]]
        if len(confirmed) != 1:
            for item in candidates:
                item["confirmed"] = False
        return candidates

    def _sarv_candidate(
        self, row, source_type, attributes, allow_weak=False,
        invalid_sarv_id=False, invalid_ma_id=False,
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
            not invalid_ma_id and official_id
            and official_id == self._normalized(attributes.get("ma_orig_id"))
        )
        explicit_match = not invalid_sarv_id and source_type == "drillcore" and (
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
        source_label = self.t({
            "site": "uuringupunkt",
            "drillcore": "puursüdamik",
        }.get(source_type, "lokaliteet"))
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

    @classmethod
    def _search_relevance(
        cls, query, primary_values=(), identifier_values=(),
        other_values=(),
    ):
        """Return a deterministic relevance score, or None when not matched."""
        normalized_query = cls._normalized(query)
        if not normalized_query:
            return 0

        def values(items):
            normalized = []
            for value in items:
                if value in (None, ""):
                    continue
                text = cls._normalized(value)
                if text:
                    normalized.append(text)
            return normalized

        primary = values(primary_values)
        identifiers = values(identifier_values)
        others = values(other_values)
        searchable = primary + identifiers + others
        tokens = normalized_query.split()
        if not searchable or not all(
            any(token in value for value in searchable)
            for token in tokens
        ):
            return None

        if normalized_query in identifiers:
            return 1000
        if normalized_query in primary:
            return 950
        if any(value.startswith(normalized_query) for value in primary):
            return 850
        if any(normalized_query in value for value in primary):
            return 800
        if any(value.startswith(normalized_query) for value in identifiers):
            return 650
        if any(normalized_query in value for value in searchable):
            return 600
        return 500

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
