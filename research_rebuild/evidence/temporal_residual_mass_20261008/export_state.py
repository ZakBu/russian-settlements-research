from pathlib import Path
import sys,json,time
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
start=time.monotonic();s=load(61);m=s.metrics();rows=[]
for sid,p in s.point_rows.items():
 rows.append({'source_record_id':sid,'root':s.uf.find(sid),'latitude':p['latitude'],'longitude':p['longitude'],'coordinate_admission_status':p.get('coordinate_admission_status',''),'coordinate_source_record_id':p.get('coordinate_source_record_id',''),'point_origin_file':p.get('point_origin_file',''),'point_origin_sha256':p.get('point_origin_sha256',''),'point_origin_locator':p.get('point_origin_locator',''),'point_origin_kind':p.get('point_origin_kind',''),'point_ledger_path':p.get('point_ledger_path',''),'conflicting_point_target':sid in s.conflicting_point_targets})
pf=pd.DataFrame(rows).drop(columns=['root']).astype(str);con=duckdb.connect();con.register('pf',pf);con.execute("COPY pf TO 'research_rebuild/evidence/temporal_residual_mass_20261008/SHARED_points_compact_stage61.parquet' (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 12)");con.close()
x=s.obs[['source_record_id','root']].copy();x['component_years']=x.root.map(lambda r:','.join(map(str,sorted(s.years[r]))));x.to_csv(O/'SHARED_component_snapshot_stage61.csv.gz',index=False,compression={'method':'gzip','compresslevel':9,'mtime':0})
pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in s.inputs};out={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in O.glob('SHARED*')};r={'baseline_stage':61,'canonical_loader_validated':True,'metrics':m,'source_input_pins':pins,'output_pins':out,'point_rows':len(rows),'conflicting_point_targets':sorted(s.conflicting_point_targets),'elapsed_seconds':time.monotonic()-start};(O/'state_snapshot_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['source_input_pins','conflicting_point_targets']},ensure_ascii=False),flush=True)
