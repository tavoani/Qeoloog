"""Read-only report outlines and a transient spatial filter for public PA layers."""
import json
import re

from qgis.PyQt.QtCore import QUrl, QUrlQuery
from qgis.core import (
    Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsCsException,
    QgsGeometry, QgsJsonUtils, QgsProject, QgsVectorLayer,
)


def report_number(value):
    text = str(value if value is not None else "").strip()
    if not re.fullmatch(r"[0-9]{1,12}(?:\.0+)?", text):
        return ""
    number = int(text.split(".")[0])
    return str(number) if number > 0 else ""


class ArchiveReportsMixin:
    ARCHIVE_REPORT_PROPERTY = "qeoloog/archive_report_id"

    def _init_archive_reports(self):
        self._archive_report_cache = {}
        self._archive_report_waiters = {}
        self._archive_report_actions = {}
        self._archive_report_filter = self._read_archive_report_filter()

    def _read_archive_report_filter(self):
        try:
            text = QgsProject.instance().readEntry("Qeoloog", "archive_report_filter_v1", "")[0]
            value = json.loads(text) if text else {}
            number = report_number(value.get("number"))
            geometry = QgsGeometry.fromWkt(value.get("wkt", ""))
            if number and not geometry.isEmpty() and geometry.type() == Qgis.GeometryType.Polygon and geometry.isGeosValid():
                return {"number": number, "geometry": geometry, "expressions": {}}
        except (AttributeError, TypeError, ValueError):
            pass
        return None

    def _save_archive_report_filter(self):
        active = self._archive_report_filter
        if active:
            QgsProject.instance().writeEntry("Qeoloog", "archive_report_filter_v1", json.dumps({"number": active["number"], "wkt": active["geometry"].asWkt()}))
        else:
            QgsProject.instance().removeEntry("Qeoloog", "archive_report_filter_v1")

    def _restore_archive_reports(self, *_args):
        self._archive_report_actions.clear()
        self._archive_report_waiters.clear()
        self._archive_report_cache.clear()
        self._archive_report_filter = self._read_archive_report_filter()
        self.apply_egt_filters()
        self._refresh_archive_report_controls()

    def _reset_archive_reports(self):
        self._archive_report_actions.clear()
        self._archive_report_waiters.clear()
        self._archive_report_cache.clear()
        self._archive_report_filter = None
        self._refresh_archive_report_controls()

    def _refresh_archive_report_controls(self):
        if self.dock and hasattr(self.dock.details, "refresh_archive_report_controls"):
            self.dock.details.refresh_archive_report_controls()

    def _archive_report_layers(self, number):
        return [layer for layer in QgsProject.instance().mapLayers().values()
                if str(layer.customProperty(self.ARCHIVE_REPORT_PROPERTY, "")) == number]

    def archive_report_status(self, number):
        active = self._archive_report_filter
        return {
            "area": bool(self._archive_report_layers(number)) or (number, "area") in self._archive_report_actions,
            "filter": bool(active and active["number"] == number) or (number, "filter") in self._archive_report_actions,
            "any_filter": bool(active) or any(action == "filter" for _, action in self._archive_report_actions),
            "active_number": active["number"] if active else "",
        }

    def _load_archive_report_geometry(self, number, success, failure):
        definition = self._registry_definition("archive_survey_areas", "EGF")
        if definition is None:
            failure(self.t("Fondi uuringualade teenus puudub seadetest."))
            return
        source_key = (definition.url, definition.layer_name, number)
        if source_key in self._archive_report_cache:
            success(QgsGeometry(self._archive_report_cache[source_key]))
            return
        if source_key in self._archive_report_waiters:
            self._archive_report_waiters[source_key].append((success, failure))
            return
        waiters = [(success, failure)]
        self._archive_report_waiters[source_key] = waiters
        geometries, seen = [], set()

        def finish(geometry=None, error=""):
            if self._archive_report_waiters.get(source_key) is not waiters:
                return
            self._archive_report_waiters.pop(source_key, None)
            if geometry is not None:
                if len(self._archive_report_cache) >= 16:
                    self._archive_report_cache.pop(next(iter(self._archive_report_cache)))
                self._archive_report_cache[source_key] = QgsGeometry(geometry)
            for loaded, failed in waiters:
                if not self._unloading:
                    failed(error) if error else loaded(QgsGeometry(geometry))

        def load(offset):
            url = QUrl(definition.url)
            query = QUrlQuery()
            for key, value in (("service", "WFS"), ("version", "2.0.0"),
                    ("request", "GetFeature"), ("typeNames", definition.layer_name),
                    ("outputFormat", "application/json"), ("srsName", "EPSG:3301"),
                    ("CQL_FILTER", f"egf_id={number}"), ("count", "500"),
                    ("startIndex", str(offset))):
                query.addQueryItem(key, value)
            url.setQuery(query)

            def decoded(payload):
                if self._archive_report_waiters.get(source_key) is not waiters:
                    return
                if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
                    finish(error=self.t("Fondi ruumikuju vastus on vigane."))
                    return
                page = payload["features"]
                try:
                    declared_crs = payload.get("crs")
                    source_crs = QgsCoordinateReferenceSystem("EPSG:3301")
                    if declared_crs:
                        source_crs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(
                            declared_crs["properties"]["name"]
                        )
                        if not source_crs.isValid():
                            raise ValueError(self.t("Fondi ruumikuju vastus on vigane."))
                    for feature in page:
                        if not isinstance(feature, dict):
                            raise ValueError(self.t("Fondi ruumikuju vastus on vigane."))
                        properties = feature.get("properties") or {}
                        if not isinstance(properties, dict):
                            raise ValueError(self.t("Fondi ruumikuju vastus on vigane."))
                        linked = report_number(properties.get("egf_id"))
                        if linked != number:
                            raise ValueError(self.t("Fondi ruumikuju vastus on vigane."))
                        signature = json.dumps(feature, sort_keys=True)
                        if signature in seen:
                            raise ValueError(self.t("Fondi teenus kordas objekte; ruumikuju on poolik."))
                        seen.add(signature)
                        geometry = QgsJsonUtils.geometryFromGeoJson(json.dumps(feature.get("geometry")))
                        if geometry.isEmpty() or geometry.type() != Qgis.GeometryType.Polygon:
                            raise ValueError(self.t("Fondi ruumikuju puudub või ei ole pindobjekt."))
                        if source_crs.authid() != "EPSG:3301":
                            geometry.transform(QgsCoordinateTransform(source_crs, QgsCoordinateReferenceSystem("EPSG:3301"), QgsProject.instance()))
                        if not geometry.isGeosValid():
                            geometry = geometry.makeValid()
                        if geometry.isEmpty() or geometry.type() != Qgis.GeometryType.Polygon:
                            raise ValueError(self.t("Fondi ruumikuju ei saa kasutada."))
                        geometries.append(geometry)
                    try:
                        more = offset + len(page) < int(payload.get("numberMatched"))
                    except (TypeError, ValueError):
                        more = len(page) >= 500
                    if more:
                        if not page or offset + len(page) >= 5000:
                            raise ValueError(self.t("Fondi ruumikuju on poolik; filtrit ei rakendatud."))
                        load(offset + len(page))
                        return
                    if not geometries:
                        raise ValueError(self.t("Sellel fondiaruandel puudub avalik ruumikuju."))
                    geometry = QgsGeometry.unaryUnion(geometries)
                    if geometry.isEmpty() or geometry.type() != Qgis.GeometryType.Polygon:
                        raise ValueError(self.t("Fondi ruumikujude ühendamine ebaõnnestus."))
                    finish(geometry)
                except (KeyError, TypeError, ValueError, QgsCsException) as error:
                    finish(error=str(error))
            self.network.get_json(url, decoded, lambda error: finish(error=str(error)))
        load(0)

    def _archive_report_action(self, number, kind, enabled, loaded):
        number = report_number(number)
        if not number:
            return
        key = (number, kind)
        self._archive_report_actions.pop(key, None)
        if not enabled:
            return
        token = object()
        definition = self._registry_definition("archive_survey_areas", "EGF")
        source = (definition.url, definition.layer_name) if definition else None
        self._archive_report_actions[key] = token
        self._refresh_archive_report_controls()
        def complete(geometry):
            if self._archive_report_actions.get(key) is token and not self._unloading:
                self._archive_report_actions.pop(key, None)
                current = self._registry_definition("archive_survey_areas", "EGF")
                if current is None or (current.url, current.layer_name) != source:
                    self.warning(self.t("Fondi teenus muutus päringu ajal. Proovi uuesti."))
                else:
                    loaded(geometry)
                self._refresh_archive_report_controls()
        def failed(error):
            if self._archive_report_actions.get(key) is token and not self._unloading:
                self._archive_report_actions.pop(key, None)
                self.warning(f"EGF {number}: {error}")
                self._refresh_archive_report_controls()
        self._load_archive_report_geometry(number, complete, failed)

    def set_archive_report_visible(self, number, enabled):
        number = report_number(number)
        if not number:
            return
        if not enabled:
            self._archive_report_actions.pop((number, "area"), None)
            QgsProject.instance().removeMapLayers([layer.id() for layer in self._archive_report_layers(number)])
            self._refresh_archive_report_controls()
            return
        if self._archive_report_layers(number):
            for layer in self._archive_report_layers(number):
                node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
                if node:
                    node.setItemVisibilityChecked(True)
            self._refresh_archive_report_controls()
            return
        def loaded(_geometry):
            definition = self._registry_definition("archive_survey_areas", "EGF")
            if definition is None:
                self.warning(self.t("Fondi uuringualade teenus puudub seadetest."))
                return
            layer = QgsVectorLayer(self._wfs_uri(definition, f'"egf_id" = {number}'), f"EGF {number} — {self.t('Fondi aruande ala')}", "WFS")
            if not layer.isValid():
                self.warning(self.t("Fondi ruumikuju kihi laadimine ebaõnnestus."))
                return
            layer.setCustomProperty(self.ARCHIVE_REPORT_PROPERTY, number)
            layer.setCustomProperty(self.ROLE_PROPERTY, "archive_survey_areas")
            self._apply_definition_renderer(layer, definition)
            QgsProject.instance().addMapLayer(layer)
            self._ensure_egt_points_on_top()
            self.iface.mapCanvas().refresh()
        self._archive_report_action(number, "area", True, loaded)

    def set_archive_report_filter(self, number, enabled):
        number = report_number(number)
        if not number:
            return
        if not enabled:
            self.clear_archive_report_filter()
            return
        for key in list(self._archive_report_actions):
            if key[1] == "filter":
                self._archive_report_actions.pop(key, None)
        def loaded(geometry):
            self._archive_report_filter = {"number": number, "geometry": geometry, "expressions": {}}
            self._save_archive_report_filter()
            if not self._role_layers("boreholes"):
                definition = next((item for item in self.definitions if item.role == "boreholes"), None)
                if definition:
                    self.add_layer(definition, force_add=True)
            self.apply_egt_filters()
        self._archive_report_action(number, "filter", True, loaded)

    def clear_archive_report_filter(self):
        for key in list(self._archive_report_actions):
            if key[1] == "filter":
                self._archive_report_actions.pop(key, None)
        self._archive_report_filter = None
        self._save_archive_report_filter()
        self.apply_egt_filters()
        self._refresh_archive_report_controls()

    def _archive_spatial_expression(self, layer, role):
        active = getattr(self, "_archive_report_filter", None)
        if not active or role != "boreholes":
            return ""
        crs = layer.crs()
        key = crs.toWkt()
        if key not in active["expressions"]:
            geometry = QgsGeometry(active["geometry"])
            try:
                geometry.transform(QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:3301"), crs, QgsProject.instance()))
                wkt = geometry.asWkt().replace("'", "''")
                active["expressions"][key] = f"intersects($geometry, geom_from_wkt('{wkt}'))"
            except QgsCsException:
                active["expressions"][key] = "FALSE"
        return active["expressions"][key]

    def _passes_archive_report_filter(self, layer, feature):
        active = getattr(self, "_archive_report_filter", None)
        if not active or self._layer_role(layer) != "boreholes":
            return True
        try:
            geometry = QgsGeometry(feature.geometry())
            geometry.transform(QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:3301"), QgsProject.instance()))
            return not geometry.isEmpty() and active["geometry"].intersects(geometry)
        except QgsCsException:
            return False
