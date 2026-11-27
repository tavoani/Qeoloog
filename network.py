"""Asynchronous HTTP helpers using QGIS' shared network stack."""

import json
from math import isfinite
from urllib.parse import quote, urlencode

from qgis.PyQt.QtCore import QByteArray, QUrl, QUrlQuery, QXmlStreamReader
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import QgsApplication, QgsNetworkAccessManager

from .egt_labels import egt_label_summaries
from .observations import OBSERVATION_LABEL_DEPTH, observation_labels
from .portal import (
    PORTAL_EDITING_ENABLED,
    arcgis_layer_metadata,
    deduplicate_portal_feature_services,
    feature_layer_url,
    feature_service_root,
    layer_renderer_definition,
    portal_feature_service_items,
    service_layer_options,
    map_service_root,
    map_layer_url,
)
from .stratigraphy import (
    STRATIGRAPHIC_INDEX_SET,
    add_stratigraphic_interval,
)


AUQ_REST = "https://gis.egt.ee/arcgis/rest/services/AUQ_public/AUQ_webapp_open/MapServer"
EGT_WFS = "https://maps.egt.ee/geoserver/faktika/ows"
GEA_API = "https://gea-api.egt.ee"
SARV_API = "https://rwapi.geoloogia.info/api/v1/public"
EELIS_API = "https://keskkonnaandmed.envir.ee"
MARU_GEODESY_API = "https://gpa.maaamet.ee/api"
MAX_CAPABILITIES_BYTES = 20 * 1024 * 1024
MAX_HTML_BYTES = 8 * 1024 * 1024


def parse_capabilities(payload, protocol):
    """Return ``(name, title)`` tuples from a WMS or WFS capabilities document."""
    if len(payload) > MAX_CAPABILITIES_BYTES:
        raise ValueError(
            "Capabilities XML exceeds the 20 MB safety limit."
        )

    reader = QXmlStreamReader(payload)
    # Keep entity expansion deliberately small and reject DTD/entity tokens
    # below. GetCapabilities documents do not need custom entities.
    reader.setEntityExpansionLimit(1024)
    result = []
    wanted_parent = "Layer" if protocol.upper() == "WMS" else "FeatureType"
    records = []
    depth = 0

    while not reader.atEnd():
        token = reader.readNext()
        if token in (
            QXmlStreamReader.TokenType.DTD,
            QXmlStreamReader.TokenType.EntityReference,
        ):
            raise ValueError(
                "DTD and custom XML entities are not allowed in capabilities."
            )
        if token == QXmlStreamReader.TokenType.StartElement:
            depth += 1
            tag = str(reader.name())
            if tag == wanted_parent:
                records.append({"depth": depth, "name": "", "title": ""})
            elif (
                records
                and depth == records[-1]["depth"] + 1
                and tag in {"Name", "Title"}
            ):
                text = reader.readElementText(
                    QXmlStreamReader.ReadElementTextBehaviour.SkipChildElements
                ).strip()
                records[-1][tag.casefold()] = text
                # readElementText() leaves the reader on this element's end.
                depth -= 1
        elif token == QXmlStreamReader.TokenType.EndElement:
            tag = str(reader.name())
            if (
                records
                and depth == records[-1]["depth"]
                and tag == wanted_parent
            ):
                record = records.pop()
                if record["name"]:
                    result.append((
                        record["name"],
                        record["title"] or record["name"],
                    ))
            depth = max(0, depth - 1)

    if reader.hasError():
        raise ValueError(
            f"Invalid capabilities XML: {reader.errorString()} "
            f"(line {reader.lineNumber()}, column {reader.columnNumber()})."
        )
    return result


