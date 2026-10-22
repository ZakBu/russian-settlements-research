#!/usr/bin/env python3
"""Conservation and linkage audit; counts are published-object counts, not census absence."""
from pathlib import Path
import json, hashlib
import pandas as pd
P=Path(__file__).resolve().parent
obj=pd.read_parquet(P/'education_objects.parquet');f=pd.read_parquet(P/'settlement_features_full_axis.parquet');legacy=pd.read_parquet(P/'settlement_features.parquet')
assert len(f)==173527 and f.id.is_unique and len(legacy)==142570 and legacy.id.is_unique
assert obj.site_id.is_unique
assert not (obj.baseline_uid.notna() & obj.candidate_uid.notna()).any()
assert set(obj.baseline_uid.dropna())|set(obj.candidate_uid.dropna()) <= set(f.id)
assert f.education_capacity.isna().all() and not f.education_capacity_total_known.any()
for c in [x for x in f if x.endswith('_observed_presence')]:assert not f[c].eq(False).any()
for g in obj.education_group.unique():
 for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
  c=f'education_osm_{g}_{mode}_count';subset=obj[obj.education_group.eq(g)&obj[key].notna()].drop_duplicates([key,'canonical_site_id'])
  assert f[c].sum()==len(subset),(c,f[c].sum(),len(subset))
assert obj.loc[obj.baseline_uid.notna(),'linked_distance_km'].le(5.00001).all()
assert obj.loc[obj.candidate_uid.notna(),'linked_distance_km'].le(2.50001).all()
f['rural_type_proxy']=~f.type.str.lower().isin(['город','пгт','посёлок городского типа','поселок городского типа'])
f['school_any']=f.education_osm_school_baseline_count.add(f.education_osm_school_candidate_additional_count).gt(0)
f['school_baseline']=f.education_osm_school_baseline_count.gt(0)
f.groupby(['region','rural_type_proxy'],dropna=False).agg(axis_settlements=('id','size'),school_baseline_settlements=('school_baseline','sum'),school_with_candidates_settlements=('school_any','sum')).reset_index().to_csv(P/'coverage_by_region_rural_proxy.csv',index=False)
rural=f[f.rural_type_proxy];s=obj[obj.education_group.eq('school')]
receipt={'status':'PASS','axis_rows':len(f),'legacy_rows':len(legacy),'source_rows':len(obj),'canonical_site_ids':obj.canonical_site_id.nunique(),'general_school_rows':len(s),'school_explicit_program_tag_rows':int(s.school_level_evidence.isin(['explicit_grades_tag_interpreted','explicit_isced_level_tag']).sum()),'school_name_only_level_signal_rows':int(s.school_level_evidence.eq('source_name_signal_not_verified_program').sum()),'school_numeric_capacity_rows':int(s.source_capacity_numeric.notna().sum()),'rural_type_proxy_axis_rows':len(rural),'rural_type_proxy_school_baseline_settlements':int(rural.school_baseline.sum()),'rural_type_proxy_school_with_candidates_settlements':int(rural.school_any.sum()),'external_unresolved_rows':int((obj.baseline_uid.isna()&obj.candidate_uid.isna()).sum()),'rural_definition':'type proxy excludes город, пгт, поселок городского типа; not an independent official urban/rural register','checks':['full and legacy unique UID cardinality','raw OSM identity uniqueness','baseline/candidate disjointness and foreign keys','all group count conservation','explicit link <=5km and candidate <=2.5km','unknown capacity not invented','unknown presence never false']}
(P/'validation_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
