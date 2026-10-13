import sys,json,importlib.util
from pathlib import Path
import pandas as pd
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
import current_chain_state_20261007 as m
rawsha=m.sha; cache={}
def sha(p):
 p=Path(p); st=p.stat();k=(str(p),st.st_size,st.st_mtime_ns)
 if k not in cache:cache[k]=rawsha(p)
 return cache[k]
m.sha=sha
from frozen_working_state58 import load
receipt=json.loads((O/'application_receipt.json').read_text())
for p,h in receipt['input_pins'].items():assert sha(p)==h,p
for p,h in receipt['output_pins'].items():assert sha(O/p)==h,p
s=load(58);protected=s.obs[['source_record_id','population','population_value_quality']].copy();graph={i:s.uf.find(i) for i in s.by_id.index};spec=importlib.util.spec_from_file_location('ff',O.parent/'native_singleton_rural_mass_20261008/frozen_finite.py');ff=importlib.util.module_from_spec(spec);spec.loader.exec_module(ff);assert ff.finite(s)==receipt['before_finite']
rej=pd.read_csv(O/'point_use_rejections.csv.gz');delta=pd.read_csv(O/'accepted_point_use_delta.csv.gz');assert rej.target_source_record_id.is_unique;assert delta.target_source_record_id.is_unique;assert set(delta.target_source_record_id)<=set(rej.target_source_record_id)
s.reject_point_uses(O/'point_use_rejections.csv.gz');s.add_deltas(point_paths=[O/'accepted_point_use_delta.csv.gz']);assert ff.finite(s)==receipt['after_finite'];pd.testing.assert_frame_equal(protected,s.obs[protected.columns]);assert graph=={i:s.uf.find(i) for i in s.by_id.index}
w=pd.read_csv(O/'owncoded_coordinate_consistency_witnesses.csv.gz',keep_default_na=False)
for z in w.to_dict('records'):
 sid=z['current_source_record_id'];assert (sid in s.point_rows)==bool(z['point_recovered'])
 if z['point_recovered']:assert s.point_rows[sid]['coordinate_source_record_id']==z['own_coded_TSV_QID']
inv=pd.read_csv(O/'corrected_carrier_component_inventory.csv.gz',keep_default_na=False);geo=inv[inv.point_json.map(lambda x:'GeoKLADR' in json.loads(x).get('point_origin_kind',''))];geo[['current_source_record_id']].to_csv(O/'new_Geo_rule_carrier_scope.csv.gz',index=False,compression={'method':'gzip','mtime':0})
rows=[]
for q,n in [('Q18770981',100694),('Q23976086',93300)]:
 sid='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'+str(n);pp=s.point_rows.get(sid);rows.append({'trajectory_id':'wikidata_secondary_expansion:'+q,'native_current_source_record_id':sid,'decision':'replace_qualified_point_with_independent_owncoded_physical_point' if pp else 'hold_qualified_point_scope_pending_independent_own_physical_point','years_affected_json':'[2002,2010,2021]','identity_and_population_values_unchanged':True,'point_json':json.dumps(pp,ensure_ascii=False) if pp else '', 'rejection_ledger':str(O/'point_use_rejections.csv.gz'),'rejection_ledger_sha256':sha(O/'point_use_rejections.csv.gz'),'replacement_ledger':str(O/'accepted_point_use_delta.csv.gz'),'replacement_ledger_sha256':sha(O/'accepted_point_use_delta.csv.gz')})
pd.DataFrame(rows).to_csv(O/'qualified_scope_point_actions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
r={'status':'PASS independent fresh State58 replay and all input/output SHA pins','rejected_uses':len(rej),'replacement_uses':len(delta),'Geo_scope_carriers':len(geo),'after_finite':ff.finite(s),'raw_census_population_quality_unchanged':True,'identity_edges_unchanged':True,'checked_code_files':{str(O/'verify.py'):sha(O/'verify.py')}};(O/'independent_replay_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
