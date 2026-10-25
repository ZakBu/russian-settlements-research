#!/usr/bin/env python3
"""Read-only audit of commerce_match_preview.py's whole-pool component preview.

Checks the same frozen raw rows against --before (a commerce directory),
positive raw-text locality witnesses, unique candidates, the existing 10 km
identity radius, clear place types and explicit source regions/countries.
This is source-consistency verification, not observed service use, administrative
boundary verification or proof that every unbound point lacks a local function.
No model, input table, assignment, radius or service eligibility is changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.sgrt_mass.match import normalize_name, normalize_region, norm

ROLES = {'wildberries': 'sites_wb_current.parquet',
         'yandex': 'yandex/sites_yandex_current.parquet',
         'fivepost': 'fivepost/sites_5post_current.parquet'}
RAW_FIELDS = ['site_lat', 'site_lon', 'supply_status',
              'default_external_seed_eligible', 'source_address_locality',
              'source_region_literal', 'activity_address', 'source_country_literal',
              'tags_json', 'source_id', 'source_year', 'source_snapshot']
CLEAR_TYPES = {'city': 'город', 'village': 'деревня', 'selo': 'село',
               'khutor': 'хутор', 'stanitsa': 'станица', 'aul': 'аул'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def audit(preview, before, reference):
    ref = pd.read_parquet(reference)
    ref = ref[ref.source_record_id.notna()].set_index('source_record_id')
    cities = set(ref[ref.region.isin(['москва', 'санкт петербург', 'севастополь'])].index)
    regions = set(ref.region_norm.dropna())
    result = {'phase': 'whole_pool_component_parser_source_evidence',
              'audit_code_sha256': sha(__file__), 'preview_path': str(preview),
              'before_path': str(before), 'reference_path': str(reference),
              'reference_sha256': sha(reference),
              'existing_identity_match_radius_km': 10.,
              'datasets': {}, 'failures': []}
    summary = preview / 'summary.json'
    if summary.exists():
        result['preview_summary_sha256'] = sha(summary)
        result['source_parser_sha256'] = json.loads(summary.read_text()).get('parser_sha256')
    frames = {}
    for family, relative in ROLES.items():
        source = preview / (family+'_all_identity_comparisons.parquet')
        d, a = pd.read_parquet(source), pd.read_parquet(before / relative)
        frames[family] = d
        m = a.merge(d, on=['provider_id', 'service_code'], how='outer',
                    suffixes=('_old', '_new'), indicator=True, validate='one_to_one')
        fields = [c for c in RAW_FIELDS if c in a and c in d]
        missing = sorted(set(c for c in RAW_FIELDS if c in a) - set(d))
        differences = {c: int((~(m[c+'_old'].eq(m[c+'_new']) |
            (m[c+'_old'].isna() & m[c+'_new'].isna()))).sum()) for c in fields}
        k = d[d.source_record_id.notna() & ~d.source_record_id.isin(cities)]
        bad_literal, bad_region, bad_type = [], [], []
        for row in k.to_dict('records'):
            target = ref.loc[row['source_record_id']]
            name = normalize_name(target['name'])
            clues = json.loads(row['locality_witnesses_json'])
            raw_present = all(c['raw'] == norm(row.get('source_address_locality', ''))
                              or c['raw'] in norm(row['activity_address']) for c in clues)
            literal = any(c['name'] == name or (c['typed'] and bool(re.fullmatch(
                re.escape(name)+r'\s*(?:(?:дом|д|корпус|корп|к)\s*)?\d.*',
                c['name']))) for c in clues)
            if not (raw_present and literal):
                bad_literal.append(row['provider_id'])
            state = row.get('source_region_literal')
            region = normalize_region(state) if pd.notna(state) else ''
            if region in regions and region != normalize_region(target['region']):
                bad_region.append(row['provider_id'])
            for clue in clues:
                if (clue['type'] in CLEAR_TYPES and norm(target['settlement_type_2021'])
                        and norm(target['settlement_type_2021']) != CLEAR_TYPES[clue['type']]):
                    bad_type.append(row['provider_id'])
        observed = d[d.supply_status.eq('observed')]
        controls = d[d.source_address_locality.fillna('').isin(['Краснодар', 'Краснодар г'])
                     & d.previous_reference_name.eq('Краснодарский')]
        item = {'rows': len(d), 'unmatched_source_keys': int(m._merge.ne('both').sum()),
                'raw_fields_changes': differences, 'missing_raw_fields_after': missing,
                'ordinary_bound_rows': len(k),
                'ordinary_without_unique_candidate': int(k.np_identity_candidate_count.ne(1).sum()),
                'ordinary_beyond_unchanged_10km': int(k.linked_distance_km.gt(10+1e-8).sum()),
                'ordinary_nearest_only': int(k.identity_is_nearest_only.fillna(False).sum()),
                'ordinary_without_actual_literal_witness': bad_literal,
                'ordinary_explicit_region_conflicts': bad_region,
                'ordinary_clear_type_conflicts': bad_type,
                'observed_foreign_or_missing_country': int((~observed.source_country_literal.map(norm)
                    .isin(['ru', 'russia', 'россия', 'российская федерация'])).sum()),
                'Krasnodar_control': controls.new_reference_name.fillna('<unknown>').value_counts().to_dict(),
                'before_sha256': sha(before / relative), 'preview_sha256': sha(source)}
        result['datasets'][family] = item
        if (any(differences.values()) or missing or item['unmatched_source_keys']
                or item['ordinary_without_unique_candidate'] or item['ordinary_beyond_unchanged_10km']
                or item['ordinary_nearest_only'] or bad_literal or bad_region or bad_type
                or item['observed_foreign_or_missing_country']):
            result['failures'].append(family)
    controls = frames['wildberries']
    controls = controls[controls.provider_id.isin(['wb:217229', 'wb:50164835'])]
    result['true_typed_Krasnodarsky_village_controls_preserved'] = bool(
        len(controls) == 2 and controls.new_reference_name.eq('Краснодарский').all())
    finer = frames['fivepost']
    finer = finer[finer.provider_id.eq('5post:01963d2f8d1d753495b250702dfdd7a2')]
    result['finer_Borsheva_over_coarse_Ramenskoye_control'] = bool(
        len(finer) == 1 and finer.new_reference_name.eq('Боршева').all())
    # These named controls belong to the frozen October 2026 source corpus.
    if len(controls) and not controls.new_reference_name.eq('Краснодарский').all():
        result['failures'].append('typed_Krasnodarsky_controls')
    if len(finer) and not finer.new_reference_name.eq('Боршева').all():
        result['failures'].append('typed_Borsheva_control')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['preview', 'before', 'reference', 'output']:
        p.add_argument('--'+name, type=Path, required=True)
    args = p.parse_args()
    result = audit(args.preview, args.before, args.reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'output': str(args.output), 'failures': result['failures']}))
    return bool(result['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
