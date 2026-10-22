"""Localize only coordinator-selected pairs; never reselect illustrations."""
from pathlib import Path
import pandas as pd,json,hashlib
B=Path(__file__).parent
selected=pd.read_csv(B.parent/'comparison/selected_illustrations.csv')
pts=pd.read_csv(B.parent/'geo/outputs/point_distances.csv.gz')
rawpath=Path('/workspace/scratch/c21afd18c709/repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz')
cols=['entity_uid']+[f'{v}_{y}' for y in [2002,2010,2021] for v in ['settlement_name','population','population_value_quality','source_locator']]
raw=pd.read_csv(rawpath,usecols=cols)
d=pts.merge(raw,on='entity_uid',validate='one_to_one')
summ=[]
for r in selected.to_dict('records'):
 for side in ['a','b']:
  q=d[d[r['kind']].astype(str)==str(r[side])].copy()
  q=q.sort_values(['population_2002','entity_uid'],ascending=[False,True]);q.to_csv(B/f"{r['selection']}_{side}_roster.csv",index=False)
  summ.append({'selection':r['selection'],'side':side,'kind':r['kind'],'unit':r[side],'n':len(q),'bounds2002':[q.longitude_2002.min(),q.latitude_2002.min(),q.longitude_2002.max(),q.latitude_2002.max()],'region_counts':q.effective_region_norm_2002.value_counts().to_dict(),'largest2002':q[['entity_uid','settlement_name_2002','population_2002','population_2021','latitude_2002','longitude_2002']].head(8).to_dict('records')})
(B/'localization.json').write_text(json.dumps(summ,ensure_ascii=False,indent=2))
(B/'localization_receipt.json').write_text(json.dumps({'raw_sha256':hashlib.sha256(rawpath.read_bytes()).hexdigest(),'selection_sha256':hashlib.sha256((B.parent/'comparison/selected_illustrations.csv').read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2))
