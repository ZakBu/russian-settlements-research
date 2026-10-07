import sys,json
from pathlib import Path
from collections import Counter
import pandas as pd
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km,sha
from build_batch import all3
r=json.loads((OUT/'simulation_receipt.json').read_text())
for path,h in r['source_inputs_sha256'].items():assert sha(Path(path))==h,path
for path,h in r['donor_ledger_sha256'].items():assert sha(Path(path))==h,path
s=load(stage=10);assert s.metrics()==r['baseline_strict_own_point'];ids=set(s.point_rows);assert all3(s,ids)==r['baseline_all_three_own_points']
d=pd.read_csv(OUT/'candidate_point_use_delta.csv',keep_default_na=False);h=pd.read_csv(OUT/'held_components.csv');assert len(d)+len(h)==40;assert not d.target_source_record_id.duplicated().any();collision=Counter((int(s.by_id.loc[x,'census_year']),p['latitude'],p['longitude']) for x,p in s.point_rows.items())
for x in d.to_dict('records'):
 target,donor=x['target_source_record_id'],x['coordinate_source_record_id'];assert target not in ids;assert donor in ids;assert s.uf.find(target)==s.uf.find(donor);assert s.years[s.uf.find(target)]=={2002,2010,2021};assert x['coordinate_admission_status']=='candidate_pending_independent_review';assert x['legal_type_change_asserted'] is False
 p=s.point_rows[donor];assert (float(x['latitude']),float(x['longitude']))==(p['latitude'],p['longitude']);key=(int(s.by_id.loc[target,'census_year']),p['latitude'],p['longitude']);assert collision[key]==0;collision[key]+=1
 for sid in s.obs.loc[s.obs.root.eq(s.uf.find(target)),'source_record_id']:
  if sid in ids:
   q=s.point_rows[sid];assert distance_km((p['latitude'],p['longitude']),(q['latitude'],q['longitude']))<=5
 ids.add(target)
assert all3(s,ids)==r['simulated_after_all_three_own_points'];assert s.metrics(extra_point_ids=d.target_source_record_id.tolist())==r['simulated_after_strict_own_point']
(OUT/'structural_verification.json').write_text(json.dumps({'status':'pass','pinned_input_hashes_match':True,'baseline_reproduced':True,'candidate_targets_previously_unpointed':True,'donors_already_accepted':True,'existing_full3_component_only':True,'zero_new_edges':True,'point_collisions_absent':True,'accepted_anchor_distance_max_5km':True,'both_metrics_reproduced':True,'candidate_status_only':True,'source_population_values_modified':False},indent=2)+'\n')
print('Structural verification pass',len(d))
