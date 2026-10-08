"""Explicit all-regional native2010 literal-name rivals, without graph or class filtering."""
from pathlib import Path
import sys,collections
import pandas as pd,duckdb
O=Path(__file__).parent;sys.path.insert(0,str(O));from scan import nm,cn
f=pd.read_csv(O/'positive_literal_native_county_ownpoint_candidates.csv.gz',keep_default_na=False)
p='/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet';c=duckdb.connect(config={'threads':1});a=c.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,population,population_value_quality,source_file,source_sha256,source_locator,source_row,source_sheet,source_name_raw from read_parquet(?) where census_year=2010',[p]).fetchdf();c.close();idx=collections.defaultdict(list)
for z in a.to_dict('records'):idx[(z['region_norm'],nm(z['settlement_name']))].append(z)
out=[]
for z in f.to_dict('records'):
 for q in idx[(z['region'],nm(z['name']))]:out.append({'target2010_source_record_id':z['native2010_source_record_id'],**q,'selected_own_target':q['source_record_id']==z['native2010_source_record_id'],'county_key':cn(q['district_raw'])})
pd.DataFrame(out).to_csv(O/'all_2010_regional_name_type_rivals.csv.gz',index=False,compression={'method':'gzip','mtime':0,'compresslevel':9});print(len(out))
