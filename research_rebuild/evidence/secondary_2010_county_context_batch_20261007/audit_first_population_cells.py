"""Independent physical-cell audit: chosen population must be the first numeric cell after the own label."""
from pathlib import Path
import hashlib,json,pandas as pd,xlrd
OUT=Path(__file__).resolve().parent;LEDGER=Path('/workspace/settlements-work/secondary_2010_county_context_batch_20261007/literal_source_checks.csv.gz')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
c=pd.read_csv(LEDGER);bad=[];counts=0;pins={}
for filename,g in c.groupby('source_file'):
 p=Path(filename);pins[filename]=sha(p);b=xlrd.open_workbook(str(p),on_demand=True)
 for sheet,rows in g.groupby('source_sheet'):
  sh=b.sheet_by_name(sheet)
  for z in rows.itertuples():
   vals=sh.row_values(int(z.source_row_1based)-1);pos=int(z.label_column_1based)
   numeric=[(j+1,v) for j,v in enumerate(vals) if j>=pos and isinstance(v,(int,float))]
   okay=bool(numeric) and numeric[0][0]==int(z.population_column_1based) and numeric[0][1]==z.population
   if not okay:bad.append({'source_record_id':z.source_record_id,'selected_population':z.population,'claimed_column':z.population_column_1based,'first_numeric_after_label':numeric[0] if numeric else None})
   counts+=1
 b.release_resources()
r={'status':'passed' if not bad else 'failed','physical_rows_checked':counts,'failures':bad,'source_sha256':pins,'inputs_sha256':{str(p):sha(p) for p in [LEDGER,Path(__file__)]},'rule':'Protected population must equal first numeric cell after own label; intervening textual split type/name columns are skipped, later ethnicity counts cannot qualify.'}
(OUT/'first_population_cell_audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':r['status'],'physical_rows_checked':counts,'failures':len(bad)}));assert not bad
