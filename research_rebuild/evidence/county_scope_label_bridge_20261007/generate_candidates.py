"""Candidate-only literal county-caption cleanup; legacy normalizer unchanged."""
import sys,re,json
from pathlib import Path
from collections import defaultdict,Counter
from itertools import combinations
import pandas as pd,duckdb
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=ROOT/'research_rebuild/evidence/county_scope_label_bridge_20261007';WORK=Path('/workspace/settlements-work/county_scope_label_bridge_20261007')
SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
def county_key_v2(value):
 text=normalize(value)
 text=re.sub(r'\s*[-–—]\s*(?:сельское|городское)\s+население\s*[.;:]?\s*$','',text)
 text=re.sub(r'\bмуниципальное\s+образование\b',' ',text)
 return county_key(text)
s=load(14);before=s.metrics();assert [before[str(y)]['covered_population'] for y in (2002,2010,2021)]==[126150476,123382596,123960048]
c=duckdb.connect(config={'threads':1,'memory_limit':'600MB'});meta=c.execute('SELECT source_record_id,source_sheet,source_row,source_name_raw,entity_grain_status,source_raw_line FROM read_parquet(?)',[str(SEL)]).fetchdf();f=s.obs.merge(meta,on='source_record_id',validate='one_to_one');f['legacy_county']=f.district_raw.map(county_key);f['v2_county']=f.district_raw.map(county_key_v2);f['county_key_changed']=f.legacy_county.ne(f.v2_county);f['n']=f.name_norm.map(normalize);f['r']=f.region_norm.map(normalize)
f['whole']=f.is_additive_settlement_record.fillna(False)&~f.region_norm.isin(['москва','санкт петербург','севастополь'])&~f.settlement_name.fillna('').str.contains(r'\(часть|\bитого\b|\bвсего\b',case=False,regex=True)&~f.settlement_type.map(normalize).str.contains('объект',regex=False)&~f.entity_grain_status.map(normalize).str.contains('aggregate|municipal|unresolved|control_total',regex=True)
f=f[~((f.census_year==2021)&f.region_norm.eq('крым'))].copy();changed=f[f.county_key_changed].copy();changed['full_three_with_point']=[s.years[s.uf.find(a)]=={2002,2010,2021} and a in s.point_rows for a in changed.source_record_id]
affected={str(int(y)):{'rows':len(d),'population':int(d.population.sum()),'whole_rows':int(d.whole.sum()),'whole_population':int(d.loc[d.whole,'population'].sum()),'residual_whole_rows':int((d.whole&~d.full_three_with_point).sum()),'residual_whole_population':int(d.loc[d.whole&~d.full_three_with_point,'population'].sum())} for y,d in changed.groupby('census_year')}
changed[['source_record_id','census_year','settlement_name','settlement_type','region_norm','district_raw','legacy_county','v2_county','population','whole','full_three_with_point','source_file','source_sha256','source_locator']].to_csv(WORK/'affected_rows.csv.gz',index=False,compression={'method':'gzip','mtime':0})
changed[['census_year','district_raw','legacy_county','v2_county']].drop_duplicates().to_csv(OUT/'literal_county_key_changes.csv',index=False)
changedkeys=set(zip(changed.n,changed.r,changed.v2_county));allf=f[f.whole&f.n.ne('')&f.v2_county.ne('')].copy();allkey=defaultdict(list)
for a in f[f.whole&f.n.ne('')].to_dict('records'):allkey[(a['n'],a['r'])].append(a)
# Already accepted cross-year components can disambiguate a county-null competitor without creating a new county claim.
rootcounty={}
for root,g in allf.groupby('root'):
 modern=g[g.census_year.eq(2021)]
 if len(modern)==1 and modern.iloc[0].v2_county:rootcounty[root]=modern.iloc[0].v2_county
