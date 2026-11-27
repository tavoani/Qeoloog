"""Small, dependency-free helpers for ArcGIS FeatureServer layers."""

import json

from urllib.parse import urlsplit, urlunsplit


ARCGIS_FEATURE_PROTOCOL = "ARCGIS_FEATURESERVER"
ARCGIS_MAP_PROTOCOL = "ARCGIS_MAPSERVER"
# EGT policy: Qeoloog may authenticate to and read Portal services, but the
# distributed plugin must not create, update, or delete Portal data.  Keep the
# former validation/editor implementation in the source archive for a future
# separately approved workflow; this constant is deliberately not a user
# setting and cannot be enabled from the UI.
PORTAL_EDITING_ENABLED = False
EGT_PORTAL_ROOT = "https://gis.egt.ee/portal"
EGT_PORTAL_RESOURCE = "https://gis.egt.ee"
EGT_OAUTH_AUTHORIZE_URL = (
    f"{EGT_PORTAL_ROOT}/sharing/rest/oauth2/authorize"
)
EGT_OAUTH_TOKEN_URL = f"{EGT_PORTAL_ROOT}/sharing/rest/oauth2/token"


def egt_oauth_config(client_id, client_secret):
    """Return QGIS' OAuth2 payload without persisting either credential.

    The client values are deliberately supplied by the user from the internal
    EGT guide.  They are never constants in the public plugin package.
    """
    client_id = str(client_id or "").strip()
    client_secret = str(client_secret or "").strip()
    if not client_id or not client_secret:
        raise ValueError("Client ID and Client secret are required.")
    return {
        "accessMethod": 0,
        "apiKey": "",
        "clientId": client_id,
        "clientSecret": client_secret,
        "configType": 1,
        "customHeader": "X-Esri-Authorization",
        "description": "EGT ArcGIS Portal connection created by Qeoloog",
        "grantFlow": 0,
        "name": "EGT Portal",
        "objectName": "",
        "password": "",
        "persistToken": False,
        "queryPairs": {},
        "redirectHost": "127.0.0.1",
        "redirectPort": 7070,
        "redirectUrl": "auth",
        "refreshTokenUrl": "",
        "requestTimeout": 60,
        "requestUrl": EGT_OAUTH_AUTHORIZE_URL,
        "scope": "",
        "state": "",
        "tokenUrl": EGT_OAUTH_TOKEN_URL,
        "username": "",
        "version": 1,
    }


def egt_oauth_config_json(client_id, client_secret):
    """Serialize the QGIS OAuth2 payload in its native compact format."""
    return json.dumps(
        egt_oauth_config(client_id, client_secret),
        ensure_ascii=True,
        separators=(",", ":"),
    )


def is_arcgis_feature_protocol(value):
    """Return whether a saved catalog protocol denotes FeatureServer data."""
    normalized = str(value or "").strip().upper().replace(" ", "_")
    return normalized in {
        "AFS", "ARCGIS", "ARCGIS_FEATURESERVER", "ARCGIS_FEATURE_SERVER",
    }


def is_arcgis_map_protocol(value):
    """Return whether a catalog protocol denotes a public MapServer layer."""
    normalized = str(value or "").strip().upper().replace(" ", "_")
    return normalized in {
        "AMS", "ARCGIS_MAPSERVER", "ARCGIS_MAP_SERVER",
    }


def map_service_root(value):
    """Return a query-free ``.../MapServer`` URL."""
    text = str(value or "").strip()
    parts = urlsplit(text)
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        raise ValueError("ArcGIS MapServer URL is invalid.")
    segments = [segment for segment in parts.path.split("/") if segment]
    map_index = next((
        index for index, segment in enumerate(segments)
        if segment.casefold() == "mapserver"
    ), None)
    if map_index is None:
        raise ValueError("URL must point to an ArcGIS MapServer service.")
    if len(segments) > map_index + 2:
        raise ValueError("ArcGIS MapServer URL contains an invalid path.")
    if len(segments) == map_index + 2:
        try:
            int(segments[-1])
        except ValueError as error:
            raise ValueError(
                "ArcGIS MapServer layer identifier must be numeric."
            ) from error
    root_path = "/" + "/".join(segments[:map_index + 1])
    return urlunsplit((parts.scheme, parts.netloc, root_path, "", ""))


