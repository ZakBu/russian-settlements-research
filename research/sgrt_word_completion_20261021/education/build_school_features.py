#!/usr/bin/env python3
"""Link the common national OSM education inventory to the full dated settlement axis.

Exact address identity and spatial candidate layers remain separate. Source absence
is not absence of education; unknown capacities and opening dates remain nullable.
"""
from pathlib import Path
import argparse,json,hashlib,re,time
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2]
RAW=Path('/workspace/scratch/sgrt_transport')
AXIS=ROOT.parent/'axis/full_settlement_axis.parquet'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip()
def xyz(lat,lon):
 a,b=np.radians(lat),np.radians(lon)
 return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
def dist(ch):return 12742.0176*np.arcsin(np.clip(ch/2,0,1))
def school_group(r):
 n=norm(r.get('name') or '');amenity=r.amenity
 if amenity=='school' and any(t in n for t in ['дюсш','музыкальн','искусств','художествен','спортивн','автошкол','танцевальн','воскресн','языков']):return 'specialized_non_general_school'
 return {'school':'school','kindergarten':'preschool','college':'college','university':'university'}.get(amenity,'other_education')
def link(objects,axis):
 valid=axis.lat.notna()&axis.lon.notna()&axis.population_2021.notna()&axis.is_additive_source_unit.eq(True)
 ref=axis.loc[valid].reset_index(drop=True).copy();ref['_name']=ref.name.map(norm)
 tree=cKDTree(xyz(ref.lat.values,ref.lon.values));points=xyz(objects.lat.values,objects.lon.values)
 dd,ii=tree.query(points,k=2,workers=1);dd=dist(dd)
 output=[]
 for j,r in objects.iterrows():
  tags=json.loads(r.tags_json or '{}');closest=ref.iloc[ii[j,0]];second=ref.iloc[ii[j,1]];d0=float(dd[j,0]);d1=float(dd[j,1])
  locality=next((tags.get(k) for k in ['addr:city','addr:village','addr:hamlet','addr:place','is_in:city'] if tags.get(k)),None)
  literal=norm(locality) if locality else ''
  literal=re.sub(r'^(город|село|деревня|поселок|г|с|д|п)\s+','',literal)
  broad_city=literal in {'москва','санкт петербург','санктпетербург','севастополь'}
  exact=None;status='unresolved_no_locality_identity';baseline_distance=None
  if literal:
   near=tree.query_ball_point(points[j],2*np.sin(5/12742.0176));matches=[k for k in near if ref.iloc[k]['_name']==literal]
   if len(matches)==1:
    k=matches[0];exact=ref.iloc[k].id;baseline_distance=float(dist(np.linalg.norm(points[j]-xyz([ref.iloc[k].lat],[ref.iloc[k].lon])[0])));status='explicit_address_locality_unique_within5km'
   elif len(matches)>1:status='ambiguous_same_address_locality'
   else:status='explicit_locality_not_resolved_within5km'
  candidate=None
  # For explicit address conflict we preserve only the nearest diagnostic, not a linked candidate.
  no_address_conflict=(not literal) or closest['_name']==literal
  separated=(d1>=max(d0*1.5,d0+.25))
  if exact is None and d0<=2.5 and separated and no_address_conflict and not broad_city:
   candidate=closest.id;status='spatial_candidate_within2_5km_separated_not_identity_proof'
  # Federal addresses and absent current-axis places stay external; never donate a city to a nearby village.
  output.append({'baseline_uid':exact,'candidate_uid':candidate,'link_status':status,'linked_distance_km':baseline_distance if exact else d0 if candidate else None,'nearest_uid_unaccepted':closest.id,'nearest_distance_km':d0,'second_nearest_distance_km':d1,'source_address_locality':locality,'source_address_state':tags.get('addr:state'),'current2021_reference_only':True,'source_capacity':tags.get('capacity'),'source_students':tags.get('students'),'source_isced_level':tags.get('isced:level'),'source_start_date':tags.get('start_date'),'source_end_date':tags.get('end_date'),'source_school_type':tags.get('school:type'),'source_geometry_is_dated_measurement':False})
 return pd.concat([objects.reset_index(drop=True),pd.DataFrame(output)],axis=1)
