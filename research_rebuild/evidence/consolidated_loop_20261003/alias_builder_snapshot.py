"""Stage exact six-source-profile alias candidates; create no admissions."""
from pathlib import Path
import hashlib,json,time
import pandas as pd
T=time.perf_counter(); C=Path('/workspace/settlements-work/continuation_20261003'); E=Path('/workspace/settlements-delivery/continuation-loop-20261003')
PROFILE=C/'shared_named_point_region_profile_probe_v1'; PREV=C/'shared_named_point_identity_stage_v1'
OUT=Path(__file__).parent
BASE_GRAPH=E/'accepted_identity_edges.parquet'; SELECTED=E/'selected_observations.parquet'
POINTS=C/'accepted_direct_historical_point_2021_delta_v1/accepted_point_uses.parquet'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
review=json.loads((PROFILE/'summary.json').read_text())
if review['six_explicit_alias_candidates']!=1139: raise ValueError('reviewed alias profile count changed')
prof=pd.read_parquet(PROFILE/'ordinary_region_alias_profile_pairs.parquet')
orig=pd.read_parquet(PREV/'candidate_identity_edges.parquet')
oldchecks=pd.read_parquet(PREV/'source_row_checks.parquet')
oldapps=pd.read_parquet(PREV/'application_checks.parquet')
if len(prof)!=1139 or prof.edge_id.duplicated().any(): raise ValueError('profile must be exact unique 1139')
prof=prof.set_index('edge_id',drop=False); orig=orig[orig.edge_id.astype(str).isin(set(prof.index))].copy()
if len(orig)!=1139: raise ValueError('exact alias edge set missing in frozen candidate edges')
if set(orig.edge_id.astype(str))!=set(prof.index): raise ValueError('profile/candidate IDs differ')
base=pd.read_parquet(BASE_GRAPH)
if len(base)!=176568: raise ValueError(f'current accepted graph count is {len(base)}, expected 176568')
selected=pd.read_parquet(SELECTED,columns=['source_record_id','census_year','settlement_name','settlement_type','source_name_raw','source_file','source_sheet','source_row','source_sha256','source_locator','name_norm','type_norm','region_norm','region_raw','population','is_additive_settlement_record','entity_grain_status','oktmo','okato'])
if selected.source_record_id.duplicated().any(): raise ValueError('current selected IDs not unique')
sby=selected.set_index('source_record_id',drop=False)
points=pd.read_parquet(POINTS,columns=['target_source_record_id','target_year','latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_admission_status','admission_rule','coordinate_measurement_date_unknown','direct_historical_coordinate_measurement','boundary_comparability_asserted','population_scope_comparability_asserted'])
if points.target_source_record_id.duplicated().any(): raise ValueError('accepted points duplicate endpoint')
pby=points.set_index('target_source_record_id',drop=False)
graph_nodes=set(base.from_source_record_id.astype(str))|set(base.to_source_record_id.astype(str))
fromids=prof.from_source_record_id.astype(str); toids=prof.to_source_record_id.astype(str)
if fromids.duplicated().any() or toids.duplicated().any() or len(set(fromids)&set(toids)): raise ValueError('alias endpoints are not one-to-one')
endpoints=set(fromids)|set(toids)
if endpoints & graph_nodes: raise ValueError('current graph endpoint collision/competition found')
rows_checks=[]
for r in oldchecks.to_dict('records'):
 sid=str(r['source_record_id'])
 if sid not in endpoints: continue
 rr=prof[(prof.from_source_record_id.astype(str)==sid)|(prof.to_source_record_id.astype(str)==sid)]
 if len(rr)!=1: raise ValueError(f'endpoint does not map one-to-one to reviewed pair: {sid}')
 pr=rr.iloc[0]; s=sby.loc[sid]
 if int(s.census_year)!=int(r['census_year']): raise ValueError('current selected endpoint year changed')
 for nm in ['name_norm','type_norm','region_norm']:
  if str(getattr(s,nm))!=str(r[nm]): raise ValueError(f'current endpoint normalized {nm} changed: {sid}')
 if int(s.population)!=int(r['population']): raise ValueError(f'current selected population changed: {sid}')
 if sid not in pby.index: raise ValueError(f'candidate endpoint lacks current accepted point: {sid}')
 point=pby.loc[sid]
 if str(point.point_origin_kind)!='geokladr_2011_raw_dbf_coordinate' or str(point.point_origin_sha256)!=str(pr.point_origin_sha256) or str(point.point_origin_locator)!=str(pr.point_origin_locator):
  raise ValueError(f'accepted current point does not carry exact reviewed Geo object: {sid}')
 r.update({'new_stage_pair_edge_id':str(pr.edge_id),'region_alias_rule_id':'shared_named_point_explicit_region_alias_v1',
  'region_alias_raw_literal':str(pr.raw_2010_region_literal),'region_alias_canonical_norm':str(pr.allowed_region_norm),
  'region_alias_scope_source_file':str(pr.source_2010_file),'region_alias_scope_sheet':str(pr.source_2010_sheet),
  'region_alias_application_status':'candidate_only_profile_interpretation_for_independent_review',
  'raw_region_value_preserved':True,'current_selected_population':int(s.population),'current_selected_name_norm':str(s.name_norm),
  'current_selected_type_norm':str(s.type_norm),'current_selected_region_norm':str(s.region_norm),
  'current_accepted_point_present':True,'current_accepted_point_origin_kind':str(point.point_origin_kind),
  'current_accepted_point_origin_sha256':str(point.point_origin_sha256),'current_accepted_point_origin_locator':str(point.point_origin_locator),
  'current_accepted_point_status':str(point.coordinate_admission_status),
  'identity_admission_allowed':False,'coordinate_admission_allowed':False,'population_admission_allowed':False})
 rows_checks.append(r)
