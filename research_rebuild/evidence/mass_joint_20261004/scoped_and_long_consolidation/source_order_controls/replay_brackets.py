#!/usr/bin/env python3
"""Reconstruct only the ten deterministic control brackets from accepted graph/raw sources."""
import json,re,pathlib,unicodedata
from collections import defaultdict,Counter
import duckdb,xlrd
ROOT=pathlib.Path('/workspace');OUT=ROOT/'settlements-work/continuation_20261004/root/source_order_parser_controls10_diagnostic'
SUM=ROOT/'settlements-work/continuation_20261004/R4/source_order_anchor_bracketed_localdistrict_final_20261004/summary.json'
SEL=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
GRAPH=ROOT/'settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/accepted_identity_edges.parquet'
RAW=ROOT/'settlements-raw'
def k(v):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(v or '')).casefold().replace('ё','е')).strip()
def rkey(v):
 text=k(v)
 text=re.sub(r'\s+(?:область|край|республика|автономная область|автономный округ)$','',text)
 return text.strip()
def ctype(v):
 z=k(v);return {'поселок городского типа':'пгт','поселок':'поселок','рабочий поселок':'рабочий поселок'}.get(z,z)
def stems(v):
 words=re.sub(r'["«»()]+',' ',k(v)); words=re.sub(r'\s+',' ',words).strip(' ,;: .\t\n').split()
 words=[w for w in words if w not in {'район','района','округ','округа','сельсоветы','сельский','городской'}]
 return {re.sub(r'(?:ского|цкого|ской|цкой|ский|цкий|ого|его|ому|ему|ая|яя|ое|ее|ый|ий|ой)$','',w) for w in words}
def dmatch(a,b):
 x,y=stems(a),stems(b);return bool(x and y and x.issubset(y))
summary=json.loads(SUM.read_text());controls=summary['fixed_independently_approved_controls']['deterministic_controls'];pairs=[(r['from_2010_id'],r['to_2002_id']) for r in controls]
con=duckdb.connect(':memory:');con.execute('SET threads=1');con.execute("SET memory_limit='1GB'")
selected=con.execute(f"SELECT source_record_id,try_cast(census_year AS INT),source_file,source_sheet,try_cast(source_row AS INT),settlement_name,settlement_type,region_raw,district_raw,try_cast(population AS BIGINT) FROM read_parquet('{SEL}') WHERE try_cast(census_year AS INT) IN (2002,2010,2021)").fetchall()
byid={r[0]:r for r in selected}; targetgroups=set()
for id10,id02 in pairs:
 a=byid[id10];b=byid[id02];targetgroups.add((b[2],str(b[3]),a[2],str(a[3])))
# Rebuild connected components using only the producer's accepted-edge status/projection sets.
edge_rows=con.execute(f"SELECT from_source_record_id,to_source_record_id FROM read_parquet('{GRAPH}') WHERE relation='same_place' AND decision_status IN ('checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted','case_review_accepted','independent_case_review_accepted','accepted_case_specific') AND selection_projection_status IN ('active_endpoints_selected','active_after_reviewed_publication_binding_migration')").fetchall()
parent={};size={}
def find(x):
 if x not in parent:parent[x]=x;size[x]=1
 while x!=parent[x]:parent[x]=parent[parent[x]];x=parent[x]
 return x
def union(a,b):
 a=find(a);b=find(b)
 if a==b:return
 if size[a]<size[b]:a,b=b,a
 parent[b]=a;size[a]+=size[b]
for a,b in edge_rows:union(a,b)
comps=defaultdict(list)
for r in selected:comps[find(r[0])].append(r)
# Selected row groups, UF 2002-10 anchor pairs, parent context.
anchors=defaultdict(list)
for cr in comps.values():
 olds=[x for x in cr if x[1]==2002];news=[x for x in cr if x[1]==2010]
 if len(olds)!=1 or len(news)!=1:continue
 o,n=olds[0],news[0]
 group=(o[2],str(o[3]),n[2],str(n[3]))
 if group not in targetgroups or rkey(o[7])!=rkey(n[7]) or o[4] is None or n[4] is None:continue
 anchors[group].append((o,n))
# cache raw books/sheets; derive parent headings once for each old sheet
sheets={};parents={}
def get(year,rel,sname):
 key=(year,rel,str(sname))
 if key in sheets:return sheets[key]
 wb=xlrd.open_workbook(str(RAW/rel),on_demand=True)
 try:sh=wb.sheet_by_name(str(sname))
 except Exception:sh=wb.sheet_by_index(int(sname))
 sheets[key]=(wb,sh);return sheets[key]
def parmap(file,sheet):
 key=(file,str(sheet))
 if key in parents:return parents[key]
 wb,sh=get(2002,file,sheet);heads=[]
 for ri in range(sh.nrows):
  for ci,v in enumerate(sh.row_values(ri)):
   lab=str(v or '').strip()
   if 'район' in k(lab):heads.append((ri+1,ci+1,lab))
 out={}
 for rr in range(1,sh.nrows+1):
  prev=[h for h in heads if h[0]<=rr];out[rr]=prev[-1] if prev else None
 parents[key]=out;return out
