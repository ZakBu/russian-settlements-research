#!/usr/bin/env python3
"""Versioned 2021 federal-child NP extension; preserves old observations, never invents 2010."""
from pathlib import Path
import hashlib,json,re,zipfile,math
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3];ROOT=REPO/'research/sgrt_word_completion_20261021'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
oldpath=ROOT/'axis/full_settlement_axis.parquet';source=ROOT/'typology/sources/allsettlements_20260925/data_allsettlements_anon_156_v20260925.parquet';queue=HERE/'latest2021_extra_np_source_queue.parquet';oldledger=ROOT/'axis/source_observations_all.parquet'
paths=[oldpath,source,queue,oldledger];before={str(p.relative_to(REPO)):sha(p) for p in paths}
a=pd.read_parquet(oldpath);q=pd.read_parquet(queue);x=q[q.federal_child_source].copy().sort_values('native_np_oktmo11').reset_index(drop=True)
checks=[]
def check(name,v):checks.append(dict(check=name,passed=bool(v)))
check('only335_federal_children_added',len(x)==335 and x.region.isin(['Москва','Севастополь']).all())
check('no_Faktoriya_scope_conflict_admitted',~x.native_np_oktmo11.eq('11701363001').any())
check('all_source2021_native_codes_unique',x.native_np_oktmo11.is_unique)
# Type is read only from an explicit prefix; unknown source types stay generic.
def parse(v):
 for prefix,kind in [('г. ','город'),('пгт ','пгт'),('деревня ','деревня'),('село ','село'),('посёлок ','посёлок'),('поселок ','посёлок'),('хутор ','хутор')]:
  if v.startswith(prefix):
   name=v[len(prefix):].strip()
   if kind=='пгт':name=re.sub(r'\s+(?:дп|рп)$','',name)
   return name,kind,'explicit_census_source_object_name_prefix'
 return v,'населённый пункт','source_NP_type_unspecified_no_urban_or_rural_type_invented'
parsed=[parse(v) for v in x.object_name];add=pd.DataFrame({'id':['np2021supp:'+v for v in x.native_np_oktmo11],'name':[p[0] for p in parsed],'type':[p[1] for p in parsed],'region':x.region.map({'Москва':'москва','Севастополь':'севастополь'}),'lat':pd.to_numeric(x.latitude),'lon':pd.to_numeric(x.longitude),'population_2021':x.population.astype(float)})
for year in [2002,2010]:
 add[f'population_{year}']=np.nan;add[f'source_record_id_{year}']=None;add[f'population_value_quality_{year}']=None;add[f'district_raw_{year}']=None;add[f'oktmo_{year}']=None;add[f'okato_{year}']=None
