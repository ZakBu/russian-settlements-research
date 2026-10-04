#!/usr/bin/env python3
"""Independent, bounded replay of the fixed ten source-order controls."""
import ast,csv,json,re,unicodedata,hashlib,pathlib
from collections import Counter,defaultdict
import duckdb,xlrd
ROOT=pathlib.Path('/workspace')
OUT=ROOT/'settlements-work/continuation_20261004/root/source_order_parser_controls10_diagnostic'
SUMMARY=ROOT/'settlements-work/continuation_20261004/R4/source_order_anchor_bracketed_localdistrict_final_20261004/summary.json'
SCRIPT=ROOT/'russian-settlements-research/research_rebuild/mass_linkage/stage_anchor_bracketed_source_block_20261004.py'
RAW_CONTEXT=ROOT/'settlements-work/continuation_20261004/root/R4/source_order_context_all_residual_2010_20261004/supplemental_raw_context_index_20261004/seven_row_source_context.csv'
SEL=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
RAW=ROOT/'settlements-raw'

def key(v):
 if v is None:return ''
 return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е')).strip()
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
# Read the literal regex dictionary and canonical_type function source without importing the producer.
tree=ast.parse(SCRIPT.read_text(encoding='utf-8'))
ns={}
for node in tree.body:
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PROPER' for t in node.targets):
  pass
 if isinstance(node,ast.FunctionDef) and node.name=='canonical_type':
  exec(compile(ast.Module(body=[node],type_ignores=[]),str(SCRIPT),'exec'),{'k':key},ns)
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TYPE_RE' for t in node.targets):
  pass
# The parser imports its regex rules from the separate review helper; AST literal extraction is bounded.
RULES=ROOT/'russian-settlements-research/research_rebuild/mass_linkage/review_source_order_context_reserve_20261004.py'
tree2=ast.parse(RULES.read_text(encoding='utf-8'));type_prefix=None
for node in tree2.body:
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TYPE_PREFIX' for t in node.targets):
  type_prefix=ast.literal_eval(node.value);break
assert type_prefix
canonical_type=ns['canonical_type']
type_re=re.compile(r'^\s*('+'|'.join(sorted(set(type_prefix.values()),key=len,reverse=True))+r')\s*',re.I)
# fixed 10 pairs and selected endpoints only
summary=json.loads(SUMMARY.read_text(encoding='utf-8'))
controls=summary['fixed_independently_approved_controls']['deterministic_controls']
assert len(controls)==10
pairs=[(x['from_2010_id'],x['to_2002_id']) for x in controls]
ids=[z for pair in pairs for z in pair]
con=duckdb.connect(':memory:');con.execute('SET threads=1');con.execute("SET memory_limit='1GB'")
rows=con.execute(f"SELECT source_record_id,try_cast(census_year AS INT),source_file,source_sheet,try_cast(source_row AS INT),source_name_raw,settlement_name,settlement_type,region_raw,district_raw,try_cast(population AS BIGINT) FROM read_parquet('{SEL}') WHERE source_record_id IN ({','.join('?' for _ in ids)})",ids).fetchall()
byid={r[0]:r for r in rows};assert set(ids)==set(byid)
# Stream the precomputed raw context index once, retaining only exact source rows and profile summaries for involved sheets.
filesheets={(r[1],r[2],str(r[3])) for r in rows};profiles=defaultdict(Counter);target_context=defaultdict(list)
with RAW_CONTEXT.open(encoding='utf-8-sig',newline='') as f:
 for x in csv.DictReader(f):
  try:yr=int(x.get('year') or -1)
  except:continue
  ksheet=(yr,x.get('source_file',''),str(x.get('source_sheet','')))
  if ksheet not in filesheets:continue
  def col(loc):
   m=re.search(r'R\d+C(\d+)',loc or '')
   return int(m.group(1)) if m else None
  ncol=col(x.get('raw_name_cell_locator',''));tcol=col(x.get('raw_type_cell_locator',''))
  if ncol:profiles[ksheet][(tcol,ncol)]+=1
  if x.get('source_record_id') in set(ids):target_context[x['source_record_id']].append(x)

def profile(y,file,sheet):
 c=profiles[(y,file,str(sheet))]
 if not c:return None
 ranked=c.most_common()
 # match producer tie behavior
 if len(ranked)>1 and ranked[0][1]==ranked[1][1]:return {'status':'ambiguous','alternatives':ranked}
 return {'status':'reviewed','type_col':ranked[0][0][0],'name_col':ranked[0][0][1],'support_rows':ranked[0][1],'alternatives':ranked}
def parser_output(cells,prof):
 if not prof or prof['status']!='reviewed':return None
 tcol,ncol=prof['type_col'],prof['name_col']
 text=str(cells[ncol-1]).strip() if ncol and len(cells)>=ncol and cells[ncol-1] is not None else ''
 typetext=str(cells[tcol-1]).strip() if tcol and len(cells)>=tcol and cells[tcol-1] is not None else ''
 source=typetext or text
 matches=sorted({canonical_type(t) for t in type_prefix if re.match(r'^\s*'+type_prefix[t]+r'\s*',source,re.I)}) if source else []
 m=type_re.match(source) if source else None
 suffix=source[m.end():].strip(' .,:;—–-') if m else ''
 nameval=suffix if suffix else text
 # This deliberately reproduces the suspect secondary strip from producer.
 nameval=re.sub(r'^\s*(?:'+'|'.join(re.escape(x) for x in sorted(set(type_prefix.values()),key=len,reverse=True))+r')\s*','',nameval,flags=re.I).strip(' .,:;—–-')
 rawtype=matches[0] if len(matches)==1 else ('ambiguous:'+'|'.join(matches) if matches else None)
 return {'raw_name_field':text,'raw_type_field':typetext,'source_text':source,'name':key(nameval) or None,'type':rawtype,'matches':matches,'recognized':len(matches)==1}
