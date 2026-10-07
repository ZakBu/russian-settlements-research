"""Create compact physical-source checks from the pinned candidate source ledger."""
from pathlib import Path
import json,hashlib,pandas as pd
OUT=Path(__file__).resolve().parent;WORK=Path('/workspace/settlements-work/secondary_2010_county_context_batch_20261007')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks=pd.read_csv(WORK/'literal_source_checks.csv.gz',keep_default_na=False).set_index('source_record_id')
outputs=[]
for stem in ['fixed15','top5']:
 source=OUT/(stem+'_candidates.csv');f=pd.read_csv(source,keep_default_na=False);rows=[]
 for a in f.to_dict('records'):
  row={'target_2010_source_record_id':a['target_2010_source_record_id'],'settlement_name':a['settlement_name'],'inferred_county_key':a['inferred_county_key'],'population_2010_protected_unchanged':a['population_2010_protected_unchanged'],'lower_anchor_current_id':a['lower_anchor_current_id'],'upper_anchor_current_id':a['upper_anchor_current_id'],'source_file':a['source_file'],'source_sha256':a['source_sha256'],'source_sheet':a['source_sheet']}
  for role,key in [('lower','lower_anchor_2010_id'),('target','target_2010_source_record_id'),('upper','upper_anchor_2010_id')]:
   z=checks.loc[a[key]]
   for field in ['source_record_id','source_row_1based','literal_label_match','protected_population_cell_found','population','raw_label','raw_cells']:
    row[role+'_'+field]=a[key] if field=='source_record_id' else z[field]
  rows.append(row)
 output=OUT/(stem+'_physical_source_checks.csv');pd.DataFrame(rows).to_csv(output,index=False);outputs.append(output)
receipt={'status':'source_views_only','inputs':{str(p):sha(p) for p in [WORK/'literal_source_checks.csv.gz',OUT/'fixed15_candidates.csv',OUT/'top5_candidates.csv',Path(__file__)]},'outputs':{p.name:sha(p) for p in outputs},'fixed_candidate_trajectories':15,'top_candidate_trajectories':5,'physical_source_rows_per_trajectory':3,'source_population_values_modified':False}
(OUT/'source_samples_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
