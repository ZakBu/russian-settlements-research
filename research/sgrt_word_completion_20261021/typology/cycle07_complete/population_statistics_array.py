"""Array reductions equivalent to the admitted per-object population stats helper."""
from collections import Counter
import json
import numpy as np
import pandas as pd
PRIMARY={'direct_published_census_value','reviewed_primary_reported_value','reviewed_primary_source_value_or_null','direct_official_city_value','fresh_primary_r5_source','reviewed_primary_source_child_partition','reviewed_primary_control_derived_zero'}
SECONDARY='secondary_confidentiality_protected_value_exact_scope_unverified'
def stats_array(data,year):
 values=pd.to_numeric(data[f'population_{year}'],errors='coerce')
 if pd.api.types.is_bool_dtype(values.dtype):raise ValueError('Boolean population')
 p=values.to_numpy(dtype=float,na_value=np.nan);valid=np.isfinite(p)&(p>=0);q=data[f'population_value_quality_{year}'].fillna('quality_unavailable').to_numpy(dtype=object);primary=np.isin(q,list(PRIMARY));secondary=q==SECONDARY;total=float(p[valid].sum()) if valid.any() else np.nan
 return {'known_sum':total,'complete':bool(len(p)>0 and valid.all()),'n_missing':int((~valid).sum()),'n_zero':int((p[valid]==0).sum()),'primary_complete':bool(len(p)>0 and valid.all() and primary.all()),'primary_share':float(p[valid&primary].sum()/total) if total>0 else np.nan,'secondary_share':float(p[valid&secondary].sum()/total) if total>0 else np.nan,'qualities':json.dumps(dict(Counter(q.tolist()).most_common()),ensure_ascii=False)}
