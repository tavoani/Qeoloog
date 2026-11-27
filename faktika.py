"""Pure helpers for EGT's authenticated Faktika editing workflow.

The module deliberately has no QGIS imports.  Keeping validation and ArcGIS
payload construction here makes the rules testable without a live Portal and
ensures the UI cannot silently save a partially derived geological interval.
"""

from copy import deepcopy
from math import isfinite
from unicodedata import normalize as unicode_normalize
from uuid import uuid4

from .stratigraphy import STRATIGRAPHIC_INDICES


FAKTIKA_ITEM_ID = "5ce9fbbe7710417a8c565ec1d0ee2048"
FAKTIKA_SERVICE_URL = (
    "https://gis.egt.ee/arcgis/rest/services/Kaardistamine/"
    "Faktika_t%C3%B6%C3%B6kiht/FeatureServer"
)
FAKTIKA_TEST_SERVICE_URL = (
    "https://testgis.egt.ee/arcgis/rest/services/"
    "Test_Faktika_t%C3%B6%C3%B6kiht/FeatureServer"
)
FAKTIKA_GROUP_NAME = "EGT – Faktika (sisemine)"
FAKTIKA_LAYER_IDS = {
    "objects": 1,
    "people": 2,
    "attachment_keywords": 3,
    "attachments": 4,
    "access_basis": 5,
    "geological_units": 6,
}
FAKTIKA_LAYER_NAMES = {
    1: "Puurauk/vaatluspunkt",
    2: "Isik",
    3: "Manuse märksõnad",
    4: "Manus",
    5: "Juurdepääsu alus",
    6: "Geoloogiline üksus",
}
FAKTIKA_WORKSPACES = {
    "faktika": {
        "item_id": FAKTIKA_ITEM_ID,
        "title": "Faktika töökiht",
        "group": FAKTIKA_GROUP_NAME,
        "url": FAKTIKA_SERVICE_URL,
        "layers": {
            "objects": 1,
            "people": 2,
            "attachment_keywords": 3,
            "attachments": 4,
            "access_basis": 5,
            "geological_units": 6,
        },
    },
    "cleanup": {
        "item_id": "482999bd7f984d5590b5b3f65adff8f1",
        "title": "EGT korrastatavad puuraugud v2",
        "group": "EGT – korrastatavad puuraugud",
        "url": (
            "https://gis.egt.ee/arcgis/rest/services/Kaardistamine/"
            "EGT_korrastatavad_puuraugud_v2/FeatureServer"
        ),
        "layers": {
            "objects": 0,
            "geological_units": 10,
            "people": 11,
            "access_basis": 12,
            "attachments": 13,
            "attachment_keywords": 14,
        },
    },
    "faktika_test": {
        "item_id": "",
        "title": "Faktika testserver",
        "group": "EGT – Faktika testserver",
        "url": FAKTIKA_TEST_SERVICE_URL,
        "advanced": True,
        "discover_layers": True,
        "layers": {
            "objects": 1,
            "people": 2,
            "attachment_keywords": 3,
            "attachments": 4,
            "access_basis": 5,
            "geological_units": 6,
        },
    },
}

FAKTIKA_LAYER_ALIASES = {
    "objects": (
        "Puurauk/vaatluspunkt", "Puurauk ja vaatluspunkt",
        "Puuraugud ja vaatluspunktid",
    ),
    "people": ("Isik", "Isikud"),
    "attachment_keywords": (
        "Manuse märksõnad", "Manuse märksõna", "Manuste märksõnad",
    ),
    "attachments": ("Manus", "Manused"),
    "access_basis": ("Juurdepääsu alus", "Juurdepääsu alused"),
    "geological_units": (
        "Geoloogiline üksus", "Geoloogilised üksused",
    ),
}


def _layer_name_key(value):
    text = unicode_normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").casefold()
    return " ".join(
        "".join(character if character.isalnum() else " " for character in text)
        .split()
    )