EVENT=ROOT/'research_rebuild/evidence/event_aware_path_union_20261005/accepted_event_path_selected_rows.csv';eventids=set(pd.read_csv(EVENT,dtype=str).source_record_id)
occupied=defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
counts=Counter();edges=[];points=[];candidates=[];holds=[];seenkeys=[];touched=set();extra_points=set();ledgerhash={}
for key,g in allf.groupby(['n','r','v2_county']):
 if key not in changedkeys:continue
 rows=g.sort_values('census_year').to_dict('records')
 if len(set(a['census_year'] for a in rows))<2:counts['no_cross_year_same_key']+=1;continue
 reasons=[]
 if len({a['census_year'] for a in rows})!=len(rows):reasons.append('multiple_selected_same_name_county_year')
 # Every selected same-name/region/year alternative with unknown source county is a hold unless accepted current context excludes it.
 years={int(a['census_year']) for a in rows}
 unknown=[q for q in allkey[(key[0],key[1])] if int(q['census_year']) in years and not q['v2_county'] and rootcounty.get(s.uf.find(q['source_record_id']),'') in ['',key[2]]]
 if unknown:reasons.append('unresolved_selected_county_null_competitor')
 if any(a['source_record_id'] in eventids for a in rows):reasons.append('known_event_scoped_population_endpoint')
 roots={s.uf.find(a['source_record_id']) for a in rows}
 if len(roots)==1:counts['already_accepted_same_place_component']+=1;continue
 if len({a['legacy_county'] for a in rows})==1:counts['no_new_county_label_equivalence']+=1;continue
 if any(root in touched for root in roots):reasons.append('overlapping_candidate_component')
 unionyears=[]
 for root in roots:unionyears.extend(s.years[root])
 if len(unionyears)!=len(set(unionyears)):reasons.append('repeated_census_year_component_conflict')
 members=s.obs[s.obs.source_record_id.map(s.uf.find).isin(roots)]
 pointmembers=[(a,s.point_rows[a]) for a in members.source_record_id if a in s.point_rows]
 if not pointmembers:reasons.append('no_trusted_accepted_point_anchor')
 if any(a in s.conflicting_point_targets for a in members.source_record_id):reasons.append('accepted_point_alternatives_conflict')
 donor=None
 if pointmembers:
  pointmembers.sort(key=lambda x:(-int(s.by_id.loc[x[0],'census_year']),x[0]));donorsid,donor=pointmembers[0]
  if any(distance_km((p['latitude'],p['longitude']),(donor['latitude'],donor['longitude']))>5 for _,p in pointmembers):reasons.append('accepted_component_points_contradict_over_5km')
  for sid in members.source_record_id:
   if sid in s.point_rows:continue
   if occupied.get((int(s.by_id.loc[sid,'census_year']),donor['latitude'],donor['longitude']),set())-{sid}:reasons.append('point_occupied_by_distinct_same_year_record')
 if reasons:
  counts.update(set(reasons));holds.append({'name_norm':key[0],'region_norm':key[1],'v2_county':key[2],'source_record_ids':' | '.join(a['source_record_id'] for a in rows),'source_populations_by_year':json.dumps([{'source_record_id':a['source_record_id'],'year':int(a['census_year']),'population':a['population'],'type':a['settlement_type']} for a in rows],ensure_ascii=False),'reasons':';'.join(sorted(set(reasons)))});continue
 groupid=f'county-caption-{len(candidates)+1:04d}';anchor=next((a for a in rows if a['source_record_id']==donorsid),rows[-1])
 for a in rows:
  sid=a['source_record_id'];candidate={'candidate_group_id':groupid,'source_record_id':sid,'census_year':int(a['census_year']),'settlement_name':a['settlement_name'],'settlement_type':a['settlement_type'],'region_norm':a['r'],'population':a['population'],'district_raw':a['district_raw'],'legacy_county_key':a['legacy_county'],'v2_county_key':a['v2_county'],'county_key_changed':a['county_key_changed'],'printed_type_variation_flag':len({normalize(x['settlement_type']) for x in rows})>1,'source_file':a['source_file'],'source_sha256':a['source_sha256'],'source_locator':a['source_locator'],'source_sheet':a['source_sheet'],'source_row':a['source_row'],'source_name_raw':a['source_name_raw'],'source_raw_line':a['source_raw_line'],'donor_source_record_id':donorsid,'donor_year':int(s.by_id.loc[donorsid,'census_year']),'latitude':donor['latitude'],'longitude':donor['longitude'],'point_origin_file':donor.get('point_origin_file',''),'point_origin_sha256':donor.get('point_origin_sha256',''),'point_origin_locator':donor.get('point_origin_locator',''),'point_ledger':donor['point_ledger_path'],'candidate_status':'candidate_only_requires_review','source_population_values_modified':False,'source_county_field_modified':False,'historical_county_rename_inferred':False,'population_boundary_comparability_asserted':False};candidates.append(candidate)
  if s.uf.find(sid)!=s.uf.find(anchor['source_record_id']):
   s.union(sid,anchor['source_record_id']);edges.append({'candidate_group_id':groupid,'from_source_record_id':sid,'to_source_record_id':anchor['source_record_id'],'relation':'same_place','decision_status':'candidate_only_requires_review','admission_rule':'literal_parent_population_caption_or_municipal_formation_qualifier_cleanup_unique_whole_np_name_county'})
 ledger=Path(donor['point_ledger_path']);ledgerhash.setdefault(str(ledger),sha(ledger))
 for sid in members.source_record_id:
  if sid in s.point_rows:continue
  point={'candidate_group_id':groupid,'target_source_record_id':sid,'target_year':int(s.by_id.loc[sid,'census_year']),'latitude':donor['latitude'],'longitude':donor['longitude'],'coordinate_source_record_id':donorsid,'coordinate_admission_status':'candidate_only_requires_review','coordinate_origin_ledger':str(ledger),'coordinate_origin_ledger_sha256':ledgerhash[str(ledger)],'coordinate_origin_ledger_locator':'target_source_record_id='+donorsid,'direct_historical_coordinate_measurement':False,'source_population_values_modified':False,'population_boundary_comparability_asserted':False};points.append(point);extra_points.add(sid);occupied[(point['target_year'],point['latitude'],point['longitude'])].add(sid)
 touched.add(s.uf.find(anchor['source_record_id']))
