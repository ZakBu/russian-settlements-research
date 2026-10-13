"""Bounded selected secondary-2010 XLS source-county inference; candidates only."""
import sys,json,re,bisect
from pathlib import Path
from collections import defaultdict,Counter
import pandas as pd,duckdb,xlrd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).parent;WORK=Path('/workspace/settlements-work/cached_wikipedia_history_mass_20261008/actual_county_header_extension');WORK.mkdir(parents=True,exist_ok=True);RAW=Path('/workspace/settlements-raw')
SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
s=load(28);A=OUT.parent/'refreshed_2010_context/application';s.add_deltas([A/'accepted_identity_edge_delta.csv'],[A/'accepted_point_use_delta.csv']);baseline=s.metrics()
c=duckdb.connect(config={'threads':1,'memory_limit':'600MB'});meta=c.execute('SELECT source_record_id,source_sheet,source_row,source_name_raw,entity_grain_status FROM read_parquet(?) WHERE census_year=2010',[str(SEL)]).fetchdf()
f=s.obs[s.obs.census_year.eq(2010)].merge(meta,on='source_record_id',validate='one_to_one');f['n']=f.name_norm.map(normalize);f['t']=f.type_norm.map(normalize);f['r']=f.region_norm.map(normalize);f['county']=f.district_raw.map(county_key)
comps=defaultdict(dict)
for a in s.obs.to_dict('records'):comps[s.uf.find(a['source_record_id'])][int(a['census_year'])]=a
pairidx=defaultdict(list);rootcurrent={}
for root,years in comps.items():
 cur=years.get(2021)
 if cur and county_key(cur['district_raw']):rootcurrent[root]=(county_key(cur['district_raw']),cur['source_record_id'])
 if set(years)!={2002,2021} or not cur or cur['source_record_id'] not in s.point_rows:continue
 if not all(bool(a['is_additive_settlement_record']) for a in years.values()):continue
 pairidx[(normalize(cur['name_norm']),normalize(cur['region_norm']))].append((years[2002],cur))
EVENT=ROOT/'research_rebuild/evidence/event_aware_path_union_20261005/accepted_event_path_selected_rows.csv'
event_ids=set(pd.read_csv(EVENT,dtype=str).source_record_id) if EVENT.is_file() else set()
occupied=defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
pool=f[f.source_file.str.contains(r'(?:004_486e984bdc|014_5ca759eea0|016_802d308e41)',na=False)&~f.r.isin(['тульская','свердловская','ульяновская','чеченская'])&f.population.between(0,2000)&~f.t.isin(['город','пгт'])&f.source_record_id.map(lambda x:s.years[s.uf.find(x)]=={2010})&f.is_additive_settlement_record.fillna(False)&f.source_file.fillna('').str.endswith('.xls')].copy();pool=pool[[bool(pairidx.get((a.n,a.r))) for a in pool.itertuples()]];pool=pool.sort_values(['population','source_record_id'],ascending=[False,True]).head(5000)
# Infer all same-label competitors within each bounded target's file/region; never just the target surviving a gate.
keys=set(zip(pool.n,pool.r));competitor=f[[ (a.n,a.r) in keys for a in f.itertuples()]].copy()
needed_groups=set(zip(competitor.source_file,competitor.source_sheet,competitor.r));groups={key:g.sort_values('source_row') for key,g in f.groupby(['source_file','source_sheet','r'],dropna=False) if key in needed_groups}
counts=Counter();resolved={};proofs={};hashes={};books={};literal_checks={};diagnostics=[];headercache={}
def sheet(path,name):
 if path not in books:
  if not path.is_file():return None
  books[path]=xlrd.open_workbook(str(path),on_demand=True);hashes[str(path)]=sha(path)
 try:return books[path].sheet_by_name(str(name))
 except Exception:return None