add['source_record_id_2021']=[f'2021:data_allsettlements_anon_156_v20260925.parquet:parquet:{int(v)}' for v in x.source_row_1based]
add['population_value_quality_2021']='direct_published_census_value'
add['district_raw_2021']=x.mun_upper;add['oktmo_2021']=x.native_np_oktmo11;add['okato_2021']=None
# A child of a federal city is not automatically an upper-level BDMO municipality.
add['municipality_oktmo8_2021']=None;add['municipality_upper_2021']=x.mun_upper
add['root']=add.source_record_id_2021;add['latest_observation_year']=2021
add['axis_kind']='supplemental_federal_child2021_source_entity';add['three_census_complete']=False;add['is_additive_source_unit']=True
add['geography_status']='own_NP_source_point20260925_coordinate_measurement_date_unknown_precision_uncalibrated'
add['population_scope']='settlement'
add['source2021_raw_object_name']=x.object_name;add['source2021_type_rule']=[p[2] for p in parsed]
add['source2021_file_sha256']=sha(source);add['source2021_file_version']='20260925'
add['source2021_raw_row_1based']=x.source_row_1based.astype(int)
add['coordinate_measurement_date_unknown']=True;add['coordinate_precision_calibrated']=False
add['coordinate_source_geocoder_quality_raw']=x.qc_geo_dadata.astype('Int64')
add['coordinate_geocoder_quality_note']='RawDAdataQC3settlement/4city/5unspecified; sourceoriginalpoint retained; not an accuracy estimate'
add['coordinate_source']='own2021NP nativecode+population verified; sourceParquet20260925 explicit latitude/longitude'
add['source2021_supplemental_history_identity_linked']=False
check('all335_actual_source_points_numeric_and_geographic_range_valid',add.lat.between(-90,90).all() and add.lon.between(-180,180).all())
# Broad regional bounds are a sanity check, not a substitute for legal polygons.
check('all_Moscow_source_points_in_disclosed_broad_sanity_bounds',add.loc[add.region.eq('москва'),'lat'].between(54.5,56.5).all() and add.loc[add.region.eq('москва'),'lon'].between(36,39).all())
check('all_Sevastopol_source_points_in_disclosed_broad_sanity_bounds',add.loc[add.region.eq('севастополь'),'lat'].between(44,45).all() and add.loc[add.region.eq('севастополь'),'lon'].between(33,34.5).all())
# Kokoshkino's QC5 means DAdata unspecified. Preserve a separate external named-point
# witness and all name rivals; no precision calibration or provider independence claim.
gz=Path('/workspace/scratch/sgrt_themes/geonames.zip');witness=[]
with zipfile.ZipFile(gz) as z:
 for line in z.open('RU.txt'):
  fields=line.decode('utf-8').rstrip('\n').split('\t')
  if 'kokoshkin' in '\t'.join(fields[1:4]).lower():witness.append(fields)
(HERE/'kokoshkino_geonames_all_name_rivals.tsv').write_text('\n'.join('\t'.join(v) for v in witness)+'\n')
w=[v for v in witness if v[0]=='546606'];check('Kokoshkino_separate_named_source_witness_unique',len(w)==1)
r=add[add.oktmo_2021.eq('45947000051')].iloc[0];g=w[0]
lat1,lat2=math.radians(r.lat),math.radians(float(g[4]));dl=math.radians(float(g[5])-r.lon);da=lat2-lat1
metres=6371008.8*2*math.asin(math.sqrt(math.sin(da/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dl/2)**2))
check('Kokoshkino_source_point_within1km_of_named_GeoNames_locality',metres<1000)
add['coordinate_external_named_witness_geonames_id']=pd.NA
add.loc[add.oktmo_2021.eq('45947000051'),'coordinate_external_named_witness_geonames_id']='546606'
check('new_ids_do_not_collide_with_frozen_axis',set(add.id).isdisjoint(set(a.id)))
check('no_new2010_or2002_population_invented',add.population_2010.isna().all() and add.population_2002.isna().all())
check('new_population_sum_exact742897',int(add.population_2021.sum())==742897)
add.to_parquet(HERE/'federal_np2021_axis_addendum.parquet',index=False)
# Whole federal territories and source anchors remain separate nonadditive context.
newold=a.copy();fed=newold.axis_kind.eq('federal_territory_source_unit');newold.loc[fed,'is_additive_source_unit']=False
new=pd.concat([newold,add],ignore_index=True,sort=False)
check('new_axis173862_unique_ids',len(new)==173862 and new.id.is_unique)
for column in a.columns:
 if column!='is_additive_source_unit':
  check('frozen_column_'+column+'_unchanged',new.iloc[:len(a)][column].reset_index(drop=True).equals(a[column].reset_index(drop=True)))
