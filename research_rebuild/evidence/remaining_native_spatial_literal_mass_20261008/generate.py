import sys,json,re,math
from pathlib import Path
from collections import defaultdict,Counter
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
sys.path.insert(0,str(R/'research_rebuild/evidence/native2010_remaining_county_rule_mass_20261008'))
from scan import cn as county_key
O=Path(__file__).parent;s=load(56);before=s.metrics();c=duckdb.connect();H=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet');C=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');P=Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet');h=c.execute('select * from read_parquet(?)',[str(H)]).fetchdf();cl=c.execute('select historical_okato,name,status,is_settlement_raw from read_parquet(?)',[str(C)]).fetchdf();counties={r.historical_okato[:5]:county_key(r.name) for r in cl.itertuples() if r.is_settlement_raw=='f' and len(r.historical_okato)==8 and r.historical_okato.endswith('000') and 'район' in normalize(r.name) and r.historical_okato[2]=='2'};regions={k:normalize(g.historical_point_modern_region.mode().iloc[0]) for k,g in h.dropna(subset=['historical_point_modern_region']).groupby(h.historical_okato_2009_raw.str[:2])};types={'деревня':'деревня','село':'село','поселок сельского типа':'поселок','хутор':'хутор','поселок городского типа':'пгт','город':'город','станица':'станица','станция':'станция','разъезд':'разъезд','слобода':'слобода'}
def n(v):
 x=normalize(v);x=re.sub(r'^(?:поселок|посёлок|село|деревня|хутор|п\.|с\.|д\.)\s+','',x);x=re.sub(r'^(?:свх\.?|совхоз)\s+','совхоза ',x);x=re.sub(r'\bим\.\s*','имени ',x);return ' '.join(re.sub('[^а-яa-z0-9]+',' ',x).split())
def compatible(a,b):
 rural={'деревня','село','поселок','посёлок','хутор'}
 return a==b or (a in rural and b in rural)
def code(v):
 if v is None or pd.isna(v):return ''
 x=str(v).strip();return x[:-2] if x.endswith('.0') else x
classidx=defaultdict(list)
for z in cl[cl.is_settlement_raw.eq('t')].to_dict('records'):
 gc=z['historical_okato'];classidx[(n(z['name']),regions.get(gc[:2],''))].append((gc,counties.get(gc[:5],''),types.get(z['status'],normalize(z['status']))))
valid=h[h.historical_name_exact.fillna(False)&h.historical_type_exact.fillna(False)&h.historical_code_structure_compatible.fillna(False)&~h.is_deleted.fillna(True)&h.latitude_from_lat.between(41,82)&h.longitude_from_long.between(19,180)];hist={str(z['historical_okato_2009_raw']):z for z in valid.to_dict('records')};rawocc={(lat,lon):num for lat,lon,num in c.execute('select latitude_from_lat,longitude_from_long,count(distinct historical_okato) from read_parquet(?) where not is_deleted group by all',[str(P)]).fetchall()};ex=R/'research_rebuild/evidence/direct_old_geokladr_point_reserve_20261007_spatial_review/suggested_raw_point_exclusion_keys.csv';excluded=set(pd.read_csv(ex,dtype=str).raw_own_code)
eventids=set();eventpins={}
for q in (R/'research_rebuild/evidence/native2010_remaining_county_rule_mass_20261008').glob('baseline49_union_*'):
 f=pd.read_csv(q,dtype=str,keep_default_na=False);eventpins[str(q)]=sha(q)
 if 'direct_' in q.name or 'formation_' in q.name or 'merger' in q.name:
  if 'source_record_id' in f:eventids.update(f.source_record_id)
flagged=set()
for folder in ['native_mass_raw_roster_point_corrections_20261008','baseline_fullraw_point_code_conflict_scan_20261008']:
 for q in (R/'research_rebuild/evidence'/folder).glob('*.csv*'):
  try:f=pd.read_csv(q,keep_default_na=False)
  except pd.errors.EmptyDataError:continue
  if 'source_record_id' in f:flagged.update(f.source_record_id);eventpins[str(q)]=sha(q)
