#!/usr/bin/env python3
"""Check scientific identities and counterexamples in the computed local study."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def check(root):
    root=Path(root)
    nodes=pd.read_parquet(root/'services/nodes.parquet')
    links=pd.read_parquet(root/'analysis/documented_relations_with_costs.parquet')
    costs=pd.read_parquet(root/'roads/costs.parquet')
    candidates=pd.read_parquet(root/'analysis/known_service_candidates.parquet')
    supply=pd.read_parquet(root/'services/supply.parquet')
    comparison=pd.read_parquet(root/'analysis/service_comparison.parquet')
    units=pd.read_parquet(root/'analysis/documented_unit_demography.parquet')
    employees=pd.read_parquet(root/'economy/outputs/organisation_headcount.parquet')
    memberships=pd.read_parquet(root/'economy/outputs/accepted_municipal_membership.parquet')
    original_count=pd.read_parquet(root/'economy/outputs/registered_counts.parquet')
    assert nodes.source_record_id.is_unique and len(nodes)==19
    assert len(links)==26 and not links.observed_flow.any() and int(links.external.sum())==21
    assert not links.duplicated(['origin_id','destination_id','service_code']).any()
    assert not costs.duplicated(['origin_id','destination_id']).any()
    external=costs.origin_id.ne(costs.destination_id)
    assert np.allclose(costs.loc[external,'cost_minutes'],costs.loc[external,'network_minutes']+costs.loc[external,'connector_minutes'])
    assert costs.cost_minutes.notna().all() and costs.cost_minutes.ge(0).all()
    assert not candidates.established_flow.any() and candidates.supply_status.eq('observed').all()
    assert candidates.capacity_feasibility.eq('not_estimated').all()
    assert not comparison.service_code.eq('school_grade_unspecified').any()
    strict=comparison[comparison.scenario.eq('known_service_only')]
    assert len(strict)==12 and not strict.comparison_is_blind_holdout.any()
    # Unknown local supply does not become confirmed absence, an empty hospital
    # referral table does not become arrows, and undated counts remain undated.
    assert not links.service_code.eq('medical_local_hospital').any()
    hospital=supply[supply.service_code.eq('medical_local_hospital')]
    assert len(hospital)==1 and hospital.capacity_total.iloc[0]==10 and hospital.capacity_observation_year.isna().all()
    fap=supply[supply.service_code.eq('medical_primary_fap')]
    assert fap.population_reference_date.isna().all()
    small=units[units.center_name.eq('Малоказаккулово')&units.function.eq('education')].iloc[0]
    assert small.member_count==3 and small.population_2021==559 and small.population_2002==578
    assert units.descriptive_type.notna().all() and not units.type_is_causal_word_type.any()
    assert units[units.center_name.eq('Курама')].descriptive_type.eq('insufficient_comparable_demography').all()
    assert not units.is_disjoint_partition.any() and not units.historical_membership_equivalence_proven.any()
    assert len(employees)==1 and int(employees.organisation_headcount.iloc[0])==205
    assert employees.inn.astype(str).str.zfill(10).iloc[0]=='0270015537'
    assert employees.settlement_jobs.isna().all() and not employees.commuting_origins_observed.any()
    assert original_count.jobs.isna().all()
    assert len(memberships)==11 and memberships.source_record_id_2021.notna().all()
    return {'documented_relations':len(links),'strict_known_service_comparisons':len(strict),
            'strict_matches_not_blind_validation':int(strict.matches_documented_destination.sum()),
            'road_pairs':len(costs),'organisation_headcount_2025':int(employees.organisation_headcount.iloc[0]),
            'estimated_observed_flows':0}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    print(json.dumps(check(p.parse_args().root),ensure_ascii=False,indent=2))