source_checks=pd.DataFrame(rows_checks)
if len(source_checks)!=2278 or source_checks.source_record_id.duplicated().any(): raise ValueError(f'source checks incomplete/duplicate: {len(source_checks)}')
# Reverify exact current singleton signature/year for both endpoints.
sig_counts=selected.groupby(['census_year','name_norm','type_norm','region_norm'],dropna=False).source_record_id.nunique()
for rr in prof.itertuples(index=False):
 for sid,year in [(str(rr.from_source_record_id),2002),(str(rr.to_source_record_id),2010)]:
  s=sby.loc[sid]
  if int(s.census_year)!=year or int(sig_counts.loc[(year,s.name_norm,s.type_norm,s.region_norm)])!=1: raise ValueError(f'current year-signature not singleton: {sid}')
# Current accepted source-point inventory (not a point delta): two carriers per pair, both already accepted.
carrier_counts={}
for year,ids in [(2002,fromids),(2010,toids)]:
 q=points[points.target_source_record_id.astype(str).isin(set(ids))]
 if len(q)!=1139 or not q.target_year.eq(year).all(): raise ValueError(f'accepted point carrier count/year mismatch for {year}')
 carrier_counts[str(year)]={'accepted_direct_geo_point_uses':len(q),'distinct_population':int(selected[selected.source_record_id.astype(str).isin(set(ids))].population.sum()),'point_origin_kind_counts':q.point_origin_kind.value_counts().to_dict(),'incremental_point_uses_created':0}
# New candidate edge table preserves original evidence, but explicitly records the bounded interpretation.
edges=[]
for row in orig.to_dict('records'):
 pr=prof.loc[str(row['edge_id'])]
 row.update({'candidate_rule':'shared_named_geo_object_identity_explicit_2010_region_alias_v1',
  'candidate_status':'candidate_pending_independent_application_review','decision_status':'candidate_pending_independent_application_review',
  'admission_status':'not_admitted','graph_add_status':False,'candidate_only':True,
  'source_identity_witness':'Two selected census rows share one accepted direct point from the exact same unique nondeleted typed Geo2011 raw object. The exact raw 2010 region literal is retained and interpreted only through its pinned source-file/sheet alias profile; 2009 classifier and raw Geo2011 region corroborate the normalized ADM1. No census-boundary/population comparability.',
  'from_name':str(pr.name_norm_2002),'to_name':str(pr.name_norm_2010),'from_region':str(pr.region_norm_2002),'to_region':str(pr.region_norm_2010),
  'from_region_norm':str(pr.region_norm_2002),'to_region_norm':str(pr.region_norm_2010),
  'pop_from':int(pr.population_2002),'pop_to':int(pr.population_2010),
  'population_comparability_asserted':False,'boundary_comparability_asserted':False,'no_coordinate_measurement_date_claim':True,'provider_id_binding_claimed':False,
  'region_alias_raw_literal':str(pr.raw_2010_region_literal),'region_alias_canonical_norm':str(pr.allowed_region_norm),
  'region_alias_scope_source_file':str(pr.source_2010_file),'region_alias_scope_sheet':str(pr.source_2010_sheet),
  'region_alias_scope_rule_id':'shared_named_point_explicit_region_alias_v1'})
 edges.append(row)
