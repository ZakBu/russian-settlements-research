"""Apply authorized federal territory references separately from atomic NP points.

The city continuity relation keeps changing population scopes visible; it does
not harmonize boundaries and never invents pre-2021 Russian Sevastopol records.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import pandas as pd


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_csv(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


def apply(frozen, stage, output, raw):
    frozen, stage, output, raw = map(Path, (frozen, stage, output, raw))
    selected = pd.read_parquet(frozen / 'selected_observations.parquet').set_index('source_record_id')
    evidence = {r.source_record_id: json.loads(r.source_evidence_json)
                for r in pd.read_parquet(frozen / 'source_evidence.parquet').itertuples()}
    points = read_csv(stage / 'federal_territory_reference_bindings.csv')
    chains = read_csv(stage / 'federal_territorial_chain_coverage_ids.csv')
    assert len(points) == 6 and len({r['source_record_id'] for r in points}) == 6
    expected = {('2002', 'Санкт-Петербург'), ('2010', 'Москва'),
                ('2010', 'Санкт-Петербург'), ('2021', 'Москва'),
                ('2021', 'Санкт-Петербург'), ('2021', 'Севастополь')}
    assert {(r['census_year'], r['city_name']) for r in points} == expected
    inputs = {}
    witnesses = {}
    for r in points:
        sid = r['source_record_id']; s = selected.loc[sid]
        assert int(s.census_year) == int(r['census_year'])
        assert int(s.population) == int(r['source_population'])
        assert s.settlement_name == r['city_name']
        assert evidence[sid]['is_federal_aggregate'] is True
        for path, expected_sha in [(Path(r['population_source_file']), r['population_source_sha256']),
                (raw / 'wikidata_truthy_claims' / r['coordinate_claim_source_file'], r['coordinate_claim_source_sha256'])]:
            if str(path) not in inputs:
                inputs[str(path)] = sha(path)
            assert inputs[str(path)] == expected_sha
        path = raw / 'wikidata_truthy_claims' / r['coordinate_claim_source_file']
        witnesses.setdefault(path, {})[int(r['coordinate_claim_source_line'])] = r
        assert -90 <= float(r['latitude']) <= 90 and -180 <= float(r['longitude']) <= 180
        assert r['point_role'] == 'territory_reference'
        assert r['object_scope'] == 'federal_city_territory'
    for path, wanted in witnesses.items():
        with gzip.open(path, 'rt') as stream:
            for i, line in enumerate(stream, 1):
                if i in wanted:
                    r = wanted[i]
                    # Retain the raw record; exact identity/property/value must
                    # occur in the pinned claim, not merely in producer output.
                    assert r['wikidata_qid'] in line and 'P625' in line
                    assert r['coordinate_raw_value'] in line
        assert max(wanted) <= i
    accepted_chains = []
    for c in chains:
        ids = json.loads(c['source_record_ids_json'])
        assert all(sid in selected.index for sid in ids)
        years = [int(selected.loc[sid, 'census_year']) for sid in ids]
        assert len(set(years)) == len(years)
        if c['city'] == 'Севастополь':
            assert years == [2021]
            c['chain_status'] = 'outside_2002_2010_russian_census_scope'
        else:
            assert set(years) == {2002, 2010, 2021}
            assert all(selected.loc[sid, 'settlement_name'] == c['city'] for sid in ids)
            c['chain_status'] = 'continuing_city_three_observed_censuses_changing_population_scope'
        c['decision_status'] = 'checked_rule_accepted'
        c['population_boundary_comparability_asserted'] = False
        c['atomic_same_place_edge'] = False
        accepted_chains.append(c)
    for r in points:
        r['admission_status'] = 'reviewed_territory_reference_accepted'
        r['review_basis'] = 'user_authorized_scope; frozen_grain_audit; exact_raw_claim_and_source_hash_replay'
        r['population_boundary_comparability_asserted'] = False
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(points).to_parquet(output / 'accepted_territory_reference_points.parquet', index=False)
    pd.DataFrame(accepted_chains).to_parquet(output / 'accepted_typed_city_continuity.parquet', index=False)
    receipt = {'status': 'applied_separate_typed_territorial_layer', 'territory_points': len(points),
               'three_census_city_chains': 2, 'outside_older_census_city': 1,
               'source_file_hashes': inputs, 'atomic_point_uses_or_edges_modified': False,
               'additivity': 'parent territory replaces covered children in operational metric; NP metrics stay separate',
               'script_sha256': sha(__file__),
               'inputs': {str(frozen / n): sha(frozen / n) for n in
                          ['selected_observations.parquet', 'source_evidence.parquet']},
               'stage_inputs': {str(stage / n): sha(stage / n) for n in
                                ['federal_territory_reference_bindings.csv', 'federal_territorial_chain_coverage_ids.csv']}}
    receipt['outputs'] = {p.name: sha(p) for p in output.glob('*.parquet')}
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--frozen', required=True); p.add_argument('--stage', required=True)
    p.add_argument('--output', required=True); p.add_argument('--raw', required=True)
    a = p.parse_args()
    print(json.dumps(apply(a.frozen, a.stage, a.output, a.raw), ensure_ascii=False, indent=2))
