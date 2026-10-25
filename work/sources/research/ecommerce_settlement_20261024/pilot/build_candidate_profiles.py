#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Descriptive pilot screening; WGS84 geodesic circles are not catchments.

Run from any cwd:
PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 /absolute/path/to/this.py
Dependencies: pyarrow and geographiclib. Existing inputs are never overwritten.
"""
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
from geographiclib.geodesic import Geodesic

OUT = Path(__file__).resolve().parent
ROOT = next(p for p in OUT.parents if (p / 'work/sources/commerce_current.parquet').exists())
AXIS = ROOT / 'work/sources/research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet'
COMMERCE = ROOT / 'work/sources/commerce_current.parquet'
ACCEPTED_WIDE = OUT / 'inputs/data/population/settlements_census_wide.parquet'
ACCEPTED_LONG = OUT / 'inputs/data/population/settlements_census_long.parquet'
REGION = 'нижегородская'
RADIUS_KM = 20.0
WB = 'commerce_wb20261021_baseline_focus_count'
WB5 = 'commerce_wb20261021_baseline_focus_within5km_count'
CENTRES = [
    ('Воскресенское', 'пгт', 'Воскресенский муниципальный район', '73177'),
    ('Шаранга', 'пгт', 'Шарангский муниципальный район', '74916'),
    ('Тонкино', 'пгт', 'Тонкинский муниципальный район', '74826'),
    ('Тоншаево', 'пгт', 'Тоншаевский муниципальный округ', '72211'),
    ('Ветлуга', 'город', 'Ветлужский муниципальный район', '72959'),
    ('Урень', 'город', 'Уренский муниципальный округ', '72292'),
]


def distance(a, b):
    return Geodesic.WGS84.Inverse(a['lat'], a['lon'], b['lat'], b['lon'])['s12'] / 1000


def finite_coordinates(r):
    return all(isinstance(r.get(k), (float, int)) and math.isfinite(r[k]) for k in ('lat', 'lon'))


def pct(a, b):
    return 100 * (b / a - 1) if a is not None and b is not None and a > 0 else None


def wb_status(row, commerce):
    record = commerce.get(row['id'])
    value = record.get(WB) if record else None
    if value is None:
        return value, 'unknown_no_commerce_row_or_null'
    return value, 'positive_accepted_WB_focus' if value > 0 else 'zero_accepted_records_not_confirmed_absence'


def row_fields(r, commerce):
    count, status = wb_status(r, commerce)
    result = {k: r.get(k) for k in ('id', 'root', 'name', 'type', 'region', 'lat', 'lon', 'municipality_oktmo8_2021', 'municipality_upper_2021', 'oktmo_2021', 'geography_status', 'population_scope', 'is_additive_source_unit')}
    for year in (2002, 2010, 2021):
        for prefix in ('population_', 'reported_population_', 'population_value_quality_', 'population_overlay_applied_', 'source_record_id_'):
            result[prefix + str(year)] = r.get(prefix + str(year))
    result.update({
        'pct_population_2002_2010': pct(r['population_2002'], r['population_2010']),
        'pct_population_2010_2021': pct(r['population_2010'], r['population_2021']),
        'pct_population_2002_2021': pct(r['population_2002'], r['population_2021']),
        WB: count,
        WB5: commerce.get(r['id'], {}).get(WB5),
        'WB_evidence_status': status,
        'WB_snapshot_date_for_commerce_wb20261021_fields': '2026-10-21',
        'WB_legacy_link_id_via_unique_source_record_id_2021': commerce.get(r['id'], {}).get('legacy_id'),
        'coordinate_admission_status_2021': r.get('coordinate_admission_status_2021'),
        'ordinary_full3': r.get('ordinary_full3'),
    })
    return result


def write_csv(name, rows):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    # Legacy rows are consulted ONLY as an id -> exact 2021 source-record bridge.
    # No legacy root, population, coordinates, grouping or delimitation are used.
    legacy = pq.read_table(AXIS, columns=['id', 'source_record_id_2021', 'name', 'type', 'region', 'lat', 'lon']).to_pylist()
    assert len({r['id'] for r in legacy}) == len(legacy)
    legacy_with_source = [r for r in legacy if r['source_record_id_2021'] is not None]
    assert len({r['source_record_id_2021'] for r in legacy_with_source}) == len(legacy_with_source)
    bridge = {r['id']: r for r in legacy_with_source}
    long2021 = pq.read_table(ACCEPTED_LONG, filters=[('census_year', '=', 2021)]).to_pylist()
    assert len({r['source_record_id'] for r in long2021}) == len(long2021)
    source2021 = {r['source_record_id']: r for r in long2021}
    wide = pq.read_table(ACCEPTED_WIDE).to_pylist()
    assert len({r['root'] for r in wide}) == len(wide)
    axis = []
    for r in wide:
        sid = r['source_record_id_2021']
        if sid is None:
            continue
        s = source2021[sid]
        x = dict(r)
        x.update({'id': sid, 'name': r['settlement_name_2021'], 'type': r['settlement_type_2021'], 'region': r['region_norm_2021'], 'lat': r['accepted_latitude_2021'], 'lon': r['accepted_longitude_2021'], 'municipality_upper_2021': r['district_raw_2021'], 'municipality_oktmo8_2021': None, 'geography_status': s['coordinate_admission_status'], 'coordinate_admission_status_2021': s['coordinate_admission_status'], 'population_scope': s['population_scope'], 'is_additive_source_unit': s['is_additive_settlement_record']})
        for year in (2002, 2010, 2021):
            x['reported_population_' + str(year)] = r['population_' + str(year)]
            x['population_' + str(year)] = r['effective_population_' + str(year)]
        axis.append(x)
    commerce_rows = pq.read_table(COMMERCE, columns=['id', WB, WB5]).to_pylist()
    assert len({r['id'] for r in axis}) == len(axis)
    assert len({r['id'] for r in commerce_rows}) == len(commerce_rows)
    commerce = {}
    for r in commerce_rows:
        old = bridge.get(r['id'])
        if old is None:
            continue
        sid = old['source_record_id_2021']
        accepted = source2021.get(sid)
        if accepted is None:
            continue
        # Exact source identity, plus name/type/region agreement; no root join.
        if (old['name'], old['type'], old['region']) != (accepted['settlement_name'], accepted['settlement_type'], accepted['region_norm']):
            continue
        assert sid not in commerce
        commerce[sid] = dict(r, legacy_id=r['id'], id=sid)
    byid = {r['id']: r for r in axis}
    regional = [r for r in axis if r['region'] == REGION]
    eligible = [r for r in regional if finite_coordinates(r) and r['is_additive_source_unit'] is True and r['population_scope'] == 'settlement']
    anchor = [r for r in regional if r['name'] == 'Нижний Новгород' and r['type'] == 'город' and finite_coordinates(r)]
    assert len(anchor) == 1, 'Regional capital identity must be unique'
    anchor = anchor[0]
    centres, neighbours, profiles = [], [], []
    for name, kind, municipality, suffix in CENTRES:
        # Fixed source IDs independently inspected in the accepted long release.
        uid = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:' + suffix
        candidates = [r for r in regional if r['name'] == name and r['type'] == kind and r['municipality_upper_2021'] == municipality]
        assert len(candidates) == 1 and candidates[0]['id'] == uid, (name, candidates)
        centre = candidates[0]
        assert centre in eligible
        current = row_fields(centre, commerce)
        current['distance_to_nizhny_novgorod_WGS84_km'] = distance(centre, anchor)
        current['screen_radius_geodesic_km'] = RADIUS_KM
        centres.append(current)
        selected = []
        for r in eligible:
            if r['id'] == uid:
                continue
            km = distance(centre, r)
            if km > RADIUS_KM:
                continue
            x = {'centre_id': uid, 'centre_name': name, 'distance_WGS84_geodesic_km': km}
            x.update(row_fields(r, commerce))
            selected.append(x)
        selected.sort(key=lambda x: (x['distance_WGS84_geodesic_km'], x['id']))
        neighbours.extend(selected)
        positive = sum(x['WB_evidence_status'] == 'positive_accepted_WB_focus' for x in selected)
        zero = sum(x['WB_evidence_status'] == 'zero_accepted_records_not_confirmed_absence' for x in selected)
        unknown = len(selected) - positive - zero
        population_known = [x['population_2021'] for x in selected if x['population_2021'] is not None]
        profiles.append({
            'centre_id': uid, 'centre_name': name,
            'neighbours_20km_excluding_centre': len(selected),
            'neighbours_with_positive_WB_focus': positive,
            'neighbours_with_zero_accepted_WB_records_not_confirmed_absence': zero,
            'neighbours_with_unknown_WB_evidence': unknown,
            'positive_WB_share_among_all_screened_neighbours': positive / len(selected) if selected else None,
            'positive_WB_share_among_commerce_observed_neighbours': positive / (positive + zero) if positive + zero else None,
            'neighbours_population_2021_known_count': len(population_known),
            'neighbours_population_2021_unknown_count': len(selected) - len(population_known),
            'sum_known_neighbour_population_2021_not_complete_when_unknown': sum(population_known),
            'same_municipality_neighbours_count': sum(x['municipality_upper_2021'] == municipality for x in selected),
            'other_municipality_same_region_neighbours_count': sum(x['municipality_upper_2021'] != municipality for x in selected),
            'WB_focus_objects_in_neighbours_known_records_sum': sum(x[WB] for x in selected if x[WB] is not None),
        })
    pairs = [(x['centre_id'], x['id']) for x in neighbours]
    assert len(pairs) == len(set(pairs))
    assert all(x['region'] == REGION and 0 <= x['distance_WGS84_geodesic_km'] <= RADIUS_KM and x['centre_id'] != x['id'] for x in neighbours)
    assert all(x['is_additive_source_unit'] is True for x in neighbours)
    repeated = Counter(x['id'] for x in neighbours)
    overlap = {uid: n for uid, n in repeated.items() if n > 1}
    bridge_displacements = []
    for x in centres + neighbours:
        old_id = x['WB_legacy_link_id_via_unique_source_record_id_2021']
        if old_id and finite_coordinates(bridge[old_id]):
            bridge_displacements.append(distance(x, bridge[old_id]))
    # Modern object bindings were not re-estimated. If accepted coordinates move,
    # source-ID agreement alone does not validate the old geographic assignment.
    assert all(d < 1e-7 for d in bridge_displacements), 'Pilot needs object-level WB re-linkage: coordinate displacement found'
    result = {
        'audit_date': '2026-10-24', 'purpose': 'descriptive pilot screening; no causal estimation',
        'distance_definition': 'geographiclib Geodesic.WGS84 inverse ellipsoidal surface distance in km; not road travel time',
        'radius_km': RADIUS_KM, 'region_filter': REGION,
        'scope': 'Accepted census20261022 own 2021 observations, same-region additive physical settlement rows with finite accepted 2021 coordinates; each centre excluded; all settlement types retained.',
        'population_definition': 'population_YYYY fields in pilot outputs are accepted effective_population_YYYY, with original reported_population_YYYY and overlay flags retained.',
        'id_definition': 'Exact accepted source_record_id_2021; root is accepted release grouping, never a join to legacy data.',
        'WB_join_definition': 'Legacy commerce id -> unique legacy source_record_id2021 -> exact accepted source_record_id2021, with exact name/type/region agreement. Legacy population, coordinates and root never used.',
        'legacy_commerce_rows_successfully_source_bridged': len(commerce),
        'candidate_selection': 'All six user-specified candidates retained. Contrast is assessed descriptively after identities are fixed; these are not independent treated/control units.',
        'same_name_resolution': 'Exact accepted region + name + type + municipality2021, with independently inspected fixed source_record_id2021 assertion. Other namesakes are rejected.',
        'regional_axis_rows': len(regional), 'eligible_regional_rows': len(eligible),
        'regional_rows_without_finite_coordinates': sum(not finite_coordinates(r) for r in regional),
        'regional_rows_excluded_nonadditive_or_nonsettlement_among_finite_coordinates': sum(finite_coordinates(r) and not (r['is_additive_source_unit'] is True and r['population_scope'] == 'settlement') for r in regional),
        'regional_capital_anchor': {k: anchor[k] for k in ('id', 'name', 'lat', 'lon')},
        'inputs': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (ACCEPTED_WIDE, ACCEPTED_LONG, AXIS, COMMERCE)],
        'centres': centres, 'profiles': profiles,
        'neighbour_rows': len(neighbours), 'unique_neighbour_ids': len(repeated),
        'overlap_neighbour_ids_in_multiple_circles_count': len(overlap),
        'overlap_neighbour_ids': overlap,
        'WB_bridge_coordinate_displacement_check': {'checked_centre_plus_neighbour_rows': len(bridge_displacements), 'maximum_displacement_km': max(bridge_displacements, default=None), 'required_below_km': 1e-7, 'interpretation': 'Old coordinates used only for verification of transferred WB geographic binding, never as pilot geometry.'},
        'verification': {'accepted_population_release_used': True, 'legacy_root_join_forbidden': True, 'unique_source_axis_ids': True, 'unique_source_commerce_ids': True, 'exact_centre_identities': True, 'unique_centre_neighbour_pairs': True, 'all_neighbours_same_region': True, 'all_distances_in_0_20km': True, 'all_neighbours_additive_physical_settlements': True},
        'limitations': ['Circles are geographical screening windows, not functional service areas.', 'Zero WB means no accepted source record, not verified absence.', 'Missing commerce rows stay unknown, not zero.', 'WB is a 2026 snapshot; opening dates and consumer trips are unknown.', 'Population changes end in 2021 and cannot be attributed to WB2026.', 'Centres and neighbourhoods may overlap and are not independent.', 'Incomplete coordinates and historical linkage/source quality limit coverage.', 'Straight-line distance to the regional capital is a remoteness screening proxy, not travel time.'],
    }
    write_csv('candidate_centres.csv', centres)
    write_csv('candidate_neighbours.csv', neighbours)
    (OUT / 'candidate_profiles.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    notes = ['Accepted population release20261022: effective_population and accepted coordinates2021. Original reported values and overlay flags retained. Source_record_id2021 is the identity key; legacy root not used.', 'WB bridge: legacy commerce ID -> unique source_record_id2021 -> accepted source_record_id2021 with exact name/type/region agreement.', 'All six centres have positive WB in2026. No untreated central-place comparison is available inside this set.', 'Neighbour zero counts do not imply lack of service: people can use WB in the centre or another settlement.', 'Пилот: северо-восток Нижегородской области', 'Все шесть заданных центров сохранены; даты открытия WB/Ozon не восстановлены.', 'Метрика: геодезическое расстояние на эллипсоиде WGS84 (GeographicLib), радиус 20 км. Это скрининг, не функциональный ареал и не дорожное время.', 'Окружение: все типы физических аддитивных НП с координатами в Нижегородской области, центр исключён. Другие муниципалитеты внутри региона допускаются и посчитаны отдельно. Другие регионы исключены.', 'Воскресенское разрешено как пгт Воскресенского района. Одноимённые село Сергачского района и деревня Тоншаевского округа не выбирались центром.', 'Нули WB = нет принятой записи в источнике, а не доказанное отсутствие; отсутствующие строки commerce и NULL выделены отдельно.', 'Численность 2002/2010/2021 и качество каждого года сохранены вместе с source_record_id. Современное WB не является наблюдением экспозиции в этих годах.', 'Расстояние до Нижнего Новгорода — геодезический показатель положения, не транспортная доступность.', 'Вне координатной выборки остаётся региональных строк: ' + str(result['regional_rows_without_finite_coordinates']), 'Окружения пересекаются: ' + str(len(overlap)) + ' уникальных НП входят более чем в один круг. Не суммировать их как независимые объекты.', 'Проверены уникальность исходных ключей, однозначные центры, соответствие UID, отсутствие повторов centre×neighbour, границы расстояния и единый регион. Причинная регрессия не проводилась.']
    notes.append('WB bridge coordinate displacement check: ' + str(len(bridge_displacements)) + ' centre/neighbour rows; maximum km = ' + str(max(bridge_displacements, default=None)) + '. Legacy coordinates used only to check transfer, never to position the pilot.')
    for c, p in zip(centres, profiles):
        notes.append(f"{c['name']}: население2021={c['population_2021']}, изменение2010–2021={c['pct_population_2010_2021']:.2f}%; WB-focus={c[WB]}, до Нижнего Новгорода={c['distance_to_nizhny_novgorod_WGS84_km']:.1f}км; окружение={p['neighbours_20km_excluding_centre']} НП, WB-positive={p['neighbours_with_positive_WB_focus']}, нулевых принятых записей={p['neighbours_with_zero_accepted_WB_records_not_confirmed_absence']}, неизвестных={p['neighbours_with_unknown_WB_evidence']}.")
    (OUT / 'local_pilot_notes.txt').write_text('\n'.join(notes) + '\n', encoding='utf-8')
    print(json.dumps({'centres': len(centres), 'neighbour_rows': len(neighbours), 'unique_neighbours': len(repeated), 'overlap_neighbours': len(overlap), 'profiles': profiles}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
