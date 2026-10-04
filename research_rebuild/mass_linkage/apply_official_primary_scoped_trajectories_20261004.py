"""Apply a reviewed, exclusive three-place primary-source trajectory projection.

Canonical source populations and graph are immutable. Modern representative
points locate the stable physical places retrospectively, not census geometries.
"""
import argparse,csv,hashlib,json
from pathlib import Path
from datetime import datetime,timezone
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def rows(path):
    with Path(path).open(newline='',encoding='utf-8-sig') as stream:return list(csv.DictReader(stream))
def run(package, selected, points, output):
    package,selected,points,output=map(Path,[package,selected,points,output])
    assert not output.exists(), 'Choose a new immutable output'
    receiptpath=package/'integration_receipt.json';receipt=json.loads(receiptpath.read_text())
    assert sha(receiptpath)=='62c2aee20c7edeeb9033f8bba5d8a162869d0c7d1ed48dcb0987a27bd8ddced3'
    for pin in receipt['input_pins'].values():assert sha(pin['path'])==pin['sha256']
    for pin in receipt['outputs'].values():assert sha(pin['path'])==pin['sha256']
    assert sha(selected)=='4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657'
    observations=rows(package/'accepted_scoped_trajectory_projection.csv');edges=rows(package/'accepted_scoped_continuity_links.csv');contexts=rows(package/'scoped_point_context_uses.csv')
    assert len(observations)==len(contexts)==9 and len(edges)==6
    assert len({r['source_record_id'] for r in observations})==9
    assert {(r['place'],int(r['census_year'])) for r in observations}=={(p,y) for p in receipt['full_trajectory_places'] for y in [2002,2010,2021]}
    assert {(r['place'],int(r['from_year']),int(r['to_year'])) for r in edges}=={(p,a,b) for p in receipt['full_trajectory_places'] for a,b in [(2002,2010),(2010,2021)]}
    assert all(r['decision_status']=='root_approved_scoped_physical_continuity' for r in edges)
    byprojection={r['projection_row_id']:r for r in observations}
    for edge in edges:
        a,b=[byprojection[edge[k]] for k in ['from_projection_row_id','to_projection_row_id']]
        assert a['place']==b['place']==edge['place']
    con=duckdb.connect(config={'threads':1,'memory_limit':'256MB'})
    currentids=sorted({r['current_2021_source_record_id'] for r in observations})
    current={r[0]:(r[1],r[2]) for r in con.execute('select target_source_record_id,latitude,longitude from read_parquet(?) where target_source_record_id in(select unnest(?))',[str(points),currentids]).fetchall()};assert len(current)==3
    needed={r['source_record_id'] for r in observations}|set(currentids)|set(receipt['excluded_partition_source_record_ids'])|{r['preferred_same_census_alternate_selected_source_record_id'] for r in observations if r['preferred_same_census_alternate_selected_source_record_id']}
    sel={r[0]:(int(r[1]),None if r[2] is None else int(r[2])) for r in con.execute('select source_record_id,census_year,population from read_parquet(?) where source_record_id in(select unnest(?))',[str(selected),sorted(needed)]).fetchall()}
    for r in observations:
        sid=r['source_record_id'];year=int(r['census_year']);pop=int(r['population']);counterpart=r['preferred_same_census_alternate_selected_source_record_id'];carrier=r['current_2021_source_record_id']
        assert (float(r['latitude']),float(r['longitude']))==current[carrier]
        assert sel[carrier][0]==2021
        if counterpart:assert sel[counterpart][0]==year
        if year==2021:assert sid==carrier and sel[sid][1]==pop
        if sid in sel:assert sel[sid]==(year,pop)
        r.update(decision_status='accepted_scoped_physical_trajectory_projection',coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_temporal_basis='Modern accepted representative point used retrospectively for independently reviewed physical continuity; historical measurement date unknown',canonical_selected_frame_mutated=False,canonical_identity_graph_mutated=False,provider_identifier_binding_asserted=False,boundary_population_comparability_asserted=False)
    parts=receipt['excluded_partition_source_record_ids'];assert len(parts)==2 and sum(sel[s][1] for s in parts)==29533 and all(sel[s][0]==2002 for s in parts)
    assert {s for s in parts}.isdisjoint({r['source_record_id'] for r in observations})
    for e in edges:e.update(applied_scoped_decision_status='accepted_scoped_physical_continuity',candidate_packet_status_preserved_as_provenance=e['independent_review_packet_status'],application_status='applied_in_exclusive_source_projection_not_canonical_graph')
    output.mkdir();obsfile=output/'accepted_scoped_trajectory_projection.parquet';edgefile=output/'accepted_scoped_continuity_links.parquet'
    pq.write_table(pa.Table.from_pylist(observations),obsfile,compression='zstd');pq.write_table(pa.Table.from_pylist(edges),edgefile,compression='zstd')
    receiptout={'status':'applied_reviewed_official_primary_three_place_scoped_trajectories','utc':datetime.now(timezone.utc).isoformat(),'observation_rows':9,'typed_adjacent_links':6,'places':receipt['full_trajectory_places'],'excluded_partition_source_record_ids':parts,'canonical_selected_frame_mutated':False,'canonical_identity_graph_mutated':False,'protected_alternates_preserved_in_frozen_selection':True,'Vlasikha_two_year_only_excluded_from_full_trajectory_metric':True,'historical_coordinate_measurement_asserted':False,'provider_binding_or_boundary_harmonization_asserted':False,'coordinate_basis':'Accepted modern source-row point retrospectively applied to independently reviewed stable named physical place; no known contrary transformation in admitted scoped rows. Native-QID code conflict retained for Kalininets.','source_choice':'One exact official locality observation per place/year; same-census aliases/counterparts and Kushchevskaya children excluded from additive union; no duplicate source population.','inputs':{str(p):sha(p) for p in [receiptpath,selected,points]+[Path(pin['path']) for pin in receipt['outputs'].values()]},'outputs':{p.name:sha(p) for p in [obsfile,edgefile]},'script_sha256':sha(__file__)}
    (output/'application_receipt.json').write_text(json.dumps(receiptout,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receiptout,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['package','selected','points','output']:p.add_argument('--'+k,required=True)
    a=p.parse_args();run(a.package,a.selected,a.points,a.output)
