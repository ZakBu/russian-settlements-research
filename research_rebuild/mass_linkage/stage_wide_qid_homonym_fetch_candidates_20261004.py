#!/usr/bin/env python3
"""Bounded candidate inventory for missing current Wikidata entity history.

Uses current selected additive source records, an accepted current point from
any provider, exact current OKTMO/P764 and name-label matches in the frozen
Wikimedia TSV screen, and exact typed name/province old census source rows.
Outputs a ranked fetch request only; it asserts neither identity nor population.
"""
from __future__ import annotations
import hashlib,json,math,re,unicodedata
from collections import Counter
from pathlib import Path
import pandas as pd
import pyarrow.dataset as ds
from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF
from research_rebuild.mass_linkage.stage_legacy_temporal_20261004 import region_key
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES,ACCEPTED_PROJECTION_STATUSES,ACCEPTED_COORDINATE_STATUSES

W=Path('/workspace');BASE=W/'settlements-work/continuation_20261004';R4=BASE/'R4';OUT=R4/'wide_qid_homonym_full_entity_retrieval_20261004_v2'
F=W/'settlements-delivery/continuation-consolidated-20261003';SEL=F/'selected_observations.parquet';EVID=F/'source_evidence.parquet'
G=W/'settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected/accepted_identity_edges.parquet'
P=W/'settlements-work/continuation_20261004/accepted_mass_rule_corrections_origin_corrected/accepted_point_uses.parquet'
WIDE=W/'settlements-work/wikidata/wide_v5/wide_point_bindings.parquet';ENT=W/'settlements-work/wikidata/entities.parquet';HIST=BASE/'federal_and_history/wikidata_secondary_working_series.parquet'
CONFIG=W/'russian-settlements-research/config/mass_joint_20261004.json'
PHYSICAL={'город','пгт','поселок','деревня','село','хутор','станица','аул','кишлак','слобода','арбан','выселок','починок','местечко','разъезд','станция'}
COLS=['source_record_id','census_year','source_file','source_sheet','source_row','source_name_raw','settlement_name','settlement_type','type_norm','region_raw','district_raw','population','population_scope','is_additive_settlement_record','entity_grain_status','oktmo','source_locator','source_sha256']
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def norm(x):
 if x is None or pd.isna(x):return ''
 return ' '.join(unicodedata.normalize('NFKC',str(x)).casefold().replace('ё','е').replace('\xa0',' ').split())
def typ(x):
 s=norm(x).replace('.','').strip()
 return {'поселок сельского типа':'поселок','поселок городского типа':'пгт','пгт':'пгт','пос':'поселок','п':'поселок','дер':'деревня','д':'деревня','с':'село','х':'хутор','ст-ца':'станица','стца':'станица','г':'город','гор':'город'}.get(s,s)
