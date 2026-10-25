#!/usr/bin/env python3
"""Quick strict-subset diagnostic after replacing an independently rerouted school layer.

Other selected outcomes are retained verbatim from the earlier main scenario.
This computes no complete functional-star counts and does not approve an old
number of groups. Every new pair is checked against an independent pivot rule.
"""
import argparse
import json
from pathlib import Path
import sys
import hashlib
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent))
from screens import canonical,with_admission
from fast_strict_sensitivity import strict_only,rescreen_main_edges
from verify_centre_subset import expected_pairs,verify,LIMITS
from reroute_corrected import changed_rows
from hierarchy import canonical_edges
from lower_profile_quality import part_inventory


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ['old-main-edges','school-routes','old-school-routes','reference','endpoints','baseline-scenarios','output']:
        p.add_argument('--'+flag,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Choose a new diagnostic output directory')
    a.output.mkdir(parents=True)
    inputs=[a.old_main_edges,a.school_routes,a.old_school_routes,a.reference,a.endpoints]
    before={str(x):sha(x) for x in inputs}
    reference=pd.read_parquet(a.reference);endpoints=pd.read_parquet(a.endpoints)
    old=pd.read_parquet(a.old_main_edges)
    new_school=pd.read_parquet(a.school_routes)
    school=with_admission(canonical(new_school,reference),'school','school_general','daily_20_school30_wb',30.,
        'dated_SP42_general_school_transport_stage_unknown_scenario')
    edges=pd.concat([old[old.service_family.ne('school')],school],ignore_index=True,sort=False)
    if len(edges)!=len(old):raise ValueError('School replacement changed origin/family universe')
    changed,counts=changed_rows(pd.read_parquet(a.old_school_routes),new_school)
    changed.to_parquet(a.output/'changed_school_choices_vs_previous.parquet',index=False,compression='zstd')
    normalized=canonical_edges(edges)
    admitted=normalized[normalized.l0_admitted]
    identities=sorted(map(tuple,admitted[['origin_id','service_family','provider_key']].astype(str).to_numpy()))
    identity_sha=hashlib.sha256(json.dumps(identities,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    unique=admitted[['service_family','provider_key']].drop_duplicates()
    classified,_=part_inventory(reference)
    classified=classified.dropna(subset=['source_record_id']).set_index('source_record_id')
    base=(classified.analysis_origin.fillna(False)&classified.population_2021.gt(0)
          &classified.part_status.eq('unmarked_whole_place_record'))
    ordinary=classified.population_role.eq('ordinary_settlement_record')&classified.budget_population_credit.fillna(False)
    external_ids=set(classified.index[base&ordinary])
    centre_ids=set(classified.index[base&(ordinary|classified.population_role.eq('external_context_nonadditive'))])
    external=admitted[admitted.service_family.isin(['medical_basic','school','grocery'])
        & admitted.provider_settlement_id.notna() & admitted.origin_id.ne(admitted.provider_settlement_id)
        & admitted.origin_id.isin(external_ids)]
    daily=set(external.provider_settlement_id)&centre_ids
    coverage=[]
    for family,g in normalized[normalized.service_family.isin(['medical_basic','school','grocery'])].groupby('service_family'):
        coverage.append({'service_family':family,'all_origin_records':len(g),'admitted_records':int(g.l0_admitted.sum()),
            'admitted_known_np_provider':int((g.l0_admitted&g.provider_settlement_id.notna()).sum()),
            'admitted_unknown_np_physical_provider':int((g.l0_admitted&g.provider_settlement_id.isna()&g.provider_site_id.notna()).sum()),
            'far_or_unknown_records':int((~g.l0_admitted).sum())})
    aggregate={'method':'direct grouping of every corrected admitted choice; no territorial geometry recomputed',
        'admitted_direct_service_links':len(admitted),'functional_stars':len(unique),
        'known_np_centre_stars':int(admitted.provider_settlement_id.nunique()),
        'known_np_functional_stars':int(unique.provider_key.str.startswith('np:').sum()),
        'unknown_np_physical_functional_stars':int(unique.provider_key.str.startswith('site:').sum()),
        'known_daily_centres_with_positive_whole_external_core_members':len(daily),
        'core_identity_and_admission_coverage':coverage,'direct_choice_semantic_sha256':identity_sha,
        'all_strict_geometry_and_complete_national_star_tables_recomputed':False}
    (a.output/'direct_semantic_control.json').write_text(json.dumps(aggregate,ensure_ascii=False,indent=2)+'\n')
    del normalized,admitted,identities,unique,classified,external
    results={}
    for sid,limits in LIMITS.items():
        scoped=rescreen_main_edges(edges,sid)
        tables,summary=strict_only(scoped,reference,endpoints)
        members=tables['strict_three_core_memberships']
        independent=verify(expected_pairs(edges,reference,limits),members)
        previous=pd.read_parquet(a.baseline_scenarios/sid/'strict_three_core_memberships.parquet')
        old_pairs=set(zip(previous.origin_id,previous.centre_settlement_id))
        new_pairs=set(zip(members.origin_id,members.centre_settlement_id))
        target=a.output/sid;target.mkdir()
        for name,table in tables.items():table.to_parquet(target/(name+'.parquet'),index=False,compression='zstd')
        changes=pd.DataFrame([{'origin_id':o,'centre_settlement_id':c,'change':'removed'} for o,c in sorted(old_pairs-new_pairs)]
             +[{'origin_id':o,'centre_settlement_id':c,'change':'added'} for o,c in sorted(new_pairs-old_pairs)],
             columns=['origin_id','centre_settlement_id','change'])
        changes.to_parquet(target/'membership_changes_vs_previous.parquet',index=False,compression='zstd')
        summary.update(independent_check=independent,previous_pairs=len(old_pairs),
                       removed_pairs=len(old_pairs-new_pairs),added_pairs=len(new_pairs-old_pairs))
        (target/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        results[sid]=summary
        print(json.dumps({'scenario':sid,'new_pairs':len(new_pairs),'new_centres':independent['centres'],
                          'removed_pairs':len(old_pairs-new_pairs),'added_pairs':len(new_pairs-old_pairs)}),flush=True)
    if before!={str(x):sha(x) for x in inputs}:raise ValueError('Input changed during strict diagnostic')
    (a.output/'summary.json').write_text(json.dumps({'scope':'strict_subset_only_no_broad_functional_counts',
        'school_changes_vs_previous':counts,'input_sha256':before,'scenarios':results,
        'code_sha256':sha(Path(__file__))},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
