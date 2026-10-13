import json,hashlib,math
from pathlib import Path
import pandas as pd, duckdb
O=Path('/workspace/settlements-work/continuation_20261004/independent_review/admin_homonym_834_point_review')
I=Path('/workspace/settlements-work/continuation_20261004/root/point_gap_spatial_diagnostic_after_afipsky/name_collision_admin_context_diagnostic')
SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def tofloat(x):
 try:return float(str(x).strip().replace(',','.'))
 except:return None

df=pd.read_csv(O/'full_vector_replay.csv',engine='python')
df=df.drop(columns=[c for c in ['source_raw_latitude','source_raw_longitude','nearest_GN_latitude','nearest_GN_longitude'] if c in df.columns])
cand=pd.read_csv(I/'reviewed_ready_834_admin_homonym_point_candidates.csv',engine='python',usecols=['target_source_record_id','source_raw_latitude','source_raw_longitude','nearest_GN_latitude','nearest_GN_longitude'])
df=df.merge(cand,on='target_source_record_id',how='left',validate='one_to_one')
ctx=pd.read_csv(I/'reviewed_ready_834_admin_homonym_point_candidates.csv',engine='python',usecols=['target_source_record_id','accepted_component_old_2002_2010_context_json'])
ctxmap={r.target_source_record_id:json.loads(r.accepted_component_old_2002_2010_context_json) for r in ctx.itertuples(index=False)}
allids=sorted({str(x['id']) for v in ctxmap.values() for x in v if str(x.get('year')) in {'2002','2010'}})
db=duckdb.connect(config={'threads':1,'memory_limit':'1GB'})
db.register('ids',pd.DataFrame({'source_record_id':allids}))
rows=db.execute(f"SELECT source_record_id,population FROM read_parquet('{SEL}') s INNER JOIN ids USING(source_record_id)").fetchall()
popmap={str(a):float(b) for a,b in rows}
numcorrect=0
for ix,r in df.iterrows():
 checks=json.loads(r.historical_raw_row_checks_json); old=[x for x in ctxmap[r.target_source_record_id] if str(x.get('year')) in {'2002','2010'}]
 if len(checks)!=2 or len(old)!=2: raise RuntimeError('historical replay cardinality changed')
 ok=True
 for check,m in zip(checks,old):
  expected=popmap[str(m['id'])]
  samples=[tofloat(x) for x in check.get('raw_row_values_sample',[])]
  match=any(x is not None and abs(x-expected)<1e-8 for x in samples)
  check['selected_population_expected']=expected
  check['raw_row_population_match']=match
  check['raw_population_text_numeric_parse_applied']=True
  ok=ok and check.get('status')=='raw_row_replayed' and check.get('raw_row_name_match') and check.get('raw_row_type_match') and match
 df.at[ix,'historical_raw_row_checks_json']=json.dumps(checks,ensure_ascii=False)
 df.at[ix,'both_historical_raw_rows_name_type_population_replayed']=bool(ok)
 if ok:numcorrect+=1
 # Proposed coordinate columns are copied from the exact raw source row verified above.
 df.at[ix,'proposed_coordinate_latitude']=float(r.source_raw_latitude)
 df.at[ix,'proposed_coordinate_longitude']=float(r.source_raw_longitude)
 df.at[ix,'proposed_coordinate_origin']='2021 Tochno source parquet raw latitude_dadata/longitude_dadata exact row'
 df.at[ix,'coordinate_use_scope']='current 2021 source-point candidate only; GeoNames is corroborating witness only and its coordinates are not substituted'
 df.at[ix,'geonames_latitude']=r.nearest_GN_latitude
 df.at[ix,'geonames_longitude']=r.nearest_GN_longitude
 oldhold=str(r.hold_reasons or '')
 if ok:
  df.at[ix,'eligible_scoped_point_seed']=True
  df.at[ix,'hold_reasons']=''
 else:
  df.at[ix,'eligible_scoped_point_seed']=False
  df.at[ix,'hold_reasons']='both_historical_publisher_rows_replayed_name_type_population'
# Serialize finalized vectors and explicit subsets.
elig=df[df.eligible_scoped_point_seed].copy(); held=df[~df.eligible_scoped_point_seed].copy()
risk=pd.read_csv(O/'fixed_risk_sample.csv',engine='python')
risk=risk.drop(columns=[c for c in ['proposed_coordinate_latitude','proposed_coordinate_longitude','coordinate_use_scope','geonames_latitude','geonames_longitude','both_historical_raw_rows_name_type_population_replayed','eligible_scoped_point_seed','hold_reasons'] if c in risk.columns])
risk=risk.merge(df[['target_source_record_id','proposed_coordinate_latitude','proposed_coordinate_longitude','coordinate_use_scope','geonames_latitude','geonames_longitude','both_historical_raw_rows_name_type_population_replayed','eligible_scoped_point_seed','hold_reasons']],on='target_source_record_id',how='left',validate='one_to_one')
df.to_csv(O/'full_vector_replay.csv',index=False); elig.to_csv(O/'eligible_point_seedlist.csv',index=False); held.to_csv(O/'held_candidates.csv',index=False); risk.to_csv(O/'fixed_risk_sample.csv',index=False)
receipt=json.load(open(O/'independent_review_receipt.json'))
receipt['counts']['historical_rows_name_type_population_match']=numcorrect
receipt['counts']['eligible_rows']=len(elig); receipt['counts']['held_rows']=len(held)
receipt['counts']['eligible_population']=float(elig.candidate_population.sum()); receipt['counts']['held_population']=float(held.candidate_population.sum())
receipt['counts']['raw_population_numeric_strings_parsed']=True
receipt['counts']['coordinate_columns_scope']='raw 2021 Tochno latitude/longitude are proposed; GeoNames coordinates are separate corroboration only'
for f in ['eligible_point_seedlist.csv','held_candidates.csv','full_vector_replay.csv','fixed_risk_sample.csv']:
 p=O/f; receipt['outputs'][f]={'path':str(p),'sha256':sha(p),'rows':len(pd.read_csv(p,engine='python'))}
receipt['status']='independent_review_candidate_point_seed_only'
receipt['methods']['historical_raw_population_replay']='The 2002 workbooks encode population cells both numerically and as digit strings; the direct replay parser reads either representation and compares to the exact selected endpoint value.'
rp=O/'independent_review_receipt.json'; rp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps({'receipt':str(rp),'sha256':sha(rp),'eligible_rows':len(elig),'eligible_population':float(elig.candidate_population.sum()),'held_rows':len(held),'held_population':float(held.candidate_population.sum()),'historical_rows_matched':numcorrect,'eligible_sha256':sha(O/'eligible_point_seedlist.csv'),'risk_sha256':sha(O/'fixed_risk_sample.csv')},ensure_ascii=False,indent=2))
