#!/usr/bin/env python3
"""Describe strict direct groups and sensitivity without inventing causal types."""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hierarchy import demographic_summaries
from type_readout import centre_periphery


def readout(root, reference_path):
    reference = pd.read_parquet(reference_path)
    scenario_summaries={}
    for folder in sorted((root/'scenarios').iterdir()):
        if folder.is_dir():
            summary=json.loads((folder/'summary.json').read_text())
            if summary['scenario_id']!=folder.name:raise ValueError('Scenario folder/identity mismatch')
            scenario_summaries[folder.name]=summary
    (root/'scenarios/combined_summary.json').write_text(json.dumps({'scenarios':scenario_summaries,
        'additional_scenarios_may_contain_strict_subset_only':True},ensure_ascii=False,indent=2)+'\n')
    main = root / 'scenarios/daily_20_school30_wb'
    stars = pd.read_parquet(main / 'strict_three_core_stars.parquet')
    members = pd.read_parquet(main / 'strict_three_core_memberships.parquet')
    units = stars.rename(columns={'star_id':'unit_id'}).copy()
    units['provider_keys_json'] = units.centre_settlement_id.map(lambda x: json.dumps(['np:'+x]))
    mm = members.rename(columns={'star_id':'unit_id'})
    centre = centre_periphery(units, mm, reference)
    if 'unit_id' not in centre:centre['unit_id']=pd.Series(dtype='string')
    for year in [2002,2010]:
        field = f'joint_centre_surrounding_direction_{year}_2021'
        if field not in centre:centre[field] = pd.Series(dtype='string')
    demographics = demographic_summaries(mm, reference, compute_geometry=False)
    centre.to_parquet(main / 'strict_centre_surrounding_dynamics.parquet', index=False, compression='zstd')
    demographics.to_parquet(main / 'strict_group_dynamics.parquet', index=False, compression='zstd')
    roster=stars[['star_id','centre_settlement_id','centre_name','centre_region',
                  'strict_external_member_count','strict_geodesic_diameter_km',
                  'strict_school_stage_unknown_records']].merge(
        reference.dropna(subset=['source_record_id'])[['source_record_id','settlement_type_2021','population_2021']],
        left_on='centre_settlement_id',right_on='source_record_id',validate='one_to_one').drop(columns='source_record_id')
    roster=roster.merge(centre[['unit_id','joint_centre_surrounding_direction_2002_2021',
                                'joint_centre_surrounding_direction_2010_2021']],
                        left_on='star_id',right_on='unit_id',validate='one_to_one').drop(columns='unit_id')
    roster.sort_values(['centre_region','centre_name']).to_csv(root/'checked_model_centres.csv',index=False)
    # Compare by real endpoint identities; scenario-specific star IDs must not
    # make identical memberships look like different geographical groups.
    base = set(zip(members.origin_id, members.centre_settlement_id))
    sensitivity = []
    for folder in sorted((root/'scenarios').iterdir()):
        if not folder.is_dir():continue
        others = pd.read_parquet(folder / 'strict_three_core_memberships.parquet')
        keys = set(zip(others.origin_id, others.centre_settlement_id))
        if folder.name in {'core3_20_school30','daily_20_school30_yandex'} and keys != base:
            raise ValueError('Optional PVZ channel changed strict three-core membership')
        sensitivity.append({'scenario_id':folder.name,'centre_member_pairs':len(keys),
                            'same_pairs_as_main':len(base & keys),
                            'pairs_main_only':len(base-keys),'pairs_sensitivity_only':len(keys-base)})
    pd.DataFrame(sensitivity).to_parquet(root / 'scenario_membership_comparison.parquet', index=False)
    edges=pd.read_parquet(main/'daily_edges.parquet')
    core_edges=edges[edges.service_family.isin(['medical_basic','school','grocery'])]
    strict_links=mm[['unit_id','origin_id','centre_settlement_id']].merge(core_edges,
        left_on=['origin_id','centre_settlement_id'],right_on=['origin_id','provider_settlement_id'],
        validate='one_to_many')
    if len(strict_links)!=3*len(mm) or not strict_links.l0_admitted.all():
        raise ValueError('Every strict member must have exactly three admitted direct core links')
    strict_links['scope']='strict_core_only_parcel_not_included'
    strict_links.to_parquet(main/'strict_selected_core_links.parquet',index=False,compression='zstd')
    coverage=[]
    for family,g in edges[edges.service_family.isin(['medical_basic','school','grocery'])].groupby('service_family'):
        coverage.append({'service_family':family,'all_origin_records':len(g),
                         'admitted_records':int(g.l0_admitted.sum()),
                         'admitted_known_np_provider':int((g.l0_admitted & g.provider_settlement_id.notna()).sum()),
                         'admitted_unknown_np_physical_provider':int((g.l0_admitted & g.provider_settlement_id.isna() & g.provider_site_id.notna()).sum()),
                         'far_or_unknown_records':int((~g.l0_admitted).sum())})
    pd.DataFrame(coverage).to_parquet(root/'core_provider_identity_coverage.parquet',index=False)
    broad=pd.read_parquet(main/'centre_stars.parquet')
    daily=broad[broad.one_or_more_core_external_positive_whole.gt(0)
        & broad.centre_unmarked_whole_record & broad.centre_positive_population_known
        & broad.centre_ordinary_credited_or_nonadditive_context]
    result = {'strict_model_groups':len(stars),
              'unique_centre_member_pairs':len(base),
              'unique_origin_records':int(members.origin_id.nunique()),
              'origin_records_in_multiple_strict_groups':int(members.groupby('origin_id').star_id.nunique().gt(1).sum()),
              'joint_centre_surrounding_2002_2021':centre.joint_centre_surrounding_direction_2002_2021.value_counts().to_dict(),
              'joint_centre_surrounding_2010_2021':centre.joint_centre_surrounding_direction_2010_2021.value_counts().to_dict(),
              'fixed_current_membership_not_historical_service_boundaries':True,
              'optional_parcel_strict_membership_identity_is_by_construction_not_validation':True,
              'core_identity_and_admission_coverage':coverage,
              'known_daily_centres_with_positive_whole_external_core_members':len(daily),
              'wider_daily_stars_are_overlapping_not_a_sgrt_count':True,
              'causal_word_typology_established':False,
              'all_groups_with_coordinate_review':int(stars.any_strict_coordinate_review.sum()),
              'all_groups_with_endpoint_review':int(stars.any_strict_road_endpoint_review.sum()),
              'groups_with_unknown_component_size':int(stars.strict_road_component_quality_unknown.sum()),
              'groups_with_component_lt100_diagnostic':int(stars.strict_any_component_lt100_diagnostic.sum()),
              'groups_with_unknown_school_stage':int(stars.strict_school_stage_unknown_records.gt(0).sum()),
              'diameter_km':{k:float(stars.strict_geodesic_diameter_km.quantile(q)) if len(stars) else None for k,q in [('median',.5),('p95',.95),('max',1)]},
              'membership_sensitivity':sensitivity}
    (root/'readout.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);a=p.parse_args();print(json.dumps(readout(a.root,a.reference),ensure_ascii=False,indent=2))
