"""Correct accepted decision labels without changing identities or coordinates."""
from pathlib import Path
import hashlib
import json
import shutil
import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import gc

BASE = Path('/workspace/settlements-work/continuation_20261004')
INPUT = BASE / 'accepted_mass_fifth_with_context'
OUTPUT = BASE / 'accepted_mass_fifth_canonical_v3'
PREVIOUS = BASE / 'accepted_mass_rule_corrections_origin_corrected'
GRAPH_SHA = '4d115e06d5a4f1dfecf50d87a945b32664458c4c7e615618cf8b1481e295326a'
POINT_SHA = '19793a3d5440dd54866355078c7f623f13771c5ec282b489cb5a0d062842052d'
CORRIDOR_REVIEW_SHA = '63dbcb6a2b1583e8ddd78851d0d331255178bedaefaa89feb67dd595f09f842e'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    graph, points = INPUT / 'accepted_identity_edges.parquet', INPUT / 'accepted_point_uses.parquet'
    assert sha(graph) == GRAPH_SHA and sha(points) == POINT_SHA
    receipt = json.loads((INPUT / 'receipt.json').read_text())
    assert receipt['inputs']['identity']['identity:1']['review_receipt_sha256'] == CORRIDOR_REVIEW_SHA
    assert sha(receipt['inputs']['identity']['identity:1']['review_receipt']) == CORRIDOR_REVIEW_SHA
    assert sha(PREVIOUS / 'accepted_point_uses.parquet') == receipt['inputs']['base']['points']['sha256']
    con = duckdb.connect(config={'threads': 1, 'memory_limit': '3GB'})
    con.read_parquet(str(graph)).create_view('g')
    con.read_parquet(str(points)).create_view('p')
    con.read_parquet(str(PREVIOUS / 'accepted_point_uses.parquet')).project('target_source_record_id').create_view('previous_points')
    bad = con.execute("SELECT count(*) FROM g WHERE relation<>'same_place' AND NOT (relation='same_place_candidate' AND integration_rule_family='dependency_aware_three_census_corridor_v1' AND decision_status='checked_rule_accepted' AND admission_status='checked_rule_accepted' AND identity_review_receipt_sha256=?)", [CORRIDOR_REVIEW_SHA]).fetchone()[0]
    assert bad == 0
    assert con.execute("SELECT count(*) FROM g WHERE relation='same_place_candidate'").fetchone()[0] == 114
    OUTPUT.mkdir(parents=True, exist_ok=False)
    # Arrow edits only two admission metadata columns, avoiding DuckDB's
    # pathological wide-table expression COPY observed in the failed v1 run.
    table = pq.read_table(graph)
    relation = table['relation']
    alias = pc.equal(relation, 'same_place_candidate')
    table = table.set_column(table.schema.get_field_index('relation'), 'relation', pc.if_else(alias, 'same_place', relation))
    before = pa.array([value if value == 'same_place_candidate' else None for value in relation.to_pylist()], type=relation.type)
    name = 'source_candidate_relation_before_application'
    if name in table.column_names:
        # Baseline may already preserve other pre-admission labels.
        before = pc.if_else(alias, relation, table[name])
        table = table.set_column(table.schema.get_field_index(name), name, before)
    else:
        table = table.append_column(name, before)
    table.validate(full=True)
    pq.write_table(table, OUTPUT / graph.name, compression='zstd')
    del table, relation, before, alias
    gc.collect()
    table = pq.read_table(points)
    previous_ids = pq.read_table(PREVIOUS / points.name, columns=['target_source_record_id'])['target_source_record_id']
    new = pc.invert(pc.is_in(table['target_source_record_id'], value_set=previous_ids))
    assert pc.sum(pc.cast(new, pa.int64())).as_py() == 221
    name = 'source_candidate_only_before_application'
    before = pc.if_else(new, pc.coalesce(table[name], table['candidate_only']), table[name])
    table = table.set_column(table.schema.get_field_index(name), name, before)
    table = table.set_column(table.schema.get_field_index('candidate_only'), 'candidate_only', pc.if_else(new, 'False', table['candidate_only']))
    table.validate(full=True)
    pq.write_table(table, OUTPUT / points.name, compression='zstd')
    del table, previous_ids, new, before
    gc.collect()
    for name in ('coverage.json', 'joint_residual.parquet', 'point_continuity_holds.csv'):
        shutil.copyfile(INPUT / name, OUTPUT / name)
    g2, p2 = OUTPUT / graph.name, OUTPUT / points.name
    assert con.execute('SELECT count(*) FROM g').fetchone()[0] == 327745
    assert con.execute('SELECT count(*) FROM read_parquet(?)', [str(g2)]).fetchone()[0] == 327745
    assert con.execute('SELECT count(*) FROM read_parquet(?) n JOIN g o USING(decision_id) WHERE n.from_source_record_id IS DISTINCT FROM o.from_source_record_id OR n.to_source_record_id IS DISTINCT FROM o.to_source_record_id', [str(g2)]).fetchone()[0] == 0
    assert con.execute('SELECT count(*) FROM read_parquet(?) n JOIN p o USING(target_source_record_id) WHERE n.latitude IS DISTINCT FROM o.latitude OR n.longitude IS DISTINCT FROM o.longitude OR n.point_origin_sha256 IS DISTINCT FROM o.point_origin_sha256 OR n.coordinate_admission_status IS DISTINCT FROM o.coordinate_admission_status', [str(p2)]).fetchone()[0] == 0
    assert con.execute('SELECT count(*) FROM p').fetchone()[0] == con.execute('SELECT count(*) FROM read_parquet(?)', [str(p2)]).fetchone()[0]
    out = {'status': 'exact_scope_admission_label_correction_no_new_scientific_admissions',
           'parent_application_receipt': {'path': str(INPUT / 'receipt.json'), 'sha256': sha(INPUT / 'receipt.json')},
           'parent_graph_sha256': GRAPH_SHA, 'parent_point_sha256': POINT_SHA,
           'accepted_relation_aliases_normalized': 114,
           'newly_admitted_point_rows_with_explicit_candidate_only_false': 221,
           'identities_coordinates_origin_hashes_and_coverage_preserved': True,
           'source_labels_preserved_in_before_application_fields': True,
           'script_sha256': sha(__file__),
           'outputs': {p.name: sha(p) for p in OUTPUT.iterdir() if p.is_file()}}
    (OUTPUT / 'receipt.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
