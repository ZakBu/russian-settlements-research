import json
from pathlib import Path
import pandas as pd
P=Path('research_staging/e3');d=pd.read_csv(P/'regional_curves.csv');q=d[d.grid.eq('absolute_km')].copy();out={'development_only':True,'geometric_not_transport':True,'conditional_null_test_performed':False,'lcc_monotonicity_violations':int((d.surviving_lcc_n>d.initial_lcc_n).sum()),'by_radius':[]}
for r,g in q.groupby('radius_value'):
 rise=g.surviving_lcc_active>g.initial_lcc_active+1e-12;fall=g.surviving_lcc_fixed<g.initial_lcc_fixed-1e-12
 out['by_radius'].append(dict(radius_km=r,regions=len(g),regions_active_denominator_rises=int(rise.sum()),regions_active_rises_fixed_falls=int((rise&fall).sum()),development_initial_n=int(g.initial_n.sum()),development_zero2021_n=int(g.zero2021_n.sum()),weighted_lcc_fixed_loss=float(((g.initial_lcc_fixed-g.surviving_lcc_fixed)*g.initial_n).sum()/g.initial_n.sum())))
examples=q[(q.radius_value==10)&q.region.isin(['ивановская','кировская','карелия'])][['region','initial_n','zero2021_n','initial_lcc_fixed','surviving_lcc_fixed','surviving_lcc_active']]
out['examples']=examples.to_dict(orient='records');(P/'descriptive_summary.json').write_text(json.dumps(out,indent=2,ensure_ascii=False));print(json.dumps(out,ensure_ascii=False))
