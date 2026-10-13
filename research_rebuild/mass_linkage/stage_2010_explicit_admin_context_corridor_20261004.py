#!/usr/bin/env python3
"""Stage source-explicit 2010 district-context candidates against the sixth baseline."""
import csv, hashlib, json, re, sys, unicodedata
from collections import defaultdict, Counter
from pathlib import Path
import duckdb, xlrd

ROOT=Path('/workspace'); OUT=ROOT/'settlements-work/continuation_20261004/R4/2010_publisher_admin_context_residual_recovery_20261004/freeze_v5'; OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'russian-settlements-research/research_rebuild/mass_linkage'))
import recover_admin_context as profiles
RES=ROOT/'settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/joint_residual.parquet'
GRAPH=ROOT/'settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/accepted_identity_edges.parquet'
POINTS=ROOT/'settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/accepted_point_uses.parquet'
POP=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
EV=ROOT/'settlements-work/candidates/optimized_run/source_evidence.parquet'; RAW=ROOT/'settlements-raw'
PSTAT={'reviewed_rule_accepted','reviewed_extension_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_case_accepted'}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def norm(x):
 s=unicodedata.normalize('NFKC',str(x or '')).casefold().replace('ё','е').strip()
 s=re.sub(r'^\s*(?:г\.?|город|пгт\.?|п\.?г\.?т\.?|поселок городского типа|посёлок городского типа|поселок|посёлок|пос\.?|село|с\.?|деревня|д\.?|хутор|х\.?|станица|ст-ца)\s*','',s)
 return ' '.join(re.sub(r'[^0-9a-zа-я]+',' ',s).split())
def typ(x):
 s=unicodedata.normalize('NFKC',str(x or '')).casefold().replace('ё','е').strip(); s=re.sub(r'[.\s]+',' ',s).strip()
 return {'г':'город','город':'город','пгт':'пгт','поселок городского типа':'пгт','поселок':'поселок','п':'поселок','пос':'поселок','с':'село','село':'село','д':'деревня','деревня':'деревня','х':'хутор','хутор':'хутор','станица':'станица','ст ца':'станица','станция':'станция'}.get(s,s)
def core(x):
 s=norm(x);s=re.sub(r'\b(?:муниципальный|муниципальная|городской|городская|район|района|округ|округа)\b','',s);return ' '.join(s.split())
def writecsv(path,rows,fields=None):
 cols=list(fields or [])
 for r in rows:
  for k in r:
   if k not in cols:cols.append(k)
 with open(path,'w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction='raise');w.writeheader()
  for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})

c=duckdb.connect();c.execute('SET threads=1');c.execute("SET memory_limit='1000MB'")
old=c.execute(f"SELECT source_record_id,source_file,source_sheet,source_row,source_name_raw,settlement_name,settlement_type,region_norm,population,source_sha256,source_locator FROM read_parquet('{RES}') WHERE census_year=2010").fetchall()
cur=c.execute(f"SELECT source_record_id,settlement_name,settlement_type,region_norm,district_raw,municipality_raw,oktmo,population,source_file,source_row,source_sha256,source_locator FROM read_parquet('{POP}') WHERE census_year=2021").fetchall()
ck=defaultdict(list); codecounts=Counter()
for q in cur:ck[(norm(q[1]),typ(q[2]),norm(q[3]))].append(q);codecounts[str(q[6] or '').strip()]+=1
ids=[q[0] for q in old];
ev={i:json.loads(j) for i,j in c.execute(f"SELECT e.source_record_id,e.source_evidence_json FROM read_parquet('{EV}') e JOIN read_parquet('{RES}') r USING(source_record_id) WHERE r.census_year=2010").fetchall()}
curids={q[0] for vs in ck.values() for q in vs}
points=defaultdict(list)
for p in c.execute(f"SELECT target_source_record_id,latitude,longitude,coordinate_source,source_sha256,source_locator,coordinate_admission_status,coordinate_source_origin FROM read_parquet('{POINTS}') WHERE target_year='2021'").fetchall():
 if p[6] in PSTAT and p[1] is not None and p[2] is not None:points[p[0]].append(p)

# Rebuild accepted graph components and year occupancy before proposing any edge.
par={};sz={};
def find(x):
 if x not in par:par[x]=x;sz[x]=1
 while par[x]!=x:par[x]=par[par[x]];x=par[x]
 return x
def union(a,b):
 a=find(a);b=find(b)
 if a==b:return a
 if sz[a]<sz[b]:a,b=b,a
 par[b]=a;sz[a]+=sz[b];return a
