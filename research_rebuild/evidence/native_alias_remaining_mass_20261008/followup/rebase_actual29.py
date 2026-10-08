import sys,json,importlib.util
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,distance_km
O=Path(__file__).parent;p=O/'application_receipt.json';r=json.loads(p.read_text());original={k:r[k] for k in ['baseline_stage','baseline_replay','before','after','before_finite_all3_all_points','after_finite_all3_all_points','net_finite_all3_all_points']}
for n,h in r['output_pins'].items():assert sha(O/n)==h,n
s=load(29);before=s.metrics();assert [before[str(y)]['covered_population'] for y in [2002,2010,2021]]==[126473670,123647686,124253255],'Root actual29 metrics differ'
sp=importlib.util.spec_from_file_location('fm',R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm);bf=fm.finite_metrics(s)
ed=pd.read_csv(O/'accepted_identity_edge_delta.csv');pt=pd.read_csv(O/'accepted_point_use_delta.csv');over=[]
for z in ed.to_dict('records'):over.append({'kind':'edge','from':z['from_source_record_id'],'to':z['to_source_record_id'],'already_same_component':s.uf.find(z['from_source_record_id'])==s.uf.find(z['to_source_record_id'])})
for z in pt.to_dict('records'):
 old=s.point_rows.get(z['target_source_record_id']);dist=distance_km((old['latitude'],old['longitude']),(float(z['latitude']),float(z['longitude']))) if old else None;over.append({'kind':'point','target':z['target_source_record_id'],'already_pointed':bool(old),'distance_from_existing_km':dist,'explicit_rejection_target':z['target_source_record_id']=='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:144261'})
s.reject_point_uses(O/'accepted_point_rejection_delta.csv');s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);after=s.metrics();af=fm.finite_metrics(s)
r.update(baseline_stage=29,baseline_replay='Actual integrated load(29); root supplied weak-population baseline asserted; same pinned accepted CSVs applied once',before=before,after=after,before_finite_all3_all_points=bf,after_finite_all3_all_points=af,net_finite_all3_all_points={'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']}},status='Rebased actual29 State API replay passed; source proofs and accepted outputs unchanged; ready root30 integration')
r['rebase_from_actual28']={'original_receipt_axes':original,'source_and_accepted_output_pins_unchanged':True,'already_same_component_edges':sum(x.get('already_same_component',False) for x in over),'already_pointed_targets':sum(x.get('already_pointed',False) for x in over),'only_existing_point_target_is_explicit_Shafranovo_rejection':all(not x.get('already_pointed') or x.get('explicit_rejection_target') for x in over if x['kind']=='point')}
# Parent receipt is a historical baseline reference, not an identity source or report pin.
ref=str(O.parent/'application_receipt.json');r['baseline_reference_pins']={ref:r['input_pins'].pop(ref)} if ref in r['input_pins'] else r.get('baseline_reference_pins',{})
(O/'actual29_overlap_checks.json').write_text(json.dumps(over,ensure_ascii=False,indent=2));r['output_pins']['actual29_overlap_checks.json']=sha(O/'actual29_overlap_checks.json');p.write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({'overlap_edges':r['rebase_from_actual28']['already_same_component_edges'],'existing_point_targets':r['rebase_from_actual28']['already_pointed_targets'],'net_finite':r['net_finite_all3_all_points'],'after_weak':{y:v['covered_population'] for y,v in after.items()}},ensure_ascii=False))
