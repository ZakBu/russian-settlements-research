#!/usr/bin/env python3
"""Reported organizationaddress→typedcensuslocality; no physicalcampus inference."""
from pathlib import Path
import pandas as pd,numpy as np,re,json,hashlib,datetime
HERE=Path(__file__).resolve().parent;BASE=HERE.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(v):return re.sub('[^а-яa-z0-9]+',' ',str(v).lower().replace('ё','е')).strip()
# Only explicitsettlementtype prefixes, nevermunicipal 'городскойокруг'.
PAT=re.compile(r'(?<![А-Яа-яA-Za-z])(?P<type>п\s*\.\s*г\s*\.\s*т\s*\.?|пгт\.?|р\s*\.\s*п\s*\.?|рабочий\s+пос[её]лок|город\s+|г\s*\.(?!\s*о\s*\.)|деревня\s+|д\s*\.\s*(?=[А-ЯЁ])|село\s+|с\s*\.\s*(?=[А-ЯЁ])|пос[её]лок\s+|пос\s*\.\s*|п\s*\.\s*(?=[А-ЯЁ])|хутор\s+|х\s*\.\s*(?=[А-ЯЁ])|станица\s+)(?P<name>[^,;\n]+)',re.I)
# Note: house д.54 is rejected because name must start with alphabeticletter;
# 'д.Кордон' remainsan explicitvillage.
def declared(text):
 out=[]
 for m in PAT.finditer(str(text or'')):
  p=norm(m['type']);name=re.split(r'\s+(?:ул\.|улица\b|проспект\b|просп\.|переулок\b|пер\.|шоссе\b|дом\b|д\.\s*\d|пл\.|площадь\b|микрорайон\b|мкр\.)',m['name'],maxsplit=1,flags=re.I)[0].strip().rstrip('.')
  if not re.match('[А-Яа-яЁёA-Za-z]',name):continue
  if p in ['п г т','пгт','р п','рабочий поселок']:types=['пгт','посёлок городского типа','рабочий посёлок'];kind='пгт'
  elif p in ['г','город']:types=['город'];kind='город'
  elif p in ['д','деревня']:types=['деревня'];kind='деревня'
  elif p in ['с','село']:types=['село'];kind='село'
  elif p in ['п','пос','поселок']:types=['посёлок'];kind='посёлок'
  elif p in ['х','хутор']:types=['хутор'];kind='хутор'
  elif p=='станица':types=['станица'];kind='станица'
  else:continue
  out.append({'name':name,'normalized_name':norm(name),'source_type':kind,'accepted_native_type_labels':types,'source_span':m.group(),'start':m.start()})
 return out

