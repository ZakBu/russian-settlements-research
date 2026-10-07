"""Bounded own historical point reserve; never admits points or identity edges."""
import sys,json,re,struct
from pathlib import Path
from collections import defaultdict,Counter
import pandas as pd
import duckdb
ROOT=Path('/workspace/russian-settlements-research')
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).parent
WORK=Path('/workspace/settlements-work/direct_old_geokladr_point_reserve_20261007')
RAW=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet')
CLASS=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet')
PARSED=Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet')
GEO=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
TYPE={'деревня':'деревня','село':'село','поселок сельского типа':'поселок','хутор':'хутор','поселок городского типа':'пгт','город':'город','станица':'станица','станция':'станция','разъезд':'разъезд','слобода':'слобода'}
s=load(14);before=s.metrics()
assert [before[str(y)]['covered_population'] for y in (2002,2010,2021)]==[126150476,123382596,123960048]
c=duckdb.connect(config={'threads':1,'memory_limit':'650MB'})
h=c.execute('SELECT * FROM read_parquet(?)',[str(RAW)]).fetchdf()
cl=c.execute('SELECT historical_okato,name,status,is_settlement_raw FROM read_parquet(?)',[str(CLASS)]).fetchdf()
counties={r.historical_okato[:5]:county_key(r.name) for r in cl.itertuples() if r.is_settlement_raw=='f' and len(r.historical_okato)==8 and r.historical_okato.endswith('000') and 'район' in normalize(r.name) and r.historical_okato[2]=='2'}
h['county']=h.historical_okato_2009_raw.map(lambda v:counties.get(str(v)[:5],''))
region_by_prefix={k:normalize(v.historical_point_modern_region.mode().iloc[0]) for k,v in h.dropna(subset=['historical_point_modern_region']).groupby(h.historical_okato_2009_raw.str[:2])}
classidx=defaultdict(set)
for r in cl[cl.is_settlement_raw.eq('t')].itertuples():
 classidx[(normalize(r.name),TYPE.get(r.status,''),region_by_prefix.get(r.historical_okato[:2],''),counties.get(r.historical_okato[:5],''))].add(r.historical_okato)
