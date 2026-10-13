"""Replay only; independent identity admission remains with the reviewer."""
import sys,json
from pathlib import Path
import pandas as pd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from build_batch import alias,exact_name,PREFIX_TYPES
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).resolve().parent
r=json.loads((OUT/'simulation_receipt.json').read_text());s=load(r['working_state_stage']);assert s.metrics()==r['baseline']
for p,h in r['inputs_sha256'].items():assert sha(Path(p))==h,p
for p,h in r['outputs_sha256'].items():assert sha(OUT/p)==h,p
edges=pd.read_csv(OUT/'candidate_identity_edge_delta.csv',keep_default_na=False);points=pd.read_csv(OUT/'candidate_point_use_delta.csv',keep_default_na=False)
assert not points.target_source_record_id.duplicated().any()
for e in edges.to_dict('records'):
 a,b=e['from_source_record_id'],e['to_source_record_id'];aa,bb=s.by_id.loc[a],s.by_id.loc[b]
 assert alias(aa.settlement_name,aa.settlement_type)[0]==alias(bb.settlement_name,bb.settlement_type)[0]==e['name_norm']
 assert exact_name(aa.settlement_name)!=exact_name(bb.settlement_name)
 assert normalize(aa.region_norm)==normalize(bb.region_norm)==e['region_norm']
 if e['county_rule']=='explicit_same_county':assert county_key(aa.district_raw)==county_key(bb.district_raw)==e['county_key']
 assert e['decision_status']=='candidate_pending_independent_review'
 assert s.union(a,b),'Not a distinct new UF edge'
for p in points.to_dict('records'):
 tid,donor=p['target_source_record_id'],p['coordinate_source_record_id'];assert tid not in s.point_rows
 assert s.uf.find(tid)==s.uf.find(donor)
 dp=s.point_rows[donor];assert distance_km((float(p['latitude']),float(p['longitude'])),(dp['latitude'],dp['longitude']))<1e-8
 assert p['coordinate_admission_status']=='candidate_pending_independent_review'
 s.point_rows[tid]=p
assert s.metrics()==r['simulated_after']
# Lexical letters and numbers remain intact; parsed type controls applicability.
checks=[('п Красные Ткачи','поселок','красные ткачи'),('п. Красные Ткачи','посёлок','красные ткачи'),('пгт Тырма','пгт','тырма'),('д. Новая 2','деревня','новая 2'),('с. Ёлки','село','ёлки'),('п Мира','село','п мира'),('ст. Станица','станица','станица'),('Петрово','поселок','петрово')]
for n,t,want in checks:assert alias(n,t)[0]==want,(n,t)
raw=pd.read_csv(OUT/'sampled_raw_source_checks.csv',keep_default_na=False);assert set(raw.status)=={'literal_name_hash_county_pass'}
raw_coordinate_distances={}
for row in raw.to_dict('records'):
 if str(row['source_file']).endswith('.parquet'):
  native=json.loads(row['raw_row_literal']);lat,lon=native.get('latitude_dadata'),native.get('longitude_dadata')
  if lat is not None and lon is not None:
   p=s.point_rows[row['source_record_id']];distance=distance_km((float(lat),float(lon)),(float(p['latitude']),float(p['longitude'])))
   assert distance<=5,'Raw current provider coordinate contradicts donor'
   raw_coordinate_distances[row['source_record_id']]=distance
result={'status':'passed_structural_replay_not_independent_identity_admission','stage':r['working_state_stage'],'distinct_new_unions':len(edges),'unique_new_point_targets':len(points),'raw_endpoint_checks':len(raw),'raw_native_provider_point_distances_km':raw_coordinate_distances,'compatible_prefix_parser_checks':len(checks),'baseline_and_simulated_after_match':True,'source_population_values_modified':False,'source_district_values_modified':False}
(OUT/'structural_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result))
