from pathlib import Path
import duckdb,pandas as pd,sys,json,collections
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;A=O.parent/'main_axis_residual_application63_20261008';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'));from current_chain_state_20261007 import sha,distance_km
F=O/'independent_named_current_candidates.csv.gz';P=A/'applied_point_snapshot.parquet';C=A/'applied_component_snapshot.csv.gz';f=pd.read_csv(F,dtype=str,keep_default_na=False);c=duckdb.connect();p=c.execute('select target_source_record_id as source_record_id,latitude,longitude,coordinate_admission_status from read_parquet(?)',[str(P)]).fetchdf().set_index('source_record_id').to_dict('index');c.close();cs=pd.read_csv(C,dtype=str,keep_default_na=False).set_index('source_record_id');members=cs.groupby('root').apply(lambda g:g.index.tolist(),include_groups=False).to_dict();occ=collections.defaultdict(set)
for i,z in p.items():
 if i.startswith('2021:'):occ[(float(z['latitude']),float(z['longitude']))].add(i)
a=[];h=[];w=[]
for z in f.to_dict('records'):
 sid=z['target_source_record_id'];xy=float(z['latitude']),float(z['longitude']);reasons=[]
 if sid in p:reasons.append('already accepted current ownpoint in actual63')
 if occ[xy]-{sid}:reasons.append('another accepted current native NP occupies source point')
 ids=members[cs.loc[sid,'root']]
 for i in ids:
  if i in p and distance_km(xy,(float(p[i]['latitude']),float(p[i]['longitude'])))>5:reasons.append('actual accepted component ownpoint >5km; independent source relocation/object resolution required')
 if reasons:h.append({**z,'held_reason':'; '.join(sorted(set(reasons)))});continue
 point={k:z[k] for k in ['target_source_record_id','latitude','longitude','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_binding_rule','external_provider_ID_binding_asserted','historical_census_coordinate_asserted']};point.update(coordinate_admission_status='reviewed_extension_rule_accepted',point_use_inference='current_ownphysicalNP_independent_named_point_with_exactcoded_source_corroboration; identical source object duplicates folded, not multiple places',population_boundary_comparability_asserted=False);a.append(point);w.append(z);p[sid]=point;occ[xy].add(sid)
for n,x in [('accepted_current_point_delta.csv.gz',a),('accepted_current_source_witnesses.csv.gz',w),('current_admission_holds.csv.gz',h)]:pd.DataFrame(x).to_csv(O/n,index=False,compression={'method':'gzip','mtime':0})
r={'baseline_stage':63,'no_State_load':True,'accepted_current_ownpoints':len(a),'held_current_points':len(h),'known2021_candidate_population_admitted_point_not_coverage_gain':sum(float(z['population']) for z in w if z['population']),'input_pins':{str(q):sha(q) for q in [F,P,C,A/'application_receipt.json',O/'independent_named_candidate_receipt.json']},'output_pins':{str(O/n):sha(O/n) for n in ['accepted_current_point_delta.csv.gz','accepted_current_source_witnesses.csv.gz','current_admission_holds.csv.gz']}};(O/'current_admission_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
