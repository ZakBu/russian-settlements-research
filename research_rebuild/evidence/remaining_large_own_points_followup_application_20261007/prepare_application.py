from pathlib import Path
import sys,json,gzip,re,os,time
import pandas as pd
R=Path('/workspace/russian-settlements-research');C=R/'research_rebuild/evidence/remaining_large_own_points_followup_20261007';A=Path(__file__).parent;A.mkdir(exist_ok=True);sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,distance_km
s=load(21);before=s.metrics();pc=pd.read_csv(C/'candidate_point_uses.csv').fillna('');obs=pd.read_csv(C/'candidate_qualified_physical_observations.csv').fillna('');proof=pd.read_csv(C/'historic_native_row_checks.csv').fillna('');pins={str(p):sha(p) for p in s.inputs}; report=R/'research_rebuild/evidence/working_full_chain_20261007';rp=report/'coverage_receipt.json';pins[str(rp)]=sha(rp);rc=json.loads(rp.read_text());assert rc['working_stage']==21
entity={}
for fn in ['entities.json.gz','additional_entities.json.gz']:
 p=C/fn;entity.update(json.loads(gzip.open(p,'rt').read())['entities']);pins[str(p)]=sha(p)
val=lambda sn:sn.get('datavalue',{}).get('value');base={};new=[];binding=[];conflicts=[]
for r in pc.to_dict('records'):
 sid=r['target_source_record_id'];assert sid in s.by_id.index
 assert sid not in s.point_rows,('Current point already active stage21',sid)
 assert sha(Path(r['point_origin_file']))==r['point_origin_sha256'];pins[r['point_origin_file']]=r['point_origin_sha256']
 q=r['coordinate_source_record_id'];rawcoords=[val(st.get('mainsnak',{})) for st in entity[q].get('claims',{}).get('P625',[])];r.update(coordinate_admission_status='reviewed_extension_rule_accepted',admission_allowed=True,wikidata_declared_coordinate_claims_json=json.dumps(rawcoords,ensure_ascii=False),coordinate_calculation='article explicitly printed DMS converted by deg+min/60+sec/3600' if r['point_origin_kind'].startswith('own_Wikipedia') else 'raw own Wikidata P625 preserved',direct_census_date_coordinate=False,modern_boundary_harmonized=False)
 base[sid]=r
 for t in s.obs[s.obs.root==s.uf.find(sid)].itertuples():
  d=0.0
  if t.source_record_id in s.point_rows:
   old=s.point_rows[t.source_record_id];d=distance_km((r['latitude'],r['longitude']),(old['latitude'],old['longitude']))
   if d>5:conflicts.append({'current_sid':sid,'historical_sid':t.source_record_id,'distance_km':d})
   binding.append({'current_sid':sid,'target_sid':t.source_record_id,'target_year':int(t.census_year),'binding_status':'already_accepted_sameplace_component_active_point_retained','active_point_distance_km':d});continue
  nr=r.copy();nr.update(target_source_record_id=t.source_record_id,target_year=int(t.census_year),population=float(t.population),source_file=t.source_file,source_sha256=t.source_sha256,source_locator=t.source_locator,point_use_inference='modern_own_representative_point_on_existing_accepted_sameplace_component' if int(t.census_year)!=2021 else 'current_own_representative_point');new.append(nr);binding.append({'current_sid':sid,'target_sid':t.source_record_id,'target_year':int(t.census_year),'binding_status':'existing_accepted_sameplace_component_new_own_point_use','active_point_distance_km':0})
# Already-admitted current Sibirsky point; historical2002urban typed own source is explicit reviewed sidecar identity, not an ordinary edge.
sib='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:41174';assert sib in s.point_rows;base[sib]=dict(s.point_rows[sib]);base[sib].update(target_source_record_id=sib,wikidata_declared_coordinate_claims_json=json.dumps([val(st.get('mainsnak',{})) for st in entity['Q953712']['claims'].get('P625',[])],ensure_ascii=False))
for i,r in obs.iterrows():
 current=r.current2021_source_record_id;point=base[current];nativeid=r.source_record_id
 if nativeid:
  b=s.by_id.loc[nativeid];assert float(b.population)==float(r.population_source_value) and b.population_value_quality==r.population_quality
  same=s.uf.find(nativeid)==s.uf.find(current)
  rule='existing_accepted_sameplace_component_native_source_binding' if same else ''
  if not same:
   assert current==sib and nativeid=='2002:1_TOM_01_04.xls:0:8457'
   pp=proof[proof.sid.eq(nativeid)];assert len(pp)==1 and bool(pp.iloc[0].own_name_in_native_row) and bool(pp.iloc[0].count_in_native_row_matches)
   assert b.settlement_type=='пгт' and b.population==12046
   rule='reviewed_typed_native_official_urban_Sibirsky12046_with_own_ZATO_article_history; distinct_rural_Sibirsky1804_excluded; no_ordinary_graph_edge'
  binding.append({'current_sid':current,'target_sid':nativeid,'target_year':int(r.year),'binding_status':rule,'active_point_distance_km':0})
  if nativeid in s.point_rows:
   old=s.point_rows[nativeid];d=distance_km((point['latitude'],point['longitude']),(old['latitude'],old['longitude']))
   if d>5:conflicts.append({'current_sid':current,'historical_sid':nativeid,'distance_km':d})
  elif not same:
   nr=dict(point);nr.update(target_source_record_id=nativeid,target_year=int(r.year),population=float(b.population),coordinate_admission_status='reviewed_extension_rule_accepted',admission_allowed=True,source_file=b.source_file,source_sha256=b.source_sha256,source_locator=b.source_locator,coordinate_binding_rule=rule,point_use_inference='modern_own_representative_point_historical_physical_continuity_inference');new.append(nr)
 else:
  assert bool(r.nonadditive_observation)
  refs=json.loads(r.census_reference_witness_json);assert refs and all(z['qualified_explicit_census'] for z in refs)
 obs.at[i,'decision_status']='qualified_accepted_secondary_own_census_history';obs.at[i,'point_binding_json']=json.dumps(point,ensure_ascii=False);obs.at[i,'point_origin_file']=point['point_origin_file'];obs.at[i,'point_origin_sha256']=point['point_origin_sha256'];obs.at[i,'point_origin_locator']=point['point_origin_locator'];obs.at[i,'selected_source_population_preserved']=bool(nativeid)
