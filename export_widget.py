"""Leapfrog-compatible spatial export page for Qeoloog."""

import csv
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)

from .leapfrog import (
    compound_index,
    hole_identifier,
    interval_row,
    latest_row,
    number,
    safe_column,
    vertical_survey,
)
from .veka import (
    aggregate as veka_aggregate,
    analysis_row_value,
    cadastral_number as veka_cadastral_number,
    specific_capacity,
)


METRIC_CRS = QgsCoordinateReferenceSystem("EPSG:3301")
COLLAR_BASE_FIELDS = (
    "HoleID", "East", "North", "Elevation", "TotalDepth",
    "Source", "SourceID", "Name", "CRS",
)
SURVEY_FIELDS = ("HoleID", "Depth", "Azimuth", "Dip")
INTERVAL_FIELDS = (
    "HoleID", "From", "To", "Lithology", "Stratigraphy",
    "Source", "IntervalType", "Description",
)


class ExportWidget(QWidget):
    """Select a polygon and export loaded Qeoloog point layers to CSV."""

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.area = None
        self.area_label = ""
        self._export_generation = 0
        self._analysis_options = []
        self._build_ui()

    def _build_ui(self):
        t = self.plugin.t
        layout = QVBoxLayout(self)

        area_group = QGroupBox(t("Ekspordi ala"))
        area_layout = QVBoxLayout(area_group)
        area_buttons = QHBoxLayout()
        draw = QPushButton(t("Joonista ala kaardil"))
        draw.clicked.connect(self.plugin.start_export_area)
        load = QPushButton(t("Vali polygon-fail"))
        load.clicked.connect(self.load_polygon_file)
        clear = QPushButton(t("Tühjenda ala"))
        clear.clicked.connect(self.clear_area)
        area_buttons.addWidget(draw)
        area_buttons.addWidget(load)
        area_buttons.addWidget(clear)
        area_layout.addLayout(area_buttons)
        self.area_status = QLabel(t("Ekspordi ala pole valitud."))
        self.area_status.setWordWrap(True)
        area_layout.addWidget(self.area_status)
        layout.addWidget(area_group)

        source_group = QGroupBox(t("Andmeallikad"))
        source_layout = QHBoxLayout(source_group)
        self.sources = {}
        for key, label in (
            ("EGT", "EGT (PA ja VP)"),
            ("SARV", "SARV (puursüdamikud)"),
            ("VEKA", "VEKA (puurkaevud)"),
        ):
            checkbox = QCheckBox(t(label))
            checkbox.setChecked(True)
            self.sources[key] = checkbox
            source_layout.addWidget(checkbox)
        layout.addWidget(source_group)

        format_group = QGroupBox(t("Leapfrog CSV"))
        format_form = QFormLayout(format_group)
        self.target_crs = QLineEdit("EPSG:3301")
        self.target_crs.setToolTip(t(
            "Koordinaadid kirjutatakse valitud CRS-i; Leapfrogis tuleb "
            "määrata sama koordinaatsüsteem."
        ))
        format_form.addRow(t("Väljundi CRS"), self.target_crs)
        note = QLabel(t(
            "Luuakse collar.csv, survey.csv ja interval.csv. "
            "Puuduva kalde ja asimuudiga puuraugud eksporditakse "
            "vertikaalselt alla (Dip 90°, Azimuth 0°)."
        ))
        note.setWordWrap(True)
        format_form.addRow(note)
        layout.addWidget(format_group)

        veka_group = QGroupBox(t("VEKA lisaväljad"))
        veka_layout = QVBoxLayout(veka_group)
        option_row = QHBoxLayout()
        self.static_water = QCheckBox(t("Staatiline veetase"))
        self.specific_capacity = QCheckBox(t("Eritootlikkus"))
        option_row.addWidget(self.static_water)
        option_row.addWidget(self.specific_capacity)
        veka_layout.addLayout(option_row)
        analysis_header = QHBoxLayout()
        analysis_header.addWidget(QLabel(t("Veeanalüüside näitajad")))
        load_analyses = QPushButton(t("Laadi näitajad"))
        load_analyses.clicked.connect(
            self.plugin.ensure_veka_analysis_options
        )
        analysis_header.addWidget(load_analyses)
        veka_layout.addLayout(analysis_header)
        self.analysis_search = QLineEdit()
        self.analysis_search.setPlaceholderText(t("Filtreeri näitajaid"))
        self.analysis_search.textChanged.connect(self._filter_analyses)
        veka_layout.addWidget(self.analysis_search)
        self.analyses = QListWidget()
        self.analyses.setMinimumHeight(150)
        veka_layout.addWidget(self.analyses)
        self.analysis_mode = QComboBox()
        for label, value in (
            ("Uusim tulemus", "latest"),
            ("Suurim tulemus", "max"),
            ("Väikseim tulemus", "min"),
            ("Keskmine tulemus", "mean"),
        ):
            self.analysis_mode.addItem(t(label), value)
        veka_layout.addWidget(self.analysis_mode)
        layout.addWidget(veka_group)

        self.export_button = QPushButton(t("Ekspordi Leapfrog CSV"))
        self.export_button.clicked.connect(self.choose_output_and_export)
        layout.addWidget(self.export_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        corrections_group = QGroupBox(t("Kohalikud andmeparandused"))
        corrections_layout = QVBoxLayout(corrections_group)
        correction_note = QLabel(t(
            "Puursüdamiku kastide kohalikud parandused ei muuda EGT ega "
            "SARV andmebaasi."
        ))
        correction_note.setWordWrap(True)
        corrections_layout.addWidget(correction_note)
        self.corrections_status = QLabel()
        corrections_layout.addWidget(self.corrections_status)
        export_corrections = QPushButton(
            t("Ekspordi puursüdamiku parandused…")
        )
        export_corrections.clicked.connect(self.choose_corrections_export)
        corrections_layout.addWidget(export_corrections)
        layout.addWidget(corrections_group)
        self.refresh_corrections_count()
        layout.addStretch(1)

    def refresh_corrections_count(self):
        count = len(getattr(self.plugin, "core_corrections", {}))
        self.corrections_status.setText(
            f"{self.plugin.t('Salvestatud parandusi')}: {count}"
        )

    def choose_corrections_export(self):
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            self.plugin.t("Ekspordi puursüdamiku parandused"),
            "qeoloog_puursydamiku_parandused.json",
            "JSON (*.json);;CSV (*.csv)",
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".csv" if "CSV" in selected_filter else ".json"
        self.plugin.export_core_corrections(path)

    def set_veka_analysis_options(self, options):
        selected = set(self.selected_analyses())
        self._analysis_options = list(options or ())
        self.analyses.clear()
        for key, label in self._analysis_options:
            item = QListWidgetItem(str(label))
            item.setData(Qt.ItemDataRole.UserRole, str(key))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if str(key) in selected else Qt.CheckState.Unchecked
            )
            self.analyses.addItem(item)
        self._filter_analyses(self.analysis_search.text())

    def selected_analyses(self):
        return [
            str(self.analyses.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.analyses.count())
            if self.analyses.item(index).checkState()
            == Qt.CheckState.Checked
        ]

    def analysis_labels(self):
        return {
            str(self.analyses.item(index).data(Qt.ItemDataRole.UserRole)):
            self.analyses.item(index).text()
            for index in range(self.analyses.count())
        }

    def _filter_analyses(self, text):
        needle = str(text or "").strip().casefold()
        for index in range(self.analyses.count()):
            item = self.analyses.item(index)
            item.setHidden(bool(needle and needle not in item.text().casefold()))

    def set_area(self, geometry, label):
        if not geometry or geometry.isEmpty():
            return
        self.area = QgsGeometry(geometry)
        self.area_label = str(label or self.plugin.t("Valitud ala"))
        area_km2 = self.area.area() / 1_000_000
        self.area_status.setText(
            f"{self.area_label} · {area_km2:.2f} km²"
        )
        self.plugin.update_export_area_band(self.area)

    def clear_area(self):
        self.area = None
        self.area_label = ""
        self.area_status.setText(self.plugin.t("Ekspordi ala pole valitud."))
        self.plugin.update_export_area_band(None)

    def load_polygon_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.plugin.t("Vali polygon-fail"), "",
            (
                "Vector files (*.gpkg *.shp *.geojson *.json *.kml);;"
                "All files (*.*)"
            ),
        )
        if not path:
            return
        layer = QgsVectorLayer(path, Path(path).stem, "ogr")
        if not layer.isValid():
            QMessageBox.warning(
                self, self.plugin.t("Ekspordi ala"),
                self.plugin.t("Polygon-faili ei õnnestunud avada."),
            )
            return
        if layer.geometryType() != Qgis.GeometryType.Polygon:
            QMessageBox.warning(
                self, self.plugin.t("Ekspordi ala"),
                self.plugin.t("Valitud fail ei ole polygonkiht."),
            )
            return
        transform = QgsCoordinateTransform(
            layer.crs(), METRIC_CRS, QgsProject.instance()
        )
        geometries = []
        for feature in layer.getFeatures():
            geometry = QgsGeometry(feature.geometry())
            try:
                geometry.transform(transform)
            except QgsCsException:
                continue
            if not geometry.isEmpty():
                geometries.append(geometry)
        if not geometries:
            QMessageBox.warning(
                self, self.plugin.t("Ekspordi ala"),
                self.plugin.t("Polygon-failis ei ole kasutatavat ala."),
            )
            return
        self.set_area(
            QgsGeometry.unaryUnion(geometries),
            f"{self.plugin.t('Fail')}: {Path(path).name}",
        )

    def choose_output_and_export(self):
        if not self.area or self.area.isEmpty():
            QMessageBox.warning(
                self, self.plugin.t("Eksport"),
                self.plugin.t("Vali esmalt ekspordi ala."),
            )
            return
        if not any(checkbox.isChecked() for checkbox in self.sources.values()):
            QMessageBox.warning(
                self, self.plugin.t("Eksport"),
                self.plugin.t("Vali vähemalt üks andmeallikas."),
            )
            return
        folder = QFileDialog.getExistingDirectory(
            self, self.plugin.t("Vali ekspordi kaust")
        )
        if not folder:
            return
        targets = [
            Path(folder) / name
            for name in ("collar.csv", "survey.csv", "interval.csv")
        ]
        if any(path.exists() for path in targets) and QMessageBox.question(
            self, self.plugin.t("Eksport"),
            self.plugin.t("Ekspordifailid on juba olemas. Kas kirjutada üle?"),
        ) != QMessageBox.StandardButton.Yes:
            return
        self.start_export(Path(folder))

    def start_export(self, folder):
        target_crs = QgsCoordinateReferenceSystem(self.target_crs.text().strip())
        if not target_crs.isValid():
            QMessageBox.warning(
                self, self.plugin.t("Eksport"),
                self.plugin.t("Väljundi CRS ei ole kehtiv."),
            )
            return
        records, collection_warnings = self._collect_records(target_crs)
        if not records:
            self.status.setText(self.plugin.t(
                "Valitud alast ei leitud valitud allikate objekte. "
                "Kontrolli, et vastavad kihid on projekti laaditud."
            ))
            return
        self._export_generation += 1
        generation = self._export_generation
        self.export_button.setEnabled(False)
        state = {
            "folder": Path(folder),
            "crs": target_crs.authid() or self.target_crs.text().strip(),
            "records": records,
            "intervals": [],
            "warnings": list(collection_warnings),
            "index": 0,
            "generation": generation,
            "analysis_columns": {},
            "include_static_water": self.static_water.isChecked(),
            "include_specific_capacity": self.specific_capacity.isChecked(),
            "analyses": self.selected_analyses(),
            "analysis_labels": self.analysis_labels(),
            "analysis_mode": self.analysis_mode.currentData(),
        }
        self._load_next_record(state)

    def cancel_pending(self):
        self._export_generation += 1
        self.export_button.setEnabled(True)

    def _collect_records(self, target_crs):
        roles = []
        if self.sources["EGT"].isChecked():
            roles.extend(("boreholes", "observations"))
        if self.sources["SARV"].isChecked():
            roles.append("sarv_drillcores")
        if self.sources["VEKA"].isChecked():
            roles.append("veka_boreholes")
        records = []
        warnings = []
        seen = set()
        role_sources = {
            "boreholes": "EGT", "observations": "EGT",
            "sarv_drillcores": "SARV", "veka_boreholes": "VEKA",
        }
        for role in roles:
            layers = self.plugin._role_layers(role)
            if not layers:
                warnings.append(
                    f"{role}: {self.plugin.t('kiht ei ole laaditud')}"
                )
                continue
            for layer in layers:
                to_metric = QgsCoordinateTransform(
                    layer.crs(), METRIC_CRS, QgsProject.instance()
                )
                to_target = QgsCoordinateTransform(
                    layer.crs(), target_crs, QgsProject.instance()
                )
                for feature in layer.getFeatures():
                    source_geometry = QgsGeometry(feature.geometry())
                    metric_geometry = QgsGeometry(source_geometry)
                    try:
                        metric_geometry.transform(to_metric)
                    except QgsCsException:
                        continue
                    if not self.area.intersects(metric_geometry):
                        continue
                    attributes = {
                        field.name(): feature.attribute(field.name())
                        for field in layer.fields()
                    }
                    source = role_sources[role]
                    hole_id = hole_identifier(source, role, attributes)
                    if hole_id in seen:
                        continue
                    seen.add(hole_id)
                    target_geometry = QgsGeometry(source_geometry)
                    try:
                        target_geometry.transform(to_target)
                    except QgsCsException:
                        continue
                    point = self._geometry_point(target_geometry)
                    source_point = self._geometry_point(source_geometry)
                    if point is None:
                        continue
                    elevation = self._elevation(
                        source, attributes, source_point
                    )
                    depth = self._depth(source, attributes)
                    name = (
                        attributes.get("nimi")
                        or attributes.get("name")
                        or attributes.get("number")
                        or attributes.get("kkr_kood")
                        or hole_id
                    )
                    source_id = (
                        attributes.get("gea_id")
                        if source == "EGT" else
                        attributes.get("eelis_id")
                        if source == "VEKA" else
                        attributes.get("sarv_id")
                    )
                    collar = {
                        "HoleID": hole_id,
                        "East": point.x(),
                        "North": point.y(),
                        "Elevation": "" if elevation is None else elevation,
                        "TotalDepth": "" if depth is None else depth,
                        "Source": source,
                        "SourceID": "" if source_id is None else source_id,
                        "Name": name,
                        "CRS": target_crs.authid(),
                    }
                    records.append({
                        "hole_id": hole_id,
                        "role": role,
                        "source": source,
                        "attributes": attributes,
                        "collar": collar,
                        "survey": self._survey(hole_id, attributes),
                    })
        records.sort(key=lambda row: (
            row["source"], row["hole_id"].casefold()
        ))
        return records, warnings

    @staticmethod
    def _geometry_point(geometry):
        if not geometry or geometry.isEmpty():
            return None
        if geometry.type() == Qgis.GeometryType.Point:
            point = geometry.constGet()
            if hasattr(point, "x"):
                return point
        centroid = geometry.centroid()
        return centroid.constGet() if not centroid.isEmpty() else None

    @staticmethod
    def _elevation(source, attributes, point):
        candidates = (
            ("z_abs", "elevation", "altitude", "height")
            if source != "EGT" else
            ("z_abs", "elevation", "altitude")
        )
        for key in candidates:
            value = number(attributes.get(key))
            if value is not None:
                return value
        if point is not None and hasattr(point, "z"):
            return number(point.z())
        return None

    @staticmethod
    def _depth(source, attributes):
        keys = (
            ("sygavus", "depth") if source == "VEKA"
            else ("depth", "pikkus") if source == "SARV"
            else ("pikkus", "vertikaalne_ulatus", "depth")
        )
        for key in keys:
            value = number(attributes.get(key))
            if value is not None:
                return value
        return None

    @staticmethod
    def _survey(hole_id, attributes):
        dip = number(attributes.get("dip"))
        azimuth = number(
            attributes.get("azimuth") or attributes.get("asimuut")
        )
        if dip is None or azimuth is None:
            return vertical_survey(hole_id)
        return {
            "HoleID": hole_id, "Depth": 0.0,
            "Azimuth": azimuth % 360, "Dip": dip,
        }

    def _load_next_record(self, state):
        if state["generation"] != self._export_generation:
            return
        records = state["records"]
        index = state["index"]
        if index >= len(records):
            self._load_analyses(state, 0)
            return
        record = records[index]
        self.status.setText(
            f"{self.plugin.t('Seotud andmeid laaditakse')} "
            f"{index + 1}/{len(records)} · {record['hole_id']}"
        )

        def completed():
            state["index"] += 1
            self._load_next_record(state)

        def failed(label):
            def handler(error):
                state["warnings"].append(
                    f"{record['hole_id']} · {label}: {error}"
                )
                completed()
            return handler

        if record["source"] == "EGT":
            global_id = record["attributes"].get("esri_globalid")
            if not global_id:
                completed()
                return

            def units_loaded(rows):
                self._append_egt_intervals(state, record, rows)
                completed()

            def wfs_failed(error):
                if record["role"] != "boreholes":
                    failed("EGT intervals")(error)
                    return
                self.plugin.network.query_borehole_profile(
                    global_id, units_loaded, failed("EGT intervals")
                )

            self.plugin.network.query_geological_units(
                record["role"], global_id, units_loaded, wfs_failed
            )
            return

        if record["source"] == "SARV":
            identifier = record["attributes"].get("sarv_id")
            if not identifier:
                completed()
                return

            def boxes_loaded(payload):
                rows = self._sarv_rows(payload)
                for row in rows:
                    lower = str(
                        row.get("stratigraphy_base_text") or ""
                    ).strip()
                    upper = str(
                        row.get("stratigraphy_top_text") or ""
                    ).strip()
                    stratigraphy = str(
                        row.get("stratigraphy_text") or ""
                    ).strip()
                    if not stratigraphy:
                        stratigraphy = (
                            f"{lower}-{upper}"
                            if lower and upper and lower != upper
                            else lower or upper
                        )
                    prepared = interval_row(
                        record["hole_id"],
                        row.get("depth_start"),
                        row.get("depth_end"),
                        stratigraphy=stratigraphy,
                        source="SARV",
                        interval_type="DrillcoreBox",
                        description=(
                            row.get("remarks") or row.get("depth_text")
                            or row.get("number") or row.get("name")
                            or row.get("id") or ""
                        ),
                    )
                    if prepared:
                        state["intervals"].append(prepared)
                completed()

            self.plugin.network.query_sarv(
                f"drillcores/{identifier}/drillcore-boxes",
                {"limit": 2000, "ordering": "depth_start"},
                boxes_loaded, failed("SARV drill-core boxes"),
            )
            return

        identifier = record["attributes"].get("eelis_id")
        if identifier in (None, ""):
            completed()
            return

        def geology_loaded(rows):
            for row in rows:
                prepared = interval_row(
                    record["hole_id"], row.get("lasum"), row.get("lamam"),
                    row.get("kivim_nimetus"), row.get("geol_vanus"),
                    "VEKA", "Geology",
                )
                if prepared:
                    state["intervals"].append(prepared)
            if (
                state["include_static_water"]
                or state["include_specific_capacity"]
            ):
                self._load_veka_hydro(state, record, identifier, completed)
            else:
                completed()

        def geology_failed(error):
            state["warnings"].append(
                f"{record['hole_id']} · VEKA geology: {error}"
            )
            if (
                state["include_static_water"]
                or state["include_specific_capacity"]
            ):
                self._load_veka_hydro(
                    state, record, identifier, completed
                )
            else:
                completed()

        self.plugin.network.query_eelis_pages(
            "f_puuraugud_labiloige",
            {
                "labil_puurauk_id": f"eq.{identifier}",
                "order": "jrk_nr.asc",
            },
            (
                "jrk_nr", "geol_vanus", "kivim_nimetus",
                "lasum", "lamam", "paksus",
            ),
            geology_loaded, geology_failed, limit=2000,
        )

    def _load_veka_hydro(self, state, record, identifier, completed):
        def loaded(rows):
            collar = record["collar"]
            if state["include_static_water"]:
                row = latest_row(rows, "st_veetase")
                value = number(row.get("st_veetase")) if row else None
                collar["StaticWaterDepth_m"] = (
                    "" if value is None else value
                )
                elevation = number(collar.get("Elevation"))
                collar["StaticWaterElevation_m"] = (
                    "" if value is None or elevation is None
                    else elevation - value
                )
            if state["include_specific_capacity"]:
                value = veka_aggregate(
                    rows, specific_capacity, "latest",
                    date_field="katse_kp",
                )
                collar["SpecificCapacity_L_s_m"] = (
                    "" if value is None else value
                )
            completed()

        def failed(error):
            state["warnings"].append(
                f"{record['hole_id']} · VEKA hydro: {error}"
            )
            completed()

        self.plugin.network.query_eelis_pages(
            "f_puuraugud_puurauk_param",
            {
                "param_puurauk_id": f"eq.{identifier}",
                "order": "katse_kp.desc",
            },
            (
                "st_veetase", "deebit", "alandus", "katse_kp",
            ),
            loaded, failed, limit=2000,
        )

    @staticmethod
    def _append_egt_intervals(state, record, rows):
        for row in rows or ():
            prepared = interval_row(
                record["hole_id"],
                row.get("z_suht_ylemine"),
                row.get("z_suht_alumine"),
                row.get("litoloogia") or row.get("litoloogia_orig"),
                compound_index(row),
                "EGT", "Geology",
            )
            if prepared:
                state["intervals"].append(prepared)

    @staticmethod
    def _sarv_rows(payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        return (
            payload.get("results")
            or payload.get("data")
            or payload.get("features")
            or []
        )

    def _load_analyses(self, state, index):
        selections = state["analyses"]
        if index >= len(selections):
            self._write_export(state)
            return
        key = selections[index]
        label = state["analysis_labels"].get(key, key)
        column = "WQ_" + safe_column(label)
        used = set(state["analysis_columns"].values())
        base = column
        suffix = 2
        while column in used:
            column = f"{base}_{suffix}"
            suffix += 1
        state["analysis_columns"][key] = column
        self.status.setText(
            f"{self.plugin.t('Veeanalüüse laaditakse')} "
            f"{index + 1}/{len(selections)} · {label}"
        )

        def loaded(rows):
            mode = state["analysis_mode"]
            for record in state["records"]:
                if record["source"] != "VEKA":
                    continue
                attributes = record["attributes"]
                cadastral = veka_cadastral_number(
                    attributes.get("katastri_nr"),
                    attributes.get("kkr_kood"),
                )
                relevant = [
                    row for row in rows
                    if str(row.get("katastri_number") or "").strip()
                    == str(cadastral or "").strip()
                ]
                value = veka_aggregate(
                    relevant,
                    lambda row: analysis_row_value(row, key),
                    mode,
                    date_field="proov_algus",
                )
                record["collar"][column] = (
                    "" if value is None else value
                )
            self._load_analyses(state, index + 1)

        self.plugin._ensure_veka_analysis(key, loaded)

    def _write_export(self, state):
        folder = state["folder"]
        try:
            folder.mkdir(parents=True, exist_ok=True)
            collar_fields = list(COLLAR_BASE_FIELDS)
            if state["include_static_water"]:
                collar_fields.extend((
                    "StaticWaterDepth_m", "StaticWaterElevation_m",
                ))
            if state["include_specific_capacity"]:
                collar_fields.append("SpecificCapacity_L_s_m")
            collar_fields.extend(state["analysis_columns"].values())
            self._write_csv(
                folder / "collar.csv", collar_fields,
                [record["collar"] for record in state["records"]],
            )
            self._write_csv(
                folder / "survey.csv", SURVEY_FIELDS,
                [record["survey"] for record in state["records"]],
            )
            self._write_csv(
                folder / "interval.csv", INTERVAL_FIELDS,
                sorted(state["intervals"], key=lambda row: (
                    row["HoleID"], row["From"], row["To"]
                )),
            )
            self._write_report(folder / "export_report.txt", state)
        except OSError as error:
            self.export_button.setEnabled(True)
            self.status.setText(
                f"{self.plugin.t('Eksport ebaõnnestus')}: {error}"
            )
            return
        self.export_button.setEnabled(True)
        missing_elevation = sum(
            number(record["collar"].get("Elevation")) is None
            for record in state["records"]
        )
        message = (
            f"{self.plugin.t('Eksporditud')}: "
            f"{len(state['records'])} Collar · "
            f"{len(state['records'])} Survey · "
            f"{len(state['intervals'])} Interval"
        )
        if missing_elevation:
            message += (
                f" · {missing_elevation} "
                + self.plugin.t("objektil puudub absoluutkõrgus")
            )
        if state["warnings"]:
            message += (
                f" · {len(state['warnings'])} "
                + self.plugin.t("hoiatust")
            )
        self.status.setText(message)
        QMessageBox.information(
            self, self.plugin.t("Eksport"), message
        )

    @staticmethod
    def _write_csv(path, fieldnames, rows):
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=fieldnames, extrasaction="ignore"
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    key: ExportWidget._csv_value(row.get(key))
                    for key in fieldnames
                })

    @staticmethod
    def _csv_value(value):
        if isinstance(value, float):
            return format(value, ".12g")
        return "" if value is None else value

    def _write_report(self, path, state):
        missing = [
            record["hole_id"] for record in state["records"]
            if number(record["collar"].get("Elevation")) is None
        ]
        lines = [
            "Qeoloog Leapfrog export",
            f"CRS: {state['crs']}",
            f"Area: {self.area_label}",
            f"Collar rows: {len(state['records'])}",
            f"Survey rows: {len(state['records'])}",
            f"Interval rows: {len(state['intervals'])}",
            (
                "Survey convention: Dip +90 = vertically down "
                "(Leapfrog default; negative dip points up)."
            ),
            "",
            f"Missing elevations ({len(missing)}):",
            *missing,
            "",
            f"Warnings ({len(state['warnings'])}):",
            *state["warnings"],
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
