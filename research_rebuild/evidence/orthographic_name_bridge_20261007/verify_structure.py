import sys,json
from pathlib import Path
import pandas as pd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from build_batch import station_alias,exact_name
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).resolve().parent
s=load(stage=10); receipt=json.loads((OUT/'simulation_receipt.json').read_text());assert s.metrics()==receipt['baseline'],'Baseline drift'
for p,h in receipt['inputs_sha256'].items():assert sha(Path(p))==h,'Pinned input changed: '+p
edges=pd.read_csv(OUT/'candidate_identity_edge_delta.csv',keep_default_na=False);points=pd.read_csv(OUT/'candidate_point_use_delta.csv',keep_default_na=False);assert not points.target_source_record_id.duplicated().any()
for r in edges.to_dict('records'):
 a,b=r['from_source_record_id'],r['to_source_record_id'];aa,bb=s.by_id.loc[a],s.by_id.loc[b]
 assert s.uf.find(a)!=s.uf.find(b)
 assert station_alias(aa.settlement_name)[0]==station_alias(bb.settlement_name)[0]==r['name_norm']
 assert exact_name(aa.settlement_name)!=exact_name(bb.settlement_name)
 assert normalize(aa.region_norm)==normalize(bb.region_norm)==r['region_norm']
 assert county_key(aa.district_raw)==county_key(bb.district_raw)==r['county_key']
 assert r['decision_status']=='candidate_pending_independent_review'
 assert s.union(a,b)
for p in points.to_dict('records'):
 tid,donor=p['target_source_record_id'],p['coordinate_source_record_id'];assert tid not in s.point_rows
 assert s.uf.find(tid)==s.uf.find(donor)
 dp=s.point_rows[donor];assert distance_km((float(p['latitude']),float(p['longitude'])),(dp['latitude'],dp['longitude']))<1e-8
 assert p['coordinate_admission_status']=='candidate_pending_independent_review'
 s.point_rows[tid]=p
assert s.metrics()==receipt['simulated_after']
result={'status':'passed_structural_replay_not_independent_identity_admission','distinct_new_unions':len(edges),'unique_new_point_targets':len(points),'baseline_matches_pinned_receipt':True,'simulated_after_matches':True,'source_population_values_modified':False,'source_district_modified':False}
(OUT/'structural_verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
