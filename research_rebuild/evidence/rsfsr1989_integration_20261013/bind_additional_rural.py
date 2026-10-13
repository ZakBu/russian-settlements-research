"""Bind published rural observations using literal region/name/district and existing points."""
import csv,re,json,math,hashlib,collections
from pathlib import Path
import pyarrow as pa,pyarrow.parquet as pq
E=Path(__file__).resolve().parent;B=E.parent
CORE=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
def n(x):return ' '.join(re.sub(r'[^а-яa-z0-9]+',' ',str(x or '').lower().replace('ё','е')).split())
def d(x):
 text=str(x or '').lower();text=re.sub(r'\bр[ -]*н\b','',text);return n(re.sub(r'\b(муниципальный|муниципальное|муниципального|округ|район)\b','',text))
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
cols=['source_record_id','census_year','name_norm','settlement_name','region_norm','district_raw','root','accepted_point_present','accepted_latitude','accepted_longitude','is_additive_settlement_record','settlement_type','population']
core=pq.read_table(CORE,columns=cols).to_pylist();index=collections.defaultdict(list);roots=collections.defaultdict(list)
for r in core:
 roots[r['root']].append(r)
 if r['is_additive_settlement_record']:index[(n(r['region_norm']),n(r['name_norm']))].append(r)
reg={'Республика Татарстан':'татарстан','Республика Башкортостан':'башкортостан','Алтайский край':'алтайский'}
source_paths=[B/'rsfsr1989_rural_south_20261013/primary_rural_1989_usable.csv',B/'rsfsr1989_rural_volga_20261013/tatarica_rural_1989_facts.csv',B/'rsfsr1989_rural_volga_20261013/bashenc_rural_1989_facts.csv',B/'rsfsr1989_rural_south_round2_20261013/kchr1989_usable.csv',B/'rsfsr1989_rural_bashenc_delta_20261013/final_facts.csv',B/'rsfsr1989_rural_tyumen_20261013/tyumen1989_usable.csv']
rows=[];status=collections.Counter()
for path in source_paths:
 kind='primary_regional_census' if ('south' in str(path) or 'tyumen' in str(path)) else 'secondary_encyclopedia_census_series'
 for raw in csv.DictReader(path.open()):
  if raw['source_record_id']=='bashenc:4199bc43024df35e':continue # frozen chunk erratum: urban in 1989, primary source takes priority
  region=reg.get(raw.get('region_norm'),raw.get('region_norm'));name=raw.get('name_norm') or n(raw.get('settlement_name') or raw.get('name_raw'));district=raw.get('district_raw','');p=int(float(raw['population']));assert p>=0
  all_candidates=index[(n(region),n(name))];candidates=all_candidates;qualified=[x for x in candidates if d(x['district_raw'])==d(district)] if district else candidates
  if district:candidates=qualified
  chosen=None;rule='';count=0
  paired=raw.get('population_2002')
  try:paired=float(paired) if paired not in (None,'','-','x') else None
  except ValueError:paired=None
  paired_candidates=[x for x in all_candidates if x['census_year']==2002 and paired is not None and paired>0 and x['population']==paired]
  paired_roots={x['root'] for x in paired_candidates}
  if len(paired_roots)==1:
   chosen=paired_candidates[0];rule='official_comparative_1989_2002_table_literal_name_region_unique_exact_2002_population';count=1
  for year in (2021,2010,2002):
   if chosen:break
   subset=[x for x in candidates if x['census_year']==year];rootids={x['root'] for x in subset};count=len(rootids)
   if len(rootids)==1:
    chosen=max(subset,key=lambda x:bool(x['accepted_point_present']));rule='literal_name_region_district_unique_snapshot_prefer_latest';break
   if rootids:break
  point=None
  if chosen:
   ps=[x for x in roots[chosen['root']] if x['accepted_point_present'] and x['accepted_latitude'] is not None and x['accepted_longitude'] is not None and math.isfinite(x['accepted_latitude']) and math.isfinite(x['accepted_longitude'])]
   if ps:point=max(ps,key=lambda x:x['census_year'])
   if not point and district:
    modern=[x for x in all_candidates if x['census_year']==2021 and d(x['district_raw'])==d(district) and x['accepted_point_present'] and x['accepted_latitude'] is not None and x['accepted_longitude'] is not None and math.isfinite(x['accepted_latitude']) and math.isfinite(x['accepted_longitude'])]
    if len({x['root'] for x in modern})==1:
     point=modern[0];rule+=';point_only_unique_modern_name_region_county_no_intercensus_graph_merge'
  state='bound_existing_accepted_point' if point else 'held_no_accepted_point' if chosen else 'held_competing_roots' if count else 'held_no_literal_qualified_match'
  status[state]+=1
  rows.append({'source_record_id':raw['source_record_id'],'source_kind':kind,'source_file':str(path),'source_sha256':raw.get('source_sha256'),'source_url':raw.get('source_url'),'source_locator':raw.get('source_locator') or raw.get('source_path') or 'article Число жителей:1989','year':1989,'historical_name':raw.get('settlement_name') or raw.get('name_raw'),'region':region,'district':district,'population':p,'population_male':int(float(raw['male_1989'])) if raw.get('male_1989') else None,'population_female':int(float(raw['female_1989'])) if raw.get('female_1989') else None,'population_basis':raw.get('population_basis') or raw.get('population_residency_basis') or 'publisher_1989_count_basis_not_yet_verified','binding_status':state,'binding_rule':rule,'source_paired_2002_population':paired,'source_county_literal_alignment':bool(chosen and d(chosen['district_raw'])==d(district)),'candidate_root_count':count,'anchor_source_record_id':chosen['source_record_id'] if chosen else None,'root':chosen['root'] if chosen else None,'point_source_record_id':point['source_record_id'] if point else None,'point_source_root':point['root'] if point else None,'point_only_cross_root_inference':bool(point and chosen and point['root']!=chosen['root']),'latitude':point['accepted_latitude'] if point else None,'longitude':point['accepted_longitude'] if point else None,'retrospective_current_point_inference':True,'historical_boundary_comparability':'UNKNOWN','publication_raw':json.dumps({k:v for k,v in raw.items() if k not in ('source_population_section','source_subtitle')},ensure_ascii=False)})
pq.write_table(pa.Table.from_pylist(rows),E/'additional_rural_bindings.parquet',compression='zstd')
accepted=[r for r in rows if r['binding_status']=='bound_existing_accepted_point']
receipt={'inputs':{str(p):sha(p) for p in source_paths+[CORE]},'rows':len(rows),'bound_rows':len(accepted),'bound_population_before_cross_source_dedup':sum(r['population'] for r in accepted),'status_counts':dict(status),'per_source':[{ 'source_kind':k,'rows':sum(r['source_kind']==k for r in accepted),'population':sum(r['population'] for r in accepted if r['source_kind']==k)} for k in sorted({r['source_kind'] for r in rows})],'output_sha256':sha(E/'additional_rural_bindings.parquet'),'excluded_frozen_chunk_source_ids':['bashenc:4199bc43024df35e'],'native_census_and_graph_unchanged':True}
(E/'additional_rural_binding_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
