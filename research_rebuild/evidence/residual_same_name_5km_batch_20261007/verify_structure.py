"""Recheck proposed edges against pinned accepted snapshot without accepting candidates."""
import json,sys
from pathlib import Path
import pandas as pd
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parents[1]/'mass_linkage'))
from working_state_20261007 import load
from build_batch import norm
from current_chain_state_20261007 import sha,distance_km
r=json.loads((OUT/'simulation_receipt.json').read_text())
for path,h in r['inputs_sha256'].items():assert sha(Path(path))==h,path
s=load();assert s.metrics()==r['baseline']
d=pd.read_csv(OUT/'candidate_identity_edge_delta.csv',keep_default_na=False);p=pd.read_csv(OUT/'candidate_point_use_delta.csv',keep_default_na=False)
lookup={}
for sid,pt in s.point_rows.items():
 x=s.by_id.loc[sid];lookup.setdefault((norm(x.settlement_name),norm(x.region_norm),int(x.census_year)),[]).append(sid)
ratios=[]
for x in d.to_dict('records'):
 a,b=x['from_source_record_id'],x['to_source_record_id'];ar,br=s.by_id.loc[a],s.by_id.loc[b];ap,bp=s.point_rows[a],s.point_rows[b]
 assert x['decision_status']=='candidate_pending_independent_review'
 assert norm(ar.settlement_name)==norm(br.settlement_name)==x['name_norm']
 assert norm(ar.region_norm)==norm(br.region_norm)==x['region_norm']
 assert distance_km((ap['latitude'],ap['longitude']),(bp['latitude'],bp['longitude']))<=5
 for v,targetyear in [(a,int(br.census_year)),(b,int(ar.census_year))]:
  pt=s.point_rows[v];near=[z for z in lookup[(x['name_norm'],x['region_norm'],targetyear)] if distance_km((pt['latitude'],pt['longitude']),(s.point_rows[z]['latitude'],s.point_rows[z]['longitude']))<=5]
  assert len(near)==1,(v,near)
 assert s.uf.find(a)!=s.uf.find(b)
 s.union(a,b)
 if ar.population and br.population:
  ratio=max(float(ar.population),float(br.population))/min(float(ar.population),float(br.population))
  if ratio>=3:ratios.append({'from_source_record_id':a,'to_source_record_id':b,'from_population':ar.population,'to_population':br.population,'max_min_ratio':ratio,'population_values_modified':False,'boundary_comparability_asserted':False})
for x in p.to_dict('records'):
 assert x['coordinate_admission_status']=='candidate_pending_independent_review'
 s.point_rows[x['target_source_record_id']]=x
assert s.metrics()==r['simulated_after']
pd.DataFrame(ratios,columns=['from_source_record_id','to_source_record_id','from_population','to_population','max_min_ratio','population_values_modified','boundary_comparability_asserted']).to_csv(OUT/'population_ratio_flags.csv',index=False)
(OUT/'structural_verification.json').write_text(json.dumps({'status':'pass','candidate_edges':len(d),'candidate_point_uses':len(p),'input_hashes_match':True,'baseline_reproduced':True,'mutual_unique_spatial_rechecked':True,'all_unions_distinct_and_no_repeated_year':True,'simulation_metrics_reproduced':True,'population_ratio_ge3_flags':len(ratios),'admission_performed':False},indent=2)+'\n')
print('Structural checks pass',len(d),len(p))
