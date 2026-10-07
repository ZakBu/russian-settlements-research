from pathlib import Path
import sys,json,re,hashlib,bisect,collections
import pandas as pd
import xlrd
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize
from apply_unique_county_name_bridge_20261007 import county_key
s=load(stage=7)
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pos(sid):
 try:
  _,fn,sh,n=sid.split(':',3)
  return fn,sh,int(n)
 except:return None
pairs=[];missing_county_pairs=[]; anchors=collections.defaultdict(list);selectedpos={};selectednames=collections.defaultdict(list)
for row in s.obs[s.obs.census_year.eq(2010)].itertuples():
 p=pos(row.source_record_id)
 if p:selectedpos[p]=row.source_record_id
 selectednames[(row.region_norm,normalize(row.settlement_name))].append(row.source_record_id)
groups=collections.defaultdict(list)
for row in s.obs.itertuples():groups[row.root].append(row)
for root,g in groups.items():
 ys=s.years[s.uf.find(g[0].source_record_id)]
 if ys=={2002,2021}:
  old=next(r for r in g if r.census_year==2002);cur=next(r for r in g if r.census_year==2021)
  ck=county_key(old.district_raw)
  if ck and ck==county_key(cur.district_raw) and normalize(old.settlement_name)==normalize(cur.settlement_name) and old.region_norm==cur.region_norm and old.is_additive_settlement_record and cur.is_additive_settlement_record:
   pairs.append({'old_id':old.source_record_id,'current_id':cur.source_record_id,'name_key':normalize(cur.settlement_name),'name':cur.settlement_name,'region':cur.region_norm,'county':ck,'population_2002':old.population,'population_2021':cur.population})
  if not ck and county_key(cur.district_raw) and normalize(old.settlement_name)==normalize(cur.settlement_name) and old.region_norm==cur.region_norm and old.is_additive_settlement_record and cur.is_additive_settlement_record:
   missing_county_pairs.append({'old_id':old.source_record_id,'current_id':cur.source_record_id,'name_key':normalize(cur.settlement_name),'name':cur.settlement_name,'region':cur.region_norm,'county':county_key(cur.district_raw),'population_2002':old.population,'population_2021':cur.population})
 if 2010 in ys and 2021 in ys:
  ten=next(r for r in g if r.census_year==2010);cur=next(r for r in g if r.census_year==2021);p=pos(ten.source_record_id);ck=county_key(cur.district_raw)
  if p and ck and ten.region_norm==cur.region_norm:
   anchors[(p[0],p[1])].append({'n':p[2],'id':ten.source_record_id,'current_id':cur.source_record_id,'county':ck,'region':cur.region_norm,'name':normalize(ten.settlement_name)})
alias_counties={}
for group in groups.values():
 counties={county_key(r.district_raw) for r in group if r.census_year in (2002,2021) and county_key(r.district_raw)}
 for r in group:
  if r.census_year==2010:
   own=county_key(r.district_raw)
   alias_counties[r.source_record_id]=own or (next(iter(counties)) if len(counties)==1 else '')
# Bounded top100 recovery of an explicitly printed2002 county absent in selected metadata.
county_replays=[];oldbooks={}
for pair in sorted(missing_county_pairs,key=lambda r:-r['population_2021'])[:100]:
 position=pos(pair['old_id'])
 if not position:continue
 fn,sheet,n=position;path=Path('/workspace/settlements-raw/data/raw/2002')/fn
 if not path.is_file():continue
 if path not in oldbooks:oldbooks[path]=xlrd.open_workbook(path,on_demand=True)
 try:tab=oldbooks[path].sheet_by_name(sheet)
 except Exception:continue
 if n>tab.nrows:continue
 for j in range(n-2,max(-1,n-502),-1):
  cells=tab.row_values(j);labels=[normalize(v) for v in cells if isinstance(v,str) and v.strip()]
  header=next((v for v in labels if ('район' in v and ('население' in v or v.endswith('район'))) or re.search(r' - все (?:сельское|население)',v)),None)
  if header is None:continue
  parsed=county_key(header.split(' - ')[0])
  replay={'old_id':pair['old_id'],'current_id':pair['current_id'],'source_path':str(path),'source_sha256':sha(path),'header_row_1based':j+1,'raw_header':header,'parsed_county':parsed,'current_county':pair['county'],'accepted_context_candidate':parsed==pair['county'],'all_header_raw_cells_json':json.dumps(cells,ensure_ascii=False)}
  county_replays.append(replay)
  if parsed==pair['county']:
   pair['county_provenance']='raw2002printedhierarchy';pair['county_source_locator']=str(path)+'#'+sheet+':row_1based='+str(j+1);pairs.append(pair)
  break
for pair in missing_county_pairs:
 if any(r['old_id']==pair['old_id'] for r in pairs):continue
 old=s.by_id.loc[pair['old_id']]
 if normalize(old.settlement_type) in {'город','пгт'} and '1_TOM_01_04.xls' in pair['old_id']:
  rivals=s.obs[s.obs.census_year.eq(2002)&s.obs.region_norm.eq(pair['region'])&s.obs.name_norm.eq(pair['name_key'])&s.obs.type_norm.isin(['город','пгт'])]
  if len(rivals)==1:
   pair['county_provenance']='old_official_unique_typed_urban_region_name_current_county_only_context_not_native2002';pairs.append(pair)