edge_df=pd.DataFrame(edges)
edge_df['decision_id']=edge_df.edge_id
edge_df['decision_status']='pending_independent_application_review';edge_df['candidate_status']='candidate_pending_independent_application_review'
edge_df['decision_rule']='shared_named_geo_object_identity_explicit_2010_region_alias_v1';edge_df['reviewer']='pending_independent_application_review';edge_df['reviewed_at']=None
edge_df['selection_projection_status']='active_endpoints_selected';edge_df['graph_add_status']='pending_independent_application_review';edge_df['coordinate_admitted']=False;edge_df['population_quality_changed']=False;edge_df['boundary_comparability_asserted']=False
edge_df['evidence_uri']=str(PROFILE/'ordinary_region_alias_profile_pairs.parquet');edge_df['evidence_sha256']=sha(PROFILE/'ordinary_region_alias_profile_pairs.parquet')
if edge_df.decision_id.duplicated().any() or len(edge_df)!=1139: raise ValueError('new edge IDs duplicated or count changed')
staged=pd.concat([base,edge_df],ignore_index=True,sort=False)
if len(staged)!=177707 or not staged.iloc[:len(base)][base.columns].reset_index(drop=True).equals(base.reset_index(drop=True)): raise ValueError('current graph base changed or staged row count wrong')
if not staged.iloc[len(base):].decision_status.eq('pending_independent_application_review').all(): raise ValueError('new edges must all be pending')
# Preserve the 60 non-alias/other source holds separately.
allprofile=pd.read_parquet(PROFILE/'all_retained_hold_pairs.parquet')
retained=allprofile[~allprofile.ordinary_alias_candidate].copy()
if len(retained)!=60: raise ValueError(f'expected 60 retained non-alias holds, got {len(retained)}')
app=[]
for r in prof.itertuples(index=False):
 app.append({'edge_id':str(r.edge_id),'from_source_record_id':str(r.from_source_record_id),'to_source_record_id':str(r.to_source_record_id),
  'candidate_rule':'shared_named_geo_object_identity_explicit_2010_region_alias_v1','status':'candidate_pending_independent_application_review','hold_reasons_json':'[]',
  'source_object_sha_locator_gate':'passed exact file hash, raw DBF record/byte locator, and accepted point-origin equality',
  'source_object_classifier_code_name_type_gate':'passed exact classifier code/name/type and unique raw Geo name/type/region key',
  'source_region_name_type_gate':'passed normalized endpoint name/type/region with explicit source-file/sheet-specific raw 2010 region alias',
  'region_alias_rule_id':'shared_named_point_explicit_region_alias_v1','region_alias_raw_literal':str(r.raw_2010_region_literal),'region_alias_canonical_norm':str(r.allowed_region_norm),
  'region_alias_scope_source_file':str(r.source_2010_file),'region_alias_scope_sheet':str(r.source_2010_sheet),
  'selected_signature_year_singleton':True,'point_origin_coordinates_exactly_match_raw_geo':True,'accepted_graph_endpoint_gate':'outside current accepted graph; verified unique',
  'graph_component_competitor_gate':'passed frozen signature-wide scan and current endpoint collision check','event_role_native_code_gate':'passed frozen event scan; no native event role on candidate endpoints',
  'known_identity_point_conflict_gate':'passed frozen candidate conflict scan','raw_2010_source_row_gate':'exact cached raw label and population; only raw-region label interpreted via this explicit source profile',
  'raw_2010_region_literal_preserved':str(r.raw_2010_region_literal),'raw_geo_region_canonical':str(r.raw_geo_region),
  'population_comparability_asserted':False,'coordinate_admission':False,'boundary_comparability_asserted':False,'admission_allowed':False})
