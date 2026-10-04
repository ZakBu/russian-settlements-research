#!/usr/bin/env python3
"""AST-extract and run the producer's typed_raw_rows exactly on ten bounded blocks."""
import ast,csv,json,re,pathlib,unicodedata
from collections import Counter,defaultdict
from types import SimpleNamespace
import xlrd
ROOT=pathlib.Path('/workspace');OUT=ROOT/'settlements-work/continuation_20261004/root/source_order_parser_controls10_diagnostic'
SCRIPT=ROOT/'russian-settlements-research/research_rebuild/mass_linkage/stage_anchor_bracketed_source_block_20261004.py'
RULES=ROOT/'russian-settlements-research/research_rebuild/mass_linkage/review_source_order_context_reserve_20261004.py'
RAW=ROOT/'settlements-raw';CTX=ROOT/'settlements-work/continuation_20261004/root/R4/source_order_context_all_residual_2010_20261004/supplemental_raw_context_index_20261004/seven_row_source_context.csv'
def key(v):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(v or '')).casefold().replace('ё','е')).strip()
def ctype(v):
 z=key(v);return {'поселок городского типа':'пгт','поселок':'поселок','рабочий поселок':'рабочий поселок'}.get(z,z)
def val(x):return '' if x is None else str(x).strip()
def txt(x):return '' if x is None else str(x).strip()
# Pull AST objects from source without importing the mass-stage script.
tree=ast.parse(SCRIPT.read_text(encoding='utf-8'));rtype=None;canon=None;typed=None
for node in tree.body:
 if isinstance(node,ast.FunctionDef) and node.name=='typed_raw_rows':typed=node
 if isinstance(node,ast.FunctionDef) and node.name=='canonical_type':canon=node
rules=ast.parse(RULES.read_text(encoding='utf-8'));prefix=None;parsefn=None
for node in rules.body:
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TYPE_PREFIX' for t in node.targets):prefix=ast.literal_eval(node.value)
 if isinstance(node,ast.FunctionDef) and node.name=='parse_type_label':parsefn=node
assert typed and canon and prefix and parsefn
ns={'k':key,'val':val,'txt':txt,'re':re}
exec(compile(ast.Module(body=[canon],type_ignores=[]),str(SCRIPT),'exec'),ns)
ns['TYPE_PREFIX']=prefix
exec(compile(ast.Module(body=[parsefn],type_ignores=[]),str(RULES),'exec'),ns)
# Recreate rawrules TYPE_RE exactly from its literal TYPE_PREFIX definition.
type_re=re.compile(r'^\s*('+'|'.join(sorted(set(prefix.values()),key=len,reverse=True))+r')\s*',re.I)
rawrules=SimpleNamespace(TYPE_PREFIX=prefix,TYPE_RE=type_re,parse_type_label=ns['parse_type_label'],_source_label_key=key)
ns['rawrules']=rawrules;ns['rawtyped_cache']={}
# Reconstitute profile counts exactly from pinned current context index (no producer top-level import).
profile_counts=defaultdict(Counter)
with CTX.open(encoding='utf-8-sig',newline='') as f:
 for row in csv.DictReader(f):
  try:y=int(row['year'])
  except:continue
  def col(v):
   m=re.search(r'R\d+C(\d+)',v or '')
   return int(m.group(1)) if m else None
  nc=col(row.get('raw_name_cell_locator'));tc=col(row.get('raw_type_cell_locator'))
  if nc:profile_counts[(y,row['source_file'],str(row['source_sheet']))][(tc,nc)]+=1
def label_profile(y,rel,sheet):
 c=profile_counts.get((int(y),rel,str(sheet)),Counter())
 if not c:return None
 ranked=c.most_common()
 if len(ranked)>1 and ranked[0][1]==ranked[1][1]:return {'status':'ambiguous_column_profile','alternatives':ranked}
 return {'status':'reviewed_context_column_profile','type_col':ranked[0][0][0],'name_col':ranked[0][0][1],'support_rows':ranked[0][1],'alternatives':ranked}
