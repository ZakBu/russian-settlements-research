#!/usr/bin/env python3
"""Candidate-only source-order corridor inventory over all sixth residual 2010 rows."""
import csv, hashlib, json, re, unicodedata
from collections import defaultdict, Counter
from pathlib import Path
import duckdb

ROOT=Path('/workspace')
OUT=ROOT/'settlements-work/continuation_20261004/root/R4/source_order_context_all_residual_2010_20261004'
OUT.mkdir(parents=True,exist_ok=True)
F=ROOT/'settlements-delivery/continuation-consolidated-20261003'
RES=ROOT/'settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/joint_residual.parquet'
GRAPH=ROOT/'settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/accepted_identity_edges.parquet'
POINTS=ROOT/'settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/accepted_point_uses.parquet'
EV=ROOT/'settlements-work/candidates/optimized_run/source_evidence.parquet'
SEL=F/'selected_observations.parquet'
ACCEPTED={'checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted','case_review_accepted','independent_case_review_accepted','accepted_case_specific'}
PSTATUS={'reviewed_rule_accepted','reviewed_extension_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_case_accepted'}
REL_ONLY={'ordinal_historical_identifier_hypothesis','legacy_not_accepted','stale_target_entity','text_similarity_only'}
PROPER={'город','пгт','посёлок','поселок','село','деревня','хутор','станица','аул','аал','слобода','арбан','починок','заимка','выселок','местечко','станция','разъезд','кишлак','улус','кордон','мыза','платформа','кишла́к'}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def key(v):
 s=unicodedata.normalize('NFKC',str(v or '')).casefold().replace('ё','е').strip()
 return ' '.join(re.sub(r'[^0-9a-zа-я]+',' ',s).split())
def parse_reasons(v):
 if not v:return []
 try:return json.loads(v) if isinstance(v,str) else list(v)
 except Exception:return ['unparsed']

c=duckdb.connect();c.execute('SET threads=1');c.execute("SET memory_limit='1500MB'")
selected=c.execute(f"SELECT source_record_id,census_year,settlement_name,settlement_type,region_raw,district_raw,municipality_raw,population,population_scope,population_value_quality,source_file,source_sheet,source_row,source_native_id,source_name_raw,source_population_raw,source_sha256,source_locator,entity_grain_status,is_additive_settlement_record,oktmo,okato FROM read_parquet('{SEL}') WHERE census_year IN (2002,2010,2021)").fetchall()
byid={r[0]:r for r in selected}
def token(r):return (key(r[2]),key(r[3]))
res2010=c.execute(f"SELECT source_record_id,population,source_file,source_row FROM read_parquet('{RES}') WHERE census_year=2010").fetchall()
resid={r[0]:r for r in res2010};resids=set(resid)
ev={i:json.loads(j) for i,j in c.execute(f"SELECT source_record_id,source_evidence_json FROM read_parquet('{EV}') WHERE census_year=2010").fetchall()}

# Accepted 2002<->2010 links form independent window anchors; no legacy ordinal logic.
accepted_pairs=set();edges=[]
for r in c.execute(f"SELECT from_source_record_id,try_cast(from_year as int),to_source_record_id,try_cast(to_year as int) FROM read_parquet('{GRAPH}') WHERE relation='same_place' AND decision_status IN ({','.join(repr(x) for x in sorted(ACCEPTED))})").fetchall():
 a,ay,b,by=r
 if {ay,by}=={2002,2010}:
  i02,i10=(a,b) if ay==2002 else (b,a);accepted_pairs.add((i02,i10));edges.append((a,b))

# Build accepted components and source-year occupancy.
parent={};size={}
def find(x):
 if x not in parent:parent[x]=x;size[x]=1
 while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
 return x
def union(a,b):
 a=find(a);b=find(b)
 if a==b:return a
 if size[a]<size[b]:a,b=b,a
 parent[b]=a;size[a]+=size[b];return a
for a,b in c.execute(f"SELECT from_source_record_id,to_source_record_id FROM read_parquet('{GRAPH}') WHERE relation='same_place' AND decision_status IN ({','.join(repr(x) for x in sorted(ACCEPTED))})").fetchall():union(a,b)
comp_members=defaultdict(list)
for r in selected:comp_members[find(r[0])].append(r)
comp_years={root:{int(x[1]) for x in rows} for root,rows in comp_members.items()}
point_ids={r[0] for r in c.execute(f"SELECT DISTINCT target_source_record_id FROM read_parquet('{POINTS}') WHERE try_cast(target_year as double)=2021 AND coordinate_admission_status IN ({','.join(repr(x) for x in sorted(PSTATUS))})").fetchall()}
code_counts=Counter(str(r[20] or '').strip() for r in selected if r[1]==2021)