apps=pd.DataFrame(app)
if len(apps)!=1139 or apps.status.nunique()!=1: raise ValueError('application checks status/count wrong')
# Current point-use count is context, not proposed coordinate change.
base_hashes={'receipt_sha256':sha(PROFILE/'summary.json'),'profile_pairs_sha256':sha(PROFILE/'ordinary_region_alias_profile_pairs.parquet'),'current_graph_sha256':sha(BASE_GRAPH),'current_selected_sha256':sha(SELECTED),'current_points_sha256':sha(POINTS)}
apps.to_parquet(OUT/'application_checks.parquet',index=False);source_checks.to_parquet(OUT/'source_row_checks.parquet',index=False);staged.to_parquet(OUT/'staged_identity_edges.parquet',index=False);retained.to_parquet(OUT/'retained_hold_pairs.parquet',index=False)
for i,p in enumerate(outs:= [OUT/'application_checks.parquet',OUT/'source_row_checks.parquet',OUT/'staged_identity_edges.parquet',OUT/'retained_hold_pairs.parquet']): pass
# Direct single-year totals are context only and do not change selected populations.
receipt={'artifact':'shared_named_point_region_alias_stage_v1','status':'candidate_identity_edges_only_no_admission',
 'candidate_rule':'shared_named_geo_object_identity_explicit_2010_region_alias_v1',
 'scope':{'staged_new_pairs':1139,'retained_other_source_row_holds':60,'base_graph_edges_preserved':len(base),'total_staged_graph_edges':len(staged)},
 'alias_profile_counts':{str(k):int(v) for k,v in prof.raw_2010_region_literal.value_counts().items()},
 'population_context_by_year':{'2002':int(prof.population_2002.sum()),'2010':int(prof.population_2010.sum())},
 'current_accepted_point_carriers_by_year':carrier_counts,
 'point_gain_from_identity_staging':{'new_point_uses':0,'reason':'All historical pair endpoints already have accepted direct GeoKLADR point uses; this stage changes identity candidates only.'},
 'three_year_chain_context':{'accepted_3year_chains_added':0,'current_2021_signature_counterparts':1138,'current_signature_points':921,'current_points_sharing_exact_geo_object':0},
 'checks':{'exact_1139_profile_ids':True,'current_selected_ids_and_population_unchanged':True,'current_name_type_region_unchanged':True,
 'year_signature_unique':True,'both_historical_endpoints_have_accepted_direct_point':True,'current_graph_no_endpoint_competitors':True,
 'staged_base_graph_byte_values_preserved':True,'all_new_edges_pending':True,'all_pop_boundary_point_admissions_false':True,
 'all_60_nonalias_event_family_population_holds_retained':True},
 'inputs':{},'outputs':{},'runtime_seconds':round(time.perf_counter()-T,3)}
inps=[PROFILE/'summary.json',PROFILE/'label_correction_addendum.json',PROFILE/'ordinary_region_alias_profile_pairs.parquet',PROFILE/'explicit_alias_profile.csv',PROFILE/'all_retained_hold_pairs.parquet',PREV/'receipt.json',PREV/'candidate_identity_edges.parquet',PREV/'source_row_checks.parquet',PREV/'application_checks.parquet',BASE_GRAPH,SELECTED,POINTS,C/'accepted_shared_named_object_identity_delta_v1/acceptance_receipt.json',C/'accepted_direct_historical_point_2021_delta_v1/acceptance_receipt.json',Path('/workspace/settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json')]
receipt['inputs']={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in inps}
receipt['outputs']={p.name:{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in outs}
receipt['application_checks_sha256']=sha(OUT/'application_checks.parquet');receipt['source_row_checks_sha256']=sha(OUT/'source_row_checks.parquet');receipt['staged_identity_edges_sha256']=sha(OUT/'staged_identity_edges.parquet')
receipt['builder_sha256']=sha(Path(__file__))
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,default=str)+'\n')
(OUT/'review.md').write_text(f"""# Explicit six-profile region alias identity candidates

Candidate-only stage. It appends {len(edge_df)} pending 2002–2010 same-place pairs to the {len(base)}-edge current R4 graph without changing any baseline edge. The 60 other source-row holds remain in retained_hold_pairs.parquet. The source-specific six-alias profile preserves every raw region literal and applies only to its reviewed file/sheet scope.

Current endpoint, uniqueness, no-competitor, raw census-row, exact Geo object, classifier, and event/conflict gates are pinned in the ledgers. Existing accepted historical points are inventoried by target ID and origin kind; no new point use is created. No population, boundary, measurement, provider-ID, or FIAS claim is made. This is not an identity admission.
""")
print(json.dumps({'status':receipt['status'],'pending_pairs':len(edge_df),'retained_holds':len(retained),'graph_edges':len(staged),'pop2002':int(prof.population_2002.sum()),'pop2010':int(prof.population_2010.sum()),'point_carriers':carrier_counts,'runtime':receipt['runtime_seconds'],'out':str(OUT)},ensure_ascii=False,indent=2))
