#!/usr/bin/env python3
"""Source-backed thematic witnesses; context and mechanisms are deliberately separate."""
from pathlib import Path
import hashlib,json,re,zipfile,shutil
import numpy as np
import pandas as pd
from lxml import html
from scipy.spatial import cKDTree
from shapely.geometry import shape,Point,Polygon
from shapely import contains_xy

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;REPO=ROOT.parents[1]
RAW=HERE/'sources'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip()
def region(x):return norm(re.sub(r'область|республика|край|автономный округ|автономная|ао|г\.', '',str(x).lower()))
def xyz(lat,lon):
 a,b=np.radians(lat),np.radians(lon)
 return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
def km(c):return 12742.0176*np.arcsin(np.clip(c/2,0,1))
def code(x):
 if pd.isna(x):return None
 s=str(x).strip().removesuffix('.0')
 return s.zfill(11) if s.isdigit() and len(s) in [10,11] else None
def swap(x):
 if len(x)==2 and all(isinstance(z,(str,int,float)) for z in x):return [float(x[1]),float(x[0])]
 return [swap(z) for z in x]
def create():
 axisfile=ROOT/'axis/full_settlement_axis.parquet';a=pd.read_parquet(axisfile);a['_name']=a.name.map(norm);a['_region']=a.region.map(region)
 f=pd.DataFrame({'id':a.id})
 # Candidate service-site context is measured against located, contemporary census units.
 located=a[a.lat.notna()&a.lon.notna()&a.population_2021.notna()&a.is_additive_source_unit].copy()
 pts=xyz(located.lat.to_numpy(),located.lon.to_numpy());tree=cKDTree(pts)
 def nearest(o):
  o=o.copy();valid=o.lat.notna()&o.lon.notna();o['nearest_axis_id']=None;o['nearest_distance_km']=np.nan
  if valid.any():
   chord,ix=tree.query(xyz(o.loc[valid,'lat'].to_numpy(),o.loc[valid,'lon'].to_numpy()))
   o.loc[valid,'nearest_axis_id']=located.id.to_numpy()[ix];o.loc[valid,'nearest_distance_km']=km(chord)
  o['link_status']='coordinate_context_candidate_not_settlement_identity';return o
 def context_count(o,col,limit):
  selected=o[o.nearest_distance_km.le(limit)]
  counts=selected.groupby('nearest_axis_id').size()
  f[col]=a.id.map(counts).fillna(0).astype('int32')
  return int(f[col].gt(0).sum())
 # Official public resort map, which uses Yandex [latitude, longitude], not GeoJSON ordering.
 resorts=json.loads((RAW/'resorts_health_json.json').read_text());rs=[]
 for key,category in [('sko_marks','sanatorium_registry_site'),('health_resorts_marks','designated_resort_point')]:
  for z in resorts.get(key,{}).get('features',[]):
   lat,lon=map(float,z['geometry']['coordinates']);rs.append({'source_id':f'MINZDRAV:{key}:{z["id"]}','name':z.get('properties',{}).get('hintContent'),'lat':lat,'lon':lon,'category':category,'source_url':'https://kurort.minzdrav.gov.ru/map_search','snapshot_date':'2026-10-21','geometry_role':'publisher_map_point_location_not_verified_building_footprint'})
 rp=nearest(pd.DataFrame(rs));rp.to_parquet(HERE/'official_resort_points.parquet',index=False)
 context_count(rp[rp.category.eq('sanatorium_registry_site')],'sanatorium_map_points_within1km',1)
 context_count(rp[rp.category.eq('sanatorium_registry_site')],'sanatorium_map_points_within5km',5)
 context_count(rp[rp.category.eq('designated_resort_point')],'designated_resort_map_points_within1km',1)
 area_count=np.zeros(len(a),int);polygon_records=[];invalid=[]
 for z in resorts.get('health_resorts',{}).get('features',[]):
  g=z.get('geometry',{});converted={'type':g.get('type'),'coordinates':swap(g.get('coordinates',[]))}
  row={'source_id':f'MINZDRAV:resort_area:{z["id"]}','name':z.get('properties',{}).get('balloonContent'),'geometry_json_lonlat':json.dumps(converted),'snapshot_date':'2026-10-21','source_url':'https://kurort.minzdrav.gov.ru/map_search?show_health_resorts=true'}
  try:
   geom=shape(converted)
   if geom.is_empty or not geom.is_valid or geom.area==0:raise ValueError('invalid_or_zero_area_source_polygon')
   row['geometry_valid']=True
   # Strict interior source membership; boundary points excluded; no invented buffer.
   hit=contains_xy(geom,a.lon.to_numpy(float),a.lat.to_numpy(float));area_count+=hit
   row['settlement_points_inside']=int(hit.sum())
  except Exception as e:row['geometry_valid']=False;row['error']=str(e);invalid.append(row['source_id'])
  polygon_records.append(row)
 pd.DataFrame(polygon_records).to_parquet(HERE/'official_resort_areas.parquet',index=False);f['official_resort_polygon_memberships']=area_count
 f['designated_resort_territory_evidence']=pd.array(np.where(area_count>0,True,None),dtype='boolean')
 # Complete Russia PBF thematic extraction: physical mapped land uses, not actual trips or migration.
 files=sorted(Path('/workspace/scratch/sgrt_transport').glob('context_poi_*.parquet'))
 if not files:raise RuntimeError('NationalOSMcontextstreamnotyetavailable')
 osm=pd.concat([pd.read_parquet(p) for p in files],ignore_index=True)
 assert not osm.duplicated(['osm_type','osm_id']).any()
 osm=nearest(osm)
 accommodation=osm.tourism.isin(['hotel','motel','hostel','guest_house','camp_site','caravan_site','chalet','apartment','resort'])
 allotment=osm.landuse.eq('allotments')
 mining=osm.man_made.isin(['adit','mineshaft','petroleum_well'])|osm.landuse.eq('quarry')|osm.industrial.isin(['mine','oil','gas','mining'])
 industrial=osm.landuse.eq('industrial')|osm.industrial.notna()
 for mask,col,limit in [(accommodation,'osm_accommodation_points_within3km',3),(allotment,'osm_allotment_geometries_within3km',3),(mining,'osm_resource_site_geometries_within5km',5),(industrial,'osm_industrial_geometries_within3km',3)]:context_count(osm[mask],col,limit)
 # Do not publish irrelevant phone/contact fields from OSM tags in this derived layer.
 keep=['osm_type','osm_id','lat','lon','geometry_role','name','tourism','landuse','man_made','industrial','nearest_axis_id','nearest_distance_km','link_status']
 osm[keep].to_parquet(HERE/'osm_thematic_objects.parquet',index=False)
 f['recreation_facility_evidence']=pd.array(np.where((f.sanatorium_map_points_within1km>0)|(f.osm_accommodation_points_within3km>0),True,None),dtype='boolean')
 f['dacha_landuse_evidence']=pd.array(np.where(f.osm_allotment_geometries_within3km>0,True,None),dtype='boolean')
 f['recreation_dacha_evidence']=pd.array(np.where(f.recreation_facility_evidence.fillna(False)|f.dacha_landuse_evidence.fillna(False)|f.designated_resort_territory_evidence.fillna(False),True,None),dtype='boolean')
 f['mapped_resource_site_context_evidence']=pd.array(np.where(f.osm_resource_site_geometries_within5km>0,True,None),dtype='boolean')
 # Historical official monoindustrial registry. Exact unique name+region links; no current designation claim.
 parsed=html.fromstring((RAW/'monotowns2012.html').read_text('cp1251'));mono=[]
 for tr in parsed.xpath('//table')[1].xpath('.//tr')[1:]:
  x=[' '.join(' '.join(t.itertext()).split()) for t in tr.xpath('./td|./th')]
  if len(x)!=5:continue
  _,reg,name,pop,enterprise=x;short=re.sub(r'^(?:ЗАТО\s+)?(?:г\.\s*о\.|г\.п\.|г\.|пгт\.|п\.|р\.п\.|с\.п\.|с\.|рп\.|пгт|пос\.)\s*','',name,flags=re.I).strip();short=re.sub(r'\s*\(ЗАТО\)\s*','',short,flags=re.I).split(',')[0].strip();nn=norm(short);rr=region(reg)
  candidates=a[a['_name'].eq(nn)&a['_region'].map(lambda s:s in rr or rr in s)].copy()
  if re.match(r'^г\.\s*(?![оп]\.)',name,re.I):
   urban_candidates=candidates[candidates.type.eq('город')]
   if len(urban_candidates):candidates=urban_candidates
  elif re.match(r'^(?:пгт|р\.п\.)',name,re.I):
   typed=candidates[candidates.type.isin(['пгт','посёлок городского типа','рабочий посёлок'])]
   if len(typed):candidates=typed
  # Prefer a source entity actually observed2021, never choose among same-year homonyms arbitrarily.
  if candidates.population_2021.notna().any():candidates=candidates[candidates.population_2021.notna()]
  accepted=candidates.id.iloc[0] if len(candidates)==1 else None
  mono.append({'registry_row':x[0],'region':reg,'name_raw':name,'name':short,'population_source2012':pop,'enterprise_source2012':enterprise,'linked_id':accepted,'candidate_count':len(candidates),'link_status':'exact_unique_name_region_current_axis' if accepted else 'unresolved_homonym_or_absent','reference_date':'2012-01-01','source_document_date':'2012-08-10','source_url':'https://base.garant.ru/70271972/','current_monotown_status_asserted':False})
 md=pd.DataFrame(mono);md.to_csv(HERE/'historical_monotowns2012.csv',index=False)
 known=set(md.linked_id.dropna());f['historical_monotown_evidence']=pd.array(np.where(a.id.isin(known),True,None),dtype='boolean')
 # Current administrative seats from a separate source. Name+point corroboration is explicit.
 z=zipfile.ZipFile(RAW/'geonames.zip');gn=pd.read_csv(z.open('RU.txt'),sep='\t',header=None,low_memory=False)
 gn=gn[gn[7].isin(['PPLC','PPLA','PPLA2','PPLA3','PPLA4'])].copy();admin=[]
 for _,r in gn.iterrows():
  names={norm(n) for n in [r[1],r[2]]+str(r[3]).split(',') if str(n)!='nan'}
  nearby=tree.query_ball_point(xyz(np.array([float(r[4])]),np.array([float(r[5])]))[0],2*np.sin(10/12742.0176))
  c=located.iloc[nearby];c=c[c['_name'].isin(names)]
  match=c.id.iloc[0] if len(c)==1 else None
  admin.append({'geonameid':int(r[0]),'source_name':r[1],'feature_code':r[7],'lat':r[4],'lon':r[5],'linked_id':match,'candidate_count':len(c),'source_modified_date':r[18],'source_url':'https://download.geonames.org/export/dump/RU.zip','link_status':'unique_name_and_point_within10km' if match else 'unresolved_or_absent','official_russian_code_binding_asserted':False})
 ad=pd.DataFrame(admin);ad=ad.merge(a[['id','municipality_oktmo8_2021','municipality_upper_2021']],left_on='linked_id',right_on='id',how='left',validate='many_to_one');ad.to_csv(HERE/'geonames_administrative_seats.csv',index=False)
 f['geonames_administrative_seat_evidence']=pd.array(np.where(a.id.isin(ad.linked_id.dropna()),True,None),dtype='boolean')
 f['geonames_district_seat_evidence']=pd.array(np.where(a.id.isin(ad.loc[ad.feature_code.eq('PPLA2'),'linked_id'].dropna()),True,None),dtype='boolean')
 # These mechanisms need temporal/behavioral corroboration; a mine, minority share or old plant is insufficient.
 for c in ['industrial_decline_evidence','resource_shift_evidence','ethnocultural_demographic_evidence','commuting_observed']:f[c]=pd.array([pd.NA]*len(f),dtype='boolean')
 f['thematic_source_snapshot_date']='2026-10-21';f['osm_context_snapshot_date']='2026-10-19'
 f['proximity_counts_are_context_not_identity']=True;f['negative_record_means_actual_absence']=False
 f.to_parquet(HERE/'settlement_features.parquet',index=False)
 receipt={'status':'COMPUTED_THEMATIC_WITNESSES_NOT_COMPLETE_TYPE_CAUSAL_PROOF','axis_rows':len(a),'unique_ids':f.id.nunique(),'sanatorium_points':int(rp.category.eq('sanatorium_registry_site').sum()),'designated_resort_points':int(rp.category.eq('designated_resort_point').sum()),'resort_polygons_raw':len(polygon_records),'invalid_or_degenerate_resort_polygons':len(invalid),'osm_thematic_assertions':len(osm),'historical_monotown_rows':len(md),'historical_monotown_linked':int(md.linked_id.notna().sum()),'admin_seat_source_rows':len(ad),'admin_seat_linked':int(ad.linked_id.notna().sum()),'positive_features':{c:int(f[c].fillna(False).sum()) for c in f if str(f[c].dtype)=='boolean'},'semantics':{'resort_geometry':'YandexlatlonconvertedtoGeoJSONlonlat;invalidsourcegeometriesnotusedasareas','negative':'noacceptedwitnessnotabsence','historical_mono':'2012designationandenterprisewitnessnot2026statusorphysicaldecline','resource':'mappedminewellquarrynotrotationalworktransition','ethnicity':'mechanismunknownuntilindependentdemographic/identityevidence','proximity':'separatecontextualcandidate,notacceptedsettlementidentity'},'inputs':{str(p):sha(p) for p in [axisfile,RAW/'resorts_health_json.json',RAW/'monotowns2012.html',RAW/'geonames.zip']+files}}
 (HERE/'thematic_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k!='inputs'},ensure_ascii=False,indent=2))

if __name__=='__main__':create()
