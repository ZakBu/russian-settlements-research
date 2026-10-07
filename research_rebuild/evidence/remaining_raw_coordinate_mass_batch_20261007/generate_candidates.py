"""Candidate-only raw named historical point corridor; no accepted files edited."""
import sys,json,re
from pathlib import Path
from collections import defaultdict,Counter
import pandas as pd
import duckdb
ROOT=Path('/workspace/russian-settlements-research')
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=ROOT/'research_rebuild/evidence/remaining_raw_coordinate_mass_batch_20261007'
WORK=Path('/workspace/settlements-work/remaining_raw_coordinate_mass_batch_20261007')
RAW=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet')
CLASS=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet')
PROVIDER=Path('/workspace/settlements-work/coordinates/ledger/coordinate_screen.parquet')
GEO=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
s=load(stage=13);before=s.metrics()
assert [before[str(y)]['covered_population'] for y in (2002,2010,2021)]==[125948693,123187272,123734052]
c=duckdb.connect(config={'threads':1,'memory_limit':'600MB'})
h=c.execute('SELECT name_key,type_key_2009,historical_point_modern_region,historical_okato_2009_raw,historical_okato_2011_raw,name_raw_2009,name_raw_2011,status,latitude_from_lat,longitude_from_long,record_number_1based,record_byte_offset_0based,source_sha256_2011,source_sha256_2009,source_line_1based FROM read_parquet(?) WHERE historical_name_exact AND historical_type_exact AND NOT is_deleted AND latitude_from_lat BETWEEN 41 AND 82 AND longitude_from_long BETWEEN 19 AND 180',[str(RAW)]).fetchdf()
cl=c.execute('SELECT historical_okato,name FROM read_parquet(?) WHERE is_settlement_raw=\'f\' AND length(historical_okato)=8 AND ends_with(historical_okato,\'000\')',[str(CLASS)]).fetchall()
counties={code[:5]:county_key(name) for code,name in cl if 'район' in normalize(name) and code[2]=='2'}
h['county']=h.historical_okato_2009_raw.map(lambda x:counties.get(str(x)[:5],''))
rawocc=Counter((r.latitude_from_lat,r.longitude_from_long) for r in h.itertuples())
idx=defaultdict(list)
for r in h.to_dict('records'):idx[(normalize(r['name_key']),normalize(r['type_key_2009']),normalize(r['historical_point_modern_region']))].append(r)
obs=s.obs[s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь','крым'])].copy()
obs['n']=obs.name_norm.map(normalize);obs['t']=obs.type_norm.map(normalize);obs['r']=obs.region_norm.map(normalize);obs['county']=obs.district_raw.map(county_key)
cur=defaultdict(list)
for r in obs[obs.census_year.eq(2021)&obs.source_record_id.isin(s.point_rows)].to_dict('records'):
 if r['source_record_id'] not in s.conflicting_point_targets:cur[(r['n'],r['t'],r['r'])].append(r)
occupied=defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
old=obs[(obs.census_year<2021)&~obs.source_record_id.isin(s.point_rows)]
all_old=defaultdict(list)
for r in obs[obs.census_year.lt(2021)].to_dict('records'):all_old[(int(r['census_year']),r['n'],r['t'],r['r'])].append(r)
counts=Counter();candidates=[];holds=[];rejects=defaultdict(dict)
for a in old.to_dict('records'):
 sid=a['source_record_id'];key=(a['n'],a['t'],a['r']);near=[]
 for b in cur.get(key,[]):
  bsid=b['source_record_id'];p=s.point_rows[bsid]
  for g in idx.get(key,[]):
   dist=distance_km((g['latitude_from_lat'],g['longitude_from_long']),(p['latitude'],p['longitude']))
   if dist>5:continue
   reasons=[]
   alternatives=[q for q in all_old[(int(a['census_year']),*key)] if q['source_record_id']!=sid and (not q['county'] or q['county']==g['county'])]
   if alternatives:reasons.append('selected_historical_homonym_without_distinct_explicit_county')
   if a['county'] and b['county'] and a['county']!=b['county']:reasons.append('explicit_historical_current_county_conflict')
   if not g['county'] or not b['county'] or g['county']!=b['county'] or (a['county'] and g['county']!=a['county']):reasons.append('raw_classifier_current_or_explicit_historical_county_missing_or_conflict')
   if rawocc[(g['latitude_from_lat'],g['longitude_from_long'])]>1:reasons.append('raw_point_shared_by_multiple_named_codes')
   if occupied.get((int(a['census_year']),g['latitude_from_lat'],g['longitude_from_long']),set())-{sid}:reasons.append('raw_point_occupied_by_other_accepted_same_year_observation')
   if s.uf.find(sid)!=s.uf.find(bsid) and s.years[s.uf.find(sid)]&s.years[s.uf.find(bsid)]:reasons.append('repeated_year_component_conflict')
   counts.update(reasons)
   for reason in reasons:
    rejects[reason][sid]={'source_record_id':sid,'census_year':int(a['census_year']),'settlement_name':a['settlement_name'],'population':a['population'],'current_population':b['population'],'current_source_record_id':bsid,'region_norm':a['r'],'historical_county':a['county'],'current_county':b['county'],'raw_county':g['county'],'raw_code':g['historical_okato_2011_raw'],'distance_km':dist,'existing_component_years':'|'.join(map(str,sorted(s.years[s.uf.find(sid)]))),'current_component_years':'|'.join(map(str,sorted(s.years[s.uf.find(bsid)])))}
   if reasons:
    if len(holds)<200:holds.append({'source_record_id':sid,'current_source_record_id':bsid,'name':a['settlement_name'],'region':a['r'],'historical_county':a['county'],'current_county':b['county'],'raw_county':g['county'],'historical_code':g['historical_okato_2011_raw'],'distance_km':dist,'reasons':';'.join(reasons)})
    continue
   near.append((b,g,dist))
 if len(near)!=1:
  counts['no_eligible_pair' if not near else 'multiple_eligible_raw_current_pairs']+=1;continue
 b,g,dist=near[0]
 # Cross-year observation must be the only still-unpointed old row resolving to this raw object/current/year.
 candidates.append({'source_record_id':sid,'census_year':int(a['census_year']),'settlement_name':a['settlement_name'],'settlement_type':a['settlement_type'],'region_norm':a['r'],'population':a['population'],'district_raw':a['district_raw'],'county_key':a['county'],'current_source_record_id':b['source_record_id'],'current_population':b['population'],'current_district_raw':b['district_raw'],'historical_okato_2009_raw':g['historical_okato_2009_raw'],'historical_okato_2011_raw':g['historical_okato_2011_raw'],'raw_county_key':g['county'],'name_raw_2009':g['name_raw_2009'],'name_raw_2011':g['name_raw_2011'],'latitude':g['latitude_from_lat'],'longitude':g['longitude_from_long'],'current_latitude':s.point_rows[b['source_record_id']]['latitude'],'current_longitude':s.point_rows[b['source_record_id']]['longitude'],'distance_km':dist,'point_origin_file':str(GEO),'point_origin_sha256':g['source_sha256_2011'],'point_origin_locator':f"DBF_record_1based={g['record_number_1based']};byte_offset_0based={g['record_byte_offset_0based']};OKATO2011_raw={g['historical_okato_2011_raw']}",'classifier_source_sha256':g['source_sha256_2009'],'classifier_locator':f"line_1based={g['source_line_1based']};OKATO2009_raw={g['historical_okato_2009_raw']}",'census_source_file':a['source_file'],'census_source_sha256':a['source_sha256'],'census_source_locator':a['source_locator'],'current_point_ledger':s.point_rows[b['source_record_id']]['point_ledger_path'],'current_point_origin_file':s.point_rows[b['source_record_id']].get('point_origin_file',''),'current_point_origin_sha256':s.point_rows[b['source_record_id']].get('point_origin_sha256',''),'current_point_origin_locator':s.point_rows[b['source_record_id']].get('point_origin_locator',''),'decision_status':'candidate_only_requires_independent_review','native_census_code_binding_asserted':False,'direct_census_date_point':False})
f=pd.DataFrame(candidates)
if len(f):
 dup=f.duplicated(['census_year','current_source_record_id'],keep=False)|f.duplicated(['census_year','historical_okato_2011_raw'],keep=False)
 counts['ambiguous_old_observations']=int(dup.sum());f=f[~dup].copy()
 f=f.sort_values(['population','source_record_id'],ascending=[False,True])
 f['population_ratio_max_over_min']=[max(a,b)/min(a,b) if pd.notna(a) and pd.notna(b) and min(a,b)>0 else None for a,b in zip(f.population,f.current_population)]
 f['population_scope_review_required']=f.population_ratio_max_over_min.gt(2)|(f.population.gt(0)&f.current_population.eq(0))|(f.population.eq(0)&f.current_population.gt(0))
 f['population_boundary_comparability_asserted']=False
 f['source_population_values_modified']=False
 f.to_csv(WORK/'preliminary_candidates_including_anchor_holds.csv',index=False)
 provider=c.execute('SELECT source_record_id AS current_source_record_id,provider_name_exact_selected_name,provider_type_exact_selected_type,provider_fias_level,provider_general_fias_id,provider_general_and_settlement_fias_ids_same,provider_general_fias_duplicate_count,provider_coordinate_duplicate_count,provider_latitude,provider_longitude,raw_okato_dadata,raw_oktmo_dadata FROM read_parquet(?) WHERE source_record_id IN (SELECT UNNEST(?))',[str(PROVIDER),list(f.current_source_record_id)]).fetchdf()
 f=f.merge(provider,on='current_source_record_id',validate='many_to_one')
 eligible=f.provider_name_exact_selected_name.fillna(False)&f.provider_type_exact_selected_type.fillna(False)&f.provider_fias_level.isin(['4','6'])&f.provider_general_and_settlement_fias_ids_same.fillna(False)&f.provider_general_fias_duplicate_count.eq(1)&f.provider_coordinate_duplicate_count.eq(1)
 f['current_own_provider_point_to_accepted_anchor_km']=[distance_km((a,b),(x,y)) if pd.notna(a) and pd.notna(b) else None for a,b,x,y in zip(f.provider_latitude,f.provider_longitude,f.current_latitude,f.current_longitude)]
 eligible &= f.current_own_provider_point_to_accepted_anchor_km.le(.5)
 counts['current_provider_binding_audit_flags']=int((~eligible).sum())
 f[~eligible].to_csv(WORK/'current_provider_binding_audit_flags.csv',index=False)
 # Trusted accepted anchor remains authoritative; current-provider duplication/mismatch is an audit flag, not a new baseline gate.
 f['current_provider_binding_clean']=eligible
 independent=~f.current_point_origin_file.fillna('').str.contains('geokladr_okato_2011',regex=False)
 counts['current_anchor_same_raw_geokladr_lineage_flags']=int((~independent).sum())
 f['shared_raw_geokladr_lineage_with_current_anchor']=~independent
 f[~independent].to_csv(WORK/'same_raw_lineage_anchor_flags.csv',index=False)
 f.to_csv(WORK/'candidates.csv',index=False)
 pointuses=f.rename(columns={'source_record_id':'target_source_record_id','census_year':'target_year'}).copy();pointuses['coordinate_admission_status']='candidate_only_requires_independent_review';pointuses.to_csv(WORK/'candidate_point_uses.csv',index=False)
 edges=[];pointids=[]
 for a in f.to_dict('records'):
  sid,bid=a['source_record_id'],a['current_source_record_id']
  if s.uf.find(sid)!=s.uf.find(bid):
   if s.years[s.uf.find(sid)]&s.years[s.uf.find(bid)]:raise ValueError('Candidate union created a repeated year')
   s.union(sid,bid);edges.append({'from_source_record_id':sid,'to_source_record_id':bid,'relation':'same_place','decision_status':'candidate_only_requires_independent_review'})
  pointids.append(sid)
 pd.DataFrame(edges,columns=['from_source_record_id','to_source_record_id','relation','decision_status']).to_csv(WORK/'candidate_identity_edges.csv',index=False)
 sample=pd.concat([f.head(15),f.sample(min(30,len(f)),random_state=20261007)]).drop_duplicates('source_record_id');sample.to_csv(OUT/'fixed_plus_largest_sample.csv',index=False)
else:
 pd.DataFrame(columns=['source_record_id','census_year','decision_status']).to_csv(WORK/'candidates.csv',index=False);pointids=[];edges=[]
pd.DataFrame(holds).to_csv(OUT/'bounded_hold_sample.csv',index=False)
rejection_mass={};topreject=[]
for reason,rows in rejects.items():
 d=pd.DataFrame(rows.values());rejection_mass[reason]={'unique_observations':len(d),'historical_population_by_year':{str(int(y)):int(v.population.sum()) for y,v in d.groupby('census_year')}}
 d=d.sort_values('population',ascending=False).head(10);d['reason']=reason;topreject.extend(d.to_dict('records'))
pd.DataFrame(topreject).to_csv(OUT/'largest_rejections_by_rule.csv',index=False)
after=s.metrics(extra_point_ids=pointids)
receipt={'status':'candidate_only_not_admitted','stage':13,'baseline':before,'simulation':after,'marginal_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'marginal_covered_rows':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'candidate_raw_point_rows':len(f),'candidate_new_edges':len(edges),'screen_counts':dict(counts),'rejected_unique_observation_mass_by_rule_overlapping':rejection_mass,'generator_sha256':sha(Path(__file__)),'candidate_population_scope_flags':int(f.population_scope_review_required.sum()) if len(f) else 0,'candidate_unique_current_anchors':int(f.current_source_record_id.nunique()) if len(f) else 0,'old_rows_without_accepted_point':len(old),'raw_objects_screened':len(h),'input_hashes':{str(p):sha(p) for p in [RAW,CLASS,GEO,PROVIDER,*s.inputs]},'outputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in list(WORK.glob('*.csv'))+list(OUT.glob('*.csv'))},'limitations':['No accepted status or source population changed. Population ratio >2 or one census being zero is explicitly scope-flagged; simulation does not imply admissible whole-place continuity.','Raw GeoKLADR 2011 point used retrospectively; no census-date measurement or direct census code join asserted.','County keys remove explicit administrative designators; historical raw object county must agree with both source counties.','Raw point name/type exactness comes from literal raw 2009 classifier object and raw 2011 GeoKLADR object, not inherited provider pointers.','Current provider duplication or mismatch retained as audit flags; trusted accepted anchor is authoritative. Current anchor sourced from the same GeoKLADR raw lineage is flagged as non-independent, not held. Candidate review must inspect point origin and current ownpoint origin; raw regional homonyms resolved only with explicit county and independently accepted current anchor.','Bounded hold sample is diagnostic only; hold reason counts may count the same pair more than once.','Union simulation permits no repeated census year and only adds actual existing observations.']}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
(OUT/'README.md').write_text('# Raw named historical point corridor (candidate only)\n\nNew pool: all historical named objects, including regional homonyms omitted by the previous unique region/name/type historical-candidate join. Raw own named/type/code objects require raw classifier and explicit current county agreement (historical county must also agree where present), all-selected historical homonym exclusion unless distinct explicit counties separate them, unique raw/current pairing, <=5 km to an accepted current point, and no raw or accepted same-year point collision. Candidate CSV and candidate edges live outside Git. No accepted input modified.\n\nReview receipt and fixed-plus-largest sample before any admission. Trusted accepted current anchors stay authoritative; duplicate or mismatched current provider tuples and shared raw lineage are audit flags, not extra baseline gates. Point use is retrospective continuity; native census identifier binding and population/boundary comparability are not asserted.\n')
print(json.dumps({k:receipt[k] for k in ['candidate_raw_point_rows','candidate_new_edges','marginal_population_gain','marginal_covered_rows','screen_counts']},ensure_ascii=False))
