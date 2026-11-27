"""Layer catalog and persistent Qeoloog settings."""

from dataclasses import asdict, dataclass
import json

from qgis.core import QgsSettings


GROUPS = ("basemaps", "geology", "studies", "helpers")
DEFAULT_GROUP_STATE = {group: True for group in GROUPS}
EGT_LABEL_FIELD_KEYS = (
    "name", "alias", "borehole_depth", "cover_thickness", "bedrock_elevation",
    "depth_0_5", "bedrock_outcrop",
)
DEFAULT_EGT_LABEL_FIELDS = {
    "boreholes": ("name",),
    "observations": ("depth_0_5",),
}

EGT_LABEL_KEYS_BY_ROLE = {
    "boreholes": EGT_LABEL_FIELD_KEYS,
    "observations": EGT_LABEL_FIELD_KEYS,
}

MAP_LABEL_KEYS_BY_ROLE = {
    **EGT_LABEL_KEYS_BY_ROLE,
    "veka_boreholes": ("name", "borehole_depth", "kkr_kood"),
    # One choice set for the SARV locality, research-site and core point layers.
    "sarv": ("name", "borehole_depth", "number"),
}
DEFAULT_MAP_LABEL_FIELDS = {
    **DEFAULT_EGT_LABEL_FIELDS,
    "veka_boreholes": ("name",),
    "sarv": ("name",),
}