def discover_faktika_layer_ids(options):
    """Match a Faktika-compatible service's live layer/table names to roles.

    ArcGIS layer identifiers are deployment-specific and can change when a
    service is republished.  Exact normalized names take priority; a unique
    suffix match also accepts service-specific prefixes without guessing
    between similarly named tables such as ``Manus`` and ``Manuse märksõnad``.
    """
    available = []
    for identifier, title in options or ():
        try:
            layer_id = int(identifier)
        except (TypeError, ValueError):
            continue
        title = str(title or "").strip()
        if title:
            available.append((layer_id, title, _layer_name_key(title)))

    resolved = {}
    missing = []
    for logical_name, aliases in FAKTIKA_LAYER_ALIASES.items():
        keys = {_layer_name_key(alias) for alias in aliases}
        exact = [row for row in available if row[2] in keys]
        candidates = exact
        if not candidates:
            candidates = [
                row for row in available
                if any(row[2].endswith(" " + key) for key in keys)
            ]
        unique = {row[0]: row for row in candidates}
        if len(unique) == 1:
            resolved[logical_name] = next(iter(unique.values()))
        else:
            missing.append(logical_name)

    if missing:
        required = ", ".join(
            FAKTIKA_LAYER_ALIASES[name][0] for name in missing
        )
        names = ", ".join(title for _layer_id, title, _key in available) or "–"
        raise ValueError(
            f"Puuduvad või ebaselged Faktika kihid/tabelid: {required}. "
            f"Teenuses leiti: {names}"
        )
    return {
        logical_name: int(row[0])
        for logical_name, row in resolved.items()
    }

OBJECT_TYPES = {
    1: "Puurauk",
    2: "Vaatluspunkt",
    3: "Vaatluspunkt merel",
}
UNIT_TYPES = {
    1: "Pinnakate",
    2: "Aluspõhi",
    3: "Aluskord",
    997: "Muu / teadmata",
}
UNIT_COLORS = {
    1: "#d7bd72",
    2: "#7796c6",
    3: "#b56b6b",
    997: "#8f8f8f",
}
COMPOUND_INDEX = 9999999


def unit_category_code(rows):
    """Return the parent category implied by geological units.

    A Faktika parent can contain intervals from more than one geological
    domain.  The parent classifier therefore uses the most specific domain
    present, with basement taking precedence over bedrock and cover.  Empty
    or unknown collections deliberately fall back to ``997`` (other /
    unknown) rather than guessing from an index string.
    """
    present = set()
    for row in rows or ():
        value = (row or {}).get("yksus_kood")
        try:
            code = int(value)
        except (TypeError, ValueError):
            text = str(value or "").strip().casefold()
            code = next(
                (
                    candidate for candidate, label in UNIT_TYPES.items()
                    if text == str(label).casefold()
                ),
                None,
            )
        if code in (1, 2, 3):
            present.add(code)
    for code in (3, 2, 1):
        if code in present:
            return code
    return 997

# These are the data fields useful in the compact General tab.  All remaining
# editable fields are still available under "Täpsemad andmed".
PARENT_CORE_FIELDS = (
    "gea_id", "sarv_id", "nimi", "alias", "objekti_tyyp", "yksus_kood",
    "pikkus", "vertikaalne_ulatus", "sygavuse_viis", "kande_alus",
    "maaratud_veealune_sygavus", "kande_alus_nr", "puursydamik",
    "asukoha_tapsusklass",
    "puurimisfirma", "valmimise_kuupaev", "tellija",
    "juurdepaasupiirang", "puurauk_staatus",
)
SEA_ONLY_PARENT_FIELDS = (
    "vertikaalne_ulatus", "sygavuse_viis", "maaratud_veealune_sygavus",
)
UNIT_CORE_FIELDS = (
    "z_suht_ylemine", "z_suht_alumine", "paksus", "yksus_kood",
    "indeks", "kihistik",
    "liityksus_indeks_ylemine", "liityksus_kihistik_ylemine",
    "liityksus_indeks_alumine", "liityksus_kihistik_alumine",
    "genees", "litoloogia", "kivim_nimetus",
    "isik_id", "kande_alus",
    "kande_alus_nr", "markus",
)
AUDIT_FIELDS = {
    "objectid", "globalid", "lisaja", "lisamise_aeg", "muutja",
    "muutmise_aeg", "created_user", "created_date", "last_edited_user",
    "last_edited_date",
}


def normalize_guid(value):
    """Return a canonical braced upper-case ArcGIS GUID, or an empty string."""
    text = str(value or "").strip().strip("{}").upper()
    if not text:
        return ""
    return "{" + text + "}"


def new_guid():
    return "{" + str(uuid4()).upper() + "}"


def escape_where(value):
    return str(value or "").replace("'", "''")


