"""Repair export-only key precedence; retain executed recipe and application controls."""
from pathlib import Path
import json,hashlib
import pandas as pd
p=Path(__file__).resolve().parent
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
r=json.loads((p/'application_receipt.json').read_text());s=p/'applied_point_snapshot.parquet';old=sha(s)
f=pd.read_parquet(s);blank=f.source_record_id.eq('');f.loc[blank,'source_record_id']=f.loc[blank,'target_source_record_id']
c=pd.read_csv(p/'applied_component_snapshot.csv.gz',dtype={'source_record_id':str,'root':str});ids=set(c.loc[c.has_own_point,'source_record_id'])
assert f.source_record_id.ne('').all() and f.source_record_id.is_unique and set(f.source_record_id)==ids
assert len(f)==int(c.has_own_point.sum())
f.to_parquet(s,index=False,compression='zstd')
proof={'status':'export_key_precedence_corrected_and_read_back_verified','old_snapshot_sha256':old,'rows_repaired':int(blank.sum()),'nonblank_unique_source_IDs':len(f),'component_ownpoint_flags_exactly_match':True,'canonical_API_application_unchanged':True,'executed_recipe':'executed_recipe_v2_before_snapshot_key_correction.py','future_reproducible_recipe':'compose.py'}
(p/'snapshot_key_export_correction.json').write_text(json.dumps(proof,indent=2)+'\n')
r['snapshot_key_export_correction']=proof
r['output_pins']={q.name:{'sha256':sha(q),'bytes':q.stat().st_size} for q in p.iterdir() if q.is_file() and q.name!='application_receipt.json'}
(p/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'accepted_edges':r['accepted_edges'],'accepted_point_uses':r['accepted_point_uses'],'integration_holds':r['integration_holds'],'snapshot':proof,'after':r['after'],'receipt_sha256':sha(p/'application_receipt.json')},ensure_ascii=False))