o=s.obs[s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь','крым'])].copy();o=o[~o.settlement_name.fillna('').str.contains(r'\(часть|\bитого\b|\bвсего\b',case=False,regex=True)];o['n']=o.settlement_name.map(n);o['t']=o.type_norm.map(normalize);o['r']=o.region_norm.map(normalize);o['d']=o.district_raw.map(county_key);o['code']=o.okato.map(code)
ctx=Path('/workspace/settlements-work/secondary_2010_county_context_batch_20261007/all_selected_competitor_county_context.csv.gz');context=pd.read_csv(ctx,dtype=str,keep_default_na=False).set_index('source_record_id').to_dict('index');o['county_binding']=o.source_record_id.map(lambda sid:context.get(sid,{}).get('inference','printed_source_county'));o.loc[o.d.eq(''),'d']=o.loc[o.d.eq(''),'source_record_id'].map(lambda sid:context.get(sid,{}).get('inferred_county_key',''))
current=defaultdict(list);oldidx=defaultdict(list);alloldidx=defaultdict(list);members=defaultdict(list);ownrail=set();W=Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet');w=c.execute('select source_record_id,wikidata_qid,wikidata_truthy_p31_claims_json from read_parquet(?)',[str(W)]).fetchdf()
for z in w.to_dict('records'):
 pp=s.point_rows.get(z['source_record_id']);
 if pp and pp.get('coordinate_source_record_id')==z['wikidata_qid'] and any(q['value_qid'] in ['Q24258416','Q27062006','Q27517483'] for q in json.loads(z['wikidata_truthy_p31_claims_json'])):ownrail.add(z['source_record_id'])
def whole(a):return 'объект' not in normalize(a['settlement_type']) or a['source_record_id'] in ownrail
component_names=s.obs.groupby('root').settlement_name.apply(list).to_dict()
for a in o.to_dict('records'):
 members[s.uf.find(a['source_record_id'])].append(a['source_record_id'])
 if a['census_year']==2021 and a['source_record_id'] in s.point_rows and whole(a):
  names={n(x) for x in component_names[s.uf.find(a['source_record_id'])]}
  for name in names:current[(name,a['r'])].append(a)
 if a['census_year'] in [2002,2010]:oldidx[(int(a['census_year']),a['n'],a['t'],a['r'])].append(a);alloldidx[(int(a['census_year']),a['n'],a['r'])].append(a)
county_associations=defaultdict(list)
for root,ids in members.items():
 if s.years[root]!={2002,2010,2021} or any(i in flagged for i in ids):continue
 cur=s.by_id.loc[next(i for i in ids if int(s.by_id.loc[i,'census_year'])==2021)];cc=county_key(cur.district_raw)
 for i in ids:
  ar=s.by_id.loc[i]
  if int(ar.census_year)==2021:continue
  ac=county_key(ar.district_raw) or county_key(context.get(i,{}).get('inferred_county_key',''))
  if ac and cc and ar.region_norm==cur.region_norm and n(ar.settlement_name)==n(cur.settlement_name):county_associations[(ar.region_norm,ac,cc)].append((i,cur.source_record_id,ar.settlement_name))
def countyroute(r,a,b):return bool(a and b and (a==b or len(county_associations.get((r,a,b),[]))>=3))
occupied=defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
counts=Counter();candidates=[];holds=[];old=o[o.census_year.isin([2002,2010])&o.source_record_id.map(lambda sid:s.years[s.uf.find(sid)]!={2002,2010,2021} or sid not in s.point_rows)].sort_values('population',ascending=False)
for a in old.to_dict('records'):
 sid=a['source_record_id'];key=(a['n'],a['t'],a['r']);clmatches=[z for z in classidx.get((a['n'],a['r']),[]) if compatible(a['t'],z[2])]
 if sid in flagged:counts['Known raw roster carrier correction pending']+=1;continue
 if a['code']:clmatches=[z for z in clmatches if z[0]==a['code'] or (len(z[0])==8 and a['code']==z[0]+'000')]
 elif a['d']:clmatches=[z for z in clmatches if z[1]==a['d']]
 if len(clmatches)!=1:counts['Historical own code/name/type/source context not uniquely bound']+=1;continue
 gc,dc,gt=clmatches[0];gh=hist.get(gc)
 if not gh:counts['No valid exact raw own point for bound historical code']+=1;continue
 if a['d'] and dc and a['d']!=dc:counts['Actual historical county contradiction']+=1;continue
 # Native old rivals need compatible source context; a raw classifier spatial guess does not resolve two indistinguishable census rows.
 rivals=[x for x in alloldidx[(int(a['census_year']),a['n'],a['r'])] if x['source_record_id']!=sid and (not a['d'] or not x['d'] or x['d']==a['d'])]
 if rivals:counts['Indistinguishable same-year native old source rivals']+=1;continue
 hp=(gh['latitude_from_lat'],gh['longitude_from_long']);
 if gc in excluded:counts['Known wrong raw point source exclusion']+=1;continue
 if rawocc.get(hp)!=1:
  stable=[b for b in current.get((a['n'],a['r']),[]) if b['source_record_id'] not in flagged and b['code'] and (b['code']==gc or b['code']+'000'==gc or gc+'000'==b['code']) and compatible(a['t'],b['t']) and countyroute(a['r'],a['d'] or dc,b['d'])]
  if len(stable)!=1:counts['Raw shared point lacks independently exact current native own code']+=1;continue
  stablecp=s.point_rows[stable[0]['source_record_id']]
  if distance_km(hp,(stablecp['latitude'],stablecp['longitude']))>5:counts['Raw shared point/current exact own code physical contradiction']+=1;continue
 # All current own-point candidates, including full histories, are considered before graph compatibility filtering.
 near=[]
 for b in current.get((a['n'],a['r']),[]):
  if b['source_record_id'] in flagged or not compatible(a['t'],b['t']):continue
  if not countyroute(a['r'],a['d'] or dc,b['d']):continue
  pp=s.point_rows[b['source_record_id']];dist=distance_km(hp,(pp['latitude'],pp['longitude']))
  if dist<=5:near.append((b,dist))
 if len(near)!=1:counts['No unique physical current candidate within 5 km']+=1;continue
 b,dist=near[0];bid=b['source_record_id'];ra,rb=s.uf.find(sid),s.uf.find(bid)
 if ra==rb and all(i in s.point_rows for i in members[ra]):counts['Already joined and all points present']+=1;continue
 reasons=[];component=list(dict.fromkeys(members[ra]+members[rb]));cp=s.point_rows[bid]
 if ra!=rb and s.years[ra]&s.years[rb]:reasons.append('Real repeated census year component')
 if any(x in flagged for x in component):reasons.append('Known pending carrier correction in component')
 if a['code'] and b['code'] and a['code']!=b['code'] and a['code']+'000'!=b['code'] and b['code']+'000'!=a['code']:reasons.append('Actual native historic/current own OKATO contradiction')
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
 candidates.append({'from_source_record_id':sid,'from_year':int(a['census_year']),'to_source_record_id':bid,'name':a['settlement_name'],'old_type':a['settlement_type'],'current_type':b['settlement_type'],'old_population':a['population'],'current_population':b['population'],'region':a['r'],'old_printed_county':a['district_raw'],'old_bound_county':a['d'],'county_binding':a['county_binding'],'raw_historical_county':dc,'county_caption_association_named_anchors_json':json.dumps(county_associations.get((a['r'],a['d'] or dc,b['d']),[])[:5],ensure_ascii=False),'current_printed_county':b['district_raw'],'historical_okato_2009_raw':gc,'historical_okato_2011_raw':gh['historical_okato_2011_raw'],'old_raw_name_2009':gh['name_raw_2009'],'old_raw_name_2011':gh['name_raw_2011'],'old_raw_type_2011':gh['settlement_type_raw'],'old_raw_record_1based':gh['record_number_1based'],'old_raw_classifier_line_1based':gh['source_line_1based'],'old_raw_latitude':hp[0],'old_raw_longitude':hp[1],'distance_km':dist,'all_region_name_current_candidates':len(current[(a['n'],a['r'])]),'current_candidates_within_5km':len(near),'old_component_years':json.dumps(sorted(s.years[ra])),'current_component_years':json.dumps(sorted(s.years[rb])),'component_source_ids_json':json.dumps(component,ensure_ascii=False),'current_own_point_json':json.dumps(cp,ensure_ascii=False),'old_source_file':a['source_file'],'old_source_locator':a['source_locator'] or sid,'current_source_file':b['source_file'],'current_source_locator':b['source_locator'],'old_native_code_asserted':bool(a['code']),'raw_historical_point_shared_code_count':rawocc.get(hp),'exact_current_native_OKATO_matches_historic_own_code':bool(b['code'] and (b['code']==gc or b['code']+'000'==gc or gc+'000'==b['code'])),'status':'Candidate only; no loader or accepted ledger changes'})
f=pd.DataFrame(candidates);f.to_csv(O/'candidate_source_bound_spatial_edges.csv',index=False);pd.DataFrame(holds).to_csv(O/'bounded_hard_holds.csv',index=False)
# Batch replay ensures global disjoint-year consistency and counts only actual newly finite histories.
edges=[];points=[];used=[];batchholds=[]
for z in candidates:
 sid,bid=z['from_source_record_id'],z['to_source_record_id'];ra,rb=s.uf.find(sid),s.uf.find(bid)
 if ra==rb and all(i in s.point_rows for i in members[ra]):continue
 if ra!=rb and s.years[ra]&s.years[rb]:batchholds.append({**z,'reason':'Batch repeated-year collision'});continue
 cp=s.point_rows[bid];m=list(dict.fromkeys(members[ra]+members[rb]))
 if any(x in s.point_rows and distance_km((s.point_rows[x]['latitude'],s.point_rows[x]['longitude']),(cp['latitude'],cp['longitude']))>5 for x in m):batchholds.append({**z,'reason':'Batch component own-point disagreement'});continue
 if any(x not in s.point_rows and occupied[(int(s.by_id.loc[x,'census_year']),cp['latitude'],cp['longitude'])] for x in m):batchholds.append({**z,'reason':'Batch same-year point collision'});continue
 s.union(sid,bid);members[s.uf.find(sid)]=m;edge=dict(z,relation='same_place',decision_status='candidate_pending_root_review');edge.pop('current_own_point_json',None);
 if ra!=rb:edges.append(edge)
 used.append(z)
 for x in m:
  if x in s.point_rows:continue
  p=dict(cp);p.update(target_source_record_id=x,coordinate_admission_status='candidate_pending_root_review',native_code_asserted=False,boundary_comparability_asserted=False,point_temporal_interpretation='Modern own representative retrospectively over proposed native physical continuity');p.pop('point_ledger_path',None);points.append(p);s.point_rows[x]=dict(p,point_ledger_path=str(O/'candidate_point_use_delta.csv'));occupied[(int(s.by_id.loc[x,'census_year']),p['latitude'],p['longitude'])].add(x)
pd.DataFrame(edges).to_csv(O/'candidate_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(O/'candidate_point_use_delta.csv',index=False);pd.DataFrame(batchholds).to_csv(O/'batch_holds.csv',index=False);after=s.metrics();newroots={s.uf.find(z['from_source_record_id']) for z in used if s.years[s.uf.find(z['from_source_record_id'])]=={2002,2010,2021}};fullpop={str(y):sum(int(s.by_id.loc[x,'population']) for root in newroots for x in members[root] if int(s.by_id.loc[x,'census_year'])==y) for y in (2002,2010,2021)};r={'baseline_stage':56,'candidate_only':True,'source_bound_edges_before_union':len(candidates),'batch_compatible_identity_edges':len(edges),'candidate_point_uses':len(points),'new_finite_full_three_year_histories':len(newroots),'new_finite_full_three_year_populations':fullpop,'before':before,'after':after,'actual_net_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'actual_net_rows_gain':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'outcomes':dict(counts),'candidate_old_observations':{str(y):{'rows':len(g),'population':int(g.old_population.sum())} for y,g in f.groupby('from_year')} if len(f) else {},'spatial_rule':'All exact name/region current physical alternatives within 5 km considered before graph filtering; historical own code/name/type/source county bound before spatial search','independence_interpretation':'Each record has its own binding, independent of proposed edge; same original provider is allowed','input_pins':eventpins|{str(p):sha(p) for p in [H,C,P,W,ctx,ex,*s.inputs]},'output_pins':{p.name:sha(p) for p in O.glob('*.csv')}};(O/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:r[k] for k in ['source_bound_edges_before_union','batch_compatible_identity_edges','candidate_point_uses','new_finite_full_three_year_histories','new_finite_full_three_year_populations','actual_net_population_gain','outcomes']},ensure_ascii=False,indent=2))
