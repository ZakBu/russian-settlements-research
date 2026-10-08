import sys,json,importlib.util,collections
from pathlib import Path
import pandas as pd
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'));sys.path.insert(0,str(O))
from frozen_working_state56 import load
import current_chain_state_20261007 as module
original_sha=module.sha;cache={}
def sha(p):
 p=Path(p);st=p.stat();key=(str(p),st.st_size,st.st_mtime_ns)
 if key not in cache:cache[key]=original_sha(p)
 return cache[key]
module.sha=sha
sp=importlib.util.spec_from_file_location('ff',O.parent/'native_singleton_rural_mass_20261008/frozen_finite.py');ff=importlib.util.module_from_spec(sp);sp.loader.exec_module(ff)
r=json.loads((O/'application_receipt.json').read_text());identity=json.loads((O/'history_fullraw_rival_identity_receipt.json').read_text());r['input_pins'].update(identity['input_pins']);r['input_pins'][str(O/'verify.py')]=sha(O/'verify.py')
for p,h in r['input_pins'].items():assert sha(Path(p))==h,p
s=load(56);before=ff.finite(s);assert before==r['before_finite'];protected=s.obs[['source_record_id','population','population_value_quality']].copy();graph={sid:s.uf.find(sid) for sid in s.by_id.index};original=dict(s.point_rows)
s.reject_point_uses(O/'point_use_rejections.csv.gz');s.add_deltas(point_paths=[O/'accepted_point_use_delta.csv.gz']);after=ff.finite(s);pd.testing.assert_frame_equal(protected,s.obs[protected.columns]);assert graph=={sid:s.uf.find(sid) for sid in s.by_id.index}
rejections=pd.read_csv(O/'point_use_rejections.csv.gz');points=pd.read_csv(O/'accepted_point_use_delta.csv.gz');w=pd.read_csv(O/'fullraw_own_code_point_recovery_witnesses.csv.gz',keep_default_na=False);known=set(w.source_record_id);ownpoints=set(points.loc[points.target_source_record_id.str.startswith('2021:'),'target_source_record_id']);q=O.parent/'cached_current_bound_secondary2002_mass_20261008/accepted_qualified_physical_observations.csv.gz';secondary=pd.read_csv(q,keep_default_na=False);intersection=secondary[secondary.native_current_source_record_id.isin(known)].copy();intersection['coordinate_correction_status']=intersection.native_current_source_record_id.map(lambda sid:'own_point_recovered' if sid in ownpoints else 'point_hold_required');out=O/'secondary26_point_risk_intersections.csv.gz';intersection.to_csv(out,index=False,compression={'method':'gzip','mtime':0});r['input_pins'][str(q)]=sha(q)
# Every active exact-ID/coordinate clone from an affected component must be rejected; correct independent old claims remain.
for sid in known:
 if sid not in original:continue
 carrier=original[sid];root=s.uf.find(sid)
 for target in s.obs.loc[s.obs.root.eq(root),'source_record_id']:
  if target not in original:continue
  old=original[target]
  if target==sid or (str(old.get('coordinate_source_record_id',''))==str(carrier.get('coordinate_source_record_id','')) and (old['latitude'],old['longitude'])==(carrier['latitude'],carrier['longitude'])):assert target in set(rejections.target_source_record_id),target
r.update(status='independent actual56 exact point rejection/replacement replay passed; graph and population/quality unchanged',after_finite=after,net_finite_histories=after['histories']-before['histories'],net_finite_population_by_year={y:after['populations_by_year'][y]-before['populations_by_year'][y] for y in before['populations_by_year']},accepted_replacement_point_uses=len(points),recovered_current_carriers=len(ownpoints),held_current_carriers=len(known-ownpoints),secondary26_intersection_trajectories=intersection.trajectory_id.nunique(),historical_identity_point_reuse_holds=identity['historical_point_reuse_identity_holds'])
for filename in ['point_use_rejections.csv.gz','accepted_point_use_delta.csv.gz','fullraw_own_code_point_recovery_witnesses.csv.gz','recovery_holds.csv.gz','recovered_history_fullraw_rival_identity_checks.csv.gz','history_fullraw_rival_identity_receipt.json','secondary26_point_risk_intersections.csv.gz']:r['output_pins'][filename]=sha(O/filename)
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');result={k:r[k] for k in ['baseline_stage','status','before_finite','after_finite','net_finite_histories','net_finite_population_by_year','rejection_uses','accepted_replacement_point_uses','recovered_current_carriers','held_current_carriers','secondary26_intersection_trajectories','historical_identity_point_reuse_holds']};(O/'independent_replay_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