def dedup(d):
 # Preserve all raw assertions. Only exact-name cross node/way proximity is a dedup sensitivity.
 d=d.copy();d['canonical_site_id']=d.site_id;d['possible_duplicate_of']=None
 for group,g in d[d.name.notna()].groupby('education_group'):
  pts=xyz(g.lat.values,g.lon.values);pairs=cKDTree(pts).query_pairs(2*np.sin(.05/12742.0176));ids=g.index.to_numpy()
  for a,b in sorted(pairs):
   ia,ib=ids[a],ids[b];ra,rb=d.loc[ia],d.loc[ib]
   if ra.osm_type==rb.osm_type or norm(ra['name'])!=norm(rb['name']):continue
   # A way usually describes the grounds; retain it over a duplicate label node.
   keep,drop=(ia,ib) if ra.osm_type=='way' else (ib,ia)
   d.loc[drop,'possible_duplicate_of']=d.loc[keep,'site_id'];d.loc[drop,'canonical_site_id']=d.loc[keep,'site_id']
 return d
def build():
 start=time.time();axis_sha_before=sha(AXIS);axis=pd.read_parquet(AXIS);assert axis.id.notna().all() and axis.id.is_unique
 files=sorted(RAW.glob('poi_*.parquet'))
 if not files:raise RuntimeError('Shared national extractor has not produced any complete POI partition')
 allpoi=pd.concat([pd.read_parquet(p) for p in files],ignore_index=True)
 d=allpoi[allpoi.amenity.isin(['school','kindergarten','college','university'])].copy().reset_index(drop=True)
 d['site_id']='osm:'+d.osm_type+':'+d.osm_id.astype(str);d['education_group']=d.apply(school_group,axis=1)
 d['source_snapshot']='2026-10-19T20:21:11Z';d['source']='OpenStreetMap via Geofabrik Russia';d['source_license']='ODbL-1.0'
 d=link(d,axis);d=dedup(d)
 d['source_capacity_numeric']=pd.to_numeric(d.source_capacity,errors='coerce')
 d['source_grades']=d.tags_json.map(lambda x:json.loads(x).get('grades'))
 def grade_level(r):
  if r.education_group!='school':return pd.Series([None,None])
  raw=r.source_isced_level
  if pd.notna(raw):
   digits=[int(z) for z in re.findall(r'\b[123]\b',str(raw))]
   if digits:return pd.Series([max(digits),'explicit_isced_level_tag'])
  if pd.notna(r.source_grades):
   digits=[int(z) for z in re.findall(r'\d+',str(r.source_grades))]
   if digits and max(digits)<=12:return pd.Series([3 if max(digits)>=10 else 2 if max(digits)>=5 else 1,'explicit_grades_tag_interpreted'])
  n=norm(r['name'] or '')
  for pattern,level in [(r'средняя|\bсош\b|гимназия|лицей',3),(r'основная|\bоош\b',2),(r'начальная|\bнош\b',1)]:
   if re.search(pattern,n):return pd.Series([level,'source_name_signal_not_verified_program'])
  return pd.Series([None,None])
 d[['general_school_max_level_signal','school_level_evidence']]=d.apply(grade_level,axis=1)
 d.to_parquet(ROOT/'education_objects.parquet',index=False)
 d[d.baseline_uid.isna()&d.candidate_uid.isna()].to_parquet(ROOT/'external_or_unresolved_school_providers.parquet',index=False)
 features=axis[['id','name','type','region','population_2021','axis_kind']].copy()
 for group in ['school','preschool','college','university','specialized_non_general_school']:
  for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
   counted=d[d.education_group.eq(group)&d[key].notna()].drop_duplicates([key,'canonical_site_id'])
   features[f'education_osm_{group}_{mode}_count']=features.id.map(counted.groupby(key).size()).fillna(0).astype('int32')
  features[f'education_osm_{group}_observed_presence']=pd.array(np.where((features[f'education_osm_{group}_baseline_count']+features[f'education_osm_{group}_candidate_additional_count'])>0,True,None),dtype='boolean')
 # Level signals are separate from verified programme tags.
 for level in [1,2,3]:
  for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
   objects=d[d.education_group.eq('school')&d.general_school_max_level_signal.eq(level)&d[key].notna()].drop_duplicates([key,'canonical_site_id'])
   features[f'education_osm_school_level{level}_{mode}_count']=features.id.map(objects.groupby(key).size()).fillna(0).astype('int32')
   explicit=objects[objects.school_level_evidence.isin(['explicit_isced_level_tag','explicit_grades_tag_interpreted'])]
   features[f'education_osm_school_explicit_tag_level{level}_{mode}_count']=features.id.map(explicit.groupby(key).size()).fillna(0).astype('int32')
 features['education_source_observation_scope']='OSM published objects; absent accepted object means unknown physical service presence'
 named=ROOT/'school_website_named_settlements_2022.parquet'
 if named.exists():
  nc=pd.read_parquet(named);linked=nc[nc.settlement_uid.notna()].drop_duplicates(['settlement_uid','school_name','website_raw'])
  features['education_named2022_school_institution_witness_count']=features.id.map(linked.groupby('settlement_uid').size()).fillna(0).astype('int32')
  features['education_named2022_school_presence']=pd.array(np.where(features.education_named2022_school_institution_witness_count.gt(0),True,None),dtype='boolean')
 for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
  c=d[d.education_group.eq('school')&d[key].notna()&d.source_capacity_numeric.notna()].drop_duplicates([key,'canonical_site_id'])
  features[f'education_osm_school_{mode}_capacity_observed_sites']=features.id.map(c.groupby(key).size()).fillna(0).astype('int32')
  features[f'education_osm_school_{mode}_partial_source_capacity_sum']=features.id.map(c.groupby(key).source_capacity_numeric.sum(min_count=1))
 features['education_capacity_total_known']=False;features['education_capacity']=np.nan;features['education_opening_date_known']=False
 features.to_parquet(ROOT/'settlement_features_full_axis.parquet',index=False)
 legacy=pd.read_parquet(REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet',columns=['id'])
 legacy.merge(features,on='id',how='left',validate='one_to_one').to_parquet(ROOT/'settlement_features.parquet',index=False)
 cov=[]
 for g in ['school','preschool','college','university','specialized_non_general_school']:
  x=d[d.education_group.eq(g)];cov.append({'group':g,'source_rows':len(x),'canonical_site_ids':x.canonical_site_id.nunique(),'baseline_objects':int(x.baseline_uid.notna().sum()),'candidate_objects':int(x.candidate_uid.notna().sum()),'baseline_settlements':x.baseline_uid.nunique(),'candidate_settlements':x.candidate_uid.nunique(),'union_settlements':pd.concat([x.baseline_uid,x.candidate_uid]).dropna().nunique()})
 pd.DataFrame(cov).to_csv(ROOT/'coverage.csv',index=False)
 x=features.copy();x['size_bin']=pd.cut(x.population_2021,[-1,0,99,499,1999,9999,np.inf],labels=['0','1-99','100-499','500-1999','2000-9999','10000+'])
 x.groupby('size_bin',observed=True).agg(axis_rows=('id','size'),school_baseline_sites=('education_osm_school_baseline_count','sum'),school_candidate_sites=('education_osm_school_candidate_additional_count','sum'),school_positive_settlements=('education_osm_school_observed_presence','sum')).to_csv(ROOT/'coverage_by_population_size.csv')
 extraction=ROOT.parent/'transport/extraction_receipt.json'
 receipt={'status':'COMPLETE_SHARED_OSM' if extraction.exists() else 'PARTIAL_SHARED_EXTRACTION_NOT_FINAL','axis_rows':len(axis),'legacy_rows':len(legacy),'poi_partition_count':len(files),'source_education_rows':len(d),'source_osm_rows_seen':len(allpoi),'axis_sha256':sha(AXIS),'poi_partitions':[{'file':str(p),'sha256':sha(p),'bytes':p.stat().st_size}for p in files],'coverage':cov,'duplicate_rule':'same normalized name crossnode/way within50m, raw assertions retained','baseline_rule':'explicit source address settlement literal unique within5km on current2021axis','candidate_rule':'nearest within2.5km,second separated by>=max(1.5xdistance,+0.25km),no address conflict; candidate not identity proof','physical_census_complete':False,'unknown_is_not_absent':True,'capacity_and_actual_users_not_invented':True,'seconds':time.time()-start}
 assert axis_sha_before==sha(AXIS), 'Axis input changed during education linkage'
 (ROOT/'build_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k!='poi_partitions'},ensure_ascii=False,indent=2))
if __name__=='__main__':build()
