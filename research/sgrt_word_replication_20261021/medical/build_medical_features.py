#!/usr/bin/env python3
"""Recover source-preserving medical evidence on the immutable national axis.

Places broad hospital/healthcare categories do not establish inpatient beds,
FAPs, capacity, catchments or an operating history. Pilot sites are kept apart.
"""
from pathlib import Path
import hashlib,json,re
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
MASTER=REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet'
PILOT=REPO/'research/sgrt_functional_dynamics_20261019/medical'

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(2**20),b''):h.update(x)
 return h.hexdigest()

def norm(v):
 if pd.isna(v):return ''
 return re.sub(r'[^а-яa-z0-9]+',' ',str(v).lower().replace('ё','е')).strip()

def region(v):
 s=norm(v)
 for word in ['область','республика','край','автономный','округ','автономная','обл','респ']:
  s=re.sub(r'\b'+word+r'\b','',s)
 return ' '.join(s.split())

def main():
 master_start_sha256=sha(MASTER)
 assert master_start_sha256=='8c98d5a113eec4c3bf131232b1d7e5c6362dc3a50ee484e964420de58c377f85','Unexpected master version'
 schema=pq.ParquetFile(MASTER).schema_arrow.names
 base=['id','name','type','region','lat','lon','district_raw_2021','municipality_upper_2021']
 places=[c for c in schema if c.startswith('places_') and any(z in c for z in ['hospital_count','healthcare_count','name_signal_fap_count'])]
 legal=[f'econ_native_{y}_health86_legal_entities' for y in range(2011,2026)]
 d=pd.read_parquet(MASTER,columns=base+places+legal)
 assert len(d)==142570 and d.id.notna().all() and d.id.is_unique
 d['_name']=d.name.map(norm);d['_region']=d.region.map(region)
 d['_district']=(d.district_raw_2021.fillna('')+' '+d.municipality_upper_2021.fillna('')).map(norm)
 lookup=d.groupby(['_name','_region']).indices
 def resolve(r):
  key=(norm(r.get('settlement')),region(r.get('region')))
  if not all(key):return None,'missing_name_or_region'
  ix=lookup.get(key)
  if ix is None:return None,'name_region_absent'
  c=d.iloc[ix]
  # Explicit source type resolves the city/village homonym without guessing.
  st=norm(r.get('settlement_type'))
  if st:c=c[c.type.map(norm).eq(st)]
  m=norm(r.get('municipality'))
  if m.startswith('город ') and m[6:]==key[0]:
   c=c[c.type.map(norm).eq('город')]
   if len(c)==1:return c.iloc[0].id,'explicit_city_name_region_type_pilot'
  tokens=[t for t in m.split() if len(t)>4 and t not in {'муниципальный','городской','район','округ'}]
  if not tokens:return None,'missing_administrative_context'
  mask=c['_district'].map(lambda s:any(t in s for t in tokens));c=c[mask]
  # A rural name unique only within the incomplete axis is not enough.
  if len(c)!=1:return None,'ambiguous_or_context_mismatch'
  return c.iloc[0].id,'exact_name_region_administrative_context_pilot'
 obj=pd.read_csv(PILOT/'objects.csv');obj[['settlement_uid','link_status']]=pd.DataFrame([resolve(r) for _,r in obj.iterrows()],index=obj.index)
 alias=pd.read_csv(PILOT/'object_aliases.csv');am=dict(zip(alias.object_id,alias.same_physical_unit))
 obj['canonical_object_id']=obj.object_id.map(lambda s:am.get(s,s))
 obj['record_origin']='recovered_committed_documented_pilot'
 obj['full_national_registry']=False;obj['operating_status_currently_reverified']=False
 obj['subtype_evidence']='explicit_pilot_source_label_not_places_lexical_signal'
 obj.to_parquet(HERE/'objects.parquet',index=False);obj.to_csv(HERE/'objects.csv',index=False)
 # One site may have repeated aliases/documents. No doubling across pilot aliases.
 accepted=obj[obj.settlement_uid.notna()].drop_duplicates(['settlement_uid','canonical_object_id'])
 f=d[['id']].copy()
 for c in places:f[c]=d[c]
 for c in legal:f[c]=d[c]
 for label,levels in {'fap':['FAP'],'ambulatory':['ambulatory'],'outpatient_clinic':['outpatient_clinic'],'hospital':['local_hospital','district_hospital']}.items():
  counts=accepted[accepted.service_level.isin(levels)].groupby('settlement_uid').canonical_object_id.nunique()
  f[f'medical_pilot_{label}_documented_sites']=f.id.map(counts).fillna(0).astype('int32')
 f['medical_hospital_baseline_count']=f.places_baseline_hospital_count
 f['medical_healthcare_baseline_count']=f.places_baseline_healthcare_count
 f['medical_hospital_conditional_additional_count']=f.places_conditional_hospital_count
 f['medical_healthcare_conditional_additional_count']=f.places_conditional_healthcare_count
 f['medical_coarse_physical_baseline_observed']=(f.medical_hospital_baseline_count+f.medical_healthcare_baseline_count)>0
 f['medical_pilot_explicit_subtype_observed']=f.filter(regex='medical_pilot_.*_documented_sites').sum(axis=1)>0
 f['medical_physical_evidence_observed']=f.medical_coarse_physical_baseline_observed|f.medical_pilot_explicit_subtype_observed
 f['medical_external_catchment_proven']=False
 f['medical_zero_interpretation']='no_accepted_record_not_proven_absence_of_service'
 # Places counts remain a distinct 2026 source release; RFSD a legal sequence.
 f['medical_physical_snapshot']='Overture2026-09-23.1_plus_explicit_dated_pilot2025_2026'
 f['medical_legal_history_is_physical_history']=False
 f.to_parquet(HERE/'settlement_features.parquet',index=False)
 history=pd.read_csv(PILOT/'tariff_snapshots.csv');history[['settlement_uid','link_status']]=pd.DataFrame([resolve(r) for _,r in history.iterrows()],index=history.index)
 history['source_retrieved_again_this_run']=False
 history.to_parquet(HERE/'documented_tariff_history.parquet',index=False)
 history.to_csv(HERE/'documented_tariff_history.csv',index=False)
 change=pd.read_csv(PILOT/'tariff_changes.csv');change.to_csv(HERE/'documented_tariff_changes.csv',index=False)
 agg=[]
 for year,g in history.groupby('snapshot_date'):
  agg.append({'snapshot_date':year,'listed_units':len(g),'medical_worker_present':int(g.medical_worker_present.sum()),'registered_population':int(g.registered_population.sum()),'linked_rows':int(g.settlement_uid.notna().sum()),'population_semantics':'tariff_registered_population_not_census_or_actual_visits'})
 pd.DataFrame(agg).to_csv(HERE/'documented_history_summary.csv',index=False)
 urban=d.type.map(norm).isin(['город','пгт','рабочий поселок','поселок городского типа'])
 receipt={'status':'PASS_RECOVERED_BASELINE_WITH_EXPLICIT_LIMITS','axis_rows':len(f),'uid_equal_master':set(f.id)==set(d.id),'uid_unique':bool(f.id.is_unique),'master_sha256':sha(MASTER),'places_hospital_baseline_records':int(f.medical_hospital_baseline_count.sum()),'places_healthcare_baseline_records':int(f.medical_healthcare_baseline_count.sum()),'places_hospital_baseline_settlements':int(f.medical_hospital_baseline_count.gt(0).sum()),'places_healthcare_baseline_settlements':int(f.medical_healthcare_baseline_count.gt(0).sum()),'physical_baseline_settlements':int(f.medical_coarse_physical_baseline_observed.sum()),'physical_baseline_urban_settlements':int((urban&f.medical_coarse_physical_baseline_observed).sum()),'physical_baseline_other_settlements':int((~urban&f.medical_coarse_physical_baseline_observed).sum()),'pilot_object_rows':len(obj),'pilot_linked_rows':int(obj.settlement_uid.notna().sum()),'pilot_link_status':obj.link_status.value_counts().to_dict(),'pilot_deduplicated_linked_sites':len(accepted),'pilot_subtype_counts':accepted.service_level.value_counts().to_dict(),'physical_evidence_union_settlements':int(f.medical_physical_evidence_observed.sum()),'tariff_snapshot_rows':len(history),'history_summary':agg,'national_subtype_history_available':False,'national_inpatient_capacity_available':False,'official_registry_downloaded':False,'sources':{str(p.relative_to(REPO)):sha(p) for p in [PILOT/'objects.csv',PILOT/'object_aliases.csv',PILOT/'tariff_snapshots.csv',PILOT/'tariff_changes.csv']},'limitations':['Placeshospital is a provider category, not confirmed inpatient beds or active hospital campus.','Healthcare excludes no subtype silently: clinics, FAP, ambulatory and inpatient capacity remain unknown nationally.','Pilot territorial/context binding is separate and not a national completeness estimate.','RFSDhealth86 is legal reporting presence, not physical-site service history.','Present list absence is unknown, not closure.','Urban sites are preserved; no rural-only filter applied.']}
 receipt['outputs']={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in HERE.iterdir() if p.suffix in ['.parquet','.csv']}
 assert sha(MASTER)==master_start_sha256,'Frozen master changed during build'
 receipt['master_bytes_unchanged_during_build']=True
 (HERE/'acquisition_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in receipt.items() if k not in ['sources','outputs','limitations']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
