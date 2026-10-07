from pathlib import Path
import csv,json,hashlib
import duckdb
OUT=Path(__file__).resolve().parent
source=OUT.parent/'candidate_census_observations.csv'
rows=list(csv.DictReader(source.open()))
parts=[r for r in rows if r['candidate_group']=='Podolsk_Klimovsk_Lvovskiy']
SELECTED='/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
c=duckdb.connect()
points={r[0]:dict(zip(['latitude','longitude','coordinate_source','coordinate_quality','coordinate_admission'],r[1:])) for r in c.execute('SELECT source_record_id,latitude,longitude,coordinate_source,coordinate_quality,coordinate_admission FROM read_parquet(?)',[SELECTED]).fetchall() if r[0] in {x['source_record_id'] for x in parts}}
representative=points[next(r['source_record_id'] for r in parts if r['census_year']=='2021')]
assert len(parts)==7 and len({r['source_record_id'] for r in parts})==7
for y in ['2002','2010']:
 assert {r['settlement_name'] for r in parts if r['census_year']==y}=={'Подольск','Климовск','Львовский'}
assert [r['settlement_name'] for r in parts if r['census_year']=='2021']==['Подольск']
for r in parts:
 r['population_is_component_observation_only']='True'
 r['membership_status']='legal_named_whole_urban_constituent_of_2015_merger' if r['census_year']!='2021' else 'direct_published_successor_city_observation'
 r['identity_axis']='named_urban_merger_event_group_not_ordinary_same_place'
 r['boundary_comparability']='unknown_not_modern_boundary_harmonized'
 r['legal_basis']='103/2015-OZ article1;282-PG2015 single-settlement union;283-PG2015 rural NPs stay separate'
 r['same_year_source_record_id_exclusive']='True'
 r['group_total_computed']='False'
 r['historical_point_status']='own_native_point_unavailable_in_selected_source' if r['census_year']!='2021' else 'modern_parent_representative_point_from_2021_source'
 r['own_point_provenance_json']=json.dumps(points[r['source_record_id']],ensure_ascii=False)
 r['modern_group_representative_point_json']=json.dumps(representative,ensure_ascii=False)
 r['representative_point_role']='modern_parent_representative_only_not_historical_constituent_own_point'
 r['ordinary_same_place']='False'
with (OUT/'podolsk_named_merger_constituent_observations.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(parts[0]));w.writeheader();w.writerows(parts)
series=[]
for y in ['2002','2010','2021']:
 rr=[r for r in parts if r['census_year']==y]
 vals=[float(r['population']) for r in rr];assert all(v.is_integer() for v in vals)
 series.append({'group':'Podolsk_Klimovsk_Lvovskiy','census_year':y,'population':sum(int(v) for v in vals),'value_derivation':'sum_of_three_published_whole_urban_constituent_observations' if y!='2021' else 'direct_published_successor_city_value','constituent_count':len(rr),'source_record_ids_json':json.dumps([r['source_record_id'] for r in rr],ensure_ascii=False),'roster_scope':'complete_named_2015_urban_merger_roster','population_series_scope':'historical_event_group_not_modern_boundaries_harmonized_estimate','boundary_comparability':'unknown','identity_axis':'legal_merger_lineage_group_not_ordinary_same_place','candidate_only':True,'no_child_2021_observation_created':True,'point_axis':'modern_parent_representative_available_historical_own_points_not_attached','ordinary_same_place':False,'nested_members_json':json.dumps([{'source_record_id':r['source_record_id'],'name':r['settlement_name'],'population_raw':r['population'],'source_file':r['source_file'],'source_file_sha256':r['source_file_sha256'],'source_row_locator':r['source_row_locator'],'own_point':points[r['source_record_id']]} for r in rr],ensure_ascii=False),'modern_group_representative_point_json':json.dumps(representative,ensure_ascii=False),'representative_point_role':'modern_parent_representative_only_not_historical_constituent_own_point'})
with (OUT/'podolsk_named_merger_series.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(series[0]));w.writeheader();w.writerows(series)
print(json.dumps(series,ensure_ascii=False,indent=2))
