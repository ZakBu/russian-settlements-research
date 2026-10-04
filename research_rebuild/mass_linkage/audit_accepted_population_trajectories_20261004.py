"""Flag population discontinuities in accepted components without changing data."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import duckdb

from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selected', type=Path, required=True)
    p.add_argument('--graph', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    con = duckdb.connect(config={'memory_limit': '256MB', 'threads': 1})
    records = {r[0]: dict(zip(['source_record_id', 'year', 'name', 'type', 'region',
                              'population', 'population_quality'], r))
               for r in con.execute('''SELECT source_record_id,census_year,settlement_name,
               settlement_type,region_norm,population,population_value_quality
               FROM read_parquet(?)''', [str(a.selected)]).fetchall()}
    adjacency = defaultdict(set)
    for x, y, status in con.execute('''SELECT from_source_record_id,to_source_record_id,
                                      decision_status FROM read_parquet(?)''', [str(a.graph)]).fetchall():
        if status not in ACCEPTED_EDGE_STATUSES:
            raise ValueError(f'Unexpected graph decision status: {status}')
        if x not in records or y not in records:
            raise ValueError('Graph endpoint is absent from selected census observations')
        adjacency[x].add(y)
        adjacency[y].add(x)
    seen, flagged, counters = set(), [], Counter()
    for start in adjacency:
        if start in seen:
            continue
        seen.add(start)
        stack, members = [start], []
        while stack:
            sid = stack.pop()
            members.append(records[sid])
            for other in adjacency[sid]:
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        members.sort(key=lambda r: r['year'])
        if len({r['year'] for r in members}) != len(members):
            raise ValueError('Accepted component has two observations of the same census year')
        counters['components_checked'] += 1
        for old, new in combinations(members, 2):
            label = f"{old['year']}_{new['year']}"
            counters[f'pairs_{label}'] += 1
            first, last = old['population'], new['population']
            if first is None or last is None:
                counters['unknown_population_pairs'] += 1
                continue
            delta = last-first
            growth = 100*delta/first if first > 0 else None
            reasons = []
            if first == 0 and last > 0:
                counters['positive_from_zero_pairs'] += 1
                if last >= 1000:
                    reasons.append('zero_to_at_least_1000; percentage_undefined')
            if growth is not None and growth >= 300:
                reasons.append('growth_at_least_300_percent')
            if first > 0 and last == 0 and first >= 1000:
                reasons.append('at_least_1000_to_zero')
            if growth is not None and abs(delta) >= 1000 and (growth >= 100 or growth <= -75):
                reasons.append('large_absolute_and_relative_change')
            if not reasons:
                continue
            counters[f'flagged_pairs_{label}'] += 1
            quality = f"{old['population_quality']}|{new['population_quality']}"
            flagged.append({'from_source_record_id': old['source_record_id'],
                'to_source_record_id': new['source_record_id'], 'from_year': old['year'],
                'to_year': new['year'], 'old_name': old['name'], 'new_name': new['name'],
                'old_type': old['type'], 'new_type': new['type'], 'region': new['region'],
                'old_population': first, 'new_population': last, 'absolute_change': delta,
                'growth_percent': growth, 'protected_source_in_pair': 'protected' in quality,
                'old_population_quality': old['population_quality'],
                'new_population_quality': new['population_quality'],
                'flag_reasons': '|'.join(reasons), 'decision': 'diagnostic_requires_explanation_not_error_admission'})
    flagged.sort(key=lambda r: (-abs(r['absolute_change']), r['from_source_record_id'], r['to_year']))
    csv_path = a.output/'flagged_population_changes.csv'
    columns = list(flagged[0]) if flagged else ['from_source_record_id', 'to_source_record_id']
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(flagged)
    sha = lambda path: hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
    result = {'status': 'diagnostic_only_no_data_or_identity_changes', 'counts': dict(counters),
        'flagged_pairs': len(flagged), 'flagged_pairs_with_protected_source': sum(r['protected_source_in_pair'] for r in flagged),
        'rules': 'Flag >=300% growth, zero→>=1000 (undefined percentage), >=1000→zero, or absolute change>=1000 with >=100% growth/75% decline.',
        'limitations': ['Population changes can be real or reflect boundaries, source protection, status or matching errors.',
                       'Flags do not establish an error or justify altering source populations.',
                       'Only accepted ordinary identity components are assessed; typed event and territorial paths require their own scope-aware review.'],
        'inputs': {str(path): sha(path) for path in [a.selected, a.graph]},
        'outputs': {csv_path.name: sha(csv_path)}}
    (a.output/'receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