# For every anchored source-file pair, exact 5/7 typed-name windows generate
# associations. The focal pair itself is excluded from the anchor threshold.
src_by=defaultdict(list)
for r in selected:
 if r[1] in (2002,2010) and r[12] is not None:
  src_by[(int(r[1]),key(r[4]),r[10],r[11])].append({'id':r[0],'year':int(r[1]),'region':key(r[4]),'file':r[10],'sheet':r[11],'row':float(r[12]),'name':key(r[2]),'type':key(r[3]),'district':r[5],'pop':int(r[7] or 0),'record':r})
pair_groups=defaultdict(set)
for id02,id10 in accepted_pairs:
 a=byid.get(id02);b=byid.get(id10)
 if not a or not b or key(a[4])!=key(b[4]):continue
 pair_groups[(key(a[4]),a[10],a[11],b[10],b[11])].add((id02,id10))
anchor_keys=set(accepted_pairs)
mapping5=defaultdict(list);mapping7=defaultdict(list);run_stats=Counter();pair_stats=defaultdict(lambda:{'windows5':0,'windows7':0,'focal5':set(),'focal7':set()})
for gkey,amap in pair_groups.items():
 region,file02,sheet02,file10,sheet10=gkey
 d02=sorted(src_by.get((2002,region,file02,sheet02),[]),key=lambda x:x['row'])
 d10=sorted(src_by.get((2010,region,file10,sheet10),[]),key=lambda x:x['row'])
 if not d02 or not d10:continue
 for k,min_anchor,label,mapping in [(5,2,'5',mapping5),(7,3,'7',mapping7)]:
  idx=defaultdict(list)
  for j in range(len(d02)-k+1):
   seq=tuple((x['name'],x['type']) for x in d02[j:j+k])
   if all(a and b for a,b in seq):idx[seq].append(j)
  for i in range(len(d10)-k+1):
   seq=tuple((x['name'],x['type']) for x in d10[i:i+k])
   if not all(a and b for a,b in seq):continue
   for j in idx.get(seq,[]):
    pairs=[(d02[j+n]['id'],d10[i+n]['id']) for n in range(k)]
    anchors=[p for p in pairs if p in anchor_keys]
    if len(anchors)<min_anchor:continue
    run_stats['run'+label]+=1;pair_stats[gkey]['windows'+label]+=1
    for n,(id02,id10) in enumerate(pairs):
     if id10 not in resids or (id02,id10) in anchor_keys:continue
     # Require independent accepted anchors other than focal position.
     n_other=sum(p in anchor_keys for z,p in enumerate(pairs) if z!=n)
     if n_other<min_anchor:continue
     mapping[id10].append({'id02':id02,'anchors_total':len(anchors),'anchors_excluding_focal':n_other,'window_size':k,'file02':d02[j]['file'],'file10':d10[i]['file'],'sheet02':d02[j]['sheet'],'sheet10':d10[i]['sheet'],'start02':d02[j]['row'],'start10':d10[i]['row'],'district02':d02[j+n]['district'],'focal_row02':d02[j+n]['row'],'focal_row10':d10[i+n]['row'],'anchor_pairs':[{'id02':a,'id10':b} for a,b in anchors]})
     pair_stats[gkey]['focal'+label].add(id10)

