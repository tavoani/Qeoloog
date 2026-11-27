"""Qeoloog - configurable Estonian geoscience layers and borehole explorer."""

import csv
from datetime import datetime, timezone
import json
from math import hypot, isfinite
from pathlib import Path
import sqlite3
from unicodedata import normalize
from urllib.parse import quote

from qgis.PyQt.QtCore import (
    QDateTime, QTime, Qt, QTimer, QUrl, QUrlQuery, QVariant,
)
from qgis.PyQt.QtGui import (
    QAction, QColor, QDesktopServices, QFont, QIcon, QPainter, QPen, QPixmap,
)
from qgis.PyQt.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QToolButton,
)
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsArcGisRestUtils,
    QgsAuthMethodConfig,
    QgsCategorizedSymbolRenderer,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsDataSourceUri,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsFields,
    QgsExpression,
    QgsExpressionContext,
    QgsGraduatedSymbolRenderer,
    QgsExpressionContextUtils,
    QgsFillSymbol,
    QgsGeometry,
    QgsJsonUtils,
    QgsLineSymbol,
    QgsLineString,
    QgsMarkerSymbol,
    QgsMultiLineString,
    QgsPalLayerSettings,
    QgsPathResolver,
    QgsPoint,
    QgsProject,
    QgsPointXY,
    QgsRasterLayer,
    QgsRasterShader,
    QgsRectangle,
    QgsRendererRange,
    QgsRendererCategory,
    QgsRelation,
    QgsRuleBasedRenderer,
    QgsSingleSymbolRenderer,
    QgsSingleBandPseudoColorRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsHighlight, QgsRubberBand

from .corrections import (
    CORE_FIELDS,
    apply_core_values,
    changed_core_values,
    core_correction_key,
    core_record_id,
    core_values,
)
from .archive_reports import ArchiveReportsMixin
from .local_object_workflow import LocalObjectWorkflowMixin
from .dock import GeophysicsFieldworkDialog, QeoloogDock
from .faktika_editor import FaktikaEditorDialog
from .elevation_check import (
    BK77,
    EH2000,
    ELLIPSOIDAL,
    UNKNOWN,
    conversion_plan,
    matching_range,
    sample_summary,
)
from .faktika import (
    FAKTIKA_GROUP_NAME,
    FAKTIKA_ITEM_ID,
    FAKTIKA_LAYER_IDS,
    FAKTIKA_LAYER_NAMES,
    FAKTIKA_SERVICE_URL,
    FAKTIKA_WORKSPACES,
    OBJECT_TYPES,
    UNIT_COLORS,
    UNIT_TYPES,
    build_apply_edits,
    decode_coded_row,
    discover_faktika_layer_ids,
    editable_fields,
    escape_where,
    new_guid,
    normalize_guid,
    parent_defaults,
    subtype_label,
    unit_category_code,
    validate_apply_edits_response,
)
from .gtk import parse_feature_info_html
from .egt_labels import egt_label_summary
from .fieldwork import (
    coded_value_options,
    read_collar_points,
    split_line_parts,
    value_map_options,
)
from .i18n import GROUP_LABELS, translate
from .identify import (
    CrossSectionLineTool,
    ElevationCandidateTool,
    EgtIdentifyTool,
    ExportAreaTool,
    FaktikaPointTool,
)
from .map_point_labels import (
    join_label_components, label_component, normalize_sarv_core_depth,
)
from .models import (
    DEFAULT_EGT_LABEL_FIELDS,
    DEFAULT_GROUP_STATE,
    DEFAULT_LAYERS,
    DEFAULT_MAP_LABEL_FIELDS,
    EGT_LABEL_FIELD_KEYS,
    EGT_LABEL_KEYS_BY_ROLE,
    GROUPS,
    LayerDefinition,
    LATVIA_INSPIRE_GEOLOGY_WFS,
    LEGACY_LATVIA_INSPIRE_GEOLOGY_WFS,
    MAP_GRIDS,
    MAP_LABEL_KEYS_BY_ROLE,
    PluginSettings,
    is_legacy_latvia_wfs,
    normalize_map_label_fields,
)
from .network import NetworkClient
from .maaru import (
    MAARU_ARCHIVE_URL,
    MAX_ARCHIVE_BYTES as MAARU_MAX_ARCHIVE_BYTES,
    MaaruDatabase,
    build_database as build_maaru_database,
    core_boxes as maaru_core_boxes,
    detail_url as maaru_detail_url,
    geological_units as maaru_geological_units,
    image_attachments as maaru_image_attachments,
    samples as maaru_samples,
)
from .observations import observation_label
from .portal import (
    EGT_PORTAL_RESOURCE,
    PORTAL_EDITING_ENABLED,
    egt_oauth_config_json,
    feature_layer_url,
    is_arcgis_feature_protocol,
    is_arcgis_map_protocol,
    map_layer_url,
)
from .stratigraphy import stratigraphic_thickness_label_items
from .veka import (
    FILTER_CONSTRUCTION_TYPES,
    aggregate as veka_aggregate,
    analysis_codes,
    analysis_matches as veka_analysis_matches,
    analysis_options as veka_analysis_options,
    analysis_row_value,
    analysis_row_result,
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
    usage_options as veka_usage_options,
    usage_value as veka_usage_value,
)