ns['label_profile']=label_profile
exec(compile(ast.Module(body=[typed],type_ignores=[]),str(SCRIPT),'exec'),ns)
producer_typed_raw_rows=ns['typed_raw_rows']
controls=json.loads((OUT/'replayed_bracket_counts.json').read_text())
results=[];bookcache={}
for c in controls:
 if c['bracket']=='NOT_FOUND':continue
 for year,rel,sheet,lo,hi,expectedname,expectedtype,role in [
  (2002,c['source_2002'].split(':')[1].split(':')[0],None,None,None,c['name'],c['type'],'old'),
  (2010,c['source_2010'].split(':')[1].split(':')[0],None,None,None,c['name'],c['type'],'new')]:pass
 # Use source ids from the fixed summary to retain exact path/sheet/row metadata.
 # The exact row descriptors and block counts from first replay are in this JSON.
# Since summary supplies metadata in a separate artifact, recover it by DuckDB narrow selection.
import duckdb
sumdata=json.loads((ROOT/'settlements-work/continuation_20261004/R4/source_order_anchor_bracketed_localdistrict_final_20261004/summary.json').read_text())
ids=[]
for x in sumdata['fixed_independently_approved_controls']['deterministic_controls']:ids += [x['to_2002_id'],x['from_2010_id']]
sel=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet';db=duckdb.connect(':memory:')
byid={r[0]:r for r in db.execute(f"select source_record_id,try_cast(census_year as int),source_file,source_sheet,try_cast(source_row as int),settlement_name,settlement_type from read_parquet('{sel}') where source_record_id in ({','.join('?' for _ in ids)})",ids).fetchall()}
for c in controls:
 if c['bracket']=='NOT_FOUND':continue
 ctl=next(x for x in sumdata['fixed_independently_approved_controls']['deterministic_controls'] if x['to_2002_id']==c['source_2002'] and x['from_2010_id']==c['source_2010'])
 for role,sid,year,lo,hi in [('old',c['source_2002'],2002,*c['bracket']['rows02']),('new',c['source_2010'],2010,*c['bracket']['rows10'])]:
  r=byid[sid];keywb=(year,r[2],str(r[3]))
  if keywb not in bookcache:
   wb=xlrd.open_workbook(str(RAW/r[2]),on_demand=True)
   try:sh=wb.sheet_by_name(str(r[3]))
   except Exception:sh=wb.sheet_by_index(int(r[3]))
   bookcache[keywb]=(wb,sh)
  wb,sh=bookcache[keywb]
  descriptors=producer_typed_raw_rows(sh,year,r[2],r[3])
  matches=[x for x in descriptors if lo<x['row']<hi and x.get('name')==key(c['name']) and x.get('type')==ctype(c['type'])]
  target=next(x for x in descriptors if x['row']==r[4])
  results.append({'source_id':sid,'control_name':c['name'],'control_type':c['type'],'role':role,'profile':label_profile(year,r[2],r[3]),'exact_target_row_descriptor':target,'producer_exact_token_count_inside_control_bracket':len(matches),'producer_matching_row_numbers_inside_control_bracket':[x['row'] for x in matches],'producer_target_exact_pair':target.get('name')==key(c['name']) and target.get('type')==ctype(c['type'])})
for wb,sh in bookcache.values():wb.release_resources()
(OUT/'exact_producer_function_replay.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print('rows',len(results),'producer target exact',sum(x['producer_target_exact_pair'] for x in results),'bracket raw token counts',Counter(x['producer_exact_token_count_inside_control_bracket'] for x in results))
for x in results:print(x['role'],x['control_name'],x['producer_target_exact_pair'],x['producer_exact_token_count_inside_control_bracket'],x['producer_matching_row_numbers_inside_control_bracket'],x['profile'])