pd.DataFrame(missing_county_pairs).to_csv(OUT/'missing_old_county_pair_probe.csv',index=False)
for book in oldbooks.values():book.release_resources()
pd.DataFrame(county_replays).to_csv(OUT/'top100_missing_old_county_printed_hierarchy_replay.csv',index=False)
counts=collections.Counter((r['region'],r['county'],r['name_key']) for r in pairs)
pairs=[r for r in pairs if counts[(r['region'],r['county'],r['name_key'])]==1]
lookup=collections.defaultdict(list)
for r in pairs:
 old=s.by_id.loc[r['old_id']];cur=s.by_id.loc[r['current_id']];point=s.point_rows.get(r['current_id'],{})
 r.update(old_settlement_type=old.settlement_type,current_settlement_type=cur.settlement_type,auxiliary2010_type_inference='Historical/current typed endpoints; raw2010 name-cell omits recognized type prefix, no rawvalue rewritten',old_population_quality=old.population_value_quality,current_population_quality=cur.population_value_quality,old_source_locator=old.source_locator,current_source_locator=cur.source_locator,old_source_sha256=old.source_sha256,current_source_sha256=cur.source_sha256,current_accepted_point_latitude=point.get('latitude'),current_accepted_point_longitude=point.get('longitude'),current_point_origin_file=point.get('point_origin_file'),current_point_origin_sha256=point.get('point_origin_sha256'),current_point_origin_locator=point.get('point_origin_locator'))
 lookup[r['name_key']].append(r)
