#!/usr/bin/env python3
"""Candidate-only homonym identity diagnostic using two dated P1082 assertions.

It expands the prior P625-only funnel to all accepted current point providers.
No identities or population values are admitted by this stage.
"""
from __future__ import annotations
import hashlib, json, math, re, unicodedata
from collections import Counter, deque
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF, metrics
from research_rebuild.mass_linkage.stage_legacy_temporal_20261004 import region_key
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES, ACCEPTED_PROJECTION_STATUSES, ACCEPTED_COORDINATE_STATUSES

W=Path('/workspace'); BASE=W/'settlements-work/continuation_20261004'; R4=BASE/'R4'
OUT=R4/'two_year_wikidata_population_homonym_identity_20261004'
F=W/'settlements-delivery/continuation-consolidated-20261003'
SEL=F/'selected_observations.parquet'; EVID=F/'source_evidence.parquet'
HIST=BASE/'federal_and_history/wikidata_secondary_working_series.parquet'
CLAIMS=W/'settlements-work/wikidata/claims.parquet'; ENT=W/'settlements-work/wikidata/entities.parquet'
PB=W/'settlements-work/wikidata/point_bindings.parquet'
CONFIG=W/'russian-settlements-research/config/mass_joint_20261004.json'

PHYSICAL={'город','пгт','поселок','деревня','село','хутор','станица','аул','кишлак','слобода','арбан','выселок','починок','местечко','разъезд','станция'}
SEL_COLS=['source_record_id','census_year','source_file','source_sheet','source_row','source_name_raw','settlement_name','settlement_type','type_norm','region_raw','district_raw','population','population_scope','is_additive_settlement_record','entity_grain_status','okato','oktmo','source_locator','source_sha256']

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def norm(v):
 if v is None or pd.isna(v):return ''
 return ' '.join(unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е').replace('\xa0',' ').split())

def typ(v):
 s=norm(v).replace('.','').strip()
 return {'поселок сельского типа':'поселок','посёлок сельского типа':'поселок','поселок городского типа':'пгт','посёлок городского типа':'пгт','пгт':'пгт','пос':'поселок','п':'поселок','дер':'деревня','д':'деревня','с':'село','х':'хутор','ст-ца':'станица','стца':'станица','г':'город','гор':'город'}.get(s,s)

def district(v):
 s=norm(v)
 s=re.sub(r'^(городской округ|муниципальный округ|муниципальный район|городской район|район)\s+','',s)
 s=re.sub(r'\s+(муниципальный район|муниципальный округ|городской округ|район|округ)$','',s)
 return s.strip()

def intpop(v):
 try:
  f=float(v)
  if math.isfinite(f) and f>=0 and f.is_integer():return int(f)
 except Exception:pass
 return None

def raw_year_p1082(row):
 try:d=json.loads(row.raw_statement_json)
 except Exception:return False
 if d.get('rank')=='deprecated' or d.get('mainsnak',{}).get('property')!='P1082':return False
 q=d.get('qualifiers',{}).get('P585',[])
 if len(q)!=1 or q[0].get('snaktype')!='value':return False
 try:t=q[0]['datavalue']['value']['time'];precision=int(q[0]['datavalue']['value']['precision'])
 except Exception:return False
 return precision==9 and bool(re.fullmatch(r'\+'+str(int(row.year_prefix))+r'-00-00T00:00:00Z',str(t)))

def truth(x):
 if isinstance(x,bool):return x
 if x is None:return False
 if isinstance(x,(int,float)):return x!=0
 return str(x).strip().casefold() in {'true','1','yes'}

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 cfg=json.loads(CONFIG.read_text());G=Path(cfg['working_identity_graph']);P=Path(cfg['working_point_uses']);COV=Path(cfg['working_coverage'])
 pinpaths=[SEL,EVID,HIST,CLAIMS,ENT,PB,G,P,COV,CONFIG]
 pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in pinpaths}
 if pins[str(G)]['sha256']!=cfg['working_identity_graph_sha256'] or pins[str(P)]['sha256']!=cfg['working_point_uses_sha256']:
  raise SystemExit('canonical graph/point pin mismatch')

 s=pd.read_parquet(SEL,columns=['source_record_id','census_year','population']);s.source_record_id=s.source_record_id.astype(str);s.census_year=s.census_year.astype(int)
 uf=YearUF(s.source_record_id.tolist(),s.census_year.tolist());years=dict(zip(s.source_record_id,s.census_year))
 g=pd.read_parquet(G,columns=['decision_id','from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
 if not set(g.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES) or not set(g.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES) or not g.relation.eq('same_place').all():raise SystemExit('canonical accepted graph status guard failed')
 for e in g.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  if a not in uf.idx or b not in uf.idx or years[a]!=int(e.from_year) or years[b]!=int(e.to_year):raise SystemExit('graph endpoint/year mismatch')
  if uf.union_ids(a,b)=='year_constrained_collision':raise SystemExit('baseline graph same-year collision')
 points=pd.read_parquet(P,columns=['target_source_record_id','target_year','coordinate_admission_status'])
 points=points[points.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
 if points.target_source_record_id.astype(str).duplicated().any():raise SystemExit('duplicate accepted point target')
 point_ids=set(points.target_source_record_id.astype(str))
 base=metrics(s,uf,point_ids);cov=json.loads(COV.read_text());axes={str(x['year']):x['axes'] for x in cov['census_metrics']};checks={}
 for y in (2002,2010,2021):
  a=axes[str(y)];z=base[str(y)]
  checks[str(y)]={'full_chain':z['full_chain']=={'rows':int(a['full_census_chain']['rows']),'population':int(a['full_census_chain']['known_population'])},'joint':z['joint_point_full_chain']=={'rows':int(a['joint_admitted_coordinate_and_full_chain']['rows']),'population':int(a['joint_admitted_coordinate_and_full_chain']['known_population'])}}
 if not all(x['full_chain'] and x['joint'] for x in checks.values()):raise SystemExit('baseline metrics failed coverage reproduction')

 stats=Counter()
 # Current-source target funnel: current accepted point may have any provider;
 # Wikidata itself contributes exact current identity anchors, not coordinates.
 pts=pd.read_parquet(P,columns=['target_source_record_id','target_year','coordinate_provider','coordinate_provider_id','point_origin_kind','coordinate_admission_status'])
 pts=pts[(pts.target_year==2021)&pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)].copy()
 approved_direct=pts[pts.coordinate_provider.astype(str).str.casefold().isin(['wikidata p625','wikidata_p625'])&pts.point_origin_kind.astype(str).eq('wikidata_truthy_p625_raw_claim')]
 pts=pts[['target_source_record_id']].drop_duplicates()
 pb=pd.read_parquet(PB)
 pb['wikidata_qid']=pb.wikidata_qid.astype(str);pb['source_record_id']=pb.source_record_id.astype(str)
 pb=pb[(pb.census_year==2021)&pb.wikidata_qid.str.match(r'^Q[0-9]+$')]
 pb=pb[~pb.known_admin_only_type.fillna(True)&(pb.provider_p764_oktmo_claim_count==1)&(~pb.competing_qids_for_p764_code.fillna(True))]
 pb=pb.merge(pts,left_on='source_record_id',right_on='target_source_record_id',how='inner')
 stats['point_binding_current_targets_any_accepted_provider']=len(pb)
 stats['point_binding_current_targets_with_accepted_direct_p625']=len(set(pb.source_record_id)&set(approved_direct.target_source_record_id.astype(str)))
 # Exact native code claims: unique, nondeprecated P764 string digits and exactly one code per QID.
 cl=pd.read_parquet(CLAIMS,columns=['wikidata_qid','property','value_raw','value_normalized','statement_id','rank','is_nondeprecated'])
 p764=cl[(cl.property=='P764')&cl.is_nondeprecated.fillna(False)].copy()
 p764['native_code']=p764.value_normalized.fillna(p764.value_raw).map(lambda x:re.sub(r'\D','',str(x)))
 p764=p764[p764.native_code.str.len()==11].copy();p764['code_qid_n']=p764.groupby('native_code').wikidata_qid.transform('nunique');p764['qid_code_n']=p764.groupby('wikidata_qid').native_code.transform('nunique')
 p764=p764[(p764.code_qid_n==1)&(p764.qid_code_n==1)]
 pb['native_code']=pb.source_oktmo_normalized.fillna(pb.source_oktmo_raw).map(lambda x:re.sub(r'\D','',str(x)))
 current=pb[pb.native_code.str.len()==11].merge(p764,on=['wikidata_qid','native_code'],how='inner',suffixes=('','_p764'))
 stats['exact_unique_P764_current_native_code']=len(current)
 en=pd.read_parquet(ENT,columns=['wikidata_qid','label_ru','p31_qids_json'])
 current=current.merge(en,on='wikidata_qid',how='inner')
 current['name_key']=current.source_settlement_name.map(norm);current['label_key']=current.label_ru.map(norm);current['type_key']=current.source_settlement_type.map(typ);current['region_key']=current.source_region.map(region_key)
 current=current[(current.name_key!='')&(current.name_key==current.label_key)&current.type_key.isin(PHYSICAL)&(current.region_key!='')]
 # Confirm one source row and one target per typed name/province key; the QID
 # label and exact native code must name that same source observation.
 current=current.drop_duplicates('source_record_id')
 current['current_qid_subject_claims_exact_typed_name_region']=True
 stats['current exact name/type/region QID anchors'.replace(' ','_')]=len(current)
 # Whole selected source frame supplies all same-year alternatives, including
 # competitors without a Wikidata binding. Narrow historical rows to keys in
 # this explicit current anchor set only after deriving whole-year counts.
 selected=pd.read_parquet(SEL,columns=SEL_COLS);selected.source_record_id=selected.source_record_id.astype(str);selected.census_year=selected.census_year.astype(int)
 selected['name_key']=selected.settlement_name.map(norm);selected['type_key']=selected.settlement_type.map(typ);selected['region_key']=selected.region_raw.map(region_key);selected['district_key']=selected.district_raw.map(district);selected['pop_i']=selected.population.map(intpop)
 selected=selected[(selected.name_key!='')&selected.type_key.isin(PHYSICAL)&(selected.region_key!='')&selected.is_additive_settlement_record.fillna(False)&selected.pop_i.notna()]
 keys=set(map(tuple,current[['name_key','type_key','region_key']].itertuples(index=False,name=None)))
 old=selected[selected.census_year.isin([2002,2010])&selected.apply(lambda r:(r.name_key,r.type_key,r.region_key) in keys,axis=1)].copy()
 old['district_context']=old.district_key.map(lambda x:'explicit' if x else 'blank_unknown');old.loc[old.district_key.eq(''),'district_key']='__blank_unknown__'
 # Current source multiplicity can reveal a current-year homonym too.
 current_counts=selected[selected.census_year==2021].groupby(['name_key','type_key','region_key']).size().rename('current_source_objects').reset_index()
 current=current.merge(current_counts,on=['name_key','type_key','region_key'],how='left')
 current=current[current.current_source_objects==1]
 stats['current whole-year unique typed source keys']=len(current)
 keys=set(map(tuple,current[['name_key','type_key','region_key']].itertuples(index=False,name=None)))
 old=old[old.apply(lambda r:(r.name_key,r.type_key,r.region_key) in keys,axis=1)]
 # Existing population pair must be a real accepted pair, not a computed code
 # or ordinal. Keep district context as evidence/stratum; don't require county
 # equality where cells are blank. Explicit disagreements are held below.
 old02=old[old.census_year==2002].copy();old10=old[old.census_year==2010].copy()
 pairs=old02.merge(old10,on=['name_key','type_key','region_key'],suffixes=('_2002','_2010'))
 if len(pairs):pairs['old_pair_signature_count']=pairs.groupby(['name_key','type_key','region_key','pop_i_2002','pop_i_2010'],dropna=False).source_record_id_2002.transform('size')
 else:pairs['old_pair_signature_count']=pd.Series(dtype='int64')
 stats['old exact typed key 2002x2010 pairs before graph gate']=len(pairs)
 # Check statement coverage for all current anchored QIDs before pairing.
 qids=set(current.wikidata_qid.astype(str))
 hist=pd.read_parquet(HIST,columns=['qid','statement_id','population_value_raw','year_prefix','date_assignment_status','date_ambiguous_hold','date_precision','rank_raw','rank_is_deprecated','raw_source_file','raw_source_sha256','raw_tsv_line_number','raw_source_locator','raw_record_locator','raw_statement_json','references_count','reference_p854_urls_json'])
 hist=hist[hist.qid.astype(str).isin(qids)&hist.year_prefix.astype(str).isin(['2002','2010'])&(~hist.rank_is_deprecated.fillna(True))&(~hist.date_ambiguous_hold.fillna(True))].copy()
 hist['pop_i']=hist.population_value_raw.map(intpop);hist['raw_claim_valid']=hist.apply(raw_year_p1082,axis=1);hist=hist[hist.pop_i.notna()&hist.raw_claim_valid]
 statement_n=hist.groupby(['qid','year_prefix']).statement_id.nunique();valid=set(k for k,v in statement_n.items() if v==1)
 hist=hist[[ (str(r.qid),str(r.year_prefix)) in valid for r in hist.itertuples(index=False) ]]
 if not hist.empty:
  uniqueval=hist.groupby(['qid','year_prefix']).pop_i.nunique();bad=set(k for k,v in uniqueval.items() if v!=1)
  hist=hist[[ (str(r.qid),str(r.year_prefix)) not in bad for r in hist.itertuples(index=False) ]]
 hist['qid']=hist.qid.astype(str);h02=hist[hist.year_prefix.astype(str)=='2002'].set_index('qid');h10=hist[hist.year_prefix.astype(str)=='2010'].set_index('qid')
 dual=set(h02.index)&set(h10.index)
 stats['current anchored QIDs']=len(qids);stats['current QIDs with both valid cached dated claims']=len(dual)
 stats['current QIDs missing either dated claim from local cache']=len(qids-dual)
 stats['current source keys with more than one QID binding']=int(current.groupby(['name_key','type_key','region_key']).wikidata_qid.nunique().gt(1).sum())
 stats['current distinct typed source keys']=int(current.groupby(['name_key','type_key','region_key']).ngroups)
 # Record per key cache gaps for follow-up retrieval; never call cache-missing a
 # negative historical population claim.
 current_by_key={k:g for k,g in current.groupby(['name_key','type_key','region_key'])}
 key_qids={k:set(g.wikidata_qid.astype(str)) for k,g in current_by_key.items()}
 # Build accepted graph components and path provenance.
 adjacency={}
 for e in g.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  row={'decision_id':str(e.decision_id),'from_source_record_id':a,'from_year':int(e.from_year),'to_source_record_id':b,'to_year':int(e.to_year)}
  adjacency.setdefault(a,[]).append((b,row));adjacency.setdefault(b,[]).append((a,row))
 def path(a,b):
  a,b=str(a),str(b);qq=deque([a]);prev={a:None};via={}
  while qq:
   n=qq.popleft()
   if n==b:break
   for nxt,e in adjacency.get(n,[]):
    if nxt not in prev:prev[nxt]=n;via[nxt]=e;qq.append(nxt)
  if b not in prev:return []
  out=[];n=b
  while prev[n] is not None:out.append(via[n]);n=prev[n]
  return list(reversed(out))
 # Candidate old publisher pairs with exactly one P1082 claim per QID/year,
 # exact 2002 and exact/±10 2010 population corroboration.
 pairs=pairs.merge(current[['wikidata_qid','source_record_id','native_code','statement_id','value_raw','value_normalized','source_settlement_name','source_settlement_type','source_region','name_key','type_key','region_key','current_source_objects']],on=['name_key','type_key','region_key'],how='inner',suffixes=('','_current'))
 stats['old-pair/current-QID typed key combinations']=len(pairs)
 residual_pair_rows=[];residual_keyset=set();residual_flags=[];graph_flags=[];graph_partitions=Counter()
 for r in pairs.itertuples(index=False):
  a,b,c=str(r.source_record_id_2002),str(r.source_record_id_2010),str(r.source_record_id)
  ra,rb,rc=[uf.find(uf.idx[x]) if x in uf.idx else None for x in (a,b,c)]
  passed=ra==rb and ra is not None and rc is not None and ra!=rc and not (uf.mask[ra]&uf.mask[rc])
  residual_flags.append(passed)
  if ra is None or rb is None or rc is None:part='missing_selected_endpoint'
  elif ra!=rb:part='old_2002_2010_not_connected'
  elif ra==rc:part='current_already_connected_to_old_pair'
  elif uf.mask[ra]&uf.mask[rc]:part='year_collision_if_joined'
  else:part='old_pair_connected_current_residual_safe'
  graph_flags.append(part);graph_partitions[part]+=1
  if passed:
   residual_pair_rows.append((a,b,c,str(r.wikidata_qid)));residual_keyset.add((r.name_key,r.type_key,r.region_key))
 pairs['baseline_old_pair_residual_to_current']=residual_flags
 pairs['graph_gate_status']=graph_flags
 stats['old pairs already accepted but still residual from current target']=len(residual_pair_rows)
 stats['graph_partition_oldpair_current_combinations']=dict(graph_partitions)
 stats['distinct current typed keys with an accepted old pair still residual']=len(residual_keyset)
 all_inventory=pairs.copy()
 all_inventory['cached_single_valid_P1082_2002']=all_inventory.wikidata_qid.astype(str).isin(h02.index)
 all_inventory['cached_single_valid_P1082_2010']=all_inventory.wikidata_qid.astype(str).isin(h10.index)
 all_inventory['cached_two_year_P1082']=all_inventory.wikidata_qid.astype(str).isin(dual)
 all_inventory['p1082_2002']=all_inventory.wikidata_qid.astype(str).map(h02['pop_i'].to_dict())
 all_inventory['p1082_2010']=all_inventory.wikidata_qid.astype(str).map(h10['pop_i'].to_dict())
 all_inventory['source_pair_population_matches_P1082_2002']=all_inventory.apply(lambda r:pd.notna(r.p1082_2002) and int(r.p1082_2002)==int(r.pop_i_2002),axis=1)
 all_inventory['source_pair_population_matches_P1082_2010_exact']=all_inventory.apply(lambda r:pd.notna(r.p1082_2010) and int(r.p1082_2010)==int(r.pop_i_2010),axis=1)
 all_inventory['source_pair_population_matches_P1082_2010_within_10']=all_inventory.apply(lambda r:pd.notna(r.p1082_2010) and abs(int(r.p1082_2010)-int(r.pop_i_2010))<=10,axis=1)
 residual_inventory=all_inventory[all_inventory.baseline_old_pair_residual_to_current].copy()
 stats['residual QIDs with valid cached 2002 claim']=int(residual_inventory.cached_single_valid_P1082_2002.sum())
 stats['residual QIDs with valid cached 2010 claim']=int(residual_inventory.cached_single_valid_P1082_2010.sum())
 stats['residual QIDs with both cached claims']=int(residual_inventory.cached_two_year_P1082.sum())
 stats['residual source pairs matching both populations']=int((residual_inventory.source_pair_population_matches_P1082_2002 & residual_inventory.source_pair_population_matches_P1082_2010_within_10).sum())
 stats['oldpair combinations with both cached claims']=int(all_inventory.cached_two_year_P1082.sum())
 stats['oldpair combinations matching both source populations']=int((all_inventory.source_pair_population_matches_P1082_2002 & all_inventory.source_pair_population_matches_P1082_2010_within_10).sum())
 stats['oldpair population matches among old-year-disconnected pairs']=int(((all_inventory.graph_gate_status=='old_2002_2010_not_connected') & all_inventory.source_pair_population_matches_P1082_2002 & all_inventory.source_pair_population_matches_P1082_2010_within_10).sum())
 pairs=pairs[pairs.wikidata_qid.astype(str).isin(dual)].copy()
 if not pairs.empty:
  pairs=pairs.merge(h02[['pop_i','statement_id','raw_source_file','raw_source_sha256','raw_tsv_line_number','raw_source_locator','raw_record_locator','raw_statement_json','references_count','reference_p854_urls_json']].rename(columns={'pop_i':'p1082_2002','statement_id':'p1082_statement_2002','raw_source_file':'p1082_file_2002','raw_source_sha256':'p1082_sha256_2002','raw_tsv_line_number':'p1082_line_2002','raw_source_locator':'p1082_locator_2002','raw_record_locator':'p1082_record_locator_2002','raw_statement_json':'p1082_raw_2002','references_count':'p1082_references_2002','reference_p854_urls_json':'p1082_refs_2002'}),left_on='wikidata_qid',right_index=True,how='inner')
  pairs=pairs.merge(h10[['pop_i','statement_id','raw_source_file','raw_source_sha256','raw_tsv_line_number','raw_source_locator','raw_record_locator','raw_statement_json','references_count','reference_p854_urls_json']].rename(columns={'pop_i':'p1082_2010','statement_id':'p1082_statement_2010','raw_source_file':'p1082_file_2010','raw_source_sha256':'p1082_sha256_2010','raw_tsv_line_number':'p1082_line_2010','raw_source_locator':'p1082_locator_2010','raw_record_locator':'p1082_record_locator_2010','raw_statement_json':'p1082_raw_2010','references_count':'p1082_references_2010','reference_p854_urls_json':'p1082_refs_2010'}),left_on='wikidata_qid',right_index=True,how='inner')
  pairs=pairs[(pairs.pop_i_2002.astype(int)==pairs.p1082_2002.astype(int))&(pairs.p1082_2010.astype(int)-pairs.pop_i_2010.astype(int)).abs().le(10)].copy()
  pairs['p1082_2010_delta']=pairs.p1082_2010.astype(int)-pairs.pop_i_2010.astype(int);pairs['p1082_2010_exact']=pairs.p1082_2010_delta.eq(0)
 stats['rows matching both dated P1082 signatures']=len(pairs)
 stats['exact 2010 matches']=int(pairs.p1082_2010_exact.sum()) if len(pairs) else 0
 # Uniqueness applies against every possible old typed-key pair and every
 # current QID subject sharing that key, including cache-missing QIDs.
 if len(pairs):
  sig=['name_key','type_key','region_key','pop_i_2002','pop_i_2010']
  pairs['same_signature_source_pair_n']=pairs.groupby(sig,dropna=False).source_record_id_2002.transform('size')
  pairs['same_signature_qid_n']=pairs.groupby(sig,dropna=False).wikidata_qid.transform('nunique')
  pairs['key_qid_count']=pairs.apply(lambda r:len(key_qids.get((r.name_key,r.type_key,r.region_key),set())),axis=1)
  pairs['key_qid_cache_complete']=pairs.apply(lambda r:key_qids.get((r.name_key,r.type_key,r.region_key),set()).issubset(dual),axis=1)
  pairs=pairs[(pairs.old_pair_signature_count==1)&(pairs.same_signature_source_pair_n==1)&(pairs.same_signature_qid_n==1)&pairs.key_qid_cache_complete].copy()
 stats['signature-unique candidates before graph/evidence gates']=len(pairs)
 # Authoritative selected-source evidence; old district mismatch is a hold,
 # blank stays unknown. Aggregate, event, collision and actual identifier
 # conflicts stay held.
 ids=set(pairs.get('source_record_id_2002',pd.Series(dtype=str)).astype(str))|set(pairs.get('source_record_id_2010',pd.Series(dtype=str)).astype(str))|set(pairs.get('source_record_id',pd.Series(dtype=str)).astype(str))
 ev={}
 if ids:
  et=ds.dataset(EVID,format='parquet').to_table(columns=['source_record_id','source_evidence_json'],filter=ds.field('source_record_id').isin(ids));ev={str(z['source_record_id']):json.loads(z['source_evidence_json']) for z in et.to_pylist()}
 sourceholds=Counter();eligible=[];review=[]
 for r in pairs.to_dict('records'):
  endpoints=[str(r['source_record_id_2002']),str(r['source_record_id_2010']),str(r['source_record_id'])];why=[]
  # An explicit different historical district is not waived here. Blank is
  # unknown; aliases were normalized conservatively for comparison.
  d02=str(r.get('district_key_2002') or '');d10=str(r.get('district_key_2010') or '')
  if d02 and d10 and d02!='__blank_unknown__' and d10!='__blank_unknown__' and d02!=d10:why.append('explicit_2002_2010_district_difference_unresolved')
  roots=[uf.find(uf.idx[x]) if x in uf.idx else None for x in endpoints]
  oldpath=path(endpoints[0],endpoints[1])
  if None in roots:why.append('selected_vertex_missing')
  elif roots[0]!=roots[1]:why.append('old_2002_2010_not_already_accepted_pair')
  elif roots[0]==roots[2]:why.append('current_target_already_connected')
  elif uf.mask[roots[0]]&uf.mask[roots[2]]:why.append('year_constrained_collision')
  for eid in endpoints:
   e=ev.get(eid,{})
   if truth(e.get('is_federal_aggregate')) or truth(e.get('legacy_same_year_collision')) or e.get('legacy_verified_successor_settlement_id'):why.append('aggregate_collision_or_event:'+eid)
   if e.get('is_additive_settlement_record') is False:why.append('nonadditive:'+eid)
   if truth(e.get('legacy_identity_conflict')):
    try:cf=set(json.loads(e.get('legacy_identity_reasons') or '[]'))
    except Exception:cf={'unparsed_identity_conflict'}
    cf-={'administrative_conflict','ordinal_historical_identifier_hypothesis'}
    if cf:why.append('nonadministrative_identity_conflict:'+eid+':'+','.join(sorted(cf)))
  r['accepted_old_pair_path_decision_ids_json']=json.dumps([x['decision_id'] for x in oldpath],ensure_ascii=False)
  r['accepted_old_pair_path_edges_json']=json.dumps(oldpath,ensure_ascii=False)
  r['old_district_2002_context']=str(r.get('district_raw_2002') or '') or 'unknown_blank'
  r['old_district_2010_context']=str(r.get('district_raw_2010') or '') or 'unknown_blank'
  r['gate_status']='candidate_for_independent_review' if not why else 'held'
  r['hold_reasons_json']=json.dumps(why,ensure_ascii=False);review.append(r)
  if not why:eligible.append(r)
  for x in why:sourceholds[x]+=1
 # Deduplicate QID-pair candidates before conditional UF; never count a current
 # QID twice or use a candidate-only edge to bypass year constraints.
 eligible.sort(key=lambda r:(-int(r['pop_i_2002']+r['pop_i_2010']),str(r['source_record_id_2002']),str(r['source_record_id'])))
 applied=[];outcomes=Counter()
 for r in eligible:
  res=uf.union_ids(str(r['source_record_id_2002']),str(r['source_record_id']))
  outcomes[res]+=1;r['conditional_union_result']=res
  if res=='merged':applied.append(r)
 after=metrics(s,uf,point_ids)
 delta={y:{ax:{k:after[y][ax][k]-base[y][ax][k] for k in ('rows','population')} for ax in ('full_chain','joint_point_full_chain')} for y in base}
 # Missing local cache is reported as a QID batch request, never as “no claim”.
 missing=[]
 for key,group in current.groupby(['name_key','type_key','region_key']):
  if key not in residual_keyset:continue
  for qid in sorted(set(group.wikidata_qid.astype(str))-dual):
   row=group[group.wikidata_qid.astype(str)==qid].iloc[0]
   missing.append({'wikidata_qid':qid,'target_source_record_id':row.source_record_id,'settlement_name':row.source_settlement_name,'settlement_type':row.source_settlement_type,'region':row.source_region,'native_code':row.native_code,'reason':'current exact typed key participates in old-pair candidate funnel but one or both dated raw P1082 years are absent from local working-series cache; absence is not a negative claim'})
 ledger=[]
 for r in review:
  keep=['source_record_id_2002','source_record_id_2010','source_file_2002','source_file_2010','source_sheet_2002','source_sheet_2010','source_row_2002','source_row_2010','source_locator_2002','source_locator_2010','source_sha256_2002','source_sha256_2010','source_name_raw_2002','source_name_raw_2010','settlement_type_2002','settlement_type_2010','region_raw_2002','region_raw_2010','district_raw_2002','district_raw_2010','population_2002','population_2010','population_scope_2002','population_scope_2010','wikidata_qid','source_record_id','native_code','statement_id','value_raw','value_normalized','p1082_2002','p1082_statement_2002','p1082_file_2002','p1082_sha256_2002','p1082_line_2002','p1082_locator_2002','p1082_raw_2002','p1082_references_2002','p1082_refs_2002','p1082_2010','p1082_statement_2010','p1082_file_2010','p1082_sha256_2010','p1082_line_2010','p1082_locator_2010','p1082_raw_2010','p1082_references_2010','p1082_refs_2010','p1082_2010_delta','p1082_2010_exact','old_pair_signature_count','same_signature_source_pair_n','same_signature_qid_n','key_qid_count','key_qid_cache_complete','old_district_2002_context','old_district_2010_context','accepted_old_pair_path_decision_ids_json','accepted_old_pair_path_edges_json','gate_status','hold_reasons_json','conditional_union_result']
  ledger.append({k:r.get(k) for k in keep}|{'population_signature_used_as_corroboration_only':True,'identity_admitted':False,'population_values_replaced':False})
 pd.DataFrame(ledger).to_csv(OUT/'candidate_pair_ledger.csv',index=False)
 pd.DataFrame(applied).to_csv(OUT/'conditional_identity_edges.csv',index=False)
 pd.DataFrame(missing).to_csv(OUT/'missing_cached_p1082_candidate_qids.csv',index=False)
 invcols=['source_record_id_2002','source_record_id_2010','source_record_id','wikidata_qid','native_code','source_file_2002','source_sheet_2002','source_row_2002','source_file_2010','source_sheet_2010','source_row_2010','source_locator_2002','source_locator_2010','source_sha256_2002','source_sha256_2010','source_name_raw_2002','source_name_raw_2010','settlement_type_2002','settlement_type_2010','region_raw_2002','region_raw_2010','district_raw_2002','district_raw_2010','pop_i_2002','pop_i_2010','baseline_old_pair_residual_to_current','cached_single_valid_P1082_2002','cached_single_valid_P1082_2010','cached_two_year_P1082','p1082_2002','p1082_2010','source_pair_population_matches_P1082_2002','source_pair_population_matches_P1082_2010_exact','source_pair_population_matches_P1082_2010_within_10']
 residual_inventory[invcols].to_csv(OUT/'residual_oldpair_population_funnel.csv',index=False)
 all_inventory[invcols+['graph_gate_status']].to_csv(OUT/'oldpair_population_funnel.csv',index=False)
 summary={'status':'candidate_generation_only_no_identity_or_population_admissions','candidate_rule':'Current target is a selected additive physical 2021 settlement with an accepted coordinate from any approved provider, an exact unique P764=source 11-digit OKTMO binding, exact QID label/source name, and exact physical source type/region key. Historical exact typed-name/region 2002 and 2010 pair must already share a canonical accepted identity component; raw source populations must match one nondeprecated single year-precision P1082 claim exactly for 2002 and exactly or within ten persons for 2010. Signature must uniquely select one old pair and one current QID among every source row/QID sharing the typed key; missing QID claim years make key incomplete and produce a retrieval list. Explicit different old districts, source events, aggregates, collisions, nonadditive rows and unresolved non-administrative identity conflicts remain held. Population claims are corroboration only; no source population is changed.','baseline_graph_sha256':pins[str(G)]['sha256'],'baseline_point_uses_sha256':pins[str(P)]['sha256'],'baseline_coverage_reproduced':True,'baseline_checks':checks,'stage_counts':dict(stats),'source_evidence_and_residual_holds':dict(sourceholds),'candidates_after_all_gates':len(eligible),'simulated_nonredundant_identity_edges':len(applied),'conditional_union_outcomes':dict(outcomes),'conditional_full_graph_metric_delta':delta,'missing_cache_qids_for_candidate_typed_keys':len(missing),'inputs':pins}
 summary['outputs']={x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in sorted(OUT.iterdir()) if x.is_file()}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 rec={'status':summary['status'],'input_sha256':{k:v['sha256'] for k,v in pins.items()},'output_sha256':{x.name:sha(x) for x in sorted(OUT.iterdir()) if x.is_file() and x.name!='receipt.json'},'script':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__))}
 (OUT/'receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in {'inputs','outputs'}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