def coded_values(domain):
    """Return ``[(code, label), ...]`` from one ArcGIS coded-value domain."""
    if not isinstance(domain, dict):
        return []
    values = []
    for item in domain.get("codedValues") or []:
        if not isinstance(item, dict) or item.get("code") in (None, ""):
            continue
        values.append((item.get("code"), str(item.get("name") or item["code"])))
    return values


def field_map(metadata):
    return {
        str(field.get("name")): field
        for field in (metadata or {}).get("fields") or []
        if isinstance(field, dict) and field.get("name")
    }


def editable_fields(metadata):
    """Return service fields that may safely be sent back by the editor."""
    return [
        field for field in (metadata or {}).get("fields") or []
        if isinstance(field, dict)
        and field.get("name")
        and field.get("editable", True)
        and str(field.get("name")).casefold() not in AUDIT_FIELDS
    ]


def subtype(metadata, code):
    text = str(code)
    for item in (metadata or {}).get("types") or []:
        if str(item.get("id")) == text:
            return item
    return {}


def subtype_label(metadata, code):
    """Return the ArcGIS subtype name, leaving an unknown code intact."""
    if code in (None, ""):
        return code
    item = subtype(metadata, code)
    return item.get("name") if item.get("name") not in (None, "") else code


def domain_for(metadata, field_name, subtype_code=None):
    """Resolve a field domain, preferring the selected subtype override."""
    requested = str(field_name or "")
    if subtype_code not in (None, ""):
        domains = subtype(metadata, subtype_code).get("domains") or {}
        domain = domains.get(requested)
        if not isinstance(domain, dict):
            domain = next((
                value for name, value in domains.items()
                if str(name).casefold() == requested.casefold()
                and isinstance(value, dict)
            ), None)
        if isinstance(domain, dict):
            return domain
    fields = field_map(metadata)
    field = fields.get(requested)
    if field is None:
        field = next((
            value for name, value in fields.items()
            if str(name).casefold() == requested.casefold()
        ), {})
    return (field or {}).get("domain") or {}


def coded_value_label(metadata, field_name, value, subtype_code=None):
    """Return the ArcGIS coded-value label, leaving unknown values intact."""
    if value in (None, ""):
        return value
    for code, label in coded_values(domain_for(
        metadata, field_name, subtype_code,
    )):
        if str(code) == str(value):
            return label
    return value


def hierarchical_coded_values(options, parent_value):
    """Limit a coded hierarchy to descendants of the selected parent code."""
    if parent_value in (None, ""):
        return []
    parent = str(parent_value).strip()
    try:
        parent = str(int(float(parent)))
    except (TypeError, ValueError):
        return []
    if parent in {"997", "998", "999"}:
        return [
            (code, label) for code, label in options
            if str(code) == parent
        ]
    prefix = parent.rstrip("0")
    if not prefix:
        return []
    descendants = [
        (code, label) for code, label in options
        if str(code).strip().startswith(prefix)
    ]
    # Unknown and Not applicable are valid formation choices regardless of
    # the selected stratigraphic parent. Keeping them in the filtered list
    # also prevents QComboBox from falling back to a raw 997/998 code.
    specials = [
        (code, label) for code, label in options
        if str(code) in {"997", "998"}
    ]
    seen = {str(code) for code, _label in descendants}
    return descendants + [
        item for item in specials if str(item[0]) not in seen
    ]


def decode_coded_row(metadata, row, *, preserve=()):
    """Return a display copy of an ArcGIS row with domain codes decoded.

    The original row remains untouched so edits can still be submitted using
    the service's numeric codes.  ``preserve`` is useful for discriminator
    fields such as ``yksus_kood`` which drawing logic needs numerically.
    """
    source = dict(row or {})
    subtype_field = str((metadata or {}).get("typeIdField") or "")
    subtype_code = source.get(subtype_field) if subtype_field else None
    preserved = {str(name) for name in preserve}
    return {
        name: (
            value if name in preserved or str(name).startswith("_")
            else coded_value_label(metadata, name, value, subtype_code)
        )
        for name, value in source.items()
    }


def template_defaults(metadata, subtype_code=None):
    """Return a deep copy of the matching service template defaults."""
    owner = subtype(metadata, subtype_code) if subtype_code not in (None, "") else metadata
    templates = owner.get("templates") or [] if isinstance(owner, dict) else []
    for item in templates:
        prototype = item.get("prototype") if isinstance(item, dict) else None
        attributes = prototype.get("attributes") if isinstance(prototype, dict) else None
        if isinstance(attributes, dict):
            return deepcopy(attributes)
    return {}


