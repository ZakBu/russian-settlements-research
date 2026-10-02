"""Population-weighted selected-row coordinate screen for 2021; no admissions."""
from __future__ import annotations
import argparse, hashlib, io, json, re, unicodedata, zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .coordinate_rules import in_broad_russia_envelope, valid_wgs84, haversine_km

SELECTED_DEFAULT=Path('/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet')
MANIFEST_DEFAULT=SELECTED_DEFAULT.parent/'release_manifest.json'
RAW_ZIP_DEFAULT=Path('/workspace/settlements-raw/data/raw/2021/tochno_2021.zip')
RAW_MEMBER='data_allsettlements_anon_156_v20251217.parquet'
BASELINE_DEFAULT=Path('/workspace/settlements-baseline/output')
WIKIDATA_DEFAULT=Path('/workspace/settlements-work/wikidata/point_bindings.parquet')
PRIOR_COORDINATE_ADMISSIONS=Path('/workspace/settlements-data/research_rebuild/evidence/releases/national_reviewed_admissions_r5b_yearbook_20260930/coordinate_admissions.csv')
OUTPUT_DEFAULT=Path('/workspace/settlements-work/coordinates/ledger')
KNOWN_PHYSICAL_P31={'Q486972':'human_settlement','Q532':'village','Q515':'city'}
RAW_COLUMNS=['object_level','object_name','oktmo','region','mun_upper','mun_lower','settlement','population','settlement_fias_id_dadata','settlement_with_type_dadata','settlement_type_dadata','settlement_type_full_dadata','settlement_dadata','fias_id_dadata','fias_level_dadata','okato_dadata','oktmo_dadata','qc_geo_dadata','qc_dadata','latitude_dadata','longitude_dadata']
QA_COLUMNS=['source_record_id','settlement_id','coordinate_source_record_id','coordinate_candidate_source','candidate_latitude','candidate_longitude','fias_level_dadata','qc_geo_dadata','address_level_mismatch','provider_reports_no_coordinate','federal_city_region_scope','provider_coordinate_conflict','coordinate_corroborated_provider','coordinate_wgs84_valid','coordinate_in_russia_envelope','duplicate_point_group_size','duplicate_point','coordinate_certified','coordinate_review_required','coordinate_quality_class','coordinate_passes_automated_screens']

