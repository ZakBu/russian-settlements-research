#!/usr/bin/env python3
"""Extract a reference-complete national OSM medical inventory, preserving uncertainty.

Reads a shared Geofabrik PBF; does not download or edit its source. OSM tags
are community assertions of physical locations, not official establishment dates.
"""
from pathlib import Path
import argparse, hashlib, json, time, re
import numpy as np
import pandas as pd
import osmium

ROOT=Path(__file__).resolve().parent
EDUCATION_AMENITIES={'school','college','university','kindergarten'}
AMENITIES={'hospital','clinic','doctors','dentist','pharmacy','nursing_home'}
KEYS=['name','name:ru','amenity','healthcare','healthcare:speciality','operator','operator:type','ownership','hospital:type','beds','capacity','opening_hours','addr:city','addr:village','addr:hamlet','addr:suburb','addr:district','addr:region','addr:full','addr:street','addr:housenumber','addr:postcode','website','start_date','end_date','disused','abandoned','demolished','disused:amenity','disused:healthcare','building']

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()

def is_medical(tags):
 return bool(tags.get('healthcare') or tags.get('amenity') in AMENITIES or tags.get('building') in {'hospital','clinic'} or tags.get('disused:amenity') in AMENITIES or tags.get('disused:healthcare'))

def classify(tags):
 name=(tags.get('name:ru') or tags.get('name') or '').lower().replace('ё','е')
 healthcare=tags.get('healthcare','');amenity=tags.get('amenity','')
 # Explicit source-name classes are separate from official coded service levels.
 if re.search(r'(?<![а-я])фап(?![а-я])|фельдшерско.?акушер|фельдшерск.{0,12}пункт',name):return 'fap_name_assertion'
 if re.search(r'амбулатор',name):return 'ambulatory_name_assertion'
 if re.search(r'поликлиник',name):return 'polyclinic_name_assertion'
 if re.search(r'участков.{0,8}больниц',name):return 'district_local_hospital_name_assertion'
 if re.search(r'центральн.{0,8}районн.{0,8}больниц|(?<![а-я])црб(?![а-я])',name):return 'central_district_hospital_name_assertion'
 if re.search(r'областн.{0,8}больниц|республиканск.{0,8}больниц',name):return 'regional_hospital_name_assertion'
 if healthcare=='hospital' or amenity=='hospital':return 'hospital_source_tag'
 if healthcare in {'clinic','centre'} or amenity=='clinic':return 'clinic_source_tag'
 if healthcare=='doctor' or amenity=='doctors':return 'doctor_source_tag'
 if healthcare=='midwife':return 'midwife_source_tag_not_automatically_fap'
 if healthcare=='dentist' or amenity=='dentist':return 'dentist_source_tag'
 if healthcare=='pharmacy' or amenity=='pharmacy':return 'pharmacy_source_tag'
 if healthcare in {'laboratory','sample_collection'}:return 'laboratory_source_tag'
 if amenity=='nursing_home':return 'nursing_home_source_tag'
 return 'other_healthcare_source_tag'

