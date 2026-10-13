"""Select one published 1989 observation per bound current subject; preserve alternatives."""
from pathlib import Path
import collections,json,hashlib,math
import pyarrow as pa,pyarrow.parquet as pq
E=Path(__file__).resolve().parent;B=E.parent
paths=[B/'rsfsr1989_primary_binding_20261013/primary_bindings.parquet',E/'additional_rural_bindings.parquet',B/'rsfsr1989_secondary_module_name_point_20261013/secondary_population_1989_long.parquet']
corepath=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
core={r['source_record_id']:r for r in pq.read_table(corepath,columns=['source_record_id','accepted_latitude','accepted_longitude','accepted_point_present','root','census_year']).to_pylist()}
years=collections.defaultdict(set)
for r in core.values():years[r['root']].add(r['census_year'])
override_path=B/'rsfsr1989_point_corrections_20261013/oktyabrsky_skopin_point_override.json'
point_override=json.loads(override_path.read_text())
selected={};external_seen={};reference_root_seen={};alternatives=[];excluded=[];nonadditive_zato=[]
extra=B/'rsfsr1989_external_points_20261013/external_point_delta.parquet'
if extra.exists():paths.insert(1,extra)
extra2=B/'rsfsr1989_external_points_delta2_20261013/external_point_delta2.parquet'
if extra2.exists():paths.insert(2,extra2)
extra3=B/'rsfsr1989_external_points_delta3_20261013/external_point_delta3.parquet'
if extra3.exists():paths.insert(3,extra3)
extra4=B/'rsfsr1989_external_points_delta4_20261013/external_point_delta4.parquet'
if extra4.exists():paths.insert(4,extra4)
extra5=B/'rsfsr1989_external_points_delta5_20261013/external_point_delta5.parquet'
if extra5.exists():paths.insert(5,extra5)
wiki=B/'wiki1989_cached_population_20261013/accepted_additional_facts.parquet'
if wiki.exists():paths.append(wiki)
for path in paths:
 tier=0 if path.name in ('primary_bindings.parquet','external_point_delta.parquet','external_point_delta2.parquet','external_point_delta3.parquet','external_point_delta4.parquet','external_point_delta5.parquet') else 1 if path.name=='additional_rural_bindings.parquet' else 2
 for r in pq.read_table(path).to_pylist():
  if r.get('source_record_id')==point_override['source_record_id']:
   r.update(point_override);r['current_region']='рязанская';r['wikidata_qid']=None
  status=r.get('binding_status','secondary_bound')
  if tier==0 and not status.startswith('bound_') and not status.startswith('accepted_'):continue
  if tier==1 and status!='bound_existing_accepted_point':continue
  region=r.get('current_region') or r.get('region') or r.get('current_region_alias') or ''
  if any(x in region.lower() for x in ['крым','севастопол']):excluded.append({'source':r.get('source_record_id') or r.get('statement_uri_raw'),'reason':'outside_RSFSR_1989'});continue
  if r.get('wikidata_qid')=='Q193909':
   nonadditive_zato.append(r);excluded.append({'source':r.get('statement_uri_raw'),'reason':'Seversk_1989_already_redistributed_in_published_urban_totals_do_not_add'});continue
  if r.get('root')=='2002:040_95a4475637_02c_Rostov_obl.xls:Sheet1:2207':
   excluded.append({'source':r.get('source_record_id'),'population_1989':438,'reason':'same_name_neighbor_root_point_collision_requires_distinct_own_point'});continue
  key=r['root'];anchor=r['anchor_source_record_id'];pt=core.get(anchor,{})
  if tier==2 and r.get('same_NP_year_value_conflict',False):
   excluded.append({'source':r['statement_uri_raw'],'reason':'conflicting_secondary_year_values'});continue
  row={'root':key,'anchor_source_record_id':anchor,'year':1989,'linked_census_years':'|'.join(map(str,sorted(years[key]))),'current_full3_chain':years[key]=={2002,2010,2021},'population':int(r.get('population_total') or r.get('population') or r.get('population_value')),'population_male':int(float(r['population_male'])) if r.get('population_male') is not None else None,'population_female':int(float(r['population_female'])) if r.get('population_female') is not None else None,'historical_name':r.get('source_name_parsed_for_binding') or r.get('historical_name') or r.get('current_name'),'current_region':region,'source_tier':('primary_demoscope_present','regional_primary_or_encyclopedia','secondary_wikipedia' if path==wiki else 'secondary_wikidata')[tier],'source_kind':r.get('source_kind') or ('official_census_transcription' if tier==0 else 'wikidata_dated_claim'),'population_basis':r['population_basis'],'population_value_quality':'official_published_1989_census_unresolved_confidentiality_redistribution' if tier==0 else 'regional_published_census_basis_retained' if r.get('source_kind')=='primary_regional_census' else 'secondary_dated_population_not_independently_primary_verified','latitude':r.get('accepted_latitude') or r.get('latitude') or pt.get('accepted_latitude'),'longitude':r.get('accepted_longitude') or r.get('longitude') or pt.get('accepted_longitude'),'binding_status':status,'coordinate_source_record_id':r.get('point_source_record_id') or anchor,'coordinate_source_url':r.get('coordinate_source_url'),'coordinate_source_sha256':r.get('coordinate_source_sha256'),'coordinate_source_locator':r.get('coordinate_source_locator'),'external_id':r.get('external_id') or r.get('wikidata_qid'),'external_id_candidate':r.get('external_id_candidate'),'external_identity_asserted':r.get('external_identity_asserted',bool(r.get('external_id') or r.get('wikidata_qid'))),'point_only_cross_root_inference':r.get('point_only_cross_root_inference',False),'point_source_root':r.get('point_source_root'),'point_identity_grade':r.get('point_identity_grade') or r.get('coordinate_role') or 'existing_accepted_NP_point','source_record_id':r.get('source_record_id') or r.get('statement_uri_raw') or str(r.get('source_url'))+':1989','source_url':r.get('source_url') or r.get('statement_uri_raw'),'source_locator':r.get('source_locator') or str(r.get('source_population_row_0based')),'source_sha256':r.get('source_sha256') or r.get('source_population_sha256'),'historical_boundary_comparability':'UNKNOWN','retrospective_current_point_inference':True,'census_method_verification':r.get('source_census_method_verification') or ('published_census' if tier==0 else 'publisher_basis_retained')}
  if row['latitude'] is None or row['longitude'] is None or not math.isfinite(row['latitude']) or not math.isfinite(row['longitude']):excluded.append({'source':row['source_record_id'],'reason':'no_finite_point'});continue
  previous=selected.get(key) or selected.get(reference_root_seen.get(key)) or selected.get(reference_root_seen.get(row['point_source_root'])) or (selected.get(external_seen.get(row['external_id'])) if row['external_id'] else None)
  if previous:
   alternatives.append({'root':key,'selected_root':previous['root'],'dedup_axis':'root_or_verified_same_external_physical_entity','selected_source_record_id':previous['source_record_id'],'alternative_source_record_id':row['source_record_id'],'selected_population':previous['population'],'alternative_population':row['population'],'same_value':previous['population']==row['population']});continue
  selected[key]=row
  reference_root_seen[key]=key
  if row['point_source_root']:reference_root_seen[row['point_source_root']]=key
  if row['external_id']:external_seen[row['external_id']]=key