class QeoloogPlugin(ArchiveReportsMixin, LocalObjectWorkflowMixin):
    """Manage layer shortcuts, menus, filtering and EGT object data."""

    MENU = "&Qeoloog"
    SOURCE_PROPERTY = "qeoloog/source_id"
    LEGACY_SOURCE_PROPERTY = "eesti_wms_nupud/source_id"
    ROLE_PROPERTY = "qeoloog/role"
    LEGACY_ROLE_PROPERTY = "eesti_wms_nupud/role"
    SEARCH_RESULT_PROPERTY = "qeoloog/search_result"
    SEARCH_DEFINITION_PROPERTY = "qeoloog/search_definition_code"
    SEARCH_KEY_PROPERTY = "qeoloog/search_key"
    GEOPHYSICS_FIELDWORK_URL = (
        "https://gis.egt.ee/arcgis/rest/services/Kaardistamine/"
        "Geofüüsika_välitööd/FeatureServer"
    )
    GEOPHYSICS_FIELDWORK_LAYER = "6"
    PORTAL_LAYER_BUNDLES = {
        "field_mapping": {
            "item_id": "142fb34034104a7aa4bf0f721a546e1b",
            "title": "Faktika välikaardistamine",
            "group": "EGT – Faktika välikaardistamine",
            "url": (
                "https://gis.egt.ee/arcgis/rest/services/Kaardistamine/"
                "Faktika_välikaardistamine/FeatureServer"
            ),
            "layers": ((0, "Välitöö faktika"), (1, "Välitöö kirjeldus")),
        },
    }
    CATEGORY_COLORS = {1: "#d7bd72", 2: "#7796c6", 3: "#b56b6b", 997: "#8f8f8f"}
    MINERAL_LAYER_ROLES = {
        "mineral_deposits", "mining_claims", "exploration_areas",
    }
    # A line is deliberately a little wider than the snapping tolerance.  A
    # snap only helps place the line on an object; the corridor makes it useful
    # for building a practical multi-hole section when the line crosses an
    # area with several nearby points.
    CROSS_SECTION_AUTO_ADD_TOLERANCE_M = 100.0
    CROSS_SECTION_AUTO_ADD_MAX = 500
    MINERAL_RESOURCE_CLASSES = (
        ("liiv", "Liiv", "#e8d38a"),
        ("kruus", "Kruus", "#c7a56a"),
        ("turvas", "Turvas", "#795548"),
        ("lubjakivi", "Lubjakivi", "#a8b9c7"),
        ("dolokivi", "Dolokivi", "#7f9aa8"),
        ("savi", "Savi", "#d58b72"),
        ("põlevkivi", "Põlevkivi", "#66735b"),
        ("fosforiit", "Fosforiit", "#8f74a8"),
        ("meremuda", "Meremuda", "#4f9da6"),
        ("järvemuda", "Järvemuda", "#68aeb3"),
        ("järvelubi", "Järvelubi", "#d8d6ad"),
        ("aluskorra ehituskivi", "Aluskorra ehituskivi", "#9b6d7d"),
    )
    REGISTRY_SEARCH = {
        "mineral_deposits": {
            "code": "MR",
            "source": "Maavarade register",
            "type": "Maardla",
            "name_fields": ("maardla_nimetus", "maardla_osa_nimetus"),
            "identifier_fields": ("maardla_id", "registrikaardi_nr"),
            "numeric_fields": (),
            "other_fields": ("maavara",),
            "filter_field": "maardla_id",
            "sort_by": "maardla_nimetus",
        },
        "mining_claims": {
            "code": "ME",
            "source": "Maavarade register",
            "type": "Aktiivne mäeeraldis",
            "name_fields": ("maeeraldise_nimetus",),
            "identifier_fields": (
                "maeeraldise_kood", "maeeraldise_id", "loa_nr",
            ),
            "numeric_fields": (),
            "other_fields": ("pohimaavara",),
            "filter_field": "maeeraldise_id",
            "sort_by": "maeeraldise_nimetus",
        },
        "exploration_areas": {
            "code": "UA",
            "source": "Maavarade register",
            "type": "Aktiivne uuringuala",
            "name_fields": ("uuringuala_nimi", "maardla_nimi"),
            "identifier_fields": (
                "uuringuala_kood", "uuringuala_id", "loa_nr",
            ),
            "numeric_fields": (),
            "other_fields": ("maavarad",),
            "filter_field": "uuringuala_id",
            "sort_by": "uuringuala_nimi",
        },
        "archive_survey_areas": {
            "code": "EGF",
            "source": "Geoloogiafond",
            "type": "Geoloogiafondi uuringuala",
            "name_fields": (
                "nimetus", "nimetus_orig", "nimetus_eng", "autor",
                "maardla", "votmesona",
            ),
            "identifier_fields": (),
            # ``id`` is a CQL reserved word on this GeoServer. The public
            # Geological Archive identifier exposed to users is ``egf_id``.
            "numeric_fields": ("egf_id",),
            "other_fields": ("aasta", "max_sygavus_m"),
            "filter_field": "egf_id",
            "sort_by": "nimetus",
        },
    }
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
        "veekiht_nimi", "aadress", "z_abs", "sygavus", "kasutus",
        "kasutus_selg",
        "puur_aasta", "kesk_x", "kesk_y", "muut_aeg",
    )

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self.definitions = PluginSettings.load_layers()
        self.toggle_mode = PluginSettings.load_toggle_mode()
        self.language = PluginSettings.load_language()
        self.egt_data_source = PluginSettings.load_egt_data_source()
        self.egt_portal_authcfg = PluginSettings.load_egt_portal_authcfg()
        self.egt_test_server_enabled = (
            PluginSettings.load_egt_test_server_enabled()
        )
        self.portal_editing_enabled = PORTAL_EDITING_ENABLED
        self.label_text_size = PluginSettings.load_label_text_size()
        self.egt_label_fields = PluginSettings.load_map_label_fields()
        self.group_enabled = PluginSettings.load_groups()
        self.network = NetworkClient()
        self._maaru_cache_path = Path(
            QgsApplication.qgisSettingsDirPath()
        ) / "Qeoloog" / "maaru_puursudamikud.sqlite"
        cached_maaru = MaaruDatabase(self._maaru_cache_path)
        self._maaru_db = cached_maaru if cached_maaru.available else None
        self._maaru_loading = False
        self._maaru_waiters = []
        self._maaru_rows = {}
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
        self.egt_portal_menu = None
        self.egt_portal_menu_action = None
        self.egt_portal_button = None
        self.egt_portal_catalog = []
        self.egt_portal_catalog_account = ""
        self.egt_portal_login_loading = False
        self.egt_portal_catalog_loading = False
        self.egt_portal_layer_actions = {}
        self.egt_portal_service_layers = {}
        self.egt_portal_service_loading = set()
        self.faktika_action = None
        self.faktika_workspace_actions = {}
        self.portal_bundle_actions = {}
        self._portal_bundle_metadata = {}
        self._portal_bundle_metadata_loading = set()
        self._portal_bundle_metadata_waiters = {}
        self._faktika_metadata = {}
        self._faktika_metadata_loading = False
        self._faktika_metadata_waiters = []
        self._faktika_workspace_metadata = {}
        self._faktika_workspace_metadata_loading = set()
        self._faktika_workspace_metadata_waiters = {}
        self._faktika_workspace_discovery_loading = set()
        self._faktika_people = None
        self._faktika_people_loading = False
        self._faktika_people_waiters = []
        self._faktika_workspace_people = {}
        self._faktika_workspace_people_loading = set()
        self._faktika_workspace_people_waiters = {}
        self._faktika_public_visibility = {}
        self._faktika_visibility_nodes = {}
        self._current_faktika_context = None
        self._current_faktika_workspace = "faktika"
        self._faktika_dialog = None
        self._egt_portal_catalog_request = 0
        self._egt_portal_menu_generation = 0
        self.dock = None
        self.identify_tool = None
        self.faktika_point_tool = None
        self.faktika_point_previous_tool = None
        self._faktika_pending_new = None
        self.elevation_candidate_tool = None
        self.elevation_candidate_previous_tool = None
        self._elevation_candidate_dialog = None
        self.cross_section_line_tool = None
        self.cross_section_map_band = None
        self.cross_section_previous_tool = None
        self._local_section_bands = []
        self.export_area_tool = None
        self.export_area_band = None
        self.export_area_previous_tool = None
        self.previous_map_tool = None
        self.selection_highlight = None
        self._changing_map_tool = False
        self._unloading = False
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
        self._egt_stratigraphic_thickness_key = None
        self._egt_stratigraphic_thicknesses = {}
        self._egt_stratigraphic_filter_loading = None
        self._egt_stratigraphic_filter_generation = 0
        self._observation_labels = {}
        self._observation_labels_loaded = False
        self._observation_labels_loading = False
        self._observation_labels_generation = 0
        self._egt_map_label_details = {
            "boreholes": {}, "observations": {},
            "faktika": {}, "field_mapping": {},
        }
        self._egt_map_label_loaded_ids = {
            "boreholes": set(), "observations": set(),
            "faktika": set(), "field_mapping": set(),
        }
        self._egt_map_label_loading_ids = {
            "boreholes": set(), "observations": set(),
            "faktika": set(), "field_mapping": set(),
        }
        self._egt_map_label_generation = 0
        self._egt_label_refresh_timer = None
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
        self._veka_legacy_analysis_rows = {}
        self._veka_analysis_loading = set()
        self._veka_analysis_waiters = {}
        self._veka_analysis_grouped = {}
        self._veka_filter_generation = 0
        self._search_filter = None
        self._init_archive_reports()
        self._portal_observed_layer = None
        self._latvia_path_preprocessor_id = None

    def t(self, text):
        return translate(text, self.language)

    def export_sarv_matches(self, path):
        """Export locally persisted EGT–SARV and EGT–MaRu corrections."""
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
                "maaru_object_id": value.get("maaru_id") or "",
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
                    "format": "Qeoloog EGT–SARV and EGT–MaRu link corrections",
                    "version": 3,
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
                "maaru_object_id",
                "sarv_object_type",
                "sarv_object_id", "sarv_drillcore_id", "source",
                "updated_at",
            )
            with target.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        self.success(
            f"Exported {len(rows)} SARV/MaRu links to {target}."
            if self.language == "en" else
            f"Eksporditi {len(rows)} SARV/MaRu seost faili {target}."
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

    def local_core_boxes(self, source, parent_role, parent_id):
        """Return locally added boxes belonging to one displayed object."""
        source = str(source or "").upper()
        rows = []
        for record in self.core_corrections.values():
            if not isinstance(record, dict) or not record.get("is_new"):
                continue
            if str(record.get("source") or "").upper() != source:
                continue
            if str(record.get("parent_role") or "") != str(parent_role or ""):
                continue
            if str(record.get("parent_id") or "") != str(parent_id or ""):
                continue
            record_id = str(record.get("record_id") or "").strip()
            if not record_id:
                continue
            changes = dict(record.get("changes") or {})
            if source == "EGT":
                row = {"globalid": record_id}
            else:
                row = {"id": record_id}
            row = apply_core_values(source, row, changes)
            row["_qeoloog_local"] = True
            rows.append(row)
        return rows

    def save_core_box_correction(
        self, source, row, corrected, context=None, is_new=False,
    ):
        """Persist changed core-box values locally without touching upstream."""
        key = core_correction_key(source, row)
        if not key:
            return False
        original = core_values(source, row)
        changes = (
            {
                field: (corrected or {}).get(field)
                for field in CORE_FIELDS
                if field in (corrected or {})
            }
            if is_new else changed_core_values(original, corrected or {})
        )
        if not changes:
            self.core_corrections.pop(key, None)
        else:
            context = context or {}
            self.core_corrections[key] = {
                "source": str(source).upper(),
                "record_id": core_record_id(source, row),
                "is_new": bool(is_new),
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

    @staticmethod
    def _arcgis_coded_values(domain):
        """Return string-keyed labels from one live ArcGIS coded domain."""
        values = {}
        if not isinstance(domain, dict):
            return values
        for item in domain.get("codedValues", []):
            code = item.get("code")
            name = item.get("name")
            if code not in (None, "") and name not in (None, ""):
                values[str(code)] = str(name)
        return values

    def _cache_egt_domain_metadata(self, table_id, payload):
        """Replace one table's cached domains with current REST metadata."""
        table_id = int(table_id)
        found = {}
        for field in (payload or {}).get("fields", []):
            values = self._arcgis_coded_values(field.get("domain"))
            if values:
                found.setdefault(field.get("name"), {}).update(values)
        # ArcGIS may define a field domain only for individual subtypes.  Core
        # box status in AUQ table 22 is one such field, so collect every
        # subtype domain instead of looking only at fields[].domain.
        for subtype in (payload or {}).get("types", []):
            for field_name, domain in (subtype.get("domains") or {}).items():
                values = self._arcgis_coded_values(domain)
                if values:
                    found.setdefault(field_name, {}).update(values)
        stale = [key for key in self.egt_domains if key[0] == table_id]
        for key in stale:
            self.egt_domains.pop(key, None)
            self.egt_domain_options.pop(key, None)
        for field_name, values in found.items():
            key = (table_id, str(field_name))
            self.egt_domains[key] = values
            self.egt_domain_options[key] = sorted(
                values.items(), key=lambda item: item[1].casefold()
            )

    def refresh_egt_domain(self, table_id, success=None, failure=None):
        """Refresh one EGT table's domains directly from its REST metadata."""
        table_id = int(table_id)

        def loaded(payload):
            if (payload or {}).get("error"):
                error = payload["error"]
                message = (
                    error.get("message", "ArcGIS REST metadata query failed")
                    if isinstance(error, dict) else str(error)
                )
                failed(message)
                return
            self._cache_egt_domain_metadata(table_id, payload)
            if success:
                success()

        def failed(error):
            if failure:
                failure(error)

        self.network.query_auq_metadata(table_id, loaded, failed)

    def sarv_purpose_options(self):
        language_index = 1 if self.language == "en" else 0
        return [
            (str(code), labels[language_index])
            for code, labels in self.SARV_SAMPLE_PURPOSES.items()
        ]

    def _load_egt_domains(self):
        """Load official coded-value domains used by details and filters."""
        pending = {18, 3, 4, 22}

        def loaded(table_id):
            def handler():
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
                if not pending and self.dock:
                    self.dock.filters.reload_domain_options()
                    self.dock.search.reload_domain_options()
                    self.dock.details.refresh_decoded_values()
            return handler

        for table_id in tuple(pending):
            self.refresh_egt_domain(
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
        self._latvia_path_preprocessor_id = QgsPathResolver.setPathPreprocessor(
            self._migrate_latvia_source_uri
        )
        self.toolbar = self.iface.addToolBar("Qeoloog")
        self.toolbar.setObjectName("Qeoloog_Toolbar")
        self._create_dock()
        self.identify_tool = EgtIdentifyTool(self.iface.mapCanvas(), self)
        self.faktika_point_tool = FaktikaPointTool(self.iface.mapCanvas())
        self.faktika_point_tool.pointSelected.connect(
            self._faktika_point_selected
        )
        self.faktika_point_tool.cancelled.connect(
            self._faktika_point_cancelled
        )
        self.elevation_candidate_tool = ElevationCandidateTool(
            self.iface.mapCanvas()
        )
        self.elevation_candidate_tool.pointSelected.connect(
            self._elevation_candidate_selected
        )
        self.elevation_candidate_tool.cancelled.connect(
            self._elevation_candidate_cancelled
        )
        self.cross_section_line_tool = CrossSectionLineTool(
            self.iface.mapCanvas(), self._cross_section_snap_layers
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
        self._upgrade_loaded_portal_bundles()
        project.layersAdded.connect(self._project_layers_changed)
        project.cleared.connect(self._reset_archive_reports)
        project.readProject.connect(self._restore_archive_reports)
        project.readProject.connect(self._refresh_map_labeling)
        project.layersRemoved.connect(self._project_layers_changed)
        self.iface.currentLayerChanged.connect(self._portal_current_layer_changed)
        self._egt_label_refresh_timer = QTimer(self.iface.mainWindow())
        self._egt_label_refresh_timer.setSingleShot(True)
        self._egt_label_refresh_timer.setInterval(250)
        self._egt_label_refresh_timer.timeout.connect(
            self._refresh_egt_map_label_data
        )
        self.iface.mapCanvas().extentsChanged.connect(
            self._schedule_egt_label_refresh
        )
        self._build_actions()
        if self._faktika_is_active():
            # Project layers survive a plugin reload; rebuild the visibility
            # guard for an already loaded internal workspace.
            self._faktika_public_visibility.clear()
            self._hide_public_egt_layers_for_faktika()
        self._load_egt_domains()
        self._load_sarv_filter_options()
        QTimer.singleShot(0, self._refresh_loaded_plugin_layers)
        QTimer.singleShot(0, self._apply_loaded_portal_egt_labeling)
        QTimer.singleShot(
            0,
            lambda: self._hide_public_egt_layers_for_faktika()
            if self._faktika_is_active() else None,
        )
        QTimer.singleShot(0, self.apply_egt_filters)
        QTimer.singleShot(0, self._schedule_egt_label_refresh)
        QTimer.singleShot(
            0, lambda: self._portal_current_layer_changed(
                self.iface.activeLayer()
            )
        )

    def _create_dock(self, tab_index=0, visible=False):
        self.dock = QeoloogDock(self, self.iface.mainWindow())
        self.local_workspace_changed()
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.tabs.setCurrentIndex(max(0, min(tab_index, self.dock.tabs.count() - 1)))
        if visible:
            self.dock.show()
        else:
            self.dock.hide()

    def unload(self):
        self._unloading = True
        if self._latvia_path_preprocessor_id:
            QgsPathResolver.removePathPreprocessor(self._latvia_path_preprocessor_id)
            self._latvia_path_preprocessor_id = None
        self._archive_report_actions.clear()
        self._archive_report_waiters.clear()
        try:
            QgsProject.instance().cleared.disconnect(self._reset_archive_reports)
            QgsProject.instance().readProject.disconnect(self._restore_archive_reports)
            QgsProject.instance().readProject.disconnect(self._refresh_map_labeling)
        except (TypeError, RuntimeError):
            pass
        self._detail_token += 1
        self._observation_labels_generation += 1
        self._egt_map_label_generation += 1
        if self._egt_label_refresh_timer:
            self._egt_label_refresh_timer.stop()
        try:
            self.iface.mapCanvas().extentsChanged.disconnect(
                self._schedule_egt_label_refresh
            )
        except (TypeError, RuntimeError):
            pass
        self._clear_highlight()
        project = QgsProject.instance()
        temporary_elevation_layers = [
            layer.id() for layer in project.mapLayers().values()
            if bool(layer.customProperty("qeoloog/elevation_match", False))
        ]
        if temporary_elevation_layers:
            project.removeMapLayers(temporary_elevation_layers)
        for signal in (project.layersAdded, project.layersRemoved):
            try:
                signal.disconnect(self._project_layers_changed)
            except (TypeError, RuntimeError):
                pass
        try:
            self.iface.currentLayerChanged.disconnect(
                self._portal_current_layer_changed
            )
        except (TypeError, RuntimeError):
            pass
        self._observe_portal_layer(None)
        if self.identify_tool and self.iface.mapCanvas().mapTool() is self.identify_tool:
            self._changing_map_tool = True
            self.iface.mapCanvas().unsetMapTool(self.identify_tool)
            self._changing_map_tool = False
        if (
            self.faktika_point_tool
            and self.iface.mapCanvas().mapTool() is self.faktika_point_tool
        ):
            self.iface.mapCanvas().unsetMapTool(self.faktika_point_tool)
        self._faktika_pending_new = None
        if (
            self.elevation_candidate_tool
            and self.iface.mapCanvas().mapTool()
            is self.elevation_candidate_tool
        ):
            self.iface.mapCanvas().unsetMapTool(
                self.elevation_candidate_tool
            )
        self._elevation_candidate_dialog = None
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
        self.update_local_section_outcrops([])
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
        self.faktika_point_tool = None
        self.faktika_point_previous_tool = None
        self.elevation_candidate_tool = None
        self.elevation_candidate_previous_tool = None
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
        self._build_egt_portal_menu()
        if self.toolbar:
            self.utility_separator = self.toolbar.addSeparator()
        self.identify_action = QAction(
            self._code_icon("i", "#4c6678"), self.t("Objekti andmed"), self.iface.mainWindow()
        )
        self.identify_action.setCheckable(True)
        self.identify_action.setToolTip(
            self.t("Klõpsa toetatud kaardiobjektil ja ava selle andmed")
        )
        self.identify_action.toggled.connect(self.set_identify_active)
        self._register_action(self.identify_action)
        if identify_was_active:
            self._sync_identify_controls(True)

        self.configure_action = QAction(
            self._code_icon("⚙", "#555f69"), self.t("Seadista Qeoloogi"), self.iface.mainWindow()
        )
        self.configure_action.setToolTip(
            self.t(
                "Lisa, muuda või eemalda WMS/WFS/ArcGIS/SARV/VEKA kihte"
            )
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
            nested_menus = {}
            for definition in definitions:
                target_menu = submenu
                nested_name = str(definition.menu_group or "").strip()
                if nested_name:
                    path = ""
                    for part in (
                        value.strip() for value in nested_name.split("/")
                        if value.strip()
                    ):
                        path = f"{path}/{part}" if path else part
                        current = nested_menus.get(path)
                        if current is None:
                            current = target_menu.addMenu(self.t(part))
                            nested_menus[path] = current
                        target_menu = current
                action = target_menu.addAction(
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

    def _build_egt_portal_menu(self):
        parent = self.iface.mainWindow()
        self.egt_portal_menu = QMenu(self.t("EGT Portali kihid"), parent)
        self.egt_portal_menu.aboutToShow.connect(self.sync_dropdown_checks)
        self.egt_portal_menu_action = self.egt_portal_menu.menuAction()
        self.iface.addPluginToMenu(self.MENU, self.egt_portal_menu_action)
        if self.toolbar:
            self.egt_portal_button = QToolButton(self.toolbar)
            self.egt_portal_button.setObjectName("Qeoloog_EGT")
            self.egt_portal_button.setIcon(self._code_icon("EGT", "#256b54"))
            self.egt_portal_button.setToolTip(self.t("EGT Portali kihid"))
            self.egt_portal_button.setMenu(self.egt_portal_menu)
            self.egt_portal_button.setPopupMode(
                QToolButton.ToolButtonPopupMode.InstantPopup
            )
            self.toolbar.addWidget(self.egt_portal_button)
        self._render_egt_portal_menu()

    def _render_egt_portal_menu(self):
        menu = self.egt_portal_menu
        if menu is None:
            return
        self._egt_portal_menu_generation += 1
        generation = self._egt_portal_menu_generation
        self.egt_portal_layer_actions.clear()
        self.faktika_action = None
        self.faktika_workspace_actions.clear()
        self.portal_bundle_actions.clear()
        menu.clear()

        refresh = menu.addAction(self.t("Värskenda Portali kihte"))
        refresh.triggered.connect(self.test_egt_portal_login)
        if self.egt_portal_catalog_account:
            account = menu.addAction(self.egt_portal_catalog_account)
            account.setEnabled(False)
        menu.addSeparator()

        if self.egt_portal_catalog_loading:
            status = menu.addAction(self.t("Portali teenuseid laaditakse…"))
            status.setEnabled(False)
            return
        if not self.egt_portal_catalog and not self.egt_portal_catalog_account:
            status = menu.addAction(self.t("Logi esmalt EGT Portalisse"))
            status.setEnabled(False)
            return

        for workspace_key, workspace in FAKTIKA_WORKSPACES.items():
            if (
                workspace.get("advanced")
                and not self.egt_test_server_enabled
            ):
                continue
            is_test = workspace_key == "faktika_test"
            action = menu.addAction(
                self._code_icon(
                    "T" if is_test else "F",
                    "#c26b16" if is_test else "#1f6f54",
                    emphasized=True,
                ),
                ("⚠ " if is_test else "★ ")
                + self.t(workspace["title"]),
            )
            font = action.font()
            font.setBold(True)
            action.setFont(font)
            action.setCheckable(True)
            action.setChecked(self._faktika_is_active(workspace_key))
            action.setToolTip(self.t(
                "Testserveri andmed; muudatused ei lähe tootmiskeskkonda"
                if is_test else
                "Sisemised puuraugud, vaatluspunktid ja seotud tabelid"
            ))
            action.toggled.connect(
                lambda checked, key=workspace_key:
                self.set_faktika_workspace_active(key, checked)
            )
            self.faktika_workspace_actions[workspace_key] = action
            if workspace_key == "faktika":
                self.faktika_action = action
        for bundle_key, bundle in self.PORTAL_LAYER_BUNDLES.items():
            action = menu.addAction(
                self._code_icon("T", "#4e6c86", emphasized=True),
                "★ " + self.t(bundle["title"]),
            )
            action.setCheckable(True)
            action.setChecked(self._portal_bundle_is_active(bundle_key))
            action.setToolTip(self.t(
                "Seotud Portali kihid ja tabelid avatakse ühe tervikuna"
            ))
            action.toggled.connect(
                lambda checked, key=bundle_key:
                self.set_portal_bundle_active(key, checked)
            )
            self.portal_bundle_actions[bundle_key] = action
            if action.isChecked():
                # Upgrade bundles saved in an older project in place so the
                # point layer is immediately selectable after plugin reload.
                self.set_portal_bundle_active(bundle_key, True)
        menu.addSeparator()

        if not self.egt_portal_catalog:
            status = menu.addAction(self.t("Portali kataloogis pole teenuseid"))
            status.setEnabled(False)
            return

        access_labels = {
            "shared": self.t("Minuga jagatud"),
            "private": self.t("Minuga jagatud"),
            "org": self.t("Organisatsioon"),
            "public": self.t("Avalikud"),
        }
        access_order = ("shared", "org", "public")
        promoted_item_ids = {
            workspace["item_id"] for workspace in FAKTIKA_WORKSPACES.values()
            if workspace.get("item_id")
        } | {
            bundle["item_id"] for bundle in self.PORTAL_LAYER_BUNDLES.values()
        }
        for access in access_order:
            items = [
                item for item in self.egt_portal_catalog
                if item.get("access") == access
                and item.get("id") not in promoted_item_ids
            ]
            if not items:
                continue
            access_menu = menu.addMenu(
                f"{access_labels[access]} ({len(items)})"
            )
            folders = {}
            for item in items:
                folders.setdefault(item.get("folder") or "", []).append(item)
            for folder in sorted(
                folders,
                key=lambda value: (not bool(value), value.casefold()),
            ):
                folder_items = folders[folder]
                folder_title = folder or self.t("Põhikaust")
                folder_menu = access_menu.addMenu(
                    f"{folder_title} ({len(folder_items)})"
                )
                for item in sorted(
                    folder_items,
                    key=lambda row: str(row.get("title") or "").casefold(),
                ):
                    service_menu = folder_menu.addMenu(item["title"])
                    owner = item.get("owner") or ""
                    service_menu.menuAction().setToolTip(
                        f"{owner}\n{item['url']}" if owner else item["url"]
                    )
                    service_menu.aboutToShow.connect(
                        lambda submenu=service_menu, row=item, token=generation:
                        self._open_egt_portal_service_menu(
                            submenu, row, token
                        )
                    )
                    placeholder = service_menu.addAction(
                        self.t("Ava teenuse kihtide lugemiseks")
                    )
                    placeholder.setEnabled(False)

    def _open_egt_portal_service_menu(self, menu, item, generation):
        if generation != self._egt_portal_menu_generation:
            return
        url = item["url"]
        if url in self.egt_portal_service_layers:
            self._fill_egt_portal_service_menu(
                menu, item, self.egt_portal_service_layers[url]
            )
            return
        menu.clear()
        loading = menu.addAction(self.t("Kihte laaditakse…"))
        loading.setEnabled(False)
        if url in self.egt_portal_service_loading:
            return
        self.egt_portal_service_loading.add(url)

        def loaded(options):
            self.egt_portal_service_loading.discard(url)
            if generation != self._egt_portal_menu_generation:
                return
            self.egt_portal_service_layers[url] = options
            self._fill_egt_portal_service_menu(menu, item, options)

        def failed(error):
            self.egt_portal_service_loading.discard(url)
            if generation != self._egt_portal_menu_generation:
                return
            menu.clear()
            action = menu.addAction(
                self.t("Teenuse kihtide laadimine ebaõnnestus") + f": {error}"
            )
            action.setEnabled(False)

        self.network.query_arcgis_feature_layers(
            url, self.egt_portal_authcfg, loaded, failed,
        )

    def _fill_egt_portal_service_menu(self, menu, item, options):
        menu.clear()
        if not options:
            action = menu.addAction(self.t("Kihte ei leitud"))
            action.setEnabled(False)
            return
        service_title = item["title"]
        for layer_id, layer_title in options:
            name = service_title
            if layer_title.casefold() != service_title.casefold():
                name = f"{service_title} — {layer_title}"
            definition = LayerDefinition(
                code="EGT",
                name=name,
                name_en=name,
                protocol="ARCGIS_FEATURESERVER",
                url=item["url"],
                layer_name=layer_id,
                color="#256b54",
                placement="dropdown",
                use_portal_auth=True,
                role=(
                    "geophysics_fieldwork"
                    if self._is_geophysics_fieldwork_source(
                        item["url"], layer_id
                    ) else ""
                ),
            )
            action = menu.addAction(layer_title)
            action.setCheckable(True)
            action.setToolTip(f"{item['url']}/{layer_id}")
            action.toggled.connect(
                lambda checked, layer=definition:
                self.set_layer_active(layer, checked)
            )
            source_id = self._source_id(definition)
            self.egt_portal_layer_actions[source_id] = action
        self.sync_dropdown_checks()

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
        if self.egt_portal_menu_action:
            self.iface.removePluginMenu(
                self.MENU, self.egt_portal_menu_action
            )
        if self.toolbar:
            self.toolbar.clear()
        if self.lk_button:
            self.lk_button.deleteLater()
        if self.extra_menu:
            self.extra_menu.deleteLater()
        if self.egt_portal_button:
            self.egt_portal_button.deleteLater()
        if self.egt_portal_menu:
            self.egt_portal_menu.deleteLater()
        self.actions.clear()
        self.layer_actions.clear()
        self.dropdown_actions.clear()
        self.egt_portal_layer_actions.clear()
        self.utility_separator = None
        self.extra_menu = None
        self.extra_menu_action = None
        self.lk_button = None
        self.egt_portal_menu = None
        self.egt_portal_menu_action = None
        self.egt_portal_button = None
        self.faktika_action = None
        self._egt_portal_menu_generation += 1

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

    def portal_auth_configs(self):
        """Return safe display metadata for QGIS-managed Portal auth configs."""
        try:
            configs = QgsApplication.authManager().availableAuthMethodConfigs()
        except (AttributeError, RuntimeError):
            return []
        result = []
        for authcfg, config in configs.items():
            method = str(config.method() or "")
            if method.casefold() not in {"oauth2", "esritoken"}:
                continue
            result.append((
                str(authcfg), str(config.name() or authcfg), method,
            ))
        return sorted(result, key=lambda item: item[1].casefold())

    def preferred_egt_portal_authcfg(self):
        """Return the saved or most likely existing EGT Portal auth config."""
        configs = self.portal_auth_configs()
        identifiers = {item[0] for item in configs}
        if self.egt_portal_authcfg in identifiers:
            return self.egt_portal_authcfg
        ranked = sorted(
            configs,
            key=lambda item: (
                0 if item[0].casefold() == "egtport" else
                1 if "egt" in item[1].casefold()
                and "portal" in item[1].casefold() else
                2,
                item[1].casefold(),
            ),
        )
        if ranked and (
            ranked[0][0].casefold() == "egtport"
            or (
                "egt" in ranked[0][1].casefold()
                and "portal" in ranked[0][1].casefold()
            )
        ):
            return ranked[0][0]
        return ""

    def create_egt_portal_authentication(self, client_id, client_secret):
        """Create the fixed EGT OAuth2 setup in QGIS' encrypted auth store."""
        try:
            oauth_payload = egt_oauth_config_json(client_id, client_secret)
        except ValueError as error:
            self.warning(self.t(str(error)))
            return ""

        manager = QgsApplication.authManager()
        if manager.isDisabled():
            self.error(self.t(
                "QGIS-i autentimishoidla ei ole selles profiilis kasutatav."
            ))
            return ""
        if not manager.masterPasswordIsSet() and not manager.setMasterPassword():
            self.warning(self.t(
                "QGIS-i autentimishoidla tuleb esmalt avada."
            ))
            self.open_authentication_settings()
            return ""

        config = QgsAuthMethodConfig("OAuth2", 1)
        config.setName("EGT Portal (Qeoloog)")
        config.setUri(EGT_PORTAL_RESOURCE)
        config.setConfig("oauth2config", oauth_payload)
        config.setConfig("qeoloog_egt_portal", "1")
        try:
            stored_result = manager.storeAuthenticationConfig(config)
        except (RuntimeError, TypeError) as error:
            self.error(
                self.t("EGT Portali autentimise salvestamine ebaõnnestus")
                + f": {error}"
            )
            return ""
        if isinstance(stored_result, tuple):
            stored, stored_config = stored_result
        else:
            stored, stored_config = bool(stored_result), config
        authcfg = stored_config.id() if stored_config is not None else config.id()
        if not stored or not authcfg:
            self.error(self.t(
                "EGT Portali autentimise salvestamine ebaõnnestus."
            ))
            return ""
        self.set_egt_portal_authcfg(authcfg)
        self.success(self.t(
            "EGT Portali turvaline ühendus loodi QGIS-i autentimishoidlas."
        ))
        return authcfg

    def set_egt_portal_authcfg(self, authcfg):
        value = str(authcfg or "").strip()
        changed = value != self.egt_portal_authcfg
        self.egt_portal_authcfg = value
        PluginSettings.save_egt_portal_authcfg(self.egt_portal_authcfg)
        if changed:
            self.egt_portal_catalog_account = ""
            self.egt_portal_catalog = []
            self.egt_portal_service_layers.clear()
            if self.egt_portal_menu:
                self._render_egt_portal_menu()
            self._refresh_portal_edit_ui()
            if self.dock:
                self.dock.details.set_faktika_access(False)

    def set_egt_test_server_enabled(self, enabled):
        """Expose the fixed Faktika test workspace only after explicit opt-in."""
        enabled = bool(enabled)
        if enabled == self.egt_test_server_enabled:
            return
        if not enabled and self._faktika_is_active("faktika_test"):
            self.set_faktika_workspace_active("faktika_test", False)
        self.egt_test_server_enabled = enabled
        PluginSettings.save_egt_test_server_enabled(enabled)
        if self.egt_portal_menu:
            self._render_egt_portal_menu()

    def open_authentication_settings(self):
        # QGIS page object names are not a stable API, so open the official
        # options dialog without depending on a version-specific page id.
        self.iface.showOptionsDialog(self.iface.mainWindow())

    def test_egt_portal_login(self):
        if self.egt_portal_login_loading:
            return
        if not self.egt_portal_authcfg:
            candidate = self.preferred_egt_portal_authcfg()
            if candidate:
                self.set_egt_portal_authcfg(candidate)
            else:
                self.warning(self.t(
                    "Seadista esmalt EGT Portali turvaline ühendus."
                ))
                return
        self.egt_portal_login_loading = True
        if self.dock:
            self.dock.layers.set_portal_status(
                self.t("EGT Portalisse logitakse sisse…"), success=False,
            )

        def loaded(payload):
            self.egt_portal_login_loading = False
            username = str(payload.get("username") or "")
            full_name = str(payload.get("fullName") or "").strip()
            account = f"{full_name} ({username})" if full_name else username
            text = self.t("EGT Portali kasutaja") + f": {account}"
            if self.dock:
                self.dock.layers.set_portal_status(text, success=True)
                self.dock.details.set_faktika_access(True)
            self.success(text)
            self.refresh_egt_portal_catalog(account)

        def failed(error):
            self.egt_portal_login_loading = False
            text = self.t("EGT Portali sisselogimine ebaõnnestus") + f": {error}"
            if self.dock:
                self.dock.layers.set_portal_status(text, success=False)
                self.dock.details.set_faktika_access(False)
            self.error(text)

        self.network.query_egt_portal_user(
            self.egt_portal_authcfg, loaded, failed,
        )

    def refresh_egt_portal_catalog(self, account=""):
        """Populate the EGT toolbar menu with the signed-in catalog."""
        if not self.egt_portal_authcfg:
            return
        self._egt_portal_catalog_request += 1
        request = self._egt_portal_catalog_request
        self.egt_portal_catalog_loading = True
        self.egt_portal_service_layers.clear()
        self.egt_portal_service_loading.clear()
        if account:
            self.egt_portal_catalog_account = account
            self._refresh_portal_edit_ui()
            if self.dock:
                self.dock.details.set_faktika_access(True)
        self._render_egt_portal_menu()

        def loaded(items):
            if request != self._egt_portal_catalog_request:
                return
            self.egt_portal_catalog_loading = False
            self.egt_portal_catalog = items
            self._render_egt_portal_menu()
            if self._faktika_is_active():
                self._hide_public_egt_layers_for_faktika()
            self._refresh_portal_edit_ui()
            self.success(
                self.t("EGT Portali kataloog") + f": {len(items)} "
                + self.t("teenust")
            )

        def failed(error):
            if request != self._egt_portal_catalog_request:
                return
            self.egt_portal_catalog_loading = False
            self._render_egt_portal_menu()
            self.error(
                self.t("Portali kataloogi laadimine ebaõnnestus")
                + f": {error}"
            )

        self.network.query_egt_portal_feature_services(
            self.egt_portal_authcfg, loaded, failed,
        )

    def _faktika_is_active(self, workspace_key=None):
        return any(
            str(layer.customProperty("qeoloog/faktika_layer_id", "")) == "1"
            and (
                workspace_key is None
                or str(layer.customProperty(
                    "qeoloog/faktika_workspace", "faktika"
                )) == str(workspace_key)
            )
            for layer in QgsProject.instance().mapLayers().values()
        )

    def _portal_bundle_is_active(self, bundle_key):
        return any(
            str(layer.customProperty("qeoloog/portal_bundle", ""))
            == str(bundle_key)
            for layer in QgsProject.instance().mapLayers().values()
        )

    def _hide_public_egt_layers_for_faktika(self):
        root = QgsProject.instance().layerTreeRoot()
        for role in ("boreholes", "observations"):
            for layer in self._role_layers(role):
                node = root.findLayer(layer.id())
                if node is None:
                    continue
                if layer.id() not in self._faktika_visibility_nodes:
                    handler = lambda *_args, layer_id=layer.id(): (
                        self._enforce_faktika_public_visibility(layer_id)
                    )
                    try:
                        node.visibilityChanged.connect(handler)
                        self._faktika_visibility_nodes[layer.id()] = (
                            node, handler,
                        )
                    except (AttributeError, RuntimeError):
                        pass
                self._faktika_public_visibility.setdefault(
                    layer.id(), node.isVisible()
                )
                node.setItemVisibilityChecked(False)

    def _enforce_faktika_public_visibility(self, layer_id):
        if not self._faktika_is_active():
            return
        node = QgsProject.instance().layerTreeRoot().findLayer(layer_id)
        if node is not None and node.isVisible():
            node.setItemVisibilityChecked(False)

    def _set_faktika_action_checked(self, checked, workspace_key="faktika"):
        action = self.faktika_workspace_actions.get(workspace_key)
        if action is None and workspace_key == "faktika":
            action = self.faktika_action
        if action is None:
            return
        action.blockSignals(True)
        action.setChecked(bool(checked))
        action.blockSignals(False)

    def set_faktika_active(self, checked):
        return self.set_faktika_workspace_active("faktika", checked)

    def set_faktika_workspace_active(self, workspace_key, checked):
        """Load or remove one editable Faktika-compatible service family."""
        workspace = FAKTIKA_WORKSPACES.get(workspace_key)
        if workspace is None:
            return False
        if checked:
            if not self.egt_portal_authcfg or not self.egt_portal_catalog_account:
                self._set_faktika_action_checked(False, workspace_key)
                self.warning(self.t("Logi esmalt EGT Portalisse."))
                return False
            if (
                workspace.get("discover_layers")
                and not workspace.get("_layers_resolved")
            ):
                return self._discover_faktika_workspace_layers(workspace_key)
            if self._faktika_is_active(workspace_key):
                self._hide_public_egt_layers_for_faktika()
                self._set_faktika_action_checked(True, workspace_key)
                return True
            if not self._load_faktika_layers(workspace_key):
                self._set_faktika_action_checked(False, workspace_key)
                return False
            self._set_faktika_action_checked(True, workspace_key)
            self.success(self.t(workspace["title"]) + ": " + self.t(
                "töökiht ja seotud tabelid lisati."
            ))
            self._ensure_faktika_metadata(
                lambda _metadata: None, self.warning, workspace_key
            )
            return True

        project = QgsProject.instance()
        ids = [
            layer.id() for layer in project.mapLayers().values()
            if layer.customProperty("qeoloog/faktika_layer_id", "") not in (None, "")
            and str(layer.customProperty(
                "qeoloog/faktika_workspace", "faktika"
            )) == workspace_key
        ]
        if ids:
            project.removeMapLayers(ids)
        root = project.layerTreeRoot()
        group = root.findGroup(workspace["group"])
        if group is not None:
            root.removeChildNode(group)
        if not self._faktika_is_active():
            for layer_id, visible in tuple(self._faktika_public_visibility.items()):
                node = root.findLayer(layer_id)
                if node is not None:
                    node.setItemVisibilityChecked(bool(visible))
            for node, handler in tuple(self._faktika_visibility_nodes.values()):
                try:
                    node.visibilityChanged.disconnect(handler)
                except (AttributeError, RuntimeError, TypeError):
                    pass
            self._faktika_visibility_nodes.clear()
            self._faktika_public_visibility.clear()
        if self._current_faktika_workspace == workspace_key:
            self._current_faktika_context = None
            if self.dock:
                self.dock.details.set_faktika_context(None)
        self._set_faktika_action_checked(False, workspace_key)
        self.success(self.t(workspace["title"]) + ": " + self.t(
            "töökiht eemaldati."
        ))
        return True

    def _discover_faktika_workspace_layers(self, workspace_key):
        """Resolve deployment-specific ArcGIS layer IDs before loading."""
        if workspace_key in self._faktika_workspace_discovery_loading:
            return True
        workspace = FAKTIKA_WORKSPACES[workspace_key]
        self._faktika_workspace_discovery_loading.add(workspace_key)

        def loaded(options):
            self._faktika_workspace_discovery_loading.discard(workspace_key)
            action = self.faktika_workspace_actions.get(workspace_key)
            if action is not None and not action.isChecked():
                return
            try:
                workspace["layers"] = discover_faktika_layer_ids(options)
            except ValueError as error:
                self._set_faktika_action_checked(False, workspace_key)
                self.error(
                    self.t("Faktika teenuse kihtide tuvastamine ebaõnnestus")
                    + f": {error}"
                )
                return
            workspace["_layers_resolved"] = True
            self.set_faktika_workspace_active(workspace_key, True)

        def failed(error):
            self._faktika_workspace_discovery_loading.discard(workspace_key)
            self._set_faktika_action_checked(False, workspace_key)
            self.error(
                self.t("Faktika teenuse kihtide tuvastamine ebaõnnestus")
                + f": {error}"
            )

        self.network.query_arcgis_feature_layers(
            workspace["url"], self.egt_portal_authcfg, loaded, failed,
        )
        return True

    def _load_faktika_layers(self, workspace_key="faktika"):
        workspace = FAKTIKA_WORKSPACES[workspace_key]
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group = root.findGroup(workspace["group"]) or root.insertGroup(
            0, workspace["group"]
        )
        group.setCustomProperty("qeoloog/faktika_group", True)
        group.setCustomProperty("qeoloog/faktika_workspace", workspace_key)
        related_group = group.findGroup(self.t("Seotud tabelid")) or group.addGroup(
            self.t("Seotud tabelid")
        )
        related_group.setExpanded(False)
        loaded = {}
        for logical_name, actual_layer_id in workspace["layers"].items():
            canonical_layer_id = FAKTIKA_LAYER_IDS[logical_name]
            uri = QgsDataSourceUri()
            uri.setParam("url", f"{workspace['url']}/{actual_layer_id}")
            uri.setAuthConfigId(self.egt_portal_authcfg)
            layer = QgsVectorLayer(
                uri.uri(False), FAKTIKA_LAYER_NAMES[canonical_layer_id],
                "arcgisfeatureserver",
            )
            if not layer.isValid():
                for created in loaded.values():
                    project.removeMapLayer(created.id())
                if group.parent() is root:
                    root.removeChildNode(group)
                self._report_faktika_layer_load_failure(
                    workspace_key, logical_name, actual_layer_id, layer,
                )
                return False
            layer.setCustomProperty(
                "qeoloog/faktika_layer_id", str(canonical_layer_id)
            )
            layer.setCustomProperty(
                "qeoloog/faktika_actual_layer_id", str(actual_layer_id)
            )
            layer.setCustomProperty(
                "qeoloog/faktika_workspace", workspace_key
            )
            layer.setCustomProperty(
                self.SOURCE_PROPERTY,
                f"FAKTIKA|{workspace['url']}|{actual_layer_id}",
            )
            layer.setCustomProperty(
                self.ROLE_PROPERTY,
                "faktika" if logical_name == "objects" else "",
            )
            try:
                layer.setReadOnly(True)
            except AttributeError:
                pass
            layer.setCustomProperty("qeoloog/portal_read_only", True)
            project.addMapLayer(layer, False)
            (group if logical_name == "objects" else related_group).addLayer(layer)
            loaded[canonical_layer_id] = layer
        self._apply_faktika_renderer(loaded[1])
        self._apply_egt_labeling(loaded[1], "faktika")
        self._install_faktika_relations(loaded, workspace_key)
        group.setExpanded(True)
        point_node = root.findLayer(loaded[1].id())
        if point_node:
            point_node.setItemVisibilityChecked(True)
        self._hide_public_egt_layers_for_faktika()
        self.iface.setActiveLayer(loaded[1])
        self._schedule_egt_label_refresh()
        return True

    @staticmethod
    def _layer_error_text(layer):
        """Return the useful part of a provider error across QGIS versions."""
        try:
            error = layer.error()
        except (AttributeError, RuntimeError):
            return ""
        messages = []
        try:
            for item in error.messageList():
                value = item.message() if hasattr(item, "message") else str(item)
                value = str(value or "").strip()
                if value and value not in messages:
                    messages.append(value)
        except (AttributeError, RuntimeError, TypeError):
            pass
        for method_name in ("summary", "message"):
            try:
                value = str(getattr(error, method_name)() or "").strip()
            except (AttributeError, RuntimeError, TypeError):
                continue
            if value and value not in messages:
                messages.append(value)
        return " | ".join(messages)

    def _report_faktika_layer_load_failure(
        self, workspace_key, logical_name, actual_layer_id, layer,
    ):
        """Expose both the QGIS provider error and ArcGIS' JSON error body."""
        workspace = FAKTIKA_WORKSPACES[workspace_key]
        canonical_layer_id = FAKTIKA_LAYER_IDS[logical_name]
        layer_name = FAKTIKA_LAYER_NAMES[canonical_layer_id]
        provider_error = self._layer_error_text(layer)
        message = self.t("Faktika kihi laadimine ebaõnnestus") + f": {layer_name}"
        if provider_error:
            message += f" — {provider_error}"
        self.error(message)

        # ArcGIS commonly returns authentication failures as a JSON error with
        # HTTP 200. QGIS' Network Logger therefore cannot show the cause and
        # the provider may only report an invalid layer. Repeat the read-only
        # metadata request through the same authentication configuration and
        # surface a sanitized diagnosis; no token or payload is logged.
        url = QUrl(f"{workspace['url']}/{actual_layer_id}")
        query = QUrlQuery()
        query.addQueryItem("f", "json")
        url.setQuery(query)

        def loaded(payload):
            if not isinstance(payload, dict):
                self.error(self.t(
                    "Testserver tagastas tundmatu REST-vastuse."
                ))
                return
            arc_error = payload.get("error")
            if isinstance(arc_error, dict):
                code = str(arc_error.get("code") or "?")
                detail = str(arc_error.get("message") or "").strip()
                extra = " ".join(
                    str(value).strip()
                    for value in arc_error.get("details") or []
                    if str(value).strip()
                )
                text = self.t("ArcGIS REST-viga")
                text += f" ({code})"
                if detail:
                    text += f": {detail}"
                if extra and extra not in detail:
                    text += f" — {extra}"
                self.error(text)
                return
            layer_type = str(payload.get("type") or "?")
            geometry = str(payload.get("geometryType") or "–")
            field_count = len(payload.get("fields") or [])
            text = self.t(
                "ArcGIS REST-vastus on korras, kuid QGIS ei avanud kihti"
            )
            text += (
                f": {layer_name}; type={layer_type}, "
                f"geometry={geometry}, fields={field_count}"
            )
            if provider_error:
                text += f" — {provider_error}"
            self.error(text)

        def failed(error):
            self.error(
                self.t("Faktika REST-kontroll ebaõnnestus") + f": {error}"
            )

        self.network.get_json(
            url, loaded, failed, authcfg=self.egt_portal_authcfg,
            data_provider="arcgisfeatureserver",
        )

    def _apply_faktika_renderer(self, layer):
        root_rule = QgsRuleBasedRenderer.Rule(None)
        shapes = {1: "circle", 2: "triangle", 3: "diamond"}
        for object_code, object_label in OBJECT_TYPES.items():
            object_rule = QgsRuleBasedRenderer.Rule(
                None, 0, 0,
                f'"objekti_tyyp" = {object_code}',
                self.t(object_label),
            )
            for unit_code, unit_label in UNIT_TYPES.items():
                symbol = QgsMarkerSymbol.createSimple({
                    "name": shapes.get(object_code, "circle"),
                    "color": UNIT_COLORS.get(unit_code, "#8f8f8f"),
                    "outline_color": "#263238",
                    "outline_width": "0.35",
                    "size": "3.0" if object_code == 1 else "2.7",
                })
                object_rule.appendChild(QgsRuleBasedRenderer.Rule(
                    symbol, 0, 0,
                    f'"yksus_kood" = {unit_code}',
                    self.t(unit_label),
                ))
            root_rule.appendChild(object_rule)
        layer.setRenderer(QgsRuleBasedRenderer(root_rule))
        layer.setDisplayExpression(
            'coalesce("nimi", "alias", to_string("gea_id"))'
        )
        layer.triggerRepaint()

    def _install_faktika_relations(self, layers, workspace_key="faktika"):
        manager = QgsProject.instance().relationManager()
        definitions = (
            ("faktika_manus", "Manus", 4, "puurauk_vaatluspunkt_id", 1, "globalid"),
            ("faktika_juurdepaas", "Juurdepääsu alus", 5, "puurauk_vaatluspunkt_id", 1, "globalid"),
            ("faktika_geoloogia", "Geoloogiline üksus", 6, "puurauk_vaatluspunkt_id", 1, "globalid"),
            ("faktika_marksonad", "Manuse märksõnad", 3, "manus_id", 4, "globalid"),
            ("faktika_manuse_isik", "Manuse isik", 4, "isik_id", 2, "globalid"),
            ("faktika_geoloogia_isik", "Geoloogilise üksuse isik", 6, "isik_id", 2, "globalid"),
        )
        for relation_id, name, child, child_field, parent, parent_field in definitions:
            relation_id = f"{workspace_key}_{relation_id}"
            try:
                manager.removeRelation(relation_id)
            except (AttributeError, TypeError):
                pass
            relation = QgsRelation()
            relation.setId(relation_id)
            relation.setName(name)
            relation.setReferencingLayer(layers[child].id())
            relation.setReferencedLayer(layers[parent].id())
            relation.addFieldPair(child_field, parent_field)
            if relation.isValid():
                manager.addRelation(relation)

    def set_portal_bundle_active(self, bundle_key, checked):
        """Load a related Portal layer/table family as one project group."""
        bundle = self.PORTAL_LAYER_BUNDLES.get(bundle_key)
        action = self.portal_bundle_actions.get(bundle_key)
        if bundle is None:
            return False

        def set_checked(value):
            if action is not None:
                action.blockSignals(True)
                action.setChecked(bool(value))
                action.blockSignals(False)

        if not checked:
            project = QgsProject.instance()
            ids = [
                layer.id() for layer in project.mapLayers().values()
                if str(layer.customProperty("qeoloog/portal_bundle", ""))
                == bundle_key
            ]
            if ids:
                project.removeMapLayers(ids)
            group = project.layerTreeRoot().findGroup(bundle["group"])
            if group is not None:
                project.layerTreeRoot().removeChildNode(group)
            set_checked(False)
            return True
        if not self.egt_portal_authcfg or not self.egt_portal_catalog_account:
            set_checked(False)
            self.warning(self.t("Logi esmalt EGT Portalisse."))
            return False
        if self._portal_bundle_is_active(bundle_key):
            if bundle_key == "field_mapping":
                for layer in QgsProject.instance().mapLayers().values():
                    if (
                        str(layer.customProperty("qeoloog/portal_bundle", ""))
                        == bundle_key
                        and str(layer.customProperty(
                            "qeoloog/portal_bundle_layer_id", ""
                        )) == "0"
                    ):
                        layer.setCustomProperty(
                            self.ROLE_PROPERTY, "field_mapping"
                        )
                        self._apply_egt_labeling(layer, "field_mapping")
            self._ensure_portal_bundle_metadata(
                bundle_key, lambda _metadata: None, lambda _error: None,
            )
            self._schedule_egt_label_refresh()
            set_checked(True)
            return True
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group = root.findGroup(bundle["group"]) or root.insertGroup(
            0, bundle["group"]
        )
        group.setCustomProperty("qeoloog/portal_bundle", bundle_key)
        loaded = {}
        for layer_id, title in bundle["layers"]:
            uri = QgsDataSourceUri()
            uri.setParam("url", f"{bundle['url']}/{layer_id}")
            uri.setAuthConfigId(self.egt_portal_authcfg)
            layer = QgsVectorLayer(
                uri.uri(False), self.t(title), "arcgisfeatureserver"
            )
            if not layer.isValid():
                for created in loaded.values():
                    project.removeMapLayer(created.id())
                set_checked(False)
                self.error(self.t("Portali kihikogumi laadimine ebaõnnestus") + f": {title}")
                return False
            layer.setCustomProperty("qeoloog/portal_bundle", bundle_key)
            layer.setCustomProperty("qeoloog/portal_bundle_layer_id", str(layer_id))
            layer.setCustomProperty(
                self.SOURCE_PROPERTY,
                f"PORTAL_BUNDLE|{bundle['url']}|{layer_id}",
            )
            if bundle_key == "field_mapping" and int(layer_id) == 0:
                # Include the point layer in Qeoloog's map-click flow.  Its
                # related descriptions remain a non-spatial table.
                layer.setCustomProperty(self.ROLE_PROPERTY, "field_mapping")
            self._enforce_portal_layer_read_only(layer)
            project.addMapLayer(layer, False)
            group.addLayer(layer)
            loaded[layer_id] = layer
        if bundle_key == "field_mapping" and 0 in loaded and 1 in loaded:
            self._apply_egt_labeling(loaded[0], "field_mapping")
            manager = project.relationManager()
            relation_id = "qeoloog_field_mapping_units"
            try:
                manager.removeRelation(relation_id)
            except (AttributeError, TypeError):
                pass
            relation = QgsRelation()
            relation.setId(relation_id)
            relation.setName(self.t("Välitöö kirjeldus"))
            relation.setReferencingLayer(loaded[1].id())
            relation.setReferencedLayer(loaded[0].id())
            relation.addFieldPair("vaatluspunkt_id", "GlobalID")
            if relation.isValid():
                manager.addRelation(relation)
        group.setExpanded(True)
        node = root.findLayer(loaded[0].id()) if 0 in loaded else None
        if node is not None:
            node.setItemVisibilityChecked(True)
        if 0 in loaded:
            self.iface.setActiveLayer(loaded[0])
        self._ensure_portal_bundle_metadata(
            bundle_key, lambda _metadata: None, lambda _error: None,
        )
        set_checked(True)
        self._schedule_egt_label_refresh()
        self.success(self.t(bundle["title"]) + ": " + self.t(
            "kihid ja tabelid lisati tervikuna."
        ))
        return True

    def _ensure_portal_bundle_metadata(self, bundle_key, success, failure):
        """Load and cache metadata for a promoted Portal layer bundle."""
        bundle = self.PORTAL_LAYER_BUNDLES.get(bundle_key)
        if bundle is None:
            failure(self.t("Tundmatu Portali kihikogum."))
            return
        expected = {int(layer_id) for layer_id, _title in bundle["layers"]}
        metadata = self._portal_bundle_metadata.setdefault(bundle_key, {})
        if expected.issubset(metadata):
            success(metadata)
            return
        waiters = self._portal_bundle_metadata_waiters.setdefault(bundle_key, [])
        waiters.append((success, failure))
        if bundle_key in self._portal_bundle_metadata_loading:
            return
        self._portal_bundle_metadata_loading.add(bundle_key)
        pending = set(expected)

        def loaded(layer_id):
            def handler(payload):
                metadata[layer_id] = payload
                pending.discard(layer_id)
                if pending:
                    return
                self._portal_bundle_metadata_loading.discard(bundle_key)
                callbacks = self._portal_bundle_metadata_waiters.pop(
                    bundle_key, []
                )
                for callback, _ignored in callbacks:
                    callback(metadata)
            return handler

        def failed(layer_id):
            def handler(error):
                if bundle_key not in self._portal_bundle_metadata_loading:
                    return
                self._portal_bundle_metadata_loading.discard(bundle_key)
                callbacks = self._portal_bundle_metadata_waiters.pop(
                    bundle_key, []
                )
                title = dict(bundle["layers"]).get(layer_id, layer_id)
                message = f"{title}: {error}"
                for _ignored, callback in callbacks:
                    callback(message)
            return handler

        for layer_id in pending:
            self.network.query_arcgis_layer_metadata(
                bundle["url"], str(layer_id), self.egt_portal_authcfg,
                loaded(layer_id), failed(layer_id),
            )

    def portal_bundle_metadata(self, bundle_key="field_mapping"):
        return self._portal_bundle_metadata.get(bundle_key, {})

    def _ensure_faktika_metadata(
        self, success, failure, workspace_key="faktika",
    ):
        workspace = FAKTIKA_WORKSPACES[workspace_key]
        metadata = (
            self._faktika_metadata if workspace_key == "faktika"
            else self._faktika_workspace_metadata.setdefault(workspace_key, {})
        )
        if len(metadata) == 6:
            success(metadata)
            return
        waiters = self._faktika_workspace_metadata_waiters.setdefault(
            workspace_key, []
        )
        waiters.append((success, failure))
        if workspace_key in self._faktika_workspace_metadata_loading:
            return
        self._faktika_workspace_metadata_loading.add(workspace_key)
        pending = set(range(1, 7))

        def loaded(layer_id):
            def handler(payload):
                metadata[layer_id] = payload
                pending.discard(layer_id)
                if not pending:
                    self._faktika_workspace_metadata_loading.discard(
                        workspace_key
                    )
                    callbacks = self._faktika_workspace_metadata_waiters.pop(
                        workspace_key, []
                    )
                    for callback, _ignored in callbacks:
                        callback(metadata)
            return handler

        def failed(layer_id):
            def handler(error):
                if workspace_key not in self._faktika_workspace_metadata_loading:
                    return
                self._faktika_workspace_metadata_loading.discard(workspace_key)
                callbacks = self._faktika_workspace_metadata_waiters.pop(
                    workspace_key, []
                )
                message = f"{FAKTIKA_LAYER_NAMES[layer_id]}: {error}"
                for _ignored, callback in callbacks:
                    callback(message)
            return handler

        for logical_name, actual_layer_id in workspace["layers"].items():
            canonical_layer_id = FAKTIKA_LAYER_IDS[logical_name]
            self.network.query_arcgis_layer_metadata(
                workspace["url"], str(actual_layer_id),
                self.egt_portal_authcfg,
                loaded(canonical_layer_id), failed(canonical_layer_id),
            )

    def faktika_metadata(self, workspace_key=None):
        key = workspace_key or self._current_faktika_workspace or "faktika"
        return (
            self._faktika_metadata if key == "faktika"
            else self._faktika_workspace_metadata.get(key, {})
        )

    @staticmethod
    def _faktika_actual_layer_id(workspace_key, canonical_layer_id):
        logical_name = next(
            name for name, value in FAKTIKA_LAYER_IDS.items()
            if int(value) == int(canonical_layer_id)
        )
        return FAKTIKA_WORKSPACES[workspace_key]["layers"][logical_name]

    @staticmethod
    def _faktika_records(payload):
        records = []
        for feature in (payload or {}).get("features") or []:
            if not isinstance(feature, dict):
                continue
            row = dict(feature.get("attributes") or {})
            row["_existing"] = True
            geometry = feature.get("geometry")
            if isinstance(geometry, dict):
                row["_geometry"] = dict(geometry)
            records.append(row)
        return records

    def _query_faktika_rows(
        self, layer_id, where, success, failure, *, geometry=False,
        fields="*", order_by="", workspace_key="faktika",
    ):
        workspace = FAKTIKA_WORKSPACES[workspace_key]
        actual_layer_id = self._faktika_actual_layer_id(
            workspace_key, layer_id
        )
        self.network.query_arcgis_features(
            workspace["url"], actual_layer_id, where,
            lambda payload: success(self._faktika_records(payload)),
            failure,
            authcfg=self.egt_portal_authcfg,
            out_fields=fields,
            return_geometry=geometry,
            return_z=geometry,
            order_by=order_by,
        )

    def _ensure_faktika_people(
        self, success, failure, workspace_key="faktika",
    ):
        cached = (
            self._faktika_people if workspace_key == "faktika"
            else self._faktika_workspace_people.get(workspace_key)
        )
        if cached is not None:
            success(cached)
            return
        waiters = self._faktika_workspace_people_waiters.setdefault(
            workspace_key, []
        )
        waiters.append((success, failure))
        if workspace_key in self._faktika_workspace_people_loading:
            return
        self._faktika_workspace_people_loading.add(workspace_key)

        def loaded(rows):
            username = str(self.egt_portal_catalog_account or "").rsplit(
                "(", 1
            )[-1].rstrip(")").strip()
            if not username or any(
                str(row.get("portali_kasutaja") or "").casefold()
                == username.casefold() for row in rows
            ):
                finish(rows)
                return
            # The directory is larger than the service page limit on some
            # accounts.  Fetch the signed-in author explicitly so new units
            # can still default to the current person.
            self._query_faktika_rows(
                2,
                f"portali_kasutaja = '{escape_where(username)}'",
                lambda extra: finish(rows + extra),
                lambda _error: finish(rows),
                fields="*", workspace_key=workspace_key,
            )

        def finish(rows):
            self._faktika_workspace_people_loading.discard(workspace_key)
            unique = {}
            for row in rows or ():
                key = normalize_guid(row.get("globalid")) or str(row)
                unique[key] = row
            result = sorted(
                unique.values(),
                key=lambda row: str(row.get("isik_nimi") or "").casefold(),
            )
            if workspace_key == "faktika":
                self._faktika_people = result
            else:
                self._faktika_workspace_people[workspace_key] = result
            callbacks = self._faktika_workspace_people_waiters.pop(
                workspace_key, []
            )
            for callback, _ignored in callbacks:
                callback(result)

        def failed(error):
            self._faktika_workspace_people_loading.discard(workspace_key)
            callbacks = self._faktika_workspace_people_waiters.pop(
                workspace_key, []
            )
            for _ignored, callback in callbacks:
                callback(error)

        self._query_faktika_rows(
            2, "1=1", loaded, failed,
            fields="*", order_by="isik_nimi", workspace_key=workspace_key,
        )

    def _faktika_current_person_id(self, people):
        account = str(self.egt_portal_catalog_account or "")
        username = account.rsplit("(", 1)[-1].rstrip(")").strip()
        for row in people or ():
            if str(row.get("portali_kasutaja") or "").casefold() == username.casefold():
                return normalize_guid(row.get("globalid"))
        return ""

    def _load_faktika_context(
        self, parent, geometry, success, failure, workspace_key="faktika",
        match_attributes=None,
    ):
        parent = dict(parent or {})
        guid = normalize_guid(parent.get("globalid"))
        if not guid:
            failure(self.t("Faktika kirjel puudub globalid."))
            return

        def metadata_loaded(metadata):
            def people_loaded(people):
                context = {
                    "parent": parent,
                    "geometry": dict(geometry or parent.pop("_geometry", {}) or {}),
                    "people": people,
                    "current_person_id": self._faktika_current_person_id(people),
                    "is_new": False,
                    "edit_moment": parent.get("muutmise_aeg"),
                    "workspace_key": workspace_key,
                    "match_attributes": dict(match_attributes or parent),
                }
                pending = {"geological_units", "attachments", "access_basis"}
                failed_once = {"value": False}

                def abort(error):
                    if not failed_once["value"]:
                        failed_once["value"] = True
                        failure(error)

                def finish(key, rows):
                    if failed_once["value"]:
                        return
                    context[key] = rows
                    pending.discard(key)
                    if not pending:
                        success(context)

                where = f"puurauk_vaatluspunkt_id = '{escape_where(guid)}'"
                self._query_faktika_rows(
                    6, where,
                    lambda rows: finish("geological_units", rows), abort,
                    order_by="z_suht_ylemine", workspace_key=workspace_key,
                )
                self._query_faktika_rows(
                    5, where,
                    lambda rows: finish("access_basis", rows), abort,
                    workspace_key=workspace_key,
                )

                def attachments_loaded(rows):
                    context["attachments"] = rows
                    ids = [normalize_guid(row.get("globalid")) for row in rows]
                    ids = [value for value in ids if value]
                    if not ids:
                        context["attachment_keywords"] = []
                        finish("attachments", rows)
                        return
                    quoted = ",".join(
                        f"'{escape_where(value)}'" for value in ids
                    )
                    self._query_faktika_rows(
                        3, f"manus_id IN ({quoted})",
                        lambda keywords: (
                            context.__setitem__("attachment_keywords", keywords),
                            finish("attachments", rows),
                        )[-1],
                        abort, workspace_key=workspace_key,
                    )

                self._query_faktika_rows(
                    4, where, attachments_loaded, abort,
                    workspace_key=workspace_key,
                )

            self._ensure_faktika_people(
                people_loaded, failure, workspace_key
            )

        self._ensure_faktika_metadata(
            metadata_loaded, failure, workspace_key
        )

    def _set_current_faktika_context(self, context, status="Faktika"):
        self._current_faktika_context = context
        self._current_faktika_workspace = (
            (context or {}).get("workspace_key") or "faktika"
        )
        if self.dock:
            self.dock.details.set_faktika_context(context, status)
            units = context.get("geological_units") if context else None
            if units is not None:
                self.dock.details.set_profile(
                    self._faktika_display_units(
                        units, self._current_faktika_workspace
                    )
                )

    def _faktika_display_units(self, rows, workspace_key=None):
        """Decode Faktika interval domains without changing editable rows."""
        metadata = self.faktika_metadata(workspace_key).get(6, {})
        return [
            decode_coded_row(metadata, row, preserve=("yksus_kood",))
            for row in rows or ()
        ]

    def _resolve_faktika_context(
        self, token, role, global_id, attributes, parent=None, geometry=None,
        workspace_key="faktika",
    ):
        if not self.egt_portal_catalog_account or not self.egt_portal_authcfg:
            return
        if self.dock:
            self.dock.details.set_faktika_context(None, self.t("Faktika: otsin vastet…"))

        def context_failed(error):
            if token == self._detail_token and self.dock:
                self.dock.details.set_faktika_context(
                    None, self.t("Faktika ei ole redigeerimiseks saadaval")
                )
                self.warning(self.t("Faktika andmete laadimine ebaõnnestus") + f": {error}")

        def parent_loaded(rows, exact=True):
            if token != self._detail_token:
                return
            if not rows:
                if exact:
                    gea_id = attributes.get("gea_id")
                    try:
                        gea_value = int(gea_id)
                    except (TypeError, ValueError):
                        gea_value = None
                    if gea_value is not None:
                        self._query_faktika_rows(
                            1, f"gea_id = {gea_value}",
                            lambda found: parent_loaded(found, False),
                            context_failed, geometry=True,
                            workspace_key=workspace_key,
                        )
                        return
                self._current_faktika_context = None
                self.dock.details.set_faktika_context(
                    None, self.t("Avalik kirje · Faktika vaste puudub")
                )
                return
            record = rows[0]
            found_guid = normalize_guid(record.get("globalid"))
            requested_guid = normalize_guid(global_id)
            if not exact and requested_guid and found_guid != requested_guid:
                self._current_faktika_context = None
                self.dock.details.set_faktika_context(
                    None, self.t("Faktika konflikt · globalid ei kattu")
                )
                return
            record_geometry = record.pop("_geometry", {})
            self._load_faktika_context(
                record, record_geometry,
                lambda context: (
                    self._set_current_faktika_context(
                        context,
                        self.t("Faktika · sisemine ja avalik kirje kattuvad"),
                    ) if token == self._detail_token else None
                ),
                context_failed, workspace_key,
                match_attributes={**record, **dict(attributes or {})},
            )

        if parent is not None:
            direct = dict(parent)
            if geometry is None:
                geometry = direct.pop("_geometry", {})
            self._load_faktika_context(
                direct, geometry,
                lambda context: (
                    self._set_current_faktika_context(
                        context,
                        self.t(FAKTIKA_WORKSPACES[workspace_key]["title"])
                        + " · " + self.t("sisemine kirje")
                    ) if token == self._detail_token else None
                ),
                context_failed, workspace_key,
                match_attributes={**direct, **dict(attributes or {})},
            )
            return
        guid = normalize_guid(global_id)
        if not guid:
            parent_loaded([], True)
            return
        self._query_faktika_rows(
            1, f"globalid = '{escape_where(guid)}'",
            lambda rows: parent_loaded(rows, True), context_failed,
            geometry=True, workspace_key=workspace_key,
        )

    def add_faktika_object(self):
        if not PORTAL_EDITING_ENABLED:
            self.warning(self.t(
                "Portali kirjutamine on Qeoloogis välja lülitatud."
            ))
            return
        if not self.egt_portal_catalog_account:
            self.warning(self.t("Logi esmalt EGT Portalisse."))
            return
        workspace_key = self._faktika_workspace_for_new_object()
        if not workspace_key:
            return
        labels = [self.t(value) for value in OBJECT_TYPES.values()]
        selected, ok = QInputDialog.getItem(
            self.iface.mainWindow(), self.t("Lisa Faktika objekt"),
            self.t("Objekti tüüp"), labels, 0, False,
        )
        if not ok:
            return
        object_type = list(OBJECT_TYPES)[labels.index(selected)]
        if not self._faktika_is_active(workspace_key):
            if not self.set_faktika_workspace_active(workspace_key, True):
                return

        def metadata_loaded(metadata):
            def people_loaded(people):
                self._choose_faktika_new_location(
                    object_type, metadata, people, workspace_key,
                )

            self._ensure_faktika_people(
                people_loaded, self.error, workspace_key
            )

        self._ensure_faktika_metadata(
            metadata_loaded, self.error, workspace_key
        )

    def _faktika_workspace_for_new_object(self):
        """Choose the workspace explicitly enough to avoid test/prod mix-ups."""
        active_layer = self.iface.activeLayer()
        if active_layer is not None:
            active_key = str(active_layer.customProperty(
                "qeoloog/faktika_workspace", ""
            ))
            if active_key in FAKTIKA_WORKSPACES:
                return active_key
        active = [
            key for key in FAKTIKA_WORKSPACES
            if self._faktika_is_active(key)
            and (
                not FAKTIKA_WORKSPACES[key].get("advanced")
                or self.egt_test_server_enabled
            )
        ]
        if len(active) == 1:
            return active[0]
        if len(active) > 1:
            labels = [self.t(FAKTIKA_WORKSPACES[key]["title"]) for key in active]
            selected, accepted = QInputDialog.getItem(
                self.iface.mainWindow(), self.t("Lisa Faktika objekt"),
                self.t("Sihtkeskkond"), labels, 0, False,
            )
            return active[labels.index(selected)] if accepted else ""
        return "faktika"

    def _choose_faktika_new_location(
        self, object_type, metadata, people, workspace_key,
    ):
        """Ask whether a new PointZ object should be placed by map click."""
        answer = QMessageBox.question(
            self.iface.mainWindow(),
            self.t("Lisa Faktika objekt"),
            self.t(
                "Kas valida uue objekti asukoht kaardilt?"
                "\nJah: klõpsa kaardil; Ei: kasuta kaardi keskpunkti."
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return
        if answer == QMessageBox.StandardButton.Yes:
            if self.faktika_point_tool is None:
                self.warning(self.t("Kaardilt asukoha valimine pole saadaval."))
                return
            self._faktika_pending_new = (
                object_type, metadata, people, workspace_key,
            )
            canvas = self.iface.mapCanvas()
            self.faktika_point_previous_tool = canvas.mapTool()
            canvas.setMapTool(self.faktika_point_tool)
            self.message(
                self.t("Klõpsa kaardil uue Faktika objekti asukohas. Esc tühistab.")
            )
            return
        self._open_new_faktika_object(
            object_type, metadata, people, None, workspace_key,
        )

    def _faktika_point_selected(self, point):
        pending = self._faktika_pending_new
        self._faktika_pending_new = None
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self.faktika_point_tool:
            previous = self.faktika_point_previous_tool
            self.faktika_point_previous_tool = None
            if previous is not None and previous is not self.faktika_point_tool:
                canvas.setMapTool(previous)
            else:
                canvas.unsetMapTool(self.faktika_point_tool)
        if pending:
            object_type, metadata, people, workspace_key = pending
            self._open_new_faktika_object(
                object_type, metadata, people, point, workspace_key,
            )

    def _faktika_point_cancelled(self):
        self._faktika_pending_new = None
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self.faktika_point_tool:
            previous = self.faktika_point_previous_tool
            self.faktika_point_previous_tool = None
            if previous is not None and previous is not self.faktika_point_tool:
                canvas.setMapTool(previous)
            else:
                canvas.unsetMapTool(self.faktika_point_tool)

    def start_elevation_candidate_pick(self, dialog):
        """Temporarily hide the editor and pick one candidate XY on map."""
        if (
            not self.egt_portal_catalog_account
            or not self.egt_portal_authcfg
            or self.elevation_candidate_tool is None
        ):
            self.warning(self.t("Logi esmalt EGT Portalisse."))
            return False
        canvas = self.iface.mapCanvas()
        self._elevation_candidate_dialog = dialog
        self.elevation_candidate_previous_tool = canvas.mapTool()
        dialog.hide()
        canvas.setMapTool(self.elevation_candidate_tool)
        self.message(self.t(
            "Klõpsa kaardil kõrguse järgi kontrollitavas kandidaatkohas. "
            "Esc tühistab."
        ))
        return True

    def stop_elevation_candidate_pick(self, dialog=None):
        if dialog is not None and dialog is not self._elevation_candidate_dialog:
            return
        pending = self._elevation_candidate_dialog
        self._elevation_candidate_dialog = None
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self.elevation_candidate_tool:
            previous = self.elevation_candidate_previous_tool
            self.elevation_candidate_previous_tool = None
            if previous is not None and previous is not self.elevation_candidate_tool:
                canvas.setMapTool(previous)
            else:
                canvas.unsetMapTool(self.elevation_candidate_tool)
        if pending is not None and pending.isVisible() is False:
            pending.show()
            pending.raise_()
            pending.activateWindow()

    def _elevation_candidate_selected(self, point):
        dialog = self._elevation_candidate_dialog
        self.stop_elevation_candidate_pick()
        if dialog is None:
            return
        try:
            point = QgsCoordinateTransform(
                self.iface.mapCanvas().mapSettings().destinationCrs(),
                QgsCoordinateReferenceSystem("EPSG:3301"),
                QgsProject.instance(),
            ).transform(point)
        except QgsCsException:
            pass
        dialog.elevation_candidate_selected(point.x(), point.y())

    def _elevation_candidate_cancelled(self):
        self.stop_elevation_candidate_pick()

    def convert_portal_height(
        self, easting, northing, height, source, target, success, failure,
    ):
        """Convert an editor Z with official location-dependent MaRu models."""
        try:
            value = float(height)
            x = float(northing)  # MaRu API uses Estonian X=northing.
            y = float(easting)   # and Y=easting.
        except (TypeError, ValueError):
            failure(self.t("Kõrgus või koordinaadid ei ole korrektsed."))
            return
        steps = list(conversion_plan(source, target))
        if not steps:
            warning = (
                self.t("Kõrgussüsteem on teadmata; väärtust ei teisendatud.")
                if source == UNKNOWN or target == UNKNOWN else ""
            )
            success(value, warning)
            return

        def run(current):
            if not steps:
                success(current, "")
                return
            operation = steps.pop(0)
            if operation == "bk77_to_eh2000":
                self.network.query_maru_height_model(
                    "ymudel", x, y, current, run, failure,
                )
            elif operation == "eh2000_to_bk77":
                # ymudel returns BK77 + the local correction. Querying zero
                # gives that correction, which can safely be subtracted.
                self.network.query_maru_height_model(
                    "ymudel", x, y, 0.0,
                    lambda correction: run(current - correction), failure,
                )
            elif operation == "ellipsoidal_to_eh2000":
                self.network.query_maru_height_model(
                    "geoid", x, y, current, run, failure, direction=True,
                )
            elif operation == "eh2000_to_ellipsoidal":
                self.network.query_maru_height_model(
                    "geoid", x, y, current, run, failure, direction=False,
                )
            else:
                failure(self.t("Kõrgussüsteemide teisendus pole toetatud."))

        run(value)

    def elevation_rasters(self):
        """Return file/provider rasters suitable for numeric sampling."""
        return [
            layer for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsRasterLayer)
            and layer.isValid()
            and layer.providerType().casefold() != "wms"
            and not bool(layer.customProperty("qeoloog/elevation_match", False))
        ]

    @staticmethod
    def sample_elevation_raster(layer, easting, northing, band=1):
        """Sample the centre and its 3x3 neighbourhood in L-EST97."""
        if not isinstance(layer, QgsRasterLayer) or not layer.isValid():
            return None
        try:
            point = QgsCoordinateTransform(
                QgsCoordinateReferenceSystem("EPSG:3301"),
                layer.crs(), QgsProject.instance(),
            ).transform(QgsPointXY(float(easting), float(northing)))
        except (QgsCsException, TypeError, ValueError):
            return None
        band = min(max(1, int(band)), max(1, layer.bandCount()))
        dx = abs(float(layer.rasterUnitsPerPixelX())) or 1.0
        dy = abs(float(layer.rasterUnitsPerPixelY())) or 1.0
        provider = layer.dataProvider()
        values = []
        for x_offset in (-dx, 0.0, dx):
            for y_offset in (-dy, 0.0, dy):
                try:
                    value, valid = provider.sample(
                        QgsPointXY(point.x() + x_offset, point.y() + y_offset),
                        band,
                    )
                except Exception:
                    valid, value = False, None
                values.append(value if valid else None)
        return sample_summary(values)

    def show_elevation_match_layer(
        self, source_layer, band, target, tolerance, workspace_key,
        previous_layer_id="",
    ):
        """Clone a DEM and render only pixels matching the target elevation."""
        self.remove_elevation_match_layer(previous_layer_id)
        if not isinstance(source_layer, QgsRasterLayer) or not source_layer.isValid():
            raise ValueError(self.t("Vali sobiv rasterkiht."))
        lower, upper = matching_range(target, tolerance)
        clone = source_layer.clone()
        if not isinstance(clone, QgsRasterLayer) or not clone.isValid():
            raise ValueError(self.t("Rasterkihi koopiat ei saanud luua."))
        clone.setName(
            self.t("Kõrguse sobivusala")
            + f" · {target:.2f} ± {float(tolerance):g} m"
        )
        clone.setCustomProperty("qeoloog/elevation_match", True)
        clone.setCustomProperty("qeoloog/elevation_match_source", source_layer.id())
        shader_function = QgsColorRampShader()
        shader_function.setColorRampType(QgsColorRampShader.Interpolated)
        shader_function.setMinimumValue(lower)
        shader_function.setMaximumValue(upper)
        shader_function.setClip(True)
        shader_function.setColorRampItemList([
            QgsColorRampShader.ColorRampItem(lower, QColor(255, 193, 7, 210)),
            QgsColorRampShader.ColorRampItem(target, QColor(35, 196, 108, 225)),
            QgsColorRampShader.ColorRampItem(upper, QColor(255, 193, 7, 210)),
        ])
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(shader_function)
        renderer = QgsSingleBandPseudoColorRenderer(
            clone.dataProvider(), int(band), raster_shader
        )
        renderer.setClassificationMin(lower)
        renderer.setClassificationMax(upper)
        clone.setRenderer(renderer)
        clone.setOpacity(0.72)

        project = QgsProject.instance()
        project.addMapLayer(clone, False)
        root = project.layerTreeRoot()
        object_node = next((
            root.findLayer(layer.id())
            for layer in project.mapLayers().values()
            if str(layer.customProperty("qeoloog/faktika_layer_id", "")) == "1"
            and str(layer.customProperty(
                "qeoloog/faktika_workspace", "faktika"
            )) == str(workspace_key or "faktika")
        ), None)
        if object_node is not None and object_node.parent() is not None:
            parent = object_node.parent()
            parent.insertLayer(parent.children().index(object_node) + 1, clone)
        else:
            root.insertLayer(0, clone)
        clone.triggerRepaint()
        self.iface.mapCanvas().refresh()
        return clone.id()

    @staticmethod
    def remove_elevation_match_layer(layer_id):
        if layer_id and QgsProject.instance().mapLayer(str(layer_id)) is not None:
            QgsProject.instance().removeMapLayer(str(layer_id))

    def _open_new_faktika_object(
        self, object_type, metadata, people, point, workspace_key="faktika",
    ):
        map_point = point or self.iface.mapCanvas().center()
        try:
            map_point = QgsCoordinateTransform(
                self.iface.mapCanvas().mapSettings().destinationCrs(),
                QgsCoordinateReferenceSystem("EPSG:3301"),
                QgsProject.instance(),
            ).transform(map_point)
        except QgsCsException:
            pass
        parent = parent_defaults(metadata[1], object_type)
        parent["globalid"] = new_guid()
        parent["yksus_kood"] = unit_category_code(())
        context = {
            "parent": parent,
            "geometry": {"x": map_point.x(), "y": map_point.y(), "z": 0.0},
            "people": people,
            "current_person_id": self._faktika_current_person_id(people),
            "geological_units": [],
            "attachments": [],
            "attachment_keywords": [],
            "access_basis": [],
            "is_new": True,
            "workspace_key": workspace_key,
        }
        self._open_faktika_editor(context)

    def edit_current_faktika_object(self):
        if not PORTAL_EDITING_ENABLED:
            self.warning(self.t(
                "Portali kirjutamine on Qeoloogis välja lülitatud."
            ))
            return
        if not self._current_faktika_context:
            self.warning(self.t("Sellel objektil puudub redigeeritav Faktika vaste."))
            return
        self._open_faktika_editor(self._current_faktika_context)

    def _open_faktika_editor(self, context):
        if not PORTAL_EDITING_ENABLED:
            self.warning(self.t(
                "Portali kirjutamine on Qeoloogis välja lülitatud."
            ))
            return
        workspace_key = context.get("workspace_key") or "faktika"
        metadata = self.faktika_metadata(workspace_key)
        if len(metadata) != 6:
            self._ensure_faktika_metadata(
                lambda _metadata: self._open_faktika_editor(context),
                self.error, workspace_key,
            )
            return
        if not context.get("_sarv_suggestions_ready"):
            self._prepare_faktika_sarv_suggestions(
                context, self._open_faktika_editor,
            )
            return
        capabilities = {
            value.strip().casefold()
            for value in str(
                metadata.get(1, {}).get("capabilities") or ""
            ).split(",") if value.strip()
        }
        required = "create" if context.get("is_new") else "update"
        if required not in capabilities and "editing" not in capabilities:
            self.warning(self.t(
                "Faktika teenus ei anna sellele kasutajale vajalikku redigeerimisõigust."
            ))
            return
        dialog = FaktikaEditorDialog(
            self, metadata, context,
            self._save_faktika_editor,
            self.iface.mainWindow(),
        )
        self._faktika_dialog = dialog
        dialog.finished.connect(lambda _result: setattr(self, "_faktika_dialog", None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _prepare_faktika_sarv_suggestions(self, context, callback):
        """Attach locally confirmed and plausible SARV matches to an editor."""
        context = dict(context or {})
        parent = dict(context.get("parent") or {})
        try:
            is_borehole = int(parent.get("objekti_tyyp") or 0) == 1
        except (TypeError, ValueError):
            is_borehole = False
        source_sarv_id = str(parent.get("sarv_id") or "").strip()
        if (
            not is_borehole or context.get("is_new")
            or source_sarv_id not in {"", "0", "None"}
        ):
            context["_sarv_suggestions_ready"] = True
            callback(context)
            return

        attributes = dict(parent)
        attributes.update(context.get("match_attributes") or {})
        geometry = context.get("geometry") or {}
        attributes.setdefault("_qeoloog_x_3301", geometry.get("x"))
        attributes.setdefault("_qeoloog_y_3301", geometry.get("y"))
        if (
            attributes.get("_qeoloog_latitude") in (None, "")
            or attributes.get("_qeoloog_longitude") in (None, "")
        ):
            try:
                point = QgsCoordinateTransform(
                    QgsCoordinateReferenceSystem("EPSG:3301"),
                    QgsCoordinateReferenceSystem("EPSG:4326"),
                    QgsProject.instance(),
                ).transform(QgsPointXY(
                    float(attributes.get("_qeoloog_x_3301")),
                    float(attributes.get("_qeoloog_y_3301")),
                ))
                attributes["_qeoloog_longitude"] = point.x()
                attributes["_qeoloog_latitude"] = point.y()
            except (QgsCsException, TypeError, ValueError):
                pass

        match_key = self._egt_match_key("boreholes", attributes)
        saved = self.sarv_matches.get(match_key) if match_key else None
        saved = saved if isinstance(saved, dict) else {}

        def finish(localities=(), sites=(), drillcores=()):
            candidates = self._sarv_candidates_for_egt(
                localities, sites, attributes, drillcores,
                invalid_sarv_id=bool(saved.get("invalid_sarv_id")),
                invalid_ma_id=bool(saved.get("invalid_ma_id")),
            )
            saved_type = str(saved.get("source_type") or "")
            saved_id = str(saved.get("sarv_id") or "").strip()
            manual = next((
                candidate for candidate in candidates
                if candidate.get("source_type") == saved_type
                and str(candidate.get("sarv_id")) == saved_id
            ), None)
            if saved_type in {"drillcore", "locality", "site"} and saved_id:
                source_rows = {
                    "drillcore": drillcores,
                    "locality": localities,
                    "site": sites,
                }.get(saved_type, ())
                if manual is None:
                    row = next((
                        item for item in source_rows
                        if str(item.get("id")) == saved_id
                    ), None)
                    if row:
                        manual = self._sarv_candidate(
                            row, saved_type, attributes, allow_weak=True,
                            invalid_sarv_id=bool(saved.get("invalid_sarv_id")),
                            invalid_ma_id=bool(saved.get("invalid_ma_id")),
                        )
                        if manual:
                            candidates.insert(0, manual)
                if manual:
                    manual["manual"] = True
                    manual["confirmed"] = True
                    manual["evidence"] = self.t("Kohalik parandus")
            unique = {}
            for candidate in candidates:
                key = (
                    str(candidate.get("source_type") or ""),
                    str(candidate.get("sarv_id") or ""),
                )
                if key[1] and key not in unique:
                    unique[key] = candidate
            ordered = sorted(
                unique.values(),
                key=lambda item: (
                    not bool(item.get("manual")),
                    -float(item.get("score") or 0),
                ),
            )[:5]
            context["match_attributes"] = attributes
            context["sarv_match_key"] = match_key
            context["sarv_suggestions"] = ordered
            context["_sarv_suggestions_ready"] = True
            callback(context)

        self.message(self.t("SARV vaste kandidaate kontrollitakse…"))
        self._ensure_sarv_point_cache(
            finish,
            lambda _error: finish(),
        )

    def _persist_faktika_sarv_match(self, payload):
        candidate = payload.get("sarv_match")
        match_key = str(payload.get("sarv_match_key") or "").strip()
        if not match_key or not isinstance(candidate, dict):
            return
        source_type = str(candidate.get("source_type") or "")
        source_id = str(candidate.get("sarv_id") or "").strip()
        if source_type not in {"drillcore", "locality", "site"} or not source_id:
            return
        attributes = payload.get("sarv_match_attributes") or {}
        value = dict(self.sarv_matches.get(match_key) or {})
        value.update({
            "source_type": source_type,
            "sarv_id": source_id,
            "gea_id": str(attributes.get("gea_id") or ""),
            "original_sarv_id": str(attributes.get("sarv_id") or ""),
            "original_ma_id": str(attributes.get("ma_orig_id") or ""),
            "source": "local_override",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        self.sarv_matches[match_key] = value
        PluginSettings.save_sarv_matches(self.sarv_matches)

    def _clean_faktika_attributes(
        self, layer_id, values, workspace_key="faktika",
    ):
        allowed = {
            str(field.get("name"))
            for field in editable_fields(
                self.faktika_metadata(workspace_key).get(layer_id, {})
            )
        }
        allowed.add("globalid")
        cleaned = {
            key: value for key, value in dict(values or {}).items()
            if key in allowed
        }
        if values.get("_existing"):
            cleaned["_existing"] = True
        return cleaned

    def _save_faktika_editor(self, payload, dialog):
        if not PORTAL_EDITING_ENABLED:
            dialog.save_failed(self.t(
                "Portali kirjutamine on Qeoloogis välja lülitatud."
            ))
            return
        workspace_key = payload.get("workspace_key") or "faktika"
        workspace = FAKTIKA_WORKSPACES[workspace_key]
        parent = self._clean_faktika_attributes(
            1, payload["parent"], workspace_key
        )
        units = [
            self._clean_faktika_attributes(6, row, workspace_key)
            for row in payload.get("geological_units") or ()
        ]
        attachments = [
            self._clean_faktika_attributes(4, row, workspace_key)
            for row in payload.get("attachments") or ()
        ]
        keywords = [
            self._clean_faktika_attributes(3, row, workspace_key)
            for row in payload.get("attachment_keywords") or ()
        ]
        access_rows = [
            self._clean_faktika_attributes(5, row, workspace_key)
            for row in payload.get("access_basis") or ()
        ]
        people = [
            self._clean_faktika_attributes(2, row, workspace_key)
            for row in payload.get("people") or ()
        ]
        edits = build_apply_edits(
            parent, payload["geometry"], units,
            is_new=payload.get("is_new", False),
            deleted_unit_ids=payload.get("deleted_unit_ids") or (),
            attachments=attachments,
            deleted_attachment_ids=payload.get("deleted_attachment_ids") or (),
            attachment_keywords=keywords,
            deleted_keyword_ids=payload.get("deleted_keyword_ids") or (),
            access_rows=access_rows,
            deleted_access_ids=payload.get("deleted_access_ids") or (),
            people=people,
            deleted_person_ids=payload.get("deleted_person_ids") or (),
        )
        for edit in edits:
            edit["id"] = self._faktika_actual_layer_id(
                workspace_key, edit["id"]
            )

        def failed(error):
            dialog.save_failed(error)

        def applied(response):
            try:
                validate_apply_edits_response(response)
            except ValueError as error:
                failed(str(error))
                return
            for layer in QgsProject.instance().mapLayers().values():
                if (
                    layer.customProperty("qeoloog/faktika_layer_id", "")
                    and str(layer.customProperty(
                        "qeoloog/faktika_workspace", "faktika"
                    )) == workspace_key
                ):
                    try:
                        layer.reload()
                    except AttributeError:
                        layer.dataProvider().reloadData()
                    layer.triggerRepaint()
            if people or payload.get("deleted_person_ids"):
                if workspace_key == "faktika":
                    self._faktika_people = None
                else:
                    self._faktika_workspace_people.pop(workspace_key, None)
            self._persist_faktika_sarv_match(payload)
            dialog.save_succeeded()
            self.success(self.t("Faktika muudatused salvestati Portalisse."))
            guid = normalize_guid(parent.get("globalid"))
            if guid:
                QTimer.singleShot(
                    250,
                    lambda: self._query_faktika_rows(
                        1, f"globalid = '{escape_where(guid)}'",
                        lambda rows: self._open_saved_faktika(
                            rows, workspace_key
                        ),
                        self.warning, geometry=True,
                        workspace_key=workspace_key,
                    ),
                )

        def perform_save():
            self.network.apply_arcgis_service_edits(
                workspace["url"], edits, self.egt_portal_authcfg,
                applied, failed,
            )

        edit_moment = payload.get("edit_moment")
        guid = normalize_guid(parent.get("globalid"))
        if payload.get("is_new") or not edit_moment or not guid:
            perform_save()
            return

        def checked(rows):
            latest = rows[0].get("muutmise_aeg") if rows else None
            if latest not in (None, edit_moment) and str(latest) != str(edit_moment):
                failed(self.t(
                    "Kirjet on Portalis vahepeal muudetud. Ava objekt uuesti, "
                    "et vältida teise kasutaja muudatuste ülekirjutamist."
                ))
                return
            perform_save()

        self._query_faktika_rows(
            1, f"globalid = '{escape_where(guid)}'", checked, failed,
            fields=("globalid", "muutmise_aeg"),
            workspace_key=workspace_key,
        )

    def _open_saved_faktika(self, rows, workspace_key="faktika"):
        if not rows:
            return
        record = dict(rows[0])
        geometry = record.pop("_geometry", {})
        object_type = int(record.get("objekti_tyyp") or 2)
        role = "boreholes" if object_type == 1 else "observations"
        name = record.get("nimi") or record.get("alias") or record.get("gea_id")
        record.update({
            "_qeoloog_x_3301": geometry.get("x"),
            "_qeoloog_y_3301": geometry.get("y"),
            "z_abs": geometry.get("z"),
        })
        self._load_details(
            role, str(record.get("globalid") or ""), str(name or "Faktika"), record,
            faktika_parent=record, faktika_geometry=geometry,
            faktika_workspace=workspace_key,
        )

    @staticmethod
    def is_portal_feature_layer(layer):
        return (
            isinstance(layer, QgsVectorLayer)
            and layer.providerType().casefold()
            in {"arcgisfeatureserver", "afs"}
        )

    def _enforce_portal_layer_read_only(self, layer):
        """Prevent QGIS' native editing tools from writing Qeoloog layers."""
        if not self.is_portal_feature_layer(layer):
            return False
        managed = bool(
            str(layer.customProperty(self.SOURCE_PROPERTY, "")).strip()
            or str(layer.customProperty("qeoloog/faktika_layer_id", "")).strip()
            or str(layer.customProperty("qeoloog/portal_bundle", "")).strip()
        )
        if not managed:
            return False
        if layer.isEditable():
            modified = bool(layer.isModified())
            try:
                layer.rollBack()
            except (AttributeError, RuntimeError):
                pass
            if modified:
                self.warning(self.t(
                    "Portali kihi pooleliolevad muudatused tühistati, sest "
                    "Qeoloog avab Portali andmeid ainult kirjutuskaitstult."
                ))
        try:
            layer.setReadOnly(True)
        except (AttributeError, RuntimeError):
            return False
        layer.setCustomProperty("qeoloog/portal_read_only", True)
        return True

    @staticmethod
    def portal_edit_operations(layer):
        """Return edit operation keys advertised by the AFS provider."""
        if not PORTAL_EDITING_ENABLED:
            return []
        if not QeoloogPlugin.is_portal_feature_layer(layer):
            return []
        capabilities = layer.dataProvider().capabilities()
        flags = Qgis.VectorProviderCapability
        operations = []
        if capabilities & flags.AddFeatures:
            operations.append("add")
        if capabilities & (
            flags.ChangeAttributeValues | flags.ChangeGeometries
        ):
            operations.append("update")
        if capabilities & flags.DeleteFeatures:
            operations.append("delete")
        return operations

    def _observe_portal_layer(self, layer):
        previous = self._portal_observed_layer
        if previous is layer:
            return
        if previous is not None:
            for signal in (previous.editingStarted, previous.editingStopped):
                try:
                    signal.disconnect(self._refresh_portal_edit_ui)
                except (TypeError, RuntimeError):
                    pass
        self._portal_observed_layer = (
            layer if isinstance(layer, QgsVectorLayer) else None
        )
        if self._portal_observed_layer is not None:
            for signal in (
                self._portal_observed_layer.editingStarted,
                self._portal_observed_layer.editingStopped,
            ):
                signal.connect(self._refresh_portal_edit_ui)

    def _portal_current_layer_changed(self, layer):
        self._enforce_portal_layer_read_only(layer)
        self._observe_portal_layer(layer)
        self._refresh_portal_edit_ui()

    def _refresh_portal_edit_ui(self):
        if self.dock:
            self.dock.layers.update_portal_edit_state(
                self.iface.activeLayer()
            )

    def start_portal_editing(self):
        if not PORTAL_EDITING_ENABLED:
            self.warning(self.t(
                "Portali kirjutamine on Qeoloogis välja lülitatud."
            ))
            return False
        layer = self.iface.activeLayer()
        operations = self.portal_edit_operations(layer)
        if not operations:
            self.warning(self.t(
                "Aktiivne Portali kiht ei luba selle kasutajaga redigeerimist."
            ))
            self._refresh_portal_edit_ui()
            return False
        if layer.isEditable() or layer.startEditing():
            self.success(self.t(
                "Portali kihi redigeerimine on sisse lülitatud."
            ))
            self._refresh_portal_edit_ui()
            return True
        errors = "; ".join(layer.commitErrors())
        self.error(
            self.t("Portali kihi redigeerimist ei saanud alustada.")
            + (f" {errors}" if errors else "")
        )
        self._refresh_portal_edit_ui()
        return False

    def save_portal_edits(self):
        if not PORTAL_EDITING_ENABLED:
            self.warning(self.t(
                "Portali kirjutamine on Qeoloogis välja lülitatud."
            ))
            return False
        layer = self.iface.activeLayer()
        if not self.is_portal_feature_layer(layer) or not layer.isEditable():
            self.warning(self.t("Aktiivne Portali kiht pole redigeerimisrežiimis."))
            return False
        if layer.commitChanges():
            layer.reload()
            if self._layer_role(layer) == "geophysics_fieldwork":
                self._apply_geophysics_method_renderer(layer)
            self.success(self.t("Muudatused salvestati Portalisse."))
            self._refresh_portal_edit_ui()
            return True
        errors = "; ".join(layer.commitErrors())
        self.error(
            self.t("Muudatuste salvestamine Portalisse ebaõnnestus.")
            + (f" {errors}" if errors else "")
        )
        self._refresh_portal_edit_ui()
        return False

    def discard_portal_edits(self):
        layer = self.iface.activeLayer()
        if not self.is_portal_feature_layer(layer) or not layer.isEditable():
            return False
        if layer.isModified():
            answer = QMessageBox.question(
                self.iface.mainWindow(), "Qeoloog",
                self.t("Kas loobuda aktiivse Portali kihi salvestamata muudatustest?"),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        if layer.rollBack():
            layer.reload()
            if self._layer_role(layer) == "geophysics_fieldwork":
                self._apply_geophysics_method_renderer(layer)
            self.success(self.t("Portali kihi muudatused tühistati."))
            self._refresh_portal_edit_ui()
            return True
        self.error(self.t("Portali kihi muudatusi ei saanud tühistada."))
        self._refresh_portal_edit_ui()
        return False

    def import_geophysics_fieldwork(self):
        """Open the authenticated CSV-to-Portal fieldwork workflow."""
        if not PORTAL_EDITING_ENABLED:
            self.warning(self.t(
                "Portali kirjutamine on Qeoloogis välja lülitatud."
            ))
            return
        if not self.egt_portal_authcfg or not self.egt_portal_catalog_account:
            self.warning(self.t("Logi esmalt EGT Portalisse."))
            return
        path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            self.t("Vali geofüüsika välitööde CSV"),
            "",
            "CSV (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            points = read_collar_points(path)
        except (OSError, ValueError) as error:
            self.error(self.t("CSV-faili lugemine ebaõnnestus") + f": {error}")
            return
        self.message(self.t("Geofüüsika välitööde valikuid laaditakse…"))

        def loaded(metadata):
            if metadata.get("geometryType") != "esriGeometryPolyline":
                self.error(self.t(
                    "Geofüüsika välitööde sihtkiht ei ole joonkiht."
                ))
                return
            capabilities = {
                value.strip().casefold()
                for value in str(metadata.get("capabilities") or "").split(",")
            }
            if "create" not in capabilities:
                self.error(self.t(
                    "Sisselogitud kasutajal puudub Geofüüsika välitööde "
                    "kihile lisamise õigus."
                ))
                return
            domains = {
                "method": coded_value_options(metadata, "geofys_meetod"),
                "device": coded_value_options(metadata, "geofys_seade"),
                "responsible": coded_value_options(
                    metadata, "geofys_vastutaja"
                ),
            }
            if any(not options for options in domains.values()):
                self.error(self.t(
                    "Geofüüsika välitööde koodivalikuid ei saanud "
                    "Portali kihist lugeda."
                ))
                return
            dialog = GeophysicsFieldworkDialog(
                self, path, len(points), domains,
                self.egt_portal_catalog_account,
                self.iface.mainWindow(),
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self._upload_geophysics_fieldwork(
                points, dialog.values()
            )

        self.network.query_arcgis_layer_metadata(
            self.GEOPHYSICS_FIELDWORK_URL,
            self.GEOPHYSICS_FIELDWORK_LAYER,
            self.egt_portal_authcfg,
            loaded,
            lambda error: self.error(
                self.t("Geofüüsika välitööde kihi lugemine ebaõnnestus")
                + f": {error}"
            ),
        )

    @classmethod
    def _is_geophysics_fieldwork_source(cls, url, layer_name):
        """Return whether an ArcGIS layer is the managed fieldwork layer."""
        return (
            str(url or "").strip().rstrip("/").casefold()
            == cls.GEOPHYSICS_FIELDWORK_URL.rstrip("/").casefold()
            and str(layer_name or "").strip().lstrip("0")
            == cls.GEOPHYSICS_FIELDWORK_LAYER.lstrip("0")
        )

    def _is_geophysics_fieldwork_layer(self, layer):
        if not isinstance(layer, QgsVectorLayer):
            return False
        definition = self._geophysics_fieldwork_definition()
        if self._layer_source_id(layer) == self._source_id(definition):
            return True
        if layer.providerType() != "arcgisfeatureserver":
            return False
        try:
            source_url = QgsDataSourceUri(layer.source()).param("url")
        except (AttributeError, TypeError, ValueError):
            return False
        expected = feature_layer_url(
            self.GEOPHYSICS_FIELDWORK_URL,
            self.GEOPHYSICS_FIELDWORK_LAYER,
        )
        return (
            str(source_url or "").strip().rstrip("/").casefold()
            == expected.rstrip("/").casefold()
        )

    def _geophysics_fieldwork_definition(self):
        return LayerDefinition(
            code="EGT",
            name="Geofüüsika välitööd",
            name_en="Geophysical fieldwork",
            protocol="ARCGIS_FEATURESERVER",
            url=self.GEOPHYSICS_FIELDWORK_URL,
            layer_name=self.GEOPHYSICS_FIELDWORK_LAYER,
            color="#7a4ea3",
            placement="dropdown",
            use_portal_auth=True,
            role="geophysics_fieldwork",
        )

    def _upload_geophysics_fieldwork(self, points, values):
        """Create and commit one Z-enabled multipart line to EGT Portal."""
        if not PORTAL_EDITING_ENABLED:
            self.warning(self.t(
                "Portali kirjutamine on Qeoloogis välja lülitatud."
            ))
            return False
        definition = self._geophysics_fieldwork_definition()
        source_id = self._source_id(definition)
        project = QgsProject.instance()
        layer = next((
            candidate for candidate in project.mapLayers().values()
            if self._layer_source_id(candidate) == source_id
        ), None)
        if layer is None:
            if not self.add_layer(definition, force_add=True):
                return False
            layer = next((
                candidate for candidate in project.mapLayers().values()
                if self._layer_source_id(candidate) == source_id
            ), None)
        if layer is None or "add" not in self.portal_edit_operations(layer):
            self.error(self.t(
                "Sisselogitud kasutajal puudub Geofüüsika välitööde "
                "kihile lisamise õigus."
            ))
            return False
        if layer.isEditable() and layer.isModified():
            self.warning(self.t(
                "Salvesta või tühista esmalt Geofüüsika välitööde kihi "
                "pooleliolevad muudatused."
            ))
            return False

        try:
            transform = QgsCoordinateTransform(
                values["crs"], layer.crs(), project.transformContext()
            )
            transformed = []
            for x, y, z, identifier in points:
                point = transform.transform(QgsPointXY(x, y))
                transformed.append((point.x(), point.y(), z, identifier))
        except (QgsCsException, ValueError) as error:
            self.error(self.t("Koordinaatide teisendamine ebaõnnestus") + f": {error}")
            return False

        parts = split_line_parts(transformed, 50.0)
        used_points = sum(len(part) for part in parts)
        if not parts:
            self.error(self.t(
                "CSV punktidest ei tekkinud ühtegi vähemalt kahe punktiga joont."
            ))
            return False
        multiline = QgsMultiLineString()
        for part in parts:
            multiline.addGeometry(QgsLineString([
                QgsPoint(x, y, z) for x, y, z, _identifier in part
            ]))
        geometry = QgsGeometry(multiline)
        if geometry.isNull() or geometry.isEmpty():
            self.error(self.t("Multipart-joone loomine ebaõnnestus."))
            return False

        required_fields = {
            "nimi", "aeg", "geofys_meetod", "geofys_seade",
            "geofys_vastutaja", "markus",
        }
        available = {field.name() for field in layer.fields()}
        missing = sorted(required_fields.difference(available))
        if missing:
            self.error(
                self.t("Sihtkihi skeemist puuduvad väljad") + ": "
                + ", ".join(missing)
            )
            return False

        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        feature["nimi"] = values["name"]
        feature["aeg"] = QDateTime(
            values["date"], QTime(12, 0), Qt.TimeSpec.UTC
        )
        feature["geofys_meetod"] = values["method"]
        feature["geofys_seade"] = values["device"]
        feature["geofys_vastutaja"] = values["responsible"]
        feature["markus"] = values["notes"] or None

        started_here = not layer.isEditable()
        if started_here and not layer.startEditing():
            self.error(self.t("Portali kihi redigeerimist ei saanud alustada."))
            return False
        if not layer.addFeature(feature):
            if started_here:
                layer.rollBack()
            self.error(self.t("Multipart-joont ei saanud Portali kihile lisada."))
            return False
        if not layer.commitChanges():
            errors = "; ".join(layer.commitErrors())
            if started_here:
                layer.rollBack()
            self.error(
                self.t("Geofüüsika välitööde üleslaadimine ebaõnnestus.")
                + (f" {errors}" if errors else "")
            )
            self._refresh_portal_edit_ui()
            return False
        layer.reload()
        self._apply_geophysics_method_renderer(layer)
        self.iface.setActiveLayer(layer)
        self.success(
            self.t("Geofüüsika välitööd laaditi Portalisse")
            + f": {len(points)} {self.t('punkti')}, "
            + f"{len(parts)} {self.t('jooneosa')}"
            + (
                f", {len(points) - used_points} {self.t('üksikpunkti jäeti välja')}"
                if used_points < len(points) else ""
            )
        )
        self._refresh_portal_edit_ui()
        return True

    def set_label_text_size(self, value):
        """Persist and immediately reapply the shared point-label text size."""
        PluginSettings.save_label_text_size(value)
        self.label_text_size = PluginSettings.load_label_text_size()
        self._refresh_map_labeling()

    def set_egt_label_fields(self, values):
        """Persist and apply independently configurable point label rows."""
        current = getattr(self, "egt_label_fields", DEFAULT_MAP_LABEL_FIELDS)
        self.egt_label_fields = normalize_map_label_fields(
            {**current, **(values if isinstance(values, dict) else {})}
        )
        PluginSettings.save_map_label_fields(self.egt_label_fields)
        self._refresh_map_labeling()
        self._schedule_egt_label_refresh()

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
        self._refresh_map_labeling()
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
        if self._unloading:
            return
        QTimer.singleShot(
            0,
            lambda: None if self._unloading else self._sync_project_layers(),
        )
        self._schedule_egt_label_refresh()

    def _sync_project_layers(self):
        if self._unloading:
            return
        for layer in QgsProject.instance().mapLayers().values():
            self._migrate_latvia_wfs_layer(layer)
        self._upgrade_loaded_portal_bundles()
        self.sync_dropdown_checks()
        self._ensure_egt_points_on_top()
        # A project reload can restore the public PA/VP nodes after the
        # authenticated Faktika workspace has been rebuilt.  Keep the two
        # public layers hidden while Faktika is active so the map does not
        # show duplicate points or accidentally mix editable and public
        # records.  Visibility is restored by set_faktika_active(False).
        if self._faktika_is_active():
            self._hide_public_egt_layers_for_faktika()
        if self.dock:
            self.dock.cross_sections.reload_rasters()
            self.dock.cross_sections.backfill_egt_elevations()
            self._refresh_archive_report_controls()

    def _upgrade_loaded_portal_bundles(self):
        """Restore managed Portal roles and their deterministic styling."""
        for layer in QgsProject.instance().mapLayers().values():
            if (
                str(layer.customProperty("qeoloog/portal_bundle", ""))
                == "field_mapping"
                and str(layer.customProperty(
                    "qeoloog/portal_bundle_layer_id", ""
                )) == "0"
            ):
                layer.setCustomProperty(self.ROLE_PROPERTY, "field_mapping")
            if self._is_geophysics_fieldwork_layer(layer):
                layer.setCustomProperty(
                    self.ROLE_PROPERTY, "geophysics_fieldwork"
                )
                self._apply_geophysics_method_renderer(layer)
            self._enforce_portal_layer_read_only(layer)

    def sync_dropdown_checks(self):
        loaded = {self._layer_source_id(layer) for layer in QgsProject.instance().mapLayers().values()}
        for source_id, action in self.dropdown_actions.items():
            action.blockSignals(True)
            action.setChecked(source_id in loaded)
            action.blockSignals(False)
        for source_id, action in self.egt_portal_layer_actions.items():
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
                and not layer.customProperty(self.SEARCH_RESULT_PROPERTY, False)
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
        if definition.role == "maaru_cores":
            return self._add_maaru_layer(definition, force_add)
        if definition.role == "veka_boreholes":
            return self._add_veka_layer(definition, force_add)

        source_id = self._source_id(definition)
        name = self.display_name(definition)
        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if (
                self._layer_source_id(layer) == source_id
                and not layer.customProperty(self.SEARCH_RESULT_PROPERTY, False)
            ):
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
                    node.setItemVisibilityChecked(
                        not (
                            self._faktika_is_active()
                            and definition.role in {"boreholes", "observations"}
                        )
                    )
                layer.setCustomProperty(self.ROLE_PROPERTY, definition.role)
                if self.is_portal_feature_layer(layer):
                    self._enforce_portal_layer_read_only(layer)
                self._apply_definition_renderer(layer, definition)
                self._apply_layer_workarounds(layer, definition)
                self._ensure_egt_points_on_top(layer if definition.role else None)
                self.iface.setActiveLayer(layer)
                self.message(
                    f"{name} "
                    + ("is already in the project." if self.language == "en" else "on juba projektis.")
                )
                return True

        protocol = definition.protocol.upper()
        if protocol == "WFS":
            layer = QgsVectorLayer(self._wfs_uri(definition), name, "WFS")
        elif is_arcgis_map_protocol(protocol):
            try:
                source = self._arcgis_map_uri(definition)
            except ValueError as error:
                self.error(str(error))
                self.sync_dropdown_checks()
                return False
            layer = QgsVectorLayer(
                source, name, "arcgisfeatureserver"
            )
        elif is_arcgis_feature_protocol(protocol):
            if definition.use_portal_auth and not self.egt_portal_authcfg:
                self.warning(self.t(
                    "Vali Kihid-paanil EGT Portali autentimine."
                ))
                self.sync_dropdown_checks()
                return False
            try:
                source = self._arcgis_feature_uri(definition)
            except ValueError as error:
                self.error(str(error))
                self.sync_dropdown_checks()
                return False
            layer = QgsVectorLayer(
                source, name, "arcgisfeatureserver"
            )
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
        if is_arcgis_feature_protocol(protocol):
            self._enforce_portal_layer_read_only(layer)
        self._apply_layer_workarounds(layer, definition)
        self._apply_definition_renderer(layer, definition)
        project.addMapLayer(layer, False)
        root = project.layerTreeRoot()
        if definition.base_map:
            root.addLayer(layer)
        else:
            root.insertLayer(0, layer)
        if (
            self._faktika_is_active()
            and definition.role in {"boreholes", "observations"}
        ):
            node = root.findLayer(layer.id())
            if node:
                node.setItemVisibilityChecked(False)
        self._ensure_egt_points_on_top(layer if definition.role else None)
        self.iface.setActiveLayer(layer)
        if (
            is_arcgis_map_protocol(protocol)
            or (is_arcgis_feature_protocol(protocol) and not definition.role)
        ):
            self._apply_egt_portal_standard_legend(layer, definition)
        if is_arcgis_feature_protocol(protocol):
            self.message(self.t("Portali kiht avati kirjutuskaitstult."))
        if definition.role:
            self.apply_egt_filters()
        if definition.role == "latvia_boreholes":
            self._apply_latvia_search_filter()
        self.success(f"{name} " + ("added." if self.language == "en" else "lisatud."))
        self.sync_dropdown_checks()
        return True

    # ---- MaRu historical drill-core database -----------------------------------

    def _ensure_maaru_database(self, success, failure, force=False):
        """Provide the local MaRu cache, downloading the official ZIP once."""
        if self._maaru_db is not None and self._maaru_db.available and not force:
            success(self._maaru_db)
            return
        self._maaru_waiters.append((success, failure))
        if self._maaru_loading:
            return
        self._maaru_loading = True
        self.message(self.t("MaRu puursüdamike andmebaasi laaditakse…"))

        def loaded(payload):
            try:
                build_maaru_database(payload, self._maaru_cache_path)
                database = MaaruDatabase(self._maaru_cache_path)
                if not database.available:
                    raise ValueError("The local MaRu cache is invalid.")
            except (OSError, ValueError, sqlite3.Error) as error:
                failed(error)
                return
            self._maaru_db = database
            self._maaru_rows = {}
            self._maaru_loading = False
            waiters = self._maaru_waiters
            self._maaru_waiters = []
            metadata = database.metadata()
            self.success(
                (
                    f"MaRu drill-core database ready: "
                    f"{metadata.get('record_count', '?')} objects."
                    if self.language == "en" else
                    f"MaRu puursüdamike andmebaas on valmis: "
                    f"{metadata.get('record_count', '?')} objekti."
                )
            )
            if self.dock and hasattr(self.dock.layers, "set_maaru_status"):
                self.dock.layers.set_maaru_status(metadata)
            for callback, _failed in waiters:
                callback(database)

        def failed(error):
            self._maaru_loading = False
            waiters = self._maaru_waiters
            self._maaru_waiters = []
            if self.dock and hasattr(self.dock.layers, "set_maaru_status"):
                self.dock.layers.set_maaru_status({}, str(error))
            for _callback, callback_failed in waiters:
                callback_failed(str(error))

        self.network.get_bytes(
            MAARU_ARCHIVE_URL, loaded, failed,
            max_bytes=MAARU_MAX_ARCHIVE_BYTES,
        )

    def refresh_maaru_database(self):
        self._ensure_maaru_database(
            lambda _database: self.message(
                self.t("MaRu andmebaasi kohalik koopia uuendati.")
            ),
            lambda error: self.error(
                self.t("MaRu andmebaasi uuendamine ebaõnnestus")
                + f": {error}"
            ),
            force=True,
        )

    def _add_maaru_layer(self, definition, force_add=False):
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
            node = project.layerTreeRoot().findLayer(existing[0].id())
            if node:
                node.setItemVisibilityChecked(True)
            self.iface.setActiveLayer(existing[0])
            return True

        self._ensure_maaru_database(
            lambda database: self._create_maaru_layer(definition, database),
            lambda error: self.error(
                (f"Could not load MaRu drill cores: {error}"
                 if self.language == "en" else
                 f"MaRu puursüdamike laadimine ebaõnnestus: {error}")
            ),
        )
        return True

    def _create_maaru_layer(self, definition, database):
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
        layer.setCustomProperty(self.ROLE_PROPERTY, "maaru_cores")
        provider = layer.dataProvider()
        fields = (
            ("maaru_id", QVariant.String), ("korrastatud_nr", QVariant.String),
            ("sarv_id", QVariant.String), ("gb_id", QVariant.String),
            ("number", QVariant.String), ("nimi", QVariant.String),
            ("z_abs", QVariant.Double), ("sygavus", QVariant.Double),
            ("fond", QVariant.String), ("fnr", QVariant.String),
            ("tyyp", QVariant.String), ("ap_avamus", QVariant.String),
            ("strat_algus", QVariant.String), ("strat_lopp", QVariant.String),
            ("kastide_arv", QVariant.Int),
            ("klassif_yksus_kood", QVariant.Int),
            ("yksus_kood", QVariant.String),
        )
        provider.addAttributes([
            QgsField(name, field_type) for name, field_type in fields
        ])
        layer.updateFields()
        rows = database.points()
        features = []
        cached = {}
        for row in rows:
            identifier = str(row.get("id") or "")
            x = row.get("_maaru_x")
            y = row.get("_maaru_y")
            try:
                x, y = float(x), float(y)
            except (TypeError, ValueError):
                continue
            if not (300000 <= x <= 850000 and 6300000 <= y <= 6700000):
                continue
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            feature.setAttributes([
                identifier, row.get("uus_id"), row.get("sarv_loc_id"),
                row.get("GB_id"), row.get("number"), row.get("nimetus"),
                veka_number(row.get("z")), veka_number(row.get("sygavus")),
                row.get("fond"),
                row.get("fnr"), row.get("tüüp"), row.get("AP avamus"),
                row.get("strat. algus"), row.get("strat. lõpp"),
                int(veka_number(row.get("kastide arv")) or 0),
                int(row.get("klassif_yksus_kood") or 997),
                self.t(UNIT_TYPES.get(
                    int(row.get("klassif_yksus_kood") or 997),
                    UNIT_TYPES[997],
                )),
            ])
            features.append(feature)
            cached[identifier] = row
            if len(features) >= 4000:
                provider.addFeatures(features)
                features = []
        if features:
            provider.addFeatures(features)
        layer.updateExtents()
        self._maaru_rows = cached
        self._apply_category_renderer(layer)
        self._apply_name_labeling(layer, "number")
        project = QgsProject.instance()
        project.addMapLayer(layer, False)
        project.layerTreeRoot().insertLayer(0, layer)
        self._ensure_egt_points_on_top(layer)
        self.iface.setActiveLayer(layer)
        self.sync_dropdown_checks()
        self.success(
            f"Loaded {len(cached)} MaRu drill-core records."
            if self.language == "en" else
            f"Laaditi {len(cached)} MaRu puursüdamiku kirjet."
        )

    def _apply_egt_portal_standard_legend(self, layer, definition):
        """Apply EGT's authoritative ArcGIS ``drawingInfo`` symbology.

        QGIS' native AFS provider normally converts the same renderer while
        opening a layer.  Reading and applying it explicitly keeps the legend
        deterministic for Portal layers too, including picture markers,
        geological index colours, line patterns and category labels.
        """
        layer_id = layer.id()
        source_id = self._source_id(definition)

        def loaded(renderer_data):
            current = QgsProject.instance().mapLayer(layer_id)
            if (
                current is None
                or self._layer_source_id(current) != source_id
                or not renderer_data
            ):
                return
            try:
                renderer = QgsArcGisRestUtils.convertRenderer(renderer_data)
            except (AttributeError, TypeError, ValueError):
                renderer = None
            if renderer is None:
                return
            current.setRenderer(renderer)
            current.setCustomProperty(
                "qeoloog/egt_standard_legend", True
            )
            current.triggerRepaint()
            current.emitStyleChanged()

        # The native provider renderer remains in place if metadata cannot be
        # read or QGIS cannot convert an uncommon ArcGIS symbol type.
        self.network.query_arcgis_layer_renderer(
            definition.url,
            definition.layer_name,
            self.egt_portal_authcfg if definition.use_portal_auth else "",
            loaded,
            lambda _error: None,
        )

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
                "label_depth": row.get("depth"),
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
        self._apply_external_labeling(layer, "veka_boreholes")
        project = QgsProject.instance()
        project.addMapLayer(layer, False)
        project.layerTreeRoot().insertLayer(0, layer)
        self._ensure_egt_points_on_top(layer)
        self.iface.setActiveLayer(layer)
        purposes = sorted({
            (str(row.get("tyyp")), str(row.get("tyyp_selg") or row.get("tyyp")))
            for row in usable_rows.values() if row.get("tyyp") not in (None, "")
        }, key=lambda item: item[1].casefold())
        usages = veka_usage_options(usable_rows.values())
        groundwater = sorted({
            (str(row.get("pohjaveekogum_id")), str(row.get("pohjaveekogum_nimi")))
            for row in usable_rows.values()
            if row.get("pohjaveekogum_id") not in (None, "")
            and row.get("pohjaveekogum_nimi") not in (None, "")
        }, key=lambda item: item[1].casefold())
        if self.dock:
            self.dock.veka.set_main_options(purposes, groundwater, usages)
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
        if role == "sarv_drillcores":
            provider.addAttributes([QgsField("label_depth", QVariant.String)])
        layer.updateFields()
        features = []

        def numeric_depth(value):
            try:
                return float(value) if value not in (None, "") else None
            except (TypeError, ValueError):
                return None

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
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(longitude, latitude)))
            source_type = {
                "sarv_localities": "locality",
                "sarv_sites": "site",
                "sarv_drillcores": "drillcore",
            }.get(role, "")
            attributes = [
                row.get("id"),
                source_type,
                row.get("name"),
                row.get("name_en"),
                row.get("number"),
                numeric_depth(row.get("depth")),
                type_value,
                row.get("id") if role == "sarv_localities" else locality_id,
                row.get("land_board_id"),
                latitude,
                longitude,
            ]
            if role == "sarv_drillcores":
                attributes.append(normalize_sarv_core_depth(
                    row.get("label_depth", row.get("depth"))
                ))
            feature.setAttributes(attributes)
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
        self._apply_external_labeling(layer, role)
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
        service_url = definition.url
        provider_options = ""
        if (
            definition.menu_group.casefold() == "gtk"
            and definition.protocol.upper() == "WMS"
        ):
            # QGIS unconditionally appends TRANSPARENT=true to WMS legend
            # requests.  GTK's legend text is black, so the resulting
            # transparent image is unreadable with QGIS' dark theme.  Using
            # the configured base URL for both requests lets us pin the
            # legend to an opaque white background.  QgsWmsProvider replaces
            # TRANSPARENT with TRUE for GetMap, so the actual map overlay
            # remains transparent.
            separator = "&" if "?" in service_url else "?"
            service_url = (
                f"{service_url}{separator}TRANSPARENT=FALSE&BGCOLOR=0xFFFFFF"
            )
            service_url = quote(service_url, safe="")
            provider_options = "&IgnoreGetMapUrl=1"
        return (
            f"crs={definition.service_crs or 'EPSG:3301'}&format=image/png"
            f"{layer_parameters}"
            f"{provider_options}&url={service_url}&version=1.3.0"
        )

    @staticmethod
    def _wfs_uri(definition, filter_expression=""):
        uri = QgsDataSourceUri()
        uri.setParam("url", definition.url)
        uri.setParam("typename", definition.layer_name)
        uri.setParam("version", "2.0.0")
        uri.setParam("srsname", definition.service_crs or "EPSG:3301")
        uri.setParam("pagingEnabled", "true")
        uri.setParam("restrictToRequestBBOX", "1")
        uri.setParam("forceInitialGetFeature", "true")
        if filter_expression:
            # QGIS converts this provider filter to the server-side WFS
            # request before the initial GetFeature is made.
            uri.setParam("filter", filter_expression)
        return uri.uri(False)

    def _arcgis_feature_uri(self, definition):
        uri = QgsDataSourceUri()
        uri.setParam(
            "url", feature_layer_url(definition.url, definition.layer_name)
        )
        if definition.use_portal_auth:
            uri.setAuthConfigId(self.egt_portal_authcfg)
        return uri.uri(False)

    @staticmethod
    def _arcgis_map_uri(definition):
        uri = QgsDataSourceUri()
        uri.setParam(
            "url", map_layer_url(definition.url, definition.layer_name)
        )
        return uri.uri(False)

    def _refresh_loaded_plugin_layers(self):
        definitions = {self._source_id(item): item for item in self.definitions}
        reload_veka = {}
        project = QgsProject.instance()
        for layer in list(project.mapLayers().values()):
            self._migrate_latvia_wfs_layer(layer)
            if (
                isinstance(layer, QgsRasterLayer)
                and layer.providerType() == "wms"
                and self._layer_source_id(layer)
                == f"WMS|{MAP_GRIDS}|ristkoordinaadid|"
            ):
                grid = next((item for item in self.definitions if (
                    item.code == "KV" and item.url == MAP_GRIDS
                    and item.layer_name == "epk_50T"
                )), None)
                if grid:
                    opacity = layer.opacity()
                    layer.setDataSource(
                        self._wms_uri(grid), self.display_name(grid), "wms"
                    )
                    layer.setOpacity(opacity)
                    layer.setCustomProperty(self.SOURCE_PROPERTY, self._source_id(grid))
            search_code = str(
                layer.customProperty(self.SEARCH_DEFINITION_PROPERTY, "")
            )
            definition = next(
                (item for item in self.definitions if item.code == search_code),
                None,
            ) if search_code else definitions.get(self._layer_source_id(layer))
            adopted = False
            if not definition:
                definition = self._definition_from_wfs_source(layer)
                adopted = definition is not None
            if not definition:
                continue
            if definition.role == "sarv_points":
                # The three actual point layers share the SK definition but
                # retain different roles and source fields.
                self._apply_layer_map_labeling(layer)
                continue
            if definition.role == "veka_boreholes" and not self._veka_rows:
                # A memory layer restored from a project does not rebuild the
                # related-data indexes needed by VEKA filters and styling.
                # Replace it with a fresh API-backed layer once per source.
                reload_veka[self._source_id(definition)] = definition
                project.removeMapLayer(layer.id())
                continue
            if adopted and not search_code:
                # Older projects can contain a Qeoloog WFS layer whose custom
                # properties were not persisted. Re-associate only an exact
                # service URL + typename match, then restore the plugin style.
                layer.setCustomProperty(
                    self.SOURCE_PROPERTY, self._source_id(definition)
                )
                layer.setCustomProperty(self.ROLE_PROPERTY, definition.role)
            layer.setCustomProperty(self.ROLE_PROPERTY, definition.role)
            self._apply_definition_renderer(layer, definition)
            self._apply_layer_workarounds(layer, definition)
            if definition.role == "veka_boreholes":
                self._apply_layer_map_labeling(layer)
        for definition in reload_veka.values():
            QTimer.singleShot(
                0, lambda item=definition: self._add_veka_layer(item, True)
            )
        self.sync_dropdown_checks()
        self._ensure_egt_points_on_top()

    @staticmethod
    def _migrate_latvia_source_uri(source):
        """Replace only known proxy URIs before QGIS opens a stored provider."""
        if LEGACY_LATVIA_INSPIRE_GEOLOGY_WFS not in source:
            return source
        uri = QgsDataSourceUri(source)
        if is_legacy_latvia_wfs(uri.param("url"), uri.param("typename")):
            uri.removeParam("url")
            uri.setParam("url", LATVIA_INSPIRE_GEOLOGY_WFS)
            return uri.uri(False)
        return source

    def _migrate_latvia_wfs_layer(self, layer):
        """Repair stored proxy URIs in-place, retaining node/id/name/filter/opacity."""
        if not isinstance(layer, QgsVectorLayer) or layer.providerType() != "WFS":
            return False
        uri = QgsDataSourceUri(layer.source())
        name = uri.param("typename")
        legacy_uri = is_legacy_latvia_wfs(uri.param("url"), name)
        stored = str(layer.customProperty(self.SOURCE_PROPERTY, "")).split("|", 3)
        legacy_tag = len(stored) >= 3 and is_legacy_latvia_wfs(stored[1], stored[2], stored[0])
        if not legacy_uri and not (legacy_tag and uri.param("url") == LATVIA_INSPIRE_GEOLOGY_WFS):
            return False
        definition = next((item for item in self.definitions if (
            item.layer_name == name and item.url == LATVIA_INSPIRE_GEOLOGY_WFS
            and item.protocol.upper() == "WFS"
        )), None)
        if definition is None:
            return False
        if legacy_uri:
            subset, opacity = layer.subsetString(), layer.opacity()
            canvas = self.iface.mapCanvas()
            was_frozen = canvas.isFrozen()
            canvas_layers = canvas.layers()
            canvas.freeze(True)
            canvas.stopRendering()
            canvas.setLayers([item for item in canvas_layers if item is not layer])
            try:
                # WFS initialization runs a nested event loop. A canvas
                # refresh already queued before freeze() can otherwise access
                # the half-replaced provider, so exclude it temporarily too.
                layer.setDataSource(self._wfs_uri(definition, subset), layer.name(), "WFS")
                layer.setOpacity(opacity)
            finally:
                canvas.setLayers(canvas_layers)
                canvas.freeze(was_frozen)
                if not was_frozen:
                    canvas.refresh()
        layer.setCustomProperty(self.SOURCE_PROPERTY, self._source_id(definition))
        layer.setCustomProperty(self.ROLE_PROPERTY, definition.role)
        if layer.isValid():
            self._apply_definition_renderer(layer, definition)
        else:
            self.warning(f"{self.display_name(definition)}: " + self.t("Kihi laadimine ebaõnnestus."))
        return True

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
            and definition.menu_group.casefold() == "gtk"
            and "ignoregetmapurl" not in layer.source().casefold()
        ):
            # Migrate GTK layers already stored in a project to the
            # dark-theme-safe legend request without requiring users to
            # remove and re-add them.
            opacity = layer.opacity()
            layer.setDataSource(
                self._wms_uri(definition), layer.name(), "wms"
            )
            layer.setOpacity(opacity)
            layer.setCustomProperty(
                self.SOURCE_PROPERTY, self._source_id(definition)
            )
            layer.setCustomProperty(self.ROLE_PROPERTY, definition.role)
        if (
            isinstance(layer, QgsRasterLayer)
            and definition.protocol.upper() == "WMS"
            and definition.layer_name == "ak_avamus_a_200t"
        ):
            # EGT GetMap contains western Saaremaa, but the layer-level
            # GetCapabilities bounding box is too narrow and QGIS clips to it.
            layer.setExtent(QgsRectangle(self.AK_CORRECTED_EXTENT))

    def _ensure_egt_points_on_top(self, preferred=None):
        if self._unloading:
            return
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        point_roles = {
            "boreholes", "observations", "veka_boreholes", "maaru_cores",
            "latvia_boreholes",
        }
        point_layers = [
            layer for layer in project.mapLayers().values()
            if self._layer_role(layer) in point_roles
        ]
        positions = {
            child.layerId(): index
            for index, child in enumerate(root.children())
            if hasattr(child, "layerId")
        }
        ordered = sorted(
            point_layers,
            key=lambda layer: positions.get(layer.id(), len(positions)),
        )
        if preferred in ordered:
            ordered.remove(preferred)
            ordered.insert(0, preferred)
        # Do not use takeChild() or reorderGroupLayers() here. Taking a node
        # out while a remote WFS provider is starting can make QGIS 4 delete
        # the provider layer, while reorderGroupLayers() can dereference a
        # stale QPointer during a plugin hot reload. Clone the tree node at
        # the target position and then delete only the old tree node; the
        # QgsMapLayer and its provider stay owned by QgsProject.
        for layer in reversed(ordered):
            node = root.findLayer(layer.id())
            if node is None or node.parent() is None:
                continue
            if node.parent() is root and root.children() and root.children()[0] is node:
                continue
            clone = node.clone()
            if clone is None:
                continue
            parent = node.parent()
            root.insertChildNode(0, clone)
            parent.removeChildNode(node)

    def _apply_definition_renderer(self, layer, definition):
        """Restore the built-in renderer that belongs to a managed layer."""
        if not isinstance(layer, QgsVectorLayer):
            return
        if definition.role == "geophysics_fieldwork":
            self._apply_geophysics_method_renderer(layer)
        elif definition.role in self.MINERAL_LAYER_ROLES:
            self._apply_mineral_resource_renderer(layer, definition.role)
        elif definition.role == "archive_survey_areas":
            symbol = QgsFillSymbol.createSimple({
                "style": "no",
                "outline_color": definition.color,
                "outline_width": "0.75",
            })
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.triggerRepaint()
        elif definition.role == "engineering_geology_points":
            symbol = QgsMarkerSymbol.createSimple({
                "name": "diamond",
                "color": definition.color,
                "outline_color": "#4d4037",
                "outline_width": "0.3",
                "size": "2.6",
            })
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.triggerRepaint()
        elif definition.role.startswith("latvia_"):
            self._apply_latvia_renderer(layer, definition)
        elif definition.role in {"boreholes", "observations"}:
            self._apply_category_renderer(layer, self._archive_spatial_expression(layer, definition.role))
            if definition.role == "boreholes":
                self._apply_borehole_labeling(layer)
            else:
                self._apply_observation_labeling(layer)
            self._schedule_egt_label_refresh()

    def _apply_latvia_renderer(self, layer, definition):
        """Apply stable Qeoloog symbols to Latvia's public vector layers."""
        role = definition.role
        if role in {"latvia_faults", "latvia_seismic_profiles"}:
            symbol = QgsLineSymbol.createSimple({
                "color": definition.color,
                "width": "0.7" if role == "latvia_faults" else "0.55",
                "line_style": "solid" if role == "latvia_faults" else "dash",
            })
        elif role in {
            "latvia_karst", "latvia_groundwater",
            "latvia_mining_licences", "latvia_extraction_limits",
        }:
            properties = {
                "color": definition.color,
                "outline_color": definition.color,
                "outline_width": "0.55",
            }
            if role in {"latvia_mining_licences", "latvia_extraction_limits"}:
                properties["style"] = "no"
                properties["outline_style"] = (
                    "solid" if role == "latvia_mining_licences" else "dash"
                )
            symbol = QgsFillSymbol.createSimple(properties)
            if role == "latvia_karst":
                symbol.setOpacity(0.38)
            elif role == "latvia_groundwater":
                symbol.setOpacity(0.28)
        elif role == "latvia_mineral_deposits":
            symbol = QgsMarkerSymbol.createSimple({
                "name": "diamond", "color": definition.color,
                "outline_color": "#5a4630", "outline_width": "0.3",
                "size": "2.8",
            })
        else:
            # The ArcGIS borehole layer already carries LVĢMC's
            # purpose-based renderer. Keep the source legend intact.
            return
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()

    def _apply_geophysics_method_renderer(self, layer):
        """Keep the geophysical fieldwork legend categorized by method."""
        field_name = "geofys_meetod"
        field_index = layer.fields().indexOf(field_name)
        if field_index < 0:
            return False

        current = layer.renderer()
        if (
            isinstance(current, QgsCategorizedSymbolRenderer)
            and str(current.classAttribute()).strip().casefold()
            == field_name.casefold()
            and current.categories()
        ):
            layer.setCustomProperty(
                "qeoloog/geophysics_method_legend", True
            )
            return True

        options = value_map_options(
            layer.editorWidgetSetup(field_index).config()
        )
        if not options:
            options = [
                (1, "Georadar"),
                (2, "tTEM"),
                (3, "Seismomeetria"),
                (997, "Määra meetod"),
            ]

        preferred_colors = {
            "1": "#bee777",
            "2": "#e02f46",
            "3": "#11c8b0",
            "997": "#8f8f8f",
        }
        fallback_colors = (
            "#5577aa", "#e69f00", "#8a60b0", "#009e73",
            "#cc79a7", "#56b4e9", "#d55e00",
        )
        categories = []
        seen = set()
        for code, label in options:
            key = (type(code).__name__, str(code))
            if key in seen:
                continue
            seen.add(key)
            color = preferred_colors.get(
                str(code), fallback_colors[len(categories) % len(fallback_colors)]
            )
            symbol = QgsLineSymbol.createSimple({
                "line_color": color,
                "line_width": "0.8",
            })
            categories.append(QgsRendererCategory(code, symbol, label))

        other_symbol = QgsLineSymbol.createSimple({
            "line_color": "#8f8f8f",
            "line_width": "0.65",
            "line_style": "dash",
        })
        categories.append(QgsRendererCategory(
            None, other_symbol, self.t("Määramata")
        ))
        layer.setRenderer(QgsCategorizedSymbolRenderer(
            field_name, categories
        ))
        layer.setCustomProperty(
            "qeoloog/geophysics_method_legend", True
        )
        layer.triggerRepaint()
        layer.emitStyleChanged()
        return True

    def _apply_mineral_resource_renderer(self, layer, role):
        """Group the three mineral-register polygon layers by resource."""
        field = {
            "mineral_deposits": "maavara",
            "mining_claims": "pohimaavara",
            "exploration_areas": "maavarad",
        }.get(role, "")
        if not field or layer.fields().indexOf(field) < 0:
            return

        opacity = {
            "mineral_deposits": 0.42,
            "mining_claims": 0.66,
            "exploration_areas": 1.0,
        }[role]
        outline_width = (
            0.75 if role == "exploration_areas"
            else 0.55 if role == "mining_claims" else 0.35
        )
        normalized = f'lower(trim(coalesce("{field}", \'\')))'
        known = ", ".join(
            "'" + value.replace("'", "''") + "'"
            for value, _label, _color in self.MINERAL_RESOURCE_CLASSES
        )
        root_rule = QgsRuleBasedRenderer.Rule(None)
        for value, label, color in self.MINERAL_RESOURCE_CLASSES:
            properties = {
                "color": color,
                "outline_color": "#4d4d4d",
                "outline_width": str(outline_width),
            }
            if role == "exploration_areas":
                properties.update({
                    "style": "no",
                    "outline_color": color,
                })
            symbol = QgsFillSymbol.createSimple(properties)
            symbol.setOpacity(opacity)
            rule = QgsRuleBasedRenderer.Rule(symbol)
            rule.setLabel(self.t(label))
            rule.setFilterExpression(f"{normalized} = '{value}'")
            root_rule.appendChild(rule)

        if role == "exploration_areas":
            symbol = QgsFillSymbol.createSimple({
                "style": "no",
                "outline_color": "#c99545",
                "outline_width": str(outline_width),
            })
            symbol.setOpacity(opacity)
            rule = QgsRuleBasedRenderer.Rule(symbol)
            rule.setLabel(self.t("Mitu maavara"))
            rule.setFilterExpression(f"strpos({normalized}, ',') > 0")
            root_rule.appendChild(rule)
            other_expression = (
                f"strpos({normalized}, ',') = 0 AND "
                f"{normalized} NOT IN ({known})"
            )
        else:
            other_expression = f"{normalized} NOT IN ({known})"

        other_properties = {
            "color": "#9b9b9b",
            "outline_color": "#4d4d4d",
            "outline_width": str(outline_width),
        }
        if role == "exploration_areas":
            other_properties.update({
                "style": "no",
                "outline_color": "#9b9b9b",
            })
        symbol = QgsFillSymbol.createSimple(other_properties)
        symbol.setOpacity(opacity)
        rule = QgsRuleBasedRenderer.Rule(symbol)
        rule.setLabel(self.t("Muu / teadmata"))
        rule.setFilterExpression(other_expression)
        root_rule.appendChild(rule)
        layer.setRenderer(QgsRuleBasedRenderer(root_rule))
        layer.triggerRepaint()

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

    def _apply_borehole_labeling(self, layer):
        self._apply_egt_labeling(layer, "boreholes")

    def _refresh_map_labeling(self, *_args):
        if getattr(self, "_unloading", False):
            return
        for layer in QgsProject.instance().mapLayers().values():
            self._apply_layer_map_labeling(layer)

    def _restore_sarv_point_role(self, layer):
        # Older releases could save the SK group role on an individual layer.
        index = layer.fields().indexOf("source_type")
        if index < 0:
            return ""
        request = QgsFeatureRequest().setLimit(1)
        request.setFlags(QgsFeatureRequest.Flag.NoGeometry).setSubsetOfAttributes([index])
        first = next(layer.getFeatures(request), None)
        source_type = first.attribute(index) if first is not None else None
        if not isinstance(source_type, str):
            return ""
        role = {
            "locality": "sarv_localities", "site": "sarv_sites",
            "drillcore": "sarv_drillcores",
        }.get(source_type, "")
        if role:
            layer.setCustomProperty(self.ROLE_PROPERTY, role)
        return role

    def _apply_layer_map_labeling(self, layer):
        if not isinstance(layer, QgsVectorLayer) or (
            layer.geometryType() != Qgis.GeometryType.Point
        ):
            return
        role = self._layer_role(layer)
        if role == "sarv_points":
            role = self._restore_sarv_point_role(layer)
        if role == "boreholes":
            self._apply_borehole_labeling(layer)
        elif role == "observations":
            self._apply_observation_labeling(layer)
        elif role in {"faktika", "field_mapping"}:
            self._apply_egt_labeling(layer, role)
        elif role in {
            "veka_boreholes", "sarv_localities", "sarv_sites", "sarv_drillcores",
        }:
            self._apply_external_labeling(layer, role)

    def _apply_external_labeling(self, layer, role):
        settings_role = "veka_boreholes" if role == "veka_boreholes" else "sarv"
        selected = getattr(self, "egt_label_fields", DEFAULT_MAP_LABEL_FIELDS).get(
            settings_role, DEFAULT_MAP_LABEL_FIELDS[settings_role]
        )
        language = getattr(self, "language", "et")
        expression = join_label_components(
            label_component(
                layer.fields(), role, key, language=language,
                translate=lambda caption: translate(caption, language),
            )
            for key in MAP_LABEL_KEYS_BY_ROLE[settings_role] if key in selected
        )
        if expression:
            self._apply_name_labeling(layer, expression=expression)
        else:
            layer.setLabelsEnabled(False)
            layer.triggerRepaint()

    def _apply_loaded_portal_egt_labeling(self):
        """Apply shared EGT label settings to authenticated point workspaces."""
        if getattr(self, "_unloading", False):
            return
        for role in ("faktika", "field_mapping"):
            for layer in self._role_layers(role):
                if (
                    isinstance(layer, QgsVectorLayer)
                    and layer.geometryType() == Qgis.GeometryType.Point
                ):
                    self._apply_egt_labeling(layer, role)
        self._schedule_egt_label_refresh()

    def _index_thickness_label_values(self):
        if not self.dock:
            return {}
        requirements = self.dock.filters.stratigraphic_requirements()
        key = (
            tuple(sorted(requirements["indices"])),
            requirements["contains"].casefold(),
        )
        if (
            not requirements.get("show_thickness")
            or self._egt_stratigraphic_thickness_key != key
        ):
            return {}

        return stratigraphic_thickness_label_items(
            self._egt_stratigraphic_thicknesses,
            decimal_comma=self.language == "et",
        )

    def _apply_observation_labeling(self, layer):
        # Preserve the earlier project-stored 0.5 m lookup as an immediate
        # fallback while the richer visible-extent summaries are loading.
        variable = "qeoloog_observation_labels"
        # Reuse labels saved with the project while the fresh WFS lookup is
        # loading. JSON is constant-folded by QGIS during expression.prepare(),
        # so a map redraw does not reparse it for every observation point.
        if getattr(self, "_observation_labels_loaded", False):
            values = getattr(self, "_observation_labels", {})
        else:
            saved = QgsExpressionContextUtils.layerScope(layer).variable(variable)
            try:
                values = json.loads(saved or "{}")
            except (TypeError, ValueError):
                values = {}
            if not isinstance(values, dict):
                values = {}
            values.update(getattr(self, "_observation_labels", {}))
        QgsExpressionContextUtils.setLayerVariable(
            layer, variable,
            json.dumps(values, ensure_ascii=False, separators=(",", ":")),
        )
        self._apply_egt_labeling(layer, "observations", legacy_values=values)

    @staticmethod
    def _qgis_string(value):
        return "'" + str(value).replace("'", "''") + "'"

    def _selected_egt_label_fields(self, role):
        configured = getattr(
            self, "egt_label_fields", DEFAULT_EGT_LABEL_FIELDS
        )
        if role == "field_mapping":
            role = "observations"
        if role == "faktika":
            selected = set(configured.get(
                "boreholes", DEFAULT_EGT_LABEL_FIELDS["boreholes"]
            ))
            selected.update(configured.get(
                "observations", DEFAULT_EGT_LABEL_FIELDS["observations"]
            ))
            return [key for key in EGT_LABEL_FIELD_KEYS if key in selected]
        return [
            key for key in EGT_LABEL_KEYS_BY_ROLE[role]
            if key in configured.get(role, DEFAULT_EGT_LABEL_FIELDS[role])
        ]

    def _label_number(self, value):
        try:
            text = f"{float(value):.2f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return ""
        if getattr(self, "language", "et") == "et":
            text = text.replace(".", ",")
        return f"{text} m"

    def _display_egt_label_details(self, role, layer, legacy_values=None):
        variable = "qeoloog_egt_label_details"
        saved = QgsExpressionContextUtils.layerScope(layer).variable(variable)
        try:
            values = json.loads(saved or "{}")
        except (TypeError, ValueError):
            values = {}
        if not isinstance(values, dict):
            values = {}

        details_by_role = getattr(self, "_egt_map_label_details", {})
        loaded_by_role = getattr(self, "_egt_map_label_loaded_ids", {})
        details = details_by_role.get(role, {})
        loaded = loaded_by_role.get(role, set())
        for object_id in loaded:
            summary = details.get(object_id)
            if not summary:
                values.pop(object_id, None)
                continue
            item = {}
            if "cover_thickness" in summary:
                item["cover_thickness"] = self._label_number(
                    summary["cover_thickness"]
                )
            if "bedrock_elevation" in summary:
                item["bedrock_elevation"] = self._label_number(
                    summary["bedrock_elevation"]
                )
            for key in ("depth_0_5", "bedrock_outcrop"):
                if summary.get(key):
                    item[key] = str(summary[key])
            if item:
                values[object_id] = item
            else:
                values.pop(object_id, None)

        QgsExpressionContextUtils.setLayerVariable(
            layer, variable,
            json.dumps(values, ensure_ascii=False, separators=(",", ":")),
        )
        return variable

    def _apply_egt_labeling(self, layer, role, legacy_values=None):
        selected = self._selected_egt_label_fields(role)
        borehole_selected = set(self._selected_egt_label_fields("boreholes"))
        observation_selected = set(
            self._selected_egt_label_fields("observations")
        )

        def for_object_type(expression, key):
            if role != "faktika" or layer.fields().indexOf("objekti_tyyp") < 0:
                return expression
            borehole = key in borehole_selected
            observation = key in observation_selected
            if borehole and observation:
                return expression
            if borehole:
                return f'if(to_int("objekti_tyyp") = 1, {expression}, \'\')'
            if observation:
                return f'if(to_int("objekti_tyyp") <> 1, {expression}, \'\')'
            return "''"

        language = getattr(self, "language", "et")

        def label_text(text):
            return translate(text, language)
        id_field = next((
            name for name in ("esri_globalid", "globalid")
            if layer.fields().indexOf(name) >= 0
        ), "")
        variable = self._display_egt_label_details(
            role, layer, legacy_values=legacy_values
        )
        item_expression = (
            f"map_get(from_json(@{variable}), "
            f"upper(trim(to_string(\"{id_field}\"))))"
            if id_field else "from_json('{}')"
        )
        components = []
        for key in ("name", "alias", "borehole_depth"):
            if key not in selected:
                continue
            if (
                key == "borehole_depth" and role == "faktika"
                and layer.fields().indexOf("objekti_tyyp") < 0
                and (key in borehole_selected) != (key in observation_selected)
            ):
                continue
            component = label_component(
                layer.fields(), role, key, language=language, translate=label_text,
            )
            if component:
                components.append(for_object_type(component, key))
        prefixes = {
            "cover_thickness": "PP: ",
            "bedrock_elevation": "APR: ",
            "depth_0_5": f"{label_text('0,5 m')}: ",
            "bedrock_outcrop": "AP: ",
        }
        for key in EGT_LABEL_FIELD_KEYS:
            if key not in selected or key not in prefixes:
                continue
            if role == "observations" and key == "depth_0_5" and id_field:
                value = (
                    "coalesce(to_string(map_get(@qeoloog_label_item, "
                    "'depth_0_5')), to_string(map_get("
                    "from_json(@qeoloog_observation_labels), "
                    f"upper(trim(to_string(\"{id_field}\"))))), '')"
                )
            else:
                value = (
                    f"coalesce(to_string(map_get(@qeoloog_label_item, "
                    f"'{key}')), '')"
                )
            components.append(for_object_type(
                f"if({value} = '', '', "
                f"{self._qgis_string(prefixes[key])} || {value})",
                key,
            ))

        if role == "boreholes":
            thickness_values = self._index_thickness_label_values()
            QgsExpressionContextUtils.setLayerVariable(
                layer, "qeoloog_index_thickness_labels",
                json.dumps(
                    thickness_values, ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            if thickness_values and id_field:
                # The stratigraphic-filter thickness label has always retained
                # the original borehole name, even if Name is otherwise off.
                if (
                    layer.fields().indexOf("nimi") >= 0
                    and "name" not in selected
                ):
                    components.insert(
                        0, "trim(coalesce(to_string(\"nimi\"), ''))"
                    )
                depth_fields = [
                    name for name in (
                        "pikkus", "vertikaalne_ulatus", "sygavus"
                    ) if layer.fields().indexOf(name) >= 0
                ]
                depth_expression = "NULL"
                if depth_fields:
                    depths = [f'to_real("{name}")' for name in depth_fields]
                    depth_expression = (
                        depths[0] if len(depths) == 1
                        else f"coalesce({', '.join(depths)})"
                    )
                components.append(
                    "with_variable('qeoloog_index_thickness_items', "
                    "map_get(from_json(@qeoloog_index_thickness_labels), "
                    f"upper(to_string(\"{id_field}\"))), "
                    "with_variable('qeoloog_hole_depth', "
                    f"{depth_expression}, if("
                    "@qeoloog_index_thickness_items IS NULL, '', "
                    "array_to_string(array_foreach("
                    "@qeoloog_index_thickness_items, "
                    "map_get(@element, 'text') || if("
                    "@qeoloog_hole_depth IS NOT NULL AND "
                    "map_get(@element, 'bottom') IS NOT NULL AND "
                    "abs(@qeoloog_hole_depth - "
                    "to_real(map_get(@element, 'bottom'))) <= 0.05, "
                    "'+', '')), '; '))))"
                )

        if not components:
            layer.setLabelsEnabled(False)
            layer.triggerRepaint()
            return
        expression = (
            "with_variable('qeoloog_label_item', "
            f"{item_expression}, {join_label_components(components)})"
        )
        self._apply_name_labeling(layer, id_field or "nimi", expression)

    @staticmethod
    def _egt_label_details_required(fields):
        return bool(set(fields).intersection({
            "cover_thickness", "bedrock_elevation", "depth_0_5",
            "bedrock_outcrop",
        }))

    def _schedule_egt_label_refresh(self, *args):
        if getattr(self, "_unloading", False):
            return
        if not any(
            self._egt_label_details_required(
                self._selected_egt_label_fields(role)
            ) for role in ("boreholes", "observations")
        ):
            return
        timer = getattr(self, "_egt_label_refresh_timer", None)
        if timer is not None:
            timer.start()

    def _visible_egt_label_ids(self, role, limit=2500):
        canvas = self.iface.mapCanvas()
        result = set()
        for layer in self._role_layers(role):
            node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
            if node and not node.isVisible():
                continue
            id_field = next((
                name for name in ("esri_globalid", "globalid")
                if layer.fields().indexOf(name) >= 0
            ), "")
            if not id_field:
                continue
            try:
                extent = QgsCoordinateTransform(
                    canvas.mapSettings().destinationCrs(), layer.crs(),
                    QgsProject.instance(),
                ).transformBoundingBox(canvas.extent())
                request = QgsFeatureRequest().setFilterRect(extent)
                request.setSubsetOfAttributes([id_field], layer.fields())
                request.setLimit(limit)
                for feature in layer.getFeatures(request):
                    value = str(feature.attribute(id_field) or "").strip().upper()
                    if value:
                        result.add(value)
                    if len(result) >= limit:
                        break
            except (QgsCsException, RuntimeError, ValueError):
                continue
            if len(result) >= limit:
                break
        return result

    def _visible_portal_label_objects(self, layer, limit=1500):
        """Return visible parent GUIDs and PointZ elevations for one layer."""
        canvas = self.iface.mapCanvas()
        id_field = next((
            name for name in ("esri_globalid", "globalid", "GlobalID")
            if layer.fields().indexOf(name) >= 0
        ), "")
        if not id_field:
            return {}
        result = {}
        try:
            extent = QgsCoordinateTransform(
                canvas.mapSettings().destinationCrs(), layer.crs(),
                QgsProject.instance(),
            ).transformBoundingBox(canvas.extent())
            request = QgsFeatureRequest().setFilterRect(extent)
            request.setSubsetOfAttributes([id_field], layer.fields())
            request.setLimit(limit)
            for feature in layer.getFeatures(request):
                identifier = str(
                    feature.attribute(id_field) or ""
                ).strip().upper()
                if not identifier:
                    continue
                elevation = None
                try:
                    point = feature.geometry().constGet()
                    if point is not None and hasattr(point, "z"):
                        elevation = veka_number(point.z())
                except (AttributeError, TypeError, ValueError):
                    elevation = None
                result[identifier] = elevation
                if len(result) >= limit:
                    break
        except (QgsCsException, RuntimeError, ValueError):
            return {}
        return result

    @staticmethod
    def _portal_label_units(
        rows, metadata, *, sequential_bottoms=False, elevations=None,
    ):
        """Decode and group Portal intervals for labels and cross-sections."""
        grouped = {}
        for row in rows or ():
            parent = str(
                row.get("puurauk_vaatluspunkt_id")
                or row.get("vaatluspunkt_id") or ""
            ).strip().upper()
            if parent:
                grouped.setdefault(parent, []).append(row)
        result = {}
        elevation_values = elevations or {}
        for parent, source_rows in grouped.items():
            source_rows.sort(key=lambda row: (
                veka_number(row.get("z_suht_ylemine"))
                if not sequential_bottoms else
                veka_number(row.get("z_suht_alumine"))
            ) if (
                veka_number(row.get("z_suht_ylemine"))
                if not sequential_bottoms else
                veka_number(row.get("z_suht_alumine"))
            ) is not None else float("inf"))
            units = []
            next_top = 0.0
            for row in source_rows:
                unit = decode_coded_row(
                    metadata, row, preserve=("yksus_kood",),
                )
                if sequential_bottoms:
                    bottom = veka_number(row.get("z_suht_alumine"))
                    if bottom is None or bottom < next_top:
                        continue
                    top = next_top
                    unit["z_suht_ylemine"] = top
                    unit["z_suht_alumine"] = bottom
                    next_top = bottom
                else:
                    top = veka_number(unit.get("z_suht_ylemine"))
                if unit.get("klassif_yksus_kood") in (None, ""):
                    unit["klassif_yksus_kood"] = unit.get("yksus_kood")
                elevation = elevation_values.get(parent)
                if (
                    elevation is not None and top is not None
                    and unit.get("z_abs_ylemine") in (None, "")
                ):
                    unit["z_abs_ylemine"] = elevation - top
                units.append(unit)
            result[parent] = units
        return result

    def _refresh_portal_egt_label_data(self):
        """Load only visible authenticated intervals needed by map labels."""
        root = QgsProject.instance().layerTreeRoot()
        for role in ("faktika", "field_mapping"):
            if not self._egt_label_details_required(
                self._selected_egt_label_fields(role)
            ):
                continue
            for layer in self._role_layers(role):
                node = root.findLayer(layer.id())
                if node is not None and not node.isVisible():
                    continue
                objects = self._visible_portal_label_objects(layer)
                loaded = self._egt_map_label_loaded_ids[role]
                loading = self._egt_map_label_loading_ids[role]
                requested = set(sorted(
                    set(objects) - loaded - loading
                )[:120])
                if not requested:
                    continue
                loading.update(requested)
                elevations = {
                    key: objects.get(key) for key in requested
                }
                self._load_portal_egt_label_batch(
                    layer, role, requested, elevations,
                    self._egt_map_label_generation,
                )

    def _load_portal_egt_label_batch(
        self, layer, role, requested, elevations, generation,
    ):
        """Fetch one bounded related-table batch for Portal map labels."""
        def cancelled():
            return (
                getattr(self, "_unloading", False)
                or generation != self._egt_map_label_generation
            )

        def finished(grouped):
            if cancelled():
                return
            summaries = {
                parent: summary for parent, units in grouped.items()
                if (summary := egt_label_summary(units))
            }
            loading = self._egt_map_label_loading_ids[role]
            loading.difference_update(requested)
            self._egt_map_label_loaded_ids[role].update(requested)
            self._egt_map_label_details[role].update(summaries)
            for label_layer in self._role_layers(role):
                self._apply_egt_labeling(label_layer, role)
            self._schedule_egt_label_refresh()

        def failed(error):
            if cancelled():
                return
            self._egt_map_label_loading_ids[role].difference_update(requested)
            self._egt_map_label_loaded_ids[role].update(requested)
            self.warning(
                f"{self.t('EGT kaardisiltide laadimine ebaõnnestus')}: "
                f"{error}"
            )

        quoted = ",".join(
            f"'{escape_where(identifier)}'"
            for identifier in sorted(requested)
        )
        if role == "field_mapping":
            bundle = self.PORTAL_LAYER_BUNDLES["field_mapping"]

            def metadata_loaded(metadata):
                if cancelled():
                    return

                def rows_loaded(payload):
                    rows = self._faktika_records(payload)
                    finished(self._portal_label_units(
                        rows, metadata.get(1, {}),
                        sequential_bottoms=True, elevations=elevations,
                    ))

                self.network.query_arcgis_features(
                    bundle["url"], 1,
                    f"vaatluspunkt_id IN ({quoted})",
                    rows_loaded, failed,
                    authcfg=self.egt_portal_authcfg,
                    out_fields="*", return_geometry=False, return_z=False,
                    order_by="vaatluspunkt_id,z_suht_alumine",
                )

            self._ensure_portal_bundle_metadata(
                "field_mapping", metadata_loaded, failed,
            )
            return

        workspace_key = str(layer.customProperty(
            "qeoloog/faktika_workspace", "faktika"
        ))

        def metadata_loaded(metadata):
            if cancelled():
                return
            self._query_faktika_rows(
                6,
                f"puurauk_vaatluspunkt_id IN ({quoted})",
                lambda rows: finished(self._portal_label_units(
                    rows, metadata.get(6, {}), elevations=elevations,
                )),
                failed,
                order_by="puurauk_vaatluspunkt_id,z_suht_ylemine",
                workspace_key=workspace_key,
            )

        self._ensure_faktika_metadata(
            metadata_loaded, failed, workspace_key,
        )

    def _refresh_egt_map_label_data(self):
        if getattr(self, "_unloading", False):
            return
        for role in ("boreholes", "observations"):
            fields = self._selected_egt_label_fields(role)
            if not self._egt_label_details_required(fields):
                continue
            loaded = self._egt_map_label_loaded_ids[role]
            loading = self._egt_map_label_loading_ids[role]
            wanted = self._visible_egt_label_ids(role) - loaded - loading
            requested = set(sorted(wanted)[:400])
            if not requested:
                continue
            loading.update(requested)
            generation = self._egt_map_label_generation

            def cancelled(generation=generation):
                return (
                    getattr(self, "_unloading", False)
                    or generation != self._egt_map_label_generation
                )

            def loaded_values(
                values, role=role, requested=requested,
                is_cancelled=cancelled,
            ):
                if is_cancelled():
                    return
                self._egt_map_label_loading_ids[role].difference_update(requested)
                self._egt_map_label_loaded_ids[role].update(requested)
                self._egt_map_label_details[role].update(values)
                for label_layer in self._role_layers(role):
                    if role == "boreholes":
                        self._apply_borehole_labeling(label_layer)
                    else:
                        self._apply_observation_labeling(label_layer)
                self._schedule_egt_label_refresh()

            def failed(
                error, role=role, requested=requested,
                is_cancelled=cancelled,
            ):
                if is_cancelled():
                    return
                self._egt_map_label_loading_ids[role].difference_update(requested)
                self.warning(
                    f"{self.t('EGT kaardisiltide laadimine ebaõnnestus')}: "
                    f"{error}"
                )

            self.network.query_egt_label_details(
                role, requested, loaded_values, failed, cancelled=cancelled,
            )
        self._refresh_portal_egt_label_data()

    def _apply_name_labeling(self, layer, field_name="name", expression=""):
        if not expression and layer.fields().indexOf(field_name) < 0:
            return
        text_format = QgsTextFormat()
        text_format.setSize(getattr(self, "label_text_size", 5.0))
        text_format.setSizeUnit(Qgis.RenderUnit.Points)
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(0.6)
        buffer.setSizeUnit(Qgis.RenderUnit.Millimeters)
        buffer.setColor(QColor("white"))
        text_format.setBuffer(buffer)
        settings = QgsPalLayerSettings()
        settings.fieldName = expression or field_name
        settings.isExpression = bool(expression)
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
        show_thickness = bool(stratigraphic.get("show_thickness"))
        stratigraphic_expression = ""
        if stratigraphic_active:
            if self._egt_stratigraphic_filter_key == stratigraphic_key:
                stratigraphic_expression = self._id_membership_clause(
                    self._egt_stratigraphic_filter_allowed or set()
                )
            needs_filter = (
                self._egt_stratigraphic_filter_key != stratigraphic_key
            )
            needs_thickness = (
                show_thickness
                and self._egt_stratigraphic_thickness_key
                != stratigraphic_key
            )
            request_key = (stratigraphic_key, show_thickness)
            if (
                (needs_filter or needs_thickness)
                and self._egt_stratigraphic_filter_loading != request_key
            ):
                self._egt_stratigraphic_filter_generation += 1
                generation = self._egt_stratigraphic_filter_generation
                self._egt_stratigraphic_filter_loading = request_key

                def loaded_stratigraphy(values):
                    if generation != self._egt_stratigraphic_filter_generation:
                        return
                    self._egt_stratigraphic_filter_loading = None
                    self._egt_stratigraphic_filter_key = stratigraphic_key
                    if show_thickness:
                        self._egt_stratigraphic_filter_allowed = set(
                            values.get("parent_ids", set())
                        )
                        self._egt_stratigraphic_thickness_key = (
                            stratigraphic_key
                        )
                        self._egt_stratigraphic_thicknesses = dict(
                            values.get("thicknesses", {})
                        )
                    else:
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
                    include_thickness=show_thickness,
                )
            elif not needs_filter and not needs_thickness and (
                self._egt_stratigraphic_filter_loading is not None
            ):
                self._egt_stratigraphic_filter_generation += 1
                self._egt_stratigraphic_filter_loading = None
        else:
            if self._egt_stratigraphic_filter_loading is not None:
                self._egt_stratigraphic_filter_generation += 1
            self._egt_stratigraphic_filter_loading = None
            self._egt_stratigraphic_filter_key = None
            self._egt_stratigraphic_filter_allowed = None
            self._egt_stratigraphic_thickness_key = None
            self._egt_stratigraphic_thicknesses = {}

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
                        self._archive_spatial_expression(layer, role),
                    ) if expression
                ]
                local_expression = " AND ".join(
                    f"({expression})" for expression in local_expressions
                )
                layer.setSubsetString(category_expression)
                self._apply_category_renderer(layer, local_expression)
                if role == "boreholes":
                    self._apply_borehole_labeling(layer)
                elif role == "observations":
                    self._apply_observation_labeling(layer)
                    self._schedule_egt_label_refresh()
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
        parameter_codes = tuple(value for value in analysis_codes(key) if not value.startswith("legacy:"))
        _, _, target_unit = split_analysis_key(key)
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
            rows = merge_water_analyses(rows, [
                row for values in self._veka_legacy_analysis_rows.values() for row in values
            ])
            matching_rows = []
            for row in rows:
                value = analysis_row_value(row, key)
                if analysis_row_result(row, key) is None:
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
                options = veka_analysis_options(list(rows) + [
                    row for values in self._veka_legacy_analysis_rows.values() for row in values
                ])
                self.dock.veka.set_analysis_options(options)
                self.dock.export.set_veka_analysis_options(options)
                self.dock.veka.status.setText(
                    self.t("Veeproovi näitajad on valmis.")
                )

        self._ensure_veka_aux("analysis_catalog", ready)

    def _remember_veka_legacy_analyses(self, cadastral_number, rows):
        """Keep publicly viewed legacy results available to filters/exports."""
        self._veka_legacy_analysis_rows[str(cadastral_number)] = [
            dict(row, katastri_number=str(cadastral_number)) for row in rows
        ]
        # Recompute selected aggregates after new legacy evidence arrives.
        self._veka_analysis_rows.clear()
        self._veka_analysis_grouped.clear()
        if self.dock:
            options = veka_analysis_options(list(self._veka_aux.get("analysis_catalog") or []) + [
                row for values in self._veka_legacy_analysis_rows.values() for row in values
            ])
            self.dock.veka.set_analysis_options(options)
            self.dock.export.set_veka_analysis_options(options)

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
        usages = requirements["usages"]
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
            if usages:
                usage = veka_usage_value(row)
                usage_key = "" if usage in (None, "") else str(usage).strip()
                if usage_key not in usages:
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
            self._apply_external_labeling(layer, "veka_boreholes")
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

    def add_search_results_to_cross_section(self, rows):
        """Add selected searchable point results without opening each detail."""
        if not self.dock:
            return 0
        supported = {
            "boreholes", "observations", "sarv_drillcores",
            "sarv_localities", "sarv_sites", "veka_boreholes", "maaru_cores",
        }
        if getattr(self.dock.cross_sections, "workspace", None):
            supported.discard("maaru_cores")
        snapshots = []
        existing = {
            self.dock.cross_sections.item_key(item)
            for item in self.dock.cross_sections.items
        }
        for item in rows or ():
            role = str(item.get("_role") or "")
            if role not in supported:
                continue
            snapshot = None
            layer = QgsProject.instance().mapLayer(
                str(item.get("_layer_id") or "")
            )
            if layer is not None and item.get("_feature_id") is not None:
                try:
                    feature = layer.getFeature(int(item["_feature_id"]))
                    if feature.isValid():
                        snapshot = self._cross_section_snapshot_from_feature(
                            role, layer, feature,
                        )
                except (TypeError, ValueError, RuntimeError):
                    snapshot = None
            if role == "maaru_cores" and snapshot is None:
                identifier = str(
                    item.get("_maaru_id") or item.get("id") or ""
                )
                row = (
                    self._maaru_db.point(identifier)
                    if self._maaru_db is not None
                    and self._maaru_db.available and identifier else None
                )
                if row:
                    snapshot = {
                        "key": f"maaru_cores:{identifier}",
                        "role": "maaru_cores",
                        "source": "MaRu",
                        "id": identifier,
                        "maaru_id": identifier,
                        "name": (
                            row.get("nimetus") or row.get("number")
                            or row.get("uus_id") or identifier
                        ),
                        "x": row.get("_maaru_x"),
                        "y": row.get("_maaru_y"),
                        "elevation": row.get("z"),
                        "elevation_source": "MaRu",
                        "depth": row.get("sygavus"),
                        "units": [], "core_boxes": [],
                        "sarv_core_boxes": [], "samples": [],
                        "analyses": [], "sarv_samples": [],
                        "sarv_analyses": [], "sarv_specimens": [],
                        "veka_construction": [], "static_water": None,
                        "enabled": True,
                    }
            if not snapshot or snapshot.get("key") in existing:
                continue
            self.dock.cross_sections.add_snapshot(snapshot)
            existing.add(snapshot["key"])
            snapshots.append(snapshot)
        if snapshots:
            self._load_cross_section_profiles(snapshots)
            self.dock.show_cross_sections()
        return len(snapshots)

    def remove_cross_section_item(self, key):
        if self.dock:
            self.dock.cross_sections.remove_key(key)

    def start_cross_section_line(self):
        if not self.cross_section_line_tool:
            return
        canvas = self.iface.mapCanvas()
        if canvas.mapTool() is self.cross_section_line_tool:
            self.cross_section_line_tool.activate()
        else:
            self.cross_section_previous_tool = canvas.mapTool()
            canvas.setMapTool(self.cross_section_line_tool)
        self.message(
            "Point snapping is on. Click line vertices near boreholes. "
            "Right-click or Enter finishes."
            if self.language == "en" else
            "Puuraukude snapp on sisse lülitatud. Klõpsa joone tipud "
            "puuraukude lähedal. Paremklõps või Enter lõpetab."
        )

    def _cross_section_snap_layers(self):
        """Return visible point sources which can be added to a section."""
        roles = (
            "faktika", "field_mapping", "boreholes", "observations", "sarv_drillcores",
            "veka_boreholes", "maaru_cores", "sarv_localities", "sarv_sites",
        )
        if self.dock and getattr(self.dock.cross_sections, "workspace", None):
            roles = tuple(role for role in roles if role not in {
                "faktika", "field_mapping", "maaru_cores",
            })
        root = QgsProject.instance().layerTreeRoot()
        result = []
        for role in roles:
            for layer in self._role_layers(role):
                node = root.findLayer(layer.id())
                if (
                    layer.isValid()
                    and layer.geometryType() == Qgis.GeometryType.Point
                    and (node is None or node.isVisible())
                ):
                    result.append(layer)
        return result

    @staticmethod
    def _cross_section_optional_number(attributes, *keys):
        for key in keys:
            value = (attributes or {}).get(key)
            if value in (None, "", "NULL", "<NULL>"):
                continue
            parsed = veka_number(value)
            if parsed is not None:
                return parsed
        return None

    @classmethod
    def _cross_section_feature_identity(cls, role, attributes):
        """Return ``(identifier, display_name, source_id)`` for a point."""
        values = attributes or {}
        if role in {"boreholes", "observations", "field_mapping"}:
            source_id = values.get("esri_globalid") or values.get("globalid")
            identifier = source_id or values.get("gea_id")
            name = (
                values.get("nimi") or values.get("alias")
                or values.get("valitoo_id")
                or values.get("gea_id") or source_id
                or ("Puurauk" if role == "boreholes" else "Vaatluspunkt")
            )
        elif role == "veka_boreholes":
            source_id = values.get("eelis_id") or values.get("kkr_kood")
            identifier = source_id or values.get("nimi")
            name = values.get("nimi") or values.get("kkr_kood") or source_id
        elif role in {"sarv_drillcores", "sarv_localities", "sarv_sites"}:
            source_id = values.get("sarv_id") or values.get("id")
            identifier = source_id or values.get("number")
            name = values.get("name") or values.get("number") or source_id
        elif role == "maaru_cores":
            source_id = values.get("maaru_id") or values.get("id")
            identifier = source_id or values.get("uus_id")
            name = (
                values.get("nimi") or values.get("nimetus")
                or values.get("number") or values.get("uus_id") or source_id
            )
        else:
            source_id = values.get("id")
            identifier = source_id
            name = values.get("name") or source_id
        if identifier in (None, ""):
            return "", str(name or ""), source_id
        return str(identifier), str(name or identifier), source_id

    @staticmethod
    def _cross_section_source_label(role):
        return {
            "boreholes": "EGT PA",
            "observations": "EGT VP",
            "field_mapping": "EGT välitöö",
            "veka_boreholes": "VEKA",
            "sarv_drillcores": "SARV",
            "sarv_localities": "SARV",
            "sarv_sites": "SARV",
            "maaru_cores": "MaRu",
        }.get(role, role)

    def _cross_section_snapshot_from_feature(self, role, layer, feature):
        """Create a lightweight snapshot from a visible point feature.

        Detailed EGT/VEKA intervals are filled asynchronously after the line
        is shown.  Keeping the initial snapshot small is important for WFS
        layers and means the canvas never waits for a second network roundtrip.
        """
        attributes = {
            field.name(): feature.attribute(field.name())
            for field in layer.fields()
        }
        attributes = self._detail_attributes_with_location(
            attributes, layer, feature
        )
        faktika_source = role == "faktika"
        if role == "faktika":
            try:
                object_type = int(attributes.get("objekti_tyyp") or 2)
            except (TypeError, ValueError):
                object_type = 2
            role = "boreholes" if object_type == 1 else "observations"
        identifier, name, source_id = self._cross_section_feature_identity(
            role, attributes
        )
        if not identifier:
            return None
        x = self._cross_section_optional_number(
            attributes, "_qeoloog_x_3301", "kesk_x"
        )
        y = self._cross_section_optional_number(
            attributes, "_qeoloog_y_3301", "kesk_y"
        )
        elevation = self._cross_section_optional_number(
            attributes, "z_abs", "elevation", "altitude", "height",
            "maapinna_abs_korgus", "absoluutkorgus",
        )
        depth = self._cross_section_optional_number(
            attributes, "pikkus", "vertikaalne_ulatus", "depth", "sygavus",
            "puurimissugavus",
        )
        key = f"{role}:{identifier}"
        snapshot = {
            "key": key,
            "role": role,
            "source": self._cross_section_source_label(role),
            "id": identifier,
            "name": name,
            "x": x,
            "y": y,
            "elevation": elevation,
            "elevation_source": (
                "WFS PointZ" if attributes.get("z_abs") not in (None, "")
                else ""
            ),
            "depth": depth,
            "units": [],
            "core_boxes": [],
            "sarv_core_boxes": [],
            "samples": [],
            "analyses": [],
            "sarv_samples": [],
            "sarv_analyses": [],
            "sarv_specimens": [],
            "veka_construction": [],
            "static_water": None,
            "enabled": True,
            "faktika": faktika_source,
            "faktika_workspace": (
                str(layer.customProperty(
                    "qeoloog/faktika_workspace", "faktika"
                )) if faktika_source else ""
            ),
        }
        if role in {"boreholes", "observations", "field_mapping"}:
            snapshot["global_id"] = str(source_id or "")
        elif role == "veka_boreholes":
            snapshot["eelis_id"] = str(source_id or identifier)
        elif role in {"sarv_drillcores", "sarv_localities", "sarv_sites"}:
            snapshot["sarv_id"] = str(source_id or identifier)
        elif role == "maaru_cores":
            snapshot["maaru_id"] = str(source_id or identifier)
        from .section_workspace_ui import section_source_ref
        ref = section_source_ref(snapshot, attributes)
        if ref:
            snapshot["source_ref"] = ref
        return snapshot

    def _auto_add_cross_section_objects(self, line):
        """Add visible point objects inside the drawn section corridor."""
        if not self.dock or len(line or ()) < 2:
            return 0
        try:
            metric = QgsCoordinateReferenceSystem("EPSG:3301")
            line_geometry = QgsGeometry.fromPolylineXY([
                QgsPointXY(float(x), float(y)) for x, y in line
            ])
            corridor = line_geometry.buffer(
                self.CROSS_SECTION_AUTO_ADD_TOLERANCE_M, 8
            )
        except (TypeError, ValueError, QgsCsException):
            return 0
        if corridor.isEmpty():
            return 0

        project = QgsProject.instance()
        candidates = []
        seen = {
            self.dock.cross_sections.item_key(item)
            for item in self.dock.cross_sections.items
        }
        for layer in self._cross_section_snap_layers():
            role = self._layer_role(layer)
            try:
                to_layer = QgsCoordinateTransform(metric, layer.crs(), project)
                query_geometry = QgsGeometry(corridor)
                query_geometry.transform(to_layer)
                request = QgsFeatureRequest().setFilterRect(
                    query_geometry.boundingBox()
                )
                request.setLimit(self.CROSS_SECTION_AUTO_ADD_MAX)
                to_metric = QgsCoordinateTransform(
                    layer.crs(), metric, project
                )
                for feature in layer.getFeatures(request):
                    attributes = {
                        field.name(): feature.attribute(field.name())
                        for field in layer.fields()
                    }
                    if (
                        role in {"boreholes", "observations"}
                        and (not self._passes_related_filter(attributes, role)
                             or not self._passes_archive_report_filter(layer, feature))
                    ):
                        continue
                    if not feature.hasGeometry():
                        continue
                    geometry = QgsGeometry(feature.geometry())
                    geometry.transform(to_metric)
                    if geometry.isEmpty():
                        continue
                    point = geometry.asPoint()
                    if point.isEmpty():
                        point = geometry.centroid().asPoint()
                    if point.isEmpty():
                        continue
                    point_geometry = QgsGeometry.fromPointXY(
                        QgsPointXY(point.x(), point.y())
                    )
                    distance = line_geometry.distance(point_geometry)
                    if distance > self.CROSS_SECTION_AUTO_ADD_TOLERANCE_M + 1e-6:
                        continue
                    snapshot = self._cross_section_snapshot_from_feature(
                        role, layer, feature
                    )
                    if not snapshot or snapshot["key"] in seen:
                        continue
                    snapshot["_corridor_distance"] = float(distance)
                    candidates.append(snapshot)
                    seen.add(snapshot["key"])
            except (QgsCsException, TypeError, ValueError, RuntimeError):
                continue

        candidates.sort(key=lambda item: (
            item.get("_corridor_distance", 0.0),
            str(item.get("name") or "").casefold(),
        ))
        candidates = candidates[: self.CROSS_SECTION_AUTO_ADD_MAX]
        if getattr(self.dock.cross_sections, "workspace", None):
            self.dock.cross_sections.add_nearby_local_logs(
                line, self.CROSS_SECTION_AUTO_ADD_TOLERANCE_M,
            )
        for snapshot in candidates:
            snapshot.pop("_corridor_distance", None)
            self.dock.cross_sections.add_snapshot(snapshot)
        if candidates:
            self._load_cross_section_profiles(candidates)
            message = (
                f"Added {len(candidates)} nearby point objects to the section "
                f"(corridor {self.CROSS_SECTION_AUTO_ADD_TOLERANCE_M:g} m)."
                if self.language == "en" else
                f"Läbilõikele lisati {len(candidates)} lähedast objekti "
                f"({self.CROSS_SECTION_AUTO_ADD_TOLERANCE_M:g} m koridor)."
            )
            self.message(message)
        return len(candidates)

    def _load_cross_section_profiles(self, snapshots):
        """Fill EGT/VEKA interval data after automatic object selection."""
        for snapshot in snapshots:
            if self.dock:
                snapshot = dict(snapshot, _section_serial=self.dock.cross_sections._workspace_serial)
            role = snapshot.get("role")
            if snapshot.get("faktika"):
                self._load_cross_section_faktika_profile(snapshot)
            elif role == "field_mapping":
                self._load_cross_section_field_mapping_profile(snapshot)
            elif role in {"boreholes", "observations"}:
                self._load_cross_section_egt_profile(snapshot)
            elif role == "veka_boreholes":
                self._load_cross_section_veka_profile(snapshot)
            elif role == "maaru_cores":
                self._load_cross_section_maaru_profile(snapshot)

    def _merge_cross_section_profile(self, snapshot, units):
        if not self.dock or not isinstance(units, list):
            return
        updates = {"units": units}
        depth = max((
            self._cross_section_optional_number(
                unit, "z_suht_alumine", "lamam", "depth", "sygavus"
            )
            for unit in units
        ), default=None)
        if depth is not None and self._cross_section_optional_number(
            snapshot, "depth"
        ) is None:
            updates["depth"] = depth
        self.dock.cross_sections.update_snapshot(
            snapshot.get("key"), updates, serial=snapshot.get("_section_serial"),
        )

    def _load_cross_section_maaru_profile(self, snapshot):
        identifier = str(snapshot.get("maaru_id") or snapshot.get("id") or "")
        if not identifier:
            return

        def ready(database):
            row = database.point(identifier)
            if not row:
                return
            related = database.related(identifier)
            updates = {
                "units": maaru_geological_units(related["geology"]),
                "core_boxes": maaru_core_boxes(related["core_boxes"]),
                "samples": maaru_samples(related["samples"]),
            }
            depth = self._cross_section_optional_number(row, "sygavus")
            elevation = self._cross_section_optional_number(row, "z")
            if depth is not None:
                updates["depth"] = depth
            if elevation is not None:
                updates["elevation"] = elevation
                updates["elevation_source"] = "MaRu"
            if self.dock:
                self.dock.cross_sections.update_snapshot(
                    snapshot.get("key"), updates, serial=snapshot.get("_section_serial"),
                )

        self._ensure_maaru_database(ready, lambda _error: None)

    def _load_cross_section_faktika_profile(self, snapshot):
        guid = normalize_guid(snapshot.get("global_id"))
        if not guid:
            return
        workspace_key = snapshot.get("faktika_workspace") or "faktika"
        self._query_faktika_rows(
            6,
            f"puurauk_vaatluspunkt_id = '{escape_where(guid)}'",
            lambda rows: self._merge_cross_section_profile(
                snapshot, self._faktika_display_units(rows, workspace_key)
            ),
            lambda _error: None,
            order_by="z_suht_ylemine", workspace_key=workspace_key,
        )

    def _load_cross_section_field_mapping_profile(self, snapshot):
        guid = normalize_guid(snapshot.get("global_id"))
        if not guid:
            return
        bundle = self.PORTAL_LAYER_BUNDLES["field_mapping"]

        def metadata_loaded(metadata):
            self.network.query_arcgis_features(
                bundle["url"], 1,
                f"vaatluspunkt_id = '{escape_where(guid)}'",
                lambda payload: self._merge_cross_section_profile(
                    snapshot,
                    self._portal_label_units(
                        self._faktika_records(payload), metadata.get(1, {}),
                        sequential_bottoms=True,
                        elevations={guid.upper(): snapshot.get("elevation")},
                    ).get(guid.upper(), []),
                ),
                lambda _error: None,
                authcfg=self.egt_portal_authcfg,
                out_fields="*", return_geometry=False, return_z=False,
                order_by="z_suht_alumine",
            )

        self._ensure_portal_bundle_metadata(
            "field_mapping", metadata_loaded, lambda _error: None,
        )

    def _load_cross_section_egt_profile(self, snapshot):
        global_id = str(snapshot.get("global_id") or "").strip()
        if not global_id:
            return

        def from_wfs():
            self.network.query_geological_units(
                snapshot.get("role"), global_id,
                lambda units: self._merge_cross_section_profile(snapshot, units),
                lambda _error: None,
            )

        if (
            snapshot.get("role") == "boreholes"
            and getattr(self, "egt_data_source", "wfs") == "api"
        ):
            self.network.query_borehole_profile(
                global_id,
                lambda units: self._merge_cross_section_profile(snapshot, units),
                lambda _error: from_wfs(),
            )
        else:
            self.network.query_geological_units(
                snapshot.get("role"), global_id,
                lambda units: self._merge_cross_section_profile(snapshot, units),
                lambda _error: (
                    self.network.query_borehole_profile(
                        global_id,
                        lambda units: self._merge_cross_section_profile(snapshot, units),
                        lambda _fallback_error: None,
                    )
                    if snapshot.get("role") == "boreholes" else None
                ),
            )

    def _load_cross_section_veka_profile(self, snapshot):
        identifier = str(snapshot.get("eelis_id") or snapshot.get("id") or "")
        if not identifier:
            return
        self.network.query_eelis_pages(
            "f_puuraugud_labiloige",
            {"labil_puurauk_id": f"eq.{identifier}", "order": "jrk_nr.asc"},
            (
                "labiloige_id", "jrk_nr", "geol_vanus",
                "kivim_nimetus", "lasum", "lamam", "paksus",
            ),
            lambda rows: self._merge_cross_section_profile(
                snapshot, [{
                    "z_suht_ylemine": row.get("lasum"),
                    "z_suht_alumine": row.get("lamam"),
                    "indeks": row.get("geol_vanus"),
                    "litoloogia": row.get("kivim_nimetus"),
                    "litoloogia_orig": row.get("kivim_nimetus"),
                    "id": row.get("labiloige_id"),
                } for row in rows]
            ),
            lambda _error: None,
            limit=2000,
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
            section = self.dock.cross_sections
            section.set_line(transformed)
            # Show the line immediately, then populate it from the visible
            # point layers.  The short deferred call keeps the map-tool finish
            # event responsive even when a WFS provider has to query a page.
            QTimer.singleShot(
                0, lambda line=list(transformed), serial=section._workspace_serial:
                self._auto_add_cross_section_objects(line) if self.dock
                and self.dock.cross_sections is section
                and section._workspace_serial == serial else None
            )
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

    def update_local_section_outcrops(self, items):
        canvas = self.iface.mapCanvas() if hasattr(self.iface, "mapCanvas") else None
        if canvas is None:
            return
        for band in self._local_section_bands:
            canvas.scene().removeItem(band)
        self._local_section_bands.clear()
        local = [row for row in items if row.get("role") == "local_section"
                 and row.get("enabled", True)]
        if not local:
            return
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:3301"),
            canvas.mapSettings().destinationCrs(), QgsProject.instance(),
        )
        for row in local:
            try:
                trace = row.get("trace") or []
                points = [transform.transform(QgsPointXY(float(x), float(y))) for x, y in trace]
                if len(points) >= 2:
                    geometry = QgsGeometry.fromPolylineXY(points)
                else:
                    x, y = float(row["x"]), float(row["y"])
                    if not (isfinite(x) and isfinite(y)):
                        continue
                    geometry = QgsGeometry.fromPointXY(transform.transform(QgsPointXY(x, y)))
            except (QgsCsException, KeyError, TypeError, ValueError):
                continue
            band = QgsRubberBand(canvas, geometry.type())
            band.setColor(QColor("#5c3f9d"))
            band.setWidth(3)
            band.setToGeometry(geometry, None)
            self._local_section_bands.append(band)
        canvas.update()

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
                    and -1000.0 < elevation < 10000.0
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
                point = (
                    geometry.asPoint()
                    if not geometry.isMultipart()
                    and geometry.type() == Qgis.GeometryType.Point
                    else geometry.centroid().asPoint()
                )
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

    @staticmethod
    def detail_location(attributes):
        """Return an object's map location in EPSG:3301, if available."""
        values = attributes or {}
        for x_key, y_key, crs in (
            ("_qeoloog_x_3301", "_qeoloog_y_3301", "EPSG:3301"),
            ("_maaru_x", "_maaru_y", "EPSG:3301"),
            ("kesk_x", "kesk_y", "EPSG:3301"),
            ("_qeoloog_longitude", "_qeoloog_latitude", "EPSG:4326"),
        ):
            try:
                x, y = float(values.get(x_key)), float(values.get(y_key))
                if not isfinite(x) or not isfinite(y):
                    continue
                point = QgsPointXY(x, y)
                if crs != "EPSG:3301":
                    point = QgsCoordinateTransform(
                        QgsCoordinateReferenceSystem(crs),
                        QgsCoordinateReferenceSystem("EPSG:3301"),
                        QgsProject.instance(),
                    ).transform(point)
                return point
            except (QgsCsException, TypeError, ValueError):
                continue
        return None

    def go_to_detail_location(self, attributes):
        """Centre the map on the current object without changing its scale."""
        point = self.detail_location(attributes)
        if point is None:
            return False
        canvas = self.iface.mapCanvas()
        try:
            point = QgsCoordinateTransform(
                QgsCoordinateReferenceSystem("EPSG:3301"),
                canvas.mapSettings().destinationCrs(),
                QgsProject.instance(),
            ).transform(point)
        except QgsCsException:
            return False
        canvas.setCenter(point)
        canvas.refresh()
        return True

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
        if source in {"all", "maaru"}:
            roles.add("maaru_cores")
        if source == "latvia":
            roles.add("latvia_boreholes")
        if source == "minerals":
            roles.update((
                "mineral_deposits", "mining_claims", "exploration_areas",
            ))
        if source == "archive":
            roles.add("archive_survey_areas")
        selected = criteria.get("kinds")
        return roles if selected is None else roles.intersection(selected)

    def _registry_search_bbox(self, criteria):
        if not criteria.get("current_extent"):
            return ""
        try:
            extent = QgsCoordinateTransform(
                self.iface.mapCanvas().mapSettings().destinationCrs(),
                QgsCoordinateReferenceSystem("EPSG:3301"),
                QgsProject.instance(),
            ).transformBoundingBox(self.iface.mapCanvas().extent())
        except QgsCsException:
            return ""
        return ",".join((
            f"{extent.xMinimum():.3f}", f"{extent.yMinimum():.3f}",
            f"{extent.xMaximum():.3f}", f"{extent.yMaximum():.3f}",
            "EPSG:3301",
        ))

    def _registry_definition(self, role, code):
        """Resolve a configured registry source, with its built-in fallback."""
        configured = next((
            item for item in self.definitions
            if item.role == role and item.protocol.upper() == "WFS"
        ), None)
        if configured is not None:
            return configured
        return next((
            item for item in DEFAULT_LAYERS
            if item.code == code and item.role == role
        ), None)

    @staticmethod
    def _registry_search_cql(config, query_text):
        """Build a bounded name/identifier CQL expression for GeoServer."""
        tokens = [token for token in str(query_text or "").split() if token]
        groups = []
        for token in tokens:
            safe = token.replace("'", "''")
            clauses = [
                f"{field} ILIKE '%{safe}%'"
                for field in (
                    tuple(config.get("name_fields", ()))
                    + tuple(config.get("identifier_fields", ()))
                )
            ]
            if token.isdigit():
                clauses.extend(
                    f"{field}={int(token)}"
                    for field in config.get("numeric_fields", ())
                )
            if clauses:
                groups.append("(" + " OR ".join(clauses) + ")")
        return " AND ".join(groups)

    def _run_registry_search(self, criteria, callback):
        query_text = str(criteria.get("text") or "").strip()
        if not query_text:
            callback([], self.t("Sisesta otsingusse nimi või registri ID."))
            return
        roles = [
            role for role in self._search_roles(criteria)
            if role in self.REGISTRY_SEARCH
        ]
        if not roles:
            callback([], self.t("Vali vähemalt üks objekti liik."))
            return
        pending = {"count": 0, "truncated": False}
        rows = []
        errors = []
        bbox = self._registry_search_bbox(criteria)

        def completed():
            pending["count"] -= 1
            if pending["count"]:
                return
            unique = {}
            for row in rows:
                key = (row.get("_role"), str(row.get("_filter_id")))
                previous = unique.get(key)
                if (
                    previous is None
                    or int(row.get("_search_score") or 0)
                    > int(previous.get("_search_score") or 0)
                ):
                    unique[key] = row
            ordered = sorted(unique.values(), key=lambda row: (
                -int(row.get("_search_score") or 0),
                str(row.get("source") or ""),
                str(row.get("name") or "").casefold(),
            ))
            message = f"{len(ordered)} {self.t('tulemust')}"
            if pending["truncated"]:
                message += f". {self.t('Kuvatakse esimesed 500.')}"
            if errors:
                message += ". " + self.t("Mõni registripäring ebaõnnestus: ")
                message += "; ".join(errors)
            callback(ordered[:500], message)

        for role in roles:
            config = self.REGISTRY_SEARCH[role]
            definition = self._registry_definition(role, config["code"])
            if definition is None:
                errors.append(
                    f"{config['code']}: {self.t('kiht puudub seadetest')}"
                )
                continue
            cql_filter = self._registry_search_cql(config, query_text)
            if not cql_filter:
                continue
            pending["count"] += 1

            def loaded(features, number_matched, role=role, config=config):
                try:
                    pending["truncated"] = (
                        pending["truncated"] or int(number_matched) > len(features)
                    )
                except (TypeError, ValueError):
                    pass
                for feature in features:
                    attributes = feature.get("properties", {})
                    filter_value = attributes.get(config["filter_field"])
                    if filter_value in (None, ""):
                        continue
                    preferred_names = list(config["name_fields"])
                    if role == "archive_survey_areas" and self.language == "en":
                        preferred_names = [
                            "nimetus_eng", "nimetus", "nimetus_orig",
                        ]
                    name = next((
                        attributes.get(field) for field in preferred_names
                        if attributes.get(field) not in (None, "")
                    ), filter_value)
                    identifier_values = [
                        attributes.get(field)
                        for field in (
                            tuple(config.get("identifier_fields", ()))
                            + tuple(config.get("numeric_fields", ()))
                        )
                    ]
                    relevance = self._search_relevance(
                        query_text,
                        primary_values=[
                            attributes.get(field)
                            for field in config.get("name_fields", ())
                        ],
                        identifier_values=identifier_values,
                        other_values=[
                            attributes.get(field)
                            for field in config.get("other_fields", ())
                        ],
                    )
                    if relevance is None:
                        continue
                    rows.append({
                        "source": self.t(config["source"]),
                        "type": self.t(config["type"]),
                        "name": name,
                        "id": filter_value,
                        "depth": attributes.get("max_sygavus_m"),
                        "_role": role,
                        "_filter_id": filter_value,
                        "_registry_definition_code": config["code"],
                        "_registry_filter_field": config["filter_field"],
                        "_attributes": attributes,
                        "_geometry": feature.get("geometry"),
                        "_search_score": relevance,
                    })
                completed()

            def failed(error, role=role):
                errors.append(
                    f"{self.t(self.REGISTRY_SEARCH[role]['type'])}: {error}"
                )
                completed()

            property_names = tuple(dict.fromkeys(
                tuple(config.get("name_fields", ()))
                + tuple(config.get("identifier_fields", ()))
                + tuple(config.get("numeric_fields", ()))
                + tuple(config.get("other_fields", ()))
                + (config["filter_field"],)
            ))
            self.network.query_wfs_features(
                definition.url, definition.layer_name, cql_filter,
                loaded, failed, count=500, bbox=bbox,
                sort_by=config.get("sort_by", ""),
                property_names=property_names,
            )

        if not pending["count"]:
            callback([], ". ".join(errors) or self.t("Otsingut ei saanud käivitada."))

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
        self._apply_maaru_search_filter()
        self._apply_latvia_search_filter()

    def clear_search_filter(self):
        """Remove the transient search-result filter from all point layers."""
        self._search_filter = None
        self.apply_egt_filters()
        self.apply_sarv_filters()
        self.apply_veka_filters()
        self._apply_maaru_search_filter()
        self._apply_latvia_search_filter()

    def _apply_maaru_search_filter(self):
        for layer in self._role_layers("maaru_cores"):
            expression = self._search_filter_clause(layer, "maaru_cores")
            try:
                layer.setSubsetString(expression)
            except (AttributeError, RuntimeError):
                pass

    def _apply_latvia_search_filter(self):
        for layer in self._role_layers("latvia_boreholes"):
            expression = self._search_filter_clause(layer, "latvia_boreholes")
            try:
                layer.setSubsetString(expression)
            except (AttributeError, RuntimeError):
                pass

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
            "maaru_cores": ("maaru_id",),
            "latvia_boreholes": ("FID", "Nr_DB_URB"),
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
        if source in {"minerals", "archive"}:
            self._run_registry_search(criteria, callback)
            return
        wants_egt = source in {"all", "both", "egt"}
        wants_sarv = source in {"all", "both", "sarv"}
        wants_veka = source in {"all", "veka"}
        wants_maaru = source in {"all", "maaru"}
        wants_latvia = source == "latvia"
        related = criteria.get("related", {})
        stratigraphic_indices = criteria.get("stratigraphic_indices", set())
        if (
            wants_maaru
            and not criteria.get("_maaru_ready")
            and (self._maaru_db is None or not self._maaru_db.available)
        ):
            self._ensure_maaru_database(
                lambda _database: self.run_search(
                    {**criteria, "_maaru_ready": True}, callback
                ),
                lambda error: callback(
                    [], self.t("MaRu andmekogu laadimine ebaõnnestus")
                    + f": {error}",
                ),
            )
            return
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
        if wants_latvia:
            roles.append("latvia_boreholes")
        selected_roles = criteria.get("kinds")
        if selected_roles is not None:
            roles = [role for role in roles if role in selected_roles]
        for role in roles:
            for layer in self._role_layers(role):
                loaded_sources.add(
                    "SARV" if role.startswith("sarv_")
                    else "VEKA" if role == "veka_boreholes"
                    else "LVĢMC" if role == "latvia_boreholes" else "EGT"
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
                    is_latvia = role == "latvia_boreholes"
                    object_id = (
                        attributes.get("sarv_id") if is_sarv else
                        (attributes.get("kkr_kood") or attributes.get("eelis_id"))
                        if is_veka else
                        (attributes.get("FID") or attributes.get("Nr_DB_URB"))
                        if is_latvia else
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
                    if (
                        not is_sarv and not is_veka and not is_latvia
                        and allowed_egt is not None
                    ):
                        if str(object_id).upper() not in allowed_egt:
                            continue
                    if not is_sarv and not is_veka and not is_latvia:
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
                        None if is_latvia else
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
                    elif is_latvia:
                        name = (
                            attributes.get("NOS_URB_K")
                            or attributes.get("Nos_DB_URB")
                            or attributes.get("Nr_DB_URB")
                        )
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
                            attributes.get("Nr_DB_URB"),
                            attributes.get("FID"),
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
                            attributes.get("Nos_DB_URB"),
                            attributes.get("NOS_URB_K"),
                            attributes.get("Mērķis"),
                            attributes.get("Gads"),
                        ),
                    )
                    if relevance is None:
                        continue
                    rows.append({
                        "source": (
                            "SARV" if is_sarv else "VEKA" if is_veka
                            else "LVĢMC" if is_latvia else "EGT"
                        ),
                        "type": self.t({
                            "boreholes": "Puurauk",
                            "observations": "Vaatluspunkt",
                            "sarv_localities": "Lokaliteet",
                            "sarv_sites": "Uuringupunkt",
                            "sarv_drillcores": "Puursüdamik",
                            "veka_boreholes": "VEKA puurkaev",
                            "latvia_boreholes": "Läti geoloogiline puurauk",
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
                            else attributes.get("FID") if is_latvia
                            else object_id
                        ),
                        "_search_score": relevance,
                    })
        if (
            wants_maaru
            and (selected_roles is None or "maaru_cores" in selected_roles)
            and self._maaru_db is not None
            and self._maaru_db.available
        ):
            core_requirement = related.get("core", "any")
            sample_requirement = related.get("samples", "any")
            analysis_requirement = related.get("analyses", "any")
            # The historical MaRu export contains core boxes and samples, but
            # no separate analysis table.  An explicit "analyses: yes"
            # therefore cannot match MaRu records.
            maaru_rows = [] if analysis_requirement == "yes" else self._maaru_db.search(
                text_query,
                depth_min=depth_min,
                depth_max=depth_max,
                stratigraphic_indices=stratigraphic_indices,
                require_core=(
                    core_requirement == "yes" if core_requirement != "any"
                    else None
                ),
                require_samples=(
                    sample_requirement == "yes" if sample_requirement != "any"
                    else None
                ),
                maaru_filters=criteria.get("maaru_filters", {}),
                limit=100000 if criteria.get("_return_all") else 750,
            )
            extent_3301 = None
            if criteria.get("current_extent"):
                try:
                    extent_3301 = QgsCoordinateTransform(
                        self.iface.mapCanvas().mapSettings().destinationCrs(),
                        QgsCoordinateReferenceSystem("EPSG:3301"),
                        QgsProject.instance(),
                    ).transformBoundingBox(canvas_extent)
                except QgsCsException:
                    pass
            for attributes in maaru_rows:
                x = attributes.get("_maaru_x")
                y = attributes.get("_maaru_y")
                if extent_3301 is not None:
                    try:
                        if not extent_3301.contains(float(x), float(y)):
                            continue
                    except (TypeError, ValueError):
                        continue
                identifier = str(attributes.get("id") or "")
                name = (
                    attributes.get("nimetus") or attributes.get("number")
                    or attributes.get("uus_id") or identifier
                )
                relevance = self._search_relevance(
                    text_query,
                    primary_values=(name, attributes.get("number")),
                    identifier_values=(
                        identifier, attributes.get("uus_id"),
                        attributes.get("sarv_loc_id"), attributes.get("GB_id"),
                    ),
                    other_values=(
                        attributes.get("märkused"), attributes.get("tüüp"),
                        attributes.get("strat. algus"),
                        attributes.get("strat. lõpp"),
                    ),
                )
                if (
                    relevance is None
                    and attributes.get("_maaru_search_scope") == "related"
                ):
                    # MaaruDatabase.search has already matched every query
                    # token against geology, core-box or sample rows. Keep
                    # those valid child-table matches below exact overview
                    # and identifier matches in the result ordering.
                    relevance = 550
                if relevance is None:
                    continue
                rows.append({
                    "source": "MaRu",
                    "type": self.t("Puursüdamik"),
                    "name": name,
                    "id": identifier,
                    "depth": attributes.get("sygavus"),
                    "_role": "maaru_cores",
                    "_filter_id": identifier,
                    "_maaru_id": identifier,
                    "_maaru_x": x,
                    "_maaru_y": y,
                    "_search_score": relevance,
                })
            loaded_sources.add("MaRu")
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
        if wants_maaru and "MaRu" not in loaded_sources:
            missing.append("MaRu")
        if wants_latvia and "LVĢMC" not in loaded_sources:
            missing.append("LPU")
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
        if item.get("_registry_definition_code"):
            self._open_registry_search_result(item)
            return
        if item.get("_maaru_id"):
            canvas = self.iface.mapCanvas()
            try:
                point = QgsCoordinateTransform(
                    QgsCoordinateReferenceSystem("EPSG:3301"),
                    canvas.mapSettings().destinationCrs(),
                    QgsProject.instance(),
                ).transform(QgsPointXY(
                    float(item.get("_maaru_x")),
                    float(item.get("_maaru_y")),
                ))
                canvas.setCenter(point)
                canvas.refresh()
            except (QgsCsException, TypeError, ValueError):
                pass
            self._load_maaru_point_details(
                str(item.get("_maaru_id")),
                str(item.get("name") or item.get("id")),
            )
            return
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
        elif str(role).startswith("latvia_"):
            self._show_registry_feature_details(
                role, str(item.get("name") or item.get("id")), attributes,
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

    @staticmethod
    def _provider_filter_literal(value):
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        text = str(value).replace("'", "''")
        return f"'{text}'"

    def _zoom_to_registry_geometry(self, geometry_value):
        if not geometry_value:
            return
        try:
            geometry = QgsJsonUtils.geometryFromGeoJson(
                json.dumps(geometry_value)
            )
            if geometry.isNull() or geometry.isEmpty():
                return
            canvas = self.iface.mapCanvas()
            geometry.transform(QgsCoordinateTransform(
                QgsCoordinateReferenceSystem("EPSG:3301"),
                canvas.mapSettings().destinationCrs(),
                QgsProject.instance(),
            ))
            extent = geometry.boundingBox()
            padding = max(extent.width(), extent.height(), 100.0) * 0.12
            extent.grow(padding)
            canvas.setExtent(extent)
            canvas.refresh()
        except (QgsCsException, TypeError, ValueError):
            return

    def _zoom_to_registry_layer(self, layer):
        try:
            extent = QgsCoordinateTransform(
                layer.crs(),
                self.iface.mapCanvas().mapSettings().destinationCrs(),
                QgsProject.instance(),
            ).transformBoundingBox(layer.extent())
            if extent.isEmpty():
                return
            padding = max(extent.width(), extent.height(), 100.0) * 0.12
            extent.grow(padding)
            self.iface.mapCanvas().setExtent(extent)
            self.iface.mapCanvas().refresh()
        except (QgsCsException, TypeError, ValueError):
            return

    @staticmethod
    def _registry_layer_attributes(layer):
        try:
            feature = next(layer.getFeatures(), None)
        except (RuntimeError, TypeError, ValueError):
            feature = None
        if feature is None:
            return {}
        return {
            field.name(): feature.attribute(field.name())
            for field in layer.fields()
        }

    def _open_registry_search_result(self, item):
        """Open exactly one registry object as a server-filtered WFS layer."""
        code = str(item.get("_registry_definition_code") or "")
        role = str(item.get("_role") or "")
        definition = self._registry_definition(role, code)
        if definition is None:
            self.warning(self.t("Otsingutulemuse kiht puudub seadetest."))
            return
        role = role or definition.role
        field = str(item.get("_registry_filter_field") or "")
        value = item.get("_filter_id")
        if not field or value in (None, ""):
            self.warning(self.t("Otsingutulemusel puudub püsiv registri ID."))
            return
        key = f"{role}|{field}|{value}"
        project = QgsProject.instance()
        existing = next((
            layer for layer in project.mapLayers().values()
            if str(layer.customProperty(self.SEARCH_KEY_PROPERTY, "")) == key
        ), None)
        attributes = dict(item.get("_attributes") or {})
        name = str(item.get("name") or value)
        if existing is not None:
            node = project.layerTreeRoot().findLayer(existing.id())
            if node:
                node.setItemVisibilityChecked(True)
            self.iface.setActiveLayer(existing)
            attributes.update(self._registry_layer_attributes(existing))
            if item.get("_geometry"):
                self._zoom_to_registry_geometry(item.get("_geometry"))
            else:
                self._zoom_to_registry_layer(existing)
            self._show_registry_feature_details(role, name, attributes)
            return

        previous = [
            layer.id() for layer in project.mapLayers().values()
            if layer.customProperty(self.SEARCH_RESULT_PROPERTY, False)
            and self._layer_role(layer) == role
        ]
        if previous:
            project.removeMapLayers(previous)
        expression = (
            f'"{field}" = {self._provider_filter_literal(value)}'
        )
        display_name = f"{self.display_name(definition)} — {name}"
        layer = QgsVectorLayer(
            self._wfs_uri(definition, expression), display_name, "WFS"
        )
        if not layer.isValid():
            self.error(self.t(
                "Valitud registriobjekti kihi laadimine ebaõnnestus."
            ))
            return
        layer.setCustomProperty(
            self.SOURCE_PROPERTY,
            f"{self._source_id(definition)}|search|{field}={value}",
        )
        layer.setCustomProperty(self.ROLE_PROPERTY, role)
        layer.setCustomProperty(self.SEARCH_RESULT_PROPERTY, True)
        layer.setCustomProperty(self.SEARCH_DEFINITION_PROPERTY, code)
        layer.setCustomProperty(self.SEARCH_KEY_PROPERTY, key)
        self._apply_definition_renderer(layer, definition)
        project.addMapLayer(layer, False)
        project.layerTreeRoot().insertLayer(0, layer)
        self.iface.setActiveLayer(layer)
        attributes.update(self._registry_layer_attributes(layer))
        if item.get("_geometry"):
            self._zoom_to_registry_geometry(item.get("_geometry"))
        else:
            self._zoom_to_registry_layer(layer)
        self._show_registry_feature_details(role, name, attributes)
        self.success(self.t("Valitud registriobjekt lisati filtreeritud kihina."))

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
                self.dock.show_search_filters("egt")
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
        gtk_vector_roles = [
            "gtk_bedrock_observations", "gtk_bedrock_drillings",
            "gtk_core_archive", "gtk_mineral_occurrences",
            "gtk_ground_investigations",
        ]
        latvia_vector_roles = [
            "latvia_boreholes", "latvia_karst", "latvia_faults",
            "latvia_seismic_profiles", "latvia_groundwater",
            "latvia_mineral_deposits", "latvia_mining_licences",
            "latvia_extraction_limits",
        ]
        public_vector_roles = gtk_vector_roles + latvia_vector_roles
        roles = [
            "faktika", "field_mapping", "boreholes", "observations", "veka_boreholes", "maaru_cores", "sarv_drillcores",
            "sarv_sites", "sarv_localities", "engineering_geology_points",
            "mining_claims", "exploration_areas", "mineral_deposits",
            "archive_survey_areas",
        ] + public_vector_roles
        active_layer = self.iface.activeLayer()
        active_role = self._layer_role(active_layer) if active_layer else ""
        if (
            isinstance(active_layer, QgsRasterLayer)
            and str(active_role).startswith(("gtk_", "latvia_"))
            and self._identify_gtk_wms_layer(active_layer, map_point)
        ):
            return
        if active_role in roles:
            roles.remove(active_role)
            roles.insert(0, active_role)
        for role_priority, role in enumerate(roles):
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
                            and (not self._passes_related_filter(feature_attributes, role)
                                 or not self._passes_archive_report_filter(layer, feature))
                        ):
                            continue
                        geometry = QgsGeometry(feature.geometry())
                        geometry.transform(to_map)
                        distance = geometry.distance(click_geometry)
                        # Polygon layers commonly overlap. Respect the active
                        # layer first, then prefer the smallest containing
                        # polygon instead of returning an arbitrary WFS row.
                        polygon = (
                            geometry.type() == Qgis.GeometryType.Polygon
                        )
                        area = geometry.area() if polygon else 0.0
                        score = (
                            0 if active_role and role == active_role else 1,
                            1 if polygon else 0,
                            distance,
                            role_priority,
                            area,
                        )
                        if best is None or score < best[0]:
                            best = (score, distance, role, layer, feature)
                except (QgsCsException, ValueError):
                    continue
        if best is None or best[1] > tolerance:
            for layer in canvas.layers():
                if (
                    not isinstance(layer, QgsRasterLayer)
                    or not str(self._layer_role(layer)).startswith(
                        ("gtk_", "latvia_")
                    )
                    or layer is active_layer
                ):
                    continue
                if self._identify_gtk_wms_layer(layer, map_point):
                    return
            self.message(
                "No supported visible object was found here." if self.language == "en"
                else "Selles kohas ei leitud toetatud nähtavat objekti."
            )
            return
        _, _, role, layer, feature = best
        attributes = {
            field.name(): feature.attribute(field.name())
            for field in layer.fields()
        }
        attributes = self._detail_attributes_with_location(
            attributes, layer, feature
        )
        if role == "faktika":
            try:
                object_type = int(attributes.get("objekti_tyyp") or 2)
            except (TypeError, ValueError):
                object_type = 2
            detail_role = "boreholes" if object_type == 1 else "observations"
            global_id = attributes.get("globalid") or attributes.get("esri_globalid")
            name = (
                attributes.get("nimi") or attributes.get("alias")
                or attributes.get("gea_id") or self.t(OBJECT_TYPES.get(object_type, "Faktika objekt"))
            )
            if not global_id:
                self.error(self.t("Valitud Faktika objektil puudub globalid."))
                return
            self._show_highlight(layer, feature)
            workspace_key = str(layer.customProperty(
                "qeoloog/faktika_workspace", "faktika"
            ))
            faktika_geometry = {
                "x": attributes.get("_qeoloog_x_3301"),
                "y": attributes.get("_qeoloog_y_3301"),
                "z": attributes.get("z_abs"),
            }
            self._load_details(
                detail_role, str(global_id), str(name), attributes,
                faktika_parent=attributes,
                faktika_geometry=faktika_geometry,
                faktika_workspace=workspace_key,
            )
            return
        if role == "field_mapping":
            self._show_highlight(layer, feature)
            self._load_field_mapping_details(attributes)
            return
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
        if role == "maaru_cores":
            identifier = attributes.get("maaru_id")
            name = attributes.get("nimi") or attributes.get("number") or identifier
            if identifier not in (None, ""):
                self._show_highlight(layer, feature)
                self._load_maaru_point_details(str(identifier), str(name), attributes)
            return
        if role in self.MINERAL_LAYER_ROLES:
            name_fields = {
                "mineral_deposits": (
                    "maardla_nimetus", "maardla_osa_nimetus", "maardla_id",
                ),
                "mining_claims": (
                    "maeeraldise_nimetus", "maeeraldise_kood", "maeeraldise_id",
                ),
                "exploration_areas": (
                    "uuringuala_nimi", "uuringuala_kood", "uuringuala_id",
                ),
            }[role]
            name = next(
                (attributes.get(key) for key in name_fields if attributes.get(key)),
                self.t("Maavarade registri objekt"),
            )
            self._show_highlight(layer, feature)
            self._show_registry_feature_details(role, str(name), attributes)
            return
        if role in {"engineering_geology_points", "archive_survey_areas"}:
            name = (
                attributes.get("nimetus_eng") if self.language == "en"
                else attributes.get("nimetus")
            ) or attributes.get("nimetus") or attributes.get("nimetus_orig")
            name = name or attributes.get("egf_id") or attributes.get("id")
            self._show_highlight(layer, feature)
            self._show_registry_feature_details(role, str(name), attributes)
            return
        if role in public_vector_roles:
            name = self._gtk_feature_name(
                attributes,
                layer.name() or (
                    self.t("Läti objekt") if role.startswith("latvia_")
                    else self.t("GTK objekt")
                ),
            )
            self._show_highlight(layer, feature)
            self._show_registry_feature_details(role, str(name), attributes)
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

    @staticmethod
    def _gtk_feature_name(attributes, fallback):
        """Choose a useful title across GTK's heterogeneous public schemas."""
        folded = {
            str(key).casefold(): value
            for key, value in (attributes or {}).items()
        }
        for field in (
            "hole_id2", "hole_id", "archive_number", "target_name",
            "original_name", "rock_name_", "name", "nimi", "number",
            "nos_urb_k", "nos_db_urb", "nr_db_urb", "nosaukums",
            "numurs", "featurename", "id_localid", "ifcid",
            "objectid", "gmlid",
        ):
            value = folded.get(field)
            if str(value or "").strip().casefold() not in {
                "", "null", "none", "n/a",
            }:
                return str(value)
        return str(fallback)

    def _identify_gtk_wms_layer(self, layer, map_point):
        """Show one public GTK WMS GetFeatureInfo result in Qeoloog details."""
        canvas = self.iface.mapCanvas()
        try:
            transform = QgsCoordinateTransform(
                canvas.mapSettings().destinationCrs(),
                layer.crs(), QgsProject.instance(),
            )
            layer_point = transform.transform(map_point)
            extent = transform.transformBoundingBox(canvas.extent())
            result = layer.dataProvider().identify(
                layer_point, Qgis.RasterIdentifyFormat.Html,
                extent, max(1, canvas.size().width()),
                max(1, canvas.size().height()),
            )
            if not result.isValid():
                return False
            features = []
            for payload in result.results().values():
                features.extend(parse_feature_info_html(payload))
        except (QgsCsException, AttributeError, RuntimeError, TypeError, ValueError):
            return False
        if not features:
            return False
        clean = {
            str(key): value
            for key, value in features[0].items()
            if str(value or "").strip().casefold()
            not in {"", "null", "none", "n/a"}
        }
        if not clean:
            return False
        role = str(self._layer_role(layer) or "gtk_wms_feature")
        source_label = "LVĢMC kiht" if role.startswith("latvia_") else "GTK kiht"
        attributes = {self.t(source_label): layer.name(), **clean}
        try:
            location = QgsCoordinateTransform(
                canvas.mapSettings().destinationCrs(),
                QgsCoordinateReferenceSystem("EPSG:3301"),
                QgsProject.instance(),
            ).transform(map_point)
            attributes["_qeoloog_x_3301"] = location.x()
            attributes["_qeoloog_y_3301"] = location.y()
        except QgsCsException:
            pass
        name = self._gtk_feature_name(attributes, layer.name())
        self._show_registry_feature_details(role, name, attributes)
        return True

    def _show_registry_feature_details(self, role, name, attributes):
        """Show already-loaded WFS attributes without related-data requests."""
        self._detail_token += 1
        self.dock.show_details()
        self.dock.details.show_loading(name, attributes, role)
        self.dock.details.set_ready(name)

    def _load_field_mapping_details(self, attributes):
        """Show one authenticated field-mapping point and its descriptions."""
        bundle_key = "field_mapping"
        bundle = self.PORTAL_LAYER_BUNDLES[bundle_key]
        self._detail_token += 1
        token = self._detail_token
        global_id = normalize_guid(
            attributes.get("globalid") or attributes.get("GlobalID")
        )
        object_code = attributes.get("objekti_tyyp")
        cached_parent = self.portal_bundle_metadata(bundle_key).get(0, {})
        object_label = subtype_label(cached_parent, object_code)
        name = (
            attributes.get("nimi") or attributes.get("valitoo_id")
            or object_label or self.t("Välitöö faktika")
        )
        self.dock.show_details()
        details = self.dock.details
        details.show_loading(str(name), attributes, "field_mapping")
        if not global_id:
            details.set_ready(str(name))
            self.warning(self.t("Valitud välitöö objektil puudub globalid."))
            return

        def failed(error):
            if token != self._detail_token:
                return
            details.set_ready(str(name))
            self.warning(
                (f"Field descriptions could not be loaded: {error}"
                 if self.language == "en" else
                 f"Välitöö kirjeldusi ei õnnestunud laadida: {error}")
            )

        def metadata_loaded(metadata):
            if token != self._detail_token:
                return
            details.refresh_overview_labels()
            table_metadata = metadata.get(1, {})
            safe_id = escape_where(global_id)

            def rows_loaded(payload):
                if token != self._detail_token:
                    return
                rows = self._faktika_records(payload)
                grouped = self._portal_label_units(
                    rows, table_metadata, sequential_bottoms=True,
                    elevations={
                        global_id.upper(): veka_number(
                            attributes.get("z_abs")
                        ),
                    },
                )
                units = grouped.get(global_id.upper(), [])
                top = max((
                    veka_number(unit.get("z_suht_alumine")) or 0.0
                    for unit in units
                ), default=0.0)
                details.profile.set_total_depth(top)
                details.set_profile(units)
                details.set_ready(str(name))

            self.network.query_arcgis_features(
                bundle["url"], 1,
                f"vaatluspunkt_id = '{safe_id}'",
                rows_loaded, failed,
                authcfg=self.egt_portal_authcfg,
                out_fields="*", return_geometry=False, return_z=False,
                order_by="z_suht_alumine",
            )

        self._ensure_portal_bundle_metadata(
            bundle_key, metadata_loaded, failed,
        )

        object_id = attributes.get("objectid")
        if object_id not in (None, ""):
            self.network.query_arcgis_attachments(
                bundle["url"], 0, object_id,
                lambda rows: (
                    details.set_portal_attachments(rows)
                    if token == self._detail_token else None
                ),
                lambda error: (
                    self.warning(
                        (f"Attachments could not be loaded: {error}"
                         if self.language == "en" else
                         f"Manuseid ei õnnestunud laadida: {error}")
                    ) if token == self._detail_token else None
                ),
                authcfg=self.egt_portal_authcfg,
            )
        else:
            details.set_portal_attachments([])

    def open_portal_attachment(self, attachment):
        """Download one authenticated Portal attachment and open it locally."""
        url = str((attachment or {}).get("_url") or "").strip()
        if not url:
            self.warning(self.t("Manuse URL puudub."))
            return
        original = Path(str(
            (attachment or {}).get("name")
            or f"attachment_{(attachment or {}).get('id', '')}"
        )).name
        safe_name = "".join(
            character if character.isalnum() or character in ".-_"
            else "_" for character in original
        ) or "attachment"
        cache = Path(QgsApplication.qgisSettingsDirPath()) / "Qeoloog" / "attachments"
        cache.mkdir(parents=True, exist_ok=True)
        target = cache / (
            f"{(attachment or {}).get('id', 'file')}_{safe_name}"
        )
        expected_size = veka_number((attachment or {}).get("size"))
        if (
            target.exists()
            and (expected_size is None or target.stat().st_size == expected_size)
        ):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
            return

        def downloaded(data):
            try:
                target.write_bytes(data)
            except OSError as error:
                self.error(str(error))
                return
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

        self.network.get_bytes(
            QUrl(url), downloaded,
            lambda error: self.warning(
                (f"Attachment download failed: {error}"
                 if self.language == "en" else
                 f"Manuse allalaadimine ebaõnnestus: {error}")
            ),
            authcfg=self.egt_portal_authcfg,
            max_bytes=100 * 1024 * 1024,
        )

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
        if self.dock and getattr(self.dock, "filters", None):
            clauses = self._egt_domain_filter_clauses(self.dock.filters.egt_domain_requirements())
            if clauses is None:
                return False
            # Reuse the renderer's exact membership clauses for identify/search.
            for clause in clauses:
                expression = QgsExpression(clause)
                fields = QgsFields()
                fields.append(QgsField("esri_globalid", QVariant.String))
                feature = QgsFeature(fields)
                feature.setAttributes([object_id])
                context = QgsExpressionContext()
                context.setFeature(feature)
                if not expression.evaluate(context):
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
            details._local_profile_status = 'failed'
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
                    if label == 'log':
                        details._local_profile_status = 'failed'
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
            self._remember_veka_legacy_analyses(cadastral_number, chemistry["legacy"])
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
                    if label in {"SARV", "EGT läbilõige"}:
                        details._local_profile_status = 'failed'
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

        def load_linked_profile(candidate, *, add_match=False):
            if token != self._detail_token:
                return
            if not candidate or not candidate.get("id"):
                failed("EGT läbilõige")("No valid linked geological record")
                return
            if add_match:
                details.add_match_candidates(
                    "Kinnitatud EGT vaste", [candidate], self._open_egt_candidate,
                )
            details._local_profile_status = 'pending'

            def loaded(units):
                details._local_profile_source = 'EGT'
                details.set_profile(units)

            self.network.query_geological_units(
                candidate["role"], str(candidate["id"]), current(loaded),
                failed("EGT läbilõige"),
            )

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
            local_enabled = bool(self._local_object_store())
            if len(manual_links) == 1 and not local_enabled:
                self._open_manual_egt_link(
                    manual_links[0], token, failed("EGT"),
                )
                return
            if len(manual_links) == 1:
                # Keep the SARV ID selected in an active local workspace.
                # Otherwise opening its linked EGT record would target a
                # different original/local pair and erase the SARV toggle.
                link = manual_links[0]
                candidate = self._loaded_egt_candidate(link)
                if candidate:
                    load_linked_profile(candidate, add_match=True)
                else:
                    details._local_profile_status = 'pending'
                    self.network.query_egt_object(
                        link.get("role"), link.get("key_type"), link.get("key_value"),
                        current(lambda attrs: load_linked_profile(
                            self._egt_candidate_from_attributes(link.get("role"), attrs, manual=True),
                            add_match=True,
                        )),
                        failed("EGT läbilõige"),
                    )
            else:
                candidates = self._egt_candidates_for_sarv_point(
                    match_entity, source_type, entity.get("id"),
                )
                confirmed = [item for item in candidates if item.get("confirmed")]
                if len(confirmed) == 1:
                    details.add_match_candidates(
                        "Kinnitatud EGT vaste", confirmed, self._open_egt_candidate,
                    )
                    if local_enabled and confirmed[0].get("trusted_link"):
                        load_linked_profile(confirmed[0])
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

    def _maaru_candidate(self, row, manual=False):
        identifier = str(row.get("id") or "").strip()
        display = " — ".join(
            str(value) for value in (row.get("number"), row.get("nimetus"))
            if value not in (None, "")
        ) or identifier
        return {
            "maaru_id": identifier,
            "id": identifier,
            "row": row,
            "text": f"{display} (MaRu ID {identifier})",
            "url": maaru_detail_url(identifier),
            "evidence": row.get("_evidence") or self.t(
                "Kohalik parandus" if manual else "ametlik ID kattub"
            ),
            "confirmed": bool(manual or float(row.get("_score") or 0) >= 1200),
            "manual": bool(manual),
            "score": float(row.get("_score") or (5000 if manual else 0)),
        }

    def _set_maaru_record_data(self, token, row, details, database):
        if token != self._detail_token or not row:
            return
        related = database.related(row.get("id"))
        units = maaru_geological_units(related["geology"])
        boxes = maaru_core_boxes(related["core_boxes"])
        sample_rows = maaru_samples(related["samples"])
        images = {}
        for box in boxes:
            urls = list(box.get("_urls") or ())
            if urls:
                images.setdefault(
                    str(box.get("globalid") or "").upper(), []
                ).extend(urls)
        details.set_maaru_overview(row)
        details.set_maaru_profile(units)
        details.set_maaru_core(boxes, images)
        details.set_maaru_samples(sample_rows)
        details.set_maaru_attachments(maaru_image_attachments(
            related["core_boxes"], related["samples"], row,
        ))

    def _loaded_egt_link_for_maaru(self, identifier, row=None):
        matches = []
        for role in ("boreholes", "observations"):
            for layer in self._role_layers(role):
                expressions = []
                if layer.fields().indexOf("ma_orig_id") >= 0:
                    safe = str(identifier).replace("'", "''")
                    expressions.append(f'to_string("ma_orig_id") = \'{safe}\'')
                cleaned_id = str((row or {}).get("uus_id") or "").strip()
                if cleaned_id and layer.fields().indexOf("korrastatud_nr") >= 0:
                    safe = cleaned_id.replace("'", "''")
                    expressions.append(
                        f'to_string("korrastatud_nr") = \'{safe}\''
                    )
                for expression in expressions:
                    request = QgsFeatureRequest().setFilterExpression(expression)
                    request.setLimit(3)
                    for feature in layer.getFeatures(request):
                        attributes = {
                            field.name(): feature.attribute(field.name())
                            for field in layer.fields()
                        }
                        candidate = self._egt_candidate_from_attributes(
                            role, attributes, manual=False,
                        )
                        if candidate:
                            matches.append(candidate)
        unique = {str(item.get("id")): item for item in matches}
        return list(unique.values())

    def _manual_egt_links_for_maaru(self, identifier):
        result = []
        for match_key, record in self.sarv_matches.items():
            if not isinstance(record, dict):
                continue
            if str(record.get("maaru_id") or "") != str(identifier):
                continue
            parts = str(match_key).split(":", 2)
            if len(parts) == 3 and parts[0] in {"boreholes", "observations"}:
                result.append({
                    "role": parts[0], "key_type": parts[1],
                    "key_value": parts[2], "record": record,
                })
        return result

    def _query_egt_links_for_maaru(self, identifier, row, success, failure):
        """Find safe EGT matches from WFS without relying on loaded layers."""
        def loaded(rows):
            candidates = []
            for role, attributes in rows:
                candidate = self._egt_candidate_from_attributes(
                    role, attributes, manual=False,
                )
                if not candidate:
                    continue
                official = str(attributes.get("ma_orig_id") or "").strip() == str(
                    identifier
                )
                cleaned = bool(
                    str((row or {}).get("uus_id") or "").strip()
                    and str(attributes.get("korrastatud_nr") or "").strip()
                    == str((row or {}).get("uus_id") or "").strip()
                )
                maaru_number = self._normalized((row or {}).get("number"))
                maaru_name = self._normalized((row or {}).get("nimetus"))
                egt_numbers = {
                    self._normalized(attributes.get(key))
                    for key in ("nimi", "korrastatud_nr")
                    if attributes.get(key) not in (None, "")
                }
                egt_names = {
                    self._normalized(attributes.get(key))
                    for key in ("alias", "nimi")
                    if attributes.get(key) not in (None, "")
                    and any(
                        character.isalpha()
                        for character in str(attributes.get(key))
                    )
                }
                number_match = bool(
                    maaru_number and maaru_number in egt_numbers
                )
                name_match = bool(
                    maaru_name and maaru_name != "-" and any(
                        maaru_name == name
                        or maaru_name in name or name in maaru_name
                        for name in egt_names
                    )
                )
                try:
                    distance = hypot(
                        float((row or {}).get("_maaru_x"))
                        - float(attributes.get("_qeoloog_x_3301")),
                        float((row or {}).get("_maaru_y"))
                        - float(attributes.get("_qeoloog_y_3301")),
                    )
                except (TypeError, ValueError):
                    distance = None
                depth_diff = None
                try:
                    depth_diff = abs(
                        float((row or {}).get("sygavus"))
                        - float(
                            attributes.get("pikkus")
                            or attributes.get("vertikaalne_ulatus")
                        )
                    )
                except (TypeError, ValueError):
                    pass
                confirmed = bool(
                    official or cleaned
                    or distance is not None and distance <= 500
                    and number_match and name_match
                    or distance is not None and distance <= 25 and number_match
                    or distance is not None and distance <= 25 and name_match
                    and depth_diff is not None and depth_diff <= 2
                )
                possible = bool(
                    confirmed
                    or distance is not None and distance <= 500
                    and (number_match or name_match)
                    or distance is None and number_match and name_match
                )
                if not possible:
                    continue
                evidence = []
                if official:
                    evidence.append(self.t("EGT ma_orig_id kattub"))
                if cleaned:
                    evidence.append(self.t("korrastatud ID kattub"))
                if number_match:
                    evidence.append(self.t("number kattub"))
                if name_match:
                    evidence.append(self.t("nimi kattub"))
                if distance is not None:
                    evidence.append(f"{distance:.0f} m")
                if depth_diff is not None:
                    evidence.append(f"Δh {depth_diff:g} m")
                gea_id = attributes.get("gea_id")
                if gea_id not in (None, ""):
                    candidate["text"] = (
                        f"{candidate.get('text')} (GEA {gea_id})"
                    )
                candidate["evidence"] = " · ".join(evidence)
                candidate["confirmed"] = confirmed
                candidate["score"] = (
                    (5000 if official else 0)
                    + (2500 if cleaned else 0)
                    + (500 if number_match else 0)
                    + (550 if name_match else 0)
                    + (
                        max(0, 350 - distance * 0.4)
                        if distance is not None and distance <= 500 else 0
                    )
                )
                candidates.append(candidate)
            unique = {
                (item.get("role"), str(item.get("id"))): item
                for item in candidates
            }
            success(sorted(
                unique.values(),
                key=lambda item: -float(item.get("score") or 0),
            ))

        self.network.query_egt_candidates_for_maaru(
            row, loaded, failure,
        )

    def _load_maaru_point_details(
        self, identifier, name, attributes=None, prefer_egt=True,
    ):
        """Open a MaRu result, preferring its linked EGT combined view."""
        def ready(database):
            row = database.point(identifier)
            if not row:
                self.warning(self.t("MaRu puursüdamiku kirjet ei leitud."))
                return
            manual_links = self._manual_egt_links_for_maaru(identifier)
            loaded_links = self._loaded_egt_link_for_maaru(identifier, row)

            if prefer_egt and len(manual_links) == 1:
                self._open_manual_egt_link(
                    manual_links[0], self._detail_token, lambda _error: None,
                )
                return
            if prefer_egt and not manual_links and len(loaded_links) == 1:
                self._open_egt_candidate(loaded_links[0])
                return

            def show_maaru(public_links=None):
                overview = dict(row)
                overview.update({
                    "maaru_id": row.get("id"),
                    "nimi": row.get("nimetus") or row.get("number"),
                    "z_abs": row.get("z"),
                    "sygavus": row.get("sygavus"),
                    "_qeoloog_x_3301": row.get("_maaru_x"),
                    "_qeoloog_y_3301": row.get("_maaru_y"),
                })
                overview.update(attributes or {})
                self._detail_token += 1
                token = self._detail_token
                details = self.dock.details
                self.dock.show_details()
                details.show_loading(name, overview, "maaru_cores")
                self._set_maaru_record_data(token, row, details, database)
                if manual_links:
                    candidates = [{
                        "id": item.get("key_value"),
                        "text": (
                            f"{self.t('Kohalik parandus')}: "
                            f"{item.get('role')} {item.get('key_value')}"
                        ),
                        "confirmed": True,
                        "manual": True,
                        "link_record": item,
                    } for item in manual_links]
                    details.add_match_candidates(
                        "Kinnitatud EGT vaste", candidates,
                        open_callback=lambda candidate: self._open_manual_egt_link(
                            candidate.get("link_record"), token,
                            lambda _error: None,
                        ),
                    )
                else:
                    links = list(loaded_links or public_links or ())
                    if links:
                        # A match found in an already loaded EGT layer is an
                        # explicit ID link.  Public WFS discovery can also
                        # return weaker spatial/name candidates; do not present
                        # those as confirmed merely because they are shown in
                        # the same list.
                        confirmed = (
                            links if loaded_links else [
                                item for item in links
                                if item.get("confirmed")
                            ]
                        )
                        possible = (
                            [] if loaded_links else [
                                item for item in links
                                if not item.get("confirmed")
                            ]
                        )
                        if confirmed:
                            details.add_match_candidates(
                                "Kinnitatud EGT vaste", confirmed,
                                open_callback=self._open_egt_candidate,
                            )
                        if possible:
                            details.add_match_candidates(
                                "Võimalik EGT vaste", possible,
                                open_callback=self._open_egt_candidate,
                            )
                details.set_ready(name)
                if str(row.get("sarv_loc_id") or "").isdigit():
                    self._load_sarv_details(
                        token, {"sarv_id": row.get("sarv_loc_id")}, details,
                        lambda _label: (lambda _error: None),
                        trusted_sarv_id=True,
                    )
                else:
                    self._load_sarv_candidates_for_maaru(
                        token, row, details,
                    )

            if manual_links or loaded_links:
                show_maaru()
                return

            def public_loaded(public_links):
                confirmed = [
                    candidate for candidate in public_links
                    if candidate.get("confirmed")
                ]
                if prefer_egt and len(confirmed) == 1:
                    self._open_egt_candidate(confirmed[0])
                else:
                    show_maaru(public_links)

            self._query_egt_links_for_maaru(
                identifier, row, public_loaded, lambda _error: show_maaru(),
            )

        self._ensure_maaru_database(
            ready,
            lambda error: self.error(
                self.t("MaRu andmete laadimine ebaõnnestus") + f": {error}"
            ),
        )

    def _load_sarv_candidates_for_maaru(self, token, row, details):
        """Resolve a MaRu collar to SARV only from strong spatial evidence."""
        attributes = {
            "nimi": row.get("number"),
            "alias": row.get("nimetus"),
            "pikkus": row.get("sygavus"),
            "ma_orig_id": row.get("id"),
        }
        try:
            point = QgsCoordinateTransform(
                QgsCoordinateReferenceSystem("EPSG:3301"),
                QgsCoordinateReferenceSystem("EPSG:4326"),
                QgsProject.instance(),
            ).transform(QgsPointXY(
                float(row.get("_maaru_x")), float(row.get("_maaru_y")),
            ))
            attributes["_qeoloog_longitude"] = point.x()
            attributes["_qeoloog_latitude"] = point.y()
        except (QgsCsException, TypeError, ValueError):
            pass

        def loaded(localities, _sites, _drillcores):
            if token != self._detail_token:
                return
            candidates = [
                candidate for candidate in (
                    self._sarv_candidate(
                        locality, "locality", attributes,
                    )
                    for locality in localities
                ) if candidate
            ]
            candidates.sort(
                key=lambda item: -float(item.get("score") or 0)
            )
            confirmed = [
                candidate for candidate in candidates
                if candidate.get("confirmed")
            ]
            shown = confirmed if len(confirmed) == 1 else candidates[:5]
            if shown:
                details.add_match_candidates(
                    "Kinnitatud SARV vaste"
                    if len(confirmed) == 1 else "Võimalik SARV vaste",
                    shown,
                    open_callback=lambda candidate: self._load_sarv_point_details(
                        "sarv_localities",
                        str(candidate.get("text") or candidate.get("sarv_id")),
                        {
                            **dict(candidate.get("row") or {}),
                            "sarv_id": candidate.get("sarv_id"),
                        },
                        None, None,
                    ),
                )
            if len(confirmed) == 1:
                self._load_sarv_details(
                    token,
                    {"sarv_id": confirmed[0].get("sarv_id")},
                    details,
                    lambda _label: (lambda _error: None),
                    trusted_sarv_id=True,
                )

        self._ensure_sarv_point_cache(
            loaded,
            lambda _error: None,
        )

    def _load_maaru_details(self, token, attributes, details, failed, egt_role):
        """Resolve, manage and display an EGT object's MaRu relation."""
        match_key = self._egt_match_key(egt_role, attributes)

        def ready(database):
            if token != self._detail_token:
                return

            def saved_record():
                value = self.sarv_matches.get(match_key) if match_key else None
                return value if isinstance(value, dict) else {}

            def open_candidate(candidate):
                identifier = str(candidate.get("maaru_id") or "")
                if identifier:
                    self._load_maaru_point_details(
                        identifier,
                        str(candidate.get("text") or identifier),
                        prefer_egt=False,
                    )

            def keep_record(value):
                has_sarv = (
                    value.get("source_type") in {"drillcore", "locality", "site"}
                    and str(value.get("sarv_id") or "").strip()
                )
                has_maaru = str(value.get("maaru_id") or "").strip()
                if has_sarv or has_maaru or value.get("invalid_sarv_id") or value.get("invalid_ma_id"):
                    self.sarv_matches[match_key] = value
                else:
                    self.sarv_matches.pop(match_key, None)
                PluginSettings.save_sarv_matches(self.sarv_matches)

            def render(preferred=None):
                if token != self._detail_token:
                    return
                details.reset_maaru_match_rows()
                details.set_maaru_overview({})
                details.set_maaru_core([])
                details.set_maaru_profile([])
                details.set_maaru_samples([])
                details.set_maaru_attachments([])
                saved = saved_record()
                manual_id = str(saved.get("maaru_id") or "").strip()
                source_id = str(attributes.get("ma_orig_id") or "").strip()
                invalid = bool(saved.get("invalid_ma_id"))
                effective_id = manual_id or ("" if invalid else source_id)
                details.add_maaru_match_editor(
                    effective_id, bool(manual_id), set_manual,
                    reset_manual if manual_id else None,
                    source_ma_id=source_id,
                    invalid_ma_id=invalid,
                    invalid_callback=set_invalid,
                )
                row = preferred or (
                    database.point(effective_id) if effective_id else None
                )
                if row:
                    candidate = self._maaru_candidate(row, bool(manual_id))
                    candidate["confirmed"] = True
                    details.add_match_candidates(
                        "Kinnitatud MaRu vaste", [candidate],
                        open_callback=open_candidate,
                    )
                    self._set_maaru_record_data(token, row, details, database)
                    return
                candidates = database.candidates(
                    attributes, invalid_source_id=invalid,
                )
                confirmed = [
                    self._maaru_candidate(row) for row in candidates
                    if float(row.get("_score") or 0) >= 1200
                ]
                if len(confirmed) == 1:
                    confirmed[0]["confirmed"] = True
                    details.add_match_candidates(
                        "Kinnitatud MaRu vaste", confirmed,
                        open_callback=open_candidate,
                        confirm_callback=confirm_candidate,
                    )
                    self._set_maaru_record_data(
                        token, confirmed[0]["row"], details, database,
                    )
                elif candidates:
                    details.add_match_candidates(
                        "Võimalik MaRu vaste",
                        [self._maaru_candidate(row) for row in candidates],
                        open_callback=open_candidate,
                        confirm_callback=confirm_candidate,
                    )

            def set_manual(identifier):
                row = database.point(identifier)
                if not row:
                    self.warning(self.t(
                        "Sellise ID-ga MaRu puursüdamikku ei leitud."
                    ))
                    return
                value = dict(saved_record())
                value.update({
                    "maaru_id": str(identifier),
                    "gea_id": str(attributes.get("gea_id") or ""),
                    "original_ma_id": str(attributes.get("ma_orig_id") or ""),
                    "source": "local_override",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                keep_record(value)
                self.success(self.t("MaRu vaste salvestati kohalikult."))
                render(row)

            def reset_manual():
                value = dict(saved_record())
                value.pop("maaru_id", None)
                value["invalid_ma_id"] = False
                value["updated_at"] = datetime.now(timezone.utc).isoformat()
                keep_record(value)
                self.success(self.t("EGT MaRu seos taastati."))
                render()

            def set_invalid(checked):
                value = dict(saved_record())
                value["invalid_ma_id"] = bool(checked)
                value.update({
                    "original_ma_id": str(attributes.get("ma_orig_id") or ""),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                keep_record(value)
                self.success(self.t("Vigase ID märge salvestati"))
                render()

            def confirm_candidate(candidate):
                set_manual(candidate.get("maaru_id"))

            render()

        self._ensure_maaru_database(
            ready,
            lambda error: failed("MaRu")(error),
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
                            "trusted_link": direct or explicit,
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

    def _load_details(
        self, role, global_id, name, attributes, *, faktika_parent=None,
        faktika_geometry=None, faktika_workspace="faktika",
    ):
        attributes = self._detail_attributes_with_location(attributes)
        if faktika_parent is not None:
            attributes["_qeoloog_section_private_source"] = True
            attributes["_qeoloog_section_workspace"] = faktika_workspace
        self._current_faktika_context = None
        self._detail_token += 1
        token = self._detail_token
        self._detail_warning_token = None
        details = self.dock.details
        self.dock.show_details()
        details.show_loading(name, attributes, role)
        self._resolve_faktika_context(
            token, role, global_id, attributes,
            parent=faktika_parent, geometry=faktika_geometry,
            workspace_key=faktika_workspace,
        )
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

        def profile_loaded(units):
            details.set_profile(units)
            key = str(global_id).strip().upper()
            summary = egt_label_summary(units)
            self._egt_map_label_loaded_ids[role].add(key)
            if summary:
                self._egt_map_label_details[role][key] = summary
            else:
                self._egt_map_label_details[role].pop(key, None)
            if role == "observations":
                # Opening one point can complete before the country-wide
                # label lookup; make that point's exact label available now.
                self._observation_labels[key] = observation_label(units)
                for layer in self._role_layers("observations"):
                    self._apply_observation_labeling(layer)
            else:
                for layer in self._role_layers("boreholes"):
                    self._apply_borehole_labeling(layer)

        def load_profile_from_api(wfs_error):
            if token != self._detail_token:
                return
            if role != "boreholes":
                details._local_profile_status = 'failed'
                failed(self.t("Läbilõige"))(wfs_error)
                return

            def gea_failed(gea_error):
                if token == self._detail_token:
                    details._local_profile_status = 'failed'
                failed(self.t("Läbilõige"))(f"{wfs_error}; {gea_error}")

            self.network.query_borehole_profile(
                global_id,
                current(profile_loaded),
                gea_failed,
            )

        def load_profile_from_wfs(api_error):
            if token != self._detail_token:
                return

            def wfs_failed(wfs_error):
                if token == self._detail_token:
                    details._local_profile_status = 'failed'
                failed(self.t("Läbilõige"))(f"{api_error}; {wfs_error}")

            self.network.query_geological_units(
                role,
                global_id,
                current(profile_loaded),
                wfs_failed,
            )

        if self.egt_data_source == "api" and role == "boreholes":
            self.network.query_borehole_profile(
                global_id,
                current(profile_loaded),
                load_profile_from_wfs,
            )
        else:
            self.network.query_geological_units(
                role,
                global_id,
                current(profile_loaded),
                load_profile_from_api,
            )

        self._load_sarv_details(
            token, attributes, details, failed, egt_role=role,
        )
        self._load_maaru_details(
            token, attributes, details, failed, role,
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
            details.set_sarv_attachments([])
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
                    details.set_sarv_attachments([])
                    return
                queue = list(cores)
                boxes = []

                def finish_boxes():
                    details.set_sarv_core(boxes)
                    box_ids = [str(row.get("id")) for row in boxes if row.get("id")]
                    if not box_ids:
                        details.set_sarv_core_images([])
                        details.set_sarv_attachments([])
                        return

                    def attachments_loaded(data):
                        rows = self._sarv_rows(data)
                        details.set_sarv_core_images(rows)
                        details.set_sarv_attachments(rows)

                    self.network.query_sarv(
                        "attachments",
                        {
                            "drillcore_boxes__in": ",".join(box_ids),
                            "expand": "*",
                            "limit": 2000,
                        },
                        current(attachments_loaded),
                        request_failed(
                            "SARV drill core images",
                            lambda: (
                                details.set_sarv_core_images([]),
                                details.set_sarv_attachments([]),
                            ),
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
                or bool(str(value.get("maaru_id") or "").strip())
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
                source_ma_id="",
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
            if candidate.get("conflict") and not manual:
                candidate["confirmed"] = False
                details.add_match_candidates(
                    "Võimalik SARV vaste", [candidate], open_candidate,
                    confirm_callback=confirm_candidate,
                )
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
                    candidate["confirmed"] = not candidate.get("conflict", False)
                    candidate["score"] = max(candidate.get("score", 0), 5000)
                    if not candidate.get("conflict"):
                        candidate["evidence"] = self.t("GEA SARV ID")
                    candidates.append(candidate)
                    direct_core_candidate = candidate
        candidates.sort(key=lambda item: item["score"], reverse=True)
        if direct_core_candidate:
            for item in candidates:
                item["confirmed"] = item is direct_core_candidate and not item.get("conflict", False)
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
        location = row.get("locality") if isinstance(row.get("locality"), dict) else {}
        distance = self._point_distance_m(
            attributes.get("_qeoloog_latitude"),
            attributes.get("_qeoloog_longitude"),
            row.get("latitude") if row.get("latitude") is not None else location.get("latitude"),
            row.get("longitude") if row.get("longitude") is not None else location.get("longitude"),
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

        # A source ID is evidence, not permission to combine a different hole.
        conflict = bool(explicit_match and distance is not None and distance > 1000)

        confirmed = bool(
            official_match
            or distance is not None and distance <= 500
            and number_match and descriptive_name_match
            or distance is not None and distance <= 25 and number_match
            or distance is not None and distance <= 10
            and depth_diff is not None and depth_diff <= 1
            or explicit_match and distance is not None and distance <= 50
        )
        possible = bool(
            confirmed
            or distance is not None and distance <= 500 and (
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
        if conflict:
            confirmed = False
            evidence.append(self.t("Asukohakonflikt — kinnita seos käsitsi"))
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
            "conflict": conflict,
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
