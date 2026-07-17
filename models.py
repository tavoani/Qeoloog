"""Layer catalog and persistent Qeoloog settings."""

from dataclasses import asdict, dataclass
import json

from qgis.core import QgsSettings


GROUPS = ("basemaps", "geology", "studies", "helpers")
DEFAULT_GROUP_STATE = {group: True for group in GROUPS}


@dataclass
class LayerDefinition:
    code: str
    name: str
    protocol: str
    url: str
    layer_name: str
    style: str = ""
    base_map: bool = False
    color: str = "#356a8a"
    role: str = ""
    name_en: str = ""
    home_group: str = "helpers"
    placement: str = "dropdown"  # toolbar, dropdown, disabled
    previous_placement: str = ""

    def __post_init__(self):
        if self.previous_placement not in {"toolbar", "dropdown"}:
            self.previous_placement = (
                self.placement if self.placement in {"toolbar", "dropdown"} else "dropdown"
            )

    @classmethod
    def from_dict(cls, value):
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value[key] for key in allowed if key in value})

    def to_dict(self):
        return asdict(self)


def _layer(code, name, name_en, protocol, url, layer_name, **kwargs):
    return LayerDefinition(
        code=code,
        name=name,
        name_en=name_en,
        protocol=protocol,
        url=url,
        layer_name=layer_name,
        **kwargs,
    )


K50 = "https://maps.egt.ee/geoserver/k50/ows"
K200 = "https://maps.egt.ee/geoserver/k200/ows"
EGF = "https://maps.egt.ee/geoserver/egf/ows"
MINERALS = "https://maps.egt.ee/geoserver/maavarad/ows"
KMA = "https://gsavalik.envir.ee/geoserver/kmakitsendused/wms"
KMA_LAYERS = ",".join(
    f"kma_avalik_{name}"
    for name in (
        "asjaoigus",
        "elekter",
        "gaas",
        "geodeesia",
        "kaugkyte",
        "kemikaal",
        "looduskaitse",
        "maaparandus",
        "muinsuskaitse",
        "planeering",
        "reostusoht",
        "ressurss",
        "riigikaitse",
        "side",
        "sundvaldus",
        "transport",
        "veekogu",
        "veevarustus",
    )
)