def normalize_map_label_fields(values):
    """Discard unsupported fields, retaining stored empty lists and defaults."""
    values = values if isinstance(values, dict) else {}
    result = {}
    for role, available in MAP_LABEL_KEYS_BY_ROLE.items():
        defaults = DEFAULT_MAP_LABEL_FIELDS[role]
        selected = values.get(role, defaults)
        if not isinstance(selected, (list, tuple, set, frozenset)):
            selected = defaults
        result[role] = [key for key in available if key in selected]
    return result


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
    use_portal_auth: bool = False
    service_crs: str = "EPSG:3301"
    menu_group: str = ""

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
MAP_GRIDS = "https://teenus.maaamet.ee/ows/kaardivorgud"
KMA = "https://gsavalik.envir.ee/geoserver/kmakitsendused/wms"
KMA_TECHNICAL_LAYERS = ",".join(
    f"kma_avalik_{name}"
    for name in ("side", "elekter", "gaas", "kaugkyte", "veevarustus")
)
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
GTK_BEDROCK_WMS = (
    "https://gtkdata.gtk.fi/arcgis/services/Rajapinnat/"
    "GTK_Kalliopera_WMS/MapServer/WMSServer"
)
GTK_BEDROCK_WFS = (
    "https://gtkdata.gtk.fi/arcgis/services/Rajapinnat/"
    "GTK_Kalliopera_WFS/MapServer/WFSServer"
)
GTK_SOIL_WMS = (
    "https://gtkdata.gtk.fi/arcgis/services/Rajapinnat/"
    "GTK_Maapera_WMS/MapServer/WMSServer"
)
GTK_GEOPHYSICS_WMS = (
    "https://gtkdata.gtk.fi/arcgis/services/Rajapinnat/"
    "GTK_Geofysiikka_WMS/MapServer/WMSServer"
)
GTK_GROUND_INVESTIGATIONS_WFS = (
    "https://gtkdata.gtk.fi/arcgis/services/Rajapinnat/"
    "GTK_Pohjatutkimukset_WFS/MapServer/WFSServer"
)
LATVIA_BEDROCK_WMS = (
    "https://geodata.lvgmc.lv/server/services/Public/"
    "PamatiezuKarte200tk/MapServer/WMSServer"
)
LATVIA_QUATERNARY_WMS = (
    "https://geodata.lvgmc.lv/server/services/Public/"
    "KvartaraKarte/MapServer/WMSServer"
)
LATVIA_BOREHOLES_MAPSERVER = (
    "https://geodata.lvgmc.lv/server/rest/services/"
    "%C4%A2eolo%C4%A3iskie_urbumi_MIL1/MapServer"
)
LEGACY_LATVIA_INSPIRE_GEOLOGY_WFS = (
    "https://geo-dpps.viss.gov.lv/api/DPPSPackage/client/"
    "Geologiski_315_GJeJBI/341b42b3-41de-4d21-9a2a-7bd0ae70af68"
)
LATVIA_INSPIRE_GEOLOGY_WFS = "https://geoserver.lvgmc.lv/geoserver/ge/ows"
LATVIA_GROUNDWATER_WFS = (
    "https://geodata.lvgmc.lv/server/services/GroundWaterBody_LV/"
    "MapServer/WFSServer"
)
LATVIA_MINERALS_WFS = "https://geoserver.lvgmc.lv/geoserver/ZDz/ows"


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
        "https://rwapi.geoloogia.info/api/v1/public", "localities,sites,drillcores",
        color="#356f92", role="sarv_points", home_group="geology", placement="toolbar",
    ),
    _layer(
        "MP", "MaRu - puursüdamike andmebaas",
        "MaRu - historical drill-core database", "MAARU",
        "https://geoportaal.maaamet.ee/docs/geoloogia/andmed/puuraugud.zip",
        "pa", color="#8b643f", role="maaru_cores",
        home_group="geology", placement="dropdown",
    ),
    _layer(
        "VK", "VEKA - puurkaevud", "VEKA - water wells", "VEKA",
        "https://keskkonnaandmed.envir.ee", "f_puuraugud",
        color="#2876a8", role="veka_boreholes", home_group="geology",
        placement="dropdown",
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
    _layer(
        "AP200", "Aluspõhja kaart 1:200 000", "Bedrock map 1:200,000",
        "WMS", K200, "aluspohi", color="#8a3e58", home_group="geology",
    ),
    _layer(
        "Q200", "Pinnakatte kaart 1:200 000", "Quaternary map 1:200,000",
        "WMS", K200, "pinnakate", color="#e3c74f", home_group="geology",
    ),
    _layer("AK", "Aluskorra avamused 1:200 000", "Basement outcrops 1:200,000", "WMS", K200, "ak_avamus_a_200t", color="#b45b75", home_group="geology"),
    _layer("RN", "Radooniriski ruutkaart", "Radon risk grid", "WMS", K200, "rnrisk_ruutkaart_200t", color="#9b476a", home_group="geology"),
    _layer("MG", "Aeromagnetilised anomaaliad", "Aeromagnetic anomalies", "WMS", K200, "mg_isojooned_200t", color="#6d539a", home_group="geology"),
    _layer("GR", "Gravitatsioonianomaaliad", "Gravity anomalies", "WMS", K200, "grb_isojooned_200t", color="#505b87", home_group="geology"),
    _layer(
        "GKB", "GTK – Soome aluspõhja litoloogilised üksused 1:200 000",
        "GTK – Finnish bedrock lithological units 1:200,000", "WMS",
        GTK_BEDROCK_WMS, "Litologiset_yksiköt_200k25132",
        color="#9b6f53", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_bedrock_lithology",
    ),
    _layer(
        "GKR", "GTK – Soome aluspõhja rikked 1:200 000",
        "GTK – Finnish bedrock faults 1:200,000", "WMS",
        GTK_BEDROCK_WMS, "Siirrosrakenteet_200k65168",
        color="#a84b4b", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_bedrock_faults",
    ),
    _layer(
        "GQP", "GTK – Soome pinnakatte põhjakiht 1:50 000",
        "GTK – Finnish superficial deposits, basal layer 1:50,000", "WMS",
        GTK_SOIL_WMS, "maapera_50k_pohjamaalajit",
        color="#c9aa58", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_soil_basal",
    ),
    _layer(
        "GQS", "GTK – Soome pinnakatte pindmine kiht 1:50 000",
        "GTK – Finnish superficial deposits, surface layer 1:50,000", "WMS",
        GTK_SOIL_WMS, "maapera_50k_pintamaalajit",
        color="#dfc875", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_soil_surface",
    ),
    _layer(
        "GAM", "GTK – Soome aeromagnetiline anomaaliakaart",
        "GTK – Finnish aeromagnetic anomaly map", "WMS",
        GTK_GEOPHYSICS_WMS, "aeromagneettinen_anomaliakartta",
        color="#6a5696", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_aeromagnetic",
    ),
    _layer(
        "GRA", "GTK – Soome aeroradiomeetriline koondkaart",
        "GTK – Finnish aeroradiometric composite map", "WMS",
        GTK_GEOPHYSICS_WMS, "aeroradiometrinen_yhdistelmakartta",
        color="#7f6b42", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_aeroradiometric",
    ),
    _layer(
        "GOB", "GTK – Soome aluspõhja vaatlused",
        "GTK – Finnish bedrock observations", "WFS", GTK_BEDROCK_WFS,
        "Rajapinnat_GTK_Kalliopera_WFS:Kallioperähavainnot",
        color="#3d7f68", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_bedrock_observations",
    ),
    _layer(
        "GDR", "GTK – Soome aluspõhja puurimised",
        "GTK – Finnish bedrock drillings", "WFS", GTK_BEDROCK_WFS,
        "Rajapinnat_GTK_Kalliopera_WFS:kallioperakairaukset",
        color="#4a7192", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_bedrock_drillings",
    ),
    _layer(
        "GCA", "GTK – Soome riiklik puursüdamikuarhiiv",
        "GTK – National drill-core archive of Finland", "WFS", GTK_BEDROCK_WFS,
        "Rajapinnat_GTK_Kalliopera_WFS:valtakunnallinen_kairasydanarkisto",
        color="#586b8e", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_core_archive",
    ),
    _layer(
        "GMI", "GTK – Soome mineraaliesinemised",
        "GTK – Finnish mineral occurrences", "WFS", GTK_BEDROCK_WFS,
        "Rajapinnat_GTK_Kalliopera_WFS:kaikki_mineraaliesiintymat",
        color="#a46f32", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_mineral_occurrences",
    ),
    _layer(
        "GPT", "GTK – Soome ehitusgeoloogilised uuringupunktid",
        "GTK – Finnish ground-investigation points", "WFS",
        GTK_GROUND_INVESTIGATIONS_WFS,
        "Rajapinnat_GTK_Pohjatutkimukset_WFS:Pohjatutkimukset",
        color="#6e795a", home_group="geology", menu_group="GTK",
        service_crs="EPSG:3067", role="gtk_ground_investigations",
    ),
    _layer(
        "LAB", "LVĢMC – Läti aluspõhja geoloogiline kaart 1:200 000",
        "LVĢMC – Latvian bedrock geological map 1:200,000", "WMS",
        LATVIA_BEDROCK_WMS, "4,3,2,1,0",
        color="#9b6f53", home_group="geology", menu_group="Läti",
        service_crs="EPSG:3059", role="latvia_bedrock",
    ),
    _layer(
        "LQ", "LVĢMC – Läti Kvaternaari kaart 1:200 000",
        "LVĢMC – Latvian Quaternary map 1:200,000", "WMS",
        LATVIA_QUATERNARY_WMS, "0,1,2,3,4,5,6,7,8",
        color="#d6bd65", home_group="geology", menu_group="Läti",
        service_crs="EPSG:3059", role="latvia_quaternary",
    ),
    _layer(
        "LPU", "LVĢMC – Läti geoloogilised puuraugud",
        "LVĢMC – Latvian geological boreholes", "ARCGIS_MAPSERVER",
        LATVIA_BOREHOLES_MAPSERVER, "0",
        color="#3c79a8", home_group="geology", menu_group="Läti/Puuraugud",
        service_crs="EPSG:3059", role="latvia_boreholes",
    ),
    _layer(
        "LKR", "GeoLatvija – Läti karstialad",
        "GeoLatvija – Latvian karst areas", "WFS",
        LATVIA_INSPIRE_GEOLOGY_WFS, "ge:GE.GeologicUnit.KarsticTerrain",
        color="#d18b46", home_group="geology", menu_group="Läti",
        service_crs="EPSG:4258", role="latvia_karst",
    ),
    _layer(
        "LRK", "GeoLatvija – Läti geoloogilised rikked",
        "GeoLatvija – Latvian geological faults", "WFS",
        LATVIA_INSPIRE_GEOLOGY_WFS, "ge:GE.GeologicFault",
        color="#b84f4f", home_group="geology", menu_group="Läti",
        service_crs="EPSG:4258", role="latvia_faults",
    ),
    _layer(
        "LSP", "GeoLatvija – Läti seismilised profiilid",
        "GeoLatvija – Latvian seismic profiles", "WFS",
        LATVIA_INSPIRE_GEOLOGY_WFS, "ge:GE.seismicLine",
        color="#7955a3", home_group="geology", menu_group="Läti",
        service_crs="EPSG:4258", role="latvia_seismic_profiles",
    ),
    _layer(
        "LPV", "LVĢMC – Läti põhjaveekogumid",
        "LVĢMC – Latvian groundwater bodies", "WFS",
        LATVIA_GROUNDWATER_WFS,
        "GroundWaterBody_LV:gis.sde.GroundWaterBody_LV_20221007",
        color="#4b91b8", home_group="geology", menu_group="Läti/Põhjavesi",
        service_crs="EPSG:3059", role="latvia_groundwater",
    ),
    _layer(
        "LMA", "LVĢMC – Läti maavarade leiukohad",
        "LVĢMC – Latvian mineral deposits", "WFS",
        LATVIA_MINERALS_WFS, "ZDz:geoserver_atradnes",
        color="#b6853e", home_group="geology", menu_group="Läti/Maavarad",
        service_crs="EPSG:3059", role="latvia_mineral_deposits",
    ),
    _layer(
        "LLI", "LVĢMC – Läti maavara kaevandamisload",
        "LVĢMC – Latvian mineral extraction licences", "WFS",
        LATVIA_MINERALS_WFS, "ZDz:geoserver_licencu_apjomi",
        color="#a45e35", home_group="geology", menu_group="Läti/Maavarad",
        service_crs="EPSG:3059", role="latvia_mining_licences",
    ),
    _layer(
        "LLM", "LVĢMC – Läti maavara kaevandamislimiidid",
        "LVĢMC – Latvian mineral extraction limits", "WFS",
        LATVIA_MINERALS_WFS, "ZDz:geoserver_limitu_apjomi",
        color="#8d5943", home_group="geology", menu_group="Läti/Maavarad",
        service_crs="EPSG:3059", role="latvia_extraction_limits",
    ),
    _layer(
        "EGF", "Geoloogiafondi uuringualad",
        "Geological archive survey areas", "WFS", EGF,
        "egf:wfs_koik_uuringualad", color="#6b5c45",
        role="archive_survey_areas", home_group="studies",
    ),
    _layer(
        "EH", "Ehitusgeoloogilised uuringupunktid",
        "Engineering geology survey points", "WFS", EGF,
        "egf:wfs_ehitusgeoloogilised_punktid", color="#8a7048",
        role="engineering_geology_points", home_group="studies",
    ),
    _layer(
        "MR", "Maardlate piirid", "Mineral deposit boundaries", "WFS",
        MINERALS, "maavarad:maardla_piir", color="#a46a31",
        role="mineral_deposits", home_group="studies",
    ),
    _layer(
        "ME", "Aktiivsed mäeeraldised", "Active mining claims", "WFS",
        MINERALS, "maavarad:aktiivne_maeeraldis", color="#a53f32",
        role="mining_claims", home_group="studies",
    ),
    _layer(
        "UA", "Aktiivsed uuringualad", "Active exploration areas", "WFS",
        MINERALS, "maavarad:aktiivne_uuringuala", color="#bc873b",
        role="exploration_areas", home_group="studies",
    ),
    _layer("SE", "Seismilised sündmused", "Seismic events", "WFS", "https://maps.egt.ee/geoserver/seismo/ows", "seismo:seismiline_syndmus", color="#a32727", home_group="studies"),
    _layer("KÜ", "Kehtivad katastriüksused", "Valid cadastral parcels", "WFS", "https://aks.geoportaal.ee/aks-ogc", "aks:ads_ky", color="#536f46", home_group="helpers"),
    _layer("HP", "Haldusüksused", "Administrative units", "WFS", "https://aks.geoportaal.ee/aks-ogc", "aks:knr_haldusyksused", color="#677a8d", home_group="helpers"),
    _layer(
        "KV", "Kaardilehed 1:50 000",
        "Map sheets 1:50,000", "WMS", MAP_GRIDS,
        "epk_50T", color="#5c7185", home_group="helpers",
    ),
    _layer("VR", "Värviline reljeefvarjutus", "Coloured hillshade", "WMS", "https://kaart.maaamet.ee/wms/fotokaart", "vreljeef", base_map=True, color="#6c8753", home_group="basemaps"),
    _layer("KM", "Maakatte kõrgusmudel", "Canopy height model", "WMS", "https://kaart.maaamet.ee/wms/fotokaart", "nDSM", base_map=True, color="#567b63", home_group="basemaps"),
    _layer("AJ", "Ajaloolised kaardid", "Historical maps", "WMS", "https://kaart.maaamet.ee/wms/ajalooline", "MA-AJAL", base_map=True, color="#8b6f50", home_group="basemaps"),
    _layer("KT", "Kitsenduste vööndid", "Restriction zones", "WMS", KMA, KMA_LAYERS, color="#8f4d65", home_group="helpers"),
    _layer(
        "TV", "Tehnorajatiste kitsenduste vööndid",
        "Utility infrastructure restriction zones", "WMS",
        KMA, KMA_TECHNICAL_LAYERS, color="#b06d2d", home_group="helpers",
    ),
)


