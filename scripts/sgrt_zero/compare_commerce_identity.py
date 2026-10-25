#!/usr/bin/env python3
"""Read-only comparison of two normalizations of the same frozen commerce data.

--before and --after are commerce directories containing sites.parquet,
sites_wb_current.parquet, and yandex/ and fivepost/ subdirectories. This checks
identity-only corrections; added source rows or newly assigned identities fail.
It does not rebuild data, verify actual operation, or establish administrative
boundaries. Optional --fivepost-raw supplies the frozen public-widget JSON.gz
for the observed Selkovo counterexample. Specific dated controls are skipped
explicitly when absent from a different source snapshot.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.sgrt_mass.match import normalize_name, normalize_region

ROLES = {
    'baseline': 'sites.parquet', 'wildberries': 'sites_wb_current.parquet',
    'yandex': 'yandex/sites_yandex_current.parquet',
    'fivepost': 'fivepost/sites_5post_current.parquet',
    'grocery_host': 'fivepost/sites_grocery_current_host_proxy.parquet',
}
RAW_FIELDS = ['site_lat', 'site_lon', 'supply_status',
              'default_external_seed_eligible', 'source_id', 'source_year',
              'source_snapshot', 'source_address_locality',
              'source_region_literal', 'activity_address', 'tags_json']
NESTED = [
    ('wildberries', 'wb:123582', 'зеленоград'),
    ('baseline', 'wb:123582', 'зеленоград'),
    ('baseline', 'wb:397401', 'домодедово'),
    *[('baseline', 'osm:node:'+s, 'пушкин') for s in
      ['1115483257', '7413655237', '7580415564']],
    *[('yandex', 'yandex:'+s, 'зеленоград') for s in [
      '0193cfba97f57502b7c4864fd0ddc863', '01976dd446a4747ba7addf81a189ea90',
      '019f28f839bd7748a56a0771d0701e8b', '01a0f89c1c5774459fdfe3c79dce2507',
      '322cedd3-c4d8-4a1d-9326-b91e41900038',
      '74fbeba9-e1b4-4d0c-b45c-ac8b9035f88c',
      'ede0f165-30d8-4eab-9afe-58c6ee5a81b8']],
]
STREETS = ['wb:107220', 'wb:107393', 'wb:108372', 'wb:110878',
           'wb:120993', 'wb:50210725']
SELKOVO = '5post:0196850f545072ebbd22be7a9293d9b7'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def same(a, b):
    return a.eq(b) | (a.isna() & b.isna())


def city_literal(value):
    return re.sub(r'^(?:город|г)\s+|\s+(?:город|г)$', '',
                  normalize_name(value)).strip()


def compare(before, after, reference, fivepost_raw=None):
    ref = pd.read_parquet(reference)
    cities = ref[ref.source_record_id.notna() & ref.region.isin(
        ['москва', 'санкт петербург', 'севастополь'])].set_index('source_record_id')
    city_ids = set(cities.index)
    known_regions = set(ref.region_norm.dropna())
    result = {'comparison_code_sha256': sha(__file__),
              'old_data_root': str(before), 'new_data_root': str(after),
              'reference_path': str(reference), 'reference_sha256': sha(reference),
              'all_five_tables': {}, 'failures': [],
              'literal_identity_is_not_independent_administrative_geofence_verification': True}
    frames = {}
    for name, relative in ROLES.items():
        a, b = (pd.read_parquet(root / relative) for root in [before, after])
        frames[name] = b
        keys = ['provider_id', 'service_code']
        if a.duplicated(keys).any() or b.duplicated(keys).any():
            raise ValueError('Nonunique provider/service keys: '+name)
        x = a.merge(b, on=keys, suffixes=('_old', '_new'), how='outer',
                    indicator=True, validate='one_to_one')
        fields = [c for c in RAW_FIELDS if c in a and c in b]
        missing_fields = sorted(set(c for c in RAW_FIELDS if c in a) - set(b))
        diff = {c: int((~same(x[c+'_old'], x[c+'_new'])).sum()) for c in fields}
        change = ~same(x.source_record_id_old, x.source_record_id_new)
        changed = x[change]
        retained = b[b.source_record_id.isin(city_ids)]
        locality_bad, region_bad = [], []
        for row in retained.to_dict('records'):
            expected = normalize_name(cities.loc[row['source_record_id'], 'name'])
            region = normalize_region(cities.loc[row['source_record_id'], 'region'])
            tags = json.loads(row['tags_json']) if isinstance(row.get('tags_json'), str) else {}
            localities = [city_literal(v) for v in
                          [row.get('source_address_locality'), tags.get('addr:city'), tags.get('addr:place')]
                          if v is not None and pd.notna(v) and str(v).strip()]
            if any(v != expected for v in localities):
                locality_bad.append(row['provider_id'])
            regions = [normalize_region(v) for v in
                       [row.get('source_region_literal'), tags.get('addr:state')]
                       if v is not None and pd.notna(v) and str(v).strip()]
            if any(v in known_regions and v != region for v in regions):
                region_bad.append(row['provider_id'])
        item = {'old_rows': len(a), 'new_rows': len(b),
                'unmatched_keys': int(x._merge.ne('both').sum()),
                'raw_fields_or_eligibility_changed': diff,
                'required_raw_fields_missing_after': missing_fields,
                'identity_changes': int(change.sum()),
                'noncity_known_identity_changes': int((change & x.source_record_id_old.notna()
                    & ~x.source_record_id_old.isin(city_ids)).sum()),
                'changed_to_another_identity': int(changed.source_record_id_new.notna().sum()),
                'retained_federal_city_rows': len(retained),
                'retained_structured_locality_contradictions': locality_bad,
                'retained_explicit_region_contradictions': region_bad,
                'old_sha256': sha(before / relative), 'new_sha256': sha(after / relative)}
        result['all_five_tables'][name] = item
        if (any(diff.values()) or missing_fields or item['unmatched_keys']
                or item['noncity_known_identity_changes']
                or item['changed_to_another_identity'] or locality_bad or region_bad):
            result['failures'].append(name)
    controls = []
    for role, pid, place in NESTED:
        q = frames[role][frames[role].provider_id.eq(pid)]
        control = {'family': role, 'provider_id': pid, 'nested_name': place,
                   'present': len(q) == 1,
                   'held_unknown': bool(len(q) == 1 and q.source_record_id.isna().all())}
        controls.append(control)
        if control['present'] and not control['held_unknown']:
            result['failures'].append('nested_control:'+pid)
    result['clear_nested_locality_controls'] = controls
    result['all_13_nested_controls_held'] = (len(controls) == 13 and
        all(c['present'] and c['held_unknown'] for c in controls))
    street_controls = frames['wildberries'][frames['wildberries'].provider_id.isin(STREETS)]
    gate = frames['baseline'][frames['baseline'].provider_id.eq('osm:node:7647631664')]
    result['six_numbered_city_street_controls_retained'] = bool(
        len(street_controls) == 6 and street_controls.source_record_id.isin(city_ids).all())
    result['structured_Moscow_gate_control_retained'] = bool(
        len(gate) == 1 and gate.source_record_id.isin(city_ids).all())
    if len(street_controls) and not street_controls.source_record_id.isin(city_ids).all():
        result['failures'].append('numbered_street_control')
    if len(gate) and not gate.source_record_id.isin(city_ids).all():
        result['failures'].append('gate_control')
    q = frames['fivepost'][frames['fivepost'].provider_id.eq(SELKOVO)]
    sel = {'present': len(q) == 1}
    if len(q) == 1:
        row = q.iloc[0]
        sel.update(corrected_identity=None if pd.isna(row.source_record_id) else row.source_record_id,
                   corrected_identity_basis=row.np_identity_basis,
                   physical_point_still_observed=bool(row.supply_status == 'observed'),
                   coordinates_after=[row.site_lat, row.site_lon],
                   source_address_locality=row.source_address_locality,
                   source_region_literal=row.source_region_literal)
        if pd.notna(row.source_record_id) or row.supply_status != 'observed':
            result['failures'].append('selkovo_control')
        if fivepost_raw:
            with gzip.open(fivepost_raw, 'rt', encoding='utf-8') as f:
                raw = json.load(f)
            source = next(p for p in raw['points'] if str(p['id']) == SELKOVO.split(':', 1)[1])
            sel.update(raw_source_path=str(fivepost_raw), raw_source_sha256=sha(fivepost_raw),
                       raw_address=source['address'], raw_position=source['position'],
                       physical_coordinates_unchanged=bool(row.site_lat == source['position']['latitude']
                           and row.site_lon == source['position']['longitude']))
            if not sel['physical_coordinates_unchanged']:
                result['failures'].append('selkovo_raw_coordinates')
    result['selkovo_direct_raw_source_control'] = sel
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['before', 'after', 'reference', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--fivepost-raw', type=Path)
    args = parser.parse_args()
    result = compare(args.before, args.after, args.reference, args.fivepost_raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'output': str(args.output), 'failures': result['failures'],
                      'identity_changes': {k: v['identity_changes'] for k, v in result['all_five_tables'].items()}}))
    return bool(result['failures'])


if __name__ == '__main__':
    raise SystemExit(main())
