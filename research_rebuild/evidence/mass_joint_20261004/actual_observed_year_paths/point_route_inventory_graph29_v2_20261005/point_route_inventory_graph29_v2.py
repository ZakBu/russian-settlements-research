#!/usr/bin/env python3
"""Read-only current Graph29 point-route inventory. Writes summary JSON and grouped CSV in /tmp."""
from pathlib import Path
import duckdb, hashlib, json, csv
BASE=Path('/tmp')
OUT=BASE/'point_route_inventory_graph29_v2'
OUT.mkdir(exist_ok=True)
SEL='/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
POINT='/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet'
EDGE='/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet'
CAND='/workspace/settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet'
AVAIL='/workspace/settlements-work/continuation_20261003/consolidated_alias_and_dagestan_aux_v2/legacy_availability_projected_r5.parquet'
FILES=[SEL,POINT,EDGE,CAND,AVAIL]
def sha(p):
 h=hashlib.sha256();
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
con=duckdb.connect()
# Current selected years, accepted points, and their exact residual.
con.execute(f"CREATE VIEW s AS SELECT * FROM read_parquet('{SEL}') WHERE census_year IN (2002,2010) AND COALESCE(is_additive_settlement_record,true) AND source_record_id NOT IN ('2002:1_TOM_01_04.xls:0:3218','2010:pub-11-1-4.pdf:pdf_page_11:41','2010:pub-11-1-4.pdf:pdf_page_15:39')")
POINT_STATUSES=['reviewed_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_extension_rule_accepted','reviewed_case_accepted']
status_sql=','.join("'"+x+"'" for x in POINT_STATUSES)
con.execute(f"CREATE VIEW p AS SELECT * FROM read_parquet('{POINT}') WHERE TRY_CAST(target_year AS INT) IN (2002,2010) AND coordinate_admission_status IN ({status_sql})")
con.execute(f"CREATE VIEW r AS SELECT s.* FROM s LEFT JOIN p ON p.target_source_record_id=s.source_record_id WHERE p.target_source_record_id IS NULL")
# Candidate key uniqueness measured in selected year+region+typed name.
# If path parameter views unsupported, create via interpolation fallback.
con.execute(f"CREATE VIEW c AS SELECT *, count(DISTINCT historical_okato_2011_raw) OVER (PARTITION BY census_year,longitude_from_long,latitude_from_lat) AS exact_geo_collision_n FROM read_parquet('{CAND}')")
con.execute(f"CREATE VIEW a AS SELECT source_record_id, any_legacy_point_available, legacy_availability_projection_basis FROM read_parquet('{AVAIL}')")
# Candidate columns are sparse outside candidate rows; duplicate candidate records collapse conservatively.
con.execute('''CREATE VIEW cj AS SELECT source_record_id, census_year, settlement_type, region_norm, name_norm, type_norm, population,
 max(CASE WHEN historical_named_point_candidate AND historical_name_exact AND historical_type_exact AND is_additive_settlement_record THEN 1 ELSE 0 END) candidate,
 max(CASE WHEN historical_named_point_candidate AND code_join_basis='exact_raw_code' THEN 1 ELSE 0 END) exact_code,
 max(CASE WHEN historical_named_point_candidate AND code_join_basis='typed_urban_8digit_plus_zero_third_geo_group' THEN 1 ELSE 0 END) typed_city_bridge,
 max(CASE WHEN historical_named_point_candidate AND COALESCE(possible_unlocated_historical_competitor,false) THEN 1 ELSE 0 END) competitor,
 max(CASE WHEN historical_named_point_candidate AND COALESCE(exact_geo_collision_n,0)>1 THEN 1 ELSE 0 END) shared_coord,
 max(CASE WHEN historical_named_point_candidate AND COALESCE(historical_key_region_name_type_count,0)>1 THEN 1 ELSE 0 END) source_typed_duplicate,
 max(CASE WHEN historical_named_point_candidate AND latitude_from_lat BETWEEN -90 AND 90 AND longitude_from_long BETWEEN -180 AND 180 THEN 1 ELSE 0 END) valid_coord,
 max(CASE WHEN historical_named_point_candidate AND latitude_from_lat IS NOT NULL AND longitude_from_long IS NOT NULL THEN 1 ELSE 0 END) has_coord,
 max(coalesce(provider_coordinate_duplicate_count,0)) coord_dup_n
 FROM c GROUP BY ALL''')