def parent_defaults(metadata, object_type):
    """Defaults for a new Faktika object, including the unpublished sea type."""
    object_type = int(object_type)
    source_type = 2 if object_type == 3 else object_type
    values = template_defaults(metadata, source_type)
    values["objekti_tyyp"] = object_type
    # Type 3 exists in the live data and item renderer but is not published as
    # a subtype.  Observation defaults are therefore the conservative base.
    if object_type == 3:
        values.update({
            "objekti_tyyp": 3,
            "puursydamik": 998,
            "tellija": 998,
            "puurauk_staatus": 998,
            "puurimisfirma": 998,
            "kande_alus": 1,
            "egt_ylevaatus": 0,
        })
    return values


def unit_defaults(metadata, unit_type):
    values = template_defaults(metadata, int(unit_type))
    values["yksus_kood"] = int(unit_type)
    values.setdefault("aktiivne", 1)
    values.setdefault("egt_ylevaatus", 0)
    # Some live Portal templates still publish 0 for coded-value fields even
    # though 0 is not present in the corresponding domain. Never seed an
    # editor row with a value the service itself will reject.
    for field_name in (
        "indeks", "kihistik", "genees", "litoloogia", "kivim_nimetus",
        "liityksus_indeks_ylemine", "liityksus_indeks_alumine",
        "liityksus_kihistik_ylemine", "liityksus_kihistik_alumine",
    ):
        options = coded_values(domain_for(metadata, field_name, unit_type))
        if not options:
            continue
        valid = {str(code) for code, _label in options}
        if str(values.get(field_name)) in valid:
            continue
        fallback = next((
            code for code, _label in options if str(code) == "997"
        ), next((
            code for code, _label in options if str(code) == "998"
        ), None))
        values[field_name] = fallback
    return values


def allowed_unit_type_codes(rows, row_index):
    """Return types that keep known cover/bedrock/basement order valid."""
    ranks = {1: 0, 2: 1, 3: 2}

    def rank(row):
        try:
            return ranks.get(int((row or {}).get("yksus_kood")))
        except (TypeError, ValueError):
            return None

    before = [rank(row) for row in (rows or ())[:max(0, row_index)]]
    after = [rank(row) for row in (rows or ())[row_index + 1:]]
    before = [value for value in before if value is not None]
    after = [value for value in after if value is not None]
    minimum = max(before) if before else 0
    maximum = min(after) if after else 2
    allowed = [code for code, value in ranks.items() if minimum <= value <= maximum]
    return tuple(allowed + [997])


def finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def derive_unit_depths(row, elevation):
    """Return an interval with thickness and absolute boundaries refreshed."""
    result = dict(row or {})
    top = finite_number(result.get("z_suht_ylemine"))
    bottom = finite_number(result.get("z_suht_alumine"))
    z_value = finite_number(elevation)
    if top is not None and bottom is not None:
        result["paksus"] = bottom - top
    if top is not None and z_value is not None:
        result["z_abs_ylemine"] = z_value - top
    if bottom is not None and z_value is not None:
        result["z_abs_alumine"] = z_value - bottom
    return result


def _index_rank(value):
    text = str(value or "").strip()
    try:
        return STRATIGRAPHIC_INDICES.index(text)
    except ValueError:
        return None


def validate_parent(attributes, geometry):
    errors = []
    attrs = attributes or {}
    x = finite_number((geometry or {}).get("x"))
    y = finite_number((geometry or {}).get("y"))
    z = finite_number((geometry or {}).get("z"))
    if x is None or y is None or z is None:
        errors.append("X, Y ja Z peavad olema lõplikud arvud.")
    try:
        object_type = int(attrs.get("objekti_tyyp"))
    except (TypeError, ValueError):
        object_type = 0
    if object_type not in OBJECT_TYPES:
        errors.append("Objekti tüüp on kohustuslik.")
    if attrs.get("asukoha_tapsusklass") in (None, ""):
        errors.append("Asukoha täpsusklass on kohustuslik.")
    if attrs.get("kande_alus") in (None, ""):
        errors.append("Kande alus on kohustuslik.")
    return errors