assert not conflicts,conflicts
p=pd.DataFrame(new).drop_duplicates('target_source_record_id');assert len(p)==len(new);assert not p.groupby(['target_year','latitude','longitude']).coordinate_source_record_id.nunique().gt(1).any()
for t,g in obs.groupby('trajectory_id'):assert set(g.year.astype(int))=={2002,2010,2021}
credit={sid for sid in s.point_rows if s.years[s.uf.find(sid)]=={2002,2010,2021}}
cp=report/'qualified_scope_source_id_credit_union.csv';pins[str(cp)]=sha(cp);cr=pd.read_csv(cp,dtype=str).fillna('')
for c in cr:
 if 'source_record_id'in c:credit.update(cr[c])
# Additional accepted native sidecars may be prepared between reports: expose/report-scope baseline rather than silently assuming credit.
net=[];ordinary_after=s.metrics(extra_point_ids=set(p.target_source_record_id));after_credit=set(credit)
for y in [2002,2010,2021]:
 ids=set(obs.loc[(obs.year==y)&obs.source_record_id.ne(''),'source_record_id'])-credit
 ordinarynew={sid for sid in p.target_source_record_id if int(s.by_id.loc[sid,'census_year'])==y and s.years[s.uf.find(sid)]=={2002,2010,2021}}-credit
 ids |= ordinarynew;after_credit.update(ids)
 net.append({'year':y,'new_unique_selected_ids':len(ids),'new_selected_population':float(s.by_id.loc[list(ids),'population'].sum()) if ids else 0,'ordinary_full3_new_population':ordinary_after[str(y)]['covered_population']-before[str(y)]['covered_population'],'ordinary_full3_new_rows':ordinary_after[str(y)]['covered_rows']-before[str(y)]['covered_rows'],'historic_secondary_nonadditive_population_no_selected_ID_credit':float(obs.loc[(obs.year==y)&obs.nonadditive_observation.astype(str).str.lower().eq('true'),'population_source_value'].sum())})
# Write data first; the apply receipt is the last atomic marker.
p.to_csv(A/'accepted_point_use_delta.csv',index=False);obs.to_csv(A/'accepted_qualified_physical_observations.csv',index=False);pd.DataFrame(binding).to_csv(A/'historical_native_binding_and_component_checks.csv',index=False);pd.DataFrame(net).to_csv(A/'actual_unique_selected_source_id_net_delta.csv',index=False)
for name in ['candidate_point_uses.csv','candidate_qualified_physical_observations.csv','native_and_own_article_binding_checks.csv','historic_native_row_checks.csv','fixed15_and_largest5_source_checks.csv','receipt.json']:
 pins[str(C/name)]=sha(C/name)
receipt={'status':'prepared_reviewed_application_root_integration_pending','baseline_stage':21,'report21_coverage_receipt_sha256':pins[str(rp)],'new_current_own_points':len(pc),'new_current_own_point_population':float(pc.population.sum()),'new_point_uses':len(p),'qualified_full3_trajectories':int(obs.trajectory_id.nunique()),'qualified_observations':len(obs),'qualified_current_native_population':float(obs[obs.year==2021].population_source_value.sum()),'actual_net_against_report21_unique_source_id_union':net,'ordinary_baseline':before,'ordinary_after_point_delta':ordinary_after,'active_component_or_native_point_conflicts_over5km':len(conflicts),'exact_shared_points_distinct_own_objects':0,'historical_native_component_binding_checks':len(binding),'native_population_values_and_qualities_preserved':True,'ordinary_identity_graph_modified':False,'boundaries':'UNKNOWN','error_rate':'uncalibrated','source_point_precision_policy':'calculated ownarticle DMS and raw Wikidata declared precision stored separately; no precision invented','inputs':pins,'outputs':{p.name:sha(p) for p in A.glob('*.csv')}}
tmp=A/'application_receipt.json.tmp';tmp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2));os.replace(tmp,A/'application_receipt.json');print(json.dumps({k:receipt[k] for k in ['new_current_own_points','new_point_uses','qualified_full3_trajectories','qualified_current_native_population','actual_net_against_report21_unique_source_id_union','active_component_or_native_point_conflicts_over5km']},ensure_ascii=False))