# Independently parse exactly the recognized type prefix; no regex-pattern secondary-strip.
prefix={'город':r'(?:город|г\.)','посёлок':r'(?:пос[её]лок|п\.)','поселок':r'(?:пос[её]лок|п\.)','рабочий посёлок':r'(?:рабочий пос[её]лок|рп\.)','пгт':r'(?:пгт|пос[её]лок городского типа)','село':r'(?:село|с\.)','деревня':r'(?:деревня|д\.)','хутор':r'(?:хутор|х\.)','станица':r'(?:станица|ст-?ца\.?|ст\.)'}
type_re=re.compile(r'^\s*('+'|'.join(sorted(set(prefix.values()),key=len,reverse=True))+r')\s*',re.I)
def parse_cell(cells,namecol,typecol):
 namefield=str(cells[namecol-1] or '').strip() if len(cells)>=namecol else ''
 typefield=str(cells[typecol-1] or '').strip() if typecol and len(cells)>=typecol else ''
 source=typefield or namefield;m=type_re.match(source) if source else None
 if not m:return {'name':k(namefield),'type':None,'literal':source}
 suffix=source[m.end():].strip(' .,:;—–-')
 typevalue=next((t for t,p in prefix.items() if re.match(r'^\s*'+p+r'\s*',source,re.I)),None)
 # In the separate-column case, the separate type field can be just `село`;
 # the name field may still itself carry a type prefix. Normalize that with the regex value.
 if not suffix:
  full=re.sub(r'^\s*('+'|'.join(sorted(set(prefix.values()),key=len,reverse=True))+r')\s*','',namefield,flags=re.I)
  namevalue=full
 else:namevalue=suffix
 return {'name':k(namevalue) or None,'type':ctype(typevalue) if typevalue else None,'literal':source,'raw_name_field':namefield,'raw_type_field':typefield}
# Use profile columns reported for each target by the diagnostic's source-context index replay.
profiles={}
import csv
profile_rows=defaultdict(Counter)
context=ROOT/'settlements-work/continuation_20261004/root/R4/source_order_context_all_residual_2010_20261004/supplemental_raw_context_index_20261004/seven_row_source_context.csv'
with context.open(encoding='utf-8-sig',newline='') as f:
 for x in csv.DictReader(f):
  yy=int(x['year']);g=(yy,x['source_file'],str(x['source_sheet']))
  if not any(g==(2002,a,b) or g==(2010,c,d) for a,b,c,d in targetgroups):continue
  def cnum(s):
   m=re.search(r'R\d+C(\d+)',s or '')
   return int(m.group(1)) if m else None
  n,t=cnum(x.get('raw_name_cell_locator','')),cnum(x.get('raw_type_cell_locator',''))
  if n:profile_rows[g][(t,n)]+=1
for g,c in profile_rows.items():
 ranked=c.most_common();profiles[g]=(ranked[0][0] if ranked and (len(ranked)==1 or ranked[0][1]>ranked[1][1]) else None)
result=[]
for id10,id02 in pairs:
 new=byid[id10];old=byid[id02];g=(old[2],str(old[3]),new[2],str(new[3]));pmap=parmap(old[2],old[3]);
 good=[]
 for a,b in anchors[g]:
  par=pmap.get(a[4])
  if par and dmatch(a[8],par[2]):good.append((a,b,par))
 # Per producer: partition by district stems, source-order sort, consecutive anchors in old row order; select interval containing both target rows.
 runs=defaultdict(list)
 for a,b,par in good:runs[tuple(sorted(stems(a[8])))].append((a,b,par))
 selected_bracket=None
 for dk,run in runs.items():
  run.sort(key=lambda q:(q[0][4],q[0][0]))
  for l,r in zip(run,run[1:]):
   if l[0][4]<r[0][4] and l[1][4]<r[1][4] and l[0][4]<old[4]<r[0][4] and l[1][4]<new[4]<r[1][4]:
    selected_bracket=(l,r,dk);break
  if selected_bracket:break
 targetdk=tuple(sorted(stems(old[8])))
 if not selected_bracket:
  result.append({'source_2002':id02,'source_2010':id10,'name':old[5],'type':old[6],'bracket':'NOT_FOUND','old_raw_pair_count':None,'new_raw_pair_count':None,'reason':'did not reconstruct approved inside-bracket anchors'});continue
 l,r,dk=selected_bracket
 profile02=profiles.get((2002,g[0],g[1]));profile10=profiles.get((2010,g[2],g[3]))
 oldwb,oldsh=get(2002,g[0],g[1]);newwb,newsh=get(2010,g[2],g[3])
 def block(sh,a,b,prof):
  out=[]
  if not prof:return out
  typecol,namecol=prof
  for ri in range(int(a),int(b)-1): # source rows strictly after 1-based a through before b
   c=sh.row_values(ri) # ri index a maps row a+1
   out.append((ri+1,parse_cell(c,namecol,typecol),c))
  return out
 oblock=block(oldsh,l[0][4],r[0][4],profile02);nblock=block(newsh,l[1][4],r[1][4],profile10)
 token=(k(old[5]),ctype(old[6]))
 om=[x for x in oblock if (x[1]['name'],x[1]['type'])==token];nm=[x for x in nblock if (x[1]['name'],x[1]['type'])==token]
 selected_bracket_info={'left2002':l[0][0],'right2002':r[0][0],'left2010':l[1][0],'right2010':r[1][0],'rows02':[l[0][4],r[0][4]],'rows10':[l[1][4],r[1][4]],'local_anchor_count':len(good)}
 result.append({'source_2002':id02,'source_2010':id10,'name':old[5],'type':old[6],'old_year_population':old[9],'new_year_population':new[9],'bracket':selected_bracket_info,'profile_2002':profile02,'profile_2010':profile10,'old_raw_pair_count':len(om),'old_rows':[(x[0],x[1],x[2][:8]) for x in om],'new_raw_pair_count':len(nm),'new_rows':[(x[0],x[1],x[2][:8]) for x in nm]})
for wb,sh in sheets.values():
 try:wb.release_resources()
 except:pass
(OUT/'replayed_bracket_counts.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
for x in result:print(x['name'],x['type'],'old',x.get('old_raw_pair_count'),'new',x.get('new_raw_pair_count'))
