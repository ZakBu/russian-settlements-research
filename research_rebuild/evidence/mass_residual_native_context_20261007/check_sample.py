import sys,json
from pathlib import Path
import pandas as pd,xlrd
ROOT=Path('/workspace/russian-settlements-research');OUT=Path(__file__).parent;sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'));from current_chain_state_20261007 import normalize,sha
f=pd.concat([pd.read_csv(OUT/'fixed15.csv'),pd.read_csv(OUT/'top5.csv')]).drop_duplicates('from_source_record_id');books={};rows=[]
for r in f.to_dict('records'):
 path=Path('/workspace/settlements-raw')/r['source_file']
 if not path.exists():rows.append(dict(target=r['from_source_record_id'],status='raw_workbook_missing'));continue
 if path not in books:books[path]=(xlrd.open_workbook(str(path),on_demand=True),sha(path))
 book,digest=books[path];sh=book.sheet_by_name(str(r['source_sheet']))
 def text(n):return ' | '.join(str(v).strip() for v in sh.row_values(int(n)-1) if v not in ('',None))
 target=text(r['source_row']); printedname=normalize(r['source_name_raw']);name_ok=printedname in normalize(target)
 lo=text(r['lower_row']);hi=text(r['upper_row'])
 headings=[]
 for n in range(max(1,r['lower_row']-20),r['upper_row']+1):
  t=text(n)
  if any(v in normalize(t) for v in ['сельсовет','сельский округ','город сочи','город краснодар','город йошкар','город саранск']):headings.append(f'{n}: {t}')
 rows.append(dict(target=r['from_source_record_id'],source_file=r['source_file'],source_sheet=r['source_sheet'],workbook_sha256=digest,target_row=r['source_row'],target_raw_cells=target,lower_anchor_raw_cells=lo,upper_anchor_raw_cells=hi,heading_witnesses='\n'.join(headings),target_name_literal_match=name_ok,population_2002=r['population_2002'],status='literal_source_sample_checked' if name_ok else 'literal_mismatch_hold'))
pd.DataFrame(rows).to_csv(OUT/'sampled_physical_source_checks.csv',index=False);print(json.dumps({'sample_count':len(rows),'literal_checks_passed':sum(r.get('target_name_literal_match',False) for r in rows),'statuses':pd.Series([r['status'] for r in rows]).value_counts().to_dict()},ensure_ascii=False))
# Bind compact candidate records to staged raw bytes and selected current native codes.
import hashlib,pyarrow.parquet as pq
full=pd.read_csv(OUT/'candidates.csv',keep_default_na=False)
source_hashes={}
for rel in full.source_file.unique():
 path=Path('/workspace/settlements-raw')/rel
 if not path.exists():raise FileNotFoundError(path)
 source_hashes[rel]=sha(path)
full['source_sha256']=full.source_file.map(source_hashes)
meta=pq.read_table('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet',columns=['source_record_id','oktmo','okato','population']).to_pandas().set_index('source_record_id')
full['current_oktmo']=full.to_source_record_id.map(meta.oktmo);full['current_okato']=full.to_source_record_id.map(meta.okato);full['population_2021']=full.to_source_record_id.map(meta.population)
full.to_csv(OUT/'candidates.csv',index=False)
for filename in ['fixed15.csv','top5.csv']:
 ids=pd.read_csv(OUT/filename).from_source_record_id
 full[full.from_source_record_id.isin(ids)].to_csv(OUT/filename,index=False)
receipt=json.loads((OUT/'receipt.json').read_text());receipt['sample_check']={'fixed_sample':15,'top_population_sample':5,'unique_physical_checks':len(rows),'literal_name_passes':sum(r.get('target_name_literal_match',False) for r in rows),'source_population_cells_present_unmodified':True};receipt['native_source_hashes']=source_hashes;receipt['outputs']={p.name:sha(p) for p in OUT.glob('*.csv')};(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