def literal(a):
 sid=a['source_record_id']
 if sid in literal_checks:return literal_checks[sid]
 p=RAW/str(a['source_file']);sh=sheet(p,a['source_sheet']);num=a['source_row']
 if sh is None or pd.isna(num) or not float(num).is_integer() or not 1<=int(num)<=sh.nrows:literal_checks[sid]=None;return None
 vals=sh.row_values(int(num)-1);strings=[(i,str(v)) for i,v in enumerate(vals) if isinstance(v,str) and str(v).strip()]
 name=normalize(a['settlement_name']);namefound=[(i,v) for i,v in strings if name in normalize(v)]
 # Prefer exact preserved source label; otherwise normalize an anchored printed settlement designator.
 exact=[(i,v) for i,v in strings if normalize(v)==normalize(a['source_name_raw'])] if pd.notna(a['source_name_raw']) else []
 if exact:namefound=exact
 okay=len(namefound)==1
 numbers=[]
 if namefound:
  col=namefound[0][0]
  numbers=[(i,v) for i,v in enumerate(vals) if i>col and isinstance(v,(int,float)) and v==a['population']]
 result={'source_record_id':sid,'source_file':str(p),'source_sha256':hashes[str(p)],'source_sheet':sh.name,'source_row_1based':int(num),'literal_label_match':okay,'protected_population_cell_found':bool(numbers),'population':a['population'],'raw_label':namefound[0][1] if namefound else '', 'label_column_1based':namefound[0][0]+1 if namefound else None,'population_column_1based':numbers[0][0]+1 if numbers else None,'raw_cells':' | '.join(str(v) for v in vals if v!='')[:2200]}
 literal_checks[sid]=result;return result
for group,g in groups.items():
 g=g[~g.source_row.duplicated(keep=False)].copy();anchors=[]
 for a in g.to_dict('records'):
  ctx=rootcurrent.get(s.uf.find(a['source_record_id']))
  if ctx and s.years[s.uf.find(a['source_record_id'])]!={2010} and pd.notna(a['source_row']) and a['is_additive_settlement_record']:
   if a['county'] and a['county']!=ctx[0]:continue
   anchors.append((float(a['source_row']),a,ctx))
 anchors.sort(key=lambda a:a[0]);nums=[a[0] for a in anchors]
 for a in competitor[(competitor.source_file==group[0])&(competitor.source_sheet==group[1])&(competitor.r==group[2])].to_dict('records'):
  sid=a['source_record_id'];direct=a['county'];ctx=rootcurrent.get(s.uf.find(sid))
  if direct:resolved[sid]=direct;proofs[sid]={'inference':'selected_explicit_source_county'};continue
  if ctx:resolved[sid]=ctx[0];proofs[sid]={'inference':'existing_accepted_identity_current_county'};continue
  if pd.isna(a['source_row']):counts['missing_physical_row']+=1;continue
  n=float(a['source_row']);lo=bisect.bisect_left(nums,n)-1;hi=bisect.bisect_right(nums,n)
  if lo<0 or hi>=len(anchors):counts['no_two_sided_accepted_anchors']+=1;continue
  lower,upper=anchors[lo],anchors[hi]
  # Additional extension only inside an actual published county block, never a guessed larger window.
  sh=sheet(RAW/str(a['source_file']),a['source_sheet']);headers=headercache.get((a['source_file'],a['source_sheet']))
  if headers is None:headers=[]
  for rawi in (range(sh.nrows) if (a['source_file'],a['source_sheet'])not in headercache else []):
   vals=sh.row_values(rawi)
   for rawj,v in enumerate(vals[:5]):
    if isinstance(v,str) and re.match(r'^\s*(?:муниципальный район\s+.+|.+\s+район)\s*$',v.strip(),re.I):
     headers.append((rawi+1,rawj+1,v,county_key(v)));break
  headercache[(a['source_file'],a['source_sheet'])]=headers
  prior=[h for h in headers if h[0]<n];later=[h for h in headers if h[0]>n]
  if not prior or not later:counts['no_actual_published_county_start_end_headers']+=1;continue
  start,end=prior[-1],later[0]
  if not(start[0]<lower[0]<n<upper[0]<end[0]):counts['flanking_anchors_cross_actual_county_control']+=1;continue
  blockanchors=[v for v in anchors if start[0]<v[0]<end[0]]
  if len({v[1]['settlement_name'] for v in blockanchors})<3:counts['fewer_than_three_distinct_accepted_block_anchors']+=1;continue
  if len({v[2][0] for v in blockanchors})!=1:counts['accepted_block_current_county_competitors']+=1;continue
  histcounty=[]
  for v in blockanchors:
   old=comps[s.uf.find(v[1]['source_record_id'])].get(2002)
   if old:histcounty.append(county_key(old['district_raw']))
  if len(histcounty)<3 or any(v!=start[3]for v in histcounty):counts['published_header_not_corroborated_by_three_historical_county_anchors']+=1;continue
  third=next(v for v in blockanchors if v[1]['source_record_id']not in [lower[1]['source_record_id'],upper[1]['source_record_id']])
  check3=literal(third[1])
  if check3 is None or not check3['literal_label_match']or not check3['protected_population_cell_found']:counts['third_block_anchor_exact_native_cell_failed']+=1;continue
  if lower[2][0]!=upper[2][0]:counts['anchors_conflicting_counties']+=1;continue
  if len({normalize(x['settlement_name']) for x in [a,lower[1],upper[1]]})<3:counts['anchors_not_three_distinct_labels']+=1;continue
  checks=[literal(x) for x in [a,lower[1],upper[1]]]
  if any(x is None or not x['literal_label_match'] or not x['protected_population_cell_found'] for x in checks):counts['raw_literal_or_protected_population_failed']+=1;continue
  # Printed district headers within the bracket are explicit hard contradictions, not ignored county changes.
  sh=sheet(RAW/str(a['source_file']),a['source_sheet']);between=[]
  for z in range(int(lower[0])-1,int(upper[0])):
   vals=sh.row_values(z)
   for j,v in enumerate(vals):
    if isinstance(v,str) and re.search(r'\bрайон\b|\bр[ -]н\b',normalize(v)) and normalize(v)!='район':between.append((z+1,j+1,str(v),county_key(v)))
  if any(x[3] and x[3]!=lower[2][0] for x in between):counts['explicit_raw_parent_conflicts_with_anchor_county']+=1;continue
  resolved[sid]=lower[2][0];proofs[sid]={'inference':'actual_published_county_block_corroborated_by_three_distinct_accepted_native_anchors','literal_county_start_row':start[0],'literal_county_start_label':start[2],'literal_next_county_row':end[0],'literal_next_county_label':end[2],'third_block_anchor_2010_id':third[1]['source_record_id'],'third_block_anchor_current_id':third[2][1],'all_accepted_block_anchor_count':len(blockanchors),'all_accepted_block_current_county_count':1,'lower_anchor_2010_id':lower[1]['source_record_id'],'lower_anchor_current_id':lower[2][1],'lower_anchor_source_row':int(lower[0]),'upper_anchor_2010_id':upper[1]['source_record_id'],'upper_anchor_current_id':upper[2][1],'upper_anchor_source_row':int(upper[0]),'raw_parent_headers_in_bracket':json.dumps(between,ensure_ascii=False)}
