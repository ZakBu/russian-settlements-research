#!/usr/bin/env python3
"""Scientific conservation checks on the national computed bundle, not approval."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def check(root):
    root=Path(root)
    nodes=pd.read_parquet(root/'routes/endpoints.parquet')
    reference=pd.read_parquet(root/'context/census_reference.parquet')
    units=pd.read_parquet(root/'model/units.parquet')
    memberships=pd.read_parquet(root/'model/memberships.parquet')
    states=pd.read_parquet(root/'model/settlement_functional_states.parquet')
    assert len(nodes)==153800 and nodes.source_record_id.is_unique
    assert len(states)==len(nodes) and states.source_record_id.is_unique
    assert units.unit_id.is_unique and units.type_code.notna().all() and units.type_label_ru.notna().all()
    assert not units.unit_is_established_sgrt.any() and not units.type_is_causal_word_type.any()
    assert not memberships.duplicated(['scenario','service_code','origin_id']).any()
    assert memberships.origin_id.isin(nodes.source_record_id).all()
    assert memberships.unit_id.isin(units.unit_id).all()
    assert units.loc[units.center_source_record_id.isna(),'n_populated_external'].eq(0).all()
    assert units.loc[units.center_source_record_id.isna(),'type_code'].eq('center_settlement_identity_unknown').all()
    assert units.loc[units.center_source_record_id.isna(),'external_population_2021'].isna().all()
    assert states.all_functions_satisfied.isna().all()
    assert not units.agro_or_employment_used_as_attraction_weight.any()
    # A member appears at most once within each functional/source layer. Its
    # population is demographic context, not users of the relevant service.
    budget=nodes.loc[nodes.working_credit_present,'population'].sum()
    sums=units.groupby(['scenario','service_code']).external_population_2021.sum(min_count=1)
    assert sums.dropna().le(budget+1e-6).all()
    route_rows=0;paths=[]
    for folder in ['routes/nearest','routes_sites/nearest']:
        for p in sorted((root/folder).glob('*.parquet')):
            d=pd.read_parquet(p)
            assert len(d)==len(nodes) and d.origin_id.is_unique
            assert set(d.origin_id)==set(nodes.source_record_id)
            finite=d.cost_minutes.notna()
            assert np.isfinite(d.loc[finite,'cost_minutes']).all() and d.loc[finite,'cost_minutes'].ge(0).all()
            assert np.allclose(d.loc[finite,'network_minutes']+d.loc[finite,'connector_minutes'],d.loc[finite,'cost_minutes'],rtol=0,atol=1e-8)
            assert not d.observed_flow.any() and not d.assignment_established.any()
            local=d.known_local_supply
            assert d.loc[local,'zero_cost_np_assumption'].all() and d.loc[local,'cost_minutes'].eq(0).all()
            route_rows+=len(d);paths.append(str(p.relative_to(root)))
    assert len(paths)==14
    comparison=pd.read_parquet(root/'audit/lo_normative_comparison/pair_level_comparison.parquet')
    assert not comparison.duplicated(['origin_id','service_code']).any()
    assert comparison.origin_id.isin(nodes.source_record_id).all()
    assert not comparison.parameters_fitted_to_these_pairs.any()
    assert not comparison.service_tier_equivalence_established.any()
    assert set(comparison.service_code)=={'medical_basic_primary','medical_physician_primary'}
    for p in [root/'audit/national_np_final/concrete_violations.parquet',root/'audit/national_physical_final/concrete_violations.parquet']:
        assert p.is_file(), f'Missing final audit: {p}'
        assert pd.read_parquet(p).empty
    if 'center_partial_organisation_workforce_2025' in units:
        assert units.center_partial_organisation_workforce_2025.dropna().ge(0).all()
        assert not units.reported_workers_are_total_jobs_or_commuting_flows.any()
    return {'ordinary_spatial_np':len(nodes),'route_tables':len(paths),'route_rows':route_rows,
            'functional_source_units_not_a_country_partition':len(units),
            'every_unit_typed':True,'membership_rows':len(memberships),
            'known_np_with_external_candidates':int(units.loc[units.n_populated_external.gt(0)&units.center_population_role.eq('ordinary_settlement_record'),'center_source_record_id'].nunique()),
            'direct_site_cells_without_proven_np':int(units.is_populated_site_service_cell.sum()),
            'independent_normative_origins':int(comparison.origin_id.nunique()),
            'observed_journeys_estimated':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    print(json.dumps(check(p.parse_args().root),ensure_ascii=False,indent=2))
