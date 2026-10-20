#!/usr/bin/env python3
"""Expand geography beyond complete three-census chains without inventing missing observations."""
from pathlib import Path
import base64,hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1];OUT=ROOT/'axis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def uid(root):return 'npX:'+base64.urlsafe_b64encode(hashlib.sha256(str(root).encode()).digest()).decode().rstrip('=')
def build():
 master=REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet'
 source=REPO/'publication/stage71/applied_state_observations.parquet'
 points=REPO/'publication/stage71/applied_point_snapshot.parquet'
 old=pd.read_parquet(master,columns=['id','name','type','region','lat','lon','population_2002','population_2010','population_2021','source_record_id_2002','source_record_id_2010','source_record_id_2021','municipality_oktmo8_2021','municipality_upper_2021'])
 s=pd.read_parquet(source);assert not s.duplicated(['root','census_year']).any()
 source_to_old={}
 for y in [2002,2010,2021]:
  for k,v in zip(old[f'source_record_id_{y}'],old.id):
   if pd.notna(k):
    assert k not in source_to_old or source_to_old[k]==v
    source_to_old[k]=v
 s['old_id']=s.source_record_id.map(source_to_old)
 rooted=s.dropna(subset=['old_id']).groupby('root').old_id.agg(lambda x:sorted(set(x)))
 assert rooted.map(len).max()==1
 root_to_old={root:values[0] for root,values in rooted.items()}
 s['id']=[root_to_old.get(root,uid(root)) for root in s.root]
 assert set(old.id)<=set(s.id)
 p=pd.read_parquet(points,columns=['target_source_record_id','latitude','longitude','coordinate_admission_status','point_origin_kind','coordinate_measurement_date_unknown'])
 accepted={'reviewed_extension_rule_accepted','reviewed_rule_accepted','reviewed_case_accepted','frozen_r5b_reviewed_baseline_preserved'}
 assert set(p.coordinate_admission_status)<=accepted
 assert p.target_source_record_id.is_unique
 for c in ['latitude','longitude']:p[c]=pd.to_numeric(p[c],errors='raise')
 s=s.merge(p,left_on='source_record_id',right_on='target_source_record_id',how='left',suffixes=('_raw','_accepted'),validate='one_to_one')
 extra=s[~s.id.isin(old.id)].copy();extra['has_accepted_point']=extra.latitude_accepted.notna()&extra.longitude_accepted.notna()
 # Prefer the latest available accepted point; every point remains a separately dated source claim.
 meta=extra.sort_values(['census_year','has_accepted_point'],ascending=[False,False]).drop_duplicates('id').set_index('id')
 bestpoint=extra[extra.has_accepted_point].sort_values('census_year',ascending=False).drop_duplicates('id').set_index('id')
 a=pd.DataFrame(index=meta.index)
 for dst,src in [('name','settlement_name'),('type','settlement_type'),('region','region_norm')]:a[dst]=meta[src]
 a['lat']=bestpoint.latitude_accepted;a['lon']=bestpoint.longitude_accepted
 for y in [2002,2010,2021]:
  yy=extra[extra.census_year.eq(y)].set_index('id')
  for dst,src in [(f'population_{y}','population'),(f'source_record_id_{y}','source_record_id'),(f'population_value_quality_{y}','population_value_quality'),(f'district_raw_{y}','district_raw'),(f'oktmo_{y}','oktmo'),(f'okato_{y}','okato')]:a[dst]=yy[src]
 a['root']=meta.root;a['latest_observation_year']=meta.census_year
 a['is_additive_source_unit']=extra.groupby('id').is_additive_settlement_record.all()
 a['axis_kind']='additional_dated_source_entity'
 a['three_census_complete']=a[[f'population_{y}' for y in [2002,2010,2021]]].notna().all(axis=1)
 a['geography_status']=np.where(a.lat.notna(),'accepted_point_latest_observation_not_proven_historical_boundary','unlocated_source_entity')
 a['population_scope']=meta.population_scope
 a['municipality_oktmo8_2021']=a.oktmo_2021.map(lambda x:str(x)[:8] if pd.notna(x) and str(x).isdigit() and len(str(x))==11 else None)
 a['municipality_upper_2021']=a.get('district_raw_2021')
 # Federal city-labelled territorial totals are not treated as physical settlement histories.
 fed=a.name.isin(['Москва','Санкт-Петербург','Севастополь'])&a.type.fillna('').str.contains('город',case=False)
 a.loc[fed,'axis_kind']='federal_territory_source_unit'
 old['axis_kind']='baseline_accepted_complete_chain';old['three_census_complete']=True;old['is_additive_source_unit']=True;old['geography_status']='frozen_accepted_chain_point'
 frame=pd.concat([old,a.reset_index()],ignore_index=True,sort=False)
 assert frame.id.is_unique and len(frame)==s.id.nunique()
 for c in ['lat','lon','population_2002','population_2010','population_2021']:frame[c]=pd.to_numeric(frame[c],errors='raise')
 for y in [2002,2010,2021]:
  joined=frame.set_index('id').reindex(old.id)[f'population_{y}']
  np.testing.assert_array_equal(joined.values,old[f'population_{y}'].values)
 frame.to_parquet(OUT/'full_settlement_axis.parquet',index=False)
 s[['id','root','source_record_id','census_year','population','population_value_quality','is_additive_settlement_record','latitude_accepted','longitude_accepted','coordinate_admission_status','point_origin_kind']].to_parquet(OUT/'source_observations_all.parquet',index=False)
 frame[frame.lat.isna()|~frame.is_additive_source_unit].to_csv(OUT/'unlocated_or_nonadditive_queue.csv.gz',index=False)
 receipt={'status':'EXPANDED_SOURCE_ENTITY_AXIS_NOT_CLAIMED_EXHAUSTIVE_PHYSICAL_CENSUS','rows':len(frame),'old_stable_ids_preserved':len(old),'additional_entities':len(a),'located':int(frame.lat.notna().sum()),'unlocated':int(frame.lat.isna().sum()),'latest2021_rows':int(frame.population_2021.notna().sum()),'year_counts':{str(y):int(frame[f'population_{y}'].notna().sum()) for y in [2002,2010,2021]},'missing_populations_filled':False,'frozen_values_modified':False,'identity_source':'stage71acceptedcomponentroot; no new name-based unions','source_scope':'additional existing accepted components may be incomplete or territorial; axis_kind and additive flags mandatory filters','inputs':{str(p.relative_to(REPO)):sha(p) for p in [master,source,points]}}
 (OUT/'axis_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':build()
