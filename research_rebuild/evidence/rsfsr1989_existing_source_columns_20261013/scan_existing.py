"""Read all sheets/cells in cachedregional2002sources; no source/input mutation."""
from pathlib import Path
import xlrd,json,re,hashlib
BASE=Path('/workspace/settlements-raw/data/raw/2002');OUT=Path(__file__).parent
manifest=[];hits=[];numeric=[]
for p in sorted(BASE.glob('*.xls')):
 b=xlrd.open_workbook(p)
 for s in b.sheets():
  local=[]
  for i in range(s.nrows):
   for j in range(s.ncols):
    v=s.cell_value(i,j)
    h=dict(file=p.name,sheet=s.name,row_excel=i+1,col_excel=j+1,value=v,row_values=s.row_values(i))
    if isinstance(v,str) and re.search(r'(?<!\d)(1989|1979)(?!\d)',v):h['classification']='text_header_or_note';hits.append(h);local.append(h)
    elif isinstance(v,(int,float)) and v in (1989,1979):numeric.append(h)
  manifest.append(dict(file=p.name,path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),sheet=s.name,visibility=s.visibility,nrows=s.nrows,ncols=s.ncols,first100_text_year_hits=sum(h['row_excel']<=100 for h in local),allrow_text_year_hits=len(local),header_first8rows=[s.row_values(i) for i in range(min(8,s.nrows))]))
for n,v in [('scan_manifest.json',manifest),('historical_year_hits.json',hits),('allrow_numeric_year_value_hits.json',numeric)]:
 (OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2))
print(json.dumps({'regional_files':len(list(BASE.glob('*.xls'))),'worksheets':len(manifest),'allrow_text_1989_1979_hits':len(hits),'allrow_numeric_1989_1979_hits':len(numeric),'sheetname_oldyear_hits':sum(bool(re.search('1989|1979',m['sheet'])) for m in manifest)},ensure_ascii=False))