for key in anchors:anchors[key].sort(key=lambda r:r['n'])
rawdir=Path('/workspace/settlements-raw/data/raw/2010');manifest=[];hits=[];sourceprofiles=[]
for path in sorted(rawdir.glob('*.xls')):
 if not re.match(r'^\d{3}_',path.name) or int(path.name[:3])>18:continue
 print('scan',path.name,flush=True)
 manifest.append({'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size})
 book=xlrd.open_workbook(path,on_demand=True)
 for sheetname in book.sheet_names():
  sh=book.sheet_by_name(sheetname);aa=anchors.get((path.name,sheetname),[]);nums=[r['n'] for r in aa]
  # Infer name/pop columns from exact accepted2010 source-row replay, not a global hard-coded profile.
  profiles=collections.Counter()
  for anchor in aa:
   if not 1<=anchor['n']<=sh.nrows:continue
   vals=sh.row_values(anchor['n']-1)
   for j,v in enumerate(vals):
    z=normalize(v)
    if z==anchor['name'] or z.endswith(' '+anchor['name']):
     if j+1<len(vals) and isinstance(vals[j+1],(float,int)):profiles[(j,j+1)]+=1
  profile=profiles.most_common(1)[0][0] if profiles else (5,6)
  sourceprofiles.append({'file':path.name,'sheet':sheetname,'columns_0based':profile,'accepted_anchor_support':sum(profiles.values()),'rows':sh.nrows})
  nc,pc=profile
  for i in range(sh.nrows):
   vals=sh.row_values(i)
   if nc>=len(vals):continue
   z=normalize(vals[nc])
   if z not in lookup:continue
   n=i+1;p=(path.name,sheetname,n);existing=selectedpos.get(p,'')
   ix=bisect.bisect_left(nums,n);lower=aa[ix-1] if ix else None;upper=aa[ix] if ix<len(aa) else None
   if upper and upper['n']==n:upper=aa[ix+1] if ix+1<len(aa) else None
   for pair in lookup[z]:
    good=bool(lower and upper and lower['county']==upper['county']==pair['county'] and lower['region']==upper['region']==pair['region'] and lower['name']!=upper['name'] and 0<n-lower['n']<=20 and 0<upper['n']-n<=20)
    forward=[r for r in aa if n<r['n']<=n+20][:2]
    boundary=bool(pair.get('county_provenance')=='raw2002printedhierarchy' and len(forward)==2 and len({r['name'] for r in forward})==2 and all(r['county']==pair['county'] and r['region']==pair['region'] for r in forward))
    # Weak scan hits remain clearly separated from eligible context candidates.
    if not good and len(lookup[z])>1:continue
    admin_terms=any(re.search(r'все население|все сельское|городское население|сельское население|итого|район|сельсовет|администраци',normalize(v)) for v in vals[:max(nc+1,7)] if isinstance(v,str))
    value=vals[pc] if pc<len(vals) else None
    population=None
    if isinstance(value,(int,float)) and value>=0 and float(value).is_integer():population=int(value)
    elif isinstance(value,str) and re.fullmatch(r'\d+',value.strip()):population=int(value.strip())
    aliases=selectednames.get((pair['region'],pair['name_key']),[])
    alias_review=[{'source_record_id':sid,'independently_supported_county':alias_counties.get(sid,''),'blocks':not alias_counties.get(sid,'') or alias_counties[sid]==pair['county']} for sid in aliases]
    blocking_aliases=[r for r in alias_review if r['blocks']]
    hits.append({**pair,'raw_source_record_id':'2010:'+path.name+':'+sheetname+':'+str(n),'raw_file':str(path),'source_sha256':manifest[-1]['sha256'],'raw_sheet':sheetname,'row_1based':n,'name_column_1based':nc+1,'population_column_1based':pc+1,'raw_name':vals[nc],'population_2010_as_printed':population,'population_raw':value,'selected_same_physical_row_id':existing,'all_selected_2010_exact_name_region_alias_ids':json.dumps(aliases,ensure_ascii=False),'selected2010_alias_county_review_json':json.dumps(alias_review,ensure_ascii=False),'raw_type_prefix_absent':True,'raw_admin_total_heading_detected':admin_terms,'two_accepted_county_anchors_within20':good,'two_following_county_anchors_boundary_context':boundary,'following_anchor_evidence_json':json.dumps(forward,ensure_ascii=False),'lower_anchor':json.dumps(lower,ensure_ascii=False),'upper_anchor':json.dumps(upper,ensure_ascii=False),'candidate_status':'eligible_auxiliary_observation_candidate_only' if good and not existing and not blocking_aliases and population is not None and not admin_terms else ('boundary_context_auxiliary_candidate_only' if boundary and not existing and not blocking_aliases and population is not None and not admin_terms else 'held_scan_hit'),'protected_secondary_source_precision':True,'selected2010_population_credit_allowed':False,'national_selected_not_modified':True,'all_raw_cells_json':json.dumps(vals,ensure_ascii=False)})
 book.release_resources()
 pd.DataFrame(hits).to_csv(OUT/'raw_untyped_scan_hits.csv',index=False)
eligible=[r for r in hits if r['candidate_status']=='eligible_auxiliary_observation_candidate_only']
# One raw row or target pair with competitors stays held.
rowc=collections.Counter(r['raw_source_record_id'] for r in eligible);pairc=collections.Counter(r['current_id'] for r in eligible)
eligible=[r for r in eligible if rowc[r['raw_source_record_id']]==1 and pairc[r['current_id']]==1]
boundary_candidates=[r for r in hits if r['candidate_status']=='boundary_context_auxiliary_candidate_only']
pd.DataFrame(boundary_candidates).to_csv(OUT/'boundary_context_auxiliary_candidates.csv',index=False)
cols=list(hits[0]) if hits else ['candidate_status']
pd.DataFrame(eligible,columns=cols).to_csv(OUT/'eligible_auxiliary_observation_candidates.csv',index=False)
pd.DataFrame(pairs).sort_values('population_2021',ascending=False).to_csv(OUT/'all_exact_county_two_year_residual_pairs.csv',index=False)
(OUT/'input_manifest.json').write_text(json.dumps({'stage':7,'graph_inputs':[{'path':str(p),'sha256':sha(p)} for p in s.inputs],'raw_inputs':manifest,'baseline_metrics':s.metrics()},indent=2))
(OUT/'source_column_profiles.json').write_text(json.dumps(sourceprofiles,ensure_ascii=False,indent=2))
summary={'stage':7,'missing_old_county_pairs_total':len(missing_county_pairs),'missing_old_county_top100_attempted':min(100,len(missing_county_pairs)),'top100_printed_county_replays_found':len(county_replays),'printed_old_county_recovered':sum(r['accepted_context_candidate'] for r in county_replays),'scanned_pairs_total':len(pairs),'old_unique_official_urban_region_without_nativecounty_pairs':sum(r.get('county_provenance','').startswith('old_official') for r in pairs),'eligible_missing2010_pairs_explicitcounty':sum(not r.get('county_provenance','').startswith('old_official') for r in pairs),'raw_workbooks_scanned':len(manifest),'raw_exact_bare_name_hits':len(hits),'eligible_unique_context_auxiliary_candidates':len(eligible),'potential_current2021_population':sum(r['population_2021'] for r in eligible),'potential_old2002_population':sum(r['population_2002'] for r in eligible),'genuine_printed2010_population_not_admitted':sum(r['population_2010_as_printed'] for r in eligible),'held_same_selected_physicalrow':sum(bool(r['selected_same_physical_row_id']) for r in hits),'held_selected2010_name_region_alias':sum(bool(json.loads(r['all_selected_2010_exact_name_region_alias_ids'])) for r in hits),'boundary_context_candidates':len(boundary_candidates),'boundary_context_current2021_population':sum(r['population_2021'] for r in boundary_candidates),'population_credit_admitted':0,'identity_edges_admitted':0,'interpretation':'Candidate-only raw untyped observations. Name+population never identity proof; eligible requires two distinct accepted same-county anchors <=20 rows each and no same selected row or unresolved/samecounty selectedalias; independently supported othercounty homonyms do not block. Bare admin totals excluded by source anchor sequence only provisionally; independent row/hierarchy review still required. Missing population remains null.'}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False))
