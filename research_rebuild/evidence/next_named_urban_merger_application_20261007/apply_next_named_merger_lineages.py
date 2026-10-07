"""Validate and normalize four complete named event lineages; no ordinary edges."""
import gzip, hashlib, json, subprocess, sys
from pathlib import Path
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
E = ROOT / 'research_rebuild/evidence'
C = E / 'next_named_urban_merger_batch_20261007'
sys.path.insert(0, str(ROOT / 'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km
from measure_event_aware_path_union_20261005 import SELECTED
FILES = ('group_observations', 'constituent_credit_union', 'representative_scope_points', 'event_edges')
EXPECTED = {'Krasnodar_2003_named': (723404,744995,1099344), 'Khimki_2004_named': (177445,207425,257128), 'Tula_2005_named': (530558,501169,473622), 'Donskoy_2005_named': (69653,64552,63837)}
HISTORICAL_LOADER_SHA = '29337fc949be2c9141053c553a60f355ddef90ec3fcc80fa943999db9402dddb'
STATUS = 'accepted_complete_named_event_scope_secondary_event_witness'
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def clean(v):
    return {k: None if pd.isna(x) else x.item() if hasattr(x,'item') else x for k,x in v.items()}
def require(condition, detail):
    if not condition: raise ValueError(detail)
def main():
    review = json.loads((C/'receipt.json').read_text())
    frozen = json.loads((OUT/'frozen_validation_inputs.json').read_text())
    for p,h in frozen['inputs_sha256'].items(): require(sha(p)==h, 'Frozen validation input changed: '+p)
    for p,h in review['inputs_sha256'].items(): require(sha(p)==h, 'Candidate input changed: '+p)
    for p,h in review['outputs_sha256'].items(): require(sha(C/p)==h, 'Candidate output changed: '+p)
    require(sha(C/'source_witnesses.json')==review['source_witness_sha256'], 'Event witnesses changed')
    old = subprocess.check_output(['git','show','f86fdbd:research_rebuild/mass_linkage/working_state_20261007.py'], cwd=ROOT)
    require(hashlib.sha256(old).hexdigest()==HISTORICAL_LOADER_SHA, 'Historical stage15 loader changed')
    state = load(16)
    for p in state.inputs: require(str(p) in frozen['inputs_sha256'], 'Unpinned active ledger '+str(p))
    frames = {key:pd.read_csv(C/('candidate_'+key+'.csv'),keep_default_na=False) for key in FILES}
    obs, members, points, edges = [frames[k] for k in FILES]
    require(tuple(map(len,[obs,members,points,edges]))==(12,41,4,8), 'Roster size changed')
    require(not members.source_record_id.duplicated().any(), 'Duplicate source credit')
    native_rows = duckdb.connect().execute('select * from read_parquet(?) where source_record_id in (select unnest(?))',[str(SELECTED),members.source_record_id.tolist()]).fetchdf().set_index('source_record_id')
    witness_rows=[]
    sheets={}
    for row in members.to_dict('records'):
        sid=row['source_record_id']; native=native_rows.loc[sid]; current=state.by_id.loc[sid]
        for key in ['census_year','population','settlement_name','settlement_type','source_file']:
            require(str(native[key])==str(current[key]) or key in ['census_year','population'] and float(native[key])==float(current[key]), 'Selected/current mismatch '+sid+' '+key)
        require(int(native.census_year)==int(row['census_year']) and int(native.population)==int(row['population']), 'Selected count mismatch '+sid)
        require(native.source_file==row['source_file'] and native.settlement_name==row['settlement_name'] and native.settlement_type==row['settlement_type'], 'Selected binding mismatch '+sid)
        path=Path('/workspace/settlements-raw')/native.source_file
        require(sha(path)==row['source_file_sha256'], 'Census file changed '+sid)
        expected_locator=f'{native.source_sheet}!row={native.source_row}'
        require(expected_locator==row['source_row_locator'], 'Native row locator differs '+sid)
        raw_text=''; raw_population=None
        if int(native.census_year)==2002:
            if str(path) not in sheets: sheets[str(path)]=pd.read_excel(path,header=None)
            raw=sheets[str(path)].iloc[int(native.source_row)-1]
            urban=path.name=='1_TOM_01_04.xls'; raw_text=str(raw[0 if urban else 1]);raw_population=int(raw[1 if urban else 2])
            require(raw_population==int(row['population']), 'Original 2002 cell mismatch '+sid)
            require(str(native.settlement_name).lower().replace('ё','е') in raw_text.lower().replace('ё','е'), 'Original 2002 name mismatch '+sid)
        witness_rows.append({'group':row['group'],'source_record_id':sid,'census_year':int(native.census_year),'population':int(native.population),'settlement_name':native.settlement_name,'settlement_type':native.settlement_type,'region_norm':native.region_norm,'district_raw':native.district_raw,'source_file':native.source_file,'source_file_sha256':sha(path),'source_row_locator':expected_locator,'native_source_locator':native.source_locator,'raw_2002_text':raw_text,'raw_2002_population':raw_population,'native_hierarchy_preserved':True,'selected_id_population_file_binding_verified':True})
    witnesses={x['key']:x for x in json.loads((C/'source_witnesses.json').read_text())}
    for w in witnesses.values():
        require(sha(w['asset_path'])==w['asset_sha256'], 'Event asset changed')
        if w['asset_path'].endswith('.gz'):
            data=json.load(gzip.open(w['asset_path'])); page=next(x for x in data['query']['pages'] if x['title']==w['page_title']); rev=page['revisions'][0]
            require(rev['revid']==w['revision_id'] and rev['timestamp']==w['revision_timestamp'] and w['exact_excerpt'] in rev['slots']['main']['content'], 'Own article witness mismatch')
        else: require(w['exact_excerpt'] in Path(w['asset_path']).read_text(), 'Actual law excerpt differs')
    points=points.rename(columns={'point_role':'scope_point_role','verified_state':'verified_active_state','historical_child_own_point_asserted':'historical_constituent_own_point_asserted'})
    for i,row in points.iterrows():
        sid=row.parent_source_record_id; native=state.by_id.loc[sid]; p=state.point_rows[sid]
        require(int(native.census_year)==2021 and native.settlement_type=='город', 'Parent is not published 2021 city')
        require(distance_km((float(row.latitude),float(row.longitude)),(p['latitude'],p['longitude']))<.00001, 'Active point differs')
        provenance=json.loads(row.point_provenance_json)
        for k in ['coordinate_source_record_id','coordinate_admission_status','point_origin_file','point_origin_sha256','point_origin_locator','point_ledger_path']:
            require(provenance[k]==p[k], 'Active point provenance differs '+k)
        require(sha(p['point_origin_file'])==p['point_origin_sha256'], 'Point original asset changed')
        require(p['point_ledger_path'] in frozen['inputs_sha256'], 'Point admitted ledger unpinned')
        require(not row.historical_constituent_own_point_asserted, 'Historical child own point asserted')
        points.loc[i,'verified_active_state']=16
    for group,pops in EXPECTED.items():
        rows=obs[obs.group.eq(group)].sort_values('census_year')
        require(tuple(rows.population)==pops and set(rows.census_year)=={2002,2010,2021}, 'Unexpected group series')
        for i,row in rows.iterrows():
            mm=members[members.group.eq(group)&members.census_year.eq(row.census_year)]
            require(set(json.loads(row.source_record_ids_json))==set(mm.source_record_id) and int(mm.population.sum())==int(row.population) and len(mm)==row.constituent_count, 'Incomplete roster or sum')
            require(row.roster_complete and not row.ordinary_same_place and row.boundary_comparability=='UNKNOWN', 'Scope claim differs')
            laws=[]
            for key in json.loads(row.event_source_witness_keys_json):
                w=witnesses[key]; laws.append(dict(w, source_path=w['asset_path'], source_sha256=w['asset_sha256'], clause_or_event_provenance=w['exact_excerpt']))
            obs.loc[i,'legal_basis_json']=json.dumps(laws,ensure_ascii=False)
            obs.loc[i,'members_json']=json.dumps(mm[['source_record_id','settlement_name','population']].to_dict('records'),ensure_ascii=False)
    obs=obs.rename(columns={'parent_source_record_id':'representative_parent_source_record_id','no_fake2021_child_values':'no_fake_2021_child_population'})
    obs['identity_axis']='named_merger_event_lineage';obs['official_act_verified']=False
    members['district_raw']=[state.by_id.loc[x,'district_raw'] for x in members.source_record_id]
    members['additive_only_within_complete_named_year_group']=True
    members['separate_population_credit_in_addition_to_group']=False
    members['ordinary_same_place_edge_created']=False
    members['own_native_point_available']=[x in state.point_rows for x in members.source_record_id]
    frames=dict(zip(FILES,[obs,members,points,edges])); outputs={}
    for key,frame in frames.items():
        frame['candidate_only']=False;frame['decision_status']=STATUS
        name='accepted_'+key+'.csv';frame.to_csv(OUT/name,index=False);outputs[name]=sha(OUT/name)
    pd.DataFrame(witness_rows).to_csv(OUT/'verified_native_source_bindings.csv',index=False)
    outputs['verified_native_source_bindings.csv']=sha(OUT/'verified_native_source_bindings.csv')
    receipt={'status':'applied_separate_complete_named_merger_event_lineage','groups':4,'observations':12,'constituents':41,'representative_scope_points':4,'event_edges':8,'admission_stage':16,'candidate_baseline_stage':15,'ordinary_same_place_graph_modified':False,'historical_child_points_or_missing_year_populations_created':False,'boundary_comparability':'UNKNOWN','modern_boundary_harmonization_asserted':False,'official_act_verified':False,'legal_source_quality':'secondary actual act text and own-city article complete named event witnesses; official authentication unasserted','source_population_values_modified':False,'candidate_receipt_sha256':sha(C/'receipt.json'),'frozen_validation_inputs_sha256':sha(OUT/'frozen_validation_inputs.json'),'historical_stage15_loader_git_commit':'f86fdbd','historical_stage15_loader_sha256':HISTORICAL_LOADER_SHA,'net_selected_source_id_union_gain_at_candidate_stage15':review['gains'],'net_gain':review['gains'],'outputs':outputs,'whole_group_holds':review['holds']}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':receipt['status'],'groups':4,'verified_native_bindings':41,'outputs':outputs}))
if __name__=='__main__': main()
