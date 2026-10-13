import sys,json,gzip,re,collections,math
from pathlib import Path
import pandas as pd,numpy as np
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;E=O.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,distance_km
s=load(51)
for folder in ['native_rural_type_alias_mass_20261008','cached_historical_name_alias_mass_20261008']:
 p=E/folder;s.add_deltas([p/'accepted_identity_edge_delta.csv.gz'],[p/'accepted_point_use_delta.csv.gz'])
before=s.metrics();protected=s.obs[['source_record_id','population','population_value_quality','settlement_name','settlement_type']].copy();rec=json.loads((O/'qualified_application_receipt.json').read_text());pins=rec['input_pins'];f=pd.read_csv(O/'accepted_qualified_physical_observations.csv',keep_default_na=False);cr=pd.read_csv(O/'accepted_selected_source_id_credit_union.csv');assert len(f)==3*rec['qualified_series'];assert cr.source_record_id.is_unique;assert not f.ordinary_NP3_asserted.any() and not f.boundary_comparability_asserted.any();entities={}
badtrajectories=[]
for tid,g in f.groupby('trajectory_id'):
 cur=g[g.year.eq(2021)].iloc[0];cp=s.point_rows[cur.source_record_id]
 for row in g[~g.nonadditive_observation].itertuples():
  hp=s.point_rows[row.source_record_id];dist=distance_km((cp['latitude'],cp['longitude']),(hp['latitude'],hp['longitude']))
  if dist>5:badtrajectories.append({'trajectory_id':tid,'source_record_id':row.source_record_id,'distance_km':dist,'reason':'existing_native_component_point_contradiction'})
if badtrajectories:
 pd.DataFrame(badtrajectories).to_csv(O/'accepted_component_point_hardholds.csv',index=False);badids={z['trajectory_id'] for z in badtrajectories};f=f[~f.trajectory_id.isin(badids)];cr=cr[~cr.trajectory_id.isin(badids)];f.to_csv(O/'accepted_qualified_physical_observations.csv',index=False);cr.to_csv(O/'accepted_selected_source_id_credit_union.csv',index=False);w=pd.read_csv(O/'qualified_own_source_binding_witness.csv');badq={t.split(':')[-1] for t in badids};w=w[~w.qid.isin(badq)];w.to_csv(O/'qualified_own_source_binding_witness.csv',index=False);rec.update(qualified_series=f.trajectory_id.nunique(),qualified_observations=len(f),secondary2002_nonadditive_population_display_only=int(f.loc[f.year.eq(2002),'population_source_value'].sum()),existing_component_point_hardholds=len(badids))

for _,g in f.groupby('trajectory_id'):
 assert set(g.year)=={2002,2010,2021} and len(g)==3;old=g[g.year.eq(2002)].iloc[0];cur=g[g.year.eq(2021)].iloc[0];nat=g[~g.nonadditive_observation];assert old.source_record_id=='' and old.nonadditive_observation and not old.historical_native_selected_source_ID_binding_asserted
 assert s.years[s.uf.find(cur.source_record_id)]=={2010,2021}
 p=Path(old.source_path);assert sha(p)==old.source_sha256;pins[str(p)]=sha(p)
 if p not in entities:
  d=json.loads(gzip.decompress(p.read_bytes()) if p.name.endswith('.gz') else p.read_bytes());entities[p]=d.get('entities',d.get('payload',{}).get('entities',{}))
 e=entities[p][old.wikidata_id];st=next(z for z in e['claims']['P1082'] if z.get('id')==old.statement_id);assert float(st['mainsnak']['datavalue']['value']['amount'])==old.population_source_value;assert st.get('rank')!='deprecated' and not st.get('qualifiers',{}).get('P518');assert any(z.get('datavalue',{}).get('value',{}).get('time')==old.declared_date and z.get('datavalue',{}).get('value',{}).get('precision',0)>=9 for z in st['qualifiers']['P585']);assert old.population_source_value>=0 and math.isfinite(old.population_source_value)
 if old.census_proof_class=='actual_P585_year2002_with_literal_P459_census_method':assert any(z.get('datavalue',{}).get('value',{}).get('id')=='Q39825' for z in st['qualifiers']['P459'])
 else:assert old.declared_date.startswith('+2002-10-09') or any('2002' in t and re.search('перепис|census|впн',t,re.I) for k in ['census_reference_titles_json','P248_labels_json','reference_urls_json'] for t in json.loads(old[k]))
 cp=s.point_rows[cur.source_record_id];p=Path(cp['point_origin_file']);assert sha(p)==cp['point_origin_sha256'];pins[str(p)]=sha(p)
 for row in nat.itertuples():
  r=s.by_id.loc[row.source_record_id];assert int(r.census_year)==row.year and float(r.population)==row.population_source_value and r.population_value_quality==row.population_quality;assert s.uf.find(r.source_record_id)==s.uf.find(cur.source_record_id);assert r.is_additive_settlement_record;assert distance_km((cp['latitude'],cp['longitude']),(s.point_rows[r.source_record_id]['latitude'],s.point_rows[r.source_record_id]['longitude']))<=5
