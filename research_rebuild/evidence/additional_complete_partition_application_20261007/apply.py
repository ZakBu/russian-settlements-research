"""One authorized complete primary publisher partition; no ordinary part unions."""
import sys,json,re,gzip,collections
from pathlib import Path
import pandas as pd,pyarrow.parquet as pq,xlrd
ROOT=Path('/workspace/russian-settlements-research');OUT=Path(__file__).parent;E=ROOT/'research_rebuild/evidence';RAW=Path('/workspace/settlements-raw');WORK=Path('/workspace/settlements-work/additional_complete_partition_application_20261007');RES=E/'additional_complete_partition_reserve_20261007'
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,PARTITION_MEMBERS
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
PART=re.compile(r'\s*\(\s*часть\s*(\d+)\s*\)\s*$',re.I)
s=load(stage=21);source_meta=pq.read_table(s.inputs[0],columns=['source_record_id','source_sheet','source_row','source_name_raw','municipality_raw']).to_pandas();o=s.obs.merge(source_meta,on='source_record_id');o['base']=o.settlement_name.map(lambda n:normalize(PART.sub('',str(n))))
g=o[o.base.eq('головчино')&o.region_norm.eq('белгородская')&o.settlement_type.eq('село')&o.is_additive_settlement_record.fillna(False)].copy()
assert set(g.census_year)=={2002,2010,2021}
g02=g[g.census_year.eq(2002)];g10=g[g.census_year.eq(2010)];g21=g[g.census_year.eq(2021)];assert len(g02)==2 and len(g10)==len(g21)==1
assert sorted(int(PART.search(n).group(1)) for n in g02.settlement_name)==[1,2]
assert all(county_key(x)=='грайворонский' for x in g02.district_raw)
cur=g21.iloc[0];assert county_key(cur.district_raw)=='грайворонский'
assert len(o[o.census_year.eq(2021)&o.base.eq('головчино')&o.region_norm.eq('белгородская')&o.settlement_type.eq('село')&o.district_raw.map(county_key).eq('грайворонский')])==1
assert int(g02.population.sum())==5288 and int(g10.population.sum())==4716 and int(g21.population.sum())==4621
# Complete primary roster and whole control were bounded-source checked, and all input bytes stay pinned.
checks=pd.read_csv(RES/'golovchino_bounded_primary_source_checks.csv',keep_default_na=False)
for path,digest in checks[['source_file','source_sha256']].drop_duplicates().itertuples(index=False,name=None):assert sha(Path(path))==digest
native=checks[checks.role.eq('native_2002_member')];assert set(native.source_record_id)==set(g02.source_record_id)
workbook=Path(native.iloc[0].source_file);book=xlrd.open_workbook(str(workbook));sh=book.sheet_by_name(native.iloc[0].sheet);found=[]
for i in range(sh.nrows):
 for cell in sh.row_values(i):
  if isinstance(cell,str) and PART.search(cell) and normalize(PART.sub('',cell)).endswith('головчино'):found.append(i+1);break