class NetworkClient:
    """Keep replies alive and decode XML/JSON without blocking the UI thread."""

    def __init__(self):
        self._replies = set()
        self._manager = QgsNetworkAccessManager.instance()

    def get_capabilities(self, protocol, service_url, success, failure):
        url = QUrl(service_url)
        query = QUrlQuery(url)
        query.addQueryItem("service", protocol.upper())
        query.addQueryItem("request", "GetCapabilities")
        query.addQueryItem("version", "1.3.0" if protocol.upper() == "WMS" else "2.0.0")
        url.setQuery(query)
        self._get(
            url,
            lambda data: success(parse_capabilities(data, protocol)),
            failure,
            max_bytes=MAX_CAPABILITIES_BYTES,
        )

    def get_json(
        self, url, success, failure, authcfg="", data_provider="",
    ):
        target = url if isinstance(url, QUrl) else QUrl(url)
        self._get(
            target,
            lambda data: success(json.loads(bytes(data).decode("utf-8"))),
            failure,
            authcfg=authcfg,
            data_provider=data_provider,
        )

    def get_bytes(
        self, url, success, failure, authcfg="", data_provider="",
        max_bytes=None,
    ):
        """Download authenticated binary content without exposing tokens."""
        target = url if isinstance(url, QUrl) else QUrl(url)
        self._get(
            target, lambda data: success(bytes(data)), failure,
            authcfg=authcfg, data_provider=data_provider,
            max_bytes=max_bytes,
        )

    def query_maru_height_model(
        self, model, x, y, height, success, failure, *, direction=None,
    ):
        """Convert one height with MaRu's official public model service."""
        if model not in {"ymudel", "geoid"}:
            failure("Unsupported MaRu height model.")
            return
        url = QUrl(f"{MARU_GEODESY_API}/{model}")
        query = QUrlQuery()
        query.addQueryItem("x", f"{float(x):.9f}")
        query.addQueryItem("y", f"{float(y):.9f}")
        query.addQueryItem("h", f"{float(height):.6f}")
        if model == "geoid":
            query.addQueryItem(
                "dirEllipsToGeoid", "true" if direction else "false"
            )
        url.setQuery(query)

        def decoded(payload):
            if not isinstance(payload, dict) or payload.get("h") is None:
                failure("Invalid MaRu height-model response.")
                return
            try:
                value = float(payload["h"])
            except (TypeError, ValueError):
                failure("Invalid MaRu height-model response.")
                return
            if not isfinite(value):
                failure("The coordinate is outside the MaRu height model.")
                return
            success(value)

        self.get_json(url, decoded, failure)

    def query_arcgis_feature_layers(
        self, service_url, authcfg, success, failure,
    ):
        """List layers and tables from one ArcGIS FeatureServer service."""
        try:
            root = feature_service_root(service_url)
        except ValueError as error:
            failure(str(error))
            return
        url = QUrl(root)
        query = QUrlQuery()
        query.addQueryItem("f", "json")
        url.setQuery(query)

        def decoded(payload):
            try:
                success(service_layer_options(payload))
            except ValueError as error:
                failure(str(error))

        self.get_json(
            url, decoded, failure, authcfg=authcfg,
        )

    def query_arcgis_map_layers(self, service_url, success, failure):
        """List public layers from one ArcGIS MapServer service."""
        try:
            root = map_service_root(service_url)
        except ValueError as error:
            failure(str(error))
            return
        url = QUrl(root)
        query = QUrlQuery()
        query.addQueryItem("f", "json")
        url.setQuery(query)

        def decoded(payload):
            try:
                success(service_layer_options(payload))
            except ValueError as error:
                failure(str(error))

        self.get_json(url, decoded, failure)

    def query_arcgis_layer_renderer(
        self, service_url, layer_name, authcfg, success, failure,
    ):
        """Read the authoritative renderer stored with a FeatureServer layer."""
        try:
            target = (
                map_layer_url(service_url, layer_name)
                if "/mapserver" in str(service_url).casefold()
                else feature_layer_url(service_url, layer_name)
            )
        except ValueError as error:
            failure(str(error))
            return
        url = QUrl(target)
        query = QUrlQuery()
        query.addQueryItem("f", "json")
        url.setQuery(query)

        def decoded(payload):
            try:
                success(layer_renderer_definition(payload))
            except ValueError as error:
                failure(str(error))

        self.get_json(url, decoded, failure, authcfg=authcfg)

    def query_arcgis_layer_metadata(
        self, service_url, layer_name, authcfg, success, failure,
    ):
        """Read and validate live metadata for one FeatureServer layer."""
        try:
            target = feature_layer_url(service_url, layer_name)
        except ValueError as error:
            failure(str(error))
            return
        url = QUrl(target)
        query = QUrlQuery()
        query.addQueryItem("f", "json")
        url.setQuery(query)

        def decoded(payload):
            try:
                success(arcgis_layer_metadata(payload))
            except ValueError as error:
                failure(str(error))

        self.get_json(url, decoded, failure, authcfg=authcfg)

    def query_arcgis_features(
        self, service_url, layer_id, where, success, failure, *,
        authcfg="", out_fields="*", return_geometry=True, return_z=True,
        order_by="", result_count=2000,
    ):
        """Query one authenticated ArcGIS layer/table without exposing tokens."""
        try:
            target = feature_layer_url(service_url, str(layer_id)) + "/query"
        except ValueError as error:
            failure(str(error))
            return
        params = {
            "f": "json",
            "where": str(where or "1=1"),
            "outFields": (
                ",".join(out_fields) if isinstance(out_fields, (list, tuple))
                else str(out_fields or "*")
            ),
            "returnGeometry": "true" if return_geometry else "false",
            "returnZ": "true" if return_z else "false",
            "outSR": "3301",
            "resultRecordCount": str(max(1, min(int(result_count), 2000))),
        }
        if order_by:
            params["orderByFields"] = str(order_by)

        def decoded(payload):
            if not isinstance(payload, dict):
                failure("Invalid ArcGIS FeatureServer response.")
                return
            error = payload.get("error")
            if isinstance(error, dict):
                details = error.get("details") or []
                message = error.get("message") or "ArcGIS query failed."
                if details:
                    message += " " + " ".join(str(item) for item in details if item)
                failure(message)
                return
            success(payload)

        self._post_form_json(
            target, params, decoded, failure, authcfg=authcfg,
        )

    def query_arcgis_attachments(
        self, service_url, layer_id, object_id, success, failure, *,
        authcfg="",
    ):
        """List attachments belonging to one authenticated ArcGIS feature."""
        try:
            layer_url = feature_layer_url(service_url, str(layer_id))
            object_value = int(object_id)
        except (TypeError, ValueError) as error:
            failure(str(error))
            return
        target = f"{layer_url}/{object_value}/attachments"
        url = QUrl(target)
        query = QUrlQuery()
        query.addQueryItem("f", "json")
        url.setQuery(query)

        def decoded(payload):
            if not isinstance(payload, dict):
                failure("Invalid ArcGIS attachment response.")
                return
            error = payload.get("error")
            if isinstance(error, dict):
                details = error.get("details") or []
                message = error.get("message") or "ArcGIS attachment query failed."
                if details:
                    message += " " + " ".join(
                        str(item) for item in details if item
                    )
                failure(message)
                return
            rows = []
            for item in payload.get("attachmentInfos") or []:
                if not isinstance(item, dict) or item.get("id") in (None, ""):
                    continue
                row = dict(item)
                row["_url"] = f"{target}/{item['id']}"
                rows.append(row)
            success(rows)

        self.get_json(url, decoded, failure, authcfg=authcfg)

    def apply_arcgis_service_edits(
        self, service_url, edits, authcfg, success, failure,
    ):
        """Atomically apply GlobalID-based edits across a FeatureServer."""
        if not PORTAL_EDITING_ENABLED:
            failure(
                "Portali kirjutamine on Qeoloogis organisatsiooni reegli "
                "alusel välja lülitatud."
            )
            return
        try:
            target = feature_service_root(service_url) + "/applyEdits"
        except ValueError as error:
            failure(str(error))
            return
        self._post_form_json(
            target,
            {
                "f": "json",
                "edits": json.dumps(edits, ensure_ascii=True, separators=(",", ":")),
                "useGlobalIds": "true",
                "rollbackOnFailure": "true",
                "returnEditMoment": "true",
            },
            success,
            failure,
            authcfg=authcfg,
        )

    def query_egt_portal_user(self, authcfg, success, failure):
        """Trigger EGT Portal login and return the signed-in account."""
        url = QUrl(
            "https://gis.egt.ee/portal/sharing/rest/community/self"
        )
        query = QUrlQuery()
        query.addQueryItem("f", "json")
        url.setQuery(query)

        def decoded(payload):
            if not isinstance(payload, dict):
                failure("Invalid EGT Portal response.")
                return
            error = payload.get("error")
            if isinstance(error, dict):
                failure(error.get("message") or "EGT Portal login failed.")
                return
            username = payload.get("username")
            if not username:
                failure("EGT Portal did not return a signed-in user.")
                return
            success(payload)

        self.get_json(
            url, decoded, failure, authcfg=authcfg,
        )

    def query_egt_portal_feature_services(
        self, authcfg, success, failure,
    ):
        """Return every Feature Service visible to the signed-in account."""
        collected = []
        requested_starts = set()

        def request_page(start):
            if start in requested_starts or len(requested_starts) >= 100:
                failure("Invalid EGT Portal search pagination.")
                return
            requested_starts.add(start)
            url = QUrl(
                "https://gis.egt.ee/portal/sharing/rest/search"
            )
            query = QUrlQuery()
            for key, value in (
                ("f", "json"),
                ("q", 'type:"Feature Service"'),
                ("num", "100"),
                ("start", str(start)),
                ("sortField", "title"),
                ("sortOrder", "asc"),
            ):
                query.addQueryItem(key, value)
            url.setQuery(query)

            def decoded(payload):
                try:
                    collected.extend(portal_feature_service_items(payload))
                    next_start = int(payload.get("nextStart") or -1)
                except (TypeError, ValueError) as error:
                    failure(str(error))
                    return
                if next_start > 0:
                    request_page(next_start)
                    return
                success(deduplicate_portal_feature_services(collected))

            self.get_json(
                url, decoded, failure, authcfg=authcfg,
            )

        request_page(1)

    def query_wfs_features(
        self, service_url, type_name, cql_filter, success, failure,
        count=250, bbox="", sort_by="", property_names=(),
    ):
        """Load one bounded, server-filtered WFS result page as GeoJSON."""
        url = QUrl(service_url)
        query = QUrlQuery()
        for key, value in (
            ("service", "WFS"),
            ("version", "2.0.0"),
            ("request", "GetFeature"),
            ("typeNames", type_name),
            ("outputFormat", "application/json"),
            ("count", str(max(1, min(int(count), 500)))),
            ("CQL_FILTER", cql_filter),
        ):
            if value:
                query.addQueryItem(key, value)
        if bbox:
            query.addQueryItem("bbox", bbox)
        if sort_by:
            query.addQueryItem("sortBy", sort_by)
        if property_names:
            query.addQueryItem("propertyName", ",".join(property_names))
        url.setQuery(query)

        def decoded(payload):
            if not isinstance(payload, dict):
                failure("Invalid WFS response")
                return
            if payload.get("exceptions") or payload.get("exception"):
                failure(str(payload.get("exceptions") or payload.get("exception")))
                return
            success(
                payload.get("features", []),
                payload.get("numberMatched"),
            )

        self.get_json(url, decoded, failure)

    def get_text(self, url, success, failure, max_bytes=MAX_HTML_BYTES):
        """Load a bounded public HTML/text response as UTF-8."""
        target = url if isinstance(url, QUrl) else QUrl(url)
        self._get(
            target,
            lambda data: success(bytes(data).decode("utf-8", errors="replace")),
            failure,
            max_bytes=max_bytes,
        )

    def query_auq(self, table_id, where, success, failure, order_by=""):
        self.query_auq_all(
            table_id, where, (),
            lambda rows: success({"features": [{"attributes": row} for row in rows]}),
            failure, order_by=order_by or "objectid",
        )

    def query_auq_all(
        self, table_id, where, fields, success, failure, order_by="objectid",
        page_size=2000,
    ):
        """Load every page of an ArcGIS table query."""
        rows = []

        def load_page(offset):
            url = QUrl(f"{AUQ_REST}/{table_id}/query")
            query = QUrlQuery()
            for key, value in (
                ("f", "json"),
                ("where", where),
                ("outFields", ",".join(fields) if fields else "*"),
                ("returnGeometry", "false"),
                ("resultOffset", str(offset)),
                ("resultRecordCount", str(page_size)),
            ):
                query.addQueryItem(key, value)
            if order_by:
                query.addQueryItem("orderByFields", order_by)
            url.setQuery(query)

            def decoded(payload):
                if payload.get("error"):
                    failure(payload["error"].get("message", "AUQ query failed"))
                    return
                page = [
                    feature.get("attributes", {})
                    for feature in payload.get("features", [])
                ]
                rows.extend(page)
                if not page and payload.get("exceededTransferLimit"):
                    failure("AUQ returned an incomplete empty page")
                    return
                if len(page) >= page_size or payload.get("exceededTransferLimit"):
                    load_page(offset + len(page))
                else:
                    success(rows)

            self.get_json(url, decoded, failure)

        load_page(0)

    def query_auq_metadata(self, table_id, success, failure):
        """Load ArcGIS layer/table metadata, including coded-value domains."""
        url = QUrl(f"{AUQ_REST}/{table_id}")
        query = QUrlQuery()
        query.addQueryItem("f", "json")
        url.setQuery(query)
        self.get_json(url, success, failure)

    def query_auq_parent_ids(self, table_id, success, failure):
        """Return object UUIDs which have rows in an AUQ related table."""
        statistics = json.dumps(
            [{
                "statisticType": "count",
                "onStatisticField": "objectid",
                "outStatisticFieldName": "row_count",
            }],
            separators=(",", ":"),
        )
        parameters = {
            "f": "json",
            "where": "puurauk_vaatluspunkt_id IS NOT NULL",
            "outStatistics": statistics,
            "groupByFieldsForStatistics": "puurauk_vaatluspunkt_id",
            "orderByFields": "puurauk_vaatluspunkt_id",
            "returnGeometry": "false",
            "resultRecordCount": "2000",
        }
        encoded = f"{AUQ_REST}/{table_id}/query?{urlencode(parameters)}".encode("utf-8")
        url = QUrl.fromEncoded(encoded)

        def decoded(payload):
            if payload.get("error"):
                failure(payload["error"].get("message", "AUQ query failed"))
                return
            values = {
                str(feature.get("attributes", {}).get("puurauk_vaatluspunkt_id") or "").upper()
                for feature in payload.get("features", [])
            }
            success({value for value in values if value})

        self.get_json(url, decoded, failure)

    def query_sarv(self, resource, parameters, success, failure):
        """Query a public SARV API resource and return its decoded JSON payload."""
        path = str(resource).strip("/")
        url = QUrl(f"{SARV_API}/{path}/")
        query = QUrlQuery()
        for key, value in parameters.items():
            if value not in (None, "", []):
                query.addQueryItem(key, str(value))
        url.setQuery(query)
        # Detail collections need the same pagination guarantees as indexes.
        collected = []
        visited = set()
        def load(target):
            address = target.toString()
            if address in visited or not address.startswith(SARV_API.rstrip("/") + "/"):
                failure("Invalid or repeated SARV pagination URL")
                return
            visited.add(address)
            def decoded(payload):
                if not isinstance(payload, dict) or "results" not in payload:
                    success(payload)
                    return
                collected.extend(payload.get("results") or [])
                next_url = payload.get("next")
                if next_url:
                    load(target.resolved(QUrl(str(next_url))))
                else:
                    try:
                        incomplete = int(payload.get("count", len(collected))) > len(collected)
                    except (ValueError, TypeError):
                        incomplete = False
                    if incomplete:
                        failure("SARV response is incomplete and has no next page")
                        return
                    success({**payload, "results": collected, "next": None})
            self.get_json(target, decoded, failure)
        load(url)

    def query_sarv_all(self, resource, fields, success, failure, limit=5000):
        """Load every page of a compact SARV public-API collection."""
        rows = []
        path = str(resource).strip("/")
        url = QUrl(f"{SARV_API}/{path}/")
        query = QUrlQuery()
        query.addQueryItem("fields", ",".join(fields))
        query.addQueryItem("limit", str(limit))
        url.setQuery(query)

        def load_page(target):
            def decoded(payload):
                if not isinstance(payload, dict):
                    failure("Invalid SARV response")
                    return
                rows.extend(payload.get("results", []))
                next_url = payload.get("next")
                if next_url:
                    load_page(QUrl(str(next_url)))
                else:
                    success(rows)

            self.get_json(target, decoded, failure)

        load_page(url)

    def query_sarv_pages(
        self, resource, parameters, fields, success, failure, limit=5000,
    ):
        """Load all pages of a filtered SARV collection."""
        rows = []
        path = str(resource).strip("/")
        url = QUrl(f"{SARV_API}/{path}/")
        query = QUrlQuery()
        for key, value in parameters.items():
            if value not in (None, "", []):
                query.addQueryItem(key, str(value))
        if fields:
            query.addQueryItem("fields", ",".join(fields))
        query.addQueryItem("limit", str(limit))
        url.setQuery(query)

        def load_page(target):
            def decoded(payload):
                if not isinstance(payload, dict):
                    failure("Invalid SARV response")
                    return
                rows.extend(payload.get("results", []))
                next_url = payload.get("next")
                if next_url:
                    load_page(QUrl(str(next_url)))
                else:
                    success(rows)

            self.get_json(target, decoded, failure)

        load_page(url)

    def query_eelis_pages(
        self, resource, parameters, fields, success, failure, limit=20000,
    ):
        """Load all pages from an EELIS PostgREST public-API resource."""
        rows = []
        path = str(resource).strip("/")

        def load_page(offset):
            url = QUrl(f"{EELIS_API}/{path}")
            query = QUrlQuery()
            if fields:
                query.addQueryItem("select", ",".join(fields))
            for key, value in (parameters or {}).items():
                if value not in (None, "", []):
                    query.addQueryItem(str(key), str(value))
            query.addQueryItem("limit", str(limit))
            query.addQueryItem("offset", str(offset))
            url.setQuery(query)

            def decoded(payload):
                if not isinstance(payload, list):
                    failure("Invalid EELIS API response")
                    return
                rows.extend(payload)
                if len(payload) >= limit:
                    load_page(offset + len(payload))
                else:
                    success(rows)

            self.get_json(url, decoded, failure)

        load_page(0)

    def query_geological_units(self, role, global_id, success, failure):
        """Load the selected object's depth intervals from EGT WFS as GeoJSON."""
        type_name = (
            "faktika:puurauk_geoloogiline_yksus"
            if role == "boreholes"
            else "faktika:vaatluspunkt_geoloogiline_yksus"
        )
        safe_id = str(global_id).replace("'", "''")
        url = QUrl(EGT_WFS)
        query = QUrlQuery()
        for key, value in (
            ("service", "WFS"),
            ("version", "2.0.0"),
            ("request", "GetFeature"),
            ("typeNames", type_name),
            ("outputFormat", "application/json"),
            ("count", "2000"),
            ("sortBy", "z_suht_ylemine"),
            ("CQL_FILTER", f"puurauk_vaatluspunkt_id='{safe_id}'"),
        ):
            query.addQueryItem(key, value)
        url.setQuery(query)

        rows = []
        seen_pages = set()
        def load(offset):
            target = QUrl(url)
            page_query = QUrlQuery(target)
            page_query.addQueryItem("startIndex", str(offset))
            target.setQuery(page_query)
            def decoded(payload):
                if not isinstance(payload, dict) or "features" not in payload:
                    failure("Invalid EGT WFS response")
                    return
                features = payload["features"]
                signature = json.dumps(features, sort_keys=True)
                if features and signature in seen_pages:
                    failure("EGT WFS repeated a page; intervals are incomplete")
                    return
                seen_pages.add(signature)
                rows.extend(feature.get("properties", {}) for feature in features)
                total = payload.get("numberMatched")
                try:
                    more = len(rows) < int(total)
                except (TypeError, ValueError):
                    more = len(features) >= 2000
                if more:
                    if not features:
                        failure("EGT WFS returned incomplete intervals")
                    else:
                        load(offset + len(features))
                else:
                    success(rows)
            self.get_json(target, decoded, failure)
        load(0)

    def query_observation_labels(
        self, success, failure, page_size=1000, cancelled=None,
    ):
        """Fetch only units at 0.5 m, asynchronously and once for all VP labels."""
        rows = []
        depth = OBSERVATION_LABEL_DEPTH

        def load_page(start_index):
            if cancelled and cancelled():
                return
            url = QUrl(EGT_WFS)
            query = QUrlQuery()
            for key, value in (
                ("service", "WFS"),
                ("version", "2.0.0"),
                ("request", "GetFeature"),
                ("typeNames", "faktika:vaatluspunkt_geoloogiline_yksus"),
                ("outputFormat", "application/json"),
                ("propertyName", (
                    "puurauk_vaatluspunkt_id,z_suht_ylemine,z_suht_alumine,"
                    "genees,litoloogia,litoloogia_orig"
                )),
                ("sortBy", "puurauk_vaatluspunkt_id,esri_globalid"),
                ("count", str(page_size)),
                ("startIndex", str(start_index)),
                ("CQL_FILTER", (
                    f"z_suht_ylemine <= {depth:g} AND "
                    f"z_suht_alumine >= {depth:g}"
                )),
            ):
                query.addQueryItem(key, value)
            url.setQuery(query)

            def decoded(payload):
                if cancelled and cancelled():
                    return
                if not isinstance(payload, dict):
                    failure("Invalid EGT observation-label response")
                    return
                features = payload.get("features")
                if not isinstance(features, list):
                    failure("Missing EGT observation-label features")
                    return
                rows.extend(feature.get("properties", {}) for feature in features)
                next_index = start_index + len(features)
                try:
                    matched = int(payload.get("numberMatched"))
                except (TypeError, ValueError):
                    matched = None
                has_more = (
                    next_index < matched if matched is not None
                    else len(features) >= page_size
                )
                if has_more and not features:
                    failure("Incomplete EGT observation-label response")
                elif has_more:
                    load_page(next_index)
                else:
                    success(observation_labels(rows))

            self.get_json(url, decoded, failure)

        load_page(0)

    def query_egt_label_details(
        self, role, parent_ids, success, failure, page_size=2000,
        cancelled=None,
    ):
        """Load compact geology summaries for the visible EGT point IDs.

        Requests are deliberately limited to small UUID batches.  The point
        layers themselves are BBOX-restricted, so this avoids downloading the
        complete country-wide geological-unit tables merely to draw labels.
        """
        type_name = (
            "faktika:puurauk_geoloogiline_yksus"
            if role == "boreholes"
            else "faktika:vaatluspunkt_geoloogiline_yksus"
        )
        identifiers = sorted({
            str(value or "").strip().upper()
            for value in parent_ids if str(value or "").strip()
        })
        if not identifiers:
            success({})
            return
        batches = [
            identifiers[index:index + 80]
            for index in range(0, len(identifiers), 80)
        ]
        rows = []
        properties = (
            "puurauk_vaatluspunkt_id,z_suht_ylemine,z_suht_alumine,"
            "z_abs_ylemine,klassif_yksus_kood,yksus_kood,indeks,"
            "liityksus_indeks_ylemine,liityksus_indeks_alumine,"
            "genees,litoloogia,litoloogia_orig"
        )

        def load_batch(batch_index, start_index=0):
            if cancelled and cancelled():
                return
            if batch_index >= len(batches):
                success(egt_label_summaries(rows))
                return
            quoted = ",".join(
                "'" + value.replace("'", "''") + "'"
                for value in batches[batch_index]
            )
            url = QUrl(EGT_WFS)
            query = QUrlQuery()
            for key, value in (
                ("service", "WFS"),
                ("version", "2.0.0"),
                ("request", "GetFeature"),
                ("typeNames", type_name),
                ("outputFormat", "application/json"),
                ("propertyName", properties),
                ("sortBy", "puurauk_vaatluspunkt_id,z_suht_ylemine"),
                ("count", str(page_size)),
                ("startIndex", str(start_index)),
                ("CQL_FILTER", f"puurauk_vaatluspunkt_id IN ({quoted})"),
            ):
                query.addQueryItem(key, value)
            url.setQuery(query)

            def decoded(payload):
                if cancelled and cancelled():
                    return
                if not isinstance(payload, dict):
                    failure("Invalid EGT map-label response")
                    return
                features = payload.get("features")
                if not isinstance(features, list):
                    failure("Missing EGT map-label features")
                    return
                rows.extend(
                    feature.get("properties", {}) for feature in features
                )
                next_index = start_index + len(features)
                try:
                    matched = int(payload.get("numberMatched"))
                except (TypeError, ValueError):
                    matched = None
                has_more = (
                    next_index < matched if matched is not None
                    else len(features) >= page_size
                )
                if has_more and not features:
                    failure("Incomplete EGT map-label response")
                elif has_more:
                    load_batch(batch_index, next_index)
                else:
                    load_batch(batch_index + 1, 0)

            self.get_json(url, decoded, failure)

        load_batch(0)

    def query_egt_object(
        self, role, key_type, key_value, success, failure,
    ):
        """Resolve a persisted EGT key to current WFS object attributes."""
        type_name = (
            "faktika:puurauk"
            if role == "boreholes" else "faktika:Vaatluspunkt"
        )
        value = str(key_value or "").strip()
        if key_type == "gea":
            if not value.isdigit():
                failure("Invalid GEA ID")
                return
            cql_filter = f"gea_id={value}"
        else:
            safe = value.replace("'", "''")
            cql_filter = f"esri_globalid='{safe}'"
        url = QUrl(EGT_WFS)
        query = QUrlQuery()
        for key, parameter in (
            ("service", "WFS"),
            ("version", "2.0.0"),
            ("request", "GetFeature"),
            ("typeNames", type_name),
            ("outputFormat", "application/json"),
            ("count", "2"),
            ("CQL_FILTER", cql_filter),
        ):
            query.addQueryItem(key, parameter)
        url.setQuery(query)

        def decoded(payload):
            features = payload.get("features", [])
            if not features:
                failure(f"EGT object {value} was not found")
                return
            success(features[0].get("properties", {}))

        self.get_json(url, decoded, failure)

    def query_egt_objects_by_ma_orig_id(self, identifier, success, failure):
        """Resolve an official MaRu source ID against both public EGT layers."""
        value = str(identifier or "").strip()
        if not value:
            success([])
            return
        safe = value.replace("'", "''")
        literal = value if value.isdigit() else f"'{safe}'"
        pending = {"boreholes", "observations"}
        rows = []
        errors = []

        def finished(role, payload=None, error=""):
            if role not in pending:
                return
            pending.remove(role)
            if error:
                errors.append(f"{role}: {error}")
            else:
                for feature in (payload or {}).get("features", []):
                    attributes = feature.get("properties", {})
                    if attributes:
                        rows.append((role, attributes))
            if pending:
                return
            if rows or len(errors) < 2:
                success(rows)
            else:
                failure("; ".join(errors))

        for role, type_name in (
            ("boreholes", "faktika:puurauk"),
            ("observations", "faktika:Vaatluspunkt"),
        ):
            url = QUrl(EGT_WFS)
            query = QUrlQuery()
            for key, parameter in (
                ("service", "WFS"),
                ("version", "2.0.0"),
                ("request", "GetFeature"),
                ("typeNames", type_name),
                ("outputFormat", "application/json"),
                ("count", "5"),
                ("CQL_FILTER", f"ma_orig_id={literal}"),
            ):
                query.addQueryItem(key, parameter)
            url.setQuery(query)
            self.get_json(
                url,
                lambda payload, source_role=role: finished(
                    source_role, payload=payload
                ),
                lambda error, source_role=role: finished(
                    source_role, error=str(error)
                ),
            )

    def query_egt_candidates_for_maaru(self, record, success, failure):
        """Return nearby/name-matched EGT points for a MaRu collar record."""
        record = dict(record or {})
        borehole_clauses = []
        observation_clauses = []
        identifier = str(record.get("id") or "").strip()
        if identifier.isdigit():
            # ``ma_orig_id`` only exists on the public borehole layer.
            borehole_clauses.append(f"ma_orig_id={identifier}")
        cleaned_id = str(record.get("uus_id") or "").strip()
        if cleaned_id.isdigit():
            borehole_clauses.append(f"korrastatud_nr={cleaned_id}")
            observation_clauses.append(f"korrastatud_nr={cleaned_id}")
        number = str(record.get("number") or "").strip()
        name = str(record.get("nimetus") or "").strip()
        if number:
            borehole_clauses.append(
                "nimi='" + number.replace("'", "''") + "'"
            )
        if name and name != "-":
            safe_name = name.replace("'", "''")
            borehole_clauses.extend((
                f"alias ILIKE '%{safe_name}%'",
                f"nimi ILIKE '%{safe_name}%'",
            ))
        try:
            x = float(record.get("_maaru_x"))
            y = float(record.get("_maaru_y"))
        except (TypeError, ValueError):
            x = y = None
        if x is not None and y is not None:
            spatial_clause = (
                f"BBOX(xyz,{x - 500:g},{y - 500:g},"
                f"{x + 500:g},{y + 500:g},'EPSG:3301')"
            )
            borehole_clauses.append(spatial_clause)
            observation_clauses.append(spatial_clause)
        if not borehole_clauses and not observation_clauses:
            success([])
            return

        jobs = [
            (role, type_name, clauses)
            for role, type_name, clauses in (
                ("boreholes", "faktika:puurauk", borehole_clauses),
                (
                    "observations", "faktika:Vaatluspunkt",
                    observation_clauses,
                ),
            )
            if clauses
        ]
        pending = {role for role, _type_name, _clauses in jobs}
        rows = []
        errors = []

        def finished(role, payload=None, error=""):
            if role not in pending:
                return
            pending.remove(role)
            if error:
                errors.append(f"{role}: {error}")
            else:
                for feature in (payload or {}).get("features", []):
                    attributes = dict(feature.get("properties") or {})
                    geometry = feature.get("geometry") or {}
                    coordinates = geometry.get("coordinates") or []
                    if len(coordinates) >= 2:
                        attributes["_qeoloog_x_3301"] = coordinates[0]
                        attributes["_qeoloog_y_3301"] = coordinates[1]
                    if attributes:
                        rows.append((role, attributes))
            if pending:
                return
            if rows or len(errors) < len(jobs):
                success(rows)
            else:
                failure("; ".join(errors))

        for role, type_name, clauses in jobs:
            cql_filter = " OR ".join(
                f"({clause})" for clause in clauses
            )
            url = QUrl(EGT_WFS)
            query = QUrlQuery()
            for key, parameter in (
                ("service", "WFS"),
                ("version", "2.0.0"),
                ("request", "GetFeature"),
                ("typeNames", type_name),
                ("outputFormat", "application/json"),
                ("count", "100"),
                ("CQL_FILTER", cql_filter),
            ):
                query.addQueryItem(key, parameter)
            url.setQuery(query)
            self.get_json(
                url,
                lambda payload, source_role=role: finished(
                    source_role, payload=payload,
                ),
                lambda error, source_role=role: finished(
                    source_role, error=str(error),
                ),
            )

    def query_stratigraphic_parent_ids(
        self, indices, success, failure, page_size=1000, contains="",
        include_thickness=False,
    ):
        """Return matching EGT UUIDs and optional interval thicknesses."""
        selected = sorted({
            str(index).strip()
            for index in indices
            if str(index).strip() in STRATIGRAPHIC_INDEX_SET
        })
        contains = str(contains or "").strip()
        if not selected and not contains:
            success({"parent_ids": set(), "thicknesses": {}}
                    if include_thickness else set())
            return

        # Keep URLs short even when many checkboxes are selected.
        batches = [
            selected[offset:offset + 20]
            for offset in range(0, len(selected), 20)
        ] or [[]]
        type_names = (
            "faktika:puurauk_geoloogiline_yksus",
            "faktika:vaatluspunkt_geoloogiline_yksus",
        )
        tasks = [
            (type_name, batch)
            for type_name in type_names
            for batch in batches
        ]
        parent_ids = set()
        thicknesses = {}
        seen_features = set()

        def load_task(task_index, start_index=0):
            if task_index >= len(tasks):
                success({
                    "parent_ids": parent_ids,
                    "thicknesses": thicknesses,
                } if include_thickness else parent_ids)
                return
            type_name, batch = tasks[task_index]
            selected_clauses = []
            for index in batch:
                safe = index.replace("'", "''")
                selected_clauses.append(
                    "("
                    f"indeks ILIKE '{safe}%' OR "
                    f"liityksus_indeks_ylemine ILIKE '{safe}%' OR "
                    f"liityksus_indeks_alumine ILIKE '{safe}%'"
                    ")"
                )
            filters = []
            if selected_clauses:
                filters.append("(" + " OR ".join(selected_clauses) + ")")
            if contains:
                safe_contains = contains.replace("'", "''")
                filters.append(
                    "("
                    f"indeks ILIKE '%{safe_contains}%' OR "
                    f"liityksus_indeks_ylemine ILIKE '%{safe_contains}%' OR "
                    f"liityksus_indeks_alumine ILIKE '%{safe_contains}%'"
                    ")"
                )
            properties = "puurauk_vaatluspunkt_id"
            if include_thickness:
                properties = (
                    "puurauk_vaatluspunkt_id,esri_globalid,paksus,"
                    "z_suht_ylemine,z_suht_alumine,indeks,"
                    "liityksus_indeks_ylemine,liityksus_indeks_alumine"
                )
            url = QUrl(EGT_WFS)
            query = QUrlQuery()
            for key, value in (
                ("service", "WFS"),
                ("version", "2.0.0"),
                ("request", "GetFeature"),
                ("typeNames", type_name),
                ("outputFormat", "application/json"),
                ("propertyName", properties),
                ("count", str(page_size)),
                ("startIndex", str(start_index)),
                ("CQL_FILTER", " AND ".join(filters)),
            ):
                query.addQueryItem(key, value)
            url.setQuery(query)

            def decoded(payload):
                if not isinstance(payload, dict):
                    failure("Invalid EGT WFS response")
                    return
                features = payload.get("features", [])
                for feature in features:
                    row = feature.get("properties", {})
                    value = row.get("puurauk_vaatluspunkt_id")
                    if value not in (None, ""):
                        parent_ids.add(str(value).upper())
                    if include_thickness:
                        feature_key = (
                            type_name,
                            feature.get("id") or row.get("esri_globalid") or (
                                value,
                                row.get("z_suht_ylemine"),
                                row.get("z_suht_alumine"),
                                row.get("indeks"),
                            ),
                        )
                        if feature_key not in seen_features:
                            seen_features.add(feature_key)
                            add_stratigraphic_interval(
                                thicknesses, row, selected, contains,
                            )
                next_index = start_index + len(features)
                try:
                    number_matched = int(payload.get("numberMatched"))
                except (TypeError, ValueError):
                    number_matched = None
                # GeoServer currently caps this endpoint at 1000 rows even
                # when a larger WFS ``count`` is requested.  Honour the
                # response total when available and retain page-size fallback
                # semantics for servers which omit ``numberMatched``.
                has_more = (
                    next_index < number_matched
                    if number_matched is not None
                    else len(features) >= page_size
                )
                if features and has_more:
                    load_task(task_index, next_index)
                else:
                    load_task(task_index + 1)

            self.get_json(url, decoded, failure)

        load_task(0)

    def query_borehole_profile(self, global_id, success, failure):
        """Load a borehole and its nested geology from EGT's public GEA API."""
        encoded_id = quote(str(global_id), safe="")
        url = f"{GEA_API}/puurauk/{encoded_id}"

        def decoded(payload):
            units = payload.get("geoloogiline_yksus_collection", [])
            success(units if isinstance(units, list) else [])

        self.get_json(url, decoded, failure)

    def _get(
        self, url, success, failure, max_bytes=None, authcfg="",
        data_provider="",
    ):
        request = QNetworkRequest(url)
        request.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader,
            "QGIS Qeoloog/3.32.0",
        )
        if authcfg:
            try:
                prepared = QgsApplication.authManager().updateNetworkRequest(
                    request, authcfg, data_provider,
                )
            except (AttributeError, RuntimeError) as error:
                failure(str(error))
                return
            if not prepared:
                failure(
                    "QGIS could not apply the selected authentication configuration."
                )
                return
        reply = self._manager.get(request)
        if authcfg:
            try:
                QgsApplication.authManager().updateNetworkReply(
                    reply, authcfg, data_provider,
                )
            except (AttributeError, RuntimeError):
                # The request already carries the authentication data. Reply
                # expansion is optional and mainly handles provider-specific
                # SSL/authentication follow-up behaviour.
                pass
        self._replies.add(reply)
        limit_exceeded = {"value": False}

        if max_bytes:
            def enforce_size_limit(received, total):
                if (
                    received > max_bytes
                    or total > max_bytes
                ):
                    limit_exceeded["value"] = True
                    reply.abort()

            reply.downloadProgress.connect(enforce_size_limit)

        def finished():
            self._replies.discard(reply)
            try:
                if limit_exceeded["value"]:
                    failure("Response exceeds the configured safety limit.")
                elif reply.error() != QNetworkReply.NetworkError.NoError:
                    failure(reply.errorString())
                else:
                    success(reply.readAll())
            except (ValueError, json.JSONDecodeError) as error:
                failure(str(error))
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)

    def _post_form_json(
        self, url, params, success, failure, authcfg="", data_provider="",
    ):
        """POST an encoded form through QGIS' authenticated network stack."""
        target = url if isinstance(url, QUrl) else QUrl(url)
        request = QNetworkRequest(target)
        request.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader,
            "QGIS Qeoloog/3.32.0",
        )
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/x-www-form-urlencoded; charset=UTF-8",
        )
        if authcfg:
            try:
                prepared = QgsApplication.authManager().updateNetworkRequest(
                    request, authcfg, data_provider,
                )
            except (AttributeError, RuntimeError) as error:
                failure(str(error))
                return
            if not prepared:
                failure(
                    "QGIS could not apply the selected authentication configuration."
                )
                return
        query = QUrlQuery()
        for key, value in (params or {}).items():
            if value is not None:
                query.addQueryItem(str(key), str(value))
        body = QByteArray(query.toString(QUrl.ComponentFormattingOption.FullyEncoded).encode("utf-8"))
        reply = self._manager.post(request, body)
        if authcfg:
            try:
                QgsApplication.authManager().updateNetworkReply(
                    reply, authcfg, data_provider,
                )
            except (AttributeError, RuntimeError):
                pass
        self._replies.add(reply)

        def finished():
            self._replies.discard(reply)
            try:
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    failure(reply.errorString())
                else:
                    payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
                    success(payload)
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
                failure(str(error))
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
