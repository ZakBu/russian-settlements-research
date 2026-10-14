"""Combine source-backed historical observations without changing native census layers."""
from pathlib import Path
import json,hashlib,math,collections
import pandas as pd
E=Path(__file__).resolve().parent;B=E.parent
CORE=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
core=pd.read_parquet(CORE,columns=['root','census_year','source_record_id','region_norm'])
years=core.groupby('root').census_year.apply(lambda x:'|'.join(map(str,sorted(set(x))))) .to_dict()
regions=core.drop_duplicates('root').set_index('root').region_norm.to_dict()
inputs=[]
def read(path):
 inputs.append(path);return pd.read_parquet(path)
def clean(v):
 if v is None:return None
 try:
  if pd.isna(v):return None
 except (ValueError,TypeError):pass
 return v
def canonical(r,year,kind,basis,primary=False):
 r={k:clean(v) for k,v in r.items()}
 root=r.get('root');pop=r.get('population_total') or r.get('population') or r.get('population_value')
 lat=r.get('accepted_latitude') or r.get('latitude') or r.get('reference_latitude');lon=r.get('accepted_longitude') or r.get('longitude') or r.get('reference_longitude')
 if not root or pop is None or lat is None or lon is None:return None
 return {'root':root,'anchor_source_record_id':r.get('anchor_source_record_id'),'year':year,'historical_name':r.get('source_name_parsed_for_binding') or r.get('historical_name') or r.get('settlement_name') or r.get('current_name'),'current_region':regions.get(root) or r.get('current_region') or r.get('current_region_alias'),'population':int(float(pop)),'population_male':int(float(r['population_male'])) if r.get('population_male') else None,'population_female':int(float(r['population_female'])) if r.get('population_female') else None,'population_basis':basis,'source_kind':kind,'source_record_id':r.get('source_record_id') or r.get('statement_uri_raw') or f"{r.get('source_pdf_sha256')}:{r.get('source_pdf_page_1based')}:{root}:{year}:{basis}",'source_url':r.get('source_url') or r.get('statement_uri_raw'),'source_sha256':r.get('source_sha256') or r.get('source_pdf_sha256') or r.get('source_population_sha256'),'source_locator':r.get('source_locator') or r.get('source_row_label') or str(r.get('source_population_file'))+':row0:'+str(r.get('source_population_row_0based')),'latitude':float(lat),'longitude':float(lon),'coordinate_source_record_id':r.get('coordinate_source_record_id') or r.get('anchor_source_record_id'),'coordinate_source_url':r.get('coordinate_source_url'),'coordinate_source_sha256':r.get('coordinate_source_sha256'),'coordinate_source_locator':r.get('coordinate_source_locator'),'point_identity_grade':r.get('point_identity_grade') or r.get('coordinate_role') or r.get('point_proof_basis'),'external_id':r.get('external_id') or r.get('wikidata_qid'),'external_id_candidate':r.get('external_id_candidate'),'external_identity_asserted':bool(r.get('external_identity_asserted') or r.get('wikidata_qid')),'binding_status':r.get('binding_status') or r.get('identity_1979_status'),'linked_census_years':years.get(root,''),'current_full3_chain':years.get(root)=='2002|2010|2021','retrospective_current_point_inference':True,'historical_boundary_comparability':'UNKNOWN','population_value_quality':'published_1979_census_closed_population_accounting_unresolved' if primary and year==1979 else 'official_published_1989_census_unresolved_confidentiality_redistribution' if primary else 'secondary_literal_year_primary_unverified','source_date_raw':r.get('source_date_raw'),'source_date_precision':r.get('date_precision') or 'UNKNOWN','date_basis':'official_census_campaign_year' if primary else 'literal_dated_year_not_automatically_census','qualifiers_verification':r.get('whole_item_qualifiers_verification'),'quantity_unit_verification':r.get('quantity_unit_verification'),'source_claim_proofs_json':r.get('source_proofs_json') or r.get('source_population_raw_json'),'matched_1989_source_record_id':r.get('matched_1989_source_record_id'),'historical_identity_event':r.get('historical_identity_event')}
wiki=read(B/'rsfsr1979_wikidata_mass_20261014/secondary_population_1979_long.parquet')
native_delta=read(B/'rsfsr1979_wikidata_mass_20261014/deltabinding1979native_population_long.parquet')
wiki=pd.concat([wiki,native_delta],ignore_index=True)
qmap={}
for q,grp in wiki.groupby('wikidata_qid'):
 if grp.root.nunique()==1:qmap[q]=grp.iloc[0].to_dict()
def map_verified_external_root(row):
 q=row.get('external_id');v=qmap.get(q)
 if v and row['root']!=v['root']:
  la1,lo1,la2,lo2=map(math.radians,[row['latitude'],row['longitude'],v['latitude'],v['longitude']])
  km=6371*2*math.asin(min(1,math.sqrt(math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2)))
  if km<=5:
   row['historical_original_root']=row['root'];row['root']=v['root'];row['anchor_source_record_id']=v['anchor_source_record_id'];row['root_projection_rule']='same_verified_physical_external_item_unique_accepted_current_NP_point_within5km_historical_continuity_inferred';row['linked_census_years']=years.get(v['root'],'');row['current_full3_chain']=years.get(v['root'])=='2002|2010|2021'
 return row