assert sorted(found)==sorted(int(n) for n in g02.source_row)
control=checks[checks.role.eq('primary2002_whole_control')].iloc[0];assert '5288.0' in control.raw_cells and 'Головчино' in control.raw_cells
entity_path=WORK/'golovchino_wikidata_own_entity.json';article_path=WORK/'golovchino_own_article.html.gz';entity=json.loads(entity_path.read_text())['entities']['Q2075571'];article=gzip.open(article_path,'rt').read()
assert entity['labels']['ru']['value']=='Головчино' and 'Грайворонском' in entity['descriptions']['ru']['value'] and 'Белгородской' in entity['descriptions']['ru']['value'];assert entity['sitelinks']['ruwiki']['title']=='Головчино (Белгородская область)'
assert any(x['mainsnak'].get('datavalue',{}).get('value',{}).get('id')=='Q532' for x in entity['claims']['P31'])
assert '"wgWikibaseItemId":"Q2075571"' in article and '"район":{"wt":"Грайворонский район"}' in article and '"регион":{"wt":"Белгородская область"}' in article
coordinates=[x for x in entity['claims']['P625'] if x['rank']!='deprecated'];assert len(coordinates)==1;claim=coordinates[0];value=claim['mainsnak']['datavalue']['value'];assert value['globe'].endswith('/Q2')
article_coords=json.loads(re.search(r'"wgCoordinates":(\{[^}]+\})',article).group(1));assert distance_km((value['latitude'],value['longitude']),(article_coords['lat'],article_coords['lon']))<.01
point=s.point_rows[cur.source_record_id];assert cur.source_record_id not in s.conflicting_point_targets;distance=distance_km((point['latitude'],point['longitude']),(value['latitude'],value['longitude']));assert distance<=5
place_id='complete_partition:golovchino_belgorod_primary2002_20261007';point_ledger=Path(point['point_ledger_path']);prior=set(pd.read_csv(PARTITION_MEMBERS).source_record_id)
event_members=E/'event_aware_path_union_20261005/accepted_event_path_selected_rows.csv'
if event_members.exists():prior.update(pd.read_csv(event_members,dtype=str).source_record_id)
series=[];members=[]
for year,gy in [(2002,g02),(2010,g10),(2021,g21)]:
 gy=gy.sort_values('source_record_id');ids=list(gy.source_record_id);orig=[]
 for r in gy.to_dict('records'):
  path=RAW/r['source_file'];orig.append({'source_record_id':r['source_record_id'],'source_file':str(path),'source_sha256':sha(path),'source_sheet':r['source_sheet'],'source_row':int(r['source_row']),'source_name_raw':r['source_name_raw']})
 series.append({'place_id':place_id,'place':'Головчино','region_norm':'белгородская','settlement_type':'село','year':year,'population':int(gy.population.sum()),'member_source_record_ids_json':json.dumps(ids,ensure_ascii=False),'member_populations_json':json.dumps([int(x) for x in gy.population]),'member_population_quality_json':json.dumps(list(gy.population_value_quality),ensure_ascii=False),'member_source_provenance_json':json.dumps(orig,ensure_ascii=False),'population_is_derived_sum':year==2002,'projection_status':'accepted_complete_publisher_partition' if year==2002 else 'selected_whole_locality_observation','latitude':point['latitude'],'longitude':point['longitude'],'point_ledger_path':str(point_ledger),'point_ledger_sha256':sha(point_ledger),'point_ledger_locator':'target_source_record_id='+cur.source_record_id,'point_scope':'whole locality; no individual part coordinate admitted','individual_part_coordinates_admitted':False,'direct_historical_coordinate_measurement':False,'retrospective_point_use_is_continuity_inference':year!=2021,'population_boundary_comparability_asserted':False,'modern_boundary_harmonized':False,'oktmo_native_current':cur.oktmo,'oktmo_current_year':2021,'oktmo_history_status':'not_reconstructed','physical_point_correctness_evidence':str(OUT/'accepted_whole_place_point_support.csv'),'external_provider_identifier_binding':'unassessed_preserved','primary_2002_whole_population':5288,'secondary_2002_population_alternative':5291,'secondary_primary_population_disagreement_preserved':True})
 for r in gy.itertuples():members.append({'place_id':place_id,'source_record_id':r.source_record_id,'year':year,'population':int(r.population),'coordinate_scope':'complete_whole_locality_projection' if year==2002 else 'whole_locality','ordinary_same_place_graph_mutated':False})
