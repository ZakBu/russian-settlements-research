"""Independently read direct external coordinate lines and physical source-row values."""
import sys,re,json,csv
from pathlib import Path
import pandas as pd
import duckdb
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from research_rebuild.mass_linkage.wide_wikidata_bindings import qid,rdf_text,parse_point
from current_chain_state_20261007 import normalize,sha
OUT=Path(__file__).parent;WORK=Path('/workspace/settlements-work/corrected_own_wiki_point_batch_20261007')
f=pd.read_csv(WORK/'candidate_corrected_external_own_point_delta.csv');wanted=set()
for loc in f.point_origin_locator:
 wanted.update(map(int,re.search(r'TSV_lines_1based=([0-9,]+)',loc).group(1).split(',')))
tsv={};source=Path(f.point_origin_file.iloc[0])
with source.open() as stream:
 for line,row in enumerate(csv.DictReader(stream,delimiter='\t'),2):
  if line in wanted:tsv[line]=row
sheets={};results=[];c=duckdb.connect()
for a in f.to_dict('records'):
 lines=list(map(int,re.search(r'TSV_lines_1based=([0-9,]+)',a['point_origin_locator']).group(1).split(',')))
 external=any(qid(tsv[i]['?item'])==a['coordinate_provider_id'] and normalize(rdf_text(tsv[i]['?label']))==normalize(a['source_name']) and parse_point(tsv[i]['?coord'])==(a['latitude'],a['longitude']) for i in lines)
 p=Path('/workspace/settlements-raw')/a['source_file'];sid=a['target_source_record_id'];sheet,index=sid.rsplit(':',2)[-2:];index=int(index)
 if p.suffix=='.parquet':
  row=c.execute('SELECT settlement,population FROM read_parquet(?) LIMIT 1 OFFSET ?',[str(p),index-1]).fetchdf().iloc[0];nameok=normalize(a['source_name']) in normalize(row.settlement);popok=float(row.population)==float(a['population']);excerpt=str(row.to_dict())
 else:
  key=(str(p),sheet)
  if key not in sheets:sheets[key]=pd.read_excel(p,sheet_name=sheet,header=None)
  row=sheets[key].iloc[index-1];excerpt=' | '.join(str(v) for v in row if pd.notna(v));nameok=normalize(a['source_name']) in normalize(excerpt);numbers=pd.to_numeric(row.astype(str).str.replace(' ','',regex=False),errors='coerce');popok=bool(numbers.eq(float(a['population'])).any())
 results.append({'target_source_record_id':sid,'external_direct_qid_label_coordinate_exact':external,'physical_source_row_name_present':nameok,'physical_source_row_population_exact':popok,'census_source_sha256_actual':sha(p),'raw_row_excerpt':excerpt[:650]})
g=pd.DataFrame(results);g.to_csv(OUT/'independent_direct_point_and_source_row_checks.csv',index=False);cols=['external_direct_qid_label_coordinate_exact','physical_source_row_name_present','physical_source_row_population_exact'];r={'checked_candidate_point_rows':len(g),'all_checks_pass':bool(g[cols].all().all()),'pass_counts':{k:int(g[k].sum()) for k in cols},'source_coordinate_tsv_sha256':sha(source),'point_delta_sha256':sha(WORK/'candidate_corrected_external_own_point_delta.csv'),'limit':'Checks actual external coordinates and source values; identity and historical scope are separately witnessed by the candidate case.'};(OUT/'independent_check_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r))
