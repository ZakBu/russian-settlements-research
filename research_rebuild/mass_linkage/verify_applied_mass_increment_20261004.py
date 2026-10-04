"""Independent compact readback of a pinned mass increment; no admissions."""
from pathlib import Path
import argparse
import hashlib
import json
from collections import defaultdict
import duckdb


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def run(application, output):
    application = Path(application)
    receipt = json.loads(application.read_text())
    root = application.parent
    inputs = receipt['inputs']
    pins = [inputs['frozen']['selected'], inputs['base']['graph'], inputs['base']['points']]
    for pin in pins:
        assert sha(pin['path']) == pin['sha256'], pin['path']
    for name, digest in receipt['outputs'].items():
        assert sha(root / name) == digest, name
    con = duckdb.connect(config={'threads': 1, 'memory_limit': '1GB'})
    views = {'selected': pins[0]['path'], 'old_graph': pins[1]['path'],
             'old_points': pins[2]['path'], 'graph': root / 'accepted_identity_edges.parquet',
             'points': root / 'accepted_point_uses.parquet'}
    for name, path in views.items():
        con.read_parquet(str(path)).create_view(name)
    checks = {}
    for old, new, key, fields in [
        ('old_graph', 'graph', 'decision_id', ['from_source_record_id', 'to_source_record_id',
         'from_year', 'to_year', 'relation', 'decision_status', 'selection_projection_status']),
        ('old_points', 'points', 'target_source_record_id', ['latitude', 'longitude',
         'coordinate_admission_status', 'point_origin_file', 'point_origin_sha256', 'point_origin_locator']),
    ]:
        conditions = ' or '.join(f'a."{f}" is distinct from b."{f}"' for f in fields)
        changed = con.execute(f'select count(*) from {old} a left join {new} b '
                              f'on a."{key}"=b."{key}" where b."{key}" is null or {conditions}').fetchone()[0]
        assert changed == 0, (old, changed)
        checks[old + '_scientific_fields_changed_or_missing'] = changed
    assert con.execute('select count(*)-count(distinct target_source_record_id) from points').fetchone()[0] == 0
    assert con.execute('select count(*) from points where latitude is null or longitude is null '
                       'or not isfinite(latitude) or not isfinite(longitude) '
                       'or abs(latitude)>90 or abs(longitude)>180').fetchone()[0] == 0
    # DFS is independent of the admission driver's union/find component construction.
    years = dict(con.execute('select source_record_id,census_year from selected').fetchall())
    adjacency = defaultdict(set)
    for a, b, ay, by in con.execute('select from_source_record_id,to_source_record_id,from_year,to_year from graph').fetchall():
        assert years[a] == int(ay) and years[b] == int(by) and int(ay) != int(by)
        adjacency[a].add(b)
        adjacency[b].add(a)
    admitted = {r[0] for r in con.execute('select target_source_record_id from points').fetchall()}
    full, visited = set(), set()
    components = 0
    for start in adjacency:
        if start in visited:
            continue
        stack, members = [start], []
        visited.add(start)
        while stack:
            member = stack.pop()
            members.append(member)
            for other in adjacency[member]:
                if other not in visited:
                    visited.add(other)
                    stack.append(other)
        member_years = [years[m] for m in members]
        assert len(set(member_years)) == len(member_years), members
        if set(member_years) == {2002, 2010, 2021}:
            full.update(members)
            components += 1
    coverage = json.loads((root / 'coverage.json').read_text())
    counts = defaultdict(lambda: {'rows': 0, 'known_population': 0})
    for sid, year, population in con.execute('select source_record_id,census_year,population from selected').fetchall():
        if sid in full and sid in admitted:
            counts[year]['rows'] += 1
            counts[year]['known_population'] += int(population or 0)
    for metric in coverage['census_metrics']:
        expected = metric['axes']['joint_admitted_coordinate_and_full_chain']
        assert counts[metric['year']] == {k: expected[k] for k in ['rows', 'known_population']}
    assert components == receipt['full_census_components']
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    assert not output.exists(), 'Readback receipt must be immutable'
    result = {'status': 'independent_DFS_and_scientific_field_readback_passed',
              'application_receipt': str(application), 'application_receipt_sha256': sha(application),
              'script_sha256': sha(__file__), 'full_census_components': components,
              'NP_joint_counts': dict(counts), 'baseline_checks': checks,
              'point_targets_unique_finite_geographic_range': True,
              'scope': 'Scientific fields listed in code compared; arbitrary optional proof columns are not exhaustively compared. Federal typed continuity remains separately reviewed.'}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--application', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.application, args.output)
