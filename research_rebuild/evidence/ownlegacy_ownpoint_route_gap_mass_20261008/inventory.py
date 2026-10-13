import sys,json,re,math
from pathlib import Path
from collections import defaultdict,Counter
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(39);before=s.metrics();c=duckdb.connect();H=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet');C=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');P=Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet');h=c.execute('select * from read_parquet(?)',[str(H)]).fetchdf();cl=c.execute('select historical_okato,name,status,is_settlement_raw from read_parquet(?)',[str(C)]).fetchdf();counties={r.historical_okato[:5]:county_key(r.name) for r in cl.itertuples() if r.is_settlement_raw=='f' and len(r.historical_okato)==8 and r.historical_okato.endswith('000') and 'район' in normalize(r.name) and r.historical_okato[2]=='2'};regions={k:normalize(g.historical_point_modern_region.mode().iloc[0]) for k,g in h.dropna(subset=['historical_point_modern_region']).groupby(h.historical_okato_2009_raw.str[:2])};types={'деревня':'деревня','село':'село','поселок сельского типа':'поселок','хутор':'хутор','поселок городского типа':'пгт','город':'город','станица':'станица','станция':'станция','разъезд':'разъезд','слобода':'слобода'}
def n(v):return ' '.join(re.sub('[^а-яa-z0-9]+',' ',normalize(v)).split())
def code(v):
 if v is None or pd.isna(v):return ''
 x=str(v).strip();return x[:-2] if x.endswith('.0') else x
classidx=defaultdict(list)
for z in cl[cl.is_settlement_raw.eq('t')].to_dict('records'):
 gc=z['historical_okato'];classidx[(n(z['name']),types.get(z['status'],normalize(z['status'])),regions.get(gc[:2],''))].append((gc,counties.get(gc[:5],'')))
valid=h[h.historical_name_exact.fillna(False)&h.historical_type_exact.fillna(False)&h.historical_code_structure_compatible.fillna(False)&~h.is_deleted.fillna(True)&h.latitude_from_lat.between(41,82)&h.longitude_from_long.between(19,180)];hist={str(z['historical_okato_2009_raw']):z for z in valid.to_dict('records')};rawocc={(lat,lon):num for lat,lon,num in c.execute('select latitude_from_lat,longitude_from_long,count(distinct historical_okato) from read_parquet(?) where not is_deleted group by all',[str(P)]).fetchall()};ex=R/'research_rebuild/evidence/direct_old_geokladr_point_reserve_20261007_spatial_review/suggested_raw_point_exclusion_keys.csv';excluded=set(pd.read_csv(ex,dtype=str).raw_own_code)
eventfiles=[R/'research_rebuild/evidence/event_aware_path_union_20261005/accepted_event_path_selected_rows.csv',R/'research_rebuild/evidence/working_full_chain_20261007/named_merger_lineage_observations.csv',R/'research_rebuild/evidence/working_full_chain_20261007/qualified_physical_observations.csv'];eventids=set()
for path in eventfiles:
 if path.exists():
  e=pd.read_csv(path,dtype=str)
  if 'source_record_id' in e:eventids.update(e.source_record_id)
