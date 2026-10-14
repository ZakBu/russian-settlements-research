from pathlib import Path
import json,gzip,csv,hashlib,collections
from decimal import Decimal
import pyarrow as pa,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;O=Path('/workspace/shared/rsfsr1979_wikidata_mass');B=H.parent/'rsfsr1989_secondary_module_name_point_20261013'
P=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_population.tsv');M=Path('/workspace/settlements-raw/data/raw/wikipedia_statistical/module_qid_population.jsonl.gz');C=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet');S=H.parent/'rsfsr1989_integration_20261013/population_1989_selected_long.parquet'
def sha(p):return hashlib.file_digest(open(p,'rb'),'sha256').hexdigest()
inputs={str(p):sha(p) for p in [P,M,C,S,B/'current_own_NP_bindings.parquet',B/'secondary_population_1989_long.parquet']}
bind={r['wikidata_qid']:r for r in pq.read_table(B/'current_own_NP_bindings.parquet').to_pylist() if r['current_region'] not in ['крым','севастополь']}
points={r['source_record_id']:r for r in pq.read_table(C,columns=['source_record_id','accepted_latitude','accepted_longitude','accepted_point_present']).to_pylist()}
selected={r['root']:r for r in pq.read_table(S).to_pylist()};full={};manifest=[]
for d in ['rsfsr1989_secondary_name_point_20261013','rsfsr1989_secondary_module_name_point_20261013','rsfsr1989_secondary_okato_extension_20261013','rsfsr1989_secondary_mass_20261013']:
 for p in (Path('/workspace/scratch')/d/'api_cache').glob('*entity*json'):
  try:e=json.loads(p.read_text()).get('entities',{})
  except Exception:continue
  digest=sha(p);manifest.append({'path':str(p),'sha256':digest})
  for q,v in e.items():
   if q in bind:full[q]=(v,str(p),digest)
raw=[]
with open(P) as f:
 for i,r in enumerate(csv.DictReader(f,delimiter='\t',quoting=csv.QUOTE_NONE)):
  if r['?date'].startswith('1979-'):raw.append((P,i,{'item':r['?item'].strip('<>'),'statement':r['?statement'].strip('<>'),'population':r['?population'],'date':r['?date'],'rank':r['?rank']},r))
with gzip.open(M,'rt') as f:
 for i,l in enumerate(f):
  r=json.loads(l)
  if str(r.get('date','')).startswith('1979-'):raw.append((M,i,r,r))
