#!/usr/bin/env python3
"""Full-axis OSM health-site linkage: address evidence and coordinate candidates separate."""
from pathlib import Path
import argparse, json, hashlib, re, time, unicodedata
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from extract_osm_medical import classify,is_medical,KEYS

ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2]
AXIS=ROOT.parent/'axis/full_settlement_axis.parquet'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def norm(s):
 if s is None or pd.isna(s):return ''
 t=unicodedata.normalize('NFKC',str(s)).lower().replace('ё','е')
 t=re.sub(r'^(город|г\.|село|с\.|деревня|д\.|пос[её]лок|п\.|пгт\.?|рп\.?|станица|ст-ца)\s*','',t)
 return re.sub(r'[^a-zа-я0-9]','',t)
def xyz(lat,lon):
 a,b=np.radians(lat),np.radians(lon);return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
def distance(chord):return 2*6371.0088*np.arcsin(np.clip(chord/2,0,1))
def run(pois,complete,snapshot,output):
 start=time.monotonic();output.mkdir(parents=True,exist_ok=True);axis=pd.read_parquet(AXIS)
 inventory=[];manifest=[]
 for p in pois:
  # Refuse unfinished Parquet bytes rather than accepting a truncated partition.
  with p.open('rb') as f:f.seek(-4,2);assert f.read()==b'PAR1',p
  d=pd.read_parquet(p);manifest.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p),'rows':len(d)})
  for r in d.itertuples(index=False):
   tags=json.loads(r.tags_json)
   if not is_medical(tags):continue
   x={'object_id':f'OSM:{r.osm_type}:{r.osm_id}','osm_type':r.osm_type,'osm_id':r.osm_id,'lat':r.lat,'lon':r.lon,'geometry_method':r.geometry_role,'medical_class':classify(tags),'source_snapshot_date':snapshot,'source':'OSM_Geofabrik_community_physical_location_assertion','source_complete_extract':complete,'tags_json':r.tags_json,'operating_status':'unknown_not_confirmed_open','actual_service_flow_observed':False,'capacity_known':bool(tags.get('beds') or tags.get('capacity'))}
   x['osm_version_source_metadata']=getattr(r,'osm_version',None);x['osm_timestamp_source_metadata']=getattr(r,'osm_timestamp',None)
   x.update({k.replace(':','_'):tags.get(k) for k in KEYS})
   inactive=any(tags.get(k) in {'yes','true','1'} for k in ['disused','abandoned','demolished']) or bool(tags.get('disused:amenity') or tags.get('disused:healthcare'))
   x['inactive_source_assertion']=inactive
   if inactive:x['operating_status']='inactive_source_asserted'
   inventory.append(x)
 d=pd.DataFrame(inventory).drop_duplicates('object_id');assert d.object_id.is_unique
 finite=axis[['lat','lon']].notna().all(axis=1)&axis.lat.between(-90,90)&axis.lon.between(-180,180)
 ref=axis[finite].copy();ref['normalized_name']=ref.name.map(norm);coords=xyz(ref.lat.values,ref.lon.values);tree=cKDTree(coords)
 geom=d[['lat','lon']].notna().all(axis=1)&d.lat.between(-90,90)&d.lon.between(-180,180)
 d['baseline_uid']=None;d['conditional_uid']=None;d['coordinate_candidate_uid']=None;d['link_status']='unlocated_source';d['nearest_distance_km']=np.nan;d['nearest_id_unaccepted']=None;d['second_nearest_distance_km']=np.nan
 d['source_address_locality']=d[['addr_city','addr_village','addr_hamlet']].bfill(axis=1).iloc[:,0]
 # This geography diagnostic retains objects outside the reference axis; it does not force admission.
 ch,near=tree.query(xyz(d.loc[geom,'lat'].values,d.loc[geom,'lon'].values),k=2,workers=1);dd=distance(ch)
 namegroups=ref.groupby('normalized_name').indices;refids=ref.id.to_numpy();rn=ref.normalized_name.to_numpy()
 for j,i in enumerate(d.index[geom]):
  first=int(near[j,0]);dist=float(dd[j,0]);second=float(dd[j,1]);d.at[i,'nearest_distance_km']=dist;d.at[i,'second_nearest_distance_km']=second;d.at[i,'nearest_id_unaccepted']=refids[first]
  local=norm(d.at[i,'source_address_locality']);matches=[]
  if local and local in namegroups:
   candidates=namegroups[local];src=xyz(np.array([d.at[i,'lat']]),np.array([d.at[i,'lon']]))[0]
   ds=distance(np.linalg.norm(coords[candidates]-src,axis=1));matches=[(int(c),float(z)) for c,z in zip(candidates,ds) if z<=10]
  if len(matches)==1:
   k,ld=matches[0]
   if ld<=5:d.at[i,'baseline_uid']=refids[k];d.at[i,'link_status']='exact_source_address_locality_unique_within10km_distance_le5km'
   else:d.at[i,'conditional_uid']=refids[k];d.at[i,'link_status']='exact_source_address_locality_unique_within10km_distance5to10km'
  elif len(matches)>1:d.at[i,'link_status']='address_locality_homonym_conflict'
  else:d.at[i,'link_status']='no_accepted_source_locality_link'
  if dist<=10:
   d.at[i,'coordinate_candidate_uid']=refids[first]
   if d.at[i,'baseline_uid'] is None and d.at[i,'conditional_uid'] is None and not len(matches)>1:
    if local and local!=rn[first]:d.at[i,'link_status']='source_address_locality_conflicts_with_nearest_candidate'
    elif dist<=1 and (second>=2*max(dist,.05) or second-dist>=1):d.at[i,'link_status']='strong_coordinate_candidate_le1km_not_identity_accepted'
    else:d.at[i,'link_status']='coordinate_candidate_le10km_not_identity_accepted'
  elif d.at[i,'baseline_uid'] is None and d.at[i,'conditional_uid'] is None:d.at[i,'link_status']='outside10km_reference_candidate_radius'
 d['broad_function']=np.where(d.medical_class.str.contains('pharmacy'),'pharmacy',np.where(d.medical_class.str.contains('dentist'),'dentistry','healthcare'))
 d['capacity_value_source_raw']=d.beds.where(d.beds.notna(),d.capacity)
 d['beds_numeric']=pd.to_numeric(d.beds,errors='coerce');d['capacity_numeric']=pd.to_numeric(d.capacity,errors='coerce')
 d['capacity_numeric_valid']=d.beds_numeric.ge(0)|d.capacity_numeric.ge(0)
 d['source_start_date_is_not_verified_physical_opening_date']=True
 d.to_parquet(output/'osm_medical_inventory.parquet',index=False);d.to_csv(output/'osm_medical_inventory.csv.gz',index=False)
 features=axis[['id','name','type','region','lat','lon']].copy().set_index('id');features['medical_source_snapshot_date']=snapshot;features['medical_osm_complete_extract']=complete
 eligible=~d.inactive_source_assertion
 classes=sorted(d.medical_class.unique())
 for evidence,col in [('baseline','baseline_uid'),('conditional_additional','conditional_uid'),('coordinate_candidate','coordinate_candidate_uid')]:
  a=d[eligible&d[col].notna()]
  for typ in classes:
   cnt=a[a.medical_class.eq(typ)].groupby(col).size();features[f'medical_osm_{evidence}_{typ}_count']=cnt.reindex(features.index,fill_value=0).astype('int32')
  features[f'medical_osm_{evidence}_all_sites_count']=a.groupby(col).size().reindex(features.index,fill_value=0).astype('int32')
  a=a[a.broad_function.eq('healthcare')]
  features[f'medical_osm_{evidence}_healthcare_sites_count']=a.groupby(col).size().reindex(features.index,fill_value=0).astype('int32')
 # A narrow candidate sensitivity must never silently become baseline.
 strong=d[eligible&d.link_status.eq('strong_coordinate_candidate_le1km_not_identity_accepted')]
 features['medical_osm_strong_coordinate_candidate_healthcare_sites_count']=strong[strong.broad_function.eq('healthcare')].groupby('coordinate_candidate_uid').size().reindex(features.index,fill_value=0).astype('int32')
 features['medical_osm_no_accepted_record_does_not_mean_no_service']=True
 features=features.reset_index();features.to_parquet(output/'settlement_features.parquet',index=False)
 coverage=[]
 for c in [c for c in features if c.endswith('_sites_count')]:
  pos=features[c]>0
  coverage.append({'feature':c,'positive_settlements':int(pos.sum()),'rural_settlements':int((pos&~features.type.isin(['город','пгт'])).sum()),'urban_settlements':int((pos&features.type.isin(['город','пгт'])).sum()),'source_rows':int(features[c].sum())})
 pd.DataFrame(coverage).to_csv(output/'coverage.csv',index=False)
 receipt={'status':'COMPLETE_EXTRACT_LINKED' if complete else 'PARTIAL_EXTRACT_INTERIM_ONLY','source_snapshot_date':snapshot,'axis_rows':len(axis),'axis_sha256':sha(AXIS),'unique_uid_rows':features.id.nunique(),'source_partitions':manifest,'inventory_rows':len(d),'source_healthcare_rows':int(d.broad_function.eq('healthcare').sum()),'coordinate_rows':int(geom.sum()),'link_status_counts':{str(k):int(v) for k,v in d.link_status.value_counts().items()},'medical_class_counts':{str(k):int(v) for k,v in d.medical_class.value_counts().items()},'operating_status_not_confirmed':True,'capacity_source_rows':int(d.capacity_known.sum()),'features_sha256':sha(output/'settlement_features.parquet'),'seconds':round(time.monotonic()-start,3)}
 (output/'linkage_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='source_partitions'},ensure_ascii=False,indent=2))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--poi-dir',type=Path,default=Path('/workspace/scratch/sgrt_transport'));ap.add_argument('--snapshot',default='2026-10-19');ap.add_argument('--complete',action='store_true');ap.add_argument('--output',type=Path,default=ROOT);a=ap.parse_args();run(sorted(a.poi_dir.glob('poi_*.parquet')),a.complete,a.snapshot,a.output)