def is_legacy_latvia_wfs(url, layer_name, protocol="WFS"):
    """Match only the three former built-in proxy connections, not custom URLs."""
    return (
        str(protocol).upper() == "WFS"
        and str(url).rstrip("/") == LEGACY_LATVIA_INSPIRE_GEOLOGY_WFS
        and layer_name in {
            "ge:GE.GeologicUnit.KarsticTerrain", "ge:GE.GeologicFault",
            "ge:GE.seismicLine",
        }
    )


class PluginSettings:
    ORGANIZATION = "Qeoloog"
    LEGACY_ORGANIZATION = "EestiWMSNupud"
    KEY_LAYERS = "layers_json"
    KEY_TOGGLE_MODE = "toggle_mode"
    KEY_LANGUAGE = "language"
    KEY_GROUPS = "groups_json"
    KEY_SARV_MATCHES = "sarv_matches_json"
    KEY_CORE_CORRECTIONS = "core_box_corrections_json"
    KEY_EGT_DATA_SOURCE = "egt_data_source"
    KEY_VEKA_STYLE = "veka_style_json"
    KEY_LABEL_TEXT_SIZE = "label_text_size"
    KEY_EGT_LABEL_FIELDS = "egt_label_fields_json"
    KEY_EGT_PORTAL_AUTHCFG = "egt_portal_authcfg"
    KEY_EGT_TEST_SERVER_ENABLED = "egt_test_server_enabled"
    KEY_ELEVATION_RASTERS = "elevation_rasters_json"

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
                if is_legacy_latvia_wfs(
                    merged.get("url"), merged.get("layer_name"),
                    merged.get("protocol"),
                ):
                    merged["url"] = LATVIA_INSPIRE_GEOLOGY_WFS
                # Migrate only the old built-in adaptive grid. Keep custom
                # services and the user's toolbar/disabled placement intact.
                if (
                    default and default.code == "KV"
                    and merged.get("url", "").rstrip("/") == MAP_GRIDS
                    and merged.get("protocol", "").upper() == "WMS"
                    and merged.get("layer_name") == "ristkoordinaadid"
                ):
                    for key in ("name", "name_en", "layer_name", "style"):
                        merged[key] = getattr(default, key)
                # Roles were added to some built-in layers after they had
                # already been saved in user settings. An old empty role must
                # not disable the new object-detail and renderer behaviour.
                if (
                    default and default.role and not value.get("role")
                    and str(value.get("layer_name", default.layer_name)).casefold()
                    == default.layer_name.casefold()
                ):
                    merged["role"] = default.role
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
            if item.code in {"SK", "MP", "VK"}:
                after = next((
                    index for index, current in reversed(list(enumerate(layers)))
                    if current.code in {"PA", "VP", "SK", "MP"}
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
    def load_egt_data_source(cls):
        value = QgsSettings().value(
            f"{cls.ORGANIZATION}/{cls.KEY_EGT_DATA_SOURCE}", "wfs", type=str,
        )
        return value if value in {"wfs", "api"} else "wfs"

    @classmethod
    def save_egt_data_source(cls, source):
        if source in {"wfs", "api"}:
            QgsSettings().setValue(
                f"{cls.ORGANIZATION}/{cls.KEY_EGT_DATA_SOURCE}", source,
            )

    @classmethod
    def load_egt_portal_authcfg(cls):
        """Return only the harmless QGIS authentication configuration id."""
        return QgsSettings().value(
            f"{cls.ORGANIZATION}/{cls.KEY_EGT_PORTAL_AUTHCFG}", "", type=str,
        ).strip()

    @classmethod
    def save_egt_portal_authcfg(cls, authcfg):
        # Credentials and OAuth tokens remain in qgis-auth.db. Qeoloog stores
        # only the opaque seven-character reference selected by the user.
        QgsSettings().setValue(
            f"{cls.ORGANIZATION}/{cls.KEY_EGT_PORTAL_AUTHCFG}",
            str(authcfg or "").strip(),
        )

    @classmethod
    def load_egt_test_server_enabled(cls):
        return QgsSettings().value(
            f"{cls.ORGANIZATION}/{cls.KEY_EGT_TEST_SERVER_ENABLED}",
            False,
            type=bool,
        )

    @classmethod
    def save_egt_test_server_enabled(cls, enabled):
        QgsSettings().setValue(
            f"{cls.ORGANIZATION}/{cls.KEY_EGT_TEST_SERVER_ENABLED}",
            bool(enabled),
        )

    @classmethod
    def load_elevation_raster_settings(cls):
        raw = QgsSettings().value(
            f"{cls.ORGANIZATION}/{cls.KEY_ELEVATION_RASTERS}", "", type=str,
        )
        try:
            values = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            values = {}
        return values if isinstance(values, dict) else {}

    @classmethod
    def save_elevation_raster_settings(cls, values):
        QgsSettings().setValue(
            f"{cls.ORGANIZATION}/{cls.KEY_ELEVATION_RASTERS}",
            json.dumps(values or {}, ensure_ascii=False),
        )

    @classmethod
    def load_label_text_size(cls):
        value = QgsSettings().value(
            f"{cls.ORGANIZATION}/{cls.KEY_LABEL_TEXT_SIZE}", 5.0,
        )
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 5.0
        if value != value or value in {float("inf"), float("-inf")}:
            value = 5.0
        return max(1.0, min(72.0, value))

    @classmethod
    def save_label_text_size(cls, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 5.0
        if value != value or value in {float("inf"), float("-inf")}:
            value = 5.0
        QgsSettings().setValue(
            f"{cls.ORGANIZATION}/{cls.KEY_LABEL_TEXT_SIZE}",
            max(1.0, min(72.0, value)),
        )

    @classmethod
    def load_map_label_fields(cls):
        raw = QgsSettings().value(
            f"{cls.ORGANIZATION}/{cls.KEY_EGT_LABEL_FIELDS}", "", type=str,
        )
        try:
            values = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            values = {}
        return normalize_map_label_fields(values)

    @classmethod
    def save_map_label_fields(cls, values):
        QgsSettings().setValue(
            f"{cls.ORGANIZATION}/{cls.KEY_EGT_LABEL_FIELDS}",
            json.dumps(normalize_map_label_fields(values), ensure_ascii=False),
        )

    @classmethod
    def load_egt_label_fields(cls):
        """Backwards-compatible EGT-only view of the label settings."""
        configured = cls.load_map_label_fields()
        return {role: configured[role] for role in DEFAULT_EGT_LABEL_FIELDS}

    @classmethod
    def save_egt_label_fields(cls, values):
        """Keep the SARV/VEKA selections when an EGT-only caller saves."""
        configured = cls.load_map_label_fields()
        values = values if isinstance(values, dict) else {}
        updated = normalize_map_label_fields({
            role: values.get(role, ()) for role in DEFAULT_EGT_LABEL_FIELDS
        })
        configured.update({role: updated[role] for role in DEFAULT_EGT_LABEL_FIELDS})
        cls.save_map_label_fields(configured)

    @classmethod
    def load_veka_style(cls):
        raw = QgsSettings().value(
            f"{cls.ORGANIZATION}/{cls.KEY_VEKA_STYLE}", "", type=str,
        )
        try:
            value = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            value = {}
        return value if isinstance(value, dict) else {}

    @classmethod
    def save_veka_style(cls, value):
        QgsSettings().setValue(
            f"{cls.ORGANIZATION}/{cls.KEY_VEKA_STYLE}",
            json.dumps(value or {}, ensure_ascii=False),
        )

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

    @classmethod
    def load_core_corrections(cls):
        raw = QgsSettings().value(
            f"{cls.ORGANIZATION}/{cls.KEY_CORE_CORRECTIONS}", "", type=str,
        )
        try:
            values = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            values = {}
        return values if isinstance(values, dict) else {}

    @classmethod
    def save_core_corrections(cls, corrections):
        QgsSettings().setValue(
            f"{cls.ORGANIZATION}/{cls.KEY_CORE_CORRECTIONS}",
            json.dumps(corrections or {}, ensure_ascii=False),
        )