class Inventory(osmium.SimpleHandler):
 def __init__(self):
  super().__init__();self.rows=[];self.ways={};self.relations=[]
 def row(self,o,typ,lon=np.nan,lat=np.nan,geom='unknown'):
  tags=dict(o.tags);r={'object_id':f'OSM:{typ}:{o.id}','osm_type':typ,'osm_id':o.id,'osm_version':o.version,'osm_timestamp':str(o.timestamp),'lon':lon,'lat':lat,'geometry_method':geom,'medical_class':classify(tags),'tags_json':json.dumps(tags,ensure_ascii=False),'source_type_evidence':'OSM_community_tag_or_literal_name_not_official_FRMO','source_snapshot_date':'2026-10-19','physical_opening_date_asserted':False,'unknown_scope_not_absence':True}
  r.update({k.replace(':','_'):tags.get(k) for k in KEYS})
  r['inactive_source_assertion']=any(tags.get(k) in {'yes','true','1'} for k in ['disused','abandoned','demolished']) or bool(tags.get('disused:amenity') or tags.get('disused:healthcare'))
  # Availability is unknown unless explicitly asserted; tags do not establish a census of operating sites.
  r['operating_status']='inactive_source_asserted' if r['inactive_source_assertion'] else 'unknown_not_confirmed_open'
  self.rows.append(r);return r
 def node(self,o):
  if is_medical(o.tags):self.row(o,'node',o.location.lon,o.location.lat,'direct_osm_node')
 def way(self,o):
  # Referenced untagged ways are also retained for relation representative points.
  coords=[(n.lon,n.lat) for n in o.nodes if n.location.valid()]
  if coords:
   xy=np.array(coords);lon=float(np.degrees(np.arctan2(np.sin(np.radians(xy[:,0])).mean(),np.cos(np.radians(xy[:,0])).mean())));lat=float(xy[:,1].mean());self.ways[o.id]=(lon,lat)
  else:lon=lat=np.nan
  if is_medical(o.tags):self.row(o,'way',lon,lat,'mean_boundary_nodes_representative_not_entrance')
 def relation(self,o):
  if is_medical(o.tags):
   r=self.row(o,'relation');self.relations.append((r,[(m.type,m.ref) for m in o.members]))
 def finish(self):
  for r,members in self.relations:
   pts=[self.ways[ref] for typ,ref in members if typ=='w' and ref in self.ways]
   if pts:
    xy=np.array(pts);r['lon']=float(np.degrees(np.arctan2(np.sin(np.radians(xy[:,0])).mean(),np.cos(np.radians(xy[:,0])).mean())));r['lat']=float(xy[:,1].mean());r['geometry_method']='mean_member_way_representatives_not_entrance'
  return pd.DataFrame(self.rows)

def run(source,work,snapshot,output):
 start=time.monotonic();work.mkdir(parents=True,exist_ok=True);output.mkdir(parents=True,exist_ok=True);filtered=work/'medical_reference_complete.osm.pbf'
 reader=osmium.io.Reader(str(source));header=reader.header();effective_date=header.get('osmosis_replication_timestamp');reader.close()
 receipt={'source_header_timestamp':effective_date,'source':str(source),'source_bytes':source.stat().st_size,'source_sha256':sha(source),'source_url':'https://download.geofabrik.de/'+source.name.replace('russia.osm.pbf','russia-latest.osm.pbf'),'source_date':snapshot,'attribution':'OpenStreetMap contributors; ODbL1.0; Geofabrik extract','selected_types':['healthcare=*','amenity=hospital,clinic,doctors,dentist,pharmacy,nursing_home','amenity=school,college,university,kindergarten'],'additional_medical_filter':'building=hospital/clinic included when accompanied by selected amenity/healthcare key','stages':[]}
 if not filtered.exists():
  n=0
  with osmium.BackReferenceWriter(filtered,source,remove_tags=True,relation_depth=1) as writer:
   fp=osmium.FileProcessor(source).with_filter(osmium.filter.KeyFilter('healthcare','amenity','disused:amenity','disused:healthcare'))
   for o in fp:
    if is_medical(o.tags) or o.tags.get('amenity') in EDUCATION_AMENITIES:writer.add(o);n+=1
    if (is_medical(o.tags) or o.tags.get('amenity') in EDUCATION_AMENITIES) and n and n%10000==0:print('selected',n,flush=True)
  receipt['stages'].append({'stage':'reference_complete_filter','selected_assertions':n,'bytes':filtered.stat().st_size,'sha256':sha(filtered)})
 print('filter_ready',filtered.stat().st_size,flush=True)
 inv=Inventory();inv.apply_file(str(filtered),locations=True,idx='flex_mem');d=inv.finish();d['source_snapshot_date']=snapshot;assert d.object_id.is_unique
 d.rename(columns={'geometry_method':'geometry_role'}).to_parquet(work/'poi_history.parquet',index=False);d.to_parquet(output/'osm_medical_inventory.parquet',index=False);d.to_csv(output/'osm_medical_inventory.csv.gz',index=False)
 receipt.update(rows=len(d),coordinate_rows=int(d[['lat','lon']].notna().all(axis=1).sum()),medical_classes={str(k):int(v) for k,v in d.medical_class.value_counts().items()},inactive_assertions=int(d.inactive_source_assertion.sum()),seconds=round(time.monotonic()-start,3),inventory_sha256=sha(output/'osm_medical_inventory.parquet'))
 (output/'osm_extraction_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--work',type=Path,default=Path('/workspace/scratch/medical_mass/osm'));ap.add_argument('--snapshot',default='2026-10-19');ap.add_argument('--output',type=Path,default=ROOT);args=ap.parse_args();run(args.source,args.work,args.snapshot,args.output)