def validate_units(rows, elevation, total_depth=None):
    """Return ``(derived_rows, errors, warnings)`` in depth order."""
    derived = [derive_unit_depths(row, elevation) for row in rows or []]
    derived.sort(key=lambda row: (
        finite_number(row.get("z_suht_ylemine")) is None,
        finite_number(row.get("z_suht_ylemine")) or 0,
        finite_number(row.get("z_suht_alumine")) or 0,
    ))
    errors, warnings = [], []
    previous = None
    previous_rank = None
    deepest_unit_rank = None
    depth_limit = finite_number(total_depth)
    order = {1: 0, 2: 1, 3: 2}
    for index, row in enumerate(derived, 1):
        top = finite_number(row.get("z_suht_ylemine"))
        bottom = finite_number(row.get("z_suht_alumine"))
        unit_type = row.get("yksus_kood")
        if top is None or bottom is None:
            errors.append(f"Rida {index}: Z1 suht ja Z2 suht on kohustuslikud.")
            continue
        if top < 0 or bottom <= top:
            errors.append(f"Rida {index}: sügavusvahemik peab olema kasvav ja algama 0 m-st või sügavamalt.")
        if depth_limit is not None and bottom > depth_limit + 1e-8:
            errors.append(f"Rida {index}: alumine sügavus ületab objekti sügavuse.")
        if unit_type in (None, ""):
            errors.append(f"Rida {index}: geoloogilise üksuse tüüp on kohustuslik.")
        if row.get("indeks") in (None, ""):
            errors.append(f"Rida {index}: indeks on kohustuslik.")
        elif str(row.get("indeks")) == "0":
            errors.append(f"Rida {index}: indeks 0 pole lubatud.")
        if str(unit_type) == "1" and row.get("genees") in (None, ""):
            errors.append(f"Rida {index}: pinnakatte genees on kohustuslik.")
        if row.get("isik_id") in (None, ""):
            errors.append(f"Rida {index}: autor on kohustuslik.")
        if row.get("kande_alus") in (None, ""):
            errors.append(f"Rida {index}: alus on kohustuslik.")
        compound_upper = row.get("liityksus_indeks_ylemine")
        compound_lower = row.get("liityksus_indeks_alumine")
        if bool(compound_upper not in (None, "", 997, 998)) != bool(
            compound_lower not in (None, "", 997, 998)
        ):
            errors.append(
                f"Rida {index}: liitüksuse ülemine ja alumine indeks tuleb määrata koos."
            )
        upper_rank = _index_rank(compound_upper)
        lower_rank = _index_rank(compound_lower)
        if (
            upper_rank is not None and lower_rank is not None
            and upper_rank < lower_rank
        ):
            errors.append(
                f"Rida {index}: liitüksuse ülemine ja alumine indeks on vales järjekorras."
            )
        if previous is not None:
            previous_bottom = finite_number(previous.get("z_suht_alumine"))
            if previous_bottom is not None and top < previous_bottom - 1e-8:
                errors.append(f"Rida {index}: intervall kattub eelmise intervalliga.")
            elif previous_bottom is not None and top > previous_bottom + 1e-8:
                warnings.append(f"Ridade {index - 1} ja {index} vahel on kirjeldamata vahemik.")
            if (
                str(previous.get("indeks") or "") == str(row.get("indeks") or "")
                and str(previous.get("litoloogia") or "") == str(row.get("litoloogia") or "")
            ):
                warnings.append(f"Read {index - 1} ja {index} on identsed naaberüksused.")
        rank = _index_rank(row.get("indeks"))
        if rank is not None and previous_rank is not None and rank < previous_rank:
            warnings.append(f"Rida {index}: stratigraafiline järjestus võib olla vastupidine.")
        if rank is not None:
            previous_rank = rank
        try:
            unit_rank = order.get(int(unit_type))
        except (TypeError, ValueError):
            unit_rank = None
        if (
            unit_rank is not None and deepest_unit_rank is not None
            and unit_rank < deepest_unit_rank
        ):
            errors.append(
                f"Rida {index}: üksuse kategooria ei tohi sügavusega tagasi ülespoole liikuda."
            )
        if unit_rank is not None:
            deepest_unit_rank = max(
                deepest_unit_rank if deepest_unit_rank is not None else unit_rank,
                unit_rank,
            )
        previous = row
    return derived, errors, warnings


def arcgis_feature(attributes, geometry=None):
    feature = {"attributes": dict(attributes or {})}
    if geometry is not None:
        feature["geometry"] = {
            "x": float(geometry["x"]),
            "y": float(geometry["y"]),
            "z": float(geometry["z"]),
            "spatialReference": {"wkid": 3301},
        }
    return feature


