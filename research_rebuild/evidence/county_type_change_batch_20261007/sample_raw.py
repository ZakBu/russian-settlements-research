"""Bounded raw source inspection packet; not admission or accuracy certification."""
import sys,json,random,subprocess
import pyarrow.parquet as pq
from pathlib import Path
import pandas as pd
import xlrd,openpyxl
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).resolve().parent;RAW=Path('/workspace/settlements-raw')
d=pd.read_csv(OUT/'candidate_identity_edge_delta.csv',keep_default_na=False)
# Preserve original empty locator separately; construct exact physical locators from selected row metadata.
for side in ['from','to']:
 if side+'_source_locator_raw' not in d: d[side+'_source_locator_raw']=d[side+'_source_locator']
 d[side+'_source_locator']=[v or f'{f}#{sh}!row={int(float(r))}' for v,f,sh,r in d[[side+'_source_locator',side+'_source_file',side+'_source_sheet',side+'_source_row']].itertuples(index=False,name=None)]
d.to_csv(OUT/'candidate_identity_edge_delta.csv',index=False)
rng=random.Random(20261007);top=list(d.assign(mass=pd.to_numeric(d.from_population)+pd.to_numeric(d.to_population)).sort_values('mass',ascending=False).head(5).index)
indices=top+rng.sample([i for i in d.index if i not in top],min(35,len(d)-len(top)))
books={};checks=[];hashes={}
for ix in indices:
 r=d.loc[ix]
 for side in ['from','to']:
  file=str(r[side+'_source_file']);path=RAW/file
  check={'sample_kind':'top5_population_schedule' if ix in top else 'seed20261007_random35','from_source_record_id':r.from_source_record_id,'to_source_record_id':r.to_source_record_id,'side':side,'source_record_id':r[side+'_source_record_id'],'source_locator':r[side+'_source_locator'],'selected_source_sha256':r[side+'_source_sha256'],'source_file':file,'source_name_selected':r[side+'_settlement_name'],'source_type_selected':r[side+'_type_raw'],'county_selected':r[side+'_district_raw'],'source_population_selected':r[side+'_population'],'possible_type_change':r.possible_type_change}
  if not path.exists():check.update(status='hold_raw_source_unstaged',raw_row_literal='',raw_source_sha256='')
  else:
   try:
    if path.suffix.lower()=='.parquet':
     if path not in books:
      hashes[str(path)]=sha(path);books[path]=pq.read_table(path,columns=['object_level','object_name','settlement','region','mun_upper','population','oktmo','latitude_dadata','longitude_dadata'])
     raw=books[path].slice(int(float(r[side+'_source_row']))-1,1).to_pylist()[0];literal=json.dumps(raw,ensure_ascii=False);name_ok=normalize(r[side+'_settlement_name']) in normalize(raw['object_name']);h=hashes[str(path)];expected=str(r[side+'_source_sha256']);hash_ok=not expected or expected==h
     check.update(raw_source_sha256=h,hash_matches_selected=hash_ok,raw_row_literal=literal,literal_name_found=name_ok,county_raw=raw['mun_upper'],county_key_matches=county_key(raw['mun_upper'])==str(r.county_key),status='literal_name_and_hash_pass' if name_ok and hash_ok else 'hold_literal_or_hash_mismatch');checks.append(check);continue
    if path.suffix.lower()=='.pdf':
     h=hashes.setdefault(str(path),sha(path));loc=json.loads(r[side+'_source_locator']);page=int(loc['pdf_page_1based']);literal=subprocess.check_output(['pdftotext','-f',str(page),'-l',str(page),'-layout',str(path),'-'],text=True);name=normalize(r[side+'_settlement_name']);matching=[line for line in literal.splitlines() if name in normalize(line)];expected=str(r[side+'_source_sha256']);hash_ok=not expected or expected==h
     check.update(raw_source_sha256=h,hash_matches_selected=hash_ok,raw_row_literal=' | '.join(matching),literal_name_found=bool(matching),raw_page_1based=page,exact_text_line_locator_verified=False,status='literal_name_and_hash_pass' if matching and hash_ok else 'hold_literal_or_hash_mismatch');checks.append(check);continue
    if path not in books:
     hashes[str(path)]=sha(path)
     books[path]=xlrd.open_workbook(str(path),on_demand=True) if path.suffix.lower()=='.xls' else openpyxl.load_workbook(path,read_only=True,data_only=True)
    book=books[path];sh=book.sheet_by_name(str(r[side+'_source_sheet'])) if path.suffix.lower()=='.xls' else book[str(r[side+'_source_sheet'])];n=int(float(r[side+'_source_row']))
    def values(i):return sh.row_values(i-1) if path.suffix.lower()=='.xls' else [x.value for x in sh[i]]
    vals=values(n);literal=' | '.join(str(v) for v in vals if v is not None and v!='');name=normalize(r[side+'_settlement_name']);name_ok=name in normalize(literal);h=hashes[str(path)];expected=str(r[side+'_source_sha256']);hash_ok=not expected or expected==h
    county_row=None;county_literal=''
    for i in range(n-1,max(0,n-250),-1):
     vv=values(i);ll=' | '.join(str(v) for v in vv if v is not None and v!='')
     if str(r.county_key) in county_key(ll) and any(w in normalize(ll) for w in ['район','округ','город']):county_row=i;county_literal=ll;break
    check.update(raw_source_sha256=h,hash_matches_selected=hash_ok,raw_row_literal=literal,literal_name_found=name_ok,preceding_county_context_row=county_row,preceding_county_context_literal=county_literal,status='literal_name_and_hash_pass' if name_ok and hash_ok else 'hold_literal_or_hash_mismatch')
   except Exception as e:check.update(status='hold_raw_read_error',error=str(e))
  checks.append(check)
pd.DataFrame(checks).to_csv(OUT/'sampled_raw_source_checks.csv',index=False)
r=json.loads((OUT/'simulation_receipt.json').read_text());r['sample']={'sampled_candidate_pairs':len(indices),'raw_endpoints':len(checks),'statuses':{str(k):int(v) for k,v in pd.Series([x['status'] for x in checks]).value_counts().items()},'seed':20261007,'sampling':'top5 plus random35 independent endpoint literal source inspection; candidate author is not independent admission reviewer'};r['raw_sample_source_hashes']=hashes;r['outputs_sha256']={p.name:sha(p) for p in OUT.glob('*.csv')};(OUT/'simulation_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r['sample'],ensure_ascii=False,indent=2))