DEFAULT_LAYERS = (
    _layer(
        "PK", "Maa- ja Ruumiamet - põhikaart reljeefivarjutusega",
        "Estonian Land and Spatial Development Board - shaded relief map", "WMS",
        "https://kaart.maaamet.ee/wms/alus", "pohi_vv", base_map=True,
        color="#436b3a", home_group="basemaps", placement="toolbar",
    ),
    _layer(
        "OF", "Maa- ja Ruumiamet - ortofoto", "Orthophoto", "WMS",
        "https://kaart.maaamet.ee/wms/fotokaart", "EESTIFOTO", base_map=True,
        color="#276b83", home_group="basemaps", placement="toolbar",
    ),
    _layer(
        "HK", "Maa- ja Ruumiamet - hübriidkaart", "Hybrid map", "WMS",
        "https://kaart.maaamet.ee/wms/fotokaart", "HYBRID", base_map=True,
        color="#66548f", home_group="basemaps", placement="toolbar",
    ),
    _layer(
        "PA", "EGT - puuraugud", "EGS - boreholes", "WFS",
        "https://maps.egt.ee/geoserver/faktika/ows", "faktika:puurauk",
        color="#a55b24", role="boreholes", home_group="geology", placement="toolbar",
    ),
    _layer(
        "VP", "EGT - vaatluspunktid", "EGS - observation points", "WFS",
        "https://maps.egt.ee/geoserver/faktika/ows", "faktika:Vaatluspunkt",
        color="#187f78", role="observations", home_group="geology", placement="toolbar",
    ),
    _layer(
        "SK", "SARV - kohad", "SARV - locations", "SARV",
        "https://rwapi.geoloogia.info/api/v1/public", "localities,sites",
        color="#356f92", role="sarv_points", home_group="geology", placement="toolbar",
    ),
    _layer(
        "AP", "EGT - 1:50 000 aluspõhja avamused", "EGS - 1:50,000 bedrock outcrops",
        "WMS", K50, "ap_avamus_a_50t", style="ap_avamused_k50",
        color="#8a3e58", home_group="geology", placement="toolbar",
    ),
    _layer("Q50", "Pinnakattesetted 1:50 000", "Quaternary deposits 1:50,000", "WMS", K50, "q_litoloogia_a_50t", color="#e3c74f", home_group="geology"),
    _layer("RI", "Aluspõhja rikkevööndid", "Bedrock fault zones", "WFS", K50, "k50:ap_rike_j_50t", color="#a34d4d", home_group="geology"),
    _layer("MO", "Mattunud orud", "Buried valleys", "WMS", K50, "ap_org_a_50t", color="#7d6b9e", home_group="geology"),
    _layer("AR", "Aluspõhja reljeefi samakõrgusjooned", "Bedrock relief contours", "WMS", K50, "ap_isojoon_j_50t", color="#80624b", home_group="geology"),
    _layer("KA", "Allikad ja karst", "Springs and karst", "WFS", K50, "k50:hg_punkt_p_50t", color="#3184a3", home_group="geology"),
    _layer("PV", "Põhjavee kaitstus", "Groundwater vulnerability", "WMS", K50, "hg_pvk_kaitstuse_klass_a_50t", color="#3b7b9f", home_group="geology"),
    _layer("AK", "Aluskorra avamused 1:200 000", "Basement outcrops 1:200,000", "WMS", K200, "ak_avamus_a_200t", color="#b45b75", home_group="geology"),
    _layer("RN", "Radooniriski ruutkaart", "Radon risk grid", "WMS", K200, "rnrisk_ruutkaart_200t", color="#9b476a", home_group="geology"),
    _layer("MG", "Aeromagnetilised anomaaliad", "Aeromagnetic anomalies", "WMS", K200, "mg_isojooned_200t", color="#6d539a", home_group="geology"),
    _layer("GR", "Gravitatsioonianomaaliad", "Gravity anomalies", "WMS", K200, "grb_isojooned_200t", color="#505b87", home_group="geology"),
    _layer("EGF", "Geoloogiafondi uuringualad", "Geological archive survey areas", "WFS", EGF, "egf:wfs_koik_uuringualad", color="#6b5c45", home_group="studies"),
    _layer("EH", "Ehitusgeoloogilised uuringupunktid", "Engineering geology survey points", "WFS", EGF, "egf:wfs_ehitusgeoloogilised_punktid", color="#8a7048", home_group="studies"),
    _layer("MR", "Maardlate piirid", "Mineral deposit boundaries", "WFS", MINERALS, "maavarad:maardla_piir", color="#a46a31", home_group="studies"),
    _layer("ME", "Aktiivsed mäeeraldised", "Active mining claims", "WFS", MINERALS, "maavarad:aktiivne_maeeraldis", color="#a53f32", home_group="studies"),
    _layer("UA", "Aktiivsed uuringualad", "Active exploration areas", "WFS", MINERALS, "maavarad:aktiivne_uuringuala", color="#bc873b", home_group="studies"),
    _layer("SE", "Seismilised sündmused", "Seismic events", "WFS", "https://maps.egt.ee/geoserver/seismo/ows", "seismo:seismiline_syndmus", color="#a32727", home_group="studies"),
    _layer("KÜ", "Kehtivad katastriüksused", "Valid cadastral parcels", "WFS", "https://aks.geoportaal.ee/aks-ogc", "aks:ads_ky", color="#536f46", home_group="helpers"),
    _layer("HP", "Haldusüksused", "Administrative units", "WFS", "https://aks.geoportaal.ee/aks-ogc", "aks:knr_haldusyksused", color="#677a8d", home_group="helpers"),
    _layer("VR", "Värviline reljeefvarjutus", "Coloured hillshade", "WMS", "https://kaart.maaamet.ee/wms/fotokaart", "vreljeef", base_map=True, color="#6c8753", home_group="basemaps"),
    _layer("KM", "Maakatte kõrgusmudel", "Canopy height model", "WMS", "https://kaart.maaamet.ee/wms/fotokaart", "nDSM", base_map=True, color="#567b63", home_group="basemaps"),
    _layer("AJ", "Ajaloolised kaardid", "Historical maps", "WMS", "https://kaart.maaamet.ee/wms/ajalooline", "MA-AJAL", base_map=True, color="#8b6f50", home_group="basemaps"),
    _layer("KT", "Kitsenduste vööndid", "Restriction zones", "WMS", KMA, KMA_LAYERS, color="#8f4d65", home_group="helpers"),
)