def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def sha_file(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def norm(v):
 if v is None or pd.isna(v): return ''
 return ' '.join(unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е').split())
def typekey(v):
 s=re.sub(r'[^\w]+',' ',norm(v),flags=re.UNICODE).strip()
 # Explicit source/provider abbreviation equivalence, kept intentionally small.
 return {'пгт':'поселок городского типа'}.get(s,s)
def same(a,b): return bool(norm(a)) and norm(a)==norm(b)
def source_name_key(v):
 if v is None or pd.isna(v): return ''
 return norm(re.sub(r'\bno(?=\d)','no ',str(v).replace('№',' no '),flags=re.IGNORECASE))
def num(v):
 if v is None or pd.isna(v): return None
 try:
  x=float(v); return x if np.isfinite(x) else None
 except (TypeError,ValueError): return None
def strval(v):
 if v is None or pd.isna(v): return ''
 return str(v).strip()

def provider_family(value):
 s=norm(value)
 if 'dadata' in s or 'tochno' in s: return 'tochno_dadata'
 if 'wikidata' in s or 'wikipedia' in s: return 'wikidata_wikipedia'
 if 'rcsi' in s or 'minzdrav' in s: return 'rcsi_minzdrav'
 if 'gis-lab' in s: return 'gis_lab'
 return s or 'unknown'

def haversine_array(lat1,lon1,lat2,lon2):
 a=np.column_stack([pd.to_numeric(lat1,errors='coerce').to_numpy(dtype=float),pd.to_numeric(lon1,errors='coerce').to_numpy(dtype=float),pd.to_numeric(lat2,errors='coerce').to_numpy(dtype=float),pd.to_numeric(lon2,errors='coerce').to_numpy(dtype=float)])
 ok=np.isfinite(a).all(axis=1)&(a[:,0]>=-90)&(a[:,0]<=90)&(a[:,2]>=-90)&(a[:,2]<=90)&(a[:,1]>=-180)&(a[:,1]<=180)&(a[:,3]>=-180)&(a[:,3]<=180)
 result=np.full(len(a),np.nan)
 if ok.any():
  x=np.radians(a[ok]); dlat=x[:,2]-x[:,0]; dlon=x[:,3]-x[:,1]
  h=np.sin(dlat/2)**2+np.cos(x[:,0])*np.cos(x[:,2])*np.sin(dlon/2)**2
  result[ok]=2*6371.0088*np.arcsin(np.sqrt(np.minimum(1,h)))
 return result

def source_row_index(sid,source_row):
 m=re.search(r':parquet:(\d+)$',str(sid))
 if not m: raise ValueError(f'no parquet row locator in selected 2021 ID: {sid}')
 n=int(source_row)
 if int(m.group(1))!=n or n<1: raise ValueError(f'ID/source_row mismatch: {sid}; source_row={source_row}')
 return n-1

def screen_candidate(row:Mapping[str,Any])->dict[str,Any]:
 physical=norm(row.get('raw_object_level')) in {'населенный пункт','населённый пункт'}
 atomic=norm(row.get('population_scope')) not in {'federal_city_region','municipality','municipal_aggregate','region','administrative_area','territorial_aggregate'}
 own=strval(row.get('provider_settlement_fias_id')); general=strval(row.get('provider_general_fias_id')); level=strval(row.get('provider_fias_level'))
 name_ok=same(row.get('selected_settlement_name',row.get('settlement_name')),row.get('provider_settlement_name'))
 type_value=row.get('selected_settlement_type',row.get('settlement_type'))
 type_ok=bool(typekey(type_value)) and typekey(type_value)==typekey(row.get('provider_settlement_type_full'))
 lat,lon=num(row.get('provider_latitude')),num(row.get('provider_longitude'))
 point_ok=valid_wgs84(lat,lon); russia=point_ok and in_broad_russia_envelope(lat,lon)
 own_general=bool(own and own==general); no_id_contradiction=not (own and general and own!=general)
 provider_object_present=bool(general) and level in {'4','6'}
 conflict=row.get('baseline_provider_coordinate_conflict'); no_conflict=not (conflict is True or isinstance(conflict,(np.bool_,bool)) and bool(conflict))
 unique_id=row.get('provider_general_fias_duplicate_count',1)<=1; unique_point=row.get('provider_coordinate_duplicate_count',1)<=1
 gates={
 'source_is_naselenniy_punkt':physical,'selected_population_scope_not_aggregate':atomic,
 'provider_primary_fias_object_present_at_level_4_or_6':provider_object_present,
 'provider_secondary_settlement_id_not_contradictory':no_id_contradiction,
 'provider_fias_level_4_or_6':level in {'4','6'},'provider_name_exact_selected_name':name_ok,
 'provider_full_type_exact_selected_type':type_ok,'provider_point_valid_wgs84':point_ok,
 'provider_point_inside_coarse_russia_envelope':bool(russia),'no_baseline_known_coordinate_conflict':no_conflict,
 'provider_primary_fias_id_unique_in_selected_rows':unique_id,'provider_coordinate_unique_in_selected_rows':unique_point}
 d=num(row.get('selected_to_dadata_distance_km'))
 return {**{'gate_'+k:v for k,v in gates.items()},'candidate_family_exact_named_physical_np_fias_point':all(gates.values()),
 'provider_admin_context_exactly_compared':False,'provider_admin_context_limitation':'No returned DaData parent/admin chain in source; region/municipality fields are census-row context.',
 'selected_point_available':valid_wgs84(row.get('selected_latitude'),row.get('selected_longitude')),
 'selected_point_matches_dadata_within_1m':d is not None and d<=.001,
 'candidate_status':'review_candidate_only' if all(gates.values()) else 'hold_or_incomplete_screen','admission_allowed':False}

def baseline_claims(selected,raw_provider,baseline_dir):
 qp=baseline_dir/'observation_quality.parquet'; cp=baseline_dir/'coordinate_claims.parquet'
 if not (qp.is_file() and cp.is_file()): return pd.DataFrame({'source_record_id':selected.source_record_id.astype(str)})
 quality=pd.read_parquet(qp,columns=QA_COLUMNS); quality=quality[quality.source_record_id.astype(str).isin(set(selected.source_record_id.astype(str)))].copy()
 if quality.source_record_id.duplicated().any(): raise ValueError('duplicate exact source IDs in baseline observation quality')
 claims=pd.read_parquet(cp)
 mapping=selected[['source_record_id']].merge(quality[['source_record_id','settlement_id']],on='source_record_id',how='left',validate='one_to_one')
 joined=mapping.merge(claims,on='settlement_id',how='left',validate='many_to_many')
 joined['family']=joined.source.map(provider_family); joined['other_family']=~joined.family.eq('tochno_dadata')
 pts=pd.DataFrame({'source_record_id':selected.source_record_id.astype(str),'lat':pd.to_numeric(raw_provider.latitude_dadata,errors='coerce'),'lon':pd.to_numeric(raw_provider.longitude_dadata,errors='coerce')})
 joined=joined.merge(pts,on='source_record_id',how='left',validate='many_to_one')
 ds=haversine_array(joined.lat,joined.lon,joined.latitude,joined.longitude)
 joined['other_family_near']=joined.other_family & pd.Series(ds,index=joined.index).le(.5)
 rows=[]
 for sid,g in joined.groupby('source_record_id',sort=False):
  fs=sorted(set(g.family.dropna())-{'unknown'}); ofs=sorted(set(g.loc[g.other_family,'family'].dropna())-{'unknown'}); near=sorted(set(g.loc[g.other_family_near,'family'].dropna())-{'unknown'})
  rows.append({'source_record_id':sid,'baseline_claim_rows':int(g.claim_id.notna().sum()),'baseline_claim_families_json':json.dumps(fs,ensure_ascii=False),'baseline_other_claim_families_json':json.dumps(ofs,ensure_ascii=False),'baseline_other_families_within_0_5km_json':json.dumps(near,ensure_ascii=False),'baseline_other_family_within_0_5km':bool(near)})
 return pd.DataFrame(rows).merge(quality,on='source_record_id',how='left',validate='one_to_one')

def build(selected_path=SELECTED_DEFAULT,manifest_path=MANIFEST_DEFAULT,raw_zip_path=RAW_ZIP_DEFAULT,baseline_dir=BASELINE_DEFAULT,wikidata_path=WIKIDATA_DEFAULT,output=OUTPUT_DEFAULT):
 output.mkdir(parents=True,exist_ok=True)
 sel=pd.read_parquet(selected_path); sel=sel[sel.census_year.eq(2021)].copy().reset_index(drop=True)
 if sel.source_record_id.astype(str).duplicated().any(): raise ValueError('selected 2021 source_record_id is not unique')
 with zipfile.ZipFile(raw_zip_path) as z: raw_bytes=z.read(RAW_MEMBER)
 source_hash=sha_bytes(raw_bytes); raw=pq.read_table(io.BytesIO(raw_bytes),columns=RAW_COLUMNS).to_pandas()
 idx=[source_row_index(r.source_record_id,r.source_row) for r in sel.itertuples(index=False)]
 if len(set(idx))!=len(idx) or min(idx,default=0)<0 or max(idx,default=-1)>=len(raw): raise ValueError('source row locator is not one-to-one/in-range')
 prov=raw.iloc[idx].reset_index(drop=True)
 if not pd.to_numeric(prov.population).reset_index(drop=True).eq(pd.to_numeric(sel.population).reset_index(drop=True)).all(): raise ValueError('selected-row source index failed population check')
 if not prov.oktmo.fillna('').astype(str).reset_index(drop=True).eq(sel.oktmo.fillna('').astype(str).reset_index(drop=True)).all(): raise ValueError('selected-row source index failed exact OKTMO check')
 raw_names=prov.object_name.map(source_name_key).reset_index(drop=True)
 selected_names=sel.source_name_raw.map(source_name_key).reset_index(drop=True)
 if not raw_names.eq(selected_names).all(): raise ValueError('selected-row source index failed name check beyond whitespace')
 f=sel.copy()
 for c in RAW_COLUMNS: f['raw_'+c]=prov[c].to_numpy()
 f['raw_row_link_status']='exact_source_row_index_population_oktmo_name_reconciled'
 f['provider_settlement_fias_id']=prov.settlement_fias_id_dadata.astype('string').to_numpy()
 f['provider_general_fias_id']=prov.fias_id_dadata.astype('string').to_numpy()
 f['provider_fias_level']=prov.fias_level_dadata.astype('string').to_numpy()
 f['provider_settlement_name']=prov.settlement_dadata.astype('string').to_numpy()
 f['provider_settlement_type_full']=prov.settlement_type_full_dadata.astype('string').to_numpy()
 f['provider_settlement_type_abbrev']=prov.settlement_type_dadata.astype('string').to_numpy()
 f['provider_typed_name']=prov.settlement_with_type_dadata.astype('string').to_numpy()
 f['provider_latitude']=pd.to_numeric(prov.latitude_dadata,errors='coerce').to_numpy(); f['provider_longitude']=pd.to_numeric(prov.longitude_dadata,errors='coerce').to_numpy()
 f['provider_point_available']=f.provider_latitude.notna()&f.provider_longitude.notna()
 f['provider_point_valid_wgs84']=[valid_wgs84(a,b) for a,b in zip(f.provider_latitude,f.provider_longitude)]
 f['provider_point_in_coarse_russia_envelope']=[in_broad_russia_envelope(a,b) for a,b in zip(f.provider_latitude,f.provider_longitude)]
 f['provider_name_exact_selected_name']=[same(a,b) for a,b in zip(f.settlement_name,f.provider_settlement_name)]
 f['provider_type_exact_selected_type']=[bool(typekey(a)) and typekey(a)==typekey(b) for a,b in zip(f.settlement_type,f.provider_settlement_type_full)]
 f['provider_typed_name_exact_source_typed_name']=[same(a,b) for a,b in zip(prov.settlement,prov.settlement_with_type_dadata)]
 primary_text=prov.fias_id_dadata.astype('string').fillna('')
 secondary_text=prov.settlement_fias_id_dadata.astype('string').fillna('')
 both_ids_present=primary_text.ne('')&secondary_text.ne('')
 f['provider_general_and_settlement_fias_ids_same']=(both_ids_present.to_numpy()&(primary_text==secondary_text).to_numpy())
 f['provider_settlement_id_differs_from_general_fias']=prov.settlement_fias_id_dadata.notna().to_numpy()&prov.fias_id_dadata.notna().to_numpy()&~f.provider_general_and_settlement_fias_ids_same.to_numpy()
 f['provider_fias_level_4_or_6']=f.provider_fias_level.isin(['4','6'])
 f['source_object_is_naselenniy_punkt']=prov.object_level.astype('string').str.casefold().isin(['населенный пункт','населённый пункт']).to_numpy()
 f['source_is_aggregate_scope']=f.population_scope.astype('string').isin(['federal_city_region','municipality','municipal_aggregate','region','administrative_area','territorial_aggregate'])
 f['census_region_context_raw']=prov.region.astype('string').to_numpy(); f['census_municipality_upper_raw']=prov.mun_upper.astype('string').to_numpy(); f['census_municipality_lower_raw']=prov.mun_lower.astype('string').to_numpy()
 f['provider_returned_admin_context_available']=False
 f['admin_context_evidence_note']='Raw source has census region/mun_upper/mun_lower; no DaData-returned parent/admin chain fields.'
 own=prov.settlement_fias_id_dadata.fillna('').astype(str); key=pd.Series([f'{float(a):.7f}|{float(b):.7f}' if valid_wgs84(a,b) else '' for a,b in zip(prov.latitude_dadata,prov.longitude_dadata)])
 f['provider_settlement_fias_duplicate_count']=own.map(own[own.ne('')].value_counts()).fillna(0).astype(int).to_numpy()
 general_ids=prov.fias_id_dadata.fillna('').astype(str)
 f['provider_general_fias_duplicate_count']=general_ids.map(general_ids[general_ids.ne('')].value_counts()).fillna(0).astype(int).to_numpy()
 f['provider_coordinate_duplicate_count']=key.map(key[key.ne('')].value_counts()).fillna(0).astype(int).to_numpy()
 f['qc_geo_dadata_raw']=prov.qc_geo_dadata.to_numpy(); f['qc_dadata_raw']=prov.qc_dadata.to_numpy(); f['provider_query_receipt_missing']=True; f['provider_measurement_date_unknown']=True
 ds=[haversine_km(a,b,c,d) for a,b,c,d in zip(f.latitude,f.longitude,f.provider_latitude,f.provider_longitude)]
 f['selected_to_dadata_distance_km']=ds; f['selected_matches_dadata_point_within_1m']=[d is not None and d<=.001 for d in ds]
 f['selected_point_valid_wgs84']=[valid_wgs84(a,b) for a,b in zip(f.latitude,f.longitude)]
 f['selected_point_in_coarse_russia_envelope']=[in_broad_russia_envelope(a,b) for a,b in zip(f.latitude,f.longitude)]
 qa=baseline_claims(sel,prov,baseline_dir)
 if 'baseline_claim_rows' in qa:
  qa=qa.rename(columns={c:'baseline_'+c for c in qa.columns if c!='source_record_id'})
  f=f.merge(qa,on='source_record_id',how='left',validate='one_to_one')
 if wikidata_path.is_file():
  w=pd.read_parquet(wikidata_path); w=w.drop_duplicates('source_record_id')
  cols=[c for c in ['source_record_id','wikidata_qid','provider_p721_okato_match_same_qid','name_comparison','wikidata_p17_is_russia','known_admin_only_type','wikidata_p31_qids_json','wikidata_p131_qids_json','wikidata_p17_qids_json','p625_valid_wgs84_point_count','p625_points_json'] if c in w.columns]
  w=w[cols].rename(columns={c:'wikidata_'+c for c in cols if c!='source_record_id'})
  f=f.merge(w,on='source_record_id',how='left',validate='one_to_one')
 else: f['wikidata_candidate_absent']=True
 wiki_rows=f.wikidata_wikidata_qid.notna() if 'wikidata_wikidata_qid' in f else pd.Series(False,index=f.index)
 f['wikidata_p625_nearest_distance_km']=np.nan; f['wikidata_p625_farthest_distance_km']=np.nan
 if wiki_rows.any() and 'wikidata_p625_points_json' in f:
  nearest=[];farthest=[]
  for ix in f.index[wiki_rows]:
   raw_points=f.at[ix,'wikidata_p625_points_json']
   valid=[]
   try:
    for point in json.loads('[]' if raw_points is None or pd.isna(raw_points) else str(raw_points)):
     d=haversine_km(f.at[ix,'provider_latitude'],f.at[ix,'provider_longitude'],point.get('latitude'),point.get('longitude'))
     if d is not None: valid.append(d)
   except (TypeError,ValueError,json.JSONDecodeError): pass
   nearest.append(min(valid) if valid else np.nan);farthest.append(max(valid) if valid else np.nan)
  f.loc[wiki_rows,'wikidata_p625_nearest_distance_km']=nearest
  f.loc[wiki_rows,'wikidata_p625_farthest_distance_km']=farthest
 f['wikidata_p625_nearest_over_0_5km_screen']=f.wikidata_p625_nearest_distance_km.gt(.5)
 f['wikidata_p625_any_point_over_5km_screen']=f.wikidata_p625_farthest_distance_km.gt(5)
 if PRIOR_COORDINATE_ADMISSIONS.is_file():
  pa=pd.read_csv(PRIOR_COORDINATE_ADMISSIONS,dtype={'target_source_record_id':'string'},keep_default_na=False)
  pa=pa[pa.target_year.eq(2021)].copy()
  pa=pa[['target_source_record_id','decision_id','coordinate_claim_id','coordinate_source_record_id','coordinate_source','coordinate_kind','latitude','longitude','decision_status','decision_rule']].drop_duplicates('target_source_record_id')
  pa=pa.rename(columns={c:'prior_'+c for c in pa.columns if c!='target_source_record_id'}).rename(columns={'target_source_record_id':'source_record_id'})
  f=f.merge(pa,on='source_record_id',how='left',validate='one_to_one')
  f['prior_coordinate_admission_exists']=f.prior_decision_id.notna()&f.prior_decision_id.astype('string').ne('')
 else: f['prior_coordinate_admission_exists']=False
 physical=f.source_object_is_naselenniy_punkt.fillna(False).astype(bool)
 atomic=~f.source_is_aggregate_scope.fillna(False).astype(bool)
 primary_present=f.provider_general_fias_id.notna()&f.provider_general_fias_id.astype('string').fillna('').ne('')&f.provider_fias_level_4_or_6.fillna(False).astype(bool)
 general_id=f.provider_general_fias_id.astype('string').fillna('')
 secondary_id=f.provider_settlement_fias_id.astype('string').fillna('')
 secondary_consistent=~(general_id.ne('')&secondary_id.ne('')&general_id.ne(secondary_id))
 level_ok=f.provider_fias_level_4_or_6.fillna(False).astype(bool)
 name_ok=f.provider_name_exact_selected_name.fillna(False).astype(bool)
 type_ok=f.provider_type_exact_selected_type.fillna(False).astype(bool)
 point_ok=f.provider_point_valid_wgs84.fillna(False).astype(bool)
 russia=f.provider_point_in_coarse_russia_envelope.fillna(False).astype(bool)
 conflict=f.get('baseline_provider_coordinate_conflict',pd.Series(False,index=f.index)).fillna(False).astype(bool)
 unique_id=f.provider_general_fias_duplicate_count.le(1)
 unique_point=f.provider_coordinate_duplicate_count.le(1)
 gate_frame=pd.DataFrame({
  'gate_source_is_naselenniy_punkt':physical,'gate_selected_population_scope_not_aggregate':atomic,
  'gate_provider_primary_fias_object_present_at_level_4_or_6':primary_present,
  'gate_provider_secondary_settlement_id_not_contradictory':secondary_consistent,
  'gate_provider_name_exact_selected_name':name_ok,
  'gate_provider_full_type_exact_selected_type':type_ok,'gate_provider_point_valid_wgs84':point_ok,
  'gate_provider_point_inside_coarse_russia_envelope':russia,'gate_no_baseline_known_coordinate_conflict':~conflict,
  'gate_provider_primary_fias_id_unique_in_selected_rows':unique_id,'gate_provider_coordinate_unique_in_selected_rows':unique_point},index=f.index)
 candidate=gate_frame.all(axis=1)
 gate_frame['candidate_family_exact_named_physical_np_fias_point']=candidate
 gate_frame['provider_admin_context_exactly_compared']=False
 gate_frame['provider_admin_context_limitation']='No returned DaData parent/admin chain in source; region/municipality fields are census-row context.'
 gate_frame['selected_point_available']=[valid_wgs84(a,b) for a,b in zip(f.latitude,f.longitude)]
 gate_frame['selected_point_matches_dadata_within_1m']=f.selected_matches_dadata_point_within_1m.fillna(False).astype(bool)
 gate_frame['candidate_status']=np.where(candidate,'review_candidate_only','hold_or_incomplete_screen')
 gate_frame['admission_allowed']=False
 f=pd.concat([f,gate_frame],axis=1)
 f['candidate_only_no_admission']=True
 f['coordinate_source_record_id']=f.source_record_id.astype(str)
 f['coordinate_provider']='Tochno source export with DaData-derived coordinate fields'
 f['coordinate_provider_id']=f.provider_general_fias_id
 f['settlement_provider_id']=f.provider_settlement_fias_id
 f['coordinate_id_role_note']='source_record_id=selected census observation; coordinate_source_record_id=source row locator; coordinate_provider_id=general FIAS result; settlement_provider_id=settlement-specific FIAS result.'
 f.to_parquet(output/'coordinate_screen.parquet',index=False)
 population=pd.to_numeric(f.population,errors='coerce').fillna(0)
 gates=[c for c in f.columns if c.startswith('gate_')]+['candidate_family_exact_named_physical_np_fias_point']
 summary=[{'gate':'all_selected_2021','rows':len(f),'population':int(population.sum())}]
 for g in gates:
  m=f[g].fillna(False).astype(bool); summary.append({'gate':g,'rows':int(m.sum()),'population':int(population[m].sum())})
 nested=['gate_source_is_naselenniy_punkt','gate_selected_population_scope_not_aggregate','gate_provider_primary_fias_object_present_at_level_4_or_6','gate_provider_secondary_settlement_id_not_contradictory','gate_provider_name_exact_selected_name','gate_provider_full_type_exact_selected_type','gate_provider_point_valid_wgs84','gate_provider_point_inside_coarse_russia_envelope','gate_no_baseline_known_coordinate_conflict','gate_provider_primary_fias_id_unique_in_selected_rows','gate_provider_coordinate_unique_in_selected_rows']
 mask=pd.Series(True,index=f.index)
 for g in nested:
  mask &= f[g].fillna(False).astype(bool); summary.append({'gate':'nested_through_'+g.removeprefix('gate_'),'rows':int(mask.sum()),'population':int(population[mask].sum())})
 pd.DataFrame(summary).to_csv(output/'gate_summary.csv',index=False)
 m={
 'selected_2021_rows':int(len(f)),'selected_2021_population':int(population.sum()),
 'raw_row_links_reconciled':int(f.raw_row_link_status.eq('exact_source_row_index_population_oktmo_name_reconciled').sum()),
 'provider_point_present':int(f.provider_point_available.sum()),'provider_point_valid_wgs84':int(f.provider_point_valid_wgs84.sum()),'provider_point_in_coarse_russia_envelope':int(f.provider_point_in_coarse_russia_envelope.sum()),
 'selected_release_point_valid':int(f.selected_point_valid_wgs84.sum()),'selected_release_point_same_as_dadata_within_1m':int(f.selected_matches_dadata_point_within_1m.sum()),
 'provider_fias_level4_or6':int(f.provider_fias_level_4_or_6.sum()),'provider_fias_level4_rows':int(f.provider_fias_level.eq('4').sum()),'provider_fias_level6_rows':int(f.provider_fias_level.eq('6').sum()),'provider_settlement_fias_present':int(f.provider_settlement_fias_id.notna().sum()),'provider_settlement_and_general_id_same':int(f.provider_general_and_settlement_fias_ids_same.sum()),'provider_settlement_id_differs':int(f.provider_settlement_id_differs_from_general_fias.sum()),
 'provider_name_exact':int(f.provider_name_exact_selected_name.sum()),'provider_type_exact':int(f.provider_type_exact_selected_type.sum()),'provider_admin_chain_available':0,'provider_query_receipt_missing':int(f.provider_query_receipt_missing.sum()),'provider_measurement_date_unknown':int(f.provider_measurement_date_unknown.sum()),
 'qc_geo_counts':{str(k):int(v) for k,v in f.qc_geo_dadata_raw.value_counts(dropna=False).items()},
 'baseline_provider_agreement_flag_true':int(f.get('baseline_coordinate_corroborated_provider',pd.Series(False,index=f.index)).fillna(False).sum()),'baseline_known_conflict_true':int(f.get('baseline_provider_coordinate_conflict',pd.Series(False,index=f.index)).fillna(False).sum()),'baseline_duplicate_point_true':int(f.get('baseline_duplicate_point',pd.Series(False,index=f.index)).fillna(False).sum()),'baseline_coordinate_certified_true':int(f.get('baseline_coordinate_certified',pd.Series(False,index=f.index)).fillna(False).sum()),'baseline_other_family_within_0_5km':int(f.get('baseline_baseline_other_family_within_0_5km',pd.Series(False,index=f.index)).fillna(False).sum()),
 'wikidata_same_qid_okato_candidates':int(f.get('wikidata_provider_p721_okato_match_same_qid',pd.Series(False,index=f.index)).fillna(False).sum()),'candidate_family_rows':int(f.candidate_family_exact_named_physical_np_fias_point.sum()),'candidate_family_population':int(population[f.candidate_family_exact_named_physical_np_fias_point].sum()),'candidate_family_admissions':0}
 city=f.settlement_type.fillna('').astype(str).str.casefold().eq('город')
 city_level4=city&f.provider_fias_level.eq('4')
 m['city_source_rows']=int(city.sum());m['city_source_population']=int(population[city].sum())
 m['city_with_provider_fias_level4_rows']=int(city_level4.sum());m['city_with_provider_fias_level4_population']=int(population[city_level4].sum())
 m['city_with_provider_returned_name_and_type_rows']=int((city&f.provider_name_exact_selected_name&f.provider_type_exact_selected_type).sum())
 m['city_provider_name_or_type_payload_missing_rows']=int((city&(~f.provider_name_exact_selected_name|~f.provider_type_exact_selected_type)).sum())
 pgt=f.settlement_type.fillna('').astype(str).str.casefold().eq('пгт')
 m['pgt_rows']=int(pgt.sum());m['pgt_population']=int(population[pgt].sum())
 m['source_object_level_counts']={str(k):int(v) for k,v in f.raw_object_level.value_counts(dropna=False).items()}
 m['source_census_type_counts_top30']={str(k):int(v) for k,v in f.settlement_type.value_counts(dropna=False).head(30).items()}
 wiki=wiki_rows
 m['wikidata_exact_p764_candidate_rows']=int(wiki.sum());m['wikidata_exact_p764_candidate_population']=int(population[wiki].sum())
 p721=f.get('wikidata_provider_p721_okato_match_same_qid',pd.Series(False,index=f.index)).fillna(False).astype(bool)
 m['wikidata_same_qid_p721_rows']=int((wiki&p721).sum());m['wikidata_same_qid_p721_population']=int(population[wiki&p721].sum())
 name_exact=f.get('wikidata_name_comparison',pd.Series('',index=f.index)).isin(['exact_label','exact_alias'])
 m['wikidata_exact_label_or_alias_rows']=int((wiki&name_exact).sum());m['wikidata_exact_label_or_alias_population']=int(population[wiki&name_exact].sum())
 wrong_country=wiki&~f.get('wikidata_wikidata_p17_is_russia',pd.Series(False,index=f.index)).fillna(False).astype(bool)
 admin_only=wiki&f.get('wikidata_known_admin_only_type',pd.Series(False,index=f.index)).fillna(False).astype(bool)
 m['wikidata_wrong_or_unasserted_russia_country_rows']=int(wrong_country.sum());m['wikidata_wrong_or_unasserted_russia_country_population']=int(population[wrong_country].sum())
 m['wikidata_known_admin_only_type_rows']=int(admin_only.sum());m['wikidata_known_admin_only_type_population']=int(population[admin_only].sum())
 m['wikidata_point_nearest_distance_over_0_5km_rows']=int((wiki&f.wikidata_p625_nearest_over_0_5km_screen).sum())
 m['wikidata_point_nearest_distance_over_0_5km_population']=int(population[wiki&f.wikidata_p625_nearest_over_0_5km_screen].sum())
 m['wikidata_any_point_over_5km_rows']=int((wiki&f.wikidata_p625_any_point_over_5km_screen).sum())
 m['wikidata_any_point_over_5km_population']=int(population[wiki&f.wikidata_p625_any_point_over_5km_screen].sum())
 m['wikidata_multiple_p625_points_rows']=int((wiki&pd.to_numeric(f.get('wikidata_p625_valid_wgs84_point_count',0),errors='coerce').fillna(0).gt(1)).sum())
 type_rows=defaultdict(int);type_pop=defaultdict(int);known_physical=pd.Series(False,index=f.index)
 raw_type_col='wikidata_wikidata_p31_qids_json'
 if raw_type_col in f:
  for i,value in f.loc[wiki,raw_type_col].items():
   try: types=set(json.loads('[]' if value is None or pd.isna(value) else str(value)))
   except (TypeError,ValueError,json.JSONDecodeError): types=set()
   for qid in types: type_rows[qid]+=1;type_pop[qid]+=int(population.at[i])
   if types & set(KNOWN_PHYSICAL_P31): known_physical.at[i]=True
 m['wikidata_explicit_physical_p31_whitelist']=KNOWN_PHYSICAL_P31
 m['wikidata_known_physical_p31_rows']=int((wiki&known_physical).sum());m['wikidata_known_physical_p31_population']=int(population[wiki&known_physical].sum())
 m['wikidata_p31_distinct_qid_rows']=dict(sorted(type_rows.items(),key=lambda kv:(-kv[1],kv[0])))
 m['wikidata_p31_distinct_qid_population']=dict(sorted(type_pop.items(),key=lambda kv:(-kv[1],kv[0])))
 p131col='wikidata_wikidata_p131_qids_json'
 if p131col in f:
  p131_present=f[p131col].map(lambda v: bool(v and v!='[]') if isinstance(v,str) else False)
  m['wikidata_candidate_p131_present_rows']=int((wiki&p131_present).sum());m['wikidata_candidate_p131_present_population']=int(population[wiki&p131_present].sum())
 type_strata={}
 for typ,grp in f.loc[wiki].groupby('settlement_type',dropna=False):
  key='(missing)' if pd.isna(typ) else str(typ)
  type_strata[key]={'rows':int(len(grp)),'population':int(population.loc[grp.index].sum())}
 m['wikidata_exact_p764_candidates_by_census_type']=type_strata
 inputs={'selected_observations':{'path':str(selected_path),'sha256':sha_file(selected_path)},'selection_manifest':{'path':str(manifest_path),'sha256':sha_file(manifest_path)},'raw_tochno_zip':{'path':str(raw_zip_path),'sha256':sha_file(raw_zip_path),'member':RAW_MEMBER,'member_sha256':source_hash,'rows':len(raw),'used_columns':RAW_COLUMNS}}
 for n in ['observation_quality.parquet','coordinate_claims.parquet']:
  p=baseline_dir/n
  if p.is_file():inputs['baseline_'+n]={'path':str(p),'sha256':sha_file(p)}
 if wikidata_path.is_file():inputs['wikidata_point_bindings']={'path':str(wikidata_path),'sha256':sha_file(wikidata_path)}
 if PRIOR_COORDINATE_ADMISSIONS.is_file():
  inputs['prior_reviewed_coordinate_admissions']={'path':str(PRIOR_COORDINATE_ADMISSIONS),'sha256':sha_file(PRIOR_COORDINATE_ADMISSIONS)}
 m['prior_reviewed_2021_coordinate_decision_rows']=int(f.prior_coordinate_admission_exists.sum())
 for family in ['wikidata_wikipedia','gis_lab','rcsi_minzdrav']:
  rows=0; pop=0
  for rec in f.get('baseline_baseline_other_families_within_0_5km_json',pd.Series(dtype=str)).dropna():
   if family in json.loads(rec): rows+=1
  if rows:
   # Weight unique exact source rows with family-level screen membership.
   mask=f.get('baseline_baseline_other_families_within_0_5km_json',pd.Series('',index=f.index)).fillna('').map(lambda s:family in json.loads(s))
   pop=int(population[mask].sum())
  m[f'baseline_{family}_within_0_5km_rows']=rows
  m[f'baseline_{family}_within_0_5km_population']=pop
 manifest={'status':'screen_only_no_coordinate_or_identity_admissions','method':'Selected R2 2021 exact one-based parquet row locator; reconcile original population, OKTMO and source object name after whitespace and number-sign spelling normalization; evaluate independent gates separately.','original_raw_schema':{'row_count':len(raw),'field_count':235,'oktmo_type':'string','used_fields':RAW_COLUMNS},'role_separation':{'source_record_id':'census observation','coordinate_source_record_id':'source row locator carrying coordinate','coordinate_provider_id':'general FIAS result ID','settlement_provider_id':'settlement-specific FIAS ID'},'limitations':['No per-record DaData request receipt, retrieval date, or returned DaData admin/parent chain in the frozen source. Census region/municipality fields are not provider-returned context.','qc_geo/qc are provider flags only; they do not establish correct object or coordinates.','Prior audit agreement/conflict/certification fields and coordinate claims are diagnostic; no previous admission is inherited. Baseline source-family proximity counts do not establish independently sourced point evidence.','Exact row indexing proves which source row carries the provider fields, not the correctness of the geocoding.','Current point use for 2002/2010 requires separate reviewed continuity.'],'inputs':inputs,'metrics':m,'outputs':{'coordinate_screen.parquet':{'rows':len(f)},'gate_summary.csv':{'rows':len(summary)}}}
 (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return manifest

def main():
 p=argparse.ArgumentParser();p.add_argument('--selected',type=Path,default=SELECTED_DEFAULT);p.add_argument('--selection-manifest',type=Path,default=MANIFEST_DEFAULT);p.add_argument('--raw-zip',type=Path,default=RAW_ZIP_DEFAULT);p.add_argument('--baseline-dir',type=Path,default=BASELINE_DEFAULT);p.add_argument('--wikidata-bindings',type=Path,default=WIKIDATA_DEFAULT);p.add_argument('--output',type=Path,default=OUTPUT_DEFAULT);a=p.parse_args();print(json.dumps(build(a.selected,a.selection_manifest,a.raw_zip,a.baseline_dir,a.wikidata_bindings,a.output),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
