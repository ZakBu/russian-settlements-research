#!/usr/bin/env python3
"""Review the whole bounded photography/technical/exam-preparation family."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import pandas as pd
from compare_public_education_revision import IDENTITY
from education import programme_mismatch_reason

PATTERN = re.compile(r'фотограф|фотошкол|технопарк|кванториум|робототех|подготовк.{0,35}(?:егэ|огэ)|курсы.{0,35}(?:егэ|огэ)|exam_preparation|photography|robotics', re.I)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--after', type=Path, required=True)
    p.add_argument('--routes-before', type=Path, required=True)
    p.add_argument('--routes-after', type=Path)
    p.add_argument('--strict-stars-before', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    before_path, after_path = [root / 'source_inventory_current.parquet' for root in [a.before, a.after]]
    before, after = [pd.read_parquet(path).set_index('provider_id') for path in [before_path, after_path]]
    if not before.index.is_unique or set(before.index) != set(after.index):
        raise ValueError('Source provider roster changed')
    after = after.loc[before.index]
    pd.testing.assert_frame_equal(before[IDENTITY], after[IDENTITY], check_dtype=False)
    def candidate(row):
        tags=json.loads(row.tags_json)
        values=[row['name']] + [tags.get(k,'') for k in ['name','official_name','alt_name','name:ru','name:en','description','subject','school:subject']]
        return bool(PATTERN.search(' '.join(map(str,values))))
    selected = after[after.apply(candidate,axis=1)].copy()
    selected['previously_eligible'] = before.eligible.reindex(selected.index)
    selected['newly_held'] = selected.previously_eligible & ~selected.eligible
    def review(row):
        if row.newly_held:
            return 'explicit_own_supplementary_programme_not_general_school_or_degree'
        if not row.eligible:
            return 'previously_held_programme_or_physical_role_remains_held'
        if row.education_group_original == 'preschool':
            return 'developmental_courses_do_not_prove_kindergarten_absence_keep_with_unverified_programme'
        if row.education_group_original in {'school','specialized_non_general_school'}:
            return 'explicit_grades_or_comprehensive_official_name_preserve_general_school'
        return 'university_department_or_building_keep_degree_proxy_not_child_training_inferred_from_parent'
    selected['bounded_family_review'] = selected.apply(review, axis=1)
    selected['review_scope'] = 'all_saved_names_and_raw_tags_read_not_current_operation_or_licence_check'
    selected.reset_index().to_parquet(a.output/'whole_family_review.parquet',index=False)
    selected.reset_index()[['provider_id','name','tags_json','education_group_original','previously_eligible','eligible','programme_mismatch_reason','bounded_family_review']].to_csv(a.output/'whole_family_review.csv',index=False)
    newly = before.eligible & ~after.eligible
    after[newly].reset_index().to_parquet(a.output/'newly_held_points.parquet',index=False)
    summaries=[]
    for family in ['school_general','preschool','vocational_education','higher_education']:
        oldroute = pd.read_parquet(a.routes_before/f'{family}.parquet')
        held_ids=set(after.index[newly & before.service_code.eq(family)])
        exposed=oldroute[oldroute.selected_provider_id.isin(held_ids)].copy()
        exposed.to_parquet(a.output/f'old_selected_{family}.parquet',index=False)
        summary={'family':family,'newly_held_points':len(held_ids),'selected_origins':len(exposed),
                 'selected_positive_population_origins':int(exposed.population.gt(0).sum()),
                 'selected_external_np_origins':int((exposed.selected_provider_source_record_id.notna()&exposed.origin_id.ne(exposed.selected_provider_source_record_id)).sum())}
        if a.strict_stars_before:
            strict=pd.read_parquet(a.strict_stars_before)
            summary['old_strict_centres_with_exposed_own_origin']=int(strict.centre_settlement_id.isin(exposed.origin_id).sum())
        if a.routes_after and (a.routes_after/f'{family}.parquet').exists():
            newroute=pd.read_parquet(a.routes_after/f'{family}.parquet')
            if newroute.selected_provider_id.isin(held_ids).any():
                raise ValueError(f'Held provider remains selected: {family}')
        summaries.append(summary)
    oldnp,newnp=[pd.read_parquet(root/'np_supply.parquet') for root in [a.before,a.after]]
    keys=lambda frame:set(map(tuple,frame[['source_record_id','service_code','source_pool']].to_numpy()))
    summary={'before_source_rows':len(before),'after_source_rows':len(after),'raw_identity_columns_exact':IDENTITY,
             'whole_family_candidates_reviewed':len(selected),'review_conclusions':selected.bounded_family_review.value_counts().to_dict(),
             'newly_held_current_points':int(newly.sum()),'newly_held_by_service':before.loc[newly,'service_code'].value_counts().to_dict(),
             'route_exposure':summaries,'np_supply_keys_removed':[list(k)for k in sorted(keys(oldnp)-keys(newnp))],
             'np_supply_keys_added':[list(k)for k in sorted(keys(newnp)-keys(oldnp))],
             'observed_journeys':0,'absence_of_school_or_preschool_in_np_established':False}
    historical_before=pd.read_parquet(a.before/'physical_sites_2021.parquet')
    historical_after=pd.read_parquet(a.after/'physical_sites_2021.parquet')
    removed=historical_before[~historical_before.provider_id.isin(historical_after.provider_id)].copy()
    removed['revised_programme_reason']=[programme_mismatch_reason(g,n,t) for g,n,t in
                                        zip(removed.education_group_original,removed['name'],removed.tags_json)]
    removed['raw_historical_source_preserved_in_frozen_inputs']=True
    removed.to_parquet(a.output/'historical_physical_subset_removed_programmes.parquet',index=False)
    removed[['provider_id','name','tags_json','service_code','eligible','revised_programme_reason']].to_csv(
        a.output/'historical_physical_subset_removed_programmes.csv',index=False)
    summary['historical_2021_physical_subset_rows_before']=len(historical_before)
    summary['historical_2021_physical_subset_rows_after']=len(historical_after)
    summary['historical_2021_removed_physical_rows']=len(removed)
    summary['historical_2021_removed_previously_eligible_by_family']=removed.loc[removed.eligible,'service_code'].value_counts().to_dict()
    summary['historical_source_raw_rows_not_deleted']=True
    summary['input_sha256']={}
    for path in [before_path,after_path]:
        with path.open('rb')as stream:summary['input_sha256'][str(path)]=hashlib.file_digest(stream,'sha256').hexdigest()
    (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
