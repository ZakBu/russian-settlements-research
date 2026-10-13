from pathlib import Path
import pandas as pd,duckdb,json,hashlib,gzip
O=Path(__file__).parent;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
h=pd.read_csv(O/'candidate_historical_observations.csv.gz');e=pd.read_csv(O/'candidate_included_in_event_edges.csv.gz');p=pd.read_csv(O/'candidate_former_locality_own_points.csv.gz');c=pd.read_csv(O/'actual_receiving_city_three_census_context.csv.gz');u=pd.read_csv(O/'candidate_direct_event_native_credit_union.csv.gz');ev=pd.read_csv(O/'candidate_inclusion_events.csv.gz');raw=pd.read_csv(O/'actual_native_raw_reopenings.csv.gz');receipt=json.loads((O/'receipt.json').read_text());pins=json.loads((O/'source_manifest.json').read_text())
assert receipt['baseline_stage']==46
assert len(ev)==20 and len(h)==21 and len(e)==21 and len(p)==21 and len(c)==60
assert h.source_record_id.is_unique and u.source_record_id.is_unique and set(h.source_record_id)==set(u.source_record_id)==set(e.from_source_record_id)==set(p.target_source_record_id)
assert h.year.isin([2002,2010]).all() and ~h.child_2021_population_assigned.any() and h.own_point.all()
assert ~e.same_place.any() and ~e.graph_union_allowed.any() and e.relation.eq('included_in').all()
assert c.is_receiving_city_context_only.all() and c.new_national_credit_population.eq(0).all() and c.child_count_substituted.eq(False).all()
assert ~ev.roster_closed.any() and ~ev.sum_city_equals_children_asserted.any()
for scope,g in c.groupby('scope_id'):assert set(g.census_year)=={2002,2010,2021} and g.source_record_id.nunique()==3
for scope,g in h.groupby('scope_id'):
 rec=c[c.scope_id.eq(scope)&c.census_year.eq(2021)].iloc[0];assert g.receiving_city_2021_source_record_id.eq(rec.source_record_id).all() and g.receiving_city_2021_count_context_only.eq(rec.population).all()
conn=duckdb.connect();native=conn.execute("select source_record_id,census_year,population,population_value_quality,settlement_name,settlement_type,is_additive_settlement_record from read_parquet(?) where source_record_id in (select unnest(?))",['/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet',h.source_record_id.tolist()+c.source_record_id.tolist()]).fetchdf().set_index('source_record_id');conn.close()
for z in h.itertuples():
 n=native.loc[z.source_record_id];assert n.census_year==z.year and n.population==z.native_population and n.population_value_quality==z.native_population_quality and n.is_additive_settlement_record
for z in c.itertuples():assert native.loc[z.source_record_id].population==z.population and native.loc[z.source_record_id].census_year==z.census_year
assert len(raw)==21 and raw.matches_selected_population.all() and raw.raw_reopening_status.eq('original_Excel_exact_raw_cell_reopened').all()
for path,digest in pins.items():assert Path(path).is_file() and sha(Path(path))==digest,path
for z in e.itertuples():assert sha(Path(z.event_source_file))==z.event_source_sha256
for z in p.itertuples():assert sha(Path(z.point_origin_file))==z.point_origin_sha256
net={str(int(y)):int(g.new_population_on_separate_transformation_path_axis.sum())for y,g in u.groupby('year')};net['2021']=0;assert net==receipt['conditional_separate_transformation_path_native_UID_net']
q={'status':'passed_independent_native_ID_count_quality_point_event_and_source_hash_verification','baseline_stage':46,'events':20,'historical_observations':21,'receiving_context_observations':60,'separate_transformation_path_native_UID_net':net,'original_final_mixed_delta':receipt['original_final_mixed_census_population_delta'],'new_ordinary_graph_edges':0,'new_ordinary_point_uses':0,'child2021_observations':0,'fetched_compressed_raw_bytes':sum(x.stat().st_size for x in O.glob('own_wikipedia*batch.json.gz'))}
(O/'verification_receipt.json').write_text(json.dumps(q,ensure_ascii=False,indent=2));print(json.dumps(q))