def summary_funnel(mapping):
 unique={sid:vals for sid,vals in mapping.items() if len({v['id02'] for v in vals})==1}
 ambiguous={sid:vals for sid,vals in mapping.items() if len({v['id02'] for v in vals})>1}
 out={'distinct_residual2010_focals':len(mapping),'rows_unique_2002_mapping':len(unique),'unique_population_2010':sum(int(resid[s][1] or 0) for s in unique),'rows_ambiguous_2002_mapping':len(ambiguous),'ambiguous_population_2010':sum(int(resid[s][1] or 0) for s in ambiguous)}
 codepoint=events=graphsafe=0; eligible=[]; reason=Counter()
 for sid,vals in unique.items():
  id02=next(iter({v['id02'] for v in vals})); r02=byid.get(id02);r10=byid.get(sid)
  if not r02 or not r10:reason['missing selected endpoint']+=1;continue
  if not r02[5] or not str(r02[5]).strip():reason['old2002 district blank']+=1;continue
  evv=ev.get(sid,{})
  ers=parse_reasons(evv.get('legacy_identity_reasons'))
  if evv.get('is_federal_aggregate') is True or evv.get('is_additive_settlement_record') is False or evv.get('legacy_same_year_collision') is True or evv.get('legacy_verified_successor_settlement_id'):
   reason['event/nonadditive/federal/collision']+=1;continue
  if evv.get('legacy_identity_conflict') and set(ers)-REL_ONLY:
   reason['nonquarantined legacy conflict']+=1;continue
  c02=find(id02);cm=comp_members.get(c02,[])
  currows=[x for x in cm if int(x[1])==2021 and str(x[20] or '').strip() and str(x[20]).strip().isdigit() and x[3] in PROPER and str(x[0]) in point_ids]
  # Current code is required to be literal and globally unique, with observed width preserved.
  currows=[x for x in currows if code_counts[str(x[20]).strip()]==1]
  if len(currows)!=1:reason['no unique proper native-coded accepted-point 2021 endpoint']=1+reason['no unique proper native-coded accepted-point 2021 endpoint'];continue
  codepoint+=1
  c10=find(sid)
  if c10==c02:reason['already linked 2010 to 2002-current component']+=1;continue
  if comp_years.get(c10,set())&comp_years.get(c02,set()):reason['duplicate-year graph union']=1+reason['duplicate-year graph union'];continue
  graphsafe+=1
  eligible.append({'from_2010_id':sid,'to_2002_id':id02,'accepted_current_2021_id':currows[0][0],'population_2010':int(r10[7] or 0),'source_file_2010':r10[10],'source_sheet_2010':r10[11],'source_row_2010':r10[12],'name_2010':r10[2],'type_2010':r10[3],'region_2010':r10[4],'source_file_2002':r02[10],'source_sheet_2002':r02[11],'source_row_2002':r02[12],'name_2002':r02[2],'type_2002':r02[3],'region_2002':r02[4],'district_raw_2002':r02[5],'current_native_oktmo_raw':currows[0][20],'current_native_oktmo_width':len(str(currows[0][20]).strip()),'anchor_windows_5_json':json.dumps(vals,ensure_ascii=False),'legacy_identity_reasons_2010':json.dumps(ers,ensure_ascii=False),'same_year_event_guard':'passed_source_evidence_preflight','graph_safety':'different sixth graph components, disjoint source years'})
 out.update({'rows_with_old2002district':sum(1 for x in eligible),'rows_with_current_proper_native_code_and_accepted_point':codepoint,'graph_safe_rule_candidates':graphsafe,'graph_safe_population_2010':sum(x['population_2010'] for x in eligible),'filters':dict(reason)})
 return out,eligible

f5,cand5=summary_funnel(mapping5);f7,cand7=summary_funnel(mapping7)
# Current actual full-joint residual scope controls the candidate universe.
allres={'rows':len(res2010),'population':sum(int(x[1] or 0) for x in res2010)}
pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in (SEL,RES,GRAPH,POINTS,EV)}
summary={'status':'pre_raw_source_order_mass_quantification_candidate_only','source_order_used_as_identity_proof':False,'old_reason_subset_used':False,'all_residual_2010_cohort':allres,'rule5_exact_name_type_run':f5,'rule7_exact_name_type_run':f7,'rule_definition':'Identical exact typed-name windows within one proper province and same source-file/sheet pair for 2002/2010. Five-row rule requires at least two already accepted cross-year same_place anchors excluding the focal pair; seven-row rule requires at least three. Focal 2002 member must have a nonblank selected historic district and an accepted 2002–2021 component containing exactly one 2021 proper observation with unique literal native OKTMO and an accepted current point; new 2010→2021 union must be graph-safe and evidence-event/collision gates must pass. This is only an inventory, not admission.', 'limitations':['No raw 2002/2010 workbook replay has occurred in this stage; selected row IDs/types/order are only a cheap funnel.','No 2010 district is inferred or written.','No canonical graph or coordinate ledger is changed.','Actual raw-source run proof and fixed risk-aware review must precede any edge staging.'],'inputs':pins,'script_sha256':sha(Path(__file__))}
for name,rows in [('provisional_5row_candidates.csv',cand5),('provisional_7row_candidates.csv',cand7)]:
 p=OUT/name
 fields=list(rows[0]) if rows else ['from_2010_id','to_2002_id','accepted_current_2021_id','population_2010','source_file_2010','source_row_2010','source_file_2002','source_row_2002','district_raw_2002','current_native_oktmo_raw','anchor_windows_5_json']
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
 summary.setdefault('outputs',{})[name]={'sha256':sha(p),'rows':len(rows)}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
summary['receipt_sha256']=sha(OUT/'summary.json')
(OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'residual2010':allres,'5row':f5,'7row':f7,'out':str(OUT),'receipt':sha(OUT/'receipt.json')},ensure_ascii=False,indent=2))
