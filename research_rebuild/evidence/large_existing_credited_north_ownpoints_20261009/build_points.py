from pathlib import Path
import pandas as pd, zipfile, hashlib, json, csv
BASE=Path(__file__).resolve().parent
E=BASE.parent/'large_existing_credit_missing_ownpoint_20261009'
ROSTER=E/'all_raw_or_primary_over1000_without_State_ownpoint.csv'
ZIP=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
ZIP_SHA=hashlib.sha256(ZIP.read_bytes()).hexdigest()
# Independently matched to retained named-populated-place records in cached RU.txt.
# Same accepted named locality/source UID may recur in another census year; each gets its own point-use row.
GID_BY_SOURCE={
'2002:003_308406b0ed_02c_Vladimirskaja.xls:Sheet1:5':'7042500',
'2002:058_a73d73c7dd_02c-Tyumen_obl_new.xls:Sheet1:15':'1511538',
'2002:058_a73d73c7dd_02c-Tyumen_obl_new.xls:Sheet1:31':'7607282',
'2002:058_a73d73c7dd_02c-Tyumen_obl_new.xls:Sheet1:32':'1539186',
'2002:058_a73d73c7dd_02c-Tyumen_obl_new.xls:Sheet1:35':'7607271',
'2002:058_a73d73c7dd_02c-Tyumen_obl_new.xls:Sheet1:38':'1495566',
'2002:058_a73d73c7dd_02c-Tyumen_obl_new.xls:Sheet1:5':'7607281',
'2002:1_TOM_01_04.xls:0:1948':'560154',
'2002:1_TOM_01_04.xls:0:1949':'544293',
'2002:1_TOM_01_04.xls:0:1950':'527578',
'2002:1_TOM_01_04.xls:0:1951':'492218',
'2002:1_TOM_01_04.xls:0:1960':'496269',
'2002:1_TOM_01_04.xls:0:1961':'465721',
'2002:1_TOM_01_04.xls:0:1962':'545719',
'2002:1_TOM_01_04.xls:0:1963':'517773',
'2002:1_TOM_01_04.xls:0:1964':'508216',
'2002:1_TOM_01_04.xls:0:1965':'500713',
'2002:1_TOM_01_04.xls:0:1966':'496020',
'2002:1_TOM_01_04.xls:0:248':'7042412',
'2002:1_TOM_01_04.xls:0:249':'466260',
'2002:1_TOM_01_04.xls:0:5936':'532860',
'2002:1_TOM_01_04.xls:0:5937':'6267009',
'2002:1_TOM_01_04.xls:0:6654':'517111',
'2002:1_TOM_01_04.xls:0:7402':'11049038',
'2002:1_TOM_01_04.xls:0:7405':'1492142',
'2002:1_TOM_01_04.xls:0:7723':'1499042',
'2002:1_TOM_01_04.xls:0:8696':'1504139',
'2002:1_TOM_01_04.xls:0:8697':'1490256',
'2002:1_TOM_01_04.xls:0:9751':'2023190',
'2002:1_TOM_01_04.xls:0:9753':'2020221',
'2002:1_TOM_01_04.xls:0:9754':'2015746',
'2002:1_TOM_01_04.xls:0:9933':'2027454',
'2002:1_TOM_01_04.xls:0:9934':'2012623',
'2002:1_TOM_01_04.xls:0:9935':'2014571',
'2002:1_TOM_01_04.xls:0:9958':'2013258',
'2002:1_TOM_01_04.xls:0:9959':'2020734',
'2010:003_eb441570b1_11._20Урал_ФО_2010.xls:Урал:2500':'7607281',
'2010:003_eb441570b1_11._20Урал_ФО_2010.xls:Урал:2503':'1511538',
'2010:003_eb441570b1_11._20Урал_ФО_2010.xls:Урал:2509':'7607269',
'2010:009_81f8a0e73c_17._20ДВ_ФО_2010.xls:ДВ:2851':'2015746',
}
D=pd.read_csv(ROSTER,dtype={'source_record_id':str})
region_map={'тюменская':'тюменская','тульская':'тульская','владимирская':'владимирская','кировская':'кировская','пермский':'пермский','свердловская':'свердловская','красноярский':'красноярский','саха якутия':'саха якутия','приморский':'приморский'}
D=D[D.region_norm.isin(region_map)].copy()
assert len(D)==40, len(D)
assert set(D.source_record_id)==set(GID_BY_SOURCE), (len(set(D.source_record_id)-set(GID_BY_SOURCE)),len(set(GID_BY_SOURCE)-set(D.source_record_id)))
with zipfile.ZipFile(ZIP) as z:
 ru_bytes=z.read('RU.txt'); RU_SHA=hashlib.sha256(ru_bytes).hexdigest(); lines=ru_bytes.decode('utf-8').splitlines()
 geo={}
 for i,line in enumerate(lines,1):
  fields=line.split('\t')
  if fields[0] in set(GID_BY_SOURCE.values()): geo[fields[0]]=(i,fields,line)
