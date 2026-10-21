"""Independent output readback; pyproj is the shared WGS84 numerical primitive."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from pyproj import Geod
R=Path.cwd(); B=R/'maps/cycle07_current_primary_binding_v1'; O=R/'delivery/cycle07_current_primary_v1/atlas_v2/main'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
n=pd.read_parquet(B/'nodes.parquet').set_index('id');u=pd.read_parquet(B/'all_units.parquet').set_index('unit_id');m=pd.read_parquet(B/'memberships.parquet');got=pd.read_csv(O/'cartometric_known_member_extent.csv.gz').set_index('unit_id')
assert set(got.index)==set(u.index) and got.index.is_unique
c=m.unit_id.map(u.core_id); x=m.id.map(n.lon).to_numpy(float);y=m.id.map(n.lat).to_numpy(float);cx=c.map(n.lon).to_numpy(float);cy=c.map(n.lat).to_numpy(float)
valid=np.isfinite(x)&np.isfinite(y)&np.isfinite(cx)&np.isfinite(cy)&(abs(x)<=180)&(abs(cx)<=180)&(abs(y)<=90)&(abs(cy)<=90)
a=np.full(len(m),np.nan);geo=Geod(ellps='WGS84');a[valid]=geo.inv(x[valid],y[valid],cx[valid],cy[valid])[2]/1000
assert abs(geo.inv(0,0,1,0)[2]/1000-111.31949079327357)<1e-10
m['independent_km']=a; g=m.groupby('unit_id').independent_km.agg(['max','count','size']).reindex(got.index)
np.testing.assert_allclose(got.max_known_geodesic_km,g['max'],rtol=0,atol=1e-10,equal_nan=True)
assert np.array_equal(got.n_geodesic_known,g['count']) and np.array_equal(got.n_members_total,g['size'])
assert np.array_equal(got.n_geodesic_unknown,g['size']-g['count'])
assert np.array_equal(got.geographic_extent_complete,(g['size']==g['count']))
assert np.array_equal(got.lower_bound_due_to_missing_coords,(g['size']>g['count']))
assert got.loc[g['count'].eq(0),'max_known_geodesic_km'].isna().all()
quality=pd.read_csv(O/'source_quality_by_view.csv').set_index('level')
for level,d in u.groupby('level'):
 if level not in quality.index:continue
 den=d.population2010_known_denominator;share=d.protected_secondary2010_population_share;ok=den.gt(0)&share.notna();v=quality.loc[level];total=den[ok].sum()
 assert v.n_units==len(d) and v.units_with_missing_additive2010==int(d['2010_missing_population_count'].gt(0).sum())
 np.testing.assert_allclose(v.known_population2010_denominator,total,rtol=0,atol=1e-6)
 np.testing.assert_allclose(v.secondary_share_of_known_population2010,(den[ok]*share[ok]).sum()/total,rtol=0,atol=1e-12)
r={'status':'ACCEPTED','all_checks_passed':True,'unit_rows':len(got),'membership_rows':len(m),'independent_scope':'Entire known-member WGS84 extent aggregation and missingness/count readback from bound source tables, plus separate-view population-weighted quality denominators. No producer import. Shared pyproj geodesic primitive; not an independent ellipsoidal solver. No functional-boundary inference.','source_sha256':{str(p.relative_to(R)):sha(p)for p in [B/'nodes.parquet',B/'all_units.parquet',B/'memberships.parquet',O/'cartometric_known_member_extent.csv.gz',O/'source_quality_by_view.csv']}}
(R/'reviews/cycle07_atlas_cartometry_independent_v1/admission.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False))