o=s.obs[s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь','крым'])].copy();o=o[~o.region_norm.isin(['чеченская'])];o=o[~o.settlement_name.fillna('').str.contains(r'\(часть|\bитого\b|\bвсего\b',case=False,regex=True)];o['n']=o.settlement_name.map(n);o['t']=o.type_norm.map(normalize);o['r']=o.region_norm.map(normalize);o['d']=o.district_raw.map(county_key);o['code']=o.okato.map(code)
ctx=Path('/workspace/settlements-work/secondary_2010_county_context_batch_20261007/all_selected_competitor_county_context.csv.gz');context=pd.read_csv(ctx,dtype=str,keep_default_na=False).set_index('source_record_id').to_dict('index');o['county_binding']=o.source_record_id.map(lambda sid:context.get(sid,{}).get('inference','printed_source_county'));o.loc[o.d.eq(''),'d']=o.loc[o.d.eq(''),'source_record_id'].map(lambda sid:context.get(sid,{}).get('inferred_county_key',''))
current=defaultdict(list);oldidx=defaultdict(list);members=defaultdict(list);ownrail=set();W=Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet');w=c.execute('select source_record_id,wikidata_qid,wikidata_truthy_p31_claims_json from read_parquet(?)',[str(W)]).fetchdf()
for z in w.to_dict('records'):
 pp=s.point_rows.get(z['source_record_id']);
 if pp and pp.get('coordinate_source_record_id')==z['wikidata_qid'] and any(q['value_qid'] in ['Q24258416','Q27062006','Q27517483'] for q in json.loads(z['wikidata_truthy_p31_claims_json'])):ownrail.add(z['source_record_id'])
def whole(a):return 'объект' not in normalize(a['settlement_type']) or a['source_record_id'] in ownrail
for a in o.to_dict('records'):
 members[s.uf.find(a['source_record_id'])].append(a['source_record_id'])
 if a['census_year']==2021 and a['source_record_id'] in s.point_rows and whole(a):current[(a['n'],a['r'])].append(a)
 if a['census_year'] in [2002,2010]:oldidx[(int(a['census_year']),a['n'],a['t'],a['r'])].append(a)
A=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet');aux=c.execute('select source_record_id,provider_latitude,provider_longitude,provider_fias_level,provider_general_fias_id,provider_coordinate_duplicate_count,provider_name_exact_selected_name,provider_type_exact_selected_type,source_object_is_naselenniy_punkt,source_is_aggregate_scope,record_number_1based from read_parquet(?) where census_year=2021',[str(A)]).fetchdf();raw_current_points={};A_hash=sha(A)
for z in aux.to_dict('records'):
 sid=z['source_record_id']
 if sid in s.point_rows:continue
 if not(z['provider_name_exact_selected_name'] is True and z['provider_type_exact_selected_type'] is True and z['source_object_is_naselenniy_punkt'] is True and z['source_is_aggregate_scope'] is False):continue
 lat,lon=z['provider_latitude'],z['provider_longitude']
 if not(pd.notna(lat) and pd.notna(lon) and 41<=lat<=82 and 19<=lon<=180):continue
 # Raw selected provider binding still needs positive ownlevel; streets/SNT/parent levels are excluded.
 if str(z['provider_fias_level']) not in ['4','5','6']:continue
 raw_current_points[sid]={'target_source_record_id':sid,'coordinate_source_record_id':str(z['provider_general_fias_id']),'latitude':lat,'longitude':lon,'point_origin_file':str(A),'point_origin_sha256':A_hash,'point_origin_locator':'source_record_id='+sid+';provider_latitude,provider_longitude;own name/type/NP flags','provider_ID_binding_status':'UNRESOLVED_NOT_AUTOMATIC_IDENTITY','coordinate_admission_status':'candidate_source_positive_raw_ownpoint','boundary_comparability_asserted':False,'native_code_asserted':False}
for z in o[o.census_year.eq(2021)].to_dict('records'):
 if z['source_record_id'] in raw_current_points and whole(z):current[(z['n'],z['r'])].append(z)
def currentpoint(sid):return s.point_rows.get(sid,raw_current_points.get(sid))
current_type_counts=Counter((x['n'],x['t'],x['r']) for xs in current.values() for x in xs)
old_type_counts=Counter(k for k,xs in oldidx.items() for x in xs)
occupied=defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
owner_ids=set();owner_files=[]
for pp in [R/'research_rebuild/evidence/native_alias_remaining_mass_20261008/existing_ownpoint_native02_mass/accepted_source_bindings.csv.gz',R/'research_rebuild/evidence/native_alias_remaining_mass_20261008/whole_region_type_unique_followup/whole_region_exact_type_native02_candidates.csv.gz']:
 if pp.exists():
  ff=pd.read_csv(pp,dtype=str);owner_files.append(pp)
  for cc in ['old_source_record_id','native2010_source_record_id','current_source_record_id']:owner_ids.update(ff[cc])
owner_ids.update(['2002:064_d017f142fc_Tyva.xls:Sheet1:395','2002:006_1916564aaa_02c_Kaluzhskaja.xls:Sheet1:1189'])
counts=Counter();candidates=[];holds=[];old=o[o.census_year.isin([2002,2010])&o.source_record_id.map(lambda sid:s.years[s.uf.find(sid)]!={2002,2010,2021})].sort_values('population',ascending=False)
for a in old.to_dict('records'):
 sid=a['source_record_id'];
 if sid in owner_ids:counts['Excluded frozen other-agent native alias cohort']+=1;continue
 key=(a['n'],a['t'],a['r']);
 if a['census_year']==2002 and old_type_counts[(2002,*key)]==1 and current_type_counts[key]==1:counts['Excluded other-agent globally exact-name-type unique native02 route']+=1;continue
 clmatches=classidx.get(key,[])
 if a['code']:clmatches=[z for z in clmatches if z[0]==a['code'] or (len(z[0])==8 and a['code']==z[0]+'000')]
 elif a['d']:clmatches=[z for z in clmatches if z[1]==a['d']]
 if len(clmatches)!=1:counts['Historical own code/name/type/source context not uniquely bound']+=1;continue
 gc,dc=clmatches[0];gh=hist.get(gc)
 if not gh:counts['No valid exact raw own point for bound historical code']+=1;continue
 if a['d'] and dc and a['d']!=dc:counts['Actual historical county contradiction']+=1;continue
 # Native old rivals need compatible source context; a raw classifier spatial guess does not resolve two indistinguishable census rows.
 rivals=[x for x in oldidx[(int(a['census_year']),*key)] if x['source_record_id']!=sid and (not a['d'] or not x['d'] or x['d']==a['d'])]
 if rivals:counts['Indistinguishable same-year native old source rivals']+=1;continue
 hp=(gh['latitude_from_lat'],gh['longitude_from_long']);
 if gc in excluded:counts['Known wrong raw point source exclusion']+=1;continue
 # Coordinate clustering is retained as risk info; a distinct native code and source context remain mandatory.
 raw_coordinate_cluster_size=rawocc.get(hp,0)
 # All current own-point candidates, including full histories, are considered before graph compatibility filtering.
 near=[]
 for b in current.get((a['n'],a['r']),[]):
  pp=currentpoint(b['source_record_id']);dist=distance_km(hp,(pp['latitude'],pp['longitude']))
  if dist<=5:near.append((b,dist))
 if len(near)!=1:counts['No unique physical current candidate within 5 km']+=1;continue
 b,dist=near[0];bid=b['source_record_id'];ra,rb=s.uf.find(sid),s.uf.find(bid)
 if bid in owner_ids:counts['Excluded frozen other-agent native alias cohort']+=1;continue
 if ra==rb:counts['Already joined two-year identity; third native observation remains missing']+=1;continue
 if s.years[ra]|s.years[rb]!={2002,2010,2021}:counts['Would remain two-year rather than close third-year gap']+=1;continue
 reasons=[];component=members[ra]+members[rb];cp=currentpoint(bid)
 if s.years[ra]&s.years[rb]:reasons.append('Real repeated census year component')
 if any(x in eventids for x in component):reasons.append('Known event or qualified scope lineage')
 if a['t'] in ['станция','разъезд'] and bid not in ownrail:reasons.append('Railway counterpart lacks own populated-locality class')
 if a['t']=='город' and b['t'] not in ['город','пгт','поселок']:reasons.append('Incompatible own physical type')
 for x in component:
  if x in s.conflicting_point_targets:reasons.append('Active point alternative conflict')
  pp=s.point_rows.get(x);rr=s.by_id.loc[x]
  if pp and distance_km((pp['latitude'],pp['longitude']),(cp['latitude'],cp['longitude']))>5:reasons.append('Existing admitted component point conflict')
  if pp and occupied[(int(rr.census_year),pp['latitude'],pp['longitude'])]-{x}:reasons.append('Own admitted point shared by another same-year record')
  if not pp and occupied[(int(rr.census_year),cp['latitude'],cp['longitude'])]:reasons.append('New point would collide with another same-year record')
  if pd.notna(rr.latitude) and pd.notna(rr.longitude) and (float(rr.latitude),float(rr.longitude))!=(0,0) and distance_km((float(rr.latitude),float(rr.longitude)),(cp['latitude'],cp['longitude']))>5:reasons.append('Actual selected coordinate candidate conflicts')
 if reasons:
  counts.update(set(reasons))
  if len(holds)<150:holds.append({'source_record_id':sid,'current_source_record_id':bid,'name':a['settlement_name'],'old_population':a['population'],'historical_code':gc,'distance_km':dist,'reason':'; '.join(sorted(set(reasons)))})
  continue
 candidates.append({'from_source_record_id':sid,'from_year':int(a['census_year']),'to_source_record_id':bid,'name':a['settlement_name'],'old_type':a['settlement_type'],'current_type':b['settlement_type'],'old_population':a['population'],'current_population':b['population'],'region':a['r'],'old_printed_county':a['district_raw'],'old_bound_county':a['d'],'county_binding':a['county_binding'],'raw_historical_county':dc,'current_printed_county':b['district_raw'],'historical_okato_2009_raw':gc,'historical_okato_2011_raw':gh['historical_okato_2011_raw'],'old_raw_name_2009':gh['name_raw_2009'],'old_raw_name_2011':gh['name_raw_2011'],'old_raw_type_2011':gh['settlement_type_raw'],'old_raw_record_1based':gh['record_number_1based'],'old_raw_classifier_line_1based':gh['source_line_1based'],'auxiliary_raw_coordinate_code_cluster_size':raw_coordinate_cluster_size,'current_point_previously_admitted':bid in s.point_rows,'provider_ID_binding_status':cp.get('provider_ID_binding_status','already_independently_admitted'),'old_raw_latitude':hp[0],'old_raw_longitude':hp[1],'distance_km':dist,'all_region_name_current_candidates':len(current[(a['n'],a['r'])]),'current_candidates_within_5km':len(near),'old_component_years':json.dumps(sorted(s.years[ra])),'current_component_years':json.dumps(sorted(s.years[rb])),'component_source_ids_json':json.dumps(component,ensure_ascii=False),'current_own_point_json':json.dumps(cp,ensure_ascii=False),'old_source_file':a['source_file'],'old_source_locator':a['source_locator'] or sid,'current_source_file':b['source_file'],'current_source_locator':b['source_locator'],'old_native_code_asserted':bool(a['code']),'status':'Candidate only; no loader or accepted ledger changes'})
f=pd.DataFrame(candidates);f.to_csv(O/'candidate_source_bound_spatial_edges.csv',index=False);pd.DataFrame(holds).to_csv(O/'bounded_hard_holds.csv',index=False)

receipt={'baseline_stage':39,'status':'bounded_raw_ownpoint_route_diagnostic','old_unresolved_rows_scanned':len(old),'positive_full3_native_source_candidates':len(candidates),'candidate_population_by_year':{str(y):{'rows':len(g),'population':int(g.old_population.sum())} for y,g in f.groupby('from_year')}if len(f)else{},'source_positive_unadmitted_current_raw_points':len(raw_current_points),'selected_old_raw_coordinates_count':int(s.obs[s.obs.census_year.isin([2002,2010])].latitude.notna().sum()),'outcomes':dict(counts),'input_pins':{str(p):sha(p) for p in list(s.inputs)+[H,C,P,W,ctx,ex,A]+owner_files},'output_pins':{p.name:sha(p) for p in O.glob('*.csv')},'old_raw_coordinates_require_positive_own_classifier_name_type_code_sourcecounty':True,'old_point_previously_admitted_required':False,'all_current_namesakes_before_graph_filter':True,'other_agent_exact_region_name_type_unique_missing02_excluded':True,'no_network':True,'report_loader_Git_modified':False};(O/'inventory_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