def build_apply_edits(
    parent, geometry, units, *, is_new=False, deleted_unit_ids=(),
    attachments=(), deleted_attachment_ids=(), access_rows=(),
    deleted_access_ids=(), attachment_keywords=(), deleted_keyword_ids=(),
    people=(), deleted_person_ids=(),
):
    """Build service-wide edits with GlobalID-based parent relationships."""
    parent_attributes = dict(parent or {})
    parent_attributes.pop("_existing", None)
    parent_guid = normalize_guid(parent_attributes.get("globalid")) or new_guid()
    parent_attributes["globalid"] = parent_guid
    parent_operation = "adds" if is_new else "updates"
    edits = [{
        "id": FAKTIKA_LAYER_IDS["objects"],
        parent_operation: [arcgis_feature(parent_attributes, geometry)],
    }]

    def child_edit(layer_id, rows, foreign_key, deleted_ids):
        adds, updates = [], []
        for source in rows or []:
            row = dict(source)
            guid = normalize_guid(row.get("globalid"))
            existing = bool(row.pop("_existing", False))
            row["globalid"] = guid or new_guid()
            row[foreign_key] = parent_guid
            (updates if existing else adds).append(arcgis_feature(row))
        edit = {"id": layer_id}
        if adds:
            edit["adds"] = adds
        if updates:
            edit["updates"] = updates
        deletes = [normalize_guid(value) for value in deleted_ids or () if normalize_guid(value)]
        if deletes:
            edit["deletes"] = deletes
        if len(edit) > 1:
            edits.append(edit)

    child_edit(6, units, "puurauk_vaatluspunkt_id", deleted_unit_ids)
    child_edit(4, attachments, "puurauk_vaatluspunkt_id", deleted_attachment_ids)
    child_edit(5, access_rows, "puurauk_vaatluspunkt_id", deleted_access_ids)
    # Keyword rows are children of attachments rather than the point.  Their
    # ``manus_id`` is selected explicitly in the editor and must be preserved.
    adds, updates = [], []
    for source in attachment_keywords or ():
        row = dict(source)
        guid = normalize_guid(row.get("globalid"))
        existing = bool(row.pop("_existing", False))
        row["globalid"] = guid or new_guid()
        (updates if existing else adds).append(arcgis_feature(row))
    keyword_edit = {"id": FAKTIKA_LAYER_IDS["attachment_keywords"]}
    if adds:
        keyword_edit["adds"] = adds
    if updates:
        keyword_edit["updates"] = updates
    deletes = [
        normalize_guid(value) for value in deleted_keyword_ids or ()
        if normalize_guid(value)
    ]
    if deletes:
        keyword_edit["deletes"] = deletes
    if len(keyword_edit) > 1:
        edits.append(keyword_edit)

    person_adds, person_updates = [], []
    for source in people or ():
        row = dict(source)
        guid = normalize_guid(row.get("globalid"))
        existing = bool(row.pop("_existing", False))
        row["globalid"] = guid or new_guid()
        (person_updates if existing else person_adds).append(arcgis_feature(row))
    person_edit = {"id": FAKTIKA_LAYER_IDS["people"]}
    if person_adds:
        person_edit["adds"] = person_adds
    if person_updates:
        person_edit["updates"] = person_updates
    person_deletes = [
        normalize_guid(value) for value in deleted_person_ids or ()
        if normalize_guid(value)
    ]
    if person_deletes:
        person_edit["deletes"] = person_deletes
    if len(person_edit) > 1:
        edits.append(person_edit)
    return edits


def validate_apply_edits_response(payload):
    """Raise on a service-level or per-feature ArcGIS edit error."""
    if not isinstance(payload, list):
        error = payload.get("error") if isinstance(payload, dict) else None
        message = error.get("message") if isinstance(error, dict) else "Vigane Portali vastus."
        raise ValueError(message or "Vigane Portali vastus.")
    failures = []
    for layer_result in payload:
        layer_id = layer_result.get("id", "?") if isinstance(layer_result, dict) else "?"
        for operation in ("addResults", "updateResults", "deleteResults"):
            for result in (layer_result or {}).get(operation) or []:
                if result.get("success") is False or result.get("error"):
                    error = result.get("error") or {}
                    failures.append(
                        f"kiht {layer_id}: {error.get('description') or error.get('message') or 'muudatus ebaõnnestus'}"
                    )
    if failures:
        raise ValueError("; ".join(failures))
    return payload