proof={'place_id':place_id,'target_source_record_id':cur.source_record_id,'physical_np_name':'Головчино','physical_np_type':'село','physical_region':'белгородская','physical_county':'грайворонский','coordinate_admission_status':'reviewed_case_accepted','latitude':point['latitude'],'longitude':point['longitude'],'coordinate_source_record_id':point.get('coordinate_source_record_id'),'point_origin_file':point.get('point_origin_file'),'point_origin_sha256':point.get('point_origin_sha256'),'point_origin_locator':point.get('point_origin_locator'),'point_origin_kind':point.get('point_origin_kind'),'own_article_file':str(article_path),'own_article_sha256':sha(article_path),'own_article_url':entity['sitelinks']['ruwiki']['url'],'own_article_revision':re.search(r'oldid[=/]([0-9]+)',article).group(1),'own_article_coordinates_dms':'50°32′11″ N 35°48′30″ E','own_entity_file':str(entity_path),'own_entity_sha256':sha(entity_path),'own_entity_qid':'Q2075571','own_p625_statement_id':claim['id'],'own_p625_latitude':value['latitude'],'own_p625_longitude':value['longitude'],'own_point_to_retained_geonames_km':distance,'point_correctness_rule':'unique_native_current_physical_name_type_region_county_and_own_article_coordinate_within5km','external_provider_identifier_binding':'unassessed_preserved','external_provider_id_binding_asserted':False,'point_scope':'whole physical locality','individual_part_coordinates_admitted':False}
control_review=E/'numbered_partition_source_review_20261007/official_whole_row_candidates.csv'
control_context=pd.read_csv(control_review);control_context=control_context[control_context.base_name.eq('Головчино')&control_context.region.eq('белгородская')&control_context.official_population_candidate.eq(5288)]
assert len(control_context)==1 and 'Грайворонский' in control_context.iloc[0].nearest_context_raw and 'Белгородская область' in control_context.iloc[0].nearest_subject_raw
control_context['new_complete_selected_part_sum']=5288
control_context['new_sum_equals_actual_primary_whole']=True
control_context['prior_strict_parser_missed_whitespace_part2']=True
control_context.to_csv(OUT/'primary_whole_source_admin_context.csv',index=False)
pd.DataFrame(series).to_csv(OUT/'accepted_three_census_whole_place_series.csv',index=False);pd.DataFrame(members).to_csv(OUT/'accepted_exclusive_member_projection.csv',index=False);pd.DataFrame([proof]).to_csv(OUT/'accepted_whole_place_point_support.csv',index=False);checks.to_csv(OUT/'bounded_primary_source_proof.csv',index=False)
ids={r['source_record_id'] for r in members};assert len(ids)==len(members)==4
before=s.metrics(extra_covered_ids=prior);after=s.metrics(extra_covered_ids=prior|ids);net={y:after[y]['covered_population']-before[y]['covered_population'] for y in before}
new=[r for r in members if r['source_record_id'] not in prior and not (r['source_record_id'] in s.point_rows and s.years[s.uf.find(r['source_record_id'])]=={2002,2010,2021})];pd.DataFrame(new).to_csv(OUT/'unique_source_id_net_delta.csv',index=False)
inputs={str(p):sha(p) for p in s.inputs+[PARTITION_MEMBERS,event_members,RES/'golovchino_bounded_primary_source_checks.csv',entity_path,article_path,control_review]};receipt={'status':'applied_complete_primary_publisher_partition_with_own_physical_point_support','ordinary_baseline_stage':21,'places':1,'whole_series_rows':3,'exclusive_selected_member_rows':4,'new_unique_selected_member_rows':len(new),'new_ordinary_same_place_edges':0,'new_individual_part_point_uses':0,'before_ordinary_plus_prior_selected_member_union':before,'after_plus_new_complete_partition_union':after,'net_population_gain':net,'coordinate_agreement_km':distance,'provider_identifier_binding_unassessed_preserved':True,'source_population_values_modified':False,'secondary2002_5291_vs_primary5288_disagreement_preserved':True,'population_boundary_comparability_asserted':False,'member_coordinates_not_asserted':True,'inputs':inputs,'outputs':{p.name:sha(p) for p in OUT.glob('*.csv')}};(OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['places','new_unique_selected_member_rows','net_population_gain','coordinate_agreement_km']},ensure_ascii=False))
