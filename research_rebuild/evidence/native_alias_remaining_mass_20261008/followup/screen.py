import sys,json,pandas as pd,duckdb
from pathlib import Path
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
O=Path(__file__).parent;s=load(27);s.add_deltas([O.parent/'accepted_identity_edge_delta.csv'],[O.parent/'accepted_point_use_delta.csv']);d=s.obs
names={'свердловская':['восточный','красногвардейский','северка'],'тульская':['центральный','рассвет','октябрьский','ревякино','приупский'],'ульяновская':['октябрьский','карлинское','белый ключ']}
f=d[pd.Series([n in names.get(r,[]) for r,n in zip(d.region_norm,d.name_norm)],index=d.index)].copy();f['component_years']=f.source_record_id.map(lambda x:str(sorted(s.years[s.uf.find(x)])));f['point_json']=f.source_record_id.map(lambda x:json.dumps(s.point_rows.get(x,{}),ensure_ascii=False));f.to_csv(O/'bounded_native_type_source_context_components.csv',index=False);print(f[f.population.ge(1000)][['source_record_id','census_year','settlement_name','settlement_type','district_raw','population','component_years','okato']].to_string(index=False))
c=duckdb.connect();h=c.execute("select * from read_parquet('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet') where historical_point_modern_region in ('свердловская','тульская','ульяновская') and name_key in ('восточный','красногвардейский','северка','центральный','рассвет','октябрьский','ревякино','приупский','карлинское','белый ключ')").fetchdf();h.to_csv(O/'bounded_historical_own_code_candidates.csv',index=False)
