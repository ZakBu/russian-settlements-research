import pandas as pd,duckdb,json
from pathlib import Path
O=Path(__file__).parent;c=duckdb.connect()
h=c.execute("select * from read_parquet('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet') where name_key in ('сибирский','нагорный','подгорный')").fetchdf();print(h.columns.tolist());print(h.to_string(index=False));h.to_csv(O/'urban_type_historical_candidates.csv',index=False)
d=c.execute("select * from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet') where lower(settlement_name) in ('сибирский','нагорный','подгорный') and region_norm in ('алтайский','красноярский')").fetchdf();d.to_csv(O/'urban_type_selected_context.csv',index=False);print(d[['source_record_id','census_year','settlement_name','settlement_type','district_raw','population','source_file','source_sheet','source_row','source_name_raw','latitude','longitude','okato']].to_string(index=False))