if nonadditive_zato:pq.write_table(pa.Table.from_pylist(nonadditive_zato),E/'nonadditive_zato_observations.parquet',compression='zstd')
rows=list(selected.values());pq.write_table(pa.Table.from_pylist(rows),E/'population_1989_selected_long.parquet',compression='zstd')
(E/'overlapping_observations.json').write_text(json.dumps(alternatives,ensure_ascii=False,indent=2)+'\n');(E/'excluded_observations.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2)+'\n')
groups=collections.defaultdict(lambda:[0,0])
for r in rows:groups[(r['source_kind'],r['population_basis'])][0]+=1;groups[(r['source_kind'],r['population_basis'])][1]+=r['population']
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
receipt={'selected_subjects':len(rows),'selected_population_mixed_basis':sum(r['population'] for r in rows),'population_bound_to_existing_full3_roots':sum(r['population'] for r in rows if r['current_full3_chain']),'target':120000000,'shortfall':max(0,120000000-sum(r['population'] for r in rows)),'groups':[{'source_kind':k[0],'population_basis':k[1],'subjects':v[0],'people':v[1]} for k,v in groups.items()],'overlap_count':len(alternatives),'excluded':len(excluded),'not_a_single_basis_official_census_coverage':True,'official_1989_closed_city_redistribution_not_locally_corrected':True,'held_nonadditive_ZATO_observations':len(nonadditive_zato),'inputs':{str(p):sha(p) for p in paths+[corepath,override_path]},'output_sha256':sha(E/'population_1989_selected_long.parquet'),'native_2002_2010_2021_unchanged':True}
(E/'integration_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False,indent=2))
