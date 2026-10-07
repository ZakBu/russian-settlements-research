"""Admit two reviewed complete named event lineages as a separate scope."""
import json,hashlib,sys,math
from pathlib import Path
import pandas as pd,duckdb
R=Path(__file__).resolve().parents[3];O=Path(__file__).resolve().parent;C=R/'research_rebuild/evidence/further_urban_merger_reserve_20261007'
sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from measure_event_aware_path_union_20261005 import SELECTED
FILES=('group_observations','constituent_credit_union','representative_scope_points','event_edges')
EXPECTED={'Kemerovo_2004_named':(529934,532981,557119),'Novokuznetsk_2004_named':(565680,547904,537480)}
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def require(b,msg):
 if not b:raise ValueError(msg)
def main():
 review=json.loads((C/'two_city_candidate_receipt.json').read_text())
 for path,h in review['inputs_sha256'].items():require(sha(path)==h,'Candidate input changed: '+path)
 for name,h in review['outputs'].items():require(sha(C/name)==h,'Candidate output changed: '+name)
 require((review['groups_ready'],review['observations'],review['constituents'],review['points'],review['event_edges'])==(2,6,14,2,4),'Unexpected candidate dimensions')
 state=load(17);active_pins={str(p):sha(p) for p in state.inputs}
 loader=R/'research_rebuild/mass_linkage/working_state_20261007.py';active_pins[str(loader)]=sha(loader)
 frozen_path=O/'active_validation_input_pins.json'
 if frozen_path.exists():
  previous=json.loads(frozen_path.read_text())
  require(previous['inputs_sha256']==active_pins,'Active validation inputs changed')
 else:frozen_path.write_text(json.dumps({'verification_active_state':17,'candidate_verified_state':16,'inputs_sha256':active_pins},indent=2)+'\n')
 frames={k:pd.read_csv(C/('candidate_'+k+'.csv'),keep_default_na=False) for k in FILES}
 obs,members,points,edges=[frames[k] for k in FILES]
 require(tuple(map(len,[obs,members,points,edges]))==(6,14,2,4),'Changed roster')
 require(not members.source_record_id.duplicated().any(),'Duplicate constituent credit')
 native=duckdb.connect().execute('select * from read_parquet(?) where source_record_id in (select unnest(?))',[str(SELECTED),members.source_record_id.tolist()]).fetchdf().set_index('source_record_id')
 for row in members.to_dict('records'):
  sid=row['source_record_id'];n=native.loc[sid];current=state.by_id.loc[sid]
  require(int(n.census_year)==int(row['census_year']) and int(n.population)==int(row['population'])==int(current.population),'Selected/native population mismatch '+sid)
  for k in ['settlement_name','settlement_type','source_file']:require(n[k]==row[k]==current[k],'Selected/native binding mismatch '+sid)
  require(row['source_row_locator']==f'{n.source_sheet}!row={n.source_row}','Selected row locator mismatch '+sid)
  require(sha(Path('/workspace/settlements-raw')/n.source_file)==row['source_file_sha256'],'Original source file changed '+sid)
  require(row['source_population_unmodified'] and row['exclusive_source_ID_credit'] and not row['separate_population_credit_in_addition_to_group'] and not row['ordinary_same_place_edge_created'],'Invalid source credit semantics')
 for g,pops in EXPECTED.items():
  rows=obs[obs.group.eq(g)].sort_values('census_year');require(tuple(rows.population)==pops and set(rows.census_year)=={2002,2010,2021},'Series changed '+g)
  for row in rows.to_dict('records'):
   mm=members[members.group.eq(g)&members.census_year.eq(row['census_year'])]
   require(set(json.loads(row['source_record_ids_json']))==set(mm.source_record_id) and int(mm.population.sum())==int(row['population']) and len(mm)==int(row['constituent_count']),'Incomplete source roster')
   require(row['identity_axis']=='named_merger_event_lineage' and row['roster_complete'] and not row['ordinary_same_place'] and row['boundary_comparability']=='UNKNOWN' and not row['official_act_verified'] and row['no_fake_2021_child_population'],'Invalid lineage or comparability assertion')
   if row['census_year'] in [2010,2021]:require(len(mm)==1 and mm.iloc[0].settlement_type=='город','Already absorbed child added to whole published city')
   for law in json.loads(row['legal_basis_json']):require(sha(law['source_path'])==law['source_sha256'],'Actual archived legal/event source changed')
 for i,row in points.iterrows():
  sid=row.parent_source_record_id;p=state.point_rows[sid];require(int(state.by_id.loc[sid,'census_year'])==2021,'Representative parent is not published2021 city')
  require(float(row.latitude)==float(p['latitude']) and float(row.longitude)==float(p['longitude']) and all(math.isfinite(float(p[k])) for k in ['latitude','longitude']),'Active receiving city point changed')
  old=json.loads(row.point_provenance_json)
  for k,v in old.items():require(p.get(k)==v,'Candidate16/current17 point provenance changed '+k)
  require(sha(p['point_origin_file'])==p['point_origin_sha256'],'Point original asset changed')
  require(p['point_ledger_path'] in active_pins,'Active point admitted ledger not pinned')
  require(row.scope_point_role=='representative_scope' and not row.historical_constituent_own_point_asserted,'Historical child own point asserted')
  points.loc[i,'verified_active_state']=17
 for row in edges.to_dict('records'):require(row['relation']=='complete_named_merger_lineage' and not row['ordinary_same_place'] and row['boundary_comparability']=='UNKNOWN','Invalid event edge')
 outputs={}
 for key,frame in zip(FILES,[obs,members,points,edges]):
  frame['candidate_only']=False;frame['decision_status']='accepted_complete_named_event_scope_secondary_archived_event_witness'
  name='accepted_'+key+'.csv';frame.to_csv(O/name,index=False);outputs[name]=sha(O/name)
 receipt={'status':'applied_separate_complete_named_merger_event_lineage','groups':2,'observations':6,'constituents':14,'representative_scope_points':2,'event_edges':4,'admission_stage':17,'candidate_verified_stage':16,'ordinary_same_place_graph_modified':False,'historical_child_points_or_missing_year_populations_created':False,'boundary_comparability':'UNKNOWN','modern_boundary_harmonization_asserted':False,'official_act_verified':False,'legal_source_quality':'secondary archived actual act bodies and exact own-locality receiving-city event histories; official authentication unasserted','source_population_values_modified':False,'candidate_receipt_sha256':sha(C/'two_city_candidate_receipt.json'),'candidate_loader_expected_sha256':review['inputs_sha256'][str(loader)],'active_loader_sha256':sha(loader),'loader_stage_semantics':'Stage17 adds only near_name_coordinate accepted deltas; candidate16 current17 parent point geometry and all provenance fields checked unchanged. Candidate input loader hash matches current bytes.','active_validation_input_pins_sha256':sha(frozen_path),'net_selected_source_id_union_gain_after_first_seven_groups_at_candidate_stage16':review['gains'],'net_gain':review['gains'],'outputs':outputs,'whole_group_holds':review['holds']}
 (O/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':receipt['status'],'groups':2,'observations':6,'constituents':14,'points':2,'edges':4,'outputs':outputs}))
if __name__=='__main__':main()