def map_layer_id(service_url, layer_name=""):
    """Resolve a numeric ArcGIS MapServer layer id."""
    candidate = str(layer_name or "").strip()
    if candidate:
        if candidate.isdigit():
            return str(int(candidate))
        candidate_parts = urlsplit(candidate)
        if candidate_parts.scheme and candidate_parts.netloc:
            segments = [part for part in candidate_parts.path.split("/") if part]
            if segments and segments[-1].isdigit():
                return str(int(segments[-1]))
        raise ValueError("ArcGIS MapServer layer identifier must be numeric.")
    segments = [
        part for part in urlsplit(str(service_url or "").strip()).path.split("/")
        if part
    ]
    if segments and segments[-1].isdigit():
        return str(int(segments[-1]))
    raise ValueError("Select a layer from the MapServer service.")


def map_layer_url(service_url, layer_name=""):
    """Build the canonical ArcGIS MapServer layer URL."""
    return f"{map_service_root(service_url)}/{map_layer_id(service_url, layer_name)}"


def feature_service_root(value):
    """Return a query-free ``.../FeatureServer`` URL.

    A layer endpoint such as ``.../FeatureServer/3`` is accepted as input.
    MapServer and generic REST directory URLs are deliberately rejected: only
    FeatureServer layers can expose QGIS' native editing capabilities.
    """
    text = str(value or "").strip()
    parts = urlsplit(text)
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        raise ValueError("ArcGIS FeatureServer URL is invalid.")
    segments = [segment for segment in parts.path.split("/") if segment]
    feature_index = next((
        index for index, segment in enumerate(segments)
        if segment.casefold() == "featureserver"
    ), None)
    if feature_index is None:
        raise ValueError("URL must point to an ArcGIS FeatureServer service.")
    if len(segments) > feature_index + 2:
        raise ValueError("ArcGIS FeatureServer URL contains an invalid path.")
    if len(segments) == feature_index + 2:
        try:
            int(segments[-1])
        except ValueError as error:
            raise ValueError(
                "ArcGIS FeatureServer layer identifier must be numeric."
            ) from error
    root_path = "/" + "/".join(segments[:feature_index + 1])
    scheme = parts.scheme
    if parts.hostname and parts.hostname.casefold() == "gis.egt.ee":
        scheme = "https"
    return urlunsplit((scheme, parts.netloc, root_path, "", ""))


def feature_service_folder(value):
    """Return the ArcGIS REST folder containing a FeatureServer service."""
    root = feature_service_root(value)
    segments = [segment for segment in urlsplit(root).path.split("/") if segment]
    try:
        services_index = next(
            index for index, segment in enumerate(segments)
            if segment.casefold() == "services"
        )
        feature_index = next(
            index for index, segment in enumerate(segments)
            if segment.casefold() == "featureserver"
        )
    except StopIteration:
        return ""
    between = segments[services_index + 1:feature_index]
    return "/".join(between[:-1]) if len(between) > 1 else ""