check('only_federal_territory_additivity_flags_changed',newold.loc[~fed,'is_additive_source_unit'].equals(a.loc[~fed,'is_additive_source_unit']) and newold.loc[fed,'is_additive_source_unit'].eq(False).all())
ordinary=new.is_additive_source_unit&~new.axis_kind.str.contains('territory|external_service',case=False)
check('ordinary2021_population_exact128765177_not_national147m',int(new.loc[ordinary,'population_2021'].sum())==128765177)
new.to_parquet(HERE/'full_settlement_axis_cycle05_federal_children.parquet',index=False)
ledger=pd.read_parquet(oldledger);supp=pd.DataFrame({'id':add.id,'root':add.root,'source_record_id':add.source_record_id_2021,'census_year':2021,'population':add.population_2021,'population_value_quality':add.population_value_quality_2021,'is_additive_settlement_record':True,'latitude_accepted':add.lat,'longitude_accepted':add.lon,'coordinate_admission_status':'explicit_own_source_NP_point_with_disclosed_raw_QC_and_no_calibration','point_origin_kind':'own2021source_file20260925','source_raw_row_1based':add.source2021_raw_row_1based,'source_file_sha256':add.source2021_file_sha256})
newledger=pd.concat([ledger,supp],ignore_index=True,sort=False)
check('new_ledger_source_ids_and_entityyears_unique',newledger.source_record_id.is_unique and not newledger.duplicated(['id','census_year']).any())
check('new_ledger_and_axis_entitysets_exact',set(newledger.id)==set(new.id))
newledger.to_parquet(HERE/'source_observations_all_cycle05_federal_children.parquet',index=False)
# Historic candidates are kept for later independent identity review, never silently linked.
oldhist=a[a.population_2021.isna()&a.lat.notna()&a.lon.notna()].copy();pot=[]
def n(v):return re.sub('[^а-яa-z0-9]+',' ',str(v).lower().replace('ё','е')).strip()
oldhist['name_comparison']=oldhist.name.map(n)
for row in add.itertuples():
 for v in oldhist[oldhist.name_comparison.eq(n(row.name))].itertuples():
  la,lb=math.radians(row.lat),math.radians(v.lat);dd=math.radians(row.lon-v.lon);dist=6371008.8*2*math.asin(math.sqrt(math.sin((la-lb)/2)**2+math.cos(la)*math.cos(lb)*math.sin(dd/2)**2))
  if dist<=5000:pot.append(dict(new_id=row.id,historical_id=v.id,name=row.name,historical_region=v.region,current_region=row.region,distance_metres=dist,population_2010_original=v.population_2010,population_2002_original=v.population_2002,identity_accepted=False,source_rule='literal_normalized_name_within5km_candidate_only_all_rivals_retained'))
pd.DataFrame(pot).to_csv(HERE/'supplemental2021_historical_identity_candidates_NOT_ACCEPTED.csv',index=False)
check('frozen_inputs_unchanged',before=={str(p.relative_to(REPO)):sha(p) for p in paths})
names=['build_federal_np_addendum.py','federal_np2021_axis_addendum.parquet','full_settlement_axis_cycle05_federal_children.parquet','source_observations_all_cycle05_federal_children.parquet','kokoshkino_geonames_all_name_rivals.tsv','supplemental2021_historical_identity_candidates_NOT_ACCEPTED.csv']
receipt=dict(status='335_REAL2021_FEDERAL_CHILD_NP_ADDED_WITHOUT_HISTORY_IMPUTATION_OR_POPULATION_DOUBLECOUNT',n_checks=len(checks),n_failed=sum(not c['passed'] for c in checks),checks=checks,old_axis_rows=len(a),new_axis_rows=len(new),new2021_np_rows=len(add),new2021_np_population=int(add.population_2021.sum()),new_ordinary2021_population=128765177,national_population_coverage_claim=False,federal_territorial_context_population2021=int(newold.loc[fed,'population_2021'].sum()),federal_territorial_rows_marked_nonadditive=int(fed.sum()),external_ctx_Moscow_SPB_changed=False,regions=add.region.value_counts().to_dict(),known_new2010=0,known_new2002=0,source_type_rule_counts=add.source2021_type_rule.value_counts().to_dict(),source_QC_counts={str(k):int(v) for k,v in add.coordinate_source_geocoder_quality_raw.value_counts().items()},coordinate_measurement_date_unknown=True,coordinate_precision_calibrated=False,Kokoshkino_external_named_witness_distance_metres=metres,geonames_zip_sha256=sha(gz),historical_identity_candidates_not_accepted=len(pot),old_frozen_axis_modified=False,inputs_sha256=before,outputs={n:dict(sha256=sha(HERE/n),bytes=(HERE/n).stat().st_size) for n in names})
(HERE/'federal_np_addendum_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['checks','inputs_sha256','outputs']},ensure_ascii=False,indent=2))
