"""Bind source-bounded rounded city estimates to unique current named-city series."""
import csv,json,hashlib,importlib.util
from pathlib import Path
import duckdb,pyarrow as pa,pyarrow.parquet as pq
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('city',HERE/'bind_primary_city_block.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SOURCE=m.REPO/'research_rebuild/evidence/extended_population_sources_20261013/yearbook_annual_source_observations_recovered.csv'
DETAIL=m.REPO/'research_rebuild/evidence/extended_population_sources_20261013/yearbook_table49_source_rows_recovered.csv'
details={r['row_id']:r for r in csv.DictReader(DETAIL.open())}
c=duckdb.connect();n=c.execute('select * from read_parquet(?) where census_year=2021',[str(m.NATIVE)]).fetchdf();n=n[n.type_norm.isin(['город','г'])].copy();n['city_key']=n.name_norm.map(m.norm);rows=[];holds=[]
for r in csv.DictReader(SOURCE.open()):
 d=details[r['publication_row_id']];name=d['normalized_city_label'];cand=n[n.city_key.eq(m.norm(name))]
 qualifier=d['explicit_region_qualifier_key']
 if qualifier:
  target=m.norm(qualifier);cand=cand[cand.region_norm.map(m.norm).map(lambda v: v==target or target==v+'область' or target==v+'край' or target=='республика'+v)]
 if len(cand)!=1:
  holds.append({'source_record_id':r['source_record_id'],'label':name,'reason':'city_reference_not_unique','candidates':len(cand)});continue
 x=cand.iloc[0];rows.append({**r,'anchor_source_record_id':x.source_record_id,'root':x.root,'year':int(r['observation_year']),'population':int(r['population_value_people_rounded']),'population_basis':'official_annual_estimate_rounded_to_thousands','source_quality':'primary_official_rounded_estimate','association_status':'named_city_reference_series','source_scope_footnotes_preserved':True,'historical_physical_identity_asserted':False,'boundary_comparability':'UNKNOWN','reference_latitude':x.accepted_latitude,'reference_longitude':x.accepted_longitude,'coordinate_role':'current_reference_point_not_historical_measurement','reference_entity_scope':'federal_territory' if m.norm(x.region_norm) in {'москва','санктпетербург','севастополь'} else 'named_city'})
assert rows
out=m.OUT/'primary_city_annual_2022_2024.parquet';pq.write_table(pa.Table.from_pylist(rows),out,compression='zstd')
receipt={'source_sha256':m.sha(SOURCE),'detail_sha256':m.sha(DETAIL),'native_sha256':m.sha(m.NATIVE),'source_rows':516,'associated_rows':len(rows),'cities':len(set(r['anchor_source_record_id'] for r in rows)),'holds':holds,'population_precision':'1000_people_not_exact_census_counts','census_values_unchanged':True,'output_sha256':m.sha(out)}
(HERE/'annual_city_binding_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