rawocc={tuple(x[:2]):x[2] for x in c.execute('SELECT latitude_from_lat,longitude_from_long,count(DISTINCT historical_okato) FROM read_parquet(?) WHERE NOT is_deleted AND latitude_from_lat BETWEEN 41 AND 82 AND longitude_from_long BETWEEN 19 AND 180 GROUP BY ALL',[str(PARSED)]).fetchall()}
rawidx=defaultdict(list)
valid=h[h.historical_name_exact.fillna(False)&h.historical_type_exact.fillna(False)&h.historical_code_structure_compatible.fillna(False)&~h.is_deleted.fillna(True)&h.latitude_from_lat.between(41,82)&h.longitude_from_long.between(19,180)]
for r in valid.to_dict('records'):rawidx[(normalize(r['name_key']),normalize(r['type_key_2009']),normalize(r['historical_point_modern_region']))].append(r)
obs=s.obs[s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь','крым'])].copy()
obs['n']=obs.name_norm.map(normalize);obs['t']=obs.type_norm.map(normalize);obs['r']=obs.region_norm.map(normalize);obs['county']=obs.district_raw.map(county_key)
obsidx=defaultdict(list);current=defaultdict(list);occupied=defaultdict(set);components=defaultdict(list)
for a in obs.to_dict('records'):
 obsidx[(int(a['census_year']),a['n'],a['t'],a['r'])].append(a)
 if a['census_year']==2021:current[(a['n'],a['t'],a['r'])].append(a)
 components[s.uf.find(a['source_record_id'])].append(a['source_record_id'])
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
old=obs[obs.census_year.lt(2021)&~obs.source_record_id.isin(s.point_rows)]
counts=Counter();candidates=[];holds=[]
def codeval(v):
 if v is None or pd.isna(v):return ''
 v=str(v).strip();return v[:-2] if v.endswith('.0') else v
for a in old.to_dict('records'):
 sid=a['source_record_id'];key=(a['n'],a['t'],a['r']);code=codeval(a['okato']);eligible=[];reasons=set()
 for g in rawidx.get(key,[]):
  rr=[];gcode=g['historical_okato_2009_raw'];lat,lon=g['latitude_from_lat'],g['longitude_from_long']
  binding=bool(code and (code==gcode or code==g['historical_okato_2011_raw']))
  if code and not binding:rr.append('printed_native_code_conflict')
  if not binding and (not a['county'] or not g['county'] or a['county']!=g['county']):rr.append('missing_or_conflicting_explicit_county')
  if a['county'] and g['county'] and a['county']!=g['county']:rr.append('historical_county_conflict')
  if a['t'] in ['станция','разъезд'] or any(x in a['n'] for x in ['железнодорож','ж/д']):rr.append('railway_feature_requires_case_review')
  alternatives=classidx.get((*key,g['county']),set())-{gcode}
  if alternatives:rr.append('unlocated_or_other_classifier_competitor')
  if any(q['source_record_id']!=sid and (not q['county'] or not a['county'] or q['county']==a['county']) for q in obsidx[(int(a['census_year']),*key)]):rr.append('selected_same_year_homonym_not_separated')
  if rawocc.get((lat,lon),0)!=1:rr.append('raw_coordinate_shared_distinct_codes')
  if occupied.get((int(a['census_year']),lat,lon),set())-{sid}:rr.append('accepted_same_year_coordinate_collision')
  if pd.notna(a['latitude']) and pd.notna(a['longitude']) and distance_km((lat,lon),(a['latitude'],a['longitude']))>5:rr.append('source_point_conflict_over_5km')
  for peer in components[s.uf.find(sid)]:
   if peer in s.point_rows and distance_km((lat,lon),(s.point_rows[peer]['latitude'],s.point_rows[peer]['longitude']))>5:rr.append('accepted_component_point_conflict_over_5km')
  if rr:reasons.update(rr);continue
  eligible.append((g,binding))
 if len(eligible)!=1:
  reasons.add('no_eligible_own_object' if not eligible else 'multiple_eligible_own_objects');counts.update(reasons)
  if len(holds)<300 or a['population']>1000:holds.append({'source_record_id':sid,'census_year':a['census_year'],'name':a['settlement_name'],'population':a['population'],'region':a['r'],'county':a['county'],'own_code':code,'raw_name_type_region_matches':len(rawidx.get(key,[])),'hold_reasons':';'.join(sorted(reasons))})
  continue
 g,binding=eligible[0];lat,lon=g['latitude_from_lat'],g['longitude_from_long']
 corroborators=[b for b in current.get(key,[]) if b['county']==a['county'] and a['county'] and b['source_record_id'] in s.point_rows]
 corr=[(b,distance_km((lat,lon),(s.point_rows[b['source_record_id']]['latitude'],s.point_rows[b['source_record_id']]['longitude']))) for b in corroborators]
 candidates.append({'source_record_id':sid,'census_year':int(a['census_year']),'settlement_name':a['settlement_name'],'settlement_type':a['settlement_type'],'region_norm':a['r'],'district_raw':a['district_raw'],'county_key':a['county'],'population':a['population'],'printed_native_okato':code,'native_code_binding_asserted':binding,'binding_rule':'exact_printed_native_code_name_type_region' if binding else 'exact_own_label_type_region_explicit_county_unique_object','historical_okato_2009_raw':g['historical_okato_2009_raw'],'historical_okato_2011_raw':g['historical_okato_2011_raw'],'raw_county_key':g['county'],'name_raw_2009':g['name_raw_2009'],'name_raw_2011':g['name_raw_2011'],'raw_type_2009':g['status'],'raw_type_2011':g['settlement_type_raw'],'latitude':lat,'longitude':lon,'point_origin_file':str(GEO),'point_origin_sha256':g['source_sha256_2011'],'point_origin_locator':f"DBF_record_1based={g['record_number_1based']};byte_offset_0based={g['record_byte_offset_0based']};OKATO2011_raw={g['historical_okato_2011_raw']}",'classifier_origin_sha256':g['source_sha256_2009'],'classifier_locator':f"line_1based={g['source_line_1based']};OKATO2009_raw={g['historical_okato_2009_raw']}",'census_source_file':a['source_file'],'census_source_sha256':a['source_sha256'],'census_source_locator':a['source_locator'] or sid,'existing_component_years':'|'.join(map(str,sorted(s.years[s.uf.find(sid)]))),'existing_complete_identity':s.years[s.uf.find(sid)]=={2002,2010,2021},'optional_current_corroborators':len(corr),'optional_current_nearest_km':min([d for b,d in corr],default=None),'optional_current_point_origin':s.point_rows[corr[0][0]['source_record_id']].get('point_origin_file','') if len(corr)==1 else '', 'decision_status':'candidate_only_requires_independent_review','coordinate_admission_status':'candidate_only_requires_independent_review','direct_census_date_coordinate':False,'inference':'retrospective_representative_own_named_object_point','population_or_boundary_comparability_asserted':False})
f=pd.DataFrame(candidates)
if len(f):
 dup=f.duplicated(['census_year','historical_okato_2011_raw'],keep=False)
 counts['multiple_selected_rows_same_raw_object']=int(dup.sum());f=f[~dup].copy().sort_values(['population','source_record_id'],ascending=[False,True])
 # Optional current corroboration reveals point disagreements but never provides an existence gate.
 conflicts=f.optional_current_nearest_km.gt(5);f[conflicts].to_csv(WORK/'optional_current_point_conflicts.csv',index=False)
 counts['optional_current_point_conflict_over_5km']=int(conflicts.sum());f=f[~conflicts].copy()
 files={str(p):sha(p) for value in f.census_source_file.unique() if (p:=Path(value) if Path(value).is_file() else Path('/workspace/settlements-raw')/value).is_file()}
 f['census_source_sha256_actual']=f.census_source_file.map(lambda v:files.get(str(Path(v) if Path(v).is_file() else Path('/workspace/settlements-raw')/v),''))
 f.to_csv(WORK/'candidate_point_uses.csv',index=False)
 sample=pd.concat([f.head(15),f.sample(min(25,len(f)),random_state=20261007)]).drop_duplicates('source_record_id');sample.to_csv(OUT/'fixed_plus_largest_sample.csv',index=False)
else:files={};sample=pd.DataFrame()
pd.DataFrame(holds).sort_values('population',ascending=False).to_csv(OUT/'bounded_holds.csv',index=False)
def yearstats(frame):return {str(int(y)):{'rows':len(d),'population':int(d.population.sum())} for y,d in frame.groupby('census_year')}
coordbase=obs[obs.source_record_id.isin(s.point_rows)]
after=s.metrics(extra_point_ids=list(f.source_record_id) if len(f) else [])
receipt={'status':'candidate_only_not_admitted','stage':14,'joint_baseline':before,'coordinate_axis_baseline':yearstats(coordbase),'old_unpointed_rows':len(old),'raw_own_objects_screened':len(h),'valid_exact_typed_own_objects':len(valid),'candidate_rows':len(f),'coordinate_axis_candidate_lift':yearstats(f) if len(f) else {},'joint_point_only_simulation':after,'joint_gain_without_new_links':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'candidate_rows_already_complete_identity':int(f.existing_complete_identity.sum()) if len(f) else 0,'candidate_missing_year_link_reserve':yearstats(f[~f.existing_complete_identity]) if len(f) else {},'new_identity_links_asserted':0,'native_code_bound_candidates':int(f.native_code_binding_asserted.sum()) if len(f) else 0,'optional_current_corroborated_candidates':int(f.optional_current_nearest_km.le(5).sum()) if len(f) else 0,'candidate_current_corroboration_absent':int(f.optional_current_nearest_km.isna().sum()) if len(f) else 0,'screen_counts':dict(counts),'inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [RAW,CLASS,PARSED,GEO,*s.inputs]},'selected_source_asset_hashes':files,'generator_sha256':sha(Path(__file__)),'limitations':['No admission and no identity link asserted. Coordinate-axis reserve is separate from joint coverage.','GeoKLADR point dated snapshot 2011 is a representative retrospective inference, not a census-date measurement.','No current census row or current accepted point is required. Missing optional corroboration needs independent point review.','Exact county mapping is limited to 2009 district-coded objects. City and missing county pools remain held absent own printed native code.','Known railway ambiguity, exact raw shared coordinates, same-year occupancy, classifier homonyms and accepted point contradictions held.','Population and boundary comparability not inferred. Provider QC is not treated as accuracy.']}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
(OUT/'README.md').write_text('# Direct old ownpoint reserve — candidate only\n\nUnpointed physical additive 2002/2010 observations independently bind to their own exact literal name, type, region and explicit historical county. A printed own OKATO code, where present, must agree. Raw 2009 classifier and 2011 typed GeoKLADR named objects, including unlocated classifier competitors, are screened without requiring a current observation anchor. Full raw distinct-code point collisions and all accepted same-year occupancy are held. Optional current corroboration is recorded, contradictions held. No identity edges or admissions are produced.\n\nCoordinate reserve, already-complete identity gain and unresolved missing-year linkage reserve are reported separately in the receipt. Larger candidate CSV stays outside Git.\n')
print(json.dumps({k:receipt[k] for k in ['candidate_rows','coordinate_axis_candidate_lift','joint_gain_without_new_links','candidate_missing_year_link_reserve','native_code_bound_candidates','optional_current_corroborated_candidates','candidate_current_corroboration_absent','screen_counts']},ensure_ascii=False))
