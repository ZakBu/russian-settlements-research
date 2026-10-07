"""Add one bounded actual2010 source witness per candidate, without repeating older audits."""
import sys,json,re,subprocess
from pathlib import Path
import pandas as pd,duckdb,xlrd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha
O=Path(__file__).parent;f=pd.read_csv(O/'candidate_full_triplets.csv',dtype=str,keep_default_na=False);ids=[json.loads(v)['2010'] for v in f.source_ids_json];c=duckdb.connect();q=c.execute('select source_record_id,settlement_name,population,source_file,source_sheet,source_row,source_name_raw,source_locator,source_raw_line,source_population_raw from read_parquet(?) where source_record_id in(select unnest(?))',['/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet',ids]).fetchdf();books={};out=[];hashes={}
for a in q.to_dict('records'):
 p=Path('/workspace/settlements-raw')/a['source_file'];hashes[str(p)]=sha(p);raw='';literal=population=False;page=None
 if p.suffix=='.xls':
  if p not in books:books[p]=xlrd.open_workbook(str(p),on_demand=True)
  sh=books[p].sheet_by_name(a['source_sheet']);vals=sh.row_values(int(a['source_row'])-1);labels=[i for i,v in enumerate(vals) if isinstance(v,str) and normalize(a['settlement_name']) in normalize(v)];literal=len(labels)==1
  raw=' | '.join(str(v) for v in vals if v!='')
  if literal:
   numbers=[]
   for v in vals[labels[0]+1:]:
    try:numbers.append(float(v))
    except:pass
   population=bool(numbers) and numbers[0]==float(a['population'])
 else:
  page=int(a['source_sheet'].split('_')[-1]);text=subprocess.check_output(['pdftotext','-f',str(page),'-l',str(page),'-layout',str(p),'-'],text=True);lines=[v for v in text.splitlines() if normalize(a['settlement_name']) in normalize(v)]
  count=str(int(a['population']));pattern='\\s*'.join(re.escape(v) for v in count)
  hits=[v for v in lines if re.search(r'(?<!\d)'+pattern+r'(?!\d)',v)]
  literal=bool(lines);population=len(hits)==1;raw=' | '.join(hits or lines)
 out.append({'source_record_id':a['source_record_id'],'name':a['settlement_name'],'actual_population':a['population'],'source_file':str(p),'source_sha256':hashes[str(p)],'sheet':a['source_sheet'],'row_as_selected':a['source_row'],'pdf_page_1based':page,'literal_raw_label_present':literal,'actual_population_present_exact':population,'actual_raw_row':raw})
r=pd.DataFrame(out)
if not r[['literal_raw_label_present','actual_population_present_exact']].all().all():print(r.to_string(index=False));raise ValueError('Bounded actual2010 checks failed')
r.to_csv(O/'actual2010_raw_row_witnesses.csv',index=False);d=r.set_index('source_record_id').to_dict('index')
f['actual2010_primary_witness_json']=f.source_ids_json.map(lambda v:json.dumps(d[json.loads(v)['2010']],ensure_ascii=False,default=str));f.to_csv(O/'candidate_full_triplets.csv',index=False)
receipt=json.loads((O/'receipt.json').read_text());receipt['actual2010_primary_source_rows_checked']=len(r);receipt['actual2010_primary_checks_all_passed']=True;receipt['raw_primary_source_hashes'].update(hashes);receipt['inputs'][str(Path(__file__).resolve())]=sha(Path(__file__));receipt['outputs']['candidate_full_triplets.csv']=sha(O/'candidate_full_triplets.csv');receipt['outputs']['actual2010_raw_row_witnesses.csv']=sha(O/'actual2010_raw_row_witnesses.csv');(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print('All12 actual2010 native source labels and counts pass.')
