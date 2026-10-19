"""Independent output audit. Does not import run.py."""
import pandas as pd,numpy as np,json
from pathlib import Path
O=Path(__file__).parent
w=pd.read_csv(O/'municipality_zone_matrix.csv.gz',dtype={'oktmo':str})
assert not w.duplicated(['oktmo','center_id']).any()
for s in ['count','population2010','population2021']:assert np.allclose(w.groupby('oktmo')['weight_'+s].sum(),1,atol=1e-10)
b=pd.read_csv(O/'mass_balance.csv');assert np.allclose(b.source_sum,b.allocated_sum,atol=1e-5,rtol=1e-12)
f=pd.read_csv(O/'zone_functional_main.csv');assert not f.center_id.duplicated().any();assert f.coverage.between(0,1).all();assert f.loc[f.coverage.lt(.8),'functional_context'].eq('missing').all();assert f.scheme.eq('count').all();assert f.coverage_threshold.eq(.8).all();assert f.dominance_threshold.eq(.6).all()
sh=f.filter(regex='^share_').sum(axis=1,min_count=1);assert np.allclose(sh.dropna(),1,atol=1e-10)
c=pd.read_csv(O/'municipal_crop_profiles_2021.csv');groups=['grain','technical','fodder','potato','vegetables','melon'];mixed=c[c.municipal_profile.eq('mixed')];assert mixed[groups].notna().all().all();assert mixed.sum_known_share.ge(.9).all();assert not c.loc[c.inconsistent,'municipal_profile'].ne('missing').any()
r=pd.read_parquet(O/'municipal_series_2006_2024.parquet');y=pd.to_numeric(r.oktmo_year_from,errors='coerce');t=pd.to_numeric(r.oktmo_year_to,errors='coerce');r['within_declared_code_interval']=r.year.ge(y)&r.year.le(t);r['code_interval_available']=y.notna()&t.notna();r.groupby(['year','indicator_code','oktmo_history','code_interval_available','within_declared_code_interval'],dropna=False).size().rename('rows').reset_index().to_csv(O/'territorial_time_audit.csv',index=False)
panel=pd.read_parquet(O.parent/'data/panel.parquet',columns=['id','population_2010']);bridge=pd.read_parquet(O/'settlement_municipality_zone.parquet');assert set(panel.id)==set(bridge.id);assert f.loc[f.dominance.isna()|f.coverage.eq(0),'dominant_profile'].eq('unobserved').all()
report={'zero2010_retained':int(panel.population_2010.eq(0).sum()),'panel_ids_preserved':True,'status':'passed','matrix_weight_checks':3,'mass_checks':len(b),'functional_zones':len(f),'mixed_municipalities':len(mixed),'six_observed_groups':groups,'data_year_min':int(r.year.min()),'data_year_max':int(r.year.max()),'interpretation':'2021 municipal contextual composition; historical code series retained without asserting constant territories'}
(O/'verification.json').write_text(json.dumps(report,indent=2));print(report)