for a,b in c.execute(f"SELECT from_source_record_id,to_source_record_id FROM read_parquet('{GRAPH}')").fetchall():union(a,b)
members=defaultdict(list)
for sid,yr,pop in c.execute(f"SELECT source_record_id,census_year,population FROM read_parquet('{POP}')").fetchall():members[find(sid)].append((sid,int(yr),int(pop or 0)))
years={r:set(y for _,y,_ in ms) for r,ms in members.items()}
pre_full={r for r,ys in years.items() if {2002,2010,2021}.issubset(ys)}

raw_hashes={};direct=[];holds=[];stage=[];rows_by_file=defaultdict(list)
for q in old:
 if q[1] in profiles.SHEET_PROFILES:rows_by_file[q[1]].append(q)
for fn,targets in rows_by_file.items():
 prof=profiles.SHEET_PROFILES[fn];path=RAW/fn;fsha=sha(path);raw_hashes[str(path)]=fsha
 book=xlrd.open_workbook(path,on_demand=True);sh=book.sheet_by_name(prof['sheet'])
 for q in targets:
  ri=int(q[3])-1; vals=[profiles._cell(sh,ri,col) for col in prof['district_cols']]; labels=[str(v).strip() for v in vals if profiles._nonblank(v)]
  if not labels:continue
  cand=ck[(norm(q[5]),typ(q[6]),norm(q[7]))]; ctx={core(x) for x in labels}-{''}; matched=[x for x in cand if core(x[4]) in ctx or core(x[5]) in ctx]
  row={'old_id':q[0],'from_source_record_id':q[0],'year':2010,'relation':'same_place_candidate','source_file':fn,'source_sha256_raw_workbook':fsha,'source_sheet':sh.name,'source_row_1based':int(q[3]),'source_locator':q[10] or f'{sh.name}!row{int(q[3])}','source_name_raw_selected':q[4],'source_name_raw_cell':str(profiles._cell(sh,ri,prof['name_cols'][0])),'name':q[5],'type':q[6],'region_norm':q[7],'population_2010':int(q[8] or 0),'source_district_cells_literal':labels,'admin_context_rule':'explicit nonblank publisher cells only; no inheritance; suffix-rendering normalization only','exact_current_key_candidate_count':len(cand),'matching_current_admin_context_count':len(matched),'current_candidates_json':[{'id':x[0],'district':x[4],'municipality':x[5],'native_oktmo':x[6]} for x in cand],'context_selected_current_candidates_json':[{'id':x[0],'district':x[4],'municipality':x[5],'native_oktmo':x[6]} for x in matched]}
  hard=[]; e=ev.get(q[0],{})
  if e.get('is_federal_aggregate') is True or re.search(r'federal|territor|aggregate',str(e.get('population_scope') or ''),re.I):hard.append('federal/territorial/aggregate')
  if e.get('is_additive_settlement_record') is False:hard.append('non-additive row')
  if e.get('legacy_same_year_collision') is True:hard.append('actual source-evidence same-year collision')
  if e.get('legacy_verified_successor_settlement_id'):hard.append('verified successor event')
  reasons=e.get('legacy_identity_reasons')
  try: reasons=json.loads(reasons) if isinstance(reasons,str) else (reasons or [])
  except Exception:reasons=['unparsed legacy reason']
  relation_only={'ordinal_historical_identifier_hypothesis','legacy_not_accepted','stale_target_entity','text_similarity_only'}
  if e.get('legacy_identity_conflict') and set(reasons)-relation_only:hard.append('legacy identity conflict includes non-quarantined reason: '+','.join(set(reasons)-relation_only))
  row['preserved_source_flags']={'legacy_identity_conflict':e.get('legacy_identity_conflict'),'legacy_identity_reasons':reasons,'legacy_same_year_collision':e.get('legacy_same_year_collision'),'legacy_verified_successor_settlement_id':e.get('legacy_verified_successor_settlement_id'),'is_additive_settlement_record':e.get('is_additive_settlement_record'),'population_scope':e.get('population_scope')}
  if len(matched)!=1:row['status']='held';row['hold_reason']='parent label has no unique exact current context match';holds.append(row);continue
  target=matched[0];row.update({'to_source_record_id':target[0],'target_current_district':target[4],'target_current_municipality':target[5],'target_native_oktmo_raw':target[6],'target_source_file':target[8],'target_source_row':target[9],'target_source_sha256':target[10],'target_locator':target[11]})
  if not (str(target[6] or '').strip().isdigit() and codecounts[str(target[6]).strip()]==1):hard.append('current native OKTMO literal is absent, nonnumeric, or not globally unique; observed width is preserved')
  if len(points.get(target[0],[]))>1:hard.append('target has multiple accepted current points')
  elif len(points.get(target[0],[]))==1:
   p=points[target[0]][0];row['accepted_current_point']={'latitude':p[1],'longitude':p[2],'source':p[3],'sha256':p[4],'locator':p[5],'status':p[6],'origin_kind':p[7]}
  else:row['coordinate_support_status']='identity candidate only; target has no accepted current point, so no point use or joint gain is staged'
  if hard:row['status']='held';row['hold_reason']='; '.join(hard);holds.append(row);continue
  a=find(q[0]);b=find(target[0]); ya=years.get(a,set());yb=years.get(b,set())
  if a==b:row['status']='held';row['hold_reason']='already connected in accepted sixth graph';holds.append(row);continue
  if ya&yb:row['status']='held';row['hold_reason']='candidate union creates duplicate census-year component';holds.append(row);continue
  row.update({'status':'candidate_only_review','rule':'2010 exact printed district/context selects one exact name+type+province current 2021 row; current literal native OKTMO is unique at its observed width; no code continuity, legal boundary continuity, or population comparability claim','graph_safety':'disjoint census years in sixth accepted graph'})
  stage.append(row);root=union(q[0],target[0]);members[root]=members.get(a,[])+members.get(b,[]);years[root]=ya|yb
 book.release_resources()

