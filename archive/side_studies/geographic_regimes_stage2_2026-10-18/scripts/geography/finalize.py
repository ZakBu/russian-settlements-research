from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
B=Path(__file__).parent;O=B/'outputs';m=pd.read_csv(O/'territory_metrics.csv');m['dominant_region']=m['dominant_region2002'];m['dominant_region_fraction']=m['dominant_region_row_fraction2002'];m['centre100k2002_km_median']=m['nearest100k2002_km_median'];m['nn_median_level_change_km']=m.nn2021_km_median-m.nn2002_km_median;m['nn_p90_level_change_km']=m.nn2021_km_p90-m.nn2002_km_p90;m.to_csv(O/'territory_metrics.csv',index=False)
# Concentration invariant to proportional changes, with deterministic UID tie, and aggregation conservation.
p=np.array([20.,20.,5.,0.]);uid=np.array(['b','a','c','d']);order=np.lexsort((uid,-p));k=int(np.ceil(len(p)*.1));share=p[order[:k]].sum()/p.sum();scaled=p*.72;assert share==scaled[order[:k]].sum()/scaled.sum();checks={'proportional_share_invariance':True,'deterministic_tie_top_uid':uid[order[0]],'conservation':{}}
for kind,g in m.groupby('kind'):
 assert g.n_rows.sum()==142570;assert g.population2002.sum()==127397236;assert g.population2021.sum()==125132003;checks['conservation'][kind]={'rows':int(g.n_rows.sum()),'pop2002':g.population2002.sum(),'pop2021':g.population2021.sum(),'units':len(g),'support20':int(g.support20.sum())}
(O/'aggregation_checks.json').write_text(json.dumps(checks,indent=2));(O/'FINAL_CHECKSUMS.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in O.iterdir() if p.is_file() and p.name!='FINAL_CHECKSUMS.json'},indent=2))