# selected typed key uniqueness independently from exact selected rows
con.execute('''CREATE VIEW keycounts AS SELECT census_year,region_norm,name_norm,type_norm,count(*) selected_typed_key_n FROM s GROUP BY ALL''')
con.execute('''CREATE VIEW r2 AS SELECT r.*, kc.selected_typed_key_n AS typed_key_n FROM r LEFT JOIN keycounts kc USING(census_year,region_norm,name_norm,type_norm)''')
con.execute('''CREATE VIEW prof AS SELECT r2.*, coalesce(cj.candidate,0) candidate,
 coalesce(cj.exact_code,0) exact_code,coalesce(cj.typed_city_bridge,0) typed_city_bridge,
 coalesce(cj.competitor,0) competitor,coalesce(cj.shared_coord,0) shared_coord,
 coalesce(cj.source_typed_duplicate,0) source_typed_duplicate,
 coalesce(cj.valid_coord,0) valid_coord,coalesce(cj.has_coord,0) has_coord,
 coalesce(cj.coord_dup_n,0) coord_dup_n, coalesce(a.any_legacy_point_available,false) legacy_route,
 CASE WHEN coalesce(cj.candidate,0)=1 AND coalesce(cj.valid_coord,0)=1 AND coalesce(cj.shared_coord,0)=0 AND coalesce(cj.competitor,0)=0 AND coalesce(cj.source_typed_duplicate,0)=0 AND r2.typed_key_n=1 AND coalesce(cj.exact_code,0)=1 THEN 'candidate_unique_exact_code_no_collision'
 WHEN coalesce(cj.candidate,0)=1 AND coalesce(cj.valid_coord,0)=1 AND coalesce(cj.shared_coord,0)=1 THEN 'candidate_shared_point_collision'
 WHEN coalesce(cj.candidate,0)=1 AND coalesce(cj.valid_coord,0)=1 AND coalesce(cj.competitor,0)=1 THEN 'candidate_ambiguous_unlocated_competitor'
 WHEN coalesce(cj.candidate,0)=1 AND coalesce(cj.valid_coord,0)=1 AND coalesce(cj.typed_city_bridge,0)=1 THEN 'candidate_typed_city_code_bridge_hold'
 WHEN coalesce(cj.candidate,0)=1 THEN 'candidate_other_hold_or_invalid_coordinate'
 WHEN coalesce(a.any_legacy_point_available,false) THEN 'legacy_route_available_candidate_unclassified'
 ELSE 'no_route_or_unknown' END route_status,
 CASE WHEN coalesce(cj.candidate,0)=1 THEN 'GeoKLADR_2011_named_point' WHEN coalesce(a.any_legacy_point_available,false) THEN 'R5_provider_unspecified' ELSE 'none_or_unknown' END provider
 FROM r2 LEFT JOIN cj ON cj.source_record_id=r2.source_record_id LEFT JOIN a ON a.source_record_id=r2.source_record_id''')
# Accepted-point intersection on full selected rows
accepted=con.execute(f"SELECT s.census_year,s.settlement_type,s.source_record_id,s.population FROM s JOIN p ON p.target_source_record_id=s.source_record_id").fetchall()
# Components use the exact allowlist from measure_actual_observed_year_path_coverage_v2_20261005.py.
EDGE_STATUSES=['checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted','case_review_accepted','independent_case_review_accepted','accepted_case_specific']
edge_sql=','.join("'"+x+"'" for x in EDGE_STATUSES)
edges=con.execute(f"SELECT from_source_record_id,to_source_record_id FROM read_parquet('{EDGE}') WHERE relation='same_place' AND decision_status IN ({edge_sql})").fetchall()
all_selected=con.execute(f"SELECT source_record_id,census_year FROM read_parquet('{SEL}')").fetchall()
all_ids=[x[0] for x in all_selected]
if len(all_ids)!=len(set(all_ids)):
 raise ValueError('selected observation IDs are not unique')
parent={sid:sid for sid in all_ids}
def find(x):
 while parent[x] != x:
  parent[x]=parent[parent[x]]
  x=parent[x]
 return x
def union(a,b):
 ra,rb=find(a),find(b)
 if ra!=rb: parent[rb]=ra
for a,b in edges:
 a,b=str(a),str(b)
 if a not in parent or b not in parent:
  raise ValueError(f'accepted edge endpoint missing from selected: {a} / {b}')
 union(a,b)
years_by_root={}
for sid,year in all_selected:
 years_by_root.setdefault(find(sid),[]).append(int(year))
valid_roots={root for root,years in years_by_root.items() if len(years)==len(set(years)) and len(set(years))>=2}
path_ids={sid for sid in parent if find(sid) in valid_roots}
nontrivial_roots={root for root,years in years_by_root.items() if len(years)>1}
accepted_component_count=len(nontrivial_roots)
valid_component_count=len(valid_roots)
# accepted point targets are the exact status-filtered rows used for the coverage measure
# summary aggregation
rows=con.execute("SELECT census_year, coalesce(settlement_type,'(missing)') typ, provider, route_status, count(*) n, sum(coalesce(population,0)) pop, sum(candidate) candidates, sum(valid_coord) valid_candidates FROM prof GROUP BY 1,2,3,4 ORDER BY 1,2,3,4").fetchall()
with open(OUT/'by_year_type_provider_route.csv','w',newline='') as f:
 w=csv.writer(f);w.writerow(['year','settlement_type','provider_route','route_status','rows','population','candidate_rows','valid_candidate_rows']);w.writerows(rows)
