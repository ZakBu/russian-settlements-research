#!/usr/bin/env python3
"""Export verified, versioned research inputs into an entirely static web data bundle.

No scientific calculation is rerun. Missing values and credit/comparability flags
are preserved; polygon summaries describe a fixed comparable point cohort, not
official administrative totals. Downloads and outputs are intentionally ignored.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import struct
import zipfile
import zlib
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
YEARS = (2002, 2010, 2021)
# Display-only Russian labels for the 83 explicit ISO 3166-2 codes in the
# pinned ADM1 source. This dictionary never joins polygon IDs to census/OKTMO.
REGION_NAMES_RU = {
    'RU-AD': 'Республика Адыгея', 'RU-AL': 'Республика Алтай',
    'RU-ALT': 'Алтайский край', 'RU-AMU': 'Амурская область',
    'RU-ARK': 'Архангельская область', 'RU-AST': 'Астраханская область',
    'RU-BA': 'Республика Башкортостан', 'RU-BEL': 'Белгородская область',
    'RU-BRY': 'Брянская область', 'RU-BU': 'Республика Бурятия',
    'RU-CE': 'Чеченская Республика', 'RU-CHE': 'Челябинская область',
    'RU-CHU': 'Чукотский автономный округ', 'RU-CU': 'Чувашская Республика',
    'RU-DA': 'Республика Дагестан', 'RU-IN': 'Республика Ингушетия',
    'RU-IRK': 'Иркутская область', 'RU-IVA': 'Ивановская область',
    'RU-KAM': 'Камчатский край', 'RU-KB': 'Кабардино-Балкарская Республика',
    'RU-KC': 'Карачаево-Черкесская Республика', 'RU-KDA': 'Краснодарский край',
    'RU-KEM': 'Кемеровская область', 'RU-KGD': 'Калининградская область',
    'RU-KGN': 'Курганская область', 'RU-KHA': 'Хабаровский край',
    'RU-KHM': 'Ханты-Мансийский автономный округ — Югра',
    'RU-KIR': 'Кировская область', 'RU-KK': 'Республика Хакасия',
    'RU-KL': 'Республика Калмыкия', 'RU-KLU': 'Калужская область',
    'RU-KO': 'Республика Коми', 'RU-KOS': 'Костромская область',
    'RU-KR': 'Республика Карелия', 'RU-KRS': 'Курская область',
    'RU-KYA': 'Красноярский край', 'RU-LEN': 'Ленинградская область',
    'RU-LIP': 'Липецкая область', 'RU-MAG': 'Магаданская область',
    'RU-ME': 'Республика Марий Эл', 'RU-MO': 'Республика Мордовия',
    'RU-MOS': 'Московская область', 'RU-MOW': 'Москва',
    'RU-MUR': 'Мурманская область', 'RU-NEN': 'Ненецкий автономный округ',
    'RU-NGR': 'Новгородская область', 'RU-NIZ': 'Нижегородская область',
    'RU-NVS': 'Новосибирская область', 'RU-OMS': 'Омская область',
    'RU-ORE': 'Оренбургская область', 'RU-ORL': 'Орловская область',
    'RU-PER': 'Пермский край', 'RU-PNZ': 'Пензенская область',
    'RU-PRI': 'Приморский край', 'RU-PSK': 'Псковская область',
    'RU-ROS': 'Ростовская область', 'RU-RYA': 'Рязанская область',
    'RU-SA': 'Республика Саха (Якутия)', 'RU-SAK': 'Сахалинская область',
    'RU-SAM': 'Самарская область', 'RU-SAR': 'Саратовская область',
    'RU-SE': 'Республика Северная Осетия — Алания',
    'RU-SMO': 'Смоленская область', 'RU-SPE': 'Санкт-Петербург',
    'RU-STA': 'Ставропольский край', 'RU-SVE': 'Свердловская область',
    'RU-TA': 'Республика Татарстан', 'RU-TAM': 'Тамбовская область',
    'RU-TOM': 'Томская область', 'RU-TUL': 'Тульская область',
    'RU-TVE': 'Тверская область', 'RU-TY': 'Республика Тыва',
    'RU-TYU': 'Тюменская область', 'RU-UD': 'Удмуртская Республика',
    'RU-ULY': 'Ульяновская область', 'RU-VGG': 'Волгоградская область',
    'RU-VLA': 'Владимирская область', 'RU-VLG': 'Вологодская область',
    'RU-VOR': 'Воронежская область', 'RU-YAN': 'Ямало-Ненецкий автономный округ',
    'RU-YAR': 'Ярославская область', 'RU-YEV': 'Еврейская автономная область',
    'RU-ZAB': 'Забайкальский край',
}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def short_id(source_id):
    return hashlib.sha256(str(source_id).encode()).hexdigest()[:16]


def numeric(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else round(number, 6)


def truth(value):
    return value is True or str(value).lower() == 'true'


def feature_collection(features):
    return {'type': 'FeatureCollection', 'features': features}


def preview_points(features, cell_degrees=.15):
    """Spatially thin real points for decorative thumbnails, not a statistical map."""
    cells = {}
    for feature in features:
        lon, lat = feature['geometry']['coordinates']
        key = (math.floor(lon / cell_degrees), math.floor(lat / cell_degrees))
        current = cells.get(key)
        rank = (feature['properties']['p21'] or 0, feature['properties']['id'])
        if current is None or rank > current[0]:
            cells[key] = (rank, feature)
    output = []
    for _, feature in (cells[key] for key in sorted(cells)):
        lon, lat = feature['geometry']['coordinates']
        change = feature['properties']['change']
        output.append([round(lon, 3), round(lat, 3), round(change, 1) if change is not None else None,
                       feature['properties']['name'], feature['properties']['p21']])
    return output


def compact_population(features):
    """Lossless row transport; dictionary coding changes no census values."""
    regions = sorted({feature['properties']['region'] for feature in features})
    region_index = {name: index for index, name in enumerate(regions)}
    columns = ['id', 'name', 'regionIndex', 'longitude', 'latitude', 'p02', 'p10', 'p21', 'change', 'comparable']
    rows = []
    for feature in features:
        props = feature['properties']
        rows.append([props['id'], props['name'], region_index[props['region']], *feature['geometry']['coordinates'],
                     props['p02'], props['p10'], props['p21'], props['change'], props['comparable']])
    return {'format': 'settlements-columnar-v1', 'columns': columns, 'regions': regions, 'rows': rows}


def overview_population(compact, minimum_population=10000):
    """Small cartographic first view; no census values or identifiers are changed.

    Keep historically large settlements when a later observation is missing.
    Smaller/unknown rows remain in the full transport and load at local zoom or
    search. The complete region dictionary is retained, so indexes stay stable.
    """
    if minimum_population <= 0:
        raise ValueError('Overview population threshold must be positive')
    indexes = [compact['columns'].index(column) for column in ('p02', 'p10', 'p21')]
    rows = [row for row in compact['rows']
            if max((row[index] for index in indexes if row[index] is not None), default=0) >= minimum_population]
    return {**compact, 'rows': rows}


def display_boundaries(features):
    """Round only already-simplified display coordinates, never analytic input."""
    def coordinates(values):
        return [round(value, 5) if isinstance(value, (int, float)) else coordinates(value) for value in values]
    return feature_collection([{**feature, 'geometry': {**feature['geometry'], 'coordinates': coordinates(feature['geometry']['coordinates'])}}
                               for feature in features])


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.part')
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
    temporary.replace(path)


def boundary_cache_path(cache, asset):
    return cache / (asset['id'] + ('.gpkg' if asset.get('fileFormat') == 'gpkg' else '.geojson'))


def read_boundary_source(path, asset):
    """Read pinned GeoJSON or select unchanged source IDs from a WGS84 GeoPackage."""
    if asset.get('fileFormat') != 'gpkg':
        return json.loads(path.read_text())
    from shapely import from_wkb
    from shapely.geometry import mapping
    table = asset['sourceLayer']
    if not re.fullmatch(r'adm[12]', table):
        raise ValueError('Unsupported boundary source layer')
    selected = asset['featureIds']
    if not selected or len(set(selected)) != len(selected):
        raise ValueError('Boundary source IDs must be nonempty and unique')
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        info = conn.execute('SELECT column_name,srs_id FROM gpkg_geometry_columns WHERE table_name=?', (table,)).fetchone()
        if not info or info['srs_id'] != 4326 or not re.fullmatch(r'[a-zA-Z_][a-zA-Z_0-9]*', info['column_name']):
            raise ValueError('Boundary GeoPackage requires WGS84 geometry')
        geom = info['column_name']
        source_count = conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
        if asset.get('sourceTotalCount') is not None and source_count != asset['sourceTotalCount']:
            raise ValueError('Unexpected complete GeoPackage source count')
        rows = conn.execute(f'SELECT * FROM {table} WHERE {table}_id IN ({",".join("?" for _ in selected)}) ORDER BY {table}_id', selected).fetchall()
        if {row[table + '_id'] for row in rows} != set(selected):
            raise ValueError('Selected boundary IDs missing from source')
        features = []
        for row in rows:
            blob = row[geom]
            if blob[:2] != b'GP' or (blob[3] >> 1) & 7 not in (0, 1, 2, 3, 4):
                raise ValueError('Invalid GeoPackage geometry header')
            offset = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(blob[3] >> 1) & 7]
            geometry = from_wkb(blob[offset:])
            if geometry.is_empty or geometry.geom_type not in ('Polygon', 'MultiPolygon'):
                raise ValueError('Expected source boundary polygons')
            features.append({'type': 'Feature', 'properties': {key: row[key] for key in row.keys() if key not in (geom, 'fid')},
                             'geometry': mapping(geometry)})
    return feature_collection(features)


def verified_download(asset, cache):
    """An existing cache is trusted only after rechecking its pinned SHA-256."""
    target = boundary_cache_path(cache, asset)
    if target.exists() and digest(target) == asset['sha256']:
        return target
    cache.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.part')
    request = Request(asset['url'], headers={'User-Agent': 'russian-settlements-atlas/1'})
    with urlopen(request, timeout=120) as response, temporary.open('wb') as output:
        for chunk in iter(lambda: response.read(1024 * 1024), b''):
            output.write(chunk)
    if temporary.stat().st_size != asset['bytes'] or digest(temporary) != asset['sha256']:
        temporary.unlink(missing_ok=True)
        raise ValueError('Pinned geometry checksum/size mismatch: ' + asset['id'])
    temporary.replace(target)
    return target



def pinned_catalog_member(catalog_path, member_path, cache, offline=False, max_bytes=120 * 1024 * 1024):
    """Read one SHA-verified ZIP member with bounded ranges, never the whole large archive."""
    catalog = json.loads(Path(catalog_path).read_text())
    row = next(row for row in catalog['files'] if row['path'] == member_path)
    obj = catalog['objects'][row['blob']]
    expected = obj['sha256']
    if not re.fullmatch(r'[a-f0-9]{64}', expected) or not 0 < obj['bytes'] <= max_bytes:
        raise ValueError('Invalid or oversized settlement polygon source')
    target = Path(cache) / 'settlement-polygons' / (expected + '.parquet')
    if target.is_file() and target.stat().st_size == obj['bytes'] and digest(target) == expected:
        return target
    if offline:
        raise ValueError('Offline settlement polygon source missing or hash differs')
    asset = next(asset for asset in catalog['assets'] if asset['asset'] == obj['asset'])
    size = asset['bytes']
    member = obj.get('archive_member', 'objects/' + row['blob'])
    url = f"https://github.com/{catalog['repository']}/releases/download/{catalog['release_tag']}/{obj['asset']}"

    def read_range(first, last):
        if not (0 <= first <= last < size) or last - first + 1 > max_bytes + 1024 * 1024:
            raise ValueError('Settlement polygon ZIP range outside bounded source')
        with urlopen(Request(url, headers={'Range': f'bytes={first}-{last}',
                     'User-Agent': 'russian-settlements-atlas/1'}), timeout=120) as response:
            if (response.status != 206 or response.headers.get('Content-Range') != f'bytes {first}-{last}/{size}'
                    or urlparse(response.url).scheme != 'https'):
                raise ValueError('Settlement polygon source did not honor exact HTTPS byte range')
            data = response.read(last - first + 2)
        if len(data) != last - first + 1:
            raise ValueError('Settlement polygon ZIP range length differs')
        return data

    trailer = read_range(max(0, size - 65558), size - 1)
    end_position = trailer.rfind(b'PK\x05\x06')
    if end_position < 0 or end_position + 22 > len(trailer):
        raise ValueError('Settlement polygon ZIP end record missing')
    end = struct.unpack_from('<4s4H2LH', trailer, end_position)
    if end[1] or end[2] or end[3] != end[4] or end[5] > 1024 * 1024 or end[6] >= size:
        raise ValueError('Unsupported or oversized settlement polygon ZIP directory')
    directory_offset = end[6]
    # ZipFile adjusts original offsets when reading this directory-only suffix.
    with zipfile.ZipFile(io.BytesIO(read_range(directory_offset, size - 1))) as archive:
        info = archive.getinfo(member)
    if info.file_size != obj['bytes'] or info.compress_size > max_bytes or info.flag_bits & 1:
        raise ValueError('Settlement polygon ZIP member size or encryption differs')
    header_offset = info.header_offset + directory_offset
    header = struct.unpack('<4s5H3L2H', read_range(header_offset, header_offset + 29))
    if header[0] != b'PK\x03\x04' or header[3] != info.compress_type:
        raise ValueError('Settlement polygon ZIP local header differs')
    start = header_offset + 30 + header[-2] + header[-1]
    payload = read_range(start, start + info.compress_size - 1)
    if info.compress_type == zipfile.ZIP_DEFLATED:
        decoder = zlib.decompressobj(-15)
        raw = decoder.decompress(payload, obj['bytes'] + 1)
        if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
            raise ValueError('Settlement polygon ZIP deflate stream differs or exceeds its bound')
    elif info.compress_type == zipfile.ZIP_STORED:
        raw = payload
    else:
        raise ValueError('Unsupported settlement polygon ZIP compression')
    if len(raw) != obj['bytes'] or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Settlement polygon member SHA-256 differs')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.part')
    temporary.write_bytes(raw)
    temporary.replace(target)
    return target


def settlement_polygon_features(inventory, lookup, tolerance=.00005):
    """Display accepted urban census identities only; never infer geometry from a point or ADM2."""
    import shapely
    from shapely.geometry import mapping, shape
    candidates = {}
    for row in inventory.to_dict('records'):
        source_id = row.get('source_record_id')
        if (row.get('polygon_identity_status') != 'named_census_point_in_dated_locality_polygon'
                or row.get('settlement_type_2021') not in {'город', 'пгт'}
                or row.get('geometry_identity_resolution') == 'invalid_census_point_held'
                or source_id not in lookup):
            continue
        geometry = shapely.from_wkb(row['geometry_wkb'])
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in {'Polygon', 'MultiPolygon'}:
            raise ValueError('Accepted settlement polygon geometry is invalid')
        candidates.setdefault(source_id, []).append((row, geometry))
    features = []
    for source_id, records in sorted(candidates.items()):
        # Multiple accepted source pieces retain their exact common identity; no arbitrary winner.
        geometry = shapely.union_all([geometry for _, geometry in records])
        if not geometry.is_valid or geometry.is_empty or geometry.geom_type not in {'Polygon', 'MultiPolygon'}:
            raise ValueError('Accepted settlement polygon union is invalid')
        geometry = geometry.simplify(tolerance, preserve_topology=True)
        source_rows = [row for row, _ in records]
        point = lookup[source_id]
        uid = point['properties']['id']
        feature = {'type': 'Feature', 'id': uid, 'geometry': mapping(geometry), 'properties': {
            'id': uid, 'name': point['properties']['name'], 'source': 'OpenStreetMap / Geofabrik',
            'sourceDate': min(str(row['source_snapshot'])[:10] for row in source_rows),
            'sourceFeatureIds': sorted({str(row['source_feature_id']) for row in source_rows}),
            'sourceDatasets': sorted({str(row['source_dataset']) for row in source_rows}),
            'geometryKind': 'cartographic_settlement_contour_not_legal_boundary',
            'geometryBasis': 'union_of_accepted_named_census_identity_geometries',
            'nestedMaskApplied': any(truth(row.get('nested_mask_applied')) for row in source_rows),
            'displaySimplifyDegrees': tolerance,
        }}
        rounded = display_boundaries([feature])['features'][0]
        # Coordinate rounding is display-only, but must not collapse a ring or hole.
        features.append(rounded if shape(rounded['geometry']).is_valid else feature)
    return features


def export_settlement_polygons(config, output, cache, lookup, offline=False):
    import pandas as pd
    source = pinned_catalog_member(ROOT / config['catalog'], config['member'], cache, offline=offline)
    columns = ['source_record_id', 'polygon_identity_status', 'settlement_type_2021', 'geometry_identity_resolution',
               'geometry_wkb', 'source_snapshot', 'source_feature_id', 'source_dataset', 'nested_mask_applied']
    features = settlement_polygon_features(pd.read_parquet(source, columns=columns), lookup, config.get('simplifyDegrees', .00005))
    shards = {f'{index:02x}': {} for index in range(256)}
    for feature in features:
        uid = feature['properties']['id']
        feature['properties']['sourceUrl'] = config['sourceUrl']
        shards[uid[:2]][uid] = feature
    for shard, records in shards.items():
        write_json(output / 'settlement-polygons' / (shard + '.json'), records)
    return {'count': len(features), 'path': 'settlement-polygons/{shard}.json',
            'scope': 'accepted_city_and_urban_type_settlement_census_identities_only',
            'sourceCatalog': config['catalog'], 'sourceMember': config['member'],
            'sourceSha256': digest(source), 'sourceUrl': config['sourceUrl'],
            'geometryKind': 'cartographic_settlement_contour_not_legal_boundary',
            'displaySimplifyDegrees': config.get('simplifyDegrees', .00005)}

def population_features(wide, long):
    """Use the accepted 2021 point of ordinary additive records; no inferred points."""
    ordinary = long.is_additive_settlement_record.fillna(False)
    if 'population_scope' in long:
        ordinary &= ~long.population_scope.eq('federal_city_region').fillna(False)
    accepted = long[(long.census_year == 2021) & ordinary]
    ids = set(accepted.source_record_id)
    features, details, lookup = [], {}, {}
    for row in wide.sort_values('root').to_dict('records'):
        source = row['source_record_id_2021']
        if source not in ids or not truth(row['accepted_point_present_2021']):
            continue
        lon, lat = numeric(row['accepted_longitude_2021']), numeric(row['accepted_latitude_2021'])
        if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            continue
        uid = short_id(source)
        if uid in details:
            raise ValueError('Duplicate or colliding source identity: ' + uid)
        credit = {str(y): truth(row[f'working_credit_present_{y}']) for y in YEARS}
        values = {str(y): numeric(row[f'effective_population_{y}']) if credit[str(y)] else None for y in YEARS}
        comparable = truth(row['ordinary_full3']) and all(v is not None for v in values.values())
        change = round((values['2021'] / values['2002'] - 1) * 100, 2) if comparable and values['2002'] > 0 else None
        name = str(row['settlement_name_2021'] or '')
        region = str(row['region_norm_2021'] or '')
        props = {'id': uid, 'shard': uid[:2], 'name': name, 'region': region,
                 'p02': values['2002'], 'p10': values['2010'], 'p21': values['2021'],
                 'change': change, 'comparable': comparable}
        features.append({'type': 'Feature', 'id': uid, 'properties': props,
                         'geometry': {'type': 'Point', 'coordinates': [round(lon, 6), round(lat, 6)]}})
        details[uid] = {'id': uid, 'sourceId': source, 'root': row['root'], 'name': name,
                        'region': region, 'district': row['district_raw_2021'] if isinstance(row['district_raw_2021'], str) else None,
                        'settlementType': row['settlement_type_2021'] if isinstance(row['settlement_type_2021'], str) else None,
                        'population': values, 'rawPopulation': {str(y): numeric(row[f'population_{y}']) for y in YEARS},
                        'credit': credit, 'quality': {str(y): row[f'population_value_quality_{y}'] if isinstance(row[f'population_value_quality_{y}'], str) else None for y in YEARS},
                        'comparable': comparable, 'source': 'census-population',
                        'limitations': ['Совпадение численного ряда не устанавливает неизменность исторических границ.',
                                        'Часть значений 2010 года имеет вторичное защищённое происхождение.']}
        lookup[source] = features[-1]
    return features, details, lookup


def country_preview(features):
    """Small, clockwise geographic rings for overview artwork, never analysis."""
    from shapely.geometry import shape, mapping
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union
    land = unary_union([shape(f['geometry']) for f in features]).simplify(.07, preserve_topology=True)
    polygons = list(land.geoms) if land.geom_type == 'MultiPolygon' else [land]
    return feature_collection([{'type': 'Feature', 'properties': {}, 'geometry': mapping(orient(p, sign=-1))}
                               for p in polygons if p.geom_type == 'Polygon' and p.area >= .002])


def normalize_boundary_source(raw, asset):
    """Adapt ready-made Terrae columns to the existing boundary exporter."""
    if asset.get('provider') != 'Terrae':
        return raw
    level = asset['level'].lower()
    special_names = {'x-r109876-1': 'Территория Дагестана без подтверждённого районного деления',
                     'x-r151225-lake-khanka': 'Озеро Ханка'}
    result = []
    for feature in raw['features']:
        p = feature['properties']
        identity = p[level + '_id']
        name = asset.get('nameOverrides', {}).get(identity, special_names.get(identity, p['name']))
        if not isinstance(name, str) or not re.search('[А-Яа-яЁё]', name):
            raise ValueError('Missing Russian boundary name: ' + identity)
        props = {**p, 'shapeID': identity, 'shapeName': name, 'nameRu': name,
                 'sourceLocalName': p['name'], 'sourceName': p.get('name_en') or p['name'],
                 'shapeISO': p.get('iso_3166_2') or ''}
        result.append({**feature, 'properties': props})
    return feature_collection(result)


def merge_boundary_sources(raw_assets):
    """Combine explicitly selected reference contours, preserving source identity.

    A supplement changes the displayed study coverage, never the upstream RUS
    count or its country/ISO classification. Point membership is calculated once
    over the combined geometry so overlaps cannot duplicate census observations.
    """
    groups = {}
    for asset, raw in raw_assets:
        normalized = normalize_boundary_source(raw, asset)
        if len(normalized['features']) != asset['count']:
            raise ValueError('Unexpected source boundary count: ' + asset['id'])
        divisions = sum(feature['properties'].get('kind', 'division') == 'division'
                        for feature in normalized['features'])
        if asset.get('divisionCount') is not None and divisions != asset['divisionCount']:
            raise ValueError('Unexpected administrative division count: ' + asset['id'])
        target = asset.get('appendTo', asset['id'])
        group = groups.setdefault(target, {'asset': asset, 'features': [], 'ids': set(), 'sources': {}})
        if group['asset']['level'] != asset['level']:
            raise ValueError('Supplement level differs from its target: ' + asset['id'])
        group['sources'][asset['id']] = asset['count']
        for feature in normalized['features']:
            props = feature['properties']
            identity = props['shapeID']
            if identity in group['ids']:
                raise ValueError('Repeated source boundary ID: ' + identity)
            group['ids'].add(identity)
            group['features'].append({**feature, 'properties': {**props,
                'referenceSourceId': asset['id'],
                'sourceCountry': asset.get('sourceCountry') or props.get('unit_key'),
                'referenceSupplement': bool(asset.get('appendTo'))}})
    return [(target, {**group['asset'], 'count': len(group['features'])},
             feature_collection(group['features']), group['sources'])
            for target, group in groups.items()]


def boundary_features(raw, asset, settlements, details=None, parent_names=None):
    """Exact point-in-polygon on source geometry; unique membership only.

    Render geometry is simplified afterwards. Overlapping/boundary ambiguities
    are excluded from sums rather than assigned arbitrarily.
    """
    from shapely import STRtree, points, make_valid
    from shapely.geometry import mapping, shape
    shapes = [shape(f['geometry']) for f in raw['features']]
    if len(shapes) != asset['count']:
        raise ValueError('Unexpected source boundary count: ' + asset['id'])
    repaired = sum(not s.is_valid for s in shapes)
    shapes = [make_valid(s) if not s.is_valid else s for s in shapes]
    coordinates = [f['geometry']['coordinates'] for f in settlements]
    pairs = STRtree(shapes).query(points(coordinates), predicate='covered_by')
    assignments = {}
    for point_index, polygon_index in zip(*pairs):
        assignments.setdefault(int(point_index), []).append(int(polygon_index))
    from collections import Counter
    aliases = [Counter() for _ in shapes]
    accumulators = [{'count': 0, 'comparableCount': 0, 'p02': 0, 'p10': 0, 'p21': 0,
                     'p21KnownCount': 0, 'sizeBins': [0, 0, 0, 0, 0]} for _ in shapes]
    for index, polygons in assignments.items():
        if len(polygons) != 1:
            continue
        props = settlements[index]['properties']
        stats = accumulators[polygons[0]]
        detail = (details or {}).get(props.get('id'), {})
        district_literal = detail.get('district')
        if asset['level'] == 'ADM2' and isinstance(district_literal, str) and district_literal.strip():
            aliases[polygons[0]][district_literal.strip()] += 1
        stats['count'] += 1
        if props['p21'] is not None:
            stats['p21KnownCount'] += 1
            bucket = next((i for i, threshold in enumerate((100, 1000, 10000, 100000)) if props['p21'] < threshold), 4)
            stats['sizeBins'][bucket] += 1
        if props['comparable']:
            stats['comparableCount'] += 1
            for column in ('p02', 'p10', 'p21'):
                stats[column] += props[column]
    result = []
    for feature, geometry, stats, candidate_names in zip(raw['features'], shapes, accumulators, aliases):
        source = feature['properties']
        if stats['comparableCount'] == 0:
            stats.update(p02=None, p10=None, p21=None)
        display_name = source.get('nameRu') or (REGION_NAMES_RU.get(source.get('shapeISO'), source['shapeName']) if asset['level'] == 'ADM1' else source['shapeName'])
        props = {'id': source['shapeID'], 'name': display_name, 'sourceName': source.get('sourceName', source['shapeName']), 'level': asset['level'],
                 'epoch': asset['epoch'], 'iso': source.get('shapeISO'), 'kind': source.get('kind', 'division'),
                 'provider': asset.get('provider', 'geoBoundaries'), 'sourceDate': asset.get('snapshotDate', str(asset['epoch'])), **stats}
        for field in ('referenceSourceId', 'sourceCountry', 'referenceSupplement', 'sourceLocalName'):
            if field in source:
                props[field] = source[field]
        if parent_names and source.get('adm1_id') in parent_names:
            props['region'] = parent_names[source['adm1_id']]
        if candidate_names:
            props['searchAliases'] = [name for name, _ in sorted(candidate_names.items(), key=lambda item: (-item[1], item[0]))[:8]]
            props['searchAliasBasis'] = 'district_raw_2021_of_uniquely_contained_settlement_points_not_verified_municipality_match'
        result.append({'type': 'Feature', 'id': props['id'], 'properties': props,
                       'geometry': mapping(geometry.simplify(asset.get('renderSimplifyDegrees', .002), preserve_topology=True))})
    return result, {'unassignedPoints': len(settlements) - len(assignments), 'geometriesMadeValid': repaired,
                    'ambiguousPoints': sum(len(v) != 1 for v in assignments.values()),
                    'aggregation': 'fixed_comparable_2021_point_cohort_not_official_municipal_totals'}


def local_services(inputs, population_lookup):
    """Documented service locality, never presented as a verified building point."""
    local = inputs / 'sgrt/local20261024/services'
    with (local / 'nodes.csv').open() as stream:
        nodes = {r['source_record_id']: r for r in csv.DictReader(stream)}
    with (local / 'links.csv').open() as stream:
        source_links = list(csv.DictReader(stream))
    services, links = {}, []
    for row in source_links:
        origin = nodes.get(row['origin_id'])
        destination = nodes.get(row['destination_id'])
        if not origin or not destination:
            continue
        family = 'schools' if row['function'] == 'education' else 'medical'
        source_id = row['destination_id']
        uid = short_id(source_id)
        service_key = uid + '-' + family
        properties = {'id': service_key, 'settlementId': uid, 'name': row['destination_name'],
                      'family': family, 'evidence': row['evidence_kind'], 'source': row['source_url'],
                      'sourceId': row['source_id'], 'year': row['document_date'][:4] or None,
                      'geometryKind': 'settlement_reference_not_verified_institution_building',
                      'observedFlow': False}
        coords = [numeric(destination['lon']), numeric(destination['lat'])]
        services[service_key] = {'type': 'Feature', 'properties': properties,
                                 'geometry': {'type': 'Point', 'coordinates': coords}}
        if row['origin_id'] != source_id:
            props = {**properties, 'id': row['link_id'], 'from': short_id(row['origin_id']), 'to': uid,
                     'fromName': row['origin_name'], 'toName': row['destination_name'],
                     'geometryKind': 'schematic_link_not_route'}
            links.append({'type': 'Feature', 'properties': props, 'geometry': {'type': 'LineString', 'coordinates': [
                [numeric(origin['lon']), numeric(origin['lat'])], coords]}})
    return list(services.values()), links


def run_fetch(catalog, inputs, patterns, profile='core'):
    command = [sys.executable, str(ROOT / 'scripts/research_data.py'), 'fetch', '--catalog', str(ROOT / catalog),
               '--profile', profile, '--dest', str(inputs)]
    for pattern in patterns:
        command += ['--match', pattern]
    subprocess.run(command, cwd=ROOT, check=True)


LAYER_SOURCE_LIMIT = 20 * 1024 * 1024
LAYER_GEOMETRIES = {'point': {'Point', 'MultiPoint'}, 'line': {'LineString', 'MultiLineString'},
                    'polygon': {'Polygon', 'MultiPolygon'}}


def layer_source(dataset, cache, offline=False):
    """Fetch at most 20 MiB and verify every byte against the authored pin."""
    sha = dataset.get('sha256', '')
    url = dataset.get('url', '')
    parsed = urlparse(url)
    if not re.fullmatch(r'[0-9a-fA-F]{64}', sha) or parsed.scheme != 'https' or not parsed.netloc:
        raise ValueError('Layer dataset needs an HTTPS source and exact SHA-256')
    if re.search(r'/(?:main|master|latest)(?:/|$)', parsed.path, re.I):
        raise ValueError('Layer dataset must pin a version, not main/master/latest')
    path = cache / 'layers' / (sha.lower() + '.source')
    if path.is_file() and path.stat().st_size <= LAYER_SOURCE_LIMIT and digest(path) == sha.lower():
        return path.read_bytes()
    if offline:
        raise ValueError('Offline layer source missing or hash differs: ' + dataset['id'])
    path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(Request(url, headers={'User-Agent': 'russian-settlements-atlas/1'}), timeout=120) as response:
        if urlparse(response.url).scheme != 'https':
            raise ValueError('Layer source redirected away from HTTPS')
        data = response.read(LAYER_SOURCE_LIMIT + 1)
    if len(data) > LAYER_SOURCE_LIMIT:
        raise ValueError('Layer source exceeds 20 MiB limit')
    if hashlib.sha256(data).hexdigest() != sha.lower():
        raise ValueError('Layer dataset SHA-256 mismatch: ' + dataset['id'])
    temporary = path.with_suffix('.part')
    temporary.write_bytes(data)
    temporary.replace(path)
    return data


def layer_value(value, label):
    if value is None or (isinstance(value, str) and value.strip().lower() in ('', 'null', 'none')):
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean is not a numeric layer value: ' + label)
    number = numeric(value)
    if number is None:
        raise ValueError('Layer value must be finite numeric or null: ' + label)
    return number


def checked_geometry(geometry, declared):
    from shapely.geometry import shape
    if not isinstance(geometry, dict) or geometry.get('type') not in LAYER_GEOMETRIES.get(declared, set()):
        raise ValueError('Actual layer geometry does not match declared ' + declared)
    def positions(coordinates):
        if not isinstance(coordinates, (list, tuple)) or not coordinates:
            raise ValueError('Empty or malformed layer coordinates')
        if isinstance(coordinates[0], (int, float)):
            if len(coordinates) < 2 or len(coordinates) > 3:
                raise ValueError('Layer positions require longitude, latitude, optional altitude')
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in coordinates):
                raise ValueError('Layer coordinates must be finite numbers')
            if not (-180 <= coordinates[0] <= 180 and -90 <= coordinates[1] <= 90):
                raise ValueError('Layer coordinates outside longitude/latitude range')
        else:
            for item in coordinates:
                positions(item)
    positions(geometry.get('coordinates'))
    if geometry['type'] in ('Polygon', 'MultiPolygon'):
        polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
        for polygon in polygons:
            for ring in polygon:
                if len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError('GeoJSON polygon rings must contain four positions and be closed')
    try:
        parsed = shape(geometry)
    except Exception as error:
        raise ValueError('Malformed layer geometry') from error
    if parsed.is_empty or not parsed.is_valid:
        raise ValueError('Invalid layer geometry')
    return geometry


def adapt_layer(layer, data, population_lookup):
    """Three declarative adapters, no names/nearest-location matching or custom JS."""
    adapter, declared, fields = layer['adapter'], layer['geometry'], layer['fields']
    if adapter not in ('geojson', 'csv-points', 'csv-settlement'):
        raise ValueError('Unsupported layer adapter: ' + adapter)
    if declared not in LAYER_GEOMETRIES or (adapter != 'geojson' and declared != 'point'):
        raise ValueError('Unsupported geometry for layer adapter')
    if not isinstance(fields, dict) or not fields.get('id') or not fields.get('name'):
        raise ValueError('Layer fields.id and fields.name are required')
    text = data.decode('utf-8-sig')
    if adapter == 'geojson':
        def reject_constant(value):
            raise ValueError('GeoJSON contains nonfinite JSON constant: ' + value)
        source = json.loads(text, parse_constant=reject_constant)
        if not isinstance(source, dict) or source.get('type') != 'FeatureCollection' or not isinstance(source.get('features'), list):
            raise ValueError('GeoJSON layer source must be a FeatureCollection')
        rows = []
        for feature in source['features']:
            if feature.get('type') != 'Feature' or not isinstance(feature.get('properties'), dict):
                raise ValueError('Malformed GeoJSON Feature/properties')
            rows.append((feature['properties'], feature.get('geometry')))
    else:
        rows = [(row, None) for row in csv.DictReader(io.StringIO(text))]
    features, seen = [], set()
    for row, geometry in rows:
        for role, column in fields.items():
            if not isinstance(column, str) or not column or column not in row:
                raise ValueError('Layer source lacks configured column: ' + str(column))
        if row[fields['id']] is None or isinstance(row[fields['id']], (dict, list, bool)):
            raise ValueError('Layer source identity must be primitive and nonempty')
        uid = str(row[fields['id']]).strip()
        if not uid or uid in seen:
            raise ValueError('Empty or duplicate layer feature identity: ' + uid)
        seen.add(uid)
        name = row[fields['name']]
        if name is None or isinstance(name, (dict, list, bool)):
            raise ValueError('Layer feature name must be primitive')
        properties = {'id': uid, 'name': str(name),
                      'value': layer_value(row[fields['value']], uid) if fields.get('value') else None}
        if adapter == 'csv-points':
            if not fields.get('longitude') or not fields.get('latitude'):
                raise ValueError('CSV point layer requires longitude and latitude fields')
            lon = layer_value(row[fields['longitude']], uid + ' longitude')
            lat = layer_value(row[fields['latitude']], uid + ' latitude')
            geometry = {'type': 'Point', 'coordinates': [lon, lat]}
        elif adapter == 'csv-settlement':
            if not fields.get('settlementKey'):
                raise ValueError('Settlement layer requires fields.settlementKey')
            source_id = row[fields['settlementKey']]
            accepted = population_lookup.get(source_id)
            if accepted is None:
                raise ValueError('Layer settlement identity has no accepted point: ' + str(source_id))
            geometry = accepted['geometry']
            properties.update(sourceId=source_id, settlementId=accepted['properties']['id'])
        geometry = checked_geometry(geometry, declared)
        features.append({'type': 'Feature', 'id': uid, 'properties': properties, 'geometry': geometry})
    return feature_collection(features)


def export_layers(content, output, cache, population_lookup, offline=False):
    """Export every published registry entry; drafts/archives never reach the map."""
    datasets = {d['id']: d for d in json.loads((content / 'datasets.json').read_text())}
    registry, seen = [], set()
    for path in sorted((content / 'layers').glob('*.json')):
        layer = json.loads(path.read_text())
        uid = layer.get('id', '')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', uid) or path.stem != uid or uid in seen:
            raise ValueError('Invalid, duplicate, or mismatched layer ID/path: ' + uid)
        seen.add(uid)
        if layer.get('visibility') != 'published':
            continue
        if layer.get('palette') not in ('blue', 'categorical', 'service-type', 'population-change'):
            raise ValueError('Layer must use an approved palette')
        dataset = datasets.get(layer.get('datasetId'))
        if dataset is None:
            raise ValueError('Unknown layer dataset: ' + str(layer.get('datasetId')))
        raw = layer_source(dataset, cache, offline=offline)
        features = adapt_layer(layer, raw, population_lookup)
        relative = 'custom-layers/' + uid + '.geojson'
        write_json(output / relative, features)
        registry.append({key: layer[key] for key in ('id', 'researchId', 'title', 'description', 'geometry', 'palette', 'unit', 'period', 'evidence', 'fields')})
        registry[-1].update(path=relative, source={key: dataset.get(key) for key in ('title', 'url', 'sha256', 'sourceCommit')})
    active = {entry['id'] for entry in registry}
    for path in (output / 'custom-layers').glob('*.geojson'):
        if path.stem not in active:
            path.unlink()
    write_json(output / 'layers.json', registry)
    return registry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'web/public/data')
    parser.add_argument('--cache', type=Path, default=ROOT / '.research-cache/site')
    parser.add_argument('--offline', action='store_true', help='Use existing verified inputs; never access the network.')
    args = parser.parse_args(argv)
    import pandas as pd
    assets = json.loads((ROOT / 'data/site_assets.json').read_text())
    inputs = args.cache / 'inputs'
    if not args.offline:
        run_fetch(assets['populationCatalog'], inputs, ['data/population/*'], profile='population')
        run_fetch(assets['localCatalog'], inputs, ['*/services/nodes.csv', '*/services/links.csv'])
    else:
        for catalog, profile, patterns in [(assets['populationCatalog'], 'population', ['data/population/*']),
                                          (assets['localCatalog'], 'core', ['*/services/nodes.csv', '*/services/links.csv'])]:
            command = [sys.executable, str(ROOT / 'scripts/research_data.py'), 'verify', '--catalog', str(ROOT / catalog),
                       '--profile', profile, '--dest', str(inputs)]
            for pattern in patterns:
                command += ['--match', pattern]
            subprocess.run(command, cwd=ROOT, check=True)
    wide = pd.read_parquet(inputs / 'data/population/settlements_census_wide.parquet')
    long = pd.read_parquet(inputs / 'data/population/settlements_census_long.parquet')
    settlements, details, lookup = population_features(wide, long)
    write_json(args.output / 'settlements.geojson', feature_collection(settlements))
    compact = compact_population(settlements)
    overview = overview_population(compact)
    write_json(args.output / 'settlements.compact.json', compact)
    write_json(args.output / 'settlements.overview.json', overview)
    preview = preview_points(settlements)
    write_json(args.output / 'settlements-preview.json', preview)
    shards = {}
    for uid, detail in details.items():
        shards.setdefault(uid[:2], {})[uid] = detail
    for shard, records in shards.items():
        write_json(args.output / 'settlement-details' / (shard + '.json'), records)
    sources, boundary_counts, parent_names, raw_assets = [], {}, {}, []
    for asset in assets['boundaries']:
        target = boundary_cache_path(args.cache, asset)
        if args.offline:
            if not target.exists() or digest(target) != asset['sha256']:
                raise ValueError('Offline boundary missing or hash differs: ' + asset['id'])
        else:
            target = verified_download(asset, args.cache)
        raw_assets.append((asset, read_boundary_source(target, asset)))
        sources.append(asset)
    for output_layer, asset, raw, source_counts in merge_boundary_sources(raw_assets):
        features, coverage = boundary_features(raw, asset, settlements, details, parent_names)
        if asset['level'] == 'ADM1':
            parent_names.update({f['properties']['id']: f['properties']['name'] for f in features})
        write_json(args.output / (output_layer + '.geojson'), feature_collection(features))
        write_json(args.output / (output_layer + '-display.geojson'), display_boundaries(features))
        if output_layer == 'regions':
            write_json(args.output / 'country-preview.geojson', country_preview(features))
        boundary_counts[output_layer] = {'count': len(features), 'sourceCounts': source_counts, **coverage}
    services, links = local_services(inputs, lookup)
    write_json(args.output / 'services.geojson', feature_collection(services))
    write_json(args.output / 'links.geojson', feature_collection(links))
    centre_path = ROOT / 'sgrt/zero/checked_model_centres_20261025.csv'
    centres = []
    for row in csv.DictReader(centre_path.open()):
        existing = lookup.get(row['centre_settlement_id'])
        if existing:
            props = {**existing['properties'], 'starId': row['star_id'],
                     'externalMembers': int(row['strict_external_member_count']), 'evidence': 'model',
                     'scope': 'strict_diagnostic_subset_not_all_sgrt'}
            centres.append({**existing, 'properties': props})
    write_json(args.output / 'centres.geojson', feature_collection(centres))
    registry = export_layers(ROOT / 'web/content', args.output, args.cache, lookup, offline=args.offline)
    polygon_info = export_settlement_polygons(assets['settlementPolygons'], args.output, args.cache, lookup, offline=args.offline)
    git = subprocess.check_output(['git', 'show', '-s', '--format=%H%n%cI', 'HEAD'], cwd=ROOT, text=True).splitlines()
    manifest = {'version': 1, 'generatedAt': git[1], 'sourceCommit': git[0],
                'sources': [{'id': 'census-population', 'release': 'sgrt-census-population-20261022-v1', 'catalog': assets['populationCatalog']},
                            {'id': 'local-systems-20261024', 'release': 'sgrt-local-systems-20261024-v1', 'catalog': assets['localCatalog']}, *sources],
                'counts': {'settlements': len(settlements), 'overviewSettlements': len(overview['rows']),
                           'comparableSettlements': sum(f['properties']['comparable'] for f in settlements),
                           'services': len(services), 'links': len(links), 'strictCentresMapped': len(centres), 'customLayers': len(registry), 'boundaries': boundary_counts},
                'layers': {'population': 'settlements.geojson', 'schools': 'services.geojson', 'medical': 'services.geojson',
                           'links': 'links.geojson', 'regions': 'regions.geojson', 'districts': 'districts.geojson', 'centres': 'centres.geojson'},
                'interactiveTransport': {'settlements': 'settlements.compact.json', 'settlementsOverview': 'settlements.overview.json',
                                         'overviewCount': len(overview['rows']), 'overviewMinimumKnownPopulation': 10000,
                                         'overviewBasis': 'maximum_available_working_population_2002_2010_2021_for_display_only',
                                         'regions': 'regions-display.geojson', 'districts': 'districts-display.geojson',
                                         'settlementCount': len(settlements), 'settlementValues': 'lossless_dictionary_rows',
                                         'displayCoordinateDecimals': 5, 'aggregation': 'unchanged_unsimplified_source_geometry'},
                'detailPath': 'settlement-details/{shard}.json',
                'customLayers': 'layers.json',
                'settlementPolygons': polygon_info,
                'preview': {'path': 'settlements-preview.json', 'outlinePath': 'country-preview.geojson', 'outlineUse': 'decorative_reference_land_only', 'count': len(preview), 'method': 'one_real_highest_population_point_per_0.15_degree_cell_for_thumbnail_only'},
                'limitations': [assets.get('boundaryNote', 'Справочная сетка границ не подменяет принятую переписную основу.'),
                                'Сводки внутри контуров рассчитаны по фиксированному сопоставимому набору точек; это не официальные муниципальные итоги.',
                                'Слой услуг и документированных связей охватывает локальный пример Учалинского района, а не всю Россию.',
                                '197 строгих центров — диагностический модельный поднабор; полный состав их окружений здесь не восстановлен.']}
    write_json(args.output / 'manifest.json', manifest)
    total_bytes = sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())
    if total_bytes > 350 * 1024 * 1024:
        raise ValueError('Web data exceeds 350 MiB publication budget')
    print(json.dumps({'output': str(args.output), 'bytes': total_bytes, 'counts': manifest['counts']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
