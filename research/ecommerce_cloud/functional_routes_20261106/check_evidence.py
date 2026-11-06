"""Recount published registers and check geography against pinned source rows.

This checks arithmetic, identifiers and coding boundaries, not informant truth.
Raw searches/profile pages are deliberately not redistributed.
"""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent

def main():
    base=ROOT/'work/sources/research/ecommerce_settlement_20261024'
    frame=pd.read_csv(base/'settlement_role_stage_20261024/system/centre_system_demography.csv').set_index('source_record_id_2021')
    places=pd.read_parquet(base/'national/national_target_source2021.parquet').set_index('source_record_id_2021')
    cases=pd.read_csv(HERE/'functional_evidence.csv',keep_default_na=False)
    for r in cases.itertuples():
        assert frame.loc[r.prior_centre_id,'medium_primary2002']
        assert frame.loc[r.prior_centre_id,'name_2021']==r.prior_centre
        assert places.loc[r.current_place_id,'name_2021']==r.current_receipt_place
        assert int(frame.loc[r.prior_centre_id,'population_2002'])==r.prior_centre_population2002
        assert (r.residential_origin=='')==(r.origin_status=='unknown')
        assert not r.after_trip_reduction_measured and not r.physical_goods_bypass_proven
    west=pd.read_csv(HERE/'observed_west/centre_screening.csv')
    west=west.loc[west.in_fixed_analysis]
    east=pd.read_csv(HERE/'observed_east/cohort_filter.csv')
    planned=east.loc[east.scope.eq('planned_ural_siberia_volga')]
    assert len(west)==24 and len(planned)==29
    for f in (west,planned):
        assert f.source_record_id_2021.is_unique
        assert frame.loc[f.source_record_id_2021,'medium_primary2002'].all()
    assert not set(west.source_record_id_2021)&set(planned.source_record_id_2021)
    logs=pd.read_csv(HERE/'observed_west/query_log.csv')
    assert len(logs.loc[logs.phase.eq('bounded_fixed24')])==72
    eastlogs=pd.read_csv(HERE/'observed_east/query_log.csv')
    assert len(eastlogs)==71 and eastlogs.raw_sha256.notna().sum()==63
    assert len(eastlogs.loc[eastlogs.phase.eq('planned_ural_siberia_volga')])==58
    westextract=pd.read_csv(HERE/'observed_west/primary_extracts.csv',keep_default_na=False)
    assert len(westextract)==5 and westextract.origin_status.eq('unknown').all()
    positivewest=westextract.loc[westextract.evidence_kind.isin([
        'named_prior_centre_local_receipt','named_prior_centre_order_receipt_external_lead',
        'named_prior_centre_gifts_external_lead_old_channel_unknown'])]
    assert positivewest.org_id.nunique()==2
    workers=pd.read_csv(HERE/'producer_functions/edges.csv')
    actual=workers.loc[workers.status.eq('observed_residence_workplace_link')]
    assert len(actual)==2 and not actual.origin.str.contains('Моршанск').any()
    flows=pd.read_csv(HERE/'identification/regional_operator_flows.csv')
    assert len(flows)==11
    assert not flows.absolute_volume_public.any() and not flows.complete_OD_matrix_public.any()
    assert (flows.normalised_2025_index-100*flows.reported_growth_factor).abs().max()<1e-9
    summary=dict(typed_place_cases=len(cases),prior_fixed_centres=cases.prior_centre_id.nunique(),
        new_place_cases=int(cases.first_added_in_this_pass.sum()),
        west_planned_centres=len(west),east_planned_centres=len(planned),
        planned_targeted_queries=72+58,additional_leads_not_in_query_denominator=True,
        residence_workplace_links_in_kotovsk=len(actual),operator_regional_comparisons=len(flows),
        informant_truth_automatically_verified=False)
    print(json.dumps(summary,ensure_ascii=False))
    return summary

if __name__=='__main__':main()
