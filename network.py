"""Asynchronous HTTP helpers using QGIS' shared network stack."""

import json
from urllib.parse import quote, urlencode

from qgis.PyQt.QtCore import QUrl, QUrlQuery, QXmlStreamReader
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import QgsNetworkAccessManager


AUQ_REST = "https://gis.egt.ee/arcgis/rest/services/AUQ_public/AUQ_webapp_open/MapServer"
EGT_WFS = "https://maps.egt.ee/geoserver/faktika/ows"
GEA_API = "https://gea-api.egt.ee"
SARV_API = "https://rwapi.geoloogia.info/api/v1/public"
MAX_CAPABILITIES_BYTES = 20 * 1024 * 1024


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

    def get_json(self, url, success, failure):
        target = url if isinstance(url, QUrl) else QUrl(url)
        self._get(target, lambda data: success(json.loads(bytes(data).decode("utf-8"))), failure)

    def query_auq(self, table_id, where, success, failure, order_by=""):
        url = QUrl(f"{AUQ_REST}/{table_id}/query")
        query = QUrlQuery()
        query.addQueryItem("f", "json")
        query.addQueryItem("where", where)
        query.addQueryItem("outFields", "*")
        query.addQueryItem("returnGeometry", "false")
        query.addQueryItem("resultRecordCount", "2000")
        if order_by:
            query.addQueryItem("orderByFields", order_by)
        url.setQuery(query)
        self.get_json(url, success, failure)

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
        self.get_json(url, success, failure)

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

        def decoded(payload):
            features = payload.get("features", [])
            success([feature.get("properties", {}) for feature in features])

        self.get_json(url, decoded, failure)

    def query_borehole_profile(self, global_id, success, failure):
        """Load a borehole and its nested geology from EGT's public GEA API."""
        encoded_id = quote(str(global_id), safe="")
        url = f"{GEA_API}/puurauk/{encoded_id}"

        def decoded(payload):
            units = payload.get("geoloogiline_yksus_collection", [])
            success(units if isinstance(units, list) else [])

        self.get_json(url, decoded, failure)

    def _get(self, url, success, failure, max_bytes=None):
        request = QNetworkRequest(url)
        request.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader,
            "QGIS Qeoloog/3.8.1",
        )
        reply = self._manager.get(request)
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
                    failure(
                        "Capabilities response exceeds the 20 MB safety limit."
                    )
                elif reply.error() != QNetworkReply.NetworkError.NoError:
                    failure(reply.errorString())
                else:
                    success(reply.readAll())
            except (ValueError, json.JSONDecodeError) as error:
                failure(str(error))
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