def portal_feature_service_items(payload):
    """Normalize one ArcGIS Portal search page of Feature Service items."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid EGT Portal search response.")
    error = payload.get("error")
    if isinstance(error, dict):
        details = error.get("details") or []
        message = error.get("message") or "EGT Portal search failed."
        if details:
            message += " " + " ".join(str(item) for item in details if item)
        raise ValueError(message)

    rows = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        try:
            url = feature_service_root(item.get("url"))
        except ValueError:
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            title = urlsplit(url).path.rstrip("/").split("/")[-2]
        access = str(item.get("access") or "org").strip().casefold()
        if access not in {"private", "shared", "org", "public"}:
            access = "org"
        if access == "private":
            access = "shared"
        rows.append({
            "id": str(item.get("id") or "").strip(),
            "title": title,
            "url": url,
            "owner": str(item.get("owner") or "").strip(),
            "access": access,
            "folder": feature_service_folder(url),
            "tags": tuple(
                str(tag).strip() for tag in item.get("tags") or []
                if str(tag).strip()
            ),
        })
    return rows


def deduplicate_portal_feature_services(items):
    """Return one deterministic catalog entry per FeatureServer URL."""
    access_priority = {"shared": 0, "private": 0, "org": 1, "public": 2}
    selected = {}
    for item in items:
        url = str(item.get("url") or "")
        if not url:
            continue
        current = selected.get(url)
        if current is None or (
            access_priority.get(item.get("access"), 3),
            str(item.get("title") or "").casefold(),
        ) < (
            access_priority.get(current.get("access"), 3),
            str(current.get("title") or "").casefold(),
        ):
            selected[url] = item
    return sorted(
        selected.values(),
        key=lambda item: (
            access_priority.get(item.get("access"), 3),
            str(item.get("folder") or "").casefold(),
            str(item.get("title") or "").casefold(),
        ),
    )


def feature_layer_id(service_url, layer_name=""):
    """Resolve a numeric ArcGIS layer/table id from a URL or catalog field."""
    candidate = str(layer_name or "").strip()
    if candidate:
        if candidate.isdigit():
            return str(int(candidate))
        candidate_parts = urlsplit(candidate)
        if candidate_parts.scheme and candidate_parts.netloc:
            segments = [part for part in candidate_parts.path.split("/") if part]
            if segments and segments[-1].isdigit():
                return str(int(segments[-1]))
        raise ValueError("ArcGIS FeatureServer layer identifier must be numeric.")

    parts = urlsplit(str(service_url or "").strip())
    segments = [part for part in parts.path.split("/") if part]
    if segments and segments[-1].isdigit():
        return str(int(segments[-1]))
    raise ValueError("Select a layer from the FeatureServer service.")


def feature_layer_url(service_url, layer_name=""):
    """Build the canonical ArcGIS FeatureServer layer URL."""
    return f"{feature_service_root(service_url)}/{feature_layer_id(service_url, layer_name)}"


def service_layer_options(payload):
    """Return ``(id, title)`` options from FeatureServer service metadata."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid ArcGIS FeatureServer response.")
    error = payload.get("error")
    if isinstance(error, dict):
        details = error.get("details") or []
        message = error.get("message") or "ArcGIS FeatureServer request failed."
        if details:
            message += " " + " ".join(str(item) for item in details if item)
        raise ValueError(message)
    rows = []
    for item in list(payload.get("layers") or []) + list(payload.get("tables") or []):
        if not isinstance(item, dict) or item.get("id") in (None, ""):
            continue
        try:
            identifier = str(int(item["id"]))
        except (TypeError, ValueError):
            continue
        title = str(item.get("name") or identifier).strip() or identifier
        rows.append((identifier, title))
    return sorted(rows, key=lambda item: (int(item[0]), item[1].casefold()))


def arcgis_layer_metadata(payload):
    """Validate and return one ArcGIS FeatureServer layer description."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid ArcGIS FeatureServer layer response.")
    error = payload.get("error")
    if isinstance(error, dict):
        details = error.get("details") or []
        message = error.get("message") or "ArcGIS FeatureServer request failed."
        if details:
            message += " " + " ".join(str(item) for item in details if item)
        raise ValueError(message)
    return payload


def layer_renderer_definition(payload):
    """Return the standard ArcGIS renderer from layer metadata, if present."""
    payload = arcgis_layer_metadata(payload)
    drawing_info = payload.get("drawingInfo")
    if not isinstance(drawing_info, dict):
        return None
    renderer = drawing_info.get("renderer")
    return renderer if isinstance(renderer, dict) and renderer.get("type") else None
