#!/usr/bin/env python3
"""Source-level equivalence check against direct full-reference radius searches; no model inputs."""
import importlib.util,json,re
from pathlib import Path
import numpy as np,pandas as pd
from scipy.spatial import cKDTree
P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('relink',P/'relink_sources_2021.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
a=pd.read_parquet(m.AXIS);a=a[np.isfinite(a.lat)&np.isfinite(a.lon)&a.population_2021.notna()&a.is_additive_source_unit.eq(True)&~a.axis_kind.fillna('').str.contains('territory',case=False)].reset_index(drop=True);xyz=m.xyz(a.lat.values,a.lon.values);tree=cKDTree(xyz);rows=[]
for family in ['education','commerce','medical']:
 d=pd.read_parquet(P/family/'source_objects_relinked.parquet');medical=family=='medical';names=a.name.map(m.mn if medical else m.en).to_numpy();ix=sorted(set(range(min(256,len(d))))|set(np.random.default_rng(20261021).choice(len(d),min(256,len(d)),replace=False))|set(d.index[d.baseline_changed_from_previous_axis]));checked=0
 for i in ix:
  r=d.iloc[i]
  if not np.isfinite(r.lat) or not np.isfinite(r.lon):continue
  t=json.loads(r.tags_json);keys=['addr:city','addr:village','addr:hamlet'] if medical else ['addr:city','addr:village','addr:hamlet','addr:place','is_in:city'];loc=next((t[k] for k in keys if t.get(k)),None);literal=m.mn(loc) if medical else re.sub(r'^(город|село|деревня|поселок|г|с|д|п)\s+','',m.en(loc)) if loc else '';point=m.xyz([r.lat],[r.lon])[0]
  radius=10 if medical else 5;near=tree.query_ball_point(point,2*np.sin(radius/12742.0176));matches=[j for j in near if names[j]==literal] if literal else [];baseline=None;conditional=None
  if len(matches)==1:
   j=matches[0];dist=m.distance(np.linalg.norm(point-xyz[j]));
   if medical and dist>5:conditional=a.iloc[j].id
   else:baseline=a.iloc[j].id
  assert (r.baseline_uid if pd.notna(r.baseline_uid) else None)==baseline,(family,i,'baseline')
  if medical:assert (r.conditional_uid if pd.notna(r.conditional_uid) else None)==conditional,(family,i,'conditional')
  else:
   v,j=tree.query(point,k=2);v=m.distance(v);candidate=None
   if baseline is None and v[0]<=2.5 and v[1]>=max(v[0]*1.5,v[0]+.25) and (not literal or names[j[0]]==literal) and literal not in {'москва','санкт петербург','санктпетербург','севастополь'}:candidate=a.iloc[j[0]].id
   assert (r.candidate_uid if pd.notna(r.candidate_uid) else None)==candidate,(family,i,'candidate')
  checked+=1
 # Exhaustive counted canonical uniqueness and new-frame admissibility.
 canonical='count_canonical_site_id' if medical else 'canonical_site_id';channels=[c for c in d if c.startswith('count_') and c.endswith('_uid')];allc=pd.concat([d[[canonical,c]].rename(columns={c:'uid'}).dropna() for c in channels]);assert allc.groupby(canonical).uid.nunique().le(1).all();assert allc.uid.isin(a.id).all();features=pd.read_parquet(P/family/'settlement_features_full_axis.parquet');assert len(features)==173862 and features.id.is_unique
 rows.append({'family':family,'direct_ball_query_objects_checked':checked,'selection':'all changed baseline rows plus first256 and fixedseed20261021 random256; union; unlocated skipped','all_counted_canonical_one_UID':True,'all_counted_UIDs_in_current_reference':True,'all173862_features':True})
r={'status':'PASS_SOURCE_LEVEL_EQUIVALENCE_AND_EXHAUSTIVE_COUNT_GUARDS','results':rows,'model_results_read':False,'author_self_check_not_independent_review':True,'code_sha256':m.sha(Path(__file__))};(P/'source_semantics_self_check.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
