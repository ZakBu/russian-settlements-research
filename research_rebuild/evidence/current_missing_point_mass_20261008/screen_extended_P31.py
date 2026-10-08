from pathlib import Path
import json,sys,collections
import duckdb,pandas as pd
O=Path(__file__).parent;E=O.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import distance_km,sha
P=E/'temporal_residual_mass_20261008/SHARED_points_compact_stage61.parquet';C=E/'temporal_residual_mass_20261008/SHARED_component_snapshot_stage61.csv.gz'
e=pd.read_csv(O/'accepted_extended_P31_source_bound_ownpoint_evidence.csv.gz',keep_default_na=False);p=pd.read_csv(O/'accepted_extended_P31_point_use_delta.csv.gz',keep_default_na=False);c=duckdb.connect();print(c.execute('describe select * from read_parquet(?)',[str(P)]).fetchdf().column_name.tolist());a=c.execute('select * from read_parquet(?)',[str(P)]).fetchdf();c.close();newpaths=[O/n for n in ['accepted_point_use_delta.csv.gz','accepted_provider_lexical_point_use_delta.csv.gz','accepted_top4_article_point_use_delta.csv.gz']];a=pd.concat([a,*[pd.read_csv(n).rename(columns={'target_source_record_id':'source_record_id'}) for n in newpaths]],ignore_index=True);index=a.set_index('target_source_record_id') if 'target_source_record_id' in a else a.set_index('source_record_id');occupied=collections.defaultdict(set)
for sid,z in index.iterrows():
 if str(sid).startswith('2021:'):occupied[(float(z.latitude),float(z.longitude))].add(sid)
holds=[];passed=[]
for z in e.to_dict('records'):
 sid=z['source_record_id'];point=p[p.target_source_record_id.eq(sid)].iloc[0];xy=(point.latitude,point.longitude);reasons=[];far=[]
 if occupied[xy]-{sid}:reasons.append('same_coordinate_other_current_accepted_NP')
 for target in str(z['component_source_ids']).split('|'):
  if target not in index.index:continue
  pp=index.loc[target];d=distance_km(xy,(float(pp.latitude),float(pp.longitude)))
  if d>5:far.append({'source_record_id':target,'distance_km':d,'accepted_origin_file':pp.get('point_origin_file','')})
 if far:reasons.append('accepted_component_ownpoint_over5km_conflict')
 if reasons:holds.append({**z,'point_conflict_hold_reasons':';'.join(reasons),'point_conflict_witnesses_json':json.dumps(far,ensure_ascii=False),'other_current_point_occupants_json':json.dumps(sorted(occupied[xy]-{sid}))})
 else:passed.append(z)
ids={z['source_record_id'] for z in passed};q=p[p.target_source_record_id.isin(ids)];q.to_csv(O/'accepted_extended_P31_point_use_delta_component_screened.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(passed).to_csv(O/'accepted_extended_P31_source_bound_ownpoint_evidence_component_screened.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(holds).to_csv(O/'extended_P31_component_point_conflict_holds.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'baseline_stage':61,'original':len(p),'screened_accepted':len(q),'point_conflict_holds':len(holds),'known_population2021':sum(float(z['population']) for z in passed if str(z['population'])),'input_pins':{str(x):sha(x) for x in [P,C,O/'screen_extended_P31.py',O/'accepted_extended_P31_point_use_delta.csv.gz',O/'accepted_extended_P31_source_bound_ownpoint_evidence.csv.gz']}};(O/'extended_P31_component_screen_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='input_pins'}))
