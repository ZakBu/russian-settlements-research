from pathlib import Path
import json,pandas as pd,numpy as np
R=Path(__file__).resolve().parent
d=pd.read_parquet(R/'wb_objects_crosswalk.parquet');distance=d.wb_nearest_axis_distance_km
initial_candidate=d.wb_source_federal_address_label.eq('')&~d.wb_known_outside_research_country
final_candidate=d.wb_candidate_uid.notna()
old_outside=(d.latitude.between(44.2,46.4)&d.longitude.between(32.3,36.7)&distance.gt(50)&d.wb_strict_uid.isna())|d.wb_outside_common_axis_geography.eq('baikonur_no_frozen_axis_entry')
intermediate_candidate=d.wb_federal_address_candidate.eq('')&~d.wb_known_outside_research_country&~old_outside
initial_strict=d.settlement_uid.notna()&d.link_status.eq('name_coordinate_concordance')&d.wb_source_federal_address_label.eq('')
rows=[{'iteration':'initial_mass_join','source_objects':len(d),'strict_link_objects':int(initial_strict.sum()),'candidate_link_objects':int(initial_candidate.sum()),'candidate_distance_p99_km':float(distance[initial_candidate].quantile(.99)),'candidate_more_than20km_objects':int((initial_candidate&distance.gt(20)).sum()),'explanation':'Counterfactual reconstruction of original mass rule from preserved raw federal label; no outside-axis quarantine and coarse federal label preceding named UID'},
{'iteration':'first_geography_correction','source_objects':len(d),'strict_link_objects':int(d.wb_strict_uid.notna().sum()),'candidate_link_objects':int(intermediate_candidate.sum()),'candidate_distance_p99_km':float(distance[intermediate_candidate].quantile(.99)),'candidate_more_than20km_objects':int((intermediate_candidate&distance.gt(20)).sum()),'explanation':'Reconstruction of first actual correction: distance>50 gate still missed nearby non-axis places across Kerch Strait'},
{'iteration':'after_empty_axis_footprint_review','source_objects':len(d),'strict_link_objects':int(d.wb_strict_uid.notna().sum()),'candidate_link_objects':int(final_candidate.sum()),'candidate_distance_p99_km':float(distance[final_candidate].quantile(.99)),'candidate_more_than20km_objects':int((final_candidate&distance.gt(20)).sum()),'explanation':'Finer named UID preserved; unsupported shared-census-axis geography quarantined independently of proximity to axis edge; all source objects retained'}]
pd.DataFrame(rows).to_csv(R/'linkage_iteration_summary.csv',index=False)
assert rows[0]['strict_link_objects']==74844 and rows[1]['strict_link_objects']==74849
assert rows[1]['candidate_link_objects']==81576 and rows[1]['candidate_more_than20km_objects']==25
assert len(d)==91136 and d.object_id.is_unique
removed=int((initial_candidate&~final_candidate).sum())
assert removed>=1587
assert int((final_candidate&~initial_candidate).sum())==5
(R/'ITERATION_AUDIT.json').write_text(json.dumps({'status':'PASS','rows':rows,'removed_from_point_candidate_assignment':removed,'restored_finer_named_assignments':5,'source_objects_deleted':0,'notes':'Geography quarantine is footprint/coverage handling, not a claim about political boundaries. Candidate distance does not measure service influence.'},indent=2)+'\n')
print(json.dumps(rows,ensure_ascii=False))
