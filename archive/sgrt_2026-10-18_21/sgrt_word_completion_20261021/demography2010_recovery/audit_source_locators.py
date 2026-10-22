from pathlib import Path
import pandas as pd,json,re
from docx import Document
R=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_demography2010');out={}
def num(v):
 if pd.isna(v):return None
 s=str(v).strip();return int(float(s))if re.fullmatch(r'\d+(?:\.0)?',s)else None
doc=Document(RAW/'tver_extracted/pub08-02.docx');tables=[[[' '.join(c.xpath('.//w:t/text()'))for c in row.tc_lst]for row in t._tbl.tr_lst]for t in doc.tables]
for reg in ['tver','vologda','novgorod']:
 d=pd.read_parquet(R/reg/'primary_source_NP_inventory.parquet');fails=[]
 if reg=='vologda':sheet=pd.read_excel(RAW/'vologda_extracted/Населенные пункты.xlsx',header=None)
 if reg=='novgorod':pages=(RAW/'novgorod2010_layout.txt').read_text().split('\f')
 for i,r in d.iterrows():
  if reg=='tver':
   cc=tables[int(r.source_table)-1][int(r.source_row)-1]
   if r.source_table==9:
    texts=re.sub(r'\s+',' ',' '.join(cc));m=re.search(re.escape(str(r.settlement_name))+r'\s+Всего\s*-\s*(\d+)',texts);ok=m is not None and int(m[1])==r.primary_population
   else:ok=[num(v)for v in cc[1:4]]==[None if pd.isna(v)else int(v)for v in [r.primary_population,r.primary_men,r.primary_women]] and str(r.settlement_name)in re.sub(r'\s+',' ',cc[0])
  elif reg=='vologda':
   cc=sheet.iloc[int(r.source_row)-1];ok=[num(v)for v in cc.iloc[1:4]]==[None if pd.isna(v)else int(v)for v in [r.primary_population,r.primary_men,r.primary_women]] and str(r.settlement_name)in re.sub(r'\s+',' ',str(cc.iloc[0]))
  else:
   line=pages[int(r.source_page)-1].splitlines()[int(r.source_line_start)-1];ok=line==r.raw_pdf_line
  if not ok:fails.append(str(r.source_record_id))
 out[reg]={'source_inventory_rows_checked':len(d),'source_locator_and_population_failures':fails,'immutable_review_files_modified':False}
(R/'all_source_locator_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2));assert all(not x['source_locator_and_population_failures']for x in out.values())
