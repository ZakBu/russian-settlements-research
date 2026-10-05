#!/usr/bin/env python3
"""Apply a compact exact-OKATO historical bridge rule to the pinned top-100 residual."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import duckdb
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
BASE=REPO/'research_rebuild/evidence/top60_and_proximity_review_20261005'
OUT=REPO/'research_rebuild/evidence/top100_classifier_bridge_20261005'
CANDIDATE=Path('/workspace/settlements-work/continuation_20261004/R4/large_current_remaining_route_top100_20261004/raw_classifier_code_candidate_edges.csv')
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
EDGES=Path('/workspace/settlements-work/continuation_20261004/accepted_mass_eleventh_reviewed28_point2/accepted_identity_edges.parquet')
POINTS=Path('/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet')
RESIDUAL=Path('/workspace/settlements-work/continuation_20261004/root/joint_residual_eleventh_norilsk2_krasnodar2_secondary2.parquet')
ACCEPTED={'checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted','case_review_accepted','independent_case_review_accepted','accepted_case_specific'}

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

candidates=pd.read_csv(CANDIDATE)
candidates=candidates[candidates.candidate_status.eq('candidate_for_independent_review')].copy()
candidates['population_ratio']=candidates[['population_2021','population_old']].max(axis=1)/candidates[['population_2021','population_old']].min(axis=1)
candidates['simple_rule_accept']=(candidates.population_ratio.le(2)&candidates.classifier_2011_distance_to_accepted_current_point_km.le(5)&candidates.old_selected_exact_tuple_count.eq(1)&candidates.current_okato_competitor_count_2021.eq(1)&candidates.current_okato_literal.astype(str).eq(candidates.classifier_2011_okato_literal.astype(str)))
accepted=candidates[candidates.simple_rule_accept].copy()
holds=candidates[~candidates.simple_rule_accept].copy()
if len(accepted)!=16 or accepted.source_record_id_current.nunique()!=15:
    raise RuntimeError(f'candidate cohort changed: {len(accepted)} edges/{accepted.source_record_id_current.nunique()} targets')

con=duckdb.connect(config={'threads':2,'memory_limit':'2GB'})
ids=con.execute('select source_record_id,census_year from read_parquet(?)',[str(SELECTED)]).fetchall()
parent={sid:sid for sid,year in ids}; years={sid:{int(year)} for sid,year in ids}
def find(x):
    if parent[x]!=x:parent[x]=find(parent[x])
    return parent[x]
def union(a,b):
    a,b=find(a),find(b)
    if a==b:return True
    if years[a]&years[b]:return False
    parent[b]=a;years[a]|=years[b];return True
for a,b in con.execute("select from_source_record_id,to_source_record_id from read_parquet(?) where relation='same_place' and decision_status in (select unnest(?))",[str(EDGES),sorted(ACCEPTED)]).fetchall():
    union(a,b)
# Include the prior simple deltas in this graph simulation.
prior=pd.read_csv(BASE/'simple_rule_application/accepted_identity_edge_delta.csv')
prior_cases=pd.read_csv(BASE/'simple_rule_application/top60_identity_edge_delta.csv')
for frame in (prior,prior_cases):
    for a,b in frame[['from_id','to_id']].itertuples(index=False,name=None):
        if not union(a,b):raise RuntimeError('prior admitted delta creates a same-year component conflict')
accepted['decision_id']=[f'EXACT-OKATO-{hashlib.sha256((str(r.source_record_id_old)+"|"+str(r.source_record_id_current)).encode()).hexdigest()[:16]}' for r in accepted.itertuples()]
accepted['decision_status']='checked_rule_accepted'
accepted['decision_rule']='exact old/current name type region; unique selected old tuple; current OKATO equals unique live historical OKATO classifier row; classifier point <=5km from accepted current point; population ratio <=2'
accepted['population_comparability_asserted']=False
accepted['boundary_comparability_asserted']=False
accepted['population_value_changed']=False
# A matched old source row without a point inherits the already accepted 2021 carrier point.
old_ids=sorted(accepted.source_record_id_old.astype(str).unique())
current_ids=sorted(accepted.source_record_id_current.astype(str).unique())
point_statuses=['reviewed_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_extension_rule_accepted','reviewed_case_accepted']
point_lookup=con.execute("select target_source_record_id,latitude,longitude,coordinate_source,point_origin_file,point_origin_sha256,point_origin_locator,coordinate_admission_status from read_parquet(?) where coordinate_admission_status in (select unnest(?)) and target_source_record_id in (select unnest(?))",[str(POINTS),point_statuses,old_ids]).fetchdf()
current_points=con.execute("select target_source_record_id,latitude,longitude,coordinate_source,point_origin_file,point_origin_sha256,point_origin_locator,coordinate_admission_status from read_parquet(?) where coordinate_admission_status in (select unnest(?)) and target_source_record_id in (select unnest(?))",[str(POINTS),point_statuses,current_ids]).fetchdf().set_index('target_source_record_id')
point_delta_rows=[]
for r in accepted.drop_duplicates('source_record_id_old').itertuples():
    if r.source_record_id_old in set(point_lookup.target_source_record_id.astype(str)): continue
    carrier=current_points.loc[r.source_record_id_current]
    # The exact classifier row must independently fall within the same 5 km bridge limit.
    point_delta_rows.append({'target_source_record_id':r.source_record_id_old,'target_year':int(r.year_old),'target_name':r.old_name,'target_type':r.old_type,'target_region':r.old_region_raw,'target_population':r.population_old,'carrier_source_record_id':r.source_record_id_current,'carrier_year':2021,'latitude':float(carrier.latitude),'longitude':float(carrier.longitude),'carrier_point_source':carrier.coordinate_source,'carrier_point_origin_file':carrier.point_origin_file,'carrier_point_origin_sha256':carrier.point_origin_sha256,'carrier_point_origin_locator':carrier.point_origin_locator,'historical_classifier_distance_km':float(r.classifier_2011_distance_to_accepted_current_point_km),'coordinate_admission_status':'reviewed_case_accepted','coordinate_application_family':'exact_classifier_code_bridge_retrospective_point_reuse_20261005','population_value_changed':False,'measurement_date_unknown':True,'boundary_comparability_asserted':False,'provider_identifier_binding_asserted':False})
# Require source IDs and no duplicate census year after adding whole package.
for a,b in accepted[['source_record_id_old','source_record_id_current']].itertuples(index=False,name=None):
    if not union(a,b):raise RuntimeError('new code bridge would repeat a census year in a component')
OUT.mkdir(exist_ok=True)
accepted.to_csv(OUT/'accepted_classifier_bridge_delta.csv',index=False)
pd.DataFrame(point_delta_rows).to_csv(OUT/'old_point_use_delta.csv',index=False)
holds.to_csv(OUT/'held_classifier_bridge_candidates.csv',index=False)
res=con.execute('select source_record_id,census_year,population from read_parquet(?)',[str(RESIDUAL)]).fetchdf()
accepted_ids=set(accepted.source_record_id_old)|set(accepted.source_record_id_current)
matched=res[res.source_record_id.isin(accepted_ids)]
# The residual join reports only new selected population outside the pre-existing joint axis.
matched.to_csv(OUT/'residual_rows_reached_by_delta.csv',index=False)
manifest={
 'status':'accepted_additive_top100_exact_classifier_bridge_delta',
 'inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in (CANDIDATE,SELECTED,EDGES,POINTS,RESIDUAL)},
 'candidate_edges':int(len(candidates)),'accepted_edges':int(len(accepted)),'accepted_current_targets':int(accepted.source_record_id_current.nunique()),
 'accepted_2021_unique_target_population':int(accepted.drop_duplicates('source_record_id_current').population_2021.sum()),
 'old_missing_point_uses_added':len(point_delta_rows),'old_point_population_added':int(sum(x['target_population'] for x in point_delta_rows)),
 'accepted_edges_by_old_year':{str(int(y)):int(n) for y,n in accepted.groupby('year_old').size().items()},
 'ratio_over_2_held':int((candidates.population_ratio>2).sum()),'candidate_holds_total':int(len(holds)),
 'residual_rows_reached':int(len(matched)),'residual_population_reached_by_year':{str(int(y)):int(v) for y,v in matched.groupby('census_year').population.sum().items()},
 'full_current_graph_union_simulation':True,'added_same_year_conflicts':0,
 'population_values_modified':False,'boundary_or_population_comparability_asserted':False,
 'note':'Accepted links use an exact unique historical-classifier/code route plus same name/type/region, local point agreement and <=2x population change. Values remain at their source quality; this is identity only.'}
(OUT/'summary.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(OUT/'README.md').write_text('''# Связи топ-100 остатка по точному историческому ОКАТО\n\nПрименено правило к подготовленной когорте 2021 года: точное совпадение имени, типа и региона; уникальная старая выбранная строка; ОКАТО выбранной строки 2021 совпадает с единственной активной строкой исторического классификатора; точка строки классификатора находится не дальше 5 км от уже принятой точки 2021; население отличается не более чем вдвое. Связь означает только физическую идентичность, не сопоставимость переписной численности или границ.\n\nПринятые строки и остаточные записи, которые они достигают, приведены в CSV; входные SHA и итог полного графового объединения — в `summary.json`. Все добавленные связи прошли симуляцию на полном выбранном ID-графе вместе с ранее принятыми дельтами; конфликтов повторного года нет.\n''',encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
