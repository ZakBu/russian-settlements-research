"""Compare every preferred functional link before/after a school-source addition.

This version comparison is separate from a fresh single-version calculation.
It requires identical origin/function/evidence keys and unavailable-cost masks,
checks pointwise school-time monotonicity, and checks all other functions
exactly. Medians give each settlement one vote and include local-service zeroes;
no population weights or replacement of missing values are used.

Example:
  python scripts/sgrt_saratov/compare_school_addition.py \
    --baseline-root /data/saratov-v1 --updated-root /data/saratov-v2 \
    --output /data/school-addition-links.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

MEMBER=Path('physical_official/functional_links.parquet')
KEYS=['origin_id','family','evidence_scenario']


def compare_tables(baseline,updated):
    """Check the complete matched inventory, retaining missingness explicitly."""
    required=set(KEYS+['cost_minutes','population_2021'])
    for name,table in [('baseline',baseline),('updated',updated)]:
        if not required<=set(table):raise ValueError(name+' lacks required functional-link fields')
        if table.duplicated(KEYS).any() or table[KEYS].isna().any().any():
            raise ValueError(name+' has duplicate or missing functional-link identities')
    a=baseline.sort_values(KEYS).reset_index(drop=True)
    b=updated.sort_values(KEYS).reset_index(drop=True)
    try:pd.testing.assert_frame_equal(a[KEYS],b[KEYS],check_exact=True)
    except AssertionError as error:raise ValueError('Functional-link identity sets differ') from error
    school=a.family.eq('school')
    if not school.any():raise ValueError('No school outcomes to compare')
    x=a.loc[school].reset_index(drop=True);y=b.loc[school].reset_index(drop=True)
    before=x.cost_minutes.to_numpy(dtype=float);after=y.cost_minutes.to_numpy(dtype=float)
    errors=[]
    invalid=np.isinf(before)|np.isinf(after)|(before<0)|(after<0)
    if invalid.any():errors.append('Nearest-provider costs contain infinite or negative values')
    before_missing=np.isnan(before);after_missing=np.isnan(after)
    same_missing=np.array_equal(before_missing,after_missing)
    if not same_missing:errors.append('Unavailable school-cost masks differ; the fixed-missingness comparison contract is not met')
    known=np.isfinite(before)&np.isfinite(after)
    change=after[known]-before[known]
    increased=int((change>0).sum())
    if increased:errors.append('A school travel time increased despite retaining the original offers')
    try:
        pd.testing.assert_series_equal(x.population_2021,y.population_2021,check_exact=True)
        same_population=True
    except AssertionError:
        same_population=False;errors.append('School-origin population values changed')
    try:
        pd.testing.assert_frame_equal(a.loc[~school].reset_index(drop=True),b.loc[~school].reset_index(drop=True),check_exact=True)
        other_exact=True
    except AssertionError:
        other_exact=False;errors.append('At least one non-school outcome differs in a value, missingness, column or dtype')
    facts={'schema':'sgrt.saratov.school_addition_links.v1',
        'functional_link_rows':len(a),'school_rows':len(x),
        'known_before_and_after_rows':int(known.sum()),
        'unavailable_cost_rows_before':int(before_missing.sum()),
        'unavailable_cost_rows_after':int(after_missing.sum()),
        'newly_known_cost_rows':int((before_missing&~after_missing).sum()),
        'newly_unknown_cost_rows':int((~before_missing&after_missing).sum()),
        'NA_masks_identical':bool(same_missing),'school_population_values_identical':same_population,
        'increased_rows':increased,'strictly_decreased_rows':int((change<0).sum()),
        'exactly_unchanged_known_rows':int((change==0).sum()),
        'largest_decrease_minutes':float(min(0.,change.min())) if len(change) else None,
        'other_function_families':sorted(a.loc[~school,'family'].unique().tolist()),
        'other_function_rows':int((~school).sum()),'other_functions_all_columns_exact':other_exact,
        'missing_values_replaced_with_zero':False,'population_weights_used':False,
        'fixed_positive_2021_known_cost_cohort':{}}
    for scenario in sorted(x.evidence_scenario.unique()):
        left=x[x.evidence_scenario.eq(scenario)&x.population_2021.gt(0)&np.isfinite(x.cost_minutes)].sort_values('origin_id')
        right=y[y.evidence_scenario.eq(scenario)&y.population_2021.gt(0)&np.isfinite(y.cost_minutes)].sort_values('origin_id')
        same_ids=left.origin_id.tolist()==right.origin_id.tolist()
        if not same_ids:errors.append('Positive-population known-cost origin cohort differs: '+scenario)
        facts['fixed_positive_2021_known_cost_cohort'][scenario]={
            'origin_records_before':len(left),'origin_records_after':len(right),
            'same_origin_id_set':same_ids,'own_local_zeroes_included':True,
            'NP_unweighted_median_minutes_before':float(left.cost_minutes.median()) if len(left) else None,
            'NP_unweighted_median_minutes_after':float(right.cost_minutes.median()) if len(right) else None,
            'NP_unweighted_p90_minutes_before':float(left.cost_minutes.quantile(.9)) if len(left) else None,
            'NP_unweighted_p90_minutes_after':float(right.cost_minutes.quantile(.9)) if len(right) else None}
    facts['errors']=errors;facts['violations']=len(errors)
    return facts


def compare_roots(baseline_root,updated_root):
    paths=[Path(root)/MEMBER for root in [baseline_root,updated_root]]
    result=compare_tables(*[pd.read_parquet(p) for p in paths])
    result['inputs']=[{'role':role,'member':MEMBER.as_posix(),'bytes':path.stat().st_size,
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for role,path in zip(['baseline','updated'],paths)]
    result['reproduction_script']='scripts/sgrt_saratov/compare_school_addition.py'
    result['scope']='All matched preferred-inventory origins, functions and evidence scenarios; no sampling, no conditioning on external-only membership.'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root',type=Path,required=True)
    parser.add_argument('--updated-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=compare_roots(args.baseline_root,args.updated_root)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'school_rows':result['school_rows'],'increased_rows':result['increased_rows'],
        'other_function_rows':result['other_function_rows'],'violations':result['violations']},ensure_ascii=False))
    if result['violations']:raise SystemExit(1)

if __name__=='__main__':main()