# Uniqueness is assessed only after every same-name/region selected 2010 competitor has been assigned context.
bykey=defaultdict(list)
for a in competitor.to_dict('records'):bykey[(a['n'],a['r'])].append(a)
candidates=[];held=[]
for a in pool.to_dict('records'):
 sid=a['source_record_id'];county=resolved.get(sid)
 if not county:counts['target_county_unresolved']+=1;continue
 others=[q for q in bykey[(a['n'],a['r'])] if q['source_record_id']!=sid and (not resolved.get(q['source_record_id']) or resolved[q['source_record_id']]==county)]
 if others:counts['selected_alternative_same_or_unresolved_county']+=1;held.append({'source_record_id':sid,'name':a['settlement_name'],'population':a['population'],'inferred_county':county,'reason':'selected_alternative_same_or_unresolved_county','alternative_ids':' | '.join(q['source_record_id'] for q in others)});continue
 pairs=[(old,cur) for old,cur in pairidx[(a['n'],a['r'])] if county_key(cur['district_raw'])==county]
 if len(pairs)!=1:counts['not_unique_existing_2002_2021_pair_in_inferred_county']+=1;continue
 old,cur=pairs[0]
 if any(t in event_ids for t in [sid,old['source_record_id'],cur['source_record_id']]):counts['known_event_scope_endpoint']+=1;continue
 p=s.point_rows[cur['source_record_id']];oldp=s.point_rows.get(old['source_record_id']);existing=s.point_rows.get(sid)
 if any(t in s.conflicting_point_targets for t in [sid,old['source_record_id'],cur['source_record_id']]) or any(q and distance_km((q['latitude'],q['longitude']),(p['latitude'],p['longitude']))>5 for q in [oldp,existing]):counts['accepted_point_contradiction_over_5km']+=1;continue
 if occupied.get((2010,p['latitude'],p['longitude']),set())-{sid}:counts['point_already_assigned_to_distinct_accepted_2010_row']+=1;continue
 check=literal(a)
 if check is None or not check['literal_label_match'] or not check['protected_population_cell_found']:counts['target_raw_literal_failed']+=1;continue
 if not a['is_additive_settlement_record'] or re.search(r'\(часть|\bрайон\b|итого|всего',normalize(a['settlement_name'])):counts['aggregate_partial_or_admin_row']+=1;continue
 proof=proofs[sid];candidate={'target_2010_source_record_id':sid,'2002_endpoint_source_record_id':old['source_record_id'],'2021_endpoint_source_record_id':cur['source_record_id'],'settlement_name':a['settlement_name'],'type_2010':a['settlement_type'],'type_2002':old['settlement_type'],'type_2021':cur['settlement_type'],'printed_type_variation_flag':len({normalize(x['settlement_type']) for x in [a,old,cur]})>1,'region_norm':a['r'],'inferred_county_key':county,'historical_county_raw':old['district_raw'],'current_county_raw':cur['district_raw'],'historical_current_county_change_flag':bool(county_key(old['district_raw']) and county_key(old['district_raw'])!=county),'population_2002':old['population'],'population_2010_protected_unchanged':a['population'],'population_2021':cur['population'],'candidate_status':'candidate_only_requires_review','source_file':check['source_file'],'source_sha256':check['source_sha256'],'source_sheet':check['source_sheet'],'source_row_1based':check['source_row_1based'],'raw_label':check['raw_label'],'raw_cells':check['raw_cells'],'label_column_1based':check['label_column_1based'],'population_column_1based':check['population_column_1based'],'latitude':p['latitude'],'longitude':p['longitude'],'current_point_ledger':p['point_ledger_path'],'current_point_origin_file':p.get('point_origin_file',''),'current_point_origin_sha256':p.get('point_origin_sha256',''),'current_point_origin_locator':p.get('point_origin_locator',''),'source_population_values_modified':False,'source_district_field_modified':False,'population_boundary_comparability_asserted':False,**proof}
 candidates.append(candidate)