writecsv(OUT/'candidate_edges.csv',stage,fields=['from_source_record_id','to_source_record_id','relation','status','rule','source_file','source_sha256_raw_workbook','source_sheet','source_row_1based','source_locator','source_name_raw_selected','source_name_raw_cell','name','type','region_norm','population_2010','source_district_cells_literal','admin_context_rule','exact_current_key_candidate_count','matching_current_admin_context_count','current_candidates_json','context_selected_current_candidates_json','target_current_district','target_current_municipality','target_native_oktmo_raw','target_source_file','target_source_row','target_source_sha256','target_locator','accepted_current_point','coordinate_support_status','preserved_source_flags','graph_safety'])
writecsv(OUT/'disjoint_holds.csv',holds)
from collections import Counter
hold_reasons=Counter(x.get('hold_reason','') for x in holds)
hold_pop=defaultdict(int)
for x in holds:hold_pop[x.get('hold_reason','')]+=int(x.get('population_2010') or 0)
summary={'status':'candidate_only_no_admissions','generator':str(Path(__file__).resolve()),'generator_sha256':sha(Path(__file__)),'rule':'Exact source-published 2010 district/administrative-context cells, with only suffix-only rendering normalization, uniquely select an exact current name/type/province row; require the selected current row’s exact literal native OKTMO to be nonblank and globally unique at its observed width. A missing current accepted point leaves identity as a candidate but blocks any point-use and joint-gain claim. No code padding, historical code bridge, legal municipal continuity, or census-boundary equivalence is claimed. Blank source context is never inherited.','baseline_pins':{str(p):sha(p) for p in (RES,GRAPH,POINTS,POP,EV)},'raw_source_file_sha256':raw_hashes,'explicit_context_rows_replayed':len(stage)+len(holds),'explicit_context_population_2010_sum':sum(int(x.get('population_2010') or 0) for x in stage+holds),'candidate_edges':len(stage),'candidate_population_2010_endpoint_sum':sum(x['population_2010'] for x in stage),'identity_only_candidates_without_current_point':sum(not x.get('accepted_current_point') for x in stage),'disjoint_holds':len(holds),'hold_reason_counts':dict(hold_reasons),'hold_population_2010_by_reason':dict(hold_pop),'conditional_joint_gain':{'rows':0,'population':0,'reason':'Identity candidates have no accepted current point at the target endpoints; no point use is staged, so full-chain joint coverage cannot rise under this packet.'},'altai_2010_file_008':{'all_sixth_residual_rows':sum(q[1]=='data/raw/2010/008_342f3c208b_16._20Сиб_ФО_2010.xls' for q in old),'altai_residual_rows':sum(q[1]=='data/raw/2010/008_342f3c208b_16._20Сиб_ФО_2010.xls' and q[7]=='алтайский' for q in old),'altai_residual_population':sum(int(q[8] or 0) for q in old if q[1]=='data/raw/2010/008_342f3c208b_16._20Сиб_ФО_2010.xls' and q[7]=='алтайский'),'altai_explicit_direct_district_rows':0},'outputs':{}}
for n in ('candidate_edges.csv','disjoint_holds.csv'):
 p=OUT/n;summary['outputs'][n]={'sha256':sha(p),'rows':sum(1 for _ in open(p,encoding='utf-8'))-1}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
summary['summary_sha256']=sha(OUT/'summary.json')
(OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'out':str(OUT),'candidate_edges':summary['candidate_edges'],'candidate_population_2010_endpoint_sum':summary['candidate_population_2010_endpoint_sum'],'explicit_context_rows':summary['explicit_context_rows_replayed'],'explicit_context_population':summary['explicit_context_population_2010_sum'],'altai':summary['altai_2010_file_008'],'holds':summary['hold_reason_counts'],'hold_population':summary['hold_population_2010_by_reason'],'receipt_sha256':sha(OUT/'receipt.json')},ensure_ascii=False,indent=2))
