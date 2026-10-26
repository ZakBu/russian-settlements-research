#!/usr/bin/env python3
"""Direct service-centre stars, without transitive merging or exclusive partition.

The two/three-core support strata are our diagnostic definitions, not calibrated
thresholds or observed trips. Physical providers with unknown settlement identity
remain functional stars; they never receive an invented nearest settlement.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from lower_profile_quality import part_inventory
from hierarchy import canonical_edges, coordinate_diameter

CORE = ('medical_basic', 'school', 'grocery')
NONADDITIVE_CONTEXT_ROLE = 'external_context_nonadditive'
# Empty results are legitimate (for example a regional extract containing only
# unknown-NP physical providers). Keep public schemas usable downstream.
CENTRE_COLUMNS = ['star_id','centre_settlement_id','centre_name','centre_region',
    'centre_in_analysis_origin','centre_population_is_nonadditive_context','member_records',
    'external_records','external_positive_whole_records','one_or_more_core_external_positive_whole',
    'two_or_more_core_external_positive_whole','all_three_core_external_positive_whole',
    'full_star_geodesic_diameter_km','centre_present_exactly_once','transitive_closure_used',
    'exclusive_partition','population_is_additive_across_stars','observed_flow_count',
    'independent_empirical_validation','support_type','support_type_semantics',
    'centre_unmarked_whole_record','centre_positive_population_known',
    'centre_ordinary_credited_or_nonadditive_context','centre_ordinary_spatial_or_nonadditive_context',
    'centre_own_selected_core_family_count',
    'centre_own_all_three_core_confirmed',*[f'{n}_core_subset_geodesic_diameter_km' for n in (1,2,3)]]
STRICT_EXTRA_COLUMNS = {'strict_external_member_count':'int64','strict_member_count':'int64',
    'strict_geodesic_diameter_km':'float64','strict_population_2021_credited_sum':'float64',
    'any_strict_coordinate_review':'bool','any_strict_road_endpoint_review':'bool',
    'strict_school_stage_unknown_records':'int64','strict_road_component_quality_unknown':'bool',
    'strict_any_component_lt100_diagnostic':'bool'}


def stable_id(kind, *values):
    return kind + ':' + hashlib.sha256('|'.join(map(str, values)).encode()).hexdigest()[:24]


def build_centre_stars(edges, reference, endpoints=None, *, member_batch_size=1024):
    if isinstance(member_batch_size, bool) or not isinstance(member_batch_size, int) or member_batch_size < 1:
        raise ValueError('member_batch_size must be a positive integer')
    edges = canonical_edges(edges)
    if edges.scenario_id.nunique() != 1:
        raise ValueError('Select one explicit scenario before constructing stars')
    ref, _ = part_inventory(reference)
    ref = ref[ref.source_record_id.notna()].copy()
    if not ref.source_record_id.is_unique:
        raise ValueError('Reference identities must be unique')
    ref = ref.set_index('source_record_id')
    if not edges.origin_id.isin(ref.index).all():
        raise ValueError('Unknown origin identity')
    known = edges.provider_settlement_id.dropna()
    if not known.isin(ref.index).all():
        raise ValueError('Unknown declared provider settlement identity')
    admitted = edges[edges.l0_admitted].copy()
    scenario = str(edges.scenario_id.iloc[0])
    # The caller retains the original outcomes. This validated wide copy is no
    # longer needed after admission and identity checks.
    del edges
    admitted['functional_star_id'] = [stable_id('function', scenario, f, k)
        for f, k in zip(admitted.service_family, admitted.provider_key)]
    admitted['provider_np_identity_unknown'] = admitted.provider_settlement_id.isna()
    admitted['external_np_relation_identified'] = admitted.provider_settlement_id.notna() & admitted.origin_id.ne(admitted.provider_settlement_id)
    cartographic = admitted.get('provider_np_identity_is_cartographic', pd.Series(False, index=admitted.index)).fillna(False)
    admitted['external_np_relation_proven'] = admitted.external_np_relation_identified & ~cartographic
    admitted['physical_star_is_not_proven_np_centre'] = admitted.provider_np_identity_unknown
    admitted['school_stage_unknown'] = admitted.get('school_stage_unknown', pd.Series(False, index=admitted.index)).fillna(True)
    admitted['observed_flow'] = False
    admitted['model_link_is_not_observed_assignment'] = True
    # One row per origin/family is retained, including unknown-NP physical sites.
    functional_links = admitted
    metadata = ref[['name', 'region', 'district', 'lat', 'lon', 'population_2021',
                    'population_role', 'budget_population_credit', 'analysis_origin', 'part_status']].copy()
    metadata['positive_whole_spatial'] = (metadata.population_role.eq('ordinary_settlement_record')
        & metadata.analysis_origin.fillna(False)
        & metadata.population_2021.gt(0) & metadata.part_status.eq('unmarked_whole_place_record'))
    metadata['positive_credited_whole'] = metadata.positive_whole_spatial & metadata.budget_population_credit.fillna(False)
    coords = metadata.dropna(subset=['lat', 'lon']).groupby(['lat', 'lon']).size()
    metadata['coincident_coordinate_records'] = coords.reindex(
        pd.MultiIndex.from_frame(metadata[['lat','lon']])).fillna(0).to_numpy(dtype='int64')
    if endpoints is not None:
        ep = endpoints.copy()
        key = 'source_record_id' if 'source_record_id' in ep else 'origin_id'
        ep = ep[ep[key].notna()].drop_duplicates(key).set_index(key)
        for c in ['weak_component', 'road_endpoint_accepted', 'snap_km', 'audit_component_size']:
            metadata[c] = ep[c].reindex(metadata.index) if c in ep else pd.NA
    for c in ['weak_component', 'road_endpoint_accepted', 'snap_km', 'audit_component_size']:
        if c not in metadata: metadata[c] = pd.NA
    fun = []
    functional_source = admitted[['functional_star_id','provider_settlement_id','service_family',
        'provider_key','origin_id','external_np_relation_identified','cost_minutes','school_stage_unknown']]
    for sid, g in functional_source.groupby('functional_star_id', sort=True):
        first = g.iloc[0]
        centre = first.provider_settlement_id
        external = g[g.external_np_relation_identified]
        whole_external = external.origin_id.map(metadata.positive_whole_spatial).fillna(False)
        fun.append(dict(functional_star_id=sid, service_family=first.service_family,
            provider_key=first.provider_key, centre_settlement_id=centre,
            physical_provider_np_unknown=pd.isna(centre), origin_records=len(g),
            positive_whole_origin_records=int(g.origin_id.map(metadata.positive_whole_spatial).sum()),
            external_positive_whole_records=int(whole_external.sum()),
            known_np_external_records=len(external), maximum_directed_minutes=float(g.cost_minutes.max()),
            centre_added_to_functional_origin_count=False, observed_flow_count=0,
            school_stage_unknown_records=int(g.school_stage_unknown.sum()) if first.service_family=='school' else 0))
    functional_stars = pd.DataFrame(fun)
    del functional_source
    # Combined NP stars are direct edges to one known centre. Never recursively
    # add the centres used by that centre: this is the anti-percolation rule.
    source = admitted.loc[admitted.provider_settlement_id.notna(),
        ['origin_id','provider_settlement_id','service_family','cost_minutes','school_stage_unknown']]
    member_rows = []
    member_batches = []
    star_rows = []
    for centre, group in source.groupby('provider_settlement_id', sort=True):
        sid = stable_id('centre', scenario, centre)
        members = {}
        for origin, g in group.groupby('origin_id', sort=False):
            families = set(g.service_family)
            members[origin] = dict(star_id=sid, centre_settlement_id=centre, origin_id=origin,
                member_role='centre' if origin==centre else 'direct_surroundings',
                core_family_count=len(families & set(CORE)),
                core_families_json=json.dumps(sorted(families & set(CORE))),
                all_families_json=json.dumps(sorted(families)),
                parcel_corroboration='parcel_pickup' in families,
                maximum_directed_minutes=float(g.cost_minutes.max()),
                has_direct_selected_link=True,
                school_stage_unknown=bool(g.loc[g.service_family.eq('school'),'school_stage_unknown'].any()))
        if centre not in members:
            members[centre] = dict(star_id=sid, centre_settlement_id=centre, origin_id=centre,
                member_role='centre', core_family_count=0, core_families_json='[]', all_families_json='[]',
                parcel_corroboration=False, maximum_directed_minutes=np.nan,
                has_direct_selected_link=False, school_stage_unknown=False)
        frame = pd.DataFrame(members.values())
        # Identities were validated above and dictionary members are unique.
        # Reindex only this star: an inner merge repeatedly factorized the
        # entire national reference once per centre.
        own_metadata = metadata.reindex(frame.origin_id)
        own_metadata.index = frame.index
        frame = pd.concat([frame, own_metadata], axis=1)
        frame['population_is_additive_across_stars'] = False
        frame['member_in_analysis_origin'] = frame.analysis_origin.fillna(False)
        frame['budget_population_within_star'] = frame.population_2021.where(
            frame.member_in_analysis_origin & frame.population_role.eq('ordinary_settlement_record')
            & frame.budget_population_credit.fillna(False))
        frame['source_part_requires_review'] = frame.part_status.ne('unmarked_whole_place_record')
        frame['coincident_coordinate_requires_review'] = frame.coincident_coordinate_records.gt(1)
        frame['road_component_size_verified'] = frame.audit_component_size.notna()
        frame['road_endpoint_review_needed'] = frame.road_endpoint_accepted.isna() | ~frame.road_endpoint_accepted.astype('boolean').fillna(False).astype(bool)
        frame['road_component_quality_unknown'] = frame.audit_component_size.isna()
        frame['road_component_lt100_diagnostic'] = frame.audit_component_size.lt(100).fillna(False)
        frame['road_access_component_review_needed'] = (frame.road_endpoint_review_needed
            | frame.road_component_quality_unknown | frame.road_component_lt100_diagnostic)
        frame['evidence_scope'] = 'modelled_direct_service_choice_not_observed_travel'
        outside = frame.member_role.eq('direct_surroundings')
        positive = outside & frame.positive_whole_spatial
        core_counts = frame.loc[positive, 'core_family_count']
        d = dict(star_id=sid, centre_settlement_id=centre, centre_name=ref.loc[centre,'name'],
            centre_region=ref.loc[centre,'region'], centre_in_analysis_origin=bool(ref.loc[centre,'analysis_origin']),
            centre_population_is_nonadditive_context=ref.loc[centre,'population_role']==NONADDITIVE_CONTEXT_ROLE,
            member_records=len(frame), external_records=int(outside.sum()),
            external_positive_whole_records=int(positive.sum()),
            one_or_more_core_external_positive_whole=int(core_counts.ge(1).sum()),
            two_or_more_core_external_positive_whole=int(core_counts.ge(2).sum()),
            all_three_core_external_positive_whole=int(core_counts.eq(3).sum()),
            full_star_geodesic_diameter_km=coordinate_diameter(frame.lat,frame.lon),
            centre_present_exactly_once=True, transitive_closure_used=False,
            exclusive_partition=False, population_is_additive_across_stars=False,
            observed_flow_count=0, independent_empirical_validation=False)
        d['support_type'] = ('three_core_direct_star' if d['all_three_core_external_positive_whole'] else
            'two_core_direct_star' if d['two_or_more_core_external_positive_whole'] else
            'one_core_direct_star' if d['one_or_more_core_external_positive_whole'] else
            'parcel_only_or_no_positive_whole_external_core')
        d['centre_unmarked_whole_record'] = ref.loc[centre,'part_status']=='unmarked_whole_place_record'
        d['centre_positive_population_known'] = bool(pd.notna(ref.loc[centre,'population_2021']) and ref.loc[centre,'population_2021']>0)
        d['centre_ordinary_credited_or_nonadditive_context'] = bool(
            (ref.loc[centre,'population_role']=='ordinary_settlement_record'
                and pd.notna(ref.loc[centre,'budget_population_credit']) and bool(ref.loc[centre,'budget_population_credit']))
            or ref.loc[centre,'population_role']==NONADDITIVE_CONTEXT_ROLE)
        d['centre_ordinary_spatial_or_nonadditive_context'] = bool(
            ref.loc[centre,'population_role'] in {'ordinary_settlement_record', NONADDITIVE_CONTEXT_ROLE})
        d['support_type_semantics'] = 'maximum_external_support_not_uniform_membership'
        centre_own = set(group.loc[group.origin_id.eq(centre), 'service_family']) & set(CORE)
        d['centre_own_selected_core_family_count'] = len(centre_own)
        d['centre_own_all_three_core_confirmed'] = len(centre_own)==3
        for count in (1,2,3):
            eligible = positive & frame.core_family_count.ge(count)
            frame[f'in_{count}_core_positive_whole_subset'] = eligible | frame.member_role.eq('centre')
            subset = frame.loc[frame[f'in_{count}_core_positive_whole_subset']]
            d[f'{count}_core_subset_geodesic_diameter_km'] = coordinate_diameter(subset.lat,subset.lon)
        star_rows.append(d); member_rows.append(frame)
        # Bound the small DataFrames retained before concat; tens of thousands
        # of these create unnecessary peak memory on smaller runners.
        if len(member_rows) >= member_batch_size:
            member_batches.append(pd.concat(member_rows,ignore_index=True))
            member_rows.clear()
    stars = pd.DataFrame(star_rows) if star_rows else pd.DataFrame(columns=CENTRE_COLUMNS)
    member_columns = ['star_id','centre_settlement_id','origin_id','member_role','core_family_count',
        'core_families_json','all_families_json','parcel_corroboration','maximum_directed_minutes',
        'has_direct_selected_link','school_stage_unknown',*metadata.columns,
        'population_is_additive_across_stars','member_in_analysis_origin','budget_population_within_star',
        'source_part_requires_review','coincident_coordinate_requires_review','road_component_size_verified',
        'road_endpoint_review_needed','road_component_quality_unknown','road_component_lt100_diagnostic',
        'road_access_component_review_needed','evidence_scope',
        *[f'in_{n}_core_positive_whole_subset' for n in (1,2,3)]]
    if member_rows:
        member_batches.append(pd.concat(member_rows,ignore_index=True))
        member_rows.clear()
    memberships = (member_batches[0] if len(member_batches)==1 else
        pd.concat(member_batches,ignore_index=True) if member_batches else pd.DataFrame(columns=member_columns))
    # Release intermediate tables before strict metadata is calculated.
    del member_batches, member_rows, source
    # Strict three-family groups contain no one/two-family appendages. They
    # also require the centre's own selected evidence for all three families.
    # This is a model-screened subset, not evidence of observed journeys.
    strict_stars = stars[stars.all_three_core_external_positive_whole.gt(0)
        & stars.centre_own_all_three_core_confirmed & stars.centre_in_analysis_origin
        & stars.centre_unmarked_whole_record & stars.centre_positive_population_known
        & stars.centre_ordinary_spatial_or_nonadditive_context].copy() if len(stars) else stars.copy()
    strict_members = memberships[memberships.star_id.isin(strict_stars.star_id)
        & memberships.in_3_core_positive_whole_subset].copy() if len(stars) else memberships.copy()
    if len(strict_members):
        strict_members['strict_subset_rule'] = 'centre_own_three_core_and_each_positive_whole_external_same_three_core_centre'
        external = strict_members.member_role.eq('direct_surroundings')
        repeats = strict_members[external].groupby('origin_id').star_id.nunique()
        strict_stars['strict_external_member_count'] = strict_stars.all_three_core_external_positive_whole
        strict_stars['strict_member_count'] = strict_stars.strict_external_member_count + 1
        strict_stars['strict_geodesic_diameter_km'] = strict_stars['3_core_subset_geodesic_diameter_km']
        strict_stars['strict_population_2021_credited_sum'] = strict_stars.star_id.map(strict_members.groupby('star_id').budget_population_within_star.sum(min_count=1))
        strict_stars['any_strict_coordinate_review'] = strict_stars.star_id.map(strict_members.groupby('star_id').coincident_coordinate_requires_review.any())
        strict_stars['any_strict_road_endpoint_review'] = strict_stars.star_id.map(strict_members.groupby('star_id').road_endpoint_review_needed.any())
        strict_stars['strict_road_component_quality_unknown'] = strict_stars.star_id.map(strict_members.groupby('star_id').road_component_quality_unknown.any())
        strict_stars['strict_any_component_lt100_diagnostic'] = strict_stars.star_id.map(strict_members.groupby('star_id').road_component_lt100_diagnostic.any())
        strict_stars['strict_school_stage_unknown_records'] = strict_stars.star_id.map(strict_members.groupby('star_id').school_stage_unknown.sum())
    else:
        repeats = pd.Series(dtype=int)
    for column, dtype in STRICT_EXTRA_COLUMNS.items():
        if column not in strict_stars:
            strict_stars[column] = pd.Series(index=strict_stars.index, dtype=dtype)
    if 'strict_subset_rule' not in strict_members:
        strict_members['strict_subset_rule'] = pd.Series(index=strict_members.index,dtype='string')
    summary = dict(scenario_id=scenario, admitted_direct_service_links=len(admitted),
        functional_stars=len(functional_stars),
        unknown_np_physical_functional_stars=int(functional_stars.physical_provider_np_unknown.sum()) if len(functional_stars) else 0,
        known_np_functional_stars=int((~functional_stars.physical_provider_np_unknown).sum()) if len(functional_stars) else 0,
        known_np_centre_stars=len(stars), support_type_counts=stars.support_type.value_counts().to_dict() if len(stars) else {},
        two_core_is_our_support_stratum_not_a_literature_threshold=True,
        strict_three_core_model_screened_stars=len(strict_stars),
        strict_three_core_external_positive_whole_records=int(strict_members.member_role.eq('direct_surroundings').sum()) if len(strict_members) else 0,
        strict_external_origins_with_multiple_strict_centres=int(repeats.gt(1).sum()),
        strict_groups_are_model_screened_not_observed_assignments=True,
        observed_or_fully_validated_sgrt_count=0,
        population_across_overlapping_stars_must_not_be_summed=True,
        physical_site_unknown_np_never_assigned_by_proximity=True)
    return {'functional_stars':functional_stars, 'functional_links':functional_links,
            'centre_stars':stars, 'centre_memberships':memberships,
            'strict_three_core_stars':strict_stars, 'strict_three_core_memberships':strict_members}, summary


def run(edges, reference, output, endpoints=None):
    output.mkdir(parents=True, exist_ok=True)
    tables, summary = build_centre_stars(pd.read_parquet(edges),pd.read_parquet(reference),
        pd.read_parquet(endpoints) if endpoints else None)
    for name, frame in tables.items(): frame.to_parquet(output/(name+'.parquet'),index=False)
    summary['input_sha256'] = {str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in [edges,reference,*([endpoints] if endpoints else [])]}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--edges',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--endpoints',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.edges,a.reference,a.output,a.endpoints),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