class PluginSettings:
    ORGANIZATION = "Qeoloog"
    LEGACY_ORGANIZATION = "EestiWMSNupud"
    KEY_LAYERS = "layers_json"
    KEY_TOGGLE_MODE = "toggle_mode"
    KEY_LANGUAGE = "language"
    KEY_GROUPS = "groups_json"
    KEY_SARV_MATCHES = "sarv_matches_json"

    @classmethod
    def load_layers(cls):
        settings = QgsSettings()
        raw = settings.value(f"{cls.ORGANIZATION}/{cls.KEY_LAYERS}", "", type=str)
        if not raw:
            raw = settings.value(f"{cls.LEGACY_ORGANIZATION}/{cls.KEY_LAYERS}", "", type=str)
        values = []
        if raw:
            try:
                values = json.loads(raw)
            except (TypeError, ValueError):
                values = []
        defaults = {item.code: item for item in DEFAULT_LAYERS}
        layers = []
        for value in values:
            try:
                default = defaults.get(value.get("code"))
                merged = default.to_dict() if default else {}
                merged.update(value)
                if "placement" not in value:
                    merged["placement"] = (
                        "toolbar"
                        if value.get("code") in {"PK", "OF", "HK", "PA", "VP", "SK", "AP"}
                        else "dropdown"
                    )
                layers.append(LayerDefinition.from_dict(merged))
            except (TypeError, KeyError):
                continue
        present = {item.code for item in layers}
        for item in DEFAULT_LAYERS:
            if item.code in present:
                continue
            definition = LayerDefinition.from_dict(item.to_dict())
            if item.code == "SK":
                after = next((
                    index for index, current in reversed(list(enumerate(layers)))
                    if current.code in {"PA", "VP"}
                ), None)
                layers.insert(after + 1 if after is not None else len(layers), definition)
            else:
                layers.append(definition)
        return layers or [LayerDefinition.from_dict(item.to_dict()) for item in DEFAULT_LAYERS]

    @classmethod
    def save_layers(cls, layers):
        raw = json.dumps([layer.to_dict() for layer in layers], ensure_ascii=False)
        QgsSettings().setValue(f"{cls.ORGANIZATION}/{cls.KEY_LAYERS}", raw)

    @classmethod
    def reset_layers(cls):
        layers = [LayerDefinition.from_dict(item.to_dict()) for item in DEFAULT_LAYERS]
        cls.save_layers(layers)
        return layers

    @classmethod
    def load_toggle_mode(cls):
        settings = QgsSettings()
        return settings.value(
            f"{cls.ORGANIZATION}/{cls.KEY_TOGGLE_MODE}",
            settings.value(f"{cls.LEGACY_ORGANIZATION}/{cls.KEY_TOGGLE_MODE}", False, type=bool),
            type=bool,
        )

    @classmethod
    def save_toggle_mode(cls, enabled):
        QgsSettings().setValue(f"{cls.ORGANIZATION}/{cls.KEY_TOGGLE_MODE}", bool(enabled))

    @classmethod
    def load_language(cls):
        value = QgsSettings().value(f"{cls.ORGANIZATION}/{cls.KEY_LANGUAGE}", "et", type=str)
        return value if value in {"et", "en"} else "et"

    @classmethod
    def save_language(cls, language):
        QgsSettings().setValue(f"{cls.ORGANIZATION}/{cls.KEY_LANGUAGE}", language)

    @classmethod
    def load_groups(cls):
        raw = QgsSettings().value(f"{cls.ORGANIZATION}/{cls.KEY_GROUPS}", "", type=str)
        try:
            values = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            values = {}
        return {group: bool(values.get(group, True)) for group in GROUPS}

    @classmethod
    def save_groups(cls, groups):
        QgsSettings().setValue(
            f"{cls.ORGANIZATION}/{cls.KEY_GROUPS}",
            json.dumps({group: bool(groups.get(group, True)) for group in GROUPS}),
        )

    @classmethod
    def load_sarv_matches(cls):
        raw = QgsSettings().value(
            f"{cls.ORGANIZATION}/{cls.KEY_SARV_MATCHES}", "", type=str,
        )
        try:
            values = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            values = {}
        return values if isinstance(values, dict) else {}

    @classmethod
    def save_sarv_matches(cls, matches):
        QgsSettings().setValue(
            f"{cls.ORGANIZATION}/{cls.KEY_SARV_MATCHES}",
            json.dumps(matches, ensure_ascii=False),
        )
