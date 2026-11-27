"""Public-source adapters and portable display snapshots for local objects."""

from copy import deepcopy
from datetime import datetime, timezone
from math import isfinite
from uuid import UUID

from .section_workspace_ui import section_source_ref


POINT_FIELDS = (
    'geom_x', 'geom_y', 'geom_z', 'korrastatud_nr', 'ma_orig_id', 'sarv_id',
    'hydro_id', 'nimi', 'alias', 'objekti_tyyp', 'yksus_kood', 'pikkus',
    'vertikaalne_ulatus', 'maaratud_veealune_sygavus', 'sygavuse_viis',
    'kande_alus', 'kande_alus_nr', 'puursydamik', 'asukoha_tapsusklass',
    'puurimisfirma', 'valmimise_kuupaev', 'tellija', 'juurdepaasupiirang',
    'puurauk_staatus', 'geomorfoloogia', 'paiknemine', 'kaardistus_q',
    'kaardistus_ap', 'markus', 'egt_ylevaatus', 'lisainfo',
    'juurdepaasu_alus1', 'kehtiv_kuni1', 'juurdepaasu_alus2', 'kehtiv_kuni2',
    'juurdepaasu_alus3', 'kehtiv_kuni3', 'lisaja', 'lisamise_aeg',
)


def safe_value(value):
    """Remove GIS null sentinels and preserve native scalar/date values safely."""
    if isinstance(value, dict):
        return {str(k): safe_value(v) for k, v in value.items() if not str(k).startswith('_qeoloog_')}
    if isinstance(value, (tuple, list)):
        return [safe_value(v) for v in value]
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if isfinite(value) else None
    for getter in ('toPyDateTime', 'toPyDate', 'toPyTime'):
        if hasattr(value, getter):
            try:
                return getattr(value, getter)().isoformat()
            except (AttributeError, ValueError, TypeError, OverflowError):
                return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    text = str(value)
    return None if text.strip().casefold() in {'', 'null', '<null>', 'none'} else text


def public_object_ref(role, attributes):
    if (attributes or {}).get('_qeoloog_section_private_source'):
        return None
    ref = section_source_ref({'role': role}, attributes)
    provider = ref.get('provider')
    if provider == 'EGT':
        identifier = ref.get('gea_id') or ref.get('globalid')
        if identifier and not identifier.isdigit():
            try:
                identifier = str(UUID(identifier.strip('{}')))
            except ValueError:
                return None
    elif provider == 'SARV':
        identifier = ref.get('sarv_id')
    elif provider == 'VEKA':
        identifier = ref.get('eelis_id') or ref.get('kkr_kood', '').upper()
    else:
        return None
    if not identifier or identifier == '0':
        return None
    return {'source': provider, 'entity': role, 'id': identifier}


def local_object_from_source(name, role, attributes, units, *, profile_status='', profile_source=''):
    ref = public_object_ref(role, attributes)
    if ref is None:
        return None

    def first(mapping, *keys):
        return next((v for key in keys if (v := safe_value(mapping.get(key))) is not None), None)

    source = ref['source']
    raw = safe_value(attributes)
    attrs = {
        field: value for field in POINT_FIELDS
        if (value := first(attributes, field, 'klassif_' + field)) is not None
    }
    mapped = {
        'nimi': first(attributes, 'nimi', 'name', 'number', 'kkr_kood') or name,
        'geom_x': first(attributes, '_qeoloog_x_3301', 'geom_x', 'kesk_x'),
        'geom_y': first(attributes, '_qeoloog_y_3301', 'geom_y', 'kesk_y'),
        'geom_z': first(attributes, 'z_abs', 'geom_z', 'elevation', 'altitude',
                        'height', 'maapinna_abs_korgus', 'absoluutkorgus'),
        'pikkus': first(attributes, 'pikkus', 'sygavus', 'depth'),
    }
    if source == 'VEKA':
        mapped['hydro_id'] = first(attributes, 'eelis_id')
    if source == 'EGT' and not attrs.get('objekti_tyyp'):
        mapped['objekti_tyyp'] = 1 if role == 'boreholes' else 2
    elif source == 'VEKA' or role == 'sarv_drillcores':
        mapped['objekti_tyyp'] = 1
    for key, value in mapped.items():
        if value is not None:
            attrs[key] = value
    clean_units = []
    for row in units or ():
        if not isinstance(row, dict):
            continue
        unit = safe_value(row)
        for target, aliases in {
            'indeks': ('indeks', 'stratigraafia_indeks', 'klassif_indeks', 'index'),
            'litoloogia': ('litoloogia', 'klassif_litoloogia', 'lithology'),
            'z_suht_ylemine': ('z_suht_ylemine', 'top', 'depth_top'),
            'z_suht_alumine': ('z_suht_alumine', 'bottom', 'depth_bottom'),
        }.items():
            value = first(row, *aliases)
            if value is not None:
                unit[target] = value
        clean_units.append(unit)
    # The independent baseline never changes when the working values are edited.
    working_units = deepcopy(clean_units)
    for unit in working_units:
        # A local copy is not an update to the upstream FeatureServer object.
        unit.pop('puurauk_vaatluspunkt_id', None)
    return {
        'attributes': attrs, 'units': working_units, 'related': {},
        'source_ref': ref, 'captured_at': datetime.now(timezone.utc).isoformat(),
        'source_original': {'name': str(name), 'attributes': deepcopy(attrs),
                            'raw_attributes': raw, 'units': deepcopy(clean_units)},
        'provenance': {'profile_status': profile_status, 'profile_source': profile_source or source},
    }


def local_cross_section(record):
    attrs = record.get('attributes') or {}
    identifier = record.get('id')
    return {
        'id': identifier, 'key': f'local:{identifier}', 'role': 'local_section',
        'source': 'Kohalik', 'name': attrs.get('nimi') or attrs.get('ID_ajutine') or identifier,
        'x': attrs.get('geom_x'), 'y': attrs.get('geom_y'), 'elevation': attrs.get('geom_z'),
        'depth': attrs.get('vertikaalne_ulatus') if attrs.get('pikkus') is None else attrs.get('pikkus'),
        'units': deepcopy(record.get('units') or []), 'enabled': True,
    }
