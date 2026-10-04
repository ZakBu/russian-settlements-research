"""Apply finite reviewed territorial views; never alter atomic census observations."""
from pathlib import Path
import csv, hashlib, json, subprocess
import duckdb, xlrd

C=Path('/workspace/settlements-work/continuation_20261004')
O=C/'root/accepted_territorial_scope_layers_seventh'
CORE=C/'R4/final_long_preparation/seventh_canonical_long/source_preserving_core.parquet'
REF=C/'R4/final_long_preparation/seventh_canonical_long/federal_territory_reference_points.parquet'
M=C/'independent_review/moscow2002_parent_scope/territorial_view_override.json'
A=C/'independent_review/scoped_annual_federal9_candidates/federal_annual_territory_context_candidates.csv'

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def run():
 assert sha(M)=='6352f1a14be81d848bcde08ecf0b2599ee22bf5ab8a77babc8fa44f159c84b8d'
 assert sha(A)=='806a0586c4e2af51c2b6615c9cd2d9daef4488c5c5c8e2f492af054c4961020b'
 assert sha(CORE)=='101c133fee04289b628bbd1c9dec93e36b9591c9031dd6026b2d83756d157c53'
 assert sha(REF)=='3b366d9a513b0396e90813f03c4e3af1cd0b1caef92379a9ae95cae43451d6e3'
 assert not O.exists();m=json.loads(M.read_text())
 for spec in m['inputs'].values():assert sha(spec['path'])==spec['sha256']
 ws=xlrd.open_workbook(m['source_file']).sheet_by_name(m['source_sheet']);parent=ws.row_values(m['source_excel_row']-1)
 assert parent[1:4]==[m['population'],m['male'],m['female']]
 children=[ws.row_values(int(s.rsplit('row',1)[1])-1) for s in m['excluded_child_source_record_ids']]
 assert all(sum(r[j] for r in children)==parent[j] for j in [1,2,3])
 with A.open(newline='') as f:annual=list(csv.DictReader(f))
 assert len(annual)==9 and len({r['annual_observation_id'] for r in annual})==9
 pdf=Path(annual[0]['pdf_source_path']);assert sha(pdf)=='bac43b438869d7b11ca595acd121726833d2bf2e54004351db825cade4c29da7'
 text=subprocess.run(['pdftotext','-layout',str(pdf),'-'],check=True,capture_output=True,text=True).stdout
 assert 'за остальные годы – оценка на 1 января соответствующего года' in text
 assert 'Данные по городу федерального значения Москве приведены с учетом изменения его границы с 1 июля 2012 года' in text
 con=duckdb.connect(config={'threads':1,'memory_limit':'384MB'})
 refs=con.execute("select * from read_parquet(?) where census_year='2021'",[str(REF)]).fetchdf().to_dict('records');rb={r['city_name']:r for r in refs}
 source=con.execute("select observation_id,population_value,reference_date,entity_id from read_parquet(?) where record_type='annual_official'",[str(CORE)]).fetchall();sb={r[0]:r for r in source}
 edges=[]
 for r in annual:
  city=r['city_label'];ref=rb[city];actual=sb[r['annual_observation_id']]
  assert r['raw_pdf_cell_line'].strip() in text
  assert int(float(r['population_value_as_stored']))==int(r['raw_population_thousands'].replace(' ',''))*1000==actual[1]
  assert str(actual[2])==r['reference_date'] and actual[3]==r['annual_entity_id']
  assert r['current_2021_source_record_id']==ref['source_record_id']
  assert float(r['territory_reference_latitude'])==float(ref['latitude']) and float(r['territory_reference_longitude'])==float(ref['longitude'])
  assert ref['admission_status']=='reviewed_territory_reference_accepted' and ref['point_role']=='territory_reference'
  for k in ['physical_populated_place_claim','historical_coordinate_claim','population_value_or_unit_changed','boundary_comparability_2021_to_observation_year']:assert r[k]=='False'
  r['source_candidate_only_before_application']=r.pop('federal_territory_context_candidate_only');r['candidate_only']=False;r['decision_status']='accepted_checked_rule_territorial_reference_and_series_context';r['point_role']='territory_reference';r['coordinate_temporal_basis']='accepted modern city point reused as territorial representative; no measurement at annual observation date';r['atomic_same_place_edge']=False
  edges.append({'from_observation_id':r['current_2021_source_record_id'],'from_year':2021,'to_observation_id':r['annual_observation_id'],'to_year':int(r['observation_year']),'relation':'continuing_federal_city_territory_observation','point_role':'territory_reference','population_boundary_comparability_asserted':False,'atomic_same_place_edge':False,'decision_status':'accepted_checked_rule'})
 m['source_review_status']=m.pop('review_status');m['decision_status']='accepted_exclusive_territorial_view_override';m['additivity_rule']='replace all five listed children by the published parent only in territorial view';m['canonical_atomic_population_modified']=False
 O.mkdir()
 (O/'accepted_moscow2002_territorial_override.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 for name,rows in [('accepted_annual_federal9_territorial_contexts.csv',annual),('accepted_annual_federal9_territorial_edges.csv',edges)]:
  with (O/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 receipt={'status':'accepted_scoped_federal_territorial_views_and_annual_continuity','script_sha256':sha(Path(__file__)),'counts':{'territorial_parent_overrides':1,'annual_territorial_contexts':9,'annual_territorial_edges':9},'population_source_values_modified':False,'atomic_NP_graph_points_modified':False,'inputs':{str(p):sha(p) for p in [M,A,CORE,REF,pdf]},'checks':{'Moscow_parent_and_all_child_population_male_female_sums':'exact','annual_source_pdf_rows_dates_values_rounding':'exact','reference_points_actual_accepted_2021_carriers':'exact'},'outputs':{p.name:sha(p) for p in O.iterdir()}}
 (O/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt['counts']))

if __name__=='__main__':run()
