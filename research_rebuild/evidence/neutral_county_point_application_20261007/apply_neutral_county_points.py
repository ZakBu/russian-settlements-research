"""Explicit stage17 neutral-caption application; never changes loader/source inputs."""
import sys,json
from pathlib import Path
from collections import defaultdict
import pandas as pd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,distance_km,normalize
OUT=Path(__file__).resolve().parent
REVIEW=ROOT/'research_rebuild/evidence/cross_county_independent_point_bridge_20261007'
WORK=Path('/workspace/settlements-work/cross_county_independent_point_bridge_20261007')

def main():
    checked={}
    def pin(path,expected):
        path=Path(path);got=checked.setdefault(str(path),sha(path))
        if got!=expected:raise ValueError('Pinned input changed: '+str(path))
    packet=json.loads((REVIEW/'neutral_subset_receipt.json').read_text())
    original=json.loads((REVIEW/'receipt.json').read_text())
    samples=json.loads((REVIEW/'source_check_receipt.json').read_text())
    for receipt in [packet,original]:
        for p,h in receipt['inputs'].items():pin(p,h)
        for p,h in receipt.get('donor_ledger_sha256',{}).items():pin(p,h)
        for p,info in receipt['outputs'].items():pin(p,info['sha256'])
    pin(REVIEW/'source_check_receipt.json',packet['source_check_receipt_sha256'])
    for p,h in samples['inputs_sha256'].items():pin(p,h)
    for p,h in samples['old_census_source_hashes'].items():pin(p,h)
    if not samples['all_requested_checks_pass']:raise ValueError('Bounded primary-source sample failed')
    samplecsv=REVIEW/'bounded_raw_source_code_checks.csv';pin(samplecsv,samples['output_sha256'])
    edges=pd.read_csv(WORK/'neutral_identity_edge_delta.csv.gz',dtype=str,keep_default_na=False)
    proposals=pd.read_csv(WORK/'neutral_point_use_delta.csv.gz',dtype=str,keep_default_na=False)
    candidates=pd.read_csv(WORK/'neutral_candidates.csv.gz',dtype=str,keep_default_na=False)
    if len(edges)!=547 or len(proposals)!=546 or proposals.target_source_record_id.duplicated().any():raise ValueError('Approved neutral packet count/uniqueness differs')
    s=load(17);before=s.metrics()
    if before!=packet['baseline']:raise ValueError('Stage17 baseline differs')
    for p in s.inputs:pin(p,packet['inputs'][str(p)])
    donor_ids=set(candidates.current_source_record_id)
    witnesses={(a['old_source_record_id'],a['current_source_record_id']):a for a in candidates.to_dict('records')}
    if set(witnesses)!=set(edges[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None)):raise ValueError('Neutral edge/witness mismatch')
    for a,b in edges[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None):
        witness=witnesses[a,b];old,current=s.by_id.loc[a],s.by_id.loc[b];cp=s.point_rows[b]
        if normalize(old.region_norm)!=normalize(current.region_norm) or normalize(old.region_norm)!=witness['region_norm']:raise ValueError('Region mismatch')
        if witness['county_caption_class']!='neutral_same_geographic_county_caption':raise ValueError('Different geographic county stem cannot be admitted')
        if str(old.district_raw)!=witness['old_district_raw'] or str(current.district_raw)!=witness['current_district_raw']:raise ValueError('Printed county witness differs')
        if str(old.settlement_name)!=witness['old_name'] or str(current.settlement_name)!=witness['current_name']:raise ValueError('Original census name witness differs')
        if witness['old_point_origin_file']==witness['current_point_origin_file']:raise ValueError('Historical/current point lineage is not independent')
        if cp['point_ledger_path']!=witness['current_point_ledger']:raise ValueError('Current donor admission changed')
        for k in ['point_origin_file','point_origin_sha256','point_origin_locator']:
            expected=witness.get('current_'+k,'');actual=cp.get(k,'')
            if pd.isna(actual):actual=''
            if str(actual)!=expected:raise ValueError('Current donor origin differs: '+k)
        if (float(cp['latitude']),float(cp['longitude']))!=(float(witness['current_latitude']),float(witness['current_longitude'])):raise ValueError('Current donor coordinate differs')
        if distance_km((float(witness['old_latitude']),float(witness['old_longitude'])),(cp['latitude'],cp['longitude']))>5:raise ValueError('Bound ownpoints differ by more than5km')
        if a in s.conflicting_point_targets or b in s.conflicting_point_targets:raise ValueError('Accepted endpoint point conflict')
        if s.uf.find(a)==s.uf.find(b):raise ValueError('Approved edge is no longer new')
        s.union(a,b)
    members=defaultdict(list)
    for r in s.obs.to_dict('records'):members[s.uf.find(r['source_record_id'])].append(r)
    occupied=defaultdict(set)
    for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
    points=[]
    for row in proposals.to_dict('records'):
        sid,bid=row['target_source_record_id'],row['coordinate_source_record_id']
        if sid in s.point_rows or bid not in donor_ids or s.uf.find(sid)!=s.uf.find(bid):raise ValueError('Point target lacks approved same-place continuity or is not new')
        cp=s.point_rows[bid];yr=int(s.by_id.loc[sid,'census_year'])
        if yr!=int(row['target_year']) or (float(row['latitude']),float(row['longitude']))!=(cp['latitude'],cp['longitude']):raise ValueError('Target year/donor point differs')
        relevant=members[s.uf.find(sid)]
        if any(r['source_record_id'] in s.point_rows and distance_km((s.point_rows[r['source_record_id']]['latitude'],s.point_rows[r['source_record_id']]['longitude']),(cp['latitude'],cp['longitude']))>5 for r in relevant):raise ValueError('Component point contradiction')
        if occupied[(yr,cp['latitude'],cp['longitude'])]-{sid}:raise ValueError('New same-year representative point collision')
        # Preserve actual modern source origin. Historical binding is a separate immutable witness, not the point donor.
        accepted={k:v for k,v in cp.items() if k!='point_ledger_path'}
        accepted.update(target_source_record_id=sid,target_year=yr,latitude=cp['latitude'],longitude=cp['longitude'],coordinate_source_record_id=bid,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_origin_ledger=cp['point_ledger_path'],coordinate_origin_ledger_sha256=checked[cp['point_ledger_path']],coordinate_origin_ledger_locator='target_source_record_id='+bid,continuity_inference='retrospective_representative_point_from_independently_admitted_current_ownpoint_after_neutral_county_same_place_union',historical_source_binding_witness_file=str(WORK/'neutral_candidates.csv.gz'),historical_source_binding_witness_sha256=sha(WORK/'neutral_candidates.csv.gz'),direct_historical_measurement=False,population_boundary_comparability_asserted=False,administrative_event_date='UNKNOWN')
        points.append(accepted);occupied[(yr,cp['latitude'],cp['longitude'])].add(sid)
    edges['decision_status']='checked_rule_accepted'
    edges.to_csv(OUT/'accepted_identity_edge_delta.csv',index=False)
    pd.DataFrame(points).to_csv(OUT/'accepted_point_use_delta.csv',index=False)
    s.add_deltas(point_paths=[OUT/'accepted_point_use_delta.csv']);after=s.metrics()
    if after!=packet['simulation']:raise ValueError('Actual admitted point-use metrics differ from approved simulation')
    if [after[str(y)]['covered_population'] for y in [2002,2010,2021]]!=[126189027,123416566,124002885]:raise ValueError('Expected after population differs')
    if [after[str(y)]['covered_rows'] for y in [2002,2010,2021]]!=[137016,137044,137048]:raise ValueError('Expected after row count differs')
    inputs={str(p):sha(p) for p in [*s.inputs,REVIEW/'neutral_subset_receipt.json',REVIEW/'receipt.json',REVIEW/'source_check_receipt.json',WORK/'neutral_identity_edge_delta.csv.gz',WORK/'neutral_point_use_delta.csv.gz',WORK/'neutral_candidates.csv.gz',Path(__file__)] if Path(p).resolve().parent!=OUT}
    inputs[str(Path(__file__))]=sha(Path(__file__))
    receipt={'status':'applied_neutral_county_caption_exact_name_independent_ownpoints','baseline_stage':17,'new_edges':547,'new_point_uses':546,'net_new_full_three_histories':15,'baseline':before,'after':after,'population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'full_three_row_gain':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'different_geographic_stem_edges_held':46,'historical_point_evidence_is_prior_admission_asserted':False,'point_use_origin':'actual existing independently admitted modern ownpoint; donor point_origin_* fields preserved','historical_source_binding_evidence_file':str(WORK/'neutral_candidates.csv.gz'),'historical_source_binding_evidence_sha256':sha(WORK/'neutral_candidates.csv.gz'),'administrative_eventdate':'UNKNOWN','source_population_values_modified':False,'population_boundary_comparability_asserted':False,'protected_existing_coordinate_statuses_modified':False,'bounded_source_checks_reused':20,'neutral_bounded_primary_sample_rows':19,'all_input_hashes_verified':checked,'inputs':inputs,'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in [OUT/'accepted_identity_edge_delta.csv',OUT/'accepted_point_use_delta.csv']}}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['status','new_edges','new_point_uses','net_new_full_three_histories','population_gain','after']}))
if __name__=='__main__':main()
