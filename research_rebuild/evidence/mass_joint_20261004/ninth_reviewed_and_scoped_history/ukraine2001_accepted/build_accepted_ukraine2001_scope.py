#!/usr/bin/env python3
"""Create a small accepted, source-preserving Ukraine 2001 scoped layer from frozen review artifacts."""
import csv,json,hashlib
from pathlib import Path
import duckdb
BASE=Path('/workspace/settlements-work/continuation_20261004')
REV=BASE/'independent_review/ukraine2001_to_2014_temporal_rule_independent_review'
CAND=BASE/'independent_review/ukraine2001_to_2014_temporal_rule_candidate'
STAGED=BASE/'independent_review/ukraine2001_crimea_primary_staged_v2'
NINTH=BASE/'accepted_mass_ninth_reviewed_legacy202'
CORE=BASE/'root/ninth_point35_long_rebuild/base_retry/source_preserving_core.parquet'
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
WORKBOOK=Path('/workspace/settlements-work/continuation_20261004/federal_and_history/crimea_2001_source_claim_review_20261004/official_tls_source/extracted/5.xls')
PREFACE=Path('/workspace/settlements-work/continuation_20261004/federal_and_history/ukraine_2001_official_archive_inspection/doc_text/Передмова 1.txt')
OUT=BASE/'independent_review/ukraine2001_to_2014_accepted_scope_layer'
if OUT.exists() and (OUT/'receipt.json').exists(): raise RuntimeError(f"Refusing to mutate sealed accepted packet: {OUT}")
OUT.mkdir(parents=True,exist_ok=True)

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def readcsv(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def writecsv(name,rows,fields=None):
 p=OUT/name
 with open(p,'w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=(fields or list(rows[0])));w.writeheader();w.writerows(rows)
 return p
# Pin the independently reviewed candidate rows, accepted earlier source assertions and current-carrier/point sources.
review=readcsv(REV/'independently_eligible_edge_recommendations.csv')
assert len(review)==27 and all(r['independent_verdict'].startswith('eligible') for r in review)
staged=readcsv(STAGED/'official_2001_source_observations.csv')
assert len(staged)==27
staged_by={x['source_record_id']:x for x in staged}
mappings=readcsv(STAGED/'existing_2014_to_2021_mappings.csv')
map_by={x['from_source_record_id']:x for x in mappings}
point_ctx=readcsv(STAGED/'current_2021_point_context_uses.csv')
point_by={x['target_source_record_id']:x for x in point_ctx}
# The source-preserving full 35/1009 core includes actual entity carriers. Check all exact current ids and no ninth graph join.
con=duckdb.connect(':memory:');con.execute("SET memory_limit='2GB'");con.execute('SET threads=1')
ids=sorted({r['current_source_record_id_2021'] for r in review}); sqlids=','.join("'"+x.replace("'","''")+"'" for x in ids)
core_rows=con.execute(f"select source_record_id,entity_id,observation_year,association_status,spatial_identity_status,source_name_raw,settlement_name,settlement_type,region_raw,population_value,population_scope,source_native_id from read_parquet('{CORE}') where source_record_id in ({sqlids})").fetchall()
assert len(core_rows)==27 and len({r[0] for r in core_rows})==27 and len({r[1] for r in core_rows})==27
core_by={r[0]:r for r in core_rows}
assert all(core_by[i][2]==2021 and core_by[i][1] for i in ids)
point_rows=con.execute(f"select target_source_record_id,latitude,longitude,coordinate_provider,coordinate_provider_id,coordinate_admission_status,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind,coordinate_measurement_date_unknown,boundary_comparability_asserted,source_oktmo_raw from read_parquet('{NINTH/'accepted_point_uses.parquet'}') where target_source_record_id in ({sqlids})").fetchall()
assert len(point_rows)==27 and len({r[0] for r in point_rows})==27
points_by={r[0]:r for r in point_rows}
# Verify the 27 current carriers are unchanged and have no edge to 2002/2010 in ninth graph.
graph_touch=con.execute(f"select count(*) from read_parquet('{NINTH/'accepted_identity_edges.parquet'}') where from_source_record_id in ({sqlids}) or to_source_record_id in ({sqlids})").fetchone()[0]
assert graph_touch==0,graph_touch
cross=con.execute(f"select count(*) from read_parquet('{NINTH/'accepted_identity_edges.parquet'}') where (from_source_record_id in ({sqlids}) or to_source_record_id in ({sqlids})) and (from_year in ('2002','2010') or to_year in ('2002','2010'))").fetchone()[0]
assert cross==0,cross
# Map 2001 observation population/date/source and carrier entity, retaining the distinct WD secondary corroborating statement.
obs=[]; edges=[]; pointuses=[]; pathlinks=[]; secondary=[]
for i,r in enumerate(review,1):
 sid01=r['source_record_id_2001'];sid14=r['source_record_id_2014'];sid21=r['current_source_record_id_2021']
 s=staged_by[sid01];m=map_by[sid14];pc=point_by[sid21];cr=core_by[sid21];pt=points_by[sid21]
 assert s['population_value']==str(int(float(r['2001_present_population_replayed'])))
 assert s['source_type']==('city' if r['2001_type_replayed']=='city' else 'urban_type_settlement')
 assert m['to_source_record_id']==sid21 and m['baseline_historical_identity_admitted']=='True'
 assert abs(float(pt[1])-float(r['current_point_latitude']))<1e-8 and abs(float(pt[2])-float(r['current_point_longitude']))<1e-8
 assert pt[5].startswith('reviewed') and pt[10] in ('True','true',True)
 entity=cr[1]
 eid=f'ukraine2001-primary:{sid01}'
 obs.append({'observation_id':eid,'record_type':'historical_source_observation','record_scope':'accepted_official_primary_observation_scoped_physical_identity','source_record_id':sid01,'source_publication_row_id':sid01,'historical_source_candidate_key':f'{sid01} -> {sid14} -> {sid21}','entity_id':entity,'associated_census_entity_id':entity,'association_status':'accepted_scoped_same_physical_place_via_official_2014_row_and_existing_2014_to_2021_link','spatial_identity_status':'accepted_scoped_same_physical_place; retrospective current point context only','identity_admission_status':'accepted_scoped_2001_to_2014_physical_continuity','settlement_name':s['settlement_name'],'source_name_raw':s['source_name_raw'],'source_type':s['source_type'],'source_admin_parent_raw':s['source_admin_parent_raw'],'source_grouping_raw':s['source_grouping_raw'],'observation_year':2001,'reference_date':'2001-12-05','reference_date_source':'official Ukraine 2001 census preface: enumeration at midnight of 4/5 December 2001','reference_date_basis':'official_census_reference_date','observation_date_precision':'day_source_preface','actual_census_date_claimed':True,'population_measure':'present_population','population_unit':'persons','population_value':int(s['population_value']),'population_raw':s['population_raw'],'population_value_quality':'Ukraine_2001_official_Table5_row_replayed_present_population','population_quality_limitation':'boundaries and population scopes for 2001/2014/2021 are not asserted comparable','population_assertion_admitted':True,'population_to_current_entity_binding_admitted':True,'population_boundary_comparability_asserted':False,'population_scope':'individual urban settlement row as published in Ukraine Table 5; city or urban-type settlement as printed','source_sheet':s['source_sheet'],'source_row':s['source_row'],'source_row_label_literal':s['source_row_label_literal'],'source_file':s['source_file'],'source_sha256':s['source_sha256'],'source_locator':f"Table 5 sheet {s['source_sheet']} row {s['source_row']}; present-population column for 2001",'source_has_native_locality_code':False,'native_2001_OKTMO_raw':'','native_2001_code_binding_asserted':False,'source_secondary_WD_P1082_statement_guid':s['P1082_statement_guid'],'source_secondary_WD_P1082_raw':s['population_source_claim_P1082_raw'],'source_secondary_WD_P1082_date':s['P1082_literal_date'],'source_secondary_WD_P1082_precision':s['P1082_date_precision'],'source_secondary_WD_P1082_sha256':s['P1082_statement_sha256'],'source_secondary_WD_claim_is_alternative_not_replacement':True,'source_secondary_WD_population_value_overwrote_primary':False,'intervening_2014_source_record_id':sid14,'current_2021_source_record_id':sid21,'current_2021_entity_id':entity,'current_QID_context_only':s['current_QID_context_only'],'current_QID_used_as_2001_identity_key':False,'current_native_2021_OKTMO_literal':cr[11],'current_point_latitude':float(pt[1]),'current_point_longitude':float(pt[2]),'current_point_provider':pt[3],'current_point_provider_id':pt[4],'current_point_origin_file':pt[6],'current_point_origin_sha256':pt[7],'current_point_origin_locator':pt[8],'current_point_origin_kind':pt[9],'current_point_is_historical_measurement':False,'historical_coordinates_asserted':False,'current_point_measurement_date_unknown':True,'boundary_comparability_asserted':False,'identity_review_receipt_sha256':'dba3dac13b73bee3b8de3389eabdc51d32fea67d9bade69dbe57791f25f3ac89','current_carrier_core_association_status':cr[3],'current_carrier_source_native_id':cr[11]})
 edgeid=f'ukraine2001-2014-same-place:{i:02d}'
 edges.append({'edge_id':edgeid,'relation':'same_place','from_source_record_id':sid01,'from_year':2001,'to_source_record_id':sid14,'to_year':2014,'decision_status':'accepted_root_approved_independent_review','decision_class':'scoped_official_source_physical_place_continuity','decision_rule':'official 2001 individual urban source row + exact official 2014 city/PGT row + type-specific uniqueness in 2001/2014/selected 2021 + existing accepted scoped 2014-to-2021 association','review_id':'ukraine2001_to_2014_temporal_rule_independent_review','review_sha256':'dba3dac13b73bee3b8de3389eabdc51d32fea67d9bade69dbe57791f25f3ac89','identity_witness':f"2001 source literal {s['source_name_raw']} / {s['source_type']}; 2014 {r['2014_literal_row']} / {r['2014_type_replayed']}; three-frame observed-type uniqueness; baseline 2014->2021 link {m['mapping_id']}",'population_scope_interpretation':'physical-place continuity only; published count measures/scopes remain as source states','population_quality_changed':False,'boundary_comparability_asserted':False,'population_boundary_comparability_asserted':False,'native_code_binding_asserted':False,'current_QID_used_as_historical_key':False,'legal_effective_date':'','historical_coordinate_asserted':False,'strict_Russian_2002_2010_2021_chain':False})
 pointuses.append({'point_use_id':f'ukraine2001-retrospective-point:{i:02d}','target_source_record_id':sid01,'target_year':2001,'entity_id':entity,'latitude':float(pt[1]),'longitude':float(pt[2]),'point_use_status':'accepted_retrospective_current_representative_point_context','point_role':'current representative coordinate retrospectively associated with same physical place through 2001→2014→2021 reviewed identity path','coordinate_source':pt[3],'coordinate_provider':pt[3],'coordinate_provider_id':pt[4],'point_origin_file':pt[6],'point_origin_sha256':pt[7],'point_origin_locator':pt[8],'point_origin_kind':pt[9],'coordinate_measurement_date_unknown':True,'historical_2001_coordinate_measurement':False,'coordinate_admission_basis':'root-approved scoped physical identity path; current point was independently accepted for the 2021 source object','supporting_identity_edge_id':edgeid,'supporting_2014_to_2021_mapping_id':m['mapping_id'],'boundary_comparability_asserted':False,'population_boundary_comparability_asserted':False,'point_coordinates_claimed_as_census_date_measurement':False,'point_use_admission_changed_current_coordinate_record':False})
 pathlinks.append({'path_id':f'ukraine2001-2014-2021-scoped-path:{i:02d}','source_record_id_2001':sid01,'edge_2001_to_2014_id':edgeid,'source_record_id_2014':sid14,'existing_2014_to_2021_mapping_id':m['mapping_id'],'mapping_status':m['mapping_status'],'baseline_2014_observation_id':m['baseline_2014_observation_id'],'baseline_entity_id':m['baseline_entity_id'],'current_source_record_id_2021':sid21,'current_entity_id':entity,'current_qid_context_only':s['current_QID_context_only'],'recorded_path_relation':'2001 same_place 2014; existing scoped same_place 2014 to 2021','identity_admitted_for_scoped_available_year_path':True,'strict_Russian_2002_2010_2021_chain':False,'population_boundary_comparability_asserted':False})
 secondary.append({'source_record_id_2001':sid01,'wd_current_subject_qid':s['current_QID_context_only'],'statement_guid':s['P1082_statement_guid'],'population_raw':s['population_source_claim_P1082_raw'],'observed_year':2001,'date_precision':s['P1082_date_precision'],'source_statement_sha256':s['P1082_statement_sha256'],'staged_secondary_source_layer':str(STAGED/'official_2001_source_observations.parquet'),'status':'preserved_existing_WD_secondary_claim_alternative; primary Table5 row is accepted source value; no overwrite'})
# Keep accepted layer compact and immutable with CSV and typed Parquet sidecars.
writecsv('accepted_2001_primary_observations.csv',obs)
writecsv('accepted_scoped_identity_edges.csv',edges)
writecsv('accepted_retrospective_point_uses.csv',pointuses)
writecsv('accepted_available_year_paths.csv',pathlinks)
writecsv('preserved_wikidata_secondary_alternatives.csv',secondary)
# Typed Parquet copies from CSV via DuckDB, retaining structured date/year and amounts.
for name in ['accepted_2001_primary_observations','accepted_scoped_identity_edges','accepted_retrospective_point_uses','accepted_available_year_paths','preserved_wikidata_secondary_alternatives']:
 csvp=OUT/f'{name}.csv';par=OUT/f'{name}.parquet'
 con.execute(f"COPY (SELECT * FROM read_csv_auto('{csvp}', header=true, all_varchar=true)) TO '{par}' (FORMAT PARQUET, COMPRESSION ZSTD)")
# Inputs, totals, explicit ninth graph exclusion proof.
inputs=[REV/'independent_review_receipt.json',REV/'independently_eligible_edge_recommendations.csv',REV/'retrospective_current_point_use_recommendations.csv',STAGED/'application_receipt.json',STAGED/'official_2001_source_observations.parquet',STAGED/'existing_2014_to_2021_mappings.csv',STAGED/'current_2021_point_context_uses.csv',NINTH/'accepted_identity_edges.parquet',NINTH/'accepted_point_uses.parquet',NINTH/'receipt.json',CORE,SELECTED,WORKBOOK,PREFACE]
receipt={'status':'accepted_scoped_2001_primary_available_year_layer_root_approved','scope':'Accepted primary Table 5 present-population observations for 27 Crimea/Sevastopol urban place rows, linked to source-preserving current 2021 carrier entities through an approved scoped 2001→2014 edge and previously accepted 2014→2021 association. Current accepted points are used only as retrospective physical-place context. This layer does not join Russian 2002/2010 coverage.','counts':{'accepted_primary_observations':len(obs),'accepted_2001_to_2014_identity_edges':len(edges),'accepted_retrospective_2001_point_uses':len(pointuses),'existing_2014_to_2021_links_referenced':len(pathlinks),'preserved_existing_WD_secondary_alternative_claims':len(secondary),'primary_present_population_total_2001':sum(x['population_value'] for x in obs),'distinct_2021_current_entities':len({x['entity_id'] for x in obs}),'current_entity_ids_unchanged_in_ninth_core':len(core_by),'ninth_graph_edges_touching_these_2021_ids':graph_touch,'ninth_graph_edges_touching_these_current_ids_and_2002_or_2010':cross,'boundary_or_population_comparability_assertions':0,'strict_Russian_2002_2010_2021_gains':0,'source_population_values_modified':False,'existing_WD_secondary_rows_modified':False,'canonical_graph_or_point_ledgers_modified':False},'semantic_contract':{'date':'2001-12-05 exact day from official preface enumeration at midnight 4/5 Dec 2001; P1082 year precision remains year only','population_measure':'present_population from source Table 5, individual city or urban-type settlement row; permanent-population Table 15 is not used','physical_identity':'scoped historical physical place; exact 2001→2014 edge joins via current accepted 2014→2021 association; current entity ID is the current 2021 source carrier, not a 2001 code/QID','coordinates':'modern current accepted point only, retrospectively associated physical-place context; not measured in 2001; date unknown; no boundary or population equivalence asserted','secondary_Wikidata':'existing 27 P1082 secondary claims remain preserved as alternatives; accepted primary observations do not overwrite or inherit their source confidence','Russian_census':'No Russian 2002/2010 census row is created. Strict 3-date coverage remains false.'},'root_acceptance_basis':'Root acceptance message of independent review receipt dba3dac13b73bee3b8de3389eabdc51d32fea67d9bade69dbe57791f25f3ac89; accepted layer created only after that review.', 'inputs':{str(p):sha(p) for p in inputs},'outputs':{}}
for p in sorted(OUT.iterdir()):
 if p.name=='receipt.json':continue
 if p.is_file():
  if p.suffix=='.csv':
   with open(p,encoding='utf-8',newline='') as f:n=sum(1 for _ in csv.DictReader(f))
  else:n=None
  receipt['outputs'][p.name]={'sha256':sha(p),'rows':n}
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'counts':receipt['counts'],'receipt_sha256':sha(OUT/'receipt.json'),'output_dir':str(OUT)},ensure_ascii=False,indent=2))
