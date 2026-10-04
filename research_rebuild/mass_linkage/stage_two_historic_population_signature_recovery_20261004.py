#!/usr/bin/env python3
"""Candidate-only two-date Wikidata population-signature recovery.

This explores exact two-year P1082 population agreement as independent
corroboration for source pairs that are already linked by the accepted graph.
It does not admit identity, points, or population values.
"""
from __future__ import annotations
import hashlib, json, math, re, unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF, metrics, truth, write_csv
from research_rebuild.mass_linkage.stage_legacy_temporal_20261004 import region_key
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES, ACCEPTED_PROJECTION_STATUSES

W=Path('/workspace'); BASE=W/'settlements-work/continuation_20261004'; R4=BASE/'R4'
OUT=R4/'two_historic_population_signature_recovery_20261004_v4'
F=W/'settlements-delivery/continuation-consolidated-20261003'
SEL=F/'selected_observations.parquet'; EVID=F/'source_evidence.parquet'
HIST=BASE/'federal_and_history/wikidata_secondary_working_series.parquet'
CLAIMS=W/'settlements-work/wikidata/claims.parquet'; ENT=W/'settlements-work/wikidata/entities.parquet'
PB=W/'settlements-work/wikidata/point_bindings.parquet'
CONFIG=W/'russian-settlements-research/config/mass_joint_20261004.json'

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def norm(v):
 if v is None or pd.isna(v): return ''
 return ' '.join(unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е').replace('\xa0',' ').split())

def typ(v):
 s=norm(v).replace('.','').strip()
 return {'поселок сельского типа':'поселок','посёлок сельского типа':'поселок','поселок городского типа':'пгт','посёлок городского типа':'пгт','пгт':'пгт','пос':'поселок','п':'поселок','дер':'деревня','д':'деревня','с':'село','х':'хутор','ст-ца':'станица','стца':'станица','г':'город','гор':'город'}.get(s,s)

def district(v):
 s=norm(v)
 s=re.sub(r'^(городской округ|муниципальный округ|муниципальный район|городской район|район)\s+','',s)
 s=re.sub(r'\s+(муниципальный район|муниципальный округ|городской округ|район|округ)$','',s)
 return s.strip()

def raw_p1082(row):
 """Check that cached raw claim really has a single year precision P1082/P585 statement."""
 try: d=json.loads(row.raw_statement_json)
 except Exception:return False
 if d.get('rank')=='deprecated' or d.get('mainsnak',{}).get('property')!='P1082': return False
 qualifiers=d.get('qualifiers',{}).get('P585',[])
 if len(qualifiers)!=1:return False
 snak=qualifiers[0]
 if snak.get('snaktype')!='value':return False
 try:
  t=snak['datavalue']['value']['time']
  precision=int(snak['datavalue']['value']['precision'])
 except Exception:return False
 return precision==9 and bool(re.fullmatch(r'\+'+str(int(row.year_prefix))+r'-00-00T00:00:00Z',str(t)))

def intpop(v):
 try:
  f=float(v)
  if math.isfinite(f) and f>=0 and f.is_integer():return int(f)
 except Exception:pass
 return None

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 cfg=json.loads(CONFIG.read_text()); G=Path(cfg['working_identity_graph']); P=Path(cfg['working_point_uses']); COV=Path(cfg['working_coverage'])
 # Pin every frozen source and the actual current baseline before screening.
 pinpaths=[SEL,EVID,HIST,CLAIMS,ENT,PB,G,P,COV,CONFIG]
 pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in pinpaths}
 if pins[str(G)]['sha256']!=cfg['working_identity_graph_sha256'] or pins[str(P)]['sha256']!=cfg['working_point_uses_sha256']:
  raise SystemExit('current graph/point-use pin mismatch')

 # Build and validate the full accepted temporal baseline and reproduce controls.
 s=pd.read_parquet(SEL,columns=['source_record_id','census_year','population']);s.source_record_id=s.source_record_id.astype(str)
 uf=YearUF(s.source_record_id.tolist(),s.census_year.astype(int).tolist()); years=dict(zip(s.source_record_id,s.census_year.astype(int)))
 g=pd.read_parquet(G,columns=['decision_id','from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
 if not set(g.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES) or not set(g.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES) or not g.relation.eq('same_place').all(): raise SystemExit('accepted graph canonical-status guard failed')
 for e in g.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  if a not in uf.idx or b not in uf.idx or years[a]!=int(e.from_year) or years[b]!=int(e.to_year):raise SystemExit('accepted graph vertex/year mismatch')
  if uf.union_ids(a,b)=='year_constrained_collision':raise SystemExit('accepted graph contains a same-year collision')
 p=pd.read_parquet(P,columns=['target_source_record_id','target_year','coordinate_admission_status'])
 if p.target_source_record_id.astype(str).duplicated().any():raise SystemExit('duplicate accepted point target')
 point_ids=set(p.target_source_record_id.astype(str))
 base=metrics(s,uf,point_ids); cov=json.loads(COV.read_text()); axes={str(q['year']):q['axes'] for q in cov['census_metrics']}
 checks={}
 for y in (2002,2010,2021):
  z=base[str(y)]; a=axes[str(y)]
  full={'rows':int(a['full_census_chain']['rows']),'population':int(a['full_census_chain']['known_population'])}
  joint={'rows':int(a['joint_admitted_coordinate_and_full_chain']['rows']),'population':int(a['joint_admitted_coordinate_and_full_chain']['known_population'])}
  checks[str(y)]={'full_chain':z['full_chain']==full,'joint':z['joint_point_full_chain']==joint}
 if not all(v['full_chain'] and v['joint'] for v in checks.values()):raise SystemExit('current baseline coverage failed replay; no gain claims')

 stats=Counter()
 # Accepted direct 2021 Wikidata P625 point targets only; current identity is
 # separately corroborated by a unique raw P764->source OKTMO exact match.
 points=pd.read_parquet(P,columns=['target_source_record_id','target_year','coordinate_provider','coordinate_provider_id','point_origin_kind','coordinate_admission_status'])
 points=points[(points.target_year==2021)&(points.coordinate_provider=='wikidata_p625')&(points.point_origin_kind=='wikidata_truthy_p625_raw_claim')&points.coordinate_provider_id.astype(str).str.match(r'^Q[0-9]+$')&points.coordinate_admission_status.isin(['reviewed_rule_accepted','reviewed_extension_rule_accepted'])]
 points=points[['target_source_record_id','coordinate_provider_id']].rename(columns={'coordinate_provider_id':'qid'}).drop_duplicates()
 # Only QIDs with an exact-label, non-admin P764 source-binding witness in the
 # cached primary point-binding profile are eligible for this narrow rule.
 pb=pd.read_parquet(PB,columns=['wikidata_qid','name_comparison','known_admin_only_type','provider_p764_oktmo_claim_count','competing_qids_for_p764_code'])
 pb=pb[(pb.name_comparison=='exact_label')&(~pb.known_admin_only_type.fillna(False))&(pb.provider_p764_oktmo_claim_count==1)&(~pb.competing_qids_for_p764_code.fillna(True))].drop_duplicates('wikidata_qid')
 points=points.merge(pb,left_on='qid',right_on='wikidata_qid',how='inner')
 selcols=['source_record_id','census_year','source_file','source_sheet','source_row','source_name_raw','settlement_name','settlement_type','type_norm','region_raw','district_raw','population','population_scope','is_additive_settlement_record','entity_grain_status','okato','oktmo','source_locator','source_sha256']
 selected=pd.read_parquet(SEL,columns=selcols)
 current=selected[selected.census_year==2021].merge(points,left_on='source_record_id',right_on='target_source_record_id',how='inner')
 # Raw P764 claims: one exact nondeprecated 11-digit claim, unique across QIDs.
 cl=pd.read_parquet(CLAIMS,columns=['wikidata_qid','property','value_raw','value_normalized','statement_id','rank','is_nondeprecated'])
 p764=cl[(cl.property=='P764')&cl.is_nondeprecated.fillna(False)].copy();p764['native_code']=p764.value_normalized.fillna(p764.value_raw).map(lambda x:re.sub(r'\D','',str(x)))
 p764=p764[p764.native_code.str.len()==11]
 p764['code_qid_n']=p764.groupby('native_code').wikidata_qid.transform('nunique')
 p764['qid_code_n']=p764.groupby('wikidata_qid').native_code.transform('nunique')
 current['native_code']=current.oktmo.map(lambda x:re.sub(r'\D','',str(x)))
 current=current[current.native_code.str.len()==11].merge(p764,on=['wikidata_qid','native_code'],how='inner',suffixes=('','_p764'))
 current=current[(current.code_qid_n==1)&(current.qid_code_n==1)]
 # QID's cached Russian label must match the current publisher name exactly;
 # source point target, type and province must also agree with selected row.
 en=pd.read_parquet(ENT,columns=['wikidata_qid','label_ru'])
 current=current.merge(en,on='wikidata_qid',how='inner')
 current['name_key']=current.settlement_name.map(norm);current['qid_name_key']=current.label_ru.map(norm)
 current['type_key']=current.settlement_type.map(typ);current['region_key']=current.region_raw.map(region_key)
 physical={'город','пгт','поселок','деревня','село','хутор','станица','аул','кишлак','слобода','арбан','выселок','починок','местечко','разъезд','станция'}
 current=current[(current.name_key!='')&(current.name_key==current.qid_name_key)&(current.type_key.isin(physical))&(current.region_key!='')&current.is_additive_settlement_record.fillna(False)]
 current=current.drop_duplicates('wikidata_qid')
 stats['current_direct_proper_qid_targets_after_native_P764_label_type_region']=len(current)
 # Retain actual additive physical old source rows. Candidate lineage never uses
 # old publisher numeric IDs/codes or external fuzzy/proximity matching.
 old=selected[selected.census_year.isin([2002,2010])].copy()
 old['name_key']=old.settlement_name.map(norm);old['type_key']=old.settlement_type.map(typ);old['region_key']=old.region_raw.map(region_key);old['district_key']=old.district_raw.map(district)
 old['district_context_class']=old.district_key.map(lambda x:'explicit' if x else 'blank_unknown')
 old.loc[old.district_key.eq(''),'district_key']='__blank_unknown__'
 old['pop_i']=old.population.map(intpop)
 old=old[(old.name_key!='')&(old.type_key!='')&(old.region_key!='')&old.pop_i.notna()&old.is_additive_settlement_record.fillna(False)]
 old=old[old.type_key.isin(physical)]
 # Restrict QID history to actual one-statement-per-year P1082 claims with a
 # precision-9 P585 date and an unambiguous year prefix.
 qids=set(current.wikidata_qid.astype(str))
 hist=pd.read_parquet(HIST,columns=['qid','statement_id','population_value_raw','year_prefix','date_assignment_status','date_ambiguous_hold','date_precision','rank_raw','rank_is_deprecated','raw_source_file','raw_source_sha256','raw_tsv_line_number','raw_source_locator','raw_record_locator','raw_statement_json','references_count','reference_p854_urls_json'])
 hist=hist[hist.qid.astype(str).isin(qids)&hist.year_prefix.astype(str).isin(['2002','2010'])&(~hist.rank_is_deprecated.fillna(True))&(~hist.date_ambiguous_hold.fillna(True))].copy()
 hist['population_i']=hist.population_value_raw.map(intpop)
 hist['raw_p1082_single_year_precision']=hist.apply(raw_p1082,axis=1)
 hist=hist[hist.population_i.notna()&hist.raw_p1082_single_year_precision]
 statement_counts=hist.groupby(['qid','year_prefix']).statement_id.nunique()
 valid_keys={k for k,n in statement_counts.items() if n==1}
 hist=hist[[ (str(r.qid),str(r.year_prefix)) in valid_keys for r in hist.itertuples(index=False) ]]
 if not hist.empty:
  dup=hist.groupby(['qid','year_prefix']).population_i.nunique();bad={k for k,n in dup.items() if n!=1}
  hist=hist[[ (str(r.qid),str(r.year_prefix)) not in bad for r in hist.itertuples(index=False) ]]
  h2=hist[hist.year_prefix.astype(str)=='2002'].set_index('qid');h10=hist[hist.year_prefix.astype(str)=='2010'].set_index('qid')
  dual=set(h2.index)&set(h10.index)
 else: dual=set();h2=hist;h10=hist
 stats['qids_with_one_raw_dated_nonconflicting_P1082_each_year']=len(dual)
 # Candidate old pairs: exactly one explicit old source row per year inside
 # exact name/type/ADM1/district signature; district aliases only lose legal
 # descriptor words, preserving the raw fields in output.
 pairkeys=['name_key','type_key','region_key','district_key']
 g02=old[old.census_year==2002].groupby(pairkeys,dropna=False).size().rename('n2002')
 g10=old[old.census_year==2010].groupby(pairkeys,dropna=False).size().rename('n2010')
 groups=pd.concat([g02,g10],axis=1).fillna(0).reset_index();unique=groups[(groups.n2002==1)&(groups.n2010==1)][pairkeys]
 # Blank old-county cells provide no county context. In that case require the
 # typed name/province key to be unique across the whole year, including rows
 # with explicit districts; the missing cell itself is never treated as proof.
 fullkey=['name_key','type_key','region_key']
 count02=old[old.census_year==2002].groupby(fullkey).size().rename('all2002')
 count10=old[old.census_year==2010].groupby(fullkey).size().rename('all2010')
 allcounts=pd.concat([count02,count10],axis=1).fillna(0).reset_index()
 blankgroups=set(map(tuple,allcounts[(allcounts.all2002==1)&(allcounts.all2010==1)][fullkey].itertuples(index=False,name=None)))
 unique=unique[unique.district_key.ne('__blank_unknown__')|unique.apply(lambda x:(x.name_key,x.type_key,x.region_key) in blankgroups,axis=1)]
 old=old.merge(unique,on=pairkeys,how='inner',suffixes=('','_key'))
 old02=old[old.census_year==2002].copy();old10=old[old.census_year==2010].copy()
 oldpairs=old02.merge(old10,on=pairkeys,suffixes=('_2002','_2010'))
 stats['unique_explicit_old_2002_2010_source_pairs']=len(oldpairs)
 # The candidate pair must share exact current QID label/type/province. P1082
 # values are candidate filters only: exact 2002, and <=10 difference in 2010.
 oldpairs=oldpairs.merge(current[['wikidata_qid','target_source_record_id','settlement_name','settlement_type','region_raw','native_code','statement_id','value_raw','value_normalized','source_sha256','source_locator','population','population_scope','entity_grain_status','region_key','name_key','type_key']],left_on=['name_key','type_key','region_key'],right_on=['name_key','type_key','region_key'],how='inner',suffixes=('','_current'))
 oldpairs=oldpairs[oldpairs.wikidata_qid.astype(str).isin(dual)]
 oldpairs=oldpairs.merge(h2[['population_i','statement_id','raw_source_file','raw_source_sha256','raw_tsv_line_number','raw_source_locator','raw_record_locator','raw_statement_json','references_count','reference_p854_urls_json']].rename(columns={'population_i':'p1082_2002','statement_id':'p1082_statement_2002','raw_source_file':'p1082_file_2002','raw_source_sha256':'p1082_sha256_2002','raw_tsv_line_number':'p1082_line_2002','raw_source_locator':'p1082_locator_2002','raw_record_locator':'p1082_record_locator_2002','raw_statement_json':'p1082_raw_statement_2002','references_count':'p1082_references_2002','reference_p854_urls_json':'p1082_p854_refs_2002'}),left_on='wikidata_qid',right_index=True,how='inner')
 oldpairs=oldpairs.merge(h10[['population_i','statement_id','raw_source_file','raw_source_sha256','raw_tsv_line_number','raw_source_locator','raw_record_locator','raw_statement_json','references_count','reference_p854_urls_json']].rename(columns={'population_i':'p1082_2010','statement_id':'p1082_statement_2010','raw_source_file':'p1082_file_2010','raw_source_sha256':'p1082_sha256_2010','raw_tsv_line_number':'p1082_line_2010','raw_source_locator':'p1082_locator_2010','raw_record_locator':'p1082_record_locator_2010','raw_statement_json':'p1082_raw_statement_2010','references_count':'p1082_references_2010','reference_p854_urls_json':'p1082_p854_refs_2010'}),left_on='wikidata_qid',right_index=True,how='inner')
 oldpairs=oldpairs[oldpairs.population_2002.astype(int)==oldpairs.p1082_2002.astype(int)].copy();oldpairs['p1082_2010_delta']=oldpairs.p1082_2010.astype(int)-oldpairs.population_2010.astype(int)
 oldpairs=oldpairs[oldpairs.p1082_2010_delta.abs()<=10].copy();oldpairs['p1082_2010_is_exact']=oldpairs.p1082_2010_delta.eq(0)
 stats['pairs_matching_two_year_P1082_signature']=len(oldpairs)
 stats['p1082_2010_exact_population_matches']=int(oldpairs.p1082_2010_is_exact.sum())
 stats['p1082_2010_within_10_nonexact_matches']=int((~oldpairs.p1082_2010_is_exact).sum())
 # Signatures must be unique among all exact-key old pairs and current QIDs.
 sig=['name_key','type_key','region_key','population_2002','population_2010']
 oldpairs['signature_pair_count']=oldpairs.groupby(sig,dropna=False).wikidata_qid.transform('size')
 oldpairs=oldpairs[oldpairs.signature_pair_count==1].copy()
 stats['unique_two_year_population_signature_pairs']=len(oldpairs)

 # Independent aggregate/event/code conflicts and current temporal residuals.
 # Read authoritative source evidence only for the narrowed exact candidate pairs.
 ids=set(oldpairs.source_record_id_2002.astype(str))|set(oldpairs.source_record_id_2010.astype(str))|set(oldpairs.target_source_record_id.astype(str))
 ev={}
 if ids:
  et=ds.dataset(EVID,format='parquet').to_table(columns=['source_record_id','source_evidence_json'],filter=ds.field('source_record_id').isin(ids))
  ev={str(x['source_record_id']):json.loads(x['source_evidence_json']) for x in et.to_pylist()}
 sourceholds=Counter(); candidates=[]; reviewed_pairs=[]
 pair_roots={uf.find(uf.idx[str(r.source_record_id_2002)]) for r in oldpairs.itertuples(index=False) if str(r.source_record_id_2002) in uf.idx}
 adjacency={}
 for e in g.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  ia,ib=uf.idx.get(a),uf.idx.get(b)
  if ia is None or ib is None or uf.find(ia) not in pair_roots:continue
  edge={'decision_id':str(e.decision_id),'from_source_record_id':a,'from_year':int(e.from_year),'to_source_record_id':b,'to_year':int(e.to_year),'relation':str(e.relation)}
  adjacency.setdefault(a,[]).append((b,edge));adjacency.setdefault(b,[]).append((a,edge))
 def accepted_path(start,end):
  from collections import deque
  start,end=str(start),str(end);queue=deque([start]);prev={start:None};via={}
  while queue:
   n=queue.popleft()
   if n==end:break
   for nxt,edge in adjacency.get(n,[]):
    if nxt not in prev:prev[nxt]=n;via[nxt]=edge;queue.append(nxt)
  if end not in prev:return []
  path=[];cur=end
  while prev[cur] is not None:path.append(via[cur]);cur=prev[cur]
  return list(reversed(path))
 for r in oldpairs.to_dict('records'):
  endpoints=[str(r['source_record_id_2002']),str(r['source_record_id_2010']),str(r['target_source_record_id'])];why=[]
  for eid in endpoints:
   e=ev.get(eid,{})
   if truth(e.get('is_federal_aggregate')) or truth(e.get('legacy_same_year_collision')) or e.get('legacy_verified_successor_settlement_id'):
    why.append('aggregate_collision_or_verified_event:'+eid)
   if e.get('is_additive_settlement_record') is False:why.append('nonadditive_source_evidence:'+eid)
   if truth(e.get('legacy_identity_conflict')):
    try:cf=set(json.loads(e.get('legacy_identity_reasons') or '[]'))
    except Exception:cf={'unparsed_identity_conflict'}
    cf-={'administrative_conflict','ordinal_historical_identifier_hypothesis'}
    if cf:why.append('nonadministrative_legacy_identity_conflict:'+eid+':'+','.join(sorted(cf)))
  roots=[uf.find(uf.idx[x]) if x in uf.idx else None for x in endpoints]
  path=accepted_path(endpoints[0],endpoints[1])
  r['accepted_old_identity_path_decision_ids_json']=json.dumps([x['decision_id'] for x in path],ensure_ascii=False)
  r['accepted_old_identity_path_edges_json']=json.dumps(path,ensure_ascii=False)
  if None in roots:why.append('selected_vertex_missing')
  elif roots[0]!=roots[1]:why.append('old_2002_2010_pair_not_already_in_accepted_identity_graph')
  elif roots[0]==roots[2]:why.append('current_2021_target_already_in_old_component')
  else:
   r0,r1=uf.find(uf.idx[endpoints[0]]),uf.find(uf.idx[endpoints[2]])
   if uf.mask[r0]&uf.mask[r1]:why.append('year_constrained_collision')
  r['source_evidence_gate']='eligible' if not why else 'held'
  r['source_evidence_hold_reasons_json']=json.dumps(why,ensure_ascii=False)
  r['baseline_old_pair_identity_path_source_record_ids_json']=json.dumps([endpoints[0],endpoints[1]],ensure_ascii=False)
  reviewed_pairs.append(r)
  if not why:candidates.append(r)
  for q in why:sourceholds[q]+=1
 stats['signature_pairs_already_connected_to_current_no_residual']=sourceholds['current_2021_target_already_in_old_component']
 stats['signature_pairs_with_old_pair_not_yet_connected']=sourceholds['old_2002_2010_pair_not_already_in_accepted_identity_graph']
 stats['signature_pairs_passing_source_and_residual_gates']=len(candidates)

 # Simulate all safe candidate edges over the complete accepted graph. Edges
 # remain hypothetical until a separate decision/review.
 candidates.sort(key=lambda r:(-int(r['population_2002']+r['population_2010']),str(r['source_record_id_2002'])))
 edges=[]; outcomes=Counter()
 for r in candidates:
  a=str(r['source_record_id_2002']);b=str(r['target_source_record_id']);out=uf.union_ids(a,b);outcomes[out]+=1
  r['conditional_union_result']=out
  if out=='merged':edges.append({'from_source_record_id':a,'from_year':2002,'to_source_record_id':b,'to_year':2021,'relation':'same_place','decision_rule':'two_explicit_historic_population_signature_candidate_only','candidate_only':True,'identity_admitted':False,'wikidata_qid':r['wikidata_qid'],'historical_p1082_2002_matches_exact':True,'historical_p1082_2010_match_within_10_not_exact_if_flagged':not bool(r['p1082_2010_is_exact'])})
  else:r['conditional_candidate_hold']=f'conditional_union_{out}'
 after=metrics(s,uf,point_ids)
 delta={y:{ax:{m:after[y][ax][m]-base[y][ax][m] for m in ('rows','population')} for ax in ('full_chain','joint_point_full_chain')} for y in base}
 # Reproducible concise ledger carries source row locators, raw P1082 row
 # provenance, current raw P764 claim, and baseline graph path anchors.
 ledger=[]
 for r in reviewed_pairs:
  item={k:r.get(k) for k in ['source_record_id_2002','source_record_id_2010','source_file_2002','source_file_2010','source_sheet_2002','source_sheet_2010','source_row_2002','source_row_2010','source_locator_2002','source_locator_2010','source_sha256_2002','source_sha256_2010','source_name_raw_2002','source_name_raw_2010','settlement_type_2002','settlement_type_2010','region_raw_2002','region_raw_2010','district_raw_2002','district_raw_2010','population_2002','population_2010','population_scope_2002','population_scope_2010','wikidata_qid','target_source_record_id','native_code','statement_id','value_raw','value_normalized','p1082_2002','p1082_statement_2002','p1082_file_2002','p1082_sha256_2002','p1082_line_2002','p1082_locator_2002','p1082_record_locator_2002','p1082_raw_statement_2002','p1082_references_2002','p1082_p854_refs_2002','p1082_2010','p1082_statement_2010','p1082_file_2010','p1082_sha256_2010','p1082_line_2010','p1082_locator_2010','p1082_record_locator_2010','p1082_raw_statement_2010','p1082_references_2010','p1082_p854_refs_2010','p1082_2010_delta','p1082_2010_is_exact','source_evidence_gate','source_evidence_hold_reasons_json','baseline_old_pair_identity_path_source_record_ids_json','accepted_old_identity_path_decision_ids_json','accepted_old_identity_path_edges_json','conditional_union_result','conditional_candidate_hold']}
  item['population_values_used_as_candidate_corroboration_only']=True
  item['no_population_values_replaced_or_allocated']=True
  ledger.append(item)
 write_csv(OUT/'candidate_pair_ledger.csv',ledger);write_csv(OUT/'conditional_identity_edges.csv',edges)
 summary={'status':'candidate_generation_only_no_identity_or_population_admissions','baseline_id':cfg.get('diagnostic_baseline_id','current_config_pinned'),'baseline_graph_sha256':pins[str(G)]['sha256'],'baseline_point_uses_sha256':pins[str(P)]['sha256'],'baseline_coverage_reproduced':True,'baseline_checks':checks,'candidate_rule':'Exact old 2002/2010 same typed name and ADM1; one publisher row per year within the same normalized explicit district when both county cells exist. If both county cells are blank, exact typed name/province must be unique across all selected old-year objects. Old rows are already connected by an accepted identity path. One accepted direct 2021 Wikidata point target is matched to a unique nondeprecated native 11-digit P764=source OKTMO claim and exact QID label/type/province. The same QID has exactly one nondeprecated raw P1082 statement with an unambiguous year-precision P585 qualifier in both 2002 and 2010. P1082 exactly equals the 2002 publisher count and is within 10 persons of the 2010 publisher count (the latter marked nonexact). The two-year source population pair is unique among candidates sharing exact name/type/province. Source events, aggregates, collisions, nonadditive rows, and unresolved nonadministrative identity conflicts are held. Population agreement alone is not identity proof.','stage_counts':dict(stats),'candidate_rows_after_all_gates':len(candidates),'source_evidence_and_baseline_holds':dict(sourceholds),'simulated_nonredundant_edges':len(edges),'conditional_union_outcomes':dict(outcomes),'conditional_full_graph_metric_delta':delta,'inputs':pins,'interpretation':['No identity edge or population assertion has been admitted.','The Wikidata values are supporting secondary assertions only; census selected observations and counts are unchanged.','A 2010 difference within 10 is explicitly nonexact.','Blank old county cells remain unknown; rows with blank cells are eligible only if the typed name/province signature is unique across all old objects in both years.','A candidate signature lacks a proven history of all competing QIDs, so independent scope and source-history review is still required.']}
 summary['outputs']={x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in sorted(OUT.iterdir()) if x.is_file() and x.name not in {'summary.json','receipt.json'}}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 rec={'status':summary['status'],'input_sha256':{k:v['sha256'] for k,v in pins.items()},'output_sha256':{x.name:sha(x) for x in sorted(OUT.iterdir()) if x.is_file() and x.name!='receipt.json'},'script':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__))}
 (OUT/'receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in {'inputs','outputs'}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
