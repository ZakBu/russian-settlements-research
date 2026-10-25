#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""National descriptive profile on accepted census20261022, preserving all wide rows.
Run: PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 /absolute/path/to/build_national.py
Dependencies: pyarrow, geographiclib. No causal estimates; no historical WB exposure.
"""
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq
import pyarrow as pa
from geographiclib.geodesic import Geodesic

OUT = Path(__file__).resolve().parent
PARENT = OUT.parent
ROOT = next(p for p in OUT.parents if (p / 'work/sources/commerce_current.parquet').exists())
POP = PARENT / 'pilot/inputs/data/population'
WIDE = POP / 'settlements_census_wide.parquet'
LONG = POP / 'settlements_census_long.parquet'
LEGACY = ROOT / 'work/sources/research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet'
COMMERCE = ROOT / 'work/sources/commerce_current.parquet'
WB = 'commerce_wb20261021_baseline_focus_count'
WB5 = 'commerce_wb20261021_baseline_focus_within5km_count'


def finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def size(pop):
    if pop is None:
        return 'unknown'
    for upper, label in [(0, '00_zero'), (100, '01_1_100'), (500, '02_101_500'), (1000, '03_501_1000'), (3000, '04_1001_3000'), (10000, '05_3001_10000'), (50000, '06_10001_50000'), (100000, '07_50001_100000'), (500000, '08_100001_500000'), (math.inf, '09_over_500000')]:
        if pop <= upper:
            return label


def trend(a, b):
    if a is None or b is None:
        return 'unknown_2002_or_2021'
    if a == 0:
        return 'zero_both_years' if b == 0 else 'zero2002_positive2021'
    return 'decrease' if b < a else 'increase' if b > a else 'unchanged_positive_baseline'


def aggregate(rows, keys, suffix):
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r.get(k) if r.get(k) is not None else 'unknown' for k in keys)].append(r)
    out = []
    for values, group in sorted(groups.items(), key=lambda t: tuple(map(str, t[0]))):
        c = Counter(r['WB_evidence_status' + suffix] for r in group)
        p = sum(r['population_2021'] for r in group)
        positive_pop = sum(r['population_2021'] for r in group if r['WB_evidence_status' + suffix] == 'positive')
        positive = c['positive']
        zero = c['zero_accepted_records_not_confirmed_absence']
        x = dict(zip(keys, values))
        x.update({'settlements_n': len(group), 'known_population_2021_sum': p, 'WB_positive_n': positive, 'WB_zero_accepted_records_not_confirmed_absence_n': zero, 'WB_unknown_n': len(group)-positive-zero, 'WB_positive_share_all_target_settlements': positive/len(group), 'WB_positive_share_source_observed_settlements': positive/(positive+zero) if positive+zero else None, 'population_in_WB_positive_settlements': positive_pop, 'population_share_in_WB_positive_settlements': positive_pop/p if p else None, 'accepted_points_present_n': sum(r['accepted_point_present_2021'] is True for r in group), 'historical_trend_unknown_n': sum(r['trend_2002_2021'].startswith('unknown') for r in group)})
        out.append(x)
    assert sum(x['settlements_n'] for x in out) == len(rows)
    assert all(x['WB_positive_n'] + x['WB_zero_accepted_records_not_confirmed_absence_n'] + x['WB_unknown_n'] == x['settlements_n'] for x in out)
    return out


def csvwrite(path, rows):
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    wide = pq.read_table(WIDE).to_pylist()
    source2021_rows = pq.read_table(LONG, filters=[('census_year', '=', 2021)]).to_pylist()
    assert len(wide) == 173242
    assert len({r['root'] for r in wide}) == len(wide)
    assert len({r['source_record_id'] for r in source2021_rows}) == len(source2021_rows)
    source2021 = {r['source_record_id']: r for r in source2021_rows}
    assert set(r['source_record_id_2021'] for r in wide if r['source_record_id_2021']) == set(source2021)
    old = pq.read_table(LEGACY, columns=['id', 'source_record_id_2021', 'name', 'type', 'region', 'lat', 'lon']).to_pylist()
    assert len({r['id'] for r in old}) == len(old)
    old_source = [r for r in old if r['source_record_id_2021']]
    assert len({r['source_record_id_2021'] for r in old_source}) == len(old_source)
    old_byid = {r['id']: r for r in old}
    commerce_rows = pq.read_table(COMMERCE, columns=['id', WB, WB5]).to_pylist()
    assert len({r['id'] for r in commerce_rows}) == len(commerce_rows)
    commerce = {}
    join_rows = []
    for r in commerce_rows:
        legacy = old_byid.get(r['id'])
        sid = legacy.get('source_record_id_2021') if legacy else None
        accepted = source2021.get(sid)
        if accepted is None:
            join_rows.append({'legacy_commerce_id': r['id'], 'source_record_id_2021': sid, 'accepted_source2021_present': False, 'source_metadata_agreement': None, 'accepted_vs_legacy_point_distance_km': None, 'WB_focus_count': r[WB]})
            continue
        agreement = (legacy['name'], legacy['type'], legacy['region']) == (accepted['settlement_name'], accepted['settlement_type'], accepted['region_norm'])
        coords = [legacy['lat'], legacy['lon'], accepted['accepted_latitude'], accepted['accepted_longitude']]
        displacement = Geodesic.WGS84.Inverse(coords[0], coords[1], coords[2], coords[3])['s12']/1000 if all(map(finite, coords)) else None
        info = {'legacy_commerce_id': r['id'], 'source_record_id_2021': sid, 'accepted_source2021_present': True, 'source_metadata_agreement': agreement, 'accepted_vs_legacy_point_distance_km': displacement, 'WB_focus_count': r[WB]}
        join_rows.append(info)
        assert sid not in commerce
        commerce[sid] = dict(info, WB_focus_within5km_count=r[WB5])
    base = []
    for w in wide:
        sid = w['source_record_id_2021']
        s = source2021.get(sid)
        scope = s['population_scope'] if s else None
        physical = bool(s and scope == 'settlement' and s['is_additive_settlement_record'] is True and s['effective_population'] is not None)
        group = ('target_credited_physical_settlement2021' if s['working_credit_present'] is True else 'physical2021_not_working_credited') if physical else 'federal_city_territory2021' if scope == 'federal_city_region' else 'historical_only_no_source2021' if s is None else 'other2021_outside_target'
        wb = commerce.get(sid)
        count = wb['WB_focus_count'] if wb else None
        if not physical:
            status = 'not_in_target_population'
        elif wb is None:
            status = 'unknown_no_commerce_bridge'
        elif not wb['source_metadata_agreement']:
            status = 'unknown_source_metadata_conflict'
        elif count is None:
            status = 'unknown_null_WB_count'
        else:
            status = 'positive' if count > 0 else 'zero_accepted_records_not_confirmed_absence'
        sensitivity = status
        if physical and wb is not None and status in ('positive', 'zero_accepted_records_not_confirmed_absence'):
            if wb['accepted_vs_legacy_point_distance_km'] is None:
                sensitivity = 'unknown_point_transfer_unverifiable'
            elif wb['accepted_vs_legacy_point_distance_km'] > 1:
                sensitivity = 'unknown_point_shift_over1km'
        x = {'root_accepted20261022': w['root'], 'source_record_id_2021': sid, 'analysis_population': group, 'name_2021': s['settlement_name'] if s else None, 'type_2021': s['settlement_type'] if s else None, 'region_2021': s['region_norm'] if s else None, 'district_2021': s['district_raw'] if s else None, 'population_scope_2021': scope, 'is_additive_settlement_record_2021': s['is_additive_settlement_record'] if s else None, 'accepted_point_present_2021': s['accepted_point_present'] if s else False, 'accepted_latitude_2021': s['accepted_latitude'] if s else None, 'accepted_longitude_2021': s['accepted_longitude'] if s else None, 'ordinary_full3': w['ordinary_full3'], 'size2021': size(w['effective_population_2021']), 'trend_2002_2021': trend(w['effective_population_2002'], w['effective_population_2021']), 'WB_focus20261021_count': count if physical else None, 'WB_focus20261021_within5km_count': wb['WB_focus_within5km_count'] if wb and physical else None, 'WB_evidence_status': status, 'WB_evidence_status_sensitivity': sensitivity, 'legacy_commerce_id_bridge_only': wb['legacy_commerce_id'] if wb else None, 'source_metadata_agreement': wb['source_metadata_agreement'] if wb else None, 'accepted_vs_legacy_point_distance_km': wb['accepted_vs_legacy_point_distance_km'] if wb else None}
        x['working_credit_present_2021'] = s['working_credit_present'] if s else False
        for year in (2002, 2010, 2021):
            for prefix in ('source_record_id_', 'population_value_quality_', 'population_overlay_applied_'):
                x[prefix+str(year)] = w[prefix+str(year)]
            x['reported_population_'+str(year)] = w['population_'+str(year)]
            x['population_'+str(year)] = w['effective_population_'+str(year)]
        base.append(x)
    physical_inventory = [r for r in base if r['analysis_population'] in ('target_credited_physical_settlement2021', 'physical2021_not_working_credited')]
    target = [r for r in base if r['analysis_population'] == 'target_credited_physical_settlement2021']
    notcredited = [r for r in base if r['analysis_population'] == 'physical2021_not_working_credited']
    historical = [r for r in base if r['analysis_population'] == 'historical_only_no_source2021']
    federal = [r for r in base if r['analysis_population'] == 'federal_city_territory2021']
    assert len(base) == len(wide)
    assert len(target) == 144151 and len(notcredited) == 11260 and len(federal) == 3 and len(historical) == 17828
    assert len(target) + len(notcredited) + len(federal) + len(historical) == len(base)
    assert len({r['source_record_id_2021'] for r in target}) == len(target)
    schemes = {'national': [], 'by_region': ['region_2021'], 'by_type': ['type_2021'], 'by_size2021': ['size2021'], 'by_trend2002_2021': ['trend_2002_2021'], 'by_size_and_trend': ['size2021','trend_2002_2021'], 'by_size_and_region': ['size2021','region_2021']}
    aggregates = {}
    for label, keys in schemes.items():
        for suffix in ('', '_sensitivity'):
            rows = aggregate(target, keys, suffix)
            csvwrite(OUT / (label+suffix+'.csv'), rows)
            aggregates[label+suffix] = rows
            # Source inventory is a sensitivity population, never added to main totals.
            inventory_rows = aggregate(physical_inventory, keys, suffix)
            csvwrite(OUT / ('all_physical_inventory_'+label+suffix+'.csv'), inventory_rows)
    pq.write_table(pa.Table.from_pylist(base), OUT/'national_base_all_wide.parquet', compression='zstd')
    pq.write_table(pa.Table.from_pylist(target), OUT/'national_target_source2021.parquet', compression='zstd')
    pq.write_table(pa.Table.from_pylist(physical_inventory), OUT/'all_physical_source2021_inventory.parquet', compression='zstd')
    pq.write_table(pa.Table.from_pylist(notcredited), OUT/'physical_source2021_notcredited.parquet', compression='zstd')
    csvwrite(OUT/'source2021_commerce_join.csv', join_rows)
    csvwrite(OUT/'federal_territories_separate.csv', federal)
    shifts = [r for r in target if r['accepted_vs_legacy_point_distance_km'] is not None and r['accepted_vs_legacy_point_distance_km'] > 1]
    csvwrite(OUT/'point_shifts_over1km.csv', shifts)
    statuses = Counter(r['WB_evidence_status'] for r in target)
    sens_statuses = Counter(r['WB_evidence_status_sensitivity'] for r in target)
    pos = [r for r in target if r['WB_evidence_status'] == 'positive']
    summary = {'audit_date':'2026-10-24', 'analysis':'national descriptive placement profile, no causal effects', 'accepted_population_release':'census accepted20261022', 'all_accepted_wide_roots':len(base), 'target_definition':'Accepted working_credit_present=True current2021 own physical additive settlement observations with effective population. Historical completeness and accepted coordinate availability are not required. All physical source rows are retained separately as inventory sensitivity.', 'target_settlements2021_n':len(target), 'all_physical_source2021_inventory_n':len(physical_inventory), 'physical2021_not_working_credited_n':len(notcredited), 'all_physical_inventory_national':aggregate(physical_inventory, [], '')[0], 'notcredited_population_known_sum_do_not_add_to_main_total':sum(r['population_2021'] for r in notcredited), 'federal_territory2021_n':len(federal), 'historical_only_no_source2021_n':len(historical), 'regions_in_target_n':len(set(r['region_2021'] for r in target)), 'WB_status_counts':dict(statuses), 'WB_sensitivity_status_counts':dict(sens_statuses), 'national':aggregates['national'][0], 'national_sensitivity':aggregates['national_sensitivity'][0], 'positive_WB_settlements_with_2002_2021_decrease_n':sum(r['trend_2002_2021']=='decrease' for r in pos), 'positive_WB_settlements_with_unknown_2002_2021_trend_n':sum(r['trend_2002_2021'].startswith('unknown') for r in pos), 'point_shift_over1km_target_n':len(shifts), 'point_shift_over1km_positive_n':sum(r['WB_evidence_status']=='positive' for r in shifts), 'sensitivity_rule':'Keep full target denominator; reclassify WB observations whose accepted-vs-legacy point displacement exceeds1km or cannot be measured as unknown. Do not encode them as zero.', 'join_rule':'Current commerce legacy id -> unique legacy source_record_id2021 -> exact accepted source_record_id2021; metadata conflicts are unknown. No legacy root/population/geometry used for accepted population or location.', 'population_rule':'population_YYYY=accepted effective_population_YYYY; source-reported counts and overlay flags retained.', 'WB_rule':'Positive means accepted WB types8/34 in current snapshot2026-10-21; zero accepted records is not proven physical absence or lack of service. No WB treatment assigned to2002/2010/2021.', 'trend_rule':'Compare effective2002 vs2021: decrease/increase/unchanged; zero baseline separated; unknown retained. No historical completeness restriction.', 'source_scope':'Territory and regions follow the accepted census source; region totals of federal cities are stored separately from physical settlement units. No full national territorial coverage claim follows from these counts.', 'inputs':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (WIDE,LONG,LEGACY,COMMERCE)], 'verification':{'wide_partition_reconciled':True,'source2021_unique':True,'no_legacy_root_join':True,'all_aggregate_denominators_reconciled':True,'all_WB_status_partitions_reconciled':True}, 'limitations':['Descriptive selection/placement, not influence on population or functional areas.','Snapshot lacks opening dates and consumer flows.','Unknown and zero accepted records do not establish absence.','Point-transfer sensitivity is a diagnostic; original source binding can still contain address errors.','Census historical values retain source quality flags; numerical availability does not prove longitudinal comparability.','Surrounding settlements can use another settlement pickup point; node presence is not household access.']}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    lines=['Общероссийский описательный слой на принятой базе census accepted20261022.',f'Сохранена вся wide-база: {len(base)} roots. Основная целевая совокупность: {len(target)} физических НП2021 с working_credit_present=True. Все физические строки источника: {len(physical_inventory)}, из них {len(notcredited)} notcredited выделены отдельно и не добавлены к основным суммам. Федеральные территории отдельно: {len(federal)}. Historical-only без собственной строки2021: {len(historical)}.', 'Основные знаменатели используют accepted working-credit. Все155411 физических строк сохранены отдельным inventory и CSV чувствительности all_physical_inventory_*. Неcredited строки могут дублировать рабочую ось и не включены молча в основные суммы. Неполные исторические ряды не исключались; неизвестный тренд выделен отдельно.', 'Население и координаты взяты исключительно из принятого выпуска. Старый root не использован в join.', 'WB — принятые записи типов8/34 снимка21.10.2026; к предпериоду не приписывается как экспозиция.', 'WB status counts: '+json.dumps(dict(statuses),ensure_ascii=False), 'Sensitivity status counts: '+json.dumps(dict(sens_statuses),ensure_ascii=False), f'Сдвиг принятой точки относительно прежней привязки более1км: {len(shifts)} НП, из них WB-positive: {summary["point_shift_over1km_positive_n"]}. В чувствительности эти наблюдения становятся unknown при сохранении полного знаменателя.', f'Среди WB-positive исторический спад2002–2021 отмечен у {summary["positive_WB_settlements_with_2002_2021_decrease_n"]}; это характеризует размещение в2026 относительно прошлой траектории, а не вызванный WB спад.', 'Нулевые принятые записи не означают доказанное отсутствие ПВЗ или обслуживания. Unknown не заменён нулём. Присутствие ПВЗ у соседей не измерено этим слоем.', 'Разрезы: регион, тип НП, размер2021, динамика2002–2021, размер×тренд, размер×регион. В каждом разрезе сохранён общий знаменатель, раздельные positive/zero/unknown и две доли: от всех НП и от НП с принятой записью либо нулём источника.', 'Численность территории федерального города не смешана с физическими НП. Исторические сущности сохранены в national_base_all_wide.parquet. Регионы и география следуют принятому переписному источнику; полнота национального территориального охвата из этих чисел не выводится.', 'Проверки: уникальные ключи, точное покрытие source2021, баланс всех173242 roots, баланс статусов и знаменателей всех CSV. Причинная модель не оценивалась.']
    (OUT/'national_findings.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ('all_accepted_wide_roots','target_settlements2021_n','federal_territory2021_n','historical_only_no_source2021_n','WB_status_counts','WB_sensitivity_status_counts','point_shift_over1km_target_n','point_shift_over1km_positive_n')},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
