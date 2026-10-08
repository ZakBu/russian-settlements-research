from pathlib import Path
import sys,json,re,collections
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');E=R/'research_rebuild/evidence';O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha
from apply_unique_county_name_bridge_20261007 import county_key
f=pd.read_csv(O/'positive_bound_census2010_candidates.csv.gz',dtype={'current_okato':str,'current_oktmo':str},keep_default_na=False);selected='/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet';c=duckdb.connect(config={'threads':1,'memory_limit':'200MB'});native=c.execute('select source_record_id,settlement_name,settlement_type,type_norm,region_norm,district_raw,population,population_value_quality,okato,oktmo,source_file,source_locator,source_name_raw,source_sheet,source_row,is_additive_settlement_record from read_parquet(?)where census_year=2010',[selected]).fetchdf();context={};contextproof={};pins={selected:sha(Path(selected))}
for p in [Path('/workspace/settlements-work/secondary_2010_county_context_batch_20261007/all_selected_competitor_county_context.csv.gz'),Path('/workspace/settlements-work/cached_wikipedia_history_mass_20261008/refreshed_2010_context/all_selected_competitor_county_context.csv.gz')]:
 if p.exists():
  pins[str(p)]=sha(p)
  for a in pd.read_csv(p,dtype=str,keep_default_na=False).to_dict('records'):
   if a.get('inferred_county_key'):context[a['source_record_id']]=a['inferred_county_key'];contextproof[a['source_record_id']]=a
p=E/'native_missing2010_all_components_20261008/refined_all_competitor_witness.csv.gz'
if p.exists():
 pins[str(p)]=sha(p)
 for a in pd.read_csv(p,keep_default_na=False).to_dict('records'):
  if a.get('native2010_resolved_county'):context[a['target2010_source_record_id']]=a['native2010_resolved_county'];contextproof[a['target2010_source_record_id']]=json.loads(a['source_county_proof_json'])
def typed(v):return re.sub(r'^(?:поселок|село|деревня|хутор|город)\s+','',normalize(v))
def code(v):return '' if pd.isna(v) else str(v).removesuffix('.0')
native['n']=native.settlement_name.map(typed);ix=collections.defaultdict(list);nativecodes=collections.defaultdict(list)
for a in native.to_dict('records'):
 if not a['is_additive_settlement_record']:continue
 ix[(a['region_norm'],a['n'])].append(a)
 for key in [code(a['okato']),code(a['oktmo'])]:
  if key:nativecodes[key].append(a)
rows=[];allopts=[]
for sid,g in f.groupby('current_source_record_id'):
 popset=set(g.population2010);qset=set(g.qid)
 if len(popset)!=1 or len(qset)!=1:continue
 a=g.iloc[0].to_dict();names={typed(v) for v in json.loads(a['own_aliases_json'])}|{typed(a['native2002_name']),typed(a['name'])};candidates={x['source_record_id']:x for n in names for x in ix.get((a['region'],n),[])}
 for key in [a['current_okato'],a['current_oktmo']]:
  for x in nativecodes.get(key,[]):
   if x['region_norm']==a['region']:candidates[x['source_record_id']]=x
 for x in candidates.values():
  dc=county_key(x['district_raw']) or context.get(x['source_record_id'],'');parents={county_key(a['current_county']),county_key(a['native2002_county'])}-{''};countypositive=bool(dc and dc in parents);owncode=bool({code(x['okato']),code(x['oktmo'])}-{''}) and bool(({code(x['okato']),code(x['oktmo'])}-{''})&({a['current_okato'],a['current_oktmo']}-{''}));namepositive=x['n']in names;typepositive=normalize(x['type_norm'])==normalize(a['current_type']);rivals=[y['source_record_id'] for y in candidates.values() if y['source_record_id']!=x['source_record_id'] and normalize(y['type_norm'])==normalize(x['type_norm']) and (not dc or not(county_key(y['district_raw']) or context.get(y['source_record_id'],''))or(county_key(y['district_raw']) or context.get(y['source_record_id'],''))==dc)];positive=namepositive and typepositive and(countypositive or owncode)and not rivals
  row={'current_source_record_id':sid,'native2002_source_record_id':a['native2002_source_record_id'],'qid':a['qid'],'current_name':a['name'],'native2010_source_record_id':x['source_record_id'],'native2010_name':x['settlement_name'],'native2010_type':x['settlement_type'],'native2010_population':x['population'],'native2010_quality':x['population_value_quality'],'secondary_literal2010_population':a['population2010'],'population_equal_is_candidate_feature_only':x['population']==a['population2010'],'native2010_own_alias_or_label_positive':namepositive,'native2010_current_physical_type_positive':typepositive,'native2010_printed_or_frozen_county':dc,'native2010_source_county_positive':countypositive,'native2010_own_code_positive':owncode,'same_type_same_or_unresolved_county_rivals_json':json.dumps(rivals),'all_native_name_code_options':len(candidates),'source_positive_candidate':positive,'native2010_source_file':x['source_file'],'native2010_source_locator':x['source_locator'],'native2010_source_name_raw':x['source_name_raw'],'native2010_source_sheet':x['source_sheet'],'native2010_source_row':x['source_row'],'county_witness_json':json.dumps(contextproof.get(x['source_record_id'],{'rule':'selected_printed_native_county','raw_county':str(x['district_raw'])}),ensure_ascii=False),'wikidata_source_file':a['raw_entity_path'],'wikidata_source_sha256':a['raw_entity_sha256']};allopts.append(row)
  if positive:rows.append(row)
pd.DataFrame(rows).to_csv(O/'source_positive_native2010_alias_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(allopts).to_csv(O/'all_native2010_alias_code_competitors.csv.gz',index=False,compression={'method':'gzip','mtime':0});rec={'cached_positive_cohort':f.current_source_record_id.nunique(),'native_source_options':len(allopts),'source_positive_native_candidates':len(rows),'source_positive_native2010_population':int(sum(x['native2010_population'] for x in rows)),'count_equality_not_an_admission_gate':True,'source_county_and_all_native_name_type_competitors_checked_before_graph':True,'input_pins':pins,'output_pins':{p.name:sha(p) for p in [O/'source_positive_native2010_alias_candidates.csv.gz',O/'all_native2010_alias_code_competitors.csv.gz']}};(O/'native_route_inventory_receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in rec.items() if k not in ['input_pins','output_pins']},ensure_ascii=False));print(pd.DataFrame(rows)[['current_name','native2010_name','native2010_population','native2010_printed_or_frozen_county']].head(30).to_string(index=False) if rows else 'none')
