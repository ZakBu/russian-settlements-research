from pathlib import Path
import json
import pandas as pd
raw=Path('/workspace/shared/rural1979_new_sources/stavropol_rows.jsonl')
d=pd.read_json(raw,lines=True,dtype={"okato":str});d['year']=1989;d['name']=d.name_clean.str.replace(r'^(?:село|пос[её]лок|хутор|станица|аул)\s+', '',regex=True);d['district']=d.district_context;d['provider_id']=d.okato;d['present_total']=d.pop1989;d['permanent_total']=None;d['present_male']=d.male1989;d['present_female']=d.female1989;d['source_locator']=d.excel_sheet+':row1:'+d.excel_row.astype(str);d['source_kind']='official_census_comparative_table';d['raw_cells_json']=d.raw_cells.map(lambda x:json.dumps(x,ensure_ascii=False));d=d.drop(columns='raw_cells');d.to_parquet(raw.parent/'stavropol_facts_normalized.parquet',index=False)
print(len(d),'flagged',d.admission_block.sum(),d.name.head().tolist())