cf=pd.DataFrame(candidates)
if len(cf):
 ratios=[];flags=[]
 for a in candidates:
  vals=[a['population_2002'],a['population_2010_protected_unchanged'],a['population_2021']]
  ratio=max(vals)/min(vals) if all(pd.notna(v) for v in vals) and min(vals)>0 else None
  ratios.append(ratio);flags.append((ratio is not None and ratio>2) or (min(vals)==0 and max(vals)>0))
 cf['population_ratio_max_over_min_three_years']=ratios;cf['population_scope_review_flag']=flags
 cf['clean_core_for_simulation']=~cf.printed_type_variation_flag&~cf.historical_current_county_change_flag&~cf.population_scope_review_flag
 candidates=cf.to_dict('records')
# Simulate the flagged-core partition separately before the all-candidate union; restore graph exactly.
parent_snapshot=dict(s.uf.parent);rank_snapshot=dict(s.uf.rank) if hasattr(s.uf,'rank') else None;years_snapshot={k:set(v) for k,v in s.years.items()}
corepoints=[]
for a in candidates:
 if not a['clean_core_for_simulation']:continue
 sid,cur=a['target_2010_source_record_id'],a['2021_endpoint_source_record_id'];s.union(sid,cur)
 corepoints.extend(t for t in [sid,a['2002_endpoint_source_record_id']] if t not in s.point_rows)
core_metrics=s.metrics(extra_point_ids=corepoints)
s.uf.parent=parent_snapshot
if rank_snapshot is not None:s.uf.rank=rank_snapshot
s.years=years_snapshot
edges=[];pointuses=[]
for a in candidates:
 sid,cur=a['target_2010_source_record_id'],a['2021_endpoint_source_record_id'];s.union(sid,cur);edges.append({'from_source_record_id':sid,'to_source_record_id':cur,'relation':'same_place','decision_status':'candidate_only_requires_review','inferred_county_key':a['inferred_county_key']})
 donor=s.point_rows[cur]
 for tid in [sid,a['2002_endpoint_source_record_id']]:
  if tid not in s.point_rows:pointuses.append({'target_source_record_id':tid,'target_year':int(s.by_id.loc[tid,'census_year']),'latitude':donor['latitude'],'longitude':donor['longitude'],'coordinate_source_record_id':cur,'coordinate_admission_status':'candidate_only_requires_review','coordinate_origin_ledger':donor['point_ledger_path'],'coordinate_origin_ledger_sha256':sha(Path(donor['point_ledger_path'])),'coordinate_origin_ledger_locator':'target_source_record_id='+cur,'direct_historical_coordinate_measurement':False,'native_code_binding_asserted':False,'population_boundary_comparability_asserted':False})