rows=[];holds=[];seen={};unknown=[]
for p,i,r,orig in raw:
 q=r['item'].split('/')[-1];uri=r['statement'];guid=uri.split('/')[-1].replace('-','$',1);b=bind.get(q)
 if not b:unknown.append({'wikidata_qid':q,'source_file':str(p),'row0':i,'statement':uri,'reason':'no_previously_verified_own_NP_QID_binding'});continue
 n=Decimal(str(r['population']));why=[]
 if n<0 or n!=n.to_integral_value():why.append('invalid_quantity')
 e,path,digest=full.get(q,({},None,None));claims=[s for s in e.get('claims',{}).get('P1082',[]) if s.get('id','').casefold()==guid.casefold()];s=claims[0] if len(claims)==1 else None;qual=s.get('qualifiers',{}) if s else {};dates=[v.get('datavalue',{}).get('value',{}) for v in qual.get('P585',[])];v=s.get('mainsnak',{}).get('datavalue',{}).get('value',{}) if s else {}
 if s:
  if Decimal(v.get('amount','NaN'))!=n:why.append('API_quantity_disagrees')
  if v.get('unit')!='1':why.append('API_unit_not1')
  if set(qual)&{'P518','P642','P1534','P3005','P1011'}:why.append('explicit_subset')
  if s.get('rank') not in ['normal','preferred']:why.append('API_rank_not_allowed')
  if not dates or any(not str(x.get('time','')).startswith('+1979-') or x.get('precision',0)<9 for x in dates):why.append('API_date_not_literal1979')
 elif 'DeprecatedRank' in r['rank']:why.append('flat_deprecated_rank')
 if why:holds.append({'qid':q,'guid':guid,'reasons':why,'source_file':str(p),'row0':i});continue
 locator={'file':str(p),'sha256':inputs[str(p)],'row0':i,'raw':orig}
 key=(guid.casefold(),int(n),r['date'])
 if key in seen:seen[key]['source_proofs'].append(locator);continue
 pt=points.get(b['anchor_source_record_id'],{});sel=selected.get(b['root'],{})
 if pt.get('accepted_latitude') is None and sel.get('latitude') is not None:pt={**pt,'accepted_latitude':sel['latitude'],'accepted_longitude':sel['longitude']}
 point_basis='accepted_current_table' if points.get(b['anchor_source_record_id'],{}).get('accepted_latitude') is not None else 'selected1989_accepted_ownpoint_reference'
 row={**b,'observed_year':1979,'year':1979,'population_value':int(n),'population':int(n),'raw_population_literal':str(r['population']),'source_date_raw':r['date'],'statement_uri_raw':uri,'source_GUID':guid,'source_rank_raw':r['rank'],'source_tier':'wikidata_literal1979_secondary','primary_verification':'primary_unverified','population_basis':'UNKNOWN','source_census_method_verification':'UNKNOWN_generic_dated_P1082_not_automatically_census','boundary_comparability':'UNKNOWN','identity_1979_status':'inherited_verified_current_QID_binding_historical_continuity_inference','point_proof_basis':point_basis,'latitude':pt.get('accepted_latitude'),'longitude':pt.get('accepted_longitude'),'historical_coordinates_observed':False,'retrospective_current_point_inference':True,'do_not_override_primary':True,'whole_item_qualifiers_verification':'cached_full_GUID_no_explicit_subset' if s else 'UNKNOWN_flat_cache_not_preserved','quantity_unit_verification':'cached_full_GUID_unit1' if s else 'UNKNOWN_flat_cache_not_preserved','date_precision':json.dumps([x.get('precision') for x in dates]) if s else 'UNKNOWN_flat_cache_not_preserved','full_API_statement_json':json.dumps(s,ensure_ascii=False) if s else None,'full_API_response_file':path,'full_API_response_sha256':digest,'full_API_P585_values_json':json.dumps(dates) if s else None,'full_API_qualifiers_json':json.dumps(qual,ensure_ascii=False) if s else None,'full_API_quantity_json':json.dumps(v) if s else None,'full_API_rank':s.get('rank') if s else None,'full_API_P31_claims_json':json.dumps(e.get('claims',{}).get('P31',[])) if e else None,'full_API_P625_claims_json':json.dumps(e.get('claims',{}).get('P625',[])) if e else None,'selected1989_source_tier':sel.get('source_tier'),'selected1989_population':sel.get('population'),'source_proofs':[locator]}
 rows.append(row);seen[key]=row
vals=collections.defaultdict(set)
for r in rows:vals[r['root']].add(r['population_value'])
for r in rows:r['same_root_year_value_conflict']=len(vals[r['root']])>1;r['source_proofs_json']=json.dumps(r.pop('source_proofs'),ensure_ascii=False)
assert all(r['year']==1979 and r['current_region'] not in ['крым','севастополь'] for r in rows)
assert len(seen)==len(rows)
t=pa.Table.from_pylist(rows)
for dest in [H,O]:
 pq.write_table(t,dest/'secondary_population_1979_long.parquet',compression='zstd')
 (dest/'holds.json').write_text(json.dumps(holds,ensure_ascii=False,indent=2))
 (dest/'unbound_inventory.json').write_text(json.dumps(unknown,ensure_ascii=False))
receipt={'inputs':inputs,'raw_literal1979_rows':len(raw),'bound_GUID_observations':len(rows),'roots':len(vals),'literal_sum_min':sum(min(v) for v in vals.values()),'literal_sum_max':sum(max(v) for v in vals.values()),'full_GUID_enriched':sum(r['full_API_statement_json'] is not None for r in rows),'unknown_qualifiers_unit_rows':sum(r['full_API_statement_json'] is None for r in rows),'held_rows':len(holds),'unbound_rows':len(unknown),'conflicting_roots':sum(len(v)>1 for v in vals.values()),'API_requests':0,'status':'PASS_secondary_not_verified_primary','cache_manifest':manifest,'outputs':{str(H/'secondary_population_1979_long.parquet'):sha(H/'secondary_population_1979_long.parquet')}}
for dest in [H,O]:(dest/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in receipt.items() if k not in ['inputs','cache_manifest','outputs']},ensure_ascii=False))