def main():
 src=HERE/'official_monitoring2021_reporting_organizations.parquet';ax=BASE/'axis/full_settlement_axis.parquet';d=pd.read_parquet(src);a=pd.read_parquet(ax);a=a[a.is_additive_source_unit.eq(True)&a.population_2021.notna()&a.lat.notna()&a.lon.notna()].copy();a['_name']=a.name.map(norm);rows=[]
 for _,r in d.iterrows():
  address=declared(r.source_reported_address);city=declared(r.source_reported_city);chosen=address[-1]if address else city[-1]if city else None;row={'reporting_unit_key':r.reporting_unit_key,'source_reported_city':r.source_reported_city,'source_reported_address':r.source_reported_address,'explicit_address_localities_json':json.dumps(address,ensure_ascii=False),'explicit_reported_city_localities_json':json.dumps(city,ensure_ascii=False),'selected_declaration_role':'innermost_explicit_reported_address_locality'if address else'explicit_reported_city_without_parsable_address_locality'if city else'unparsed','reported_org_locality_typed_uid':None,'selected_source_name':chosen['name']if chosen else None,'selected_source_type':chosen['source_type']if chosen else None,'source_coordinates_are_geocoded_address_not_field_measurement':True,'not_proven_teaching_site':True}
  if not chosen:row['typed_identity_status']='no_unambiguous_explicit_name_and_type_parse';row['axis_candidates_json']='[]';rows.append(row);continue
  z=a[a['_name'].eq(chosen['normalized_name'])&a.type.isin(chosen['accepted_native_type_labels'])].copy()
  if len(z):
   x=np.radians(z.lat.to_numpy());y=np.radians(z.lon.to_numpy());p=np.radians(r.lat);q=np.radians(r.lon);dist=6371.0088*2*np.arcsin(np.sqrt(np.clip(np.sin((x-p)/2)**2+np.cos(x)*np.cos(p)*np.sin((y-q)/2)**2,0,1)));z['source_point_distance_km']=dist
  else:z['source_point_distance_km']=[]
  limit=50 if chosen['source_type']in ['город','пгт']else 10;near=z[z.source_point_distance_km.le(limit)]
  row['axis_candidates_json']=json.dumps(z[['id','name','type','region','source_point_distance_km']].to_dict('records'),ensure_ascii=False);row['plausibility_distance_limit_km']=limit
  if len(near)==1:row.update(reported_org_locality_typed_uid=near.iloc[0].id,typed_identity_status='unique_source_declared_name_type_with_map_plausibility',source_point_distance_km=near.iloc[0].source_point_distance_km)
  elif len(near)>1:row['typed_identity_status']='ambiguous_explicit_same_name_type_within_plausibility_radius'
  elif not len(z):row['typed_identity_status']='explicit_name_type_not_found_in_accepted2021censusframe'
  else:row['typed_identity_status']='explicit_name_type_map_coordinate_conflict_retained'
  rows.append(row)
 out=pd.DataFrame(rows);scope=out.reported_org_locality_typed_uid.map(pd.read_parquet(ax).set_index('id').population_scope);out['typed_target_population_scope']=scope;out['reported_org_federal_territory_context_uid']=out.reported_org_locality_typed_uid.where(scope.ne('settlement'));out.loc[scope.ne('settlement')&out.reported_org_locality_typed_uid.notna(),'typed_identity_status']='explicit_federal_territory_context_not_ordinary_settlement';out.loc[scope.ne('settlement'),'reported_org_locality_typed_uid']=None;out.to_parquet(HERE/'official_monitoring2021_typed_address_identity.parquet',index=False);joined=d.merge(out[['reporting_unit_key','reported_org_locality_typed_uid','typed_identity_status']],on='reporting_unit_key',validate='one_to_one');features=pd.read_parquet(ax,columns=['id'])
 for sec in ['vpo','spo']:
  z=joined[joined.education_sector.eq(sec)&joined.reported_org_locality_typed_uid.notna()];features[f'official2021_{sec}_typed_reported_org_locality_witness_count']=features.id.map(z.groupby('reported_org_locality_typed_uid').size()).fillna(0).astype('int32')
 features['organization_address_not_physical_teaching_site']=True;features['absence_means_unknown']=True;features.to_parquet(HERE/'official_monitoring2021_typed_locality_features.parquet',index=False)
 receipt={'status':'EXPLICIT_TYPED_ORGANIZATION_ADDRESS_IDENTITIES_PENDING_INDEPENDENT_REVIEW','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_reporting_unit_rows':len(d),'matched_typed_organization_locality_rows':int(out.reported_org_locality_typed_uid.notna().sum()),'statuses':out.typed_identity_status.value_counts().to_dict(),'source_school_or_trip_model_assignments_read':False,'physical_osm_features_modified':False,'method':'Parseinnermostexplicittypedlocalityinreportaddress; fallbackexplicitreportedcity. Exactnormalizedname+nativecensustype withcoordinateplausibility50kmurban/10kmrural; retainambiguitiesandcoordinateconflicts. Thisidentifiesreportedorgaddresslocality, notteachingcampus.','plausibility_radius_is_not_service_catchment':True,'source_files_sha256':{str(src):sha(src),str(ax):sha(ax)},'code_sha256':sha(Path(__file__)),'output_files_sha256':{p.name:sha(p)for p in [HERE/'official_monitoring2021_typed_address_identity.parquet',HERE/'official_monitoring2021_typed_locality_features.parquet']}}
 (HERE/'official_monitoring2021_typed_identity_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2));print(joined.groupby('education_sector').reported_org_locality_typed_uid.agg(['count','nunique']))
if __name__=='__main__':main()
