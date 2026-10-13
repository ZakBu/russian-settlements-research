from pathlib import Path
import sys,json,hashlib,pandas as pd
BASE=Path('/workspace/russian-settlements-research'); O=Path(__file__).parent; E=BASE/'research_rebuild/evidence'; sys.path.insert(0,str(BASE/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load(71); d=s.obs.copy(); d['root']=d.source_record_id.map(s.uf.find); p=pd.DataFrame(list(s.point_rows.values())); print('pointcols',p.columns.tolist())
hist=E/'over1000_moscow_20261009/native_all_with_independent_county.csv.gz'; h=pd.read_csv(hist); d=d[d.region_norm.isin(['московская','москва'])].copy();d['derived_oldcounty']=d.source_record_id.map(h.set_index('source_record_id').derived_oldcounty)
r=pd.read_csv('/dev/shm/over500-20261009/residual.csv');r=r[r.region_norm.isin(['московская','москва'])];r.to_csv(O/'assigned111.csv',index=False)
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
inputs=[hist,E/'over1000_moscow_20261009/native2010_independent_county_anchor_inventory.csv.gz',*s.inputs,Path('/dev/shm/over500-20261009/residual.csv')]
manifest=[dict(path=str(f),sha256=sha(f),bytes=f.stat().st_size)for f in inputs];(O/'source_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
p.to_parquet('/dev/shm/over500-moscow-points.parquet',index=False);d.to_parquet('/dev/shm/over500-moscow-observations.parquet',index=False)
