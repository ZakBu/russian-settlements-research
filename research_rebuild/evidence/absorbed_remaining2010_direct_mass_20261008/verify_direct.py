"""Verify frozen direct batch against actual selected IDs and source controls."""
import json,sys
from pathlib import Path
import duckdb,pandas as pd
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha

def main():
    receipt=json.loads((OUT/'receipt.json').read_text())
    assert sha(OUT/'build_direct.py')==receipt['code_sha256']
    for name,h in receipt['input_pins'].items():assert sha(Path(name))==h,name
    for name,h in receipt['output_pins'].items():assert sha(OUT/name)==h,name
    children=pd.read_csv(OUT/'candidate_historical_observations.csv',keep_default_na=False)
    cores=pd.read_csv(OUT/'actual_receiving_city_three_census_context.csv',keep_default_na=False)
    edges=pd.read_csv(OUT/'candidate_included_in_event_edges.csv',keep_default_na=False)
    credit=pd.read_csv(OUT/'candidate_direct_event_native_credit_union.csv',keep_default_na=False)
    points=pd.read_csv(OUT/'candidate_former_locality_own_points.csv',keep_default_na=False)
    assert children.source_record_id.is_unique and len(children)==2 and len(cores)==3
    assert set(children.year)=={2002,2010} and set(cores.census_year)=={2002,2010,2021}
    assert edges.relation.eq('included_in').all() and not edges.graph_union_allowed.any()
    assert not children.child_2021_population_assigned.any() and not children.is_additive_to_original_final_mixed_census_axis.any()
    ids=children.source_record_id.tolist()+cores.source_record_id.tolist()
    db=duckdb.connect();selected=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
    actual=db.execute('SELECT source_record_id,census_year,settlement_name,settlement_type,population,population_value_quality FROM read_parquet(?) WHERE source_record_id IN (SELECT UNNEST(?))',[str(selected),ids]).fetchdf().set_index('source_record_id');db.close()
    assert len(actual)==5
    for row in children.itertuples():
        native=actual.loc[row.source_record_id];assert native.population==row.native_population and native.population_value_quality==row.native_population_quality
        assert native.settlement_name=='Куровской' and native.settlement_type=='пгт' and int(native.census_year)==row.year
    for row in cores.itertuples():
        native=actual.loc[row.source_record_id];assert native.population==row.population and native.population_value_quality==row.population_value_quality
        assert native.settlement_name=='Калуга' and native.settlement_type=='город' and row.new_national_credit_population==0
    for row in points.itertuples():
        assert row.own_locality_point and not row.recipient_point_assigned_to_child
        frame=pd.read_csv(row.point_origin_file,keep_default_na=False)
        target=frame[frame.target_source_record_id.eq(row.target_source_record_id)]
        assert len(target)==1 and float(target.iloc[0].latitude)==row.latitude and float(target.iloc[0].longitude)==row.longitude
    net={str(int(y)):int(g.new_population_on_separate_transformation_path_axis.sum()) for y,g in credit.groupby('year')};net['2021']=0
    assert net==receipt['conditional_separate_direct_plus_formation_native_UID_net']
    verification=dict(status='passed_frozen_actual51_source_UID_count_quality_ownpoint_and_direct_sidecar_checks',
        candidate_receipt_sha256=sha(OUT/'receipt.json'),literal_native_population_rows=2,actual_receiving_context_rows=3,
        ownhistorical_point_ledger_exact_row_checks=2,accepted_graph_modified=False,original_mixed_definition_unchanged=True,
        conditional_native_UID_net=net,requested_mass_target_not_claimed=True,code_sha256=sha(Path(__file__)))
    (OUT/'verification_receipt.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n');print(json.dumps(verification))
if __name__=='__main__':main()