# Open a workbook once per source file and hold no more than 2 handles.
books={};sheets={}
def getsheet(year,rel,sheet):
 path=RAW/rel
 if rel not in books:
  books[rel]=xlrd.open_workbook(str(path),on_demand=True)
 try:sh=books[rel].sheet_by_name(str(sheet))
 except Exception:sh=books[rel].sheet_by_index(int(sheet))
 return sh,path
records=[]
for id10,id02 in pairs:
 for sid in [id02,id10]:
  r=byid[sid];year,file,sheet,row=int(r[1]),r[2],str(r[3]),r[4]
  sh,path=getsheet(year,file,sheet);cells=sh.row_values(row-1);prof=profile(year,file,sheet);parsed=parser_output(cells,prof)
  records.append({'control_2010_id':id10,'control_2002_id':id02,'source_id':sid,'year':year,'source_file':file,'source_sha256':sha(path),'source_sheet':sheet,'source_row_1based':row,'selected_name':r[6],'selected_type':r[7],'selected_population':r[10],'literal_raw_cells':cells,'profile':prof,'context_rows_for_id':len(target_context.get(sid,[])),'context_excerpt':[{k:v for k,v in x.items() if k in ('raw_selected_label','raw_label_from_workbook','raw_name_exact','raw_type_cell_literal','raw_type_cell_locator','raw_name_cell_locator','raw_type_prefix_pass','raw_row_cells_json')} for x in target_context.get(sid,[])[:2]],'current_parser_row':parsed,'parser_exact_selected_pair':bool(parsed and parsed['name']==key(r[6]) and parsed['type']==canonical_type(r[7]) and parsed['recognized'])})
for rel in books:books[rel].release_resources()
# Raw exact-token counts across each entire workbook sheet: distinguish parser zero vs genuine duplication.
for rec in records:
 y=rec['year'];rel=rec['source_file'];sheet=rec['source_sheet'];sh,path=getsheet(y,rel,sheet) if rel not in books else (None,None)
 # reopened below to count; don't rely on closed handle
 if sh is None:
  wb=xlrd.open_workbook(str(RAW/rel),on_demand=True)
  try:sh=wb.sheet_by_name(sheet)
  except Exception:sh=wb.sheet_by_index(int(sheet))
 p=rec['profile'];same=[];parsed_exact=[]
 if p and p['status']=='reviewed':
  for ri in range(sh.nrows):
   cells=sh.row_values(ri);q=parser_output(cells,p)
   if q and (q['name'],q['type'])==(key(rec['selected_name']),canonical_type(rec['selected_type'])):
    same.append(ri+1)
  rec['exact_typed_raw_occurrences_full_sheet']=same
  rec['full_sheet_count']=len(same)
  rec['control_row_in_occurrences']=rec['source_row_1based'] in same
 else:
  rec['exact_typed_raw_occurrences_full_sheet']=None;rec['full_sheet_count']=None;rec['control_row_in_occurrences']=False
 try:wb.release_resources()
 except:pass
# Write exact control evidence, including failures by zero vs duplicates.
fields=list(records[0])
with (OUT/'control_rows.jsonl').open('w',encoding='utf-8') as f:
 for x in records:f.write(json.dumps(x,ensure_ascii=False)+'\n')
# CSV concise rows
csvfields=['control_2010_id','control_2002_id','source_id','year','source_file','source_sha256','source_sheet','source_row_1based','selected_name','selected_type','selected_population','profile','literal_raw_cells','raw_name_field','raw_type_field','parser_name','parser_type','parser_exact_selected_pair','full_sheet_count','full_sheet_occurrence_rows','control_row_in_occurrences','context_excerpt']
with (OUT/'control_row_summary.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=csvfields,extrasaction='ignore',lineterminator='\n');w.writeheader()
 for x in records:
  q=x['current_parser_row'] or {}
  w.writerow({**x,'profile':json.dumps(x['profile'],ensure_ascii=False),'literal_raw_cells':json.dumps(x['literal_raw_cells'],ensure_ascii=False),'raw_name_field':q.get('raw_name_field'),'raw_type_field':q.get('raw_type_field'),'parser_name':q.get('name'),'parser_type':q.get('type'),'full_sheet_occurrence_rows':json.dumps(x['exact_typed_raw_occurrences_full_sheet'],ensure_ascii=False),'context_excerpt':json.dumps(x['context_excerpt'],ensure_ascii=False)})
print('controls',len(pairs),'rows',len(records),'parser exact selected',sum(x['parser_exact_selected_pair'] for x in records),'source-row full-sheet exact token counts',Counter(x['full_sheet_count'] for x in records))
for x in records:print(x['year'],x['selected_name'],x['selected_type'],'profile',x['profile'],'parser',x['current_parser_row'],'full_count',x['full_sheet_count'])
