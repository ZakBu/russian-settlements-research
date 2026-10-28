#!/usr/bin/env python3
"""Comparable census checks, without treating outbound shares as OD flows."""
import argparse
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd


def identified_parent_share_bounds(employed, outside_known, unknown_workplace):
    """No named destination is known: its lower share is zero, not outbound/E."""
    if (not np.isfinite([employed,outside_known,unknown_workplace]).all()
        or employed <= 0 or outside_known < 0 or unknown_workplace < 0
        or outside_known+unknown_workplace > employed):
        raise ValueError('Invalid census margin')
    return 0., (outside_known + unknown_workplace) / employed


def partitioned_parent_upper_bound(employed, same_subject_other_np, outside_subject_residual, unknown):
    if (not np.isfinite([employed,same_subject_other_np,outside_subject_residual,unknown]).all()
        or employed <= 0 or min(same_subject_other_np,outside_subject_residual,unknown)<0
        or same_subject_other_np+outside_subject_residual+unknown > employed):
        raise ValueError('Invalid partitioned census margin')
    return (max(same_subject_other_np,outside_subject_residual)+unknown)/employed


def run(args):
    if not np.isfinite(args.threshold) or not 0<=args.threshold<=1:
        raise ValueError('Threshold must be a finite fraction between zero and one')
    input_sha256={name:hashlib.sha256(getattr(args,name).read_bytes()).hexdigest()
                  for name in ['regional','buryatia','memberships','municipal_profiles']}
    regional = pd.read_csv(args.regional)
    buryatia = pd.read_csv(args.buryatia)
    memberships = pd.read_parquet(args.memberships)
    if not memberships.origin_id.is_unique:
        raise ValueError('Primary census identities must be unique')
    eight = buryatia[buryatia.population_join_candidate_count.eq(1)
                     & buryatia.outside_np_known.notna()].copy()
    # Crosswalk comes from exact unique named urban NP identities in the
    # census source extractor. No municipality-name-to-village shortcut.
    eight = eight.merge(memberships[['origin_id','name','unit_id','membership_status',
        'is_registered_centre','known_function_count']],
        left_on='population_base_source_record_id', right_on='origin_id', how='left', validate='one_to_one')
    eight['named_parent_share_lower_bound'] = 0.
    eight['loose_outbound_only_parent_share_upper_bound'] = (eight.outside_np_known + eight.unknown_workplace) / eight.employed_age15_72
    eight['same_subject_other_np_from_exact_margins'] = eight.same_subject-eight.same_np
    # A particular Russian parent is either inside the same subject OR
    # outside it. It cannot receive both categories. The residual may include
    # suppressed abroad counts, so treating all residual as Russian is a
    # conservative UPPER bound, never a zero-imputation for a censored cell.
    eight['other_subject_or_abroad_exact_residual'] = eight.outside_np_known-eight.same_subject_other_np_from_exact_margins
    if eight.other_subject_or_abroad_exact_residual.lt(0).any():
        raise ValueError('Observed subject and NP margins inconsistent')
    eight['named_parent_share_upper_bound'] = [partitioned_parent_upper_bound(e,s,o,u) for e,s,o,u in zip(
        eight.employed_age15_72,eight.same_subject_other_np_from_exact_margins,
        eight.other_subject_or_abroad_exact_residual,eight.unknown_workplace)]
    eight['commuting_threshold_scenario'] = args.threshold
    eight['any_named_parent_at_threshold_ruled_out_by_2010_margin'] = eight.named_parent_share_upper_bound.lt(args.threshold)
    eight['observed_named_parent_identified'] = False
    eight['matches_2026_local_service_unit_not_2010_commuting_system'] = eight.unit_id.notna()
    eight['geographic_boundary_equivalence_2010_2021_verified'] = False
    eight['historical_margin_validates_current_medical_or_work_trip'] = False
    eight['status'] = np.where(eight.any_named_parent_at_threshold_ruled_out_by_2010_margin,
        '2010_margin_rules_out_threshold_to_any_one_other_NP',
        '2010_margin_allows_but_does_not_identify_any_parent')
    args.output.mkdir(parents=True,exist_ok=True)
    eight.to_parquet(args.output/'buryatia_eight_np_parent_bounds.parquet',index=False)
    eight[['name','employed_age15_72','outside_np_known','unknown_workplace',
           'outside_np_fraction_all_employed','named_parent_share_upper_bound','unit_id','status']].to_csv(
               args.output/'buryatia_eight_np_parent_bounds.csv',index=False)
    # The two distinct synthetic OD matrices share EXACT observed margins.
    # A and B are explicitly hypothetical destination labels, not claimed
    # Russian flows. They show why high outbound share cannot name a parent.
    counterexamples=[]
    for _,row in eight[~eight.any_named_parent_at_threshold_ruled_out_by_2010_margin].iterrows():
        for allocation in ['same_subject_outbound_to_A','same_subject_outbound_to_B']:
            counterexamples.append({'origin':row['name'],'synthetic_not_observed':True,
                'employed_observed':row.employed_age15_72,
                'outbound_observed':row.outside_np_known,
                'same_subject_outbound_observed':row.same_subject_other_np_from_exact_margins,
                'outside_subject_or_abroad_residual_unchanged':row.other_subject_or_abroad_exact_residual,
                'unknown_workplace_observed':row.unknown_workplace,
                'allocation':allocation,
                'hypothetical_A_flow':row.same_subject_other_np_from_exact_margins if allocation.endswith('_A') else 0.,
                'hypothetical_B_flow':row.same_subject_other_np_from_exact_margins if allocation.endswith('_B') else 0.})
    pd.DataFrame(counterexamples).to_parquet(args.output/'same_margin_different_parent_counterexamples.parquet',index=False)
    # Region-level margins are useful as context/aggregate constraints. They
    # cannot supply a city or NP denominator, or the destination of a flow.
    labels=['Республика Татарстан','Саратовская область','Свердловская область',
            'Челябинская область','Московская область','Ленинградская область','г. Москва','г. Санкт-Петербург']
    selected=regional[regional.region.isin(labels)].copy()
    selected['daily_fraction_all_employed']=selected.outside_daily/selected.employed_age15plus
    selected['known_outside_fraction_all_employed']=selected.outside_np/selected.employed_age15plus
    selected['outside_bound_upper_if_all_unresolved_outside']=(selected.outside_np+selected.unresolved_np_location)/selected.employed_age15plus
    selected['named_city_destination_identified']=False
    selected['medical_decay_calibration_permitted']=False
    selected.to_parquet(args.output/'pilot_subject_workplace_margins_2021.parquet',index=False)
    ecological=[]
    # Real Moscow-oblast margin, two explicitly synthetic subgroup layouts.
    # The region's daily fraction below15% cannot rule out a concentrated
    # subgroup above15%. No real municipality is assigned these numbers.
    mo=selected[selected.region.eq('Московская область')
                &selected.population_category.eq('Городское и сельское население')]
    if len(mo)==1:
        e=int(mo.iloc[0].employed_age15plus); f=int(mo.iloc[0].outside_daily); small=500000
        uniform=f/e
        ecological=[{'synthetic_layout':'uniform_share','synthetic_not_observed':True,
            'regional_employed_observed':e,'regional_daily_outbound_observed':f,
            'subgroup_employed_scenario':small,'subgroup_daily_outbound_scenario':uniform*small,
            'subgroup_daily_fraction_scenario':uniform},
            {'synthetic_layout':'concentrated_share','synthetic_not_observed':True,
            'regional_employed_observed':e,'regional_daily_outbound_observed':f,
            'subgroup_employed_scenario':small,'subgroup_daily_outbound_scenario':300000,
            'subgroup_daily_fraction_scenario':.6}]
        pd.DataFrame(ecological).to_parquet(args.output/'regional_margin_ecological_counterexample.parquet',index=False)
    # Only the federal cities have a matching 2021 census residence territory
    # and the chosen 2025 municipal/subject worker observation. Epoch and
    # statistical universes still differ, so the ratio is NOT self-containment.
    profiles=pd.read_parquet(args.municipal_profiles)
    workforce=[]
    for code,label in [('45000000','г. Москва'),('40000000','г. Санкт-Петербург')]:
        jobs=profiles[profiles.oktmo.astype(str).eq(code)]
        residents=selected[selected.region.eq(label)&selected.population_category.eq('Городское население')]
        if len(jobs)!=1 or len(residents)!=1: raise ValueError('Federal territory ambiguity')
        j=float(jobs.iloc[0].partial_organisation_workers_2025_territorial)
        e=float(residents.iloc[0].employed_age15plus)
        workforce.append({'territory':label,'partial_organisation_workers_2025':j,
            'employed_residents_private_households_age15plus_2021':e,
            'ratio_permitted':False,
            'ratio_identifies_inbound_or_outbound_flow':False})
    pd.DataFrame(workforce).to_parquet(args.output/'federal_workers_residents_scope_comparison.parquet',index=False)
    summary={'source_epochs_kept_separate':[2010,2021,2025,2026],
        'input_sha256':input_sha256,
        'buryatia_exact_matched_np':len(eight),
        'buryatia_np_with_current_local_unit':int(eight.unit_id.notna().sum()),
        'threshold_scenario':args.threshold,
        'any_parent_ruled_out_by_2010_upper_margin':int(eight.any_named_parent_at_threshold_ruled_out_by_2010_margin.sum()),
        'parent_destination_identified_by_observation':0,
        'sharper_parent_upper_bound_uses_same_subject_vs_other_subject_partition':True,
        'sharper_bound_scope':'one_named_destination_NP_in_one_subject_not_a_multisubject_parent_system',
        'multisubject_parent_must_use_loose_outbound_only_bound':True,
        'synthetic_same_margin_OD_counterexamples':len(counterexamples),
        'pilot_subject_labels_missing_in_extracted_data':sorted(set(labels)-set(selected.region)),
        'regional_margins_do_not_identify_municipal_or_NP_parent':True,
        'medical_parameters_calibrated_from_workplace_margins':False,
        'minimal_named_parent_observation':{'required':['employed_residents_of_child_same_epoch_Ei',
            'employed_residents_of_child_working_in_named_parent_Fij',
            'unresolved_membership_in_named_parent_Uij_including_unnamed_destinations',
            'exact_compatible_geographic_units'],
            'lower_bound':'Fij/Ei','upper_bound':'(Fij+Uij)/Ei',
            'accept_threshold_evidence':'lower_bound >= threshold',
            'reject_threshold_evidence':'upper_bound < threshold',
            'otherwise':'unresolved_not_zero',
            'additional_territorial_rules':'whole-child direct accessibility, non-percolation and nesting remain independent requirements'}}
    (args.output/'diagnostics_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['regional','buryatia','memberships','municipal-profiles','output']:
        p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--threshold',type=float,default=.15)
    run(p.parse_args())
