from pathlib import Path
import re,json,hashlib,xlrd,openpyxl
OUT=Path(__file__).parent
sets={'2010':Path('/workspace/settlements-raw/data/raw/2010'),'2021':Path('/workspace/shared/rsfsr1989_existing_source_columns/data/raw/2021')}
manifest=[];hits=[]
for year,base in sets.items():
 for p in sorted([*base.glob('*.xls'),*base.glob('*.xlsx')]):
  if p.name.startswith('._'):continue
  if p.suffix=='.xls':
   b=xlrd.open_workbook(p);sheets=[(s.name,s.nrows,s.ncols,s.visibility,[s.row_values(i) for i in range(min(100,s.nrows))]) for s in b.sheets()]
  else:
   b=openpyxl.load_workbook(p,read_only=True,data_only=False);sheets=[(s.title,s.max_row,s.max_column,s.sheet_state,list(s.iter_rows(min_row=1,max_row=min(100,s.max_row or 100),values_only=True))) for s in b.worksheets]
  for name,nrows,ncols,vis,rows in sheets:
   hs=[]
   for i,r in enumerate(rows,1):
    for j,v in enumerate(r,1):
     if isinstance(v,str) and re.search(r'(?<!\d)(1989|1979)(?!\d)',v) or isinstance(v,(int,float)) and v in (1989,1979):
      h=dict(source_year=year,file=p.name,sheet=name,row_excel=i,col_excel=j,value=v,row_values=list(r));hs.append(h);hits.append(h)
   manifest.append(dict(source_year=year,file=p.name,path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),sheet=name,nrows=nrows,ncols=ncols,visibility=vis,header_oldyear_hits=len(hs),sheetname_oldyear_hit=bool(re.search(r'1989|1979',name)),header_first15rows=[list(r) for r in rows[:15]]))
  if p.suffix=='.xlsx':b.close()
(OUT/'later_header_scan_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=str));(OUT/'later_header_historical_year_hits.json').write_text(json.dumps(hits,ensure_ascii=False,indent=2,default=str))
print('files',len(set((m['source_year'],m['file']) for m in manifest)),'sheets',len(manifest),'hits',len(hits))
for h in hits:print(h['source_year'],h['file'],h['sheet'],h['row_excel'],h['col_excel'],h['value'],h['row_values'])