def intpop(x):
 try:
  f=float(x)
  if math.isfinite(f) and f>=0 and f.is_integer():return int(f)
 except Exception:pass
 return None
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 cfg=json.loads(CONFIG.read_text());G=Path(cfg['working_identity_graph']);P=Path(cfg['working_point_uses']);pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SEL,EVID,G,P,WIDE,ENT,HIST,CONFIG]}
 if pins[str(G)]['sha256']!=cfg['working_identity_graph_sha256'] or pins[str(P)]['sha256']!=cfg['working_point_uses_sha256']:raise SystemExit('canonical graph/point pin mismatch')
 selected_all=pd.read_parquet(SEL,columns=COLS);selected_all.source_record_id=selected_all.source_record_id.astype(str);selected_all.census_year=selected_all.census_year.astype(int)
 selected_all['name_key']=selected_all.settlement_name.map(norm);selected_all['type_key']=selected_all.settlement_type.map(typ);selected_all['region_key']=selected_all.region_raw.map(region_key);selected_all['district_key']=selected_all.district_raw.map(norm);selected_all['pop_i']=selected_all.population.map(intpop)
 uf=YearUF(selected_all.source_record_id.tolist(),selected_all.census_year.tolist());years=dict(zip(selected_all.source_record_id,selected_all.census_year))
 sel=selected_all[selected_all.name_key.ne('')&selected_all.type_key.isin(PHYSICAL)&selected_all.region_key.ne('')&selected_all.is_additive_settlement_record.fillna(False)&selected_all.pop_i.notna()].copy()
 g=pd.read_parquet(G,columns=['decision_id','from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
 if not set(g.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES) or not set(g.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES) or not set(g.relation.astype(str)).issubset({'same_place','same_place_candidate'}):raise SystemExit('canonical graph guard failed')
 accepted_identity=g[g.relation.eq('same_place')]
 for e in accepted_identity.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  if a not in uf.idx or b not in uf.idx or years[a]!=int(e.from_year) or years[b]!=int(e.to_year):raise SystemExit('accepted edge endpoint/year mismatch')
  if uf.union_ids(a,b)=='year_constrained_collision':raise SystemExit('baseline same-year collision')
 point=pd.read_parquet(P,columns=['target_source_record_id','target_year','coordinate_admission_status'])
 point=point[point.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
 if point.target_source_record_id.astype(str).duplicated().any():raise SystemExit('duplicate accepted point target')
 point21=set(point[point.target_year==2021].target_source_record_id.astype(str))
 # Whole-year current uniqueness is assessed against all selected additive physical objects.
 selected2021=sel[sel.census_year==2021].copy();selected2021['key']=list(zip(selected2021.name_key,selected2021.type_key,selected2021.region_key))
 counts=selected2021.groupby('key').size().to_dict();selected2021['current_key_count']=[counts[k] for k in selected2021.key]
 # Frozen TSV/claim screen supplies QID candidates, exact 11-digit source P764,
 # and exact label. The screen is not an accepted Wikidata identity decision.
 wide=pd.read_parquet(WIDE,columns=['source_record_id','wikidata_qid','source_oktmo_exact_digits','source_oktmo_digit_width','wikidata_truthy_exact_p764_match','wikidata_name_exact_label','truthy_entity_competition_for_exact_oktmo','source_observation_competition_for_exact_oktmo','wikidata_truthy_p31_claims_json','wikidata_truthy_p625_claims_json','wikidata_tsv_ru_labels_json'])
 wide.source_record_id=wide.source_record_id.astype(str)
 current=selected2021.merge(wide,on='source_record_id',how='inner')
 current=current[current.source_record_id.isin(point21)&(current.current_key_count==1)&current.wikidata_truthy_exact_p764_match.fillna(False)&current.wikidata_name_exact_label.fillna(False)&~current.truthy_entity_competition_for_exact_oktmo.fillna(True)&~current.source_observation_competition_for_exact_oktmo.fillna(True)]
 current['native_code_digits']=current.oktmo.map(lambda x:re.sub(r'\D','',str(x)) if pd.notna(x) else '')
 current=current[(current.native_code_digits.str.len()==11)&current.source_oktmo_exact_digits.astype(str).eq(current.native_code_digits)]
 current=current[~current.population_scope.astype(str).str.casefold().isin({'federal_city_region','federal_city_aggregate','regional_total'})]
 current['uf_mask']=[int(uf.mask[uf.find(uf.idx[sid])]) for sid in current.source_record_id]
 current=current[current.uf_mask!=7].drop_duplicates('source_record_id')
 # Candidate old rows from both named years; no historical ordinal/source code
 # or P1082 value is used in this screening step.
 old=sel[sel.census_year.isin([2002,2010])].copy();old['key']=list(zip(old.name_key,old.type_key,old.region_key))
 kset=set(current.key);old=old[old.key.isin(kset)]
 groups={k:(g02,g10) for k,grp in old.groupby('key') for g02,g10 in [(grp[grp.census_year==2002],grp[grp.census_year==2010])] if len(g02) and len(g10)}
 entq=set(pd.read_parquet(ENT,columns=['wikidata_qid']).wikidata_qid.astype(str))
 hist=pd.read_parquet(HIST,columns=['qid','year_prefix','population_value_raw','rank_is_deprecated','date_ambiguous_hold'])
 hist=hist[hist.year_prefix.astype(str).isin(['2002','2010'])&(~hist.rank_is_deprecated.fillna(True))&(~hist.date_ambiguous_hold.fillna(True))]
 histcov=set(hist.qid.astype(str));histq02=set(hist[hist.year_prefix.astype(str)=='2002'].qid.astype(str));histq10=set(hist[hist.year_prefix.astype(str)=='2010'].qid.astype(str))
 rows=[];funnel=Counter()
 # For each candidate, retain all source-pair alternatives. A population-pair
 # signature is unique only when it points to one actual old 2002x2010 row pair.
 for r in current.itertuples(index=False):
  gr=groups.get(r.key)
  if gr is None:continue
  a,b=gr;comb=[];signature_counts=Counter()
  for x in a.itertuples(index=False):
   for y in b.itertuples(index=False):
    if x.pop_i is None or y.pop_i is None:continue
    key=(int(x.pop_i),int(y.pop_i));signature_counts[key]+=1
    roots=[];mask=int(r.uf_mask)
    for target,yr,bit in ((x.source_record_id,2002,1),(y.source_record_id,2010,2)):
     rt=uf.find(uf.idx[str(target)]);rc=uf.find(uf.idx[str(r.source_record_id)])
     if rt==rc:continue
     if uf.mask[rt]&mask:continue
     roots.append((str(target),yr))
    comb.append((x,y,key,roots))
  safe=[z for z in comb if z[3] and signature_counts[z[2]]==1]
  if not safe:continue
  # Keep the maximum source-population pair for ranking; the request CSV below
  # still contains every pair alternative for each selected QID.
  maxpair=max(safe,key=lambda z:(sum(z[2]),z[2]))
  x,y,v,targets=maxpair
  q=str(r.wikidata_qid)
  rows.append({'wikidata_qid':q,'target_source_record_id':str(r.source_record_id),'current_name':r.settlement_name,'current_type_raw':r.settlement_type,'current_region_raw':r.region_raw,'current_population':intpop(r.population),'current_scope':r.population_scope,'native_code_raw':r.oktmo,'native_code_digits':r.native_code_digits,'wikidata_tsv_code_digits':r.source_oktmo_exact_digits,'p31_claims_json':r.wikidata_truthy_p31_claims_json,'current_accepted_point_provider_unknown':True,'current_uf_year_mask':int(r.uf_mask),'selected_old_pair_source_population_2002':int(v[0]),'selected_old_pair_source_population_2010':int(v[1]),'selected_old_pair_gross_population':int(v[0]+v[1]),'selected_old_2002_source_record_id':str(x.source_record_id),'selected_old_2010_source_record_id':str(y.source_record_id),'selected_old_2002_locator':x.source_locator,'selected_old_2010_locator':y.source_locator,'selected_old_2002_sha256':x.source_sha256,'selected_old_2010_sha256':y.source_sha256,'source_pair_signature_unique_across_key':True,'qid_previously_entity_cached':q in entq,'qid_has_cached_p1082_2002':q in histq02,'qid_has_cached_p1082_2010':q in histq10,'qid_needs_new_full_entity_fetch':q not in entq,'alternative_pair_count':len(comb),'safe_unique_pair_count':len(safe),'best_pair_missing_targets_json':json.dumps(targets,ensure_ascii=False)})
  funnel['candidate_qids_with_unique_safe_pair']+=1
 # Rank distinct absent-cache QIDs by maximum source support; preserve a
 # 2,000-target request pool, with first fetch tranche 500.
 df=pd.DataFrame(rows).drop_duplicates('wikidata_qid')
 if len(df):
  df=df.sort_values(['selected_old_pair_gross_population','current_population','wikidata_qid'],ascending=[False,False,True]).reset_index(drop=True)
  df['fetch_rank']=range(1,len(df)+1)
 pool=df[(~df.qid_previously_entity_cached)&(~df.qid_has_cached_p1082_2002 | ~df.qid_has_cached_p1082_2010)].head(2000).copy()
 # Screen candidate source evidence for ranked 2k QIDs and their chosen historic rows.
 scanids=set(pool.target_source_record_id.astype(str))|set(pool.selected_old_2002_source_record_id.astype(str))|set(pool.selected_old_2010_source_record_id.astype(str))
 if scanids:
  tab=ds.dataset(EVID,format='parquet').to_table(columns=['source_record_id','source_evidence_json'],filter=ds.field('source_record_id').isin(scanids))
  ev={str(z['source_record_id']):json.loads(z['source_evidence_json']) for z in tab.to_pylist()}
 else:ev={}
 def hold(sid):
  e=ev.get(str(sid),{});reasons=[]
  if e.get('is_additive_settlement_record') is False:reasons.append('nonadditive')
  if str(e.get('population_scope') or '').casefold() in {'federal_city_region','federal_city_aggregate','regional_total'}:reasons.append('aggregate_scope')
  if str(e.get('entity_grain_status') or '').casefold() in {'aggregate','non_settlement','administrative_unit'}:reasons.append('wrong_grain')
  if e.get('legacy_verified_successor_settlement_id'):reasons.append('verified_event')
  if e.get('legacy_same_year_collision'):reasons.append('same_year_collision')
  if e.get('legacy_identity_conflict'):
   try:c=set(json.loads(e.get('legacy_identity_reasons') or '[]'))
   except Exception:c={'unparsed_conflict'}
   c-={'administrative_conflict','ordinal_historical_identifier_hypothesis'}
   if c:reasons.append('nonadministrative_identifier_conflict:'+','.join(sorted(c)))
  return reasons
 if len(pool):
  pool['source_evidence_holds_json']=pool.apply(lambda r:json.dumps([{'source_record_id':sid,'reasons':hold(sid)} for sid in [r.target_source_record_id,r.selected_old_2002_source_record_id,r.selected_old_2010_source_record_id] if hold(sid)],ensure_ascii=False),axis=1)
  pool['source_evidence_gate']=pool.source_evidence_holds_json.eq('[]')
  pool=pool[pool.source_evidence_gate].copy()
  pool['fetch_rank']=range(1,len(pool)+1)
 # Request payload preserves each requested QID; fetching is limited to first 500.
 fetch=pool.head(500).copy();fetch['request_batch']=((fetch.fetch_rank-1)//50)+1
 df.to_csv(OUT/'all_source_pair_candidate_qids.csv',index=False)
 pool.to_csv(OUT/'eligible_top2000_qid_review_pool.csv',index=False)
 fetch.to_csv(OUT/'entity_fetch_request_top500.csv',index=False)
 # All raw pair alternatives for requested QIDs, not only the one used to rank.
 chosen=set(fetch.wikidata_qid.astype(str));pairrows=[]
 for q in chosen:
  row=fetch[fetch.wikidata_qid.astype(str)==q].iloc[0];gr=groups.get(tuple(row[['current_name','current_type_raw','current_region_raw']]))
  # Use stored selected key reconstructed from current selected exact source ID.
  keyrow=selected2021[selected2021.source_record_id.astype(str)==str(row.target_source_record_id)]
  if keyrow.empty:continue
  key=keyrow.iloc[0].key;gr=groups.get(key)
  if gr is None:continue
  a,b=gr
  for x in a.itertuples(index=False):
   for y in b.itertuples(index=False):
    pairrows.append({'wikidata_qid':q,'target_source_record_id':row.target_source_record_id,'old_2002_source_record_id':x.source_record_id,'old_2002_file':x.source_file,'old_2002_sheet':x.source_sheet,'old_2002_row':x.source_row,'old_2002_locator':x.source_locator,'old_2002_sha256':x.source_sha256,'old_2002_name_raw':x.source_name_raw,'old_2002_type_raw':x.settlement_type,'old_2002_region_raw':x.region_raw,'old_2002_district_raw':x.district_raw,'old_2002_population':x.pop_i,'old_2010_source_record_id':y.source_record_id,'old_2010_file':y.source_file,'old_2010_sheet':y.source_sheet,'old_2010_row':y.source_row,'old_2010_locator':y.source_locator,'old_2010_sha256':y.source_sha256,'old_2010_name_raw':y.source_name_raw,'old_2010_type_raw':y.settlement_type,'old_2010_region_raw':y.region_raw,'old_2010_district_raw':y.district_raw,'old_2010_population':y.pop_i})
 pd.DataFrame(pairrows).to_csv(OUT/'top500_all_old_source_pair_alternatives.csv',index=False)
 summary={'status':'source_pair_and_QID_fetch_candidates_only_no_identity_or_population_admissions','baseline_graph_sha256':pins[str(G)]['sha256'],'baseline_point_uses_sha256':pins[str(P)]['sha256'],'selected_sha256':pins[str(SEL)]['sha256'],'wide_tsv_sha256':pins[str(WIDE)]['sha256'],'current_qid_rule':'Current target is a selected additive physical 2021 source row with a canonical accepted point from any provider, whole-2021 uniqueness for exact name/type/province, exact 11-digit source OKTMO = frozen TSV exact P764, exact QID label, no competing QID for the code, and no competing selected source observation for the code. The old 2002 and 2010 rows use exact normalized name/type/province; all row-pair alternatives are retained. A pair is ranked only if its two source population values are unique among those alternatives and at least one endpoint can join the current year mask without a same-year collision. No population value or identity is inferred from these screens. Fetch pool excludes QIDs already in the current full entity cache and holds source aggregate/event/collision/nonadministrative conflict flags. Relations recorded as same_place_candidate are not unioned into the identity baseline.','same_place_candidate_relation_rows_not_unionable':int(g.relation.eq('same_place_candidate').sum()),'screen_counts':{'wide_exact_P764_label_point_target_current_keys':int(len(df)),'rank_pool_after_entitycache_and_scope_evidence_holds':int(len(pool)),'fetch_request_top500':int(len(fetch)),'fetch_batches_of_50':int(fetch.request_batch.nunique()) if len(fetch) else 0,'pair_alternative_rows_for_fetch_top500':len(pairrows),'entity_cached_before_fetch_qids_in_screen':int(df.qid_previously_entity_cached.sum()) if len(df) else 0,'QIDs_in_screen_with_cached_2002_P1082':int(df.qid_has_cached_p1082_2002.sum()) if len(df) else 0,'QIDs_in_screen_with_cached_2010_P1082':int(df.qid_has_cached_p1082_2010.sum()) if len(df) else 0,'current_exact_binding_targets_not_fully_connected':int(len(current))},'inputs':pins}
 summary['outputs']={x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in sorted(OUT.iterdir()) if x.is_file()}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 (OUT/'receipt.json').write_text(json.dumps({'status':summary['status'],'input_sha256':{k:v['sha256'] for k,v in pins.items()},'output_sha256':{x.name:sha(x) for x in sorted(OUT.iterdir()) if x.is_file() and x.name!='receipt.json'},'script':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__))},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