old89=read(B/'rsfsr1989_integration_20261013/population_1989_selected_long.parquet')
delta=read(B/'rsfsr1989_residual_points_20261014/combined_reviewed_primary_delta.parquet')
mapped89=[map_verified_external_root(r) for r in old89.to_dict('records')];selected89={r['root']:r for r in mapped89};alts=[];upgrade=0;new=0
for r in delta.to_dict('records'):
 row=canonical(r,1989,'official_census_transcription',r['population_basis'],True);prev=selected89.get(row['root'])
 if prev:
  alts.append({'year':1989,'root':row['root'],'previous_source':prev['source_record_id'],'new_source':row['source_record_id'],'previous_population':prev['population'],'new_population':row['population']})
  if prev['source_kind']=='official_census_transcription':continue
  upgrade+=1
 else:new+=1
 selected89[row['root']]=row
pd.DataFrame(selected89.values()).to_parquet(E/'population_1989_selected_long.parquet',index=False)
# Native1979 published present counts have priority over retrospective books/secondary claims.
prim=read(B/'rsfsr1979_primary_binding_20261014/primary_bindings_augmented.parquet')
ency=read(B/'rsfsr1979_cached_series_20261014/population_1979_selected_long.parquet')
correction_path=B/'rsfsr1989_residual_points_20261014/bounded1979_homonym_correction_facts.parquet'
corrections={r['source_record_id']:r for r in read(correction_path).to_dict('records')}
collision_path=B/'rsfsr1989_residual_points_20261014/bounded1979_collision_correction_facts.parquet'
corrections.update({r['source_record_id']:r for r in read(collision_path).to_dict('records')})
selected79={};holds=[]
for frame,kind,primary in [(prim,'official_census_transcription',True),(ency,None,False),(wiki,'wikidata_dated_claim',False)]:
 for r in frame.to_dict('records'):
  if primary and not str(r['binding_status']).startswith('bound'):continue
  correction=corrections.get(r.get('source_record_id')) if primary else None
  if correction and str(correction.get('correction_status','')).startswith('held'):
   holds.append({'source':r['source_record_id'],'population':int(r['population_total']),'reason':correction['correction_status']});continue
  if correction:
   r.update(correction);r['root']=correction['corrected_root'];r['binding_status']='bound_corrected_historical_identity_explicit_published_event';r['anchor_source_record_id']=clean(correction.get('anchor_source_record_id'));r['historical_identity_event']=correction.get('event_or_region_explanation')
  row=canonical(r,1979,kind or r['source_kind'],r['population_basis'],primary)
  if row is None:continue
  row=map_verified_external_root(row)
  if row['root'] in ['2002:041_4b428edd23_Bashkiria_new.xls:Sheet1:3287','2002:037_5b0d431685_02c_Stavrolpski.xls:Sheet1:1023'] and primary:
   holds.append({'source':row['source_record_id'],'population':row['population'],'reason':'1979_urban_to_1989_small_rural_homonym_or_absorption_identity_conflict'});continue
  if row['external_id']=='Q193909':holds.append({'source':row['source_record_id'],'reason':'closed_city_potential_overlap_with_published_urban_totals'});continue
  prev=selected79.get(row['root'])
  if prev:
   alts.append({'year':1979,'root':row['root'],'selected_source':prev['source_record_id'],'alternative_source':row['source_record_id'],'selected_population':prev['population'],'alternative_population':row['population'],'same_value':prev['population']==row['population']});continue
  selected79[row['root']]=row
pd.DataFrame(selected79.values()).to_parquet(E/'population_1979_selected_long.parquet',index=False)
full=pd.concat([pd.DataFrame(selected79.values()),pd.DataFrame(selected89.values())],ignore_index=True)
full.to_parquet(E/'population_1979_1989_long.parquet',index=False)
full.to_csv(E/'population_1979_1989_long.csv.gz',index=False,compression={'method':'gzip','mtime':0})
(E/'overlapping_observations.json').write_text(json.dumps(alts,ensure_ascii=False,indent=2));(E/'held_observations.json').write_text(json.dumps(holds,ensure_ascii=False,indent=2))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
receipt={'inputs':{str(p):sha(p) for p in inputs+[CORE]},'native_2002_2010_2021_unchanged':True,'1989_primary_upgrades':upgrade,'1989_new_roots':new,'1989_population_change':sum(r['population'] for r in selected89.values())-int(old89.population.sum()),'years':{},'outputs':{}}
for year,data in [(1979,selected79),(1989,selected89)]:
 df=pd.DataFrame(data.values());assert not df.root.duplicated().any();assert df.population.ge(0).all();assert df.latitude.between(-90,90).all() and df.longitude.between(-180,180).all()
 groups=df.groupby(['source_kind','population_basis']).agg(subjects=('root','size'),people=('population','sum')).reset_index().to_dict('records')
 receipt['years'][str(year)]={'subjects':len(df),'selected_population_mixed_basis':int(df.population.sum()),'population_bound_to_current_full3_roots':int(df.loc[df.current_full3_chain,'population'].sum()),'groups':groups,'not_single_basis_official_coverage':True}
for p in E.glob('*.parquet'):receipt['outputs'][p.name]=sha(p)
(E/'integration_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k!='inputs'},ensure_ascii=False,indent=2))