assert len(geo)==len(set(GID_BY_SOURCE.values()))
admin_by_region={'тюменская':'78','тульская':'76','владимирская':'83','кировская':'33','пермский':'90','свердловская':'71','красноярский':'91','саха якутия':'63','приморский':'59'}
point_rows=[]; witnesses=[]
for r in D.itertuples(index=False):
 sid=r.source_record_id; srcname=str(r.settlement_name).strip(); gid=GID_BY_SOURCE[sid]; lineno,f,raw=geo[gid]
 # GeoNames format: id,name,ascii,aliases,lat,lon,class,feature,country,cc2,admin1
 if f[6]!='P' or f[7] not in {'PPL','PPLA','PPLX','PPLH'} or f[8]!='RU' or f[10]!=admin_by_region[r.region_norm]:
  raise AssertionError((sid,gid,lineno,f[:11]))
 lat,lon=float(f[4]),float(f[5])
 locator=f'RU.txt:line{lineno};geonameid={gid};feature={f[7]};country={f[8]};admin1={f[10]};fields=latitude,longitude;ownname={f[1]};aliases={f[3]}'
 point_rows.append({
  'target_source_record_id':sid,'latitude':lat,'longitude':lon,
  'coordinate_admission_status':'reviewed_rule_accepted','coordinate_source_record_id':f'GeoNames:{gid}',
  'source_sha256':ZIP_SHA,'source_locator':locator,'point_origin_file':str(ZIP),
  'point_origin_sha256':ZIP_SHA,'point_origin_locator':locator,
  'point_origin_kind':'own_named_former_NP_GeoNames_cached_retained_PPL_or_PPLX_point',
  'admission_rule':'Exact cached GeoNames RU populated-place feature; explicit feature class PPL/PPLX, country RU, admin1 region agrees, and own name/alias is a native settlement name. Accepted native identity/lifecycle is baseline; no population or identity inference from the provider point.',
  'retrospective_point_use_is_continuity_inference':True,'historical_census_coordinate_asserted':False,
  'population_boundary_comparability_asserted':False,'native_code_binding_asserted':False})
 witnesses.append({'source_record_id':sid,'census_year':r.census_year,'settlement_name':srcname,'settlement_type':r.settlement_type,'region_norm':r.region_norm,'native_population':r.population,'geonameid':gid,'geonames_line_number':lineno,'feature_class':f[6],'feature_code':f[7],'country_code':f[8],'admin1_code':f[10],'geonames_name':f[1],'ascii_name':f[2],'alternate_names':f[3],'latitude':lat,'longitude':lon,'raw_ru_txt_line':raw,'source_file':str(ZIP),'source_sha256':ZIP_SHA})
point=pd.DataFrame(point_rows)
assert point.target_source_record_id.nunique()==40 and len(point)==40
point.to_csv(BASE/'accepted_point_use_delta.csv',index=False)
pd.DataFrame(witnesses).to_csv(BASE/'ownpoint_source_row_witnesses.csv',index=False)
# Preserve the precise assigned roster and outcome for reproducible application.
D[['source_record_id','census_year','settlement_name','settlement_type','region_norm','population','source_file','source_path','source_sha256','source_locator']].to_csv(BASE/'assigned_roster.csv',index=False)
manifest={'packet_id':'large_existing_credited_north_ownpoints_20261009','input_roster_path':str(ROSTER),'input_roster_sha256':hashlib.sha256(ROSTER.read_bytes()).hexdigest(),'input_roster_rows_in_assigned_regions':len(D),'assigned_regions':sorted(D.region_norm.unique()),'point_rows':len(point),'unique_point_targets':int(point.target_source_record_id.nunique()),'geoNames_source':str(ZIP),'geoNames_source_sha256':ZIP_SHA,'GeoNames_ru_txt_sha256':RU_SHA,'scope':'Own locality points for baseline-accepted source rows only; no identity, count, lifecycle, or population-boundary re-audit; no municipality parent point use.','point_interpretation':'Cached GeoNames populated-place coordinates are modern representative points reused retrospectively on the already-accepted native-locality route. They are not census-day measurements, legal boundaries, or population-equivalent centroids.','files':{}}
for name in ['accepted_point_use_delta.csv','ownpoint_source_row_witnesses.csv','assigned_roster.csv','build_points.py']:
 p=BASE/name;manifest['files'][name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
(BASE/'FINAL_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
