"""Apply the reviewed complete numbered-part union; keep individual records intact."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(review, selected, source_evidence, output):
    review, selected, source_evidence, output = map(Path, (review, selected, source_evidence, output))
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    receipt_path = review/'review_receipt.json'
    if sha(receipt_path) != 'a594efd1eb79d2f43058165d6517cb819ddd53da964807502cfcb4201977be31':
        raise ValueError('Whole-union independent review pin changed')
    point_path, member_path = review/'eligible_whole_union_point.csv', review/'whole_union_member_observations.csv'
    if sha(point_path) != 'f913b5a477ce22ada7da4b638d4847ec7c3f944d7bcade559e8bade659009657':
        raise ValueError('Reviewed whole-union point changed')
    if sha(member_path) != '2aa30feec142c69277dd22dd83699c3768a12aa9c834f219cb4976fdbea3c12a':
        raise ValueError('Reviewed member observations changed')
    point = list(csv.DictReader(point_path.open(newline='')))[0]
    members = list(csv.DictReader(member_path.open(newline='')))
    ids = [r['source_record_id'] for r in members]
    if len(ids) != 6 or len(set(ids)) != 6:
        raise ValueError('Expected six distinct original member observations')
    origin = Path(point['coordinate_origin_file'])
    if sha(origin) != point['coordinate_origin_sha256']:
        raise ValueError('Whole-place point origin changed')
    entity = json.loads(origin.read_text())['entities'][point['coordinate_source_entity']]
    claims = [r for r in entity['claims']['P625'] if r['id'] == point['coordinate_source_P625_GUID']]
    if len(claims) != 1:
        raise ValueError('Point statement missing or duplicated')
    coordinate = claims[0]['mainsnak']['datavalue']['value']
    coords = float(point['latitude']), float(point['longitude'])
    if (float(coordinate['latitude']), float(coordinate['longitude'])) != coords:
        raise ValueError('Point differs from literal P625 statement')
    con = duckdb.connect(config={'memory_limit': '256MB', 'threads': 1})
    con.read_parquet(str(selected)).create_view('selected')
    actual = {r[0]: r[1:] for r in con.execute('''SELECT source_record_id,census_year,
        population,settlement_name,settlement_type,population_scope,
        is_additive_settlement_record,population_value_quality FROM selected
        WHERE source_record_id IN (SELECT unnest(?))''', [ids]).fetchall()}
    evidence = {r[0]: json.loads(r[1]) for r in con.execute('''SELECT source_record_id,
        source_evidence_json FROM read_parquet(?) WHERE source_record_id IN
        (SELECT unnest(?))''', [str(source_evidence), ids]).fetchall()}
    if len(actual) != 6 or len(evidence) != 6:
        raise ValueError('Reviewed members are absent from canonical source layer')
    rows = []
    for year in [2002, 2010, 2021]:
        group = sorted([r for r in members if int(r['year']) == year], key=lambda r: r['part'])
        if [r['part'] for r in group] != ['1', '2']:
            raise ValueError('Exactly the two reviewed numbered parts are required')
        year_ids, values = [r['source_record_id'] for r in group], []
        for r in group:
            a, e = actual[r['source_record_id']], evidence[r['source_record_id']]
            if (a[0] != year or int(a[1]) != int(r['population_observed']) or
                a[2] != r['settlement_name'] or a[3] != 'село' or a[5] is not True or
                e.get('is_additive_settlement_record') is not True or e.get('is_federal_aggregate')):
                raise ValueError('Member source tuple or physical grain changed')
            # The 2002 snapshot omits population_scope. Its actual reviewed
            # literal rural rows establish grain; unknown convenience metadata
            # neither proves an aggregate nor grants general scope overrides.
            if a[4] not in (None, 'settlement'):
                raise ValueError('Member has contradictory population scope')
            values.append(int(a[1]))
        all_named = con.execute('''SELECT source_record_id FROM selected WHERE
            census_year=? AND region_norm='воронежская'
            AND settlement_name LIKE 'Новая Усмань%' ''', [year]).fetchall()
        if {r[0] for r in all_named} != set(year_ids):
            raise ValueError('Unreviewed competing whole-place or numbered-part source row')
        rows.append({'observation_id': point['union_id']+':'+str(year),
            'subject_qid': point['coordinate_source_entity'], 'place': 'Новая Усмань',
            'observation_year': year, 'population': sum(values),
            'component_source_record_ids_json': json.dumps(year_ids, ensure_ascii=False),
            'component_populations_json': json.dumps(values),
            'component_population_quality_json': json.dumps([actual[s][6] for s in year_ids], ensure_ascii=False),
            'projection_status': 'accepted_complete_observed_numbered_partition_projection',
            'population_is_derived_sum': True, 'population_exactness_asserted': year != 2010,
            'modern_boundary_harmonized': False, 'boundary_comparability_asserted': False,
            'ordinary_NP_three_census_identity_asserted': False,
            'individual_part_coordinate_admission': False,
            'latitude': coords[0], 'longitude': coords[1],
            'point_scope': 'whole exclusive union of numbered parts1+2 only',
            'coordinate_measurement_date_unknown': True,
            'retrospective_point_use_is_continuity_inference': True,
            'point_origin_file': str(origin), 'point_origin_sha256': sha(origin),
            'point_origin_locator': point['coordinate_origin_locator'],
            'native_code_binding_asserted': False})
    output.mkdir(parents=True, exist_ok=True)
    destination = output/'accepted_complete_partition_observations.parquet'
    pq.write_table(pa.Table.from_pylist(rows), destination, compression='zstd')
    readback = pq.read_table(destination).to_pylist()
    if readback != rows:
        raise ValueError('Whole-union Parquet readback differs from applied records')
    receipt = {'status': 'applied_independently_reviewed_complete_numbered_partition_series',
        'source_population_values_modified': False, 'new_ordinary_identity_edges': 0,
        'new_individual_part_point_uses': 0, 'years': [2002, 2010, 2021],
        'derived_population_by_year': {str(r['observation_year']): r['population'] for r in rows},
        'input_pins': {str(p): sha(p) for p in [selected, source_evidence, receipt_path,
                     point_path, member_path, origin]}, 'script_sha256': sha(__file__),
        'limitations': ['Complete observed publisher-part union, not reconstruction in modern boundaries.',
            '2010 protection/source-scope limits remain on both original components.',
            'The whole-place point does not admit coordinates for either individual part.',
            'Coverage unions existing member source IDs once; the derived sum is never added again.'],
        'outputs': {destination.name: sha(destination)}}
    (output/'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['review', 'selected', 'source-evidence', 'output']:
        p.add_argument('--'+name, required=True)
    a = p.parse_args()
    run(a.review, a.selected, a.source_evidence, a.output)