cf=pd.DataFrame(candidates);ef=pd.DataFrame(edges);pf=pd.DataFrame(points);after=s.metrics(extra_point_ids=extra_points)
if cf.empty:cf=pd.DataFrame(columns=['candidate_group_id','source_record_id','census_year','settlement_name','region_norm','population','district_raw','legacy_county_key','v2_county_key','candidate_status'])
if ef.empty:ef=pd.DataFrame(columns=['candidate_group_id','from_source_record_id','to_source_record_id','relation','decision_status','admission_rule'])
if pf.empty:pf=pd.DataFrame(columns=['candidate_group_id','target_source_record_id','target_year','latitude','longitude','coordinate_source_record_id','coordinate_admission_status'])
cf.to_csv(WORK/'candidate_rows.csv.gz',index=False,compression={'method':'gzip','mtime':0});ef.to_csv(WORK/'candidate_identity_edges.csv',index=False);pf.to_csv(WORK/'candidate_point_uses.csv',index=False);pd.DataFrame(holds).to_csv(WORK/'held_groups.csv.gz',index=False,compression={'method':'gzip','mtime':0})
if len(cf):
 summary=cf.groupby('candidate_group_id').agg(name=('settlement_name','first'),population_sum=('population','sum')).sort_values('population_sum',ascending=False);topids=summary.head(5).index;fixedids=summary.sample(min(10,len(summary)),random_state=20261007).index
 cf[cf.candidate_group_id.isin(topids)].to_csv(OUT/'top5_group_source_candidates.csv',index=False);cf[cf.candidate_group_id.isin(fixedids)].to_csv(OUT/'fixed10_group_source_candidates.csv',index=False)
receipt={'status':'candidate_only_no_admission','stage':14,'wrapper_rule':'Remove only a literal trailing dash plus сельское/городское население and exact municipal-formation qualifier муниципальное образование; geographic words retained. Legacy county_key immutable.','affected_rows':affected,'candidate_groups':int(cf.candidate_group_id.nunique()) if len(cf) else 0,'candidate_rows':len(cf),'candidate_edges':len(ef),'candidate_point_uses':len(pf),'screen_counts':dict(counts),'baseline':before,'simulation':after,'marginal_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'marginal_full_three_rows':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'inputs_sha256':{str(p):sha(p) for p in [*s.inputs,SEL,EVENT,Path(__file__)]},'donor_ledger_sha256':ledgerhash,'outputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [*WORK.glob('*.csv'),*WORK.glob('*.csv.gz'),*OUT.glob('*.csv')]},'limitations':['County cleanup concerns source parent labels only; no historical county rename or census population scope equality inferred.','Candidate groups require exact name/region/county-key uniqueness, actual whole selected rows, disjoint census-year components, trusted accepted point anchors and no contradictory accepted points or same-year point reuse.','Unknown-county selected namesakes block unless existing accepted identity context independently excludes their current county.','Coordinates transferred only as retrospective representative points; no census-date measurement or population allocation asserted.']}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');(OUT/'README.md').write_text('# Literal county scope captions (candidate only)\n\nLocal v2 wrapper removes a trailing population-subtotal caption and the exact municipal-formation qualifier. Legacy county normalization and accepted inputs remain unchanged. Only newly equivalent county keys may produce candidates. See affected rows, graph-union simulation, source samples and held groups.\n')
print(json.dumps({k:receipt[k] for k in ['affected_rows','candidate_groups','candidate_rows','candidate_edges','candidate_point_uses','marginal_population_gain','marginal_full_three_rows','screen_counts']},ensure_ascii=False))
