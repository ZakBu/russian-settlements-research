"""Adopt independently replayed auxiliary primary dates without guessing F-row bindings."""
import json
from pathlib import Path
import duckdb
from research_rebuild.mass_linkage.apply_reviewed_large_inclusion_scope_20261004 import sha
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES


def run(folder, output, selected, graph, points):
    folder, output = Path(folder), Path(output)
    assert not output.exists()
    rp = folder/'receipt.json'; review = json.loads(rp.read_text())
    assert not review['identity_or_point_application_performed'] and not review['shared_graph_or_source_changed']
    for name, pin in review['artifacts'].items():
        assert sha(folder/name) == pin['sha256']
    for path, pin in json.loads((folder/'source_hash_pins.json').read_text())['inputs'].items():
        assert sha(path) == pin['sha256']
    proposal = folder/'auxiliary_temporal_trajectories_16.json'
    layer = json.loads(proposal.read_text()); trajectories = layer['trajectories']
    assert len(trajectories) == 16
    db = duckdb.connect(config={'threads':1, 'memory_limit':'256MB'})
    db.read_parquet(str(selected)).create_view('selected')
    db.read_parquet(str(graph)).create_view('graph')
    db.read_parquet(str(points)).create_view('points')
    refs = []
    for t in trajectories:
        obs = {int(r['year']):r for r in t['observations']}
        assert set(obs) == {2002,2010,2021}
        old, aux, current = obs[2002], obs[2010], obs[2021]
        assert db.execute('select count(*) from selected where source_record_id=?', [aux['source_record_id']]).fetchone()[0] == 0
        assert not aux['source_membership_in_selected_observations']
        assert db.execute('select count(*) from graph where from_source_record_id=? and to_source_record_id=?', [old['source_record_id'],current['source_record_id']]).fetchone()[0] > 0
        source = aux['source']; assert sha(source['parsed_reference_file']) == source['parsed_reference_sha256']
        ref = db.execute('select census_year,row_kind,population,men,women,region_raw,settlement_name,settlement_type,district_raw from read_parquet(?) where reference_id=?', [source['parsed_reference_file'],aux['source_record_id']]).fetchall()
        assert len(ref) == 1 and ref[0] == (2010,'settlement',source['total'],source['men'],source['women'],source['region_as_published'],source['typed_name'],source['typed_type'],source['historical_rayon_as_published'])
        assert source['total'] == source['men']+source['women'] == aux['population_source_value']
        assert source['literal_page_row_verified'] and sha(source['pdf_path']) == source['pdf_sha256']
        for year in (2002,2021):
            o = obs[year];sid=o['source_record_id']
            row = db.execute('select census_year,population,is_additive_settlement_record from selected where source_record_id=?',[sid]).fetchall()
            assert row == [(year,o['selected_population'],True)]
            p = o['point_carrier'];use = db.execute('select latitude,longitude,coordinate_admission_status,point_origin_file,point_origin_sha256,point_origin_locator from points where target_source_record_id=?',[sid]).fetchall()
            assert len(use)==1 and use[0][2] in ACCEPTED_COORDINATE_STATUSES
            assert use[0] == (p['latitude'],p['longitude'],p['status'],p['origin_file'],p['origin_sha256'],p['origin_locator'])
            refs.append({'source_record_id':sid,'year':year,'population':int(o['selected_population']),'trajectory_id':t['trajectory_id'],'point_carrier':p})
        t['status'] = 'accepted_scoped_primary_auxiliary_date_trajectory'
        t['ordinary_primary_NP3'] = False
        t['boundary_comparability_asserted'] = False
        t['selected_2010_source_binding_asserted'] = False
        t['national_auxiliary_2010_population_credit'] = False
    assert len(refs)==len({r['source_record_id'] for r in refs})==32
    layer['status']='applied_scoped_primary_auxiliary_date_trajectories'
    output.mkdir()
    files={'accepted_trajectories.json':layer,'accepted_existing_primary_credit_references.json':refs}
    for name,data in files.items():(output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    receipt={'status':layer['status'],'trajectories':16,'existing_primary_credit_references':32,'auxiliary_2010_population_nationally_added':0,'ordinary_graph_modified':False,'source_population_values_modified':False,'ambiguous_selected_2010_counterparts_excluded':False,'outputs':{name:sha(output/name) for name in files},'inputs':{str(rp):sha(rp),str(proposal):sha(proposal),str(selected):sha(selected),str(graph):sha(graph),str(points):sha(points)},'script_sha256':sha(__file__)}
    (output/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt
