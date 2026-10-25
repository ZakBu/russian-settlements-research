"""Independent local-input audit. Run with PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 audit.py."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import math
import pyarrow.parquet as pq

OUT = Path(__file__).resolve().parent
BASE = OUT.parent.parent
SOURCES = BASE.parent.parent
checks = []
inputs = {}


def load(relative, source=False):
    path = (SOURCES if source else BASE) / relative
    table = pq.read_table(path)
    inputs[str(path)] = {
        'rows': table.num_rows, 'columns': len(table.column_names),
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'schema': str(table.schema),
    }
    return table.to_pylist()


def check(name, passed, detail):
    checks.append({'name': name, 'status': 'PASS' if passed else 'FAIL', 'detail': detail})


def warn(name, detail):
    checks.append({'name': name, 'status': 'WARN', 'detail': detail})


def counts(rows, col):
    return dict(Counter(str(r[col]) for r in rows))


target = load('national/national_target_source2021.parquet')
combined = load('national/ozon_WB_comparison_main_target_experimental.parquet')
allwide = load('national/national_base_all_wide.parquet')
inventory = load('national/all_physical_source2021_inventory.parquet')
objects = load('national/ozon_objectlinks_experimental.parquet')
urban = load('national/urban_population_panel_main_wide.parquet')
urbanlong = load('national/urban_population_panel_linked_long.parquet')
near = load('national/nearest_marketplaces_experimental.parquet')
wb = load('wb20261021_objects.parquet', source=True)
commerce = load('commerce_current.parquet', source=True)
key = 'source_record_id_2021'
ids = {r[key] for r in target}
check('target_unique_keys', len(target) == len(ids) == 144151 and None not in ids,
      {'rows': len(target), 'unique_source_ids': len(ids)})
check('target_unique_roots', len({r['root_accepted20261022'] for r in target}) == len(target),
      'One inter-census root per target row')
check('target_grain', all(r['population_scope_2021'] == 'settlement' and
      r['is_additive_settlement_record_2021'] is True and
      r['working_credit_present_2021'] is True for r in target),
      {'regions': len({r['region_2021'] for r in target}),
       'analysis_populations': counts(target, 'analysis_population')})
check('target_inventory_subset', ids <= {r[key] for r in inventory},
      {'allwide': len(allwide), 'physical2021': len(inventory), 'target': len(target)})
check('combined_preserves_target', len(combined) == len(target) and
      {r[key] for r in combined} == ids,
      'Exact target keys retained in platform comparison')
origin = {r[key]: r for r in target}
changed = sum(any(r[c] != origin[r[key]][c] for c in origin[r[key]]) for r in combined)
check('combined_preserves_target_values', changed == 0, {'changed_rows': changed})
status = counts(target, 'WB_evidence_status')
check('wb_status_counts', status == {
    'positive': 7991, 'zero_accepted_records_not_confirmed_absence': 134577,
    'unknown_no_commerce_bridge': 1583}, status)
bad_wb = [r[key] for r in target if
          (r['WB_evidence_status'] == 'positive' and not (r['WB_focus20261021_count'] > 0)) or
          (r['WB_evidence_status'] == 'zero_accepted_records_not_confirmed_absence' and
           r['WB_focus20261021_count'] != 0) or
          (r['WB_evidence_status'].startswith('unknown') and r['WB_focus20261021_count'] is not None)]
check('wb_status_count_consistency', not bad_wb, {'inconsistent_rows': len(bad_wb)})
pop_known = [r for r in target if r['population_2021'] is not None]
pop_unknown = [r for r in target if r['population_2021'] is None]
check('population_domain', all(r['population_2021'] >= 0 for r in pop_known),
      {'known': len(pop_known), 'unknown': len(pop_unknown),
       'zero': sum(r['population_2021'] == 0 for r in pop_known),
       'positive': sum(r['population_2021'] > 0 for r in pop_known),
       'sum_known': sum(r['population_2021'] for r in pop_known)})
warn('population_quality_missing_label',
     [{'id': r[key], 'name': r['name_2021'], 'region': r['region_2021'],
       'population_2021': r['population_2021']} for r in target
      if r['population_value_quality_2021'] is None])
check('coordinate_accounting', len(near) == 144149 and
      len({r['source_record_id'] for r in near}) == len(near) and
      {r['source_record_id'] for r in near} ==
      {r[key] for r in target if r['accepted_point_present_2021'] is True},
      {'near_rows': len(near), 'coordinate_missing': len(target) - len(near)})
check('distance_domain', all(math.isfinite(r['nearest_either_straight_km_experimental']) and
      0 <= r['nearest_either_straight_km_experimental'] <= r['nearest_linked_wb_straight_km'] + 1e-9
      for r in near), 'Combined nearest distance is finite, nonnegative and no larger than WB-only')
check('ozon_object_key', len(objects) == len({r['objectid'] for r in objects}) == 92503,
      {'objects': len(objects), 'raw_p': counts(objects, 'raw_p'),
       'snapshot': counts(objects, 'declared_snapshot')})
for radius in [1, 5, 10]:
    for kind, raw_p in [('pickup', '0'), ('locker', '1')]:
        expected = Counter(r[f'accepted_source_record_id_2021_{radius}km'] for r in objects
            if r[f'link_status_{radius}km'] == 'accepted_unique_exact_name_within_radius'
            and r['raw_p'] == raw_p
            and r[f'accepted_source_record_id_2021_{radius}km'] in ids)
        errors = sum(r[f'ozon_{kind}_inferred_accepted_{radius}km_count'] != expected[r[key]]
                     for r in combined)
        check(f'ozon_{kind}_{radius}km_reaggregation', errors == 0,
              {'count_mismatches': errors, 'objects_main_target': sum(expected.values()),
               'positive_target_settlements': len(expected)})
    accepted = [r for r in objects if r[f'link_status_{radius}km'] ==
                'accepted_unique_exact_name_within_radius']
    check(f'ozon_{radius}km_link_constraints', all(
        r[f'named_candidates_within_{radius}km_n'] == 1 and
        0 <= r[f'accepted_distance_WGS84_km_{radius}km'] <= radius for r in accepted),
        {'accepted': len(accepted), 'statuses': counts(objects, f'link_status_{radius}km')})
both = sum(r['WB_evidence_status'] == 'positive' and
           r['ozon_pickup_inferred_accepted_5km_count'] > 0 for r in combined)
check('both_platforms_5km', both == 6415, {'both_positive': both})
check('wb_single_snapshot', len({r['snapshot_date'] for r in wb}) == 1,
      {'rows': len(wb), 'snapshot': counts(wb, 'snapshot_date'),
       'opening_dates_nonnull': sum(r['opening_date'] is not None for r in wb),
       'actual_consumer_flows': counts(wb, 'actual_consumer_flows_observed')})
check('urban_unique_keys', len(urban) == len({r[key] for r in urban}) == 2253,
      {'urban_target': len(urban)})
complete = sum(all(r[f'population_{y}'] is not None for y in [2023, 2024, 2025]) for r in urban)
check('urban_completeness', complete == 2149 and all(
      r['complete_2023_2025'] == all(r[f'population_{y}'] is not None for y in [2023, 2024, 2025])
      for r in urban), {'complete2023_2025': complete, 'incomplete': len(urban) - complete})
check('urban_long_unique_keys', len(urbanlong) == len({(r[key], r['year']) for r in urbanlong}),
      {'observations': len(urbanlong), 'by_year': counts(urbanlong, 'year')})
check('urban_provenance', all(r['source_url'] and r['source_excel_row'] and r['source_filename']
      for r in urbanlong), 'Source URL, Excel row and file populated for each linked observation')
warn('urban_time_and_boundaries', {
    'boundary_comparability': counts(urban, 'boundary_comparability'),
    '2022_2023_growth_permitted': counts(urban, 'population_2022_2023_growth_permitted'),
    'causal_interpretation': counts(urban, 'causal_interpretation')})
history = json.loads((BASE / 'pilot/history_evidence.json').read_text())
events = history['events']
physical_series_flags = counts(commerce, 'commerce_physical_network_comparable_time_series_available')
historical = {
    'wb_current_snapshots': len({r['snapshot_date'] for r in wb}),
    'wb_opening_dates_nonnull': sum(r['opening_date'] is not None for r in wb),
    'ozon_current_snapshots': len({r['declared_snapshot'] for r in objects}),
    'pilot_presence_records': len(events),
    'pilot_precise_opening_records': sum(r.get('eligible_for_precise_treatment_date') is True for r in events),
    'commerce_rows': len(commerce),
    'physical_network_comparable_series_flag': physical_series_flags,
    'legal_retail_columns': [c for c in commerce[0] if c.startswith('econ_native_') and 'retail47' in c],
    'ozon_index_history_note': 'Local Git history records same-day repackaging on 2026-08-06, not repeated observation years.',
}
warn('history_not_ready_for_changes_or_causal_effects', historical)
warn('coverage_and_zero_interpretation',
     '81-region accepted census-source territory; federal cities separate. Unlinked/zero accepted objects do not establish absence. Ozon unofficial, dates differ; no platform market-share comparisons.')
warn('distance_interpretation',
     'Straight-line proximity to known linked points; not road time, observed choice, actual service catchment or improvement over time.')
peer_files = {}
for name in ['geography', 'demography']:
    directory = OUT.parent / name
    peer_files[name] = [str(p.relative_to(OUT.parent)) for p in directory.glob('*') if p.is_file()]
result = {
    'run_date': '2026-10-24', 'scope': 'Independent input audit, no external source acquisition',
    'checks': checks, 'summary': dict(Counter(c['status'] for c in checks)),
    'inputs': inputs, 'historical_inventory': historical, 'peer_files_at_run': peer_files,
    'allowed_claims': ['Current infrastructure configuration on accepted national frame',
        'Descriptive association with demographic history with quality filters',
        'Potential straight-line proximity to observed points'],
    'unsupported_claims': ['Causal effect of PVZ on population or retail',
        'Observed shopping-trip reduction or actual catchment expansion',
        'Historical redistribution based only on current snapshots',
        'Legal-entity counts interpreted as physical stores'],
}
(OUT / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
lines = ['Независимый аудит национального эмпирического блока — 24.10.2026',
         json.dumps(result['summary'], ensure_ascii=False),
         'Проверка воспроизводится audit.py; точные схемы и SHA256 входов в audit.json.', '']
for c in checks:
    lines.append(c['status'] + ' ' + c['name'] + ': ' + json.dumps(c['detail'], ensure_ascii=False))
lines.extend(['', 'Допустим современный описательный анализ и анализ селективности размещения.',
    'Изменения сети во времени и причинные эффекты пока не идентифицированы: нет сопоставимых повторных национальных срезов ПВЗ и физической торговли.',
    'Старые START_HERE/пилотные записки содержат архивные выводы о доступности данных; действующая рамка — national/RESULTS и исправленный RESEARCH_PLAN.',
    'Файлы других агентов на момент запуска: ' + json.dumps(peer_files, ensure_ascii=False),
    'Их содержательные выводы требуют отдельного итогового ревью после готовности.'])
(OUT / 'findings.txt').write_text('\n'.join(lines) + '\n')
print(json.dumps(result['summary']))
if any(c['status'] == 'FAIL' for c in checks):
    raise SystemExit('Audit failed; inspect audit.json')