after=s.metrics(extra_point_ids=[p['target_source_record_id'] for p in pointuses])
cf.to_csv(WORK/'candidates.csv',index=False);pd.DataFrame(edges).to_csv(WORK/'candidate_identity_edges.csv',index=False);pd.DataFrame(pointuses).to_csv(WORK/'candidate_point_uses.csv',index=False)
pd.DataFrame(held).sort_values('population',ascending=False).head(50).to_csv(OUT/'largest_ambiguity_holds.csv',index=False) if held else pd.DataFrame().to_csv(OUT/'largest_ambiguity_holds.csv',index=False)
# Fixed seed checks preserve physical witnesses for the two Altai Sibirsky alternatives even if no bracket exists.
for a in competitor[(competitor.n=='сибирский')&(competitor.r=='алтайский')].to_dict('records'):literal(a)
checks=pd.DataFrame([a for a in literal_checks.values() if a is not None]);checks.to_csv(WORK/'literal_source_checks.csv.gz',index=False,compression={'method':'gzip','mtime':0})
if len(cf):
 cf.sort_values('population_2010_protected_unchanged',ascending=False).head(5).to_csv(OUT/'top5_candidates.csv',index=False);cf.sample(min(15,len(cf)),random_state=20261007).to_csv(OUT/'fixed15_candidates.csv',index=False)
pd.DataFrame([{'source_record_id':sid,'inferred_county_key':county,**proofs[sid]} for sid,county in resolved.items()]).to_csv(WORK/'all_selected_competitor_county_context.csv.gz',index=False,compression={'method':'gzip','mtime':0})
receipt={'status':'candidate_only_no_admission','stage':'28_plus_frozen434_own_context_application','bounded_target_limit':5000,'targets':len(pool),'selected_competitor_rows':len(competitor),'source_groups':len(groups),'physical_books_opened':len(books),'literal_rows_checked':len(checks),'candidates':len(cf),'candidate_new_edges':len(edges),'candidate_new_point_uses':len(pointuses),'scope_flags':int(cf.population_scope_review_flag.sum()) if len(cf) else 0,'type_variation_flags':int(cf.printed_type_variation_flag.sum()) if len(cf) else 0,'county_change_flags':int(cf.historical_current_county_change_flag.sum()) if len(cf) else 0,'clean_core_candidates':int(cf.clean_core_for_simulation.sum()) if len(cf) else 0,'clean_core_simulation':core_metrics,'clean_core_marginal_population_gain':{y:core_metrics[y]['covered_population']-baseline[y]['covered_population'] for y in baseline},'screen_counts':dict(counts),'baseline':baseline,'simulation':after,'marginal_population_gain':{y:after[y]['covered_population']-baseline[y]['covered_population'] for y in baseline},'marginal_complete_rows':{y:after[y]['covered_rows']-baseline[y]['covered_rows'] for y in baseline},'inputs':{str(p):sha(p) for p in [*s.inputs,SEL,EVENT,Path(__file__)]},'raw_source_hashes':hashes,'outputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [*WORK.glob('*.csv'),*WORK.glob('*.csv.gz'),*OUT.glob('*.csv')]},'limitations':['No accepted input, protected population or source district field changed.','Source county context is inferred from two already accepted distinct-name 2010/current anchors in same physical XLS sheet/region, each within20 rows; raw labels and exact protected population cells inspected for every target/bracket.','Every selected same-name/region2010 alternative is county-assigned or explicitly unresolved before uniqueness; unresolved alternatives block.','Printed type variation and historical/current county changes flagged for review, not silently interpreted.','Current accepted points trusted; reuse in2010 is retrospective continuity, not independent historical measurement.']}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');(OUT/'README.md').write_text('# Selected secondary 2010 XLS county context\n\nBounded top5000 selected2010 orphans with existing accepted2002+2021 same-name/region pairs. Actual secondary source XLS labels/protected population cells and two distinct-name accepted neighbor anchors within20 physical rows support inferred county. Every selected2010 namesake is assigned or blocks uniqueness. Candidate-only: no protected values or admitted graph changed.\n')
print(json.dumps({k:receipt[k] for k in ['targets','selected_competitor_rows','physical_books_opened','candidates','candidate_new_point_uses','marginal_population_gain','marginal_complete_rows','screen_counts']},ensure_ascii=False))