summary=[]
for yr in (2002,2010):
 vals=con.execute("SELECT route_status,count(*),sum(coalesce(population,0)),sum(candidate),sum(valid_coord),sum(CASE WHEN source_record_id IN (SELECT target_source_record_id FROM p) THEN 1 ELSE 0 END) FROM prof WHERE census_year=? GROUP BY route_status ORDER BY route_status",[yr]).fetchall()
 candidate_max=con.execute("SELECT count(*),sum(coalesce(population,0)) FROM prof WHERE census_year=? AND candidate=1 AND valid_coord=1",[yr]).fetchone()
 marginal=con.execute("SELECT sum(candidate),sum(CASE WHEN candidate=1 AND valid_coord=1 THEN 1 ELSE 0 END),sum(CASE WHEN candidate=1 AND shared_coord=1 THEN 1 ELSE 0 END),sum(CASE WHEN candidate=1 AND competitor=1 THEN 1 ELSE 0 END),sum(CASE WHEN candidate=1 AND typed_city_bridge=1 THEN 1 ELSE 0 END),sum(CASE WHEN candidate=1 AND exact_code=1 THEN 1 ELSE 0 END),sum(CASE WHEN candidate=1 AND typed_key_n=1 THEN 1 ELSE 0 END) FROM prof WHERE census_year=?",[yr]).fetchone()
 rem=con.execute("SELECT count(*),sum(coalesce(population,0)) FROM r WHERE census_year=?",[yr]).fetchone()
 summary.append({'year':yr,'current_residual_rows':rem[0],'current_residual_population':rem[1],'routes':[{ 'status':v[0],'rows':v[1],'population':v[2],'candidate_rows':v[3],'valid_coordinate_rows':v[4]} for v in vals], 'candidate_valid_coordinate_upper_bound_not_gain':{'rows':candidate_max[0],'population':candidate_max[1]}, 'candidate_gate_marginals_overlapping':{'candidate_rows':marginal[0],'valid_coordinate_rows':marginal[1],'exact_historical_point_collision_rows':marginal[2],'possible_unlocated_competitor_rows':marginal[3],'typed_city_code_bridge_rows':marginal[4],'exact_raw_code_rows':marginal[5],'unique_selected_typed_key_rows':marginal[6]}, 'residual_in_accepted_same_place_components':con.execute("SELECT count(*),sum(coalesce(population,0)) FROM prof WHERE census_year=?",[yr]).fetchone()})
# exact intersection stats via Python IDs
profrows=con.execute('SELECT census_year,source_record_id,population,route_status FROM prof').fetchall()
for s in summary:
 yy=s['year']; ids={x[1] for x in profrows if x[0]==yy}; inter=ids & path_ids
 s['residual_rows_in_accepted_same_place_components']=len(inter)
 s['residual_population_in_accepted_same_place_components']=sum((x[2] or 0) for x in profrows if x[0]==yy and x[1] in inter)
 s['accepted_point_use_rows_for_year']=sum(1 for x in accepted if x[0]==yy)
 s['accepted_point_population_for_year']=sum((x[3] or 0) for x in accepted if x[0]==yy)
 s['accepted_point_same_place_components_intersection_rows']=sum(1 for x in accepted if x[0]==yy and x[2] in path_ids)
 s['accepted_point_same_place_components_intersection_population']=sum((x[3] or 0) for x in accepted if x[0]==yy and x[2] in path_ids)
 s['residual_path_intersections_by_route_status']=[{'status':status,'rows':sum(1 for x in profrows if x[0]==yy and x[1] in path_ids and x[3]==status),'population':sum((x[2] or 0) for x in profrows if x[0]==yy and x[1] in path_ids and x[3]==status)} for status in sorted({x[3] for x in profrows if x[0]==yy and x[1] in path_ids})]
# current full-residual profile exact typed uniqueness and coordinates already summarized
receipt={'status':'read_only_graph29_current_selected_residual_point_route_profile_graph_allowlist_v2','inputs':{p:{'sha256':sha(p),'bytes':Path(p).stat().st_size} for p in FILES},'graph29_receipt':{'path':'/workspace/russian-settlements-research/research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths/graph29_ozherele_historical_points_20261005/application_receipt.json','sha256':sha('/workspace/russian-settlements-research/research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths/graph29_ozherele_historical_points_20261005/application_receipt.json')},'graph29_config':{'path':'/workspace/russian-settlements-research/research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths/graph29_ozherele_historical_points_20261005/config_graph29.json','sha256':sha('/workspace/russian-settlements-research/research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths/graph29_ozherele_historical_points_20261005/config_graph29.json')},'accepted_point_rows_total':con.execute(f"select count(*) from read_parquet('{POINT}')").fetchone()[0],'edge_status_allowlist':EDGE_STATUSES,'point_status_allowlist':POINT_STATUSES,'accepted_same_place_edges_allowlisted':len(edges),'accepted_same_place_nontrivial_component_count':accepted_component_count,'accepted_same_place_path_component_count_at_least_two_years_no_duplicate_year':valid_component_count,'selected_node_count':len(all_ids),'accepted_edge_endpoints_validated':True,'years':summary,'classification_note':'Historical route candidates are GeoKLADR 2011 named-point candidates. Legacy R5 availability is current-reintersected to Graph29 residual IDs but has no provider attribution in its schema. Candidate-valid coordinates form only a theoretical upper bound, not an increment. Shared points, competitor flags, typed-city bridge candidates, and route candidates are holds.'}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False,indent=2))