bad=~s.obs.source_record_id.isin(s.point_rows)|~np.isfinite(s.obs.population);badroots=set(s.obs.loc[bad,'root'])|{s.uf.find(i) for i in s.conflicting_point_targets};roots={r for r in s.obs.root.unique() if s.years[r]=={2002,2010,2021} and r not in badroots};finite=set(s.obs.loc[s.obs.root.isin(roots),'source_record_id']);orig=set(finite);direct=set();formation=set()
for n,target in [('complete_publisher_partition_members.csv',orig),('qualified_scope_source_id_credit_union.csv',orig),('named_merger_lineage_constituents.csv',orig),('complete_territorial_scope_constituents.csv',orig),('direct_inclusion_transformation_path_native_credit_union.csv',direct),('formation_path_native_credit_union.csv',formation)]:
 p=E/'native2010_remaining_county_rule_mass_20261008'/('baseline49_union_'+n+'.gz');g=pd.read_csv(p,keep_default_na=False);pins[str(p)]=sha(p)
 if 'source_record_id' in g:target.update(g.source_record_id)
ordinary=s.obs[s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь'])];ordinary=ordinary[~(ordinary.census_year.eq(2021)&ordinary.region_norm.eq('крым'))];axes={'original_mixed_native_ID_union':orig,'direct_lifecycle_native_ID_union':orig|direct,'direct_lifecycle_plus_formation_native_ID_union':orig|direct|formation};new=set(cr.source_record_id);net={};rows=[];base={};after={}
for axis,ids in axes.items():
 base[axis]={str(int(y)):int(g[g.source_record_id.isin(ids)].population.sum()) for y,g in ordinary.groupby('census_year')};after[axis]={str(int(y)):int(g[g.source_record_id.isin(ids|new)].population.sum()) for y,g in ordinary.groupby('census_year')};net[axis]={y:after[axis][y]-base[axis][y] for y in base[axis]}
 for r in ordinary[ordinary.source_record_id.isin(new-ids)].itertuples():rows.append({'axis':axis,'source_record_id':r.source_record_id,'year':r.census_year,'native_population':r.population,'native_quality':r.population_value_quality})
pd.DataFrame(rows).to_csv(O/'exact_exclusive_native_source_ID_gain.csv.gz',index=False,compression={'method':'gzip','mtime':0});assert s.metrics()==before;pd.testing.assert_frame_equal(protected,s.obs[protected.columns]);assert net['original_mixed_native_ID_union']['2002']==0
for p,h in pins.items():assert sha(Path(p))==h,p
rec.update(status='frozen_qualified_secondary2002_current_bound_native_pair_census_sources_independently_verified',source_and_component_replay_passed=True,net_selected_source_ID_credit_by_axis=net,baseline_native_ID_population_by_axis=base,after_native_ID_population_by_axis=after,ordinary_finite_metrics_unchanged=before,no_previous_qualified_QID_overlap='not_asserted_UID_union_deduplicated',new_API_requests=json.loads((O/'network_receipt.json').read_text())['requests'],input_pins=pins)
rec['net_selected_source_ID_credit_by_year']={y:{'population':net['original_mixed_native_ID_union'][y]} for y in ['2002','2010','2021']};rec['output_hashes']={p.name:sha(p) for p in [O/'accepted_qualified_physical_observations.csv',O/'accepted_selected_source_id_credit_union.csv',O/'qualified_own_source_binding_witness.csv',O/'exact_exclusive_native_source_ID_gain.csv.gz',O/'cached_reference_item_witness.csv',O/'qualified_packet_holds.csv']};(O/'qualified_application_receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2));print(json.dumps({'series':rec['qualified_series'],'net':net,'ordinary_graph_unchanged':True},ensure_ascii=False))
