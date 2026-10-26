#!/usr/bin/env python3
"""Independent numerical checks of upper research results, without model imports.

These checks establish arithmetic consistency, not empirical SGRT identification.
The census LP deliberately relaxes foreign destinations into the outside-subject
residual: its optimum is a conservative upper bound, not a sharp identified flow.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.stats import spearmanr


def require(condition, message):
    if not condition:
        raise ValueError(message)


def census_bounds(frame):
    require(frame.population_base_source_record_id.is_unique, 'Duplicate census NP identity')
    rows=[]
    for r in frame.itertuples():
        employed=float(r.employed_age15_72)
        same=float(r.same_subject-r.same_np)
        residual=float(r.outside_np_known-same)
        unknown=float(r.unknown_workplace)
        require(np.isfinite([employed,same,residual,unknown]).all() and employed>0
                and min(same,residual,unknown)>=0 and same+residual+unknown<=employed,
                'Invalid observed census margins: '+str(r.name))
        opt=[]
        # A single external NP is inside OR outside the origin subject.
        for inside in (True,False):
            sol=linprog([-1.,-1.,-1.],bounds=[(0,same if inside else 0),
                (0,0 if inside else residual),(0,unknown)],method='highs')
            require(sol.success, 'Census LP failed: '+str(r.name))
            opt.append(-sol.fun/employed)
        upper=max(opt)
        require(np.isclose(upper,r.named_parent_share_upper_bound,rtol=0,atol=1e-12),
                'Census conservative upper mismatch: '+str(r.name))
        rejected=upper<float(r.commuting_threshold_scenario)
        require(rejected==bool(r.any_named_parent_at_threshold_ruled_out_by_2010_margin),
                'Census threshold flag mismatch: '+str(r.name))
        require(not r.observed_named_parent_identified, 'Unnamed census margin claimed as named OD')
        rows.append({'name':r.name,'employed':int(employed),'relaxed_LP_conservative_upper':upper,
                     'threshold_scenario':float(r.commuting_threshold_scenario),
                     'historical_threshold_ruled_out':rejected})
    return {'records':len(rows),'upper_bound_mismatches':0,
        'LP_scope':'conservative_relaxation_including_foreign_in_residual_not_sharp_identified_OD',
        'named_destinations_identified':0,'rows':rows}


def envelope_intersections(audit,candidates,pairs,footprints):
    require(audit.unit_id.is_unique,'Duplicate audited unit')
    for frame,columns in [(candidates,['unit_id','external_efua_id']),
                          (pairs,['origin_id','external_efua_id']),
                          (footprints,['unit_id','origin_id'])]:
        require(not frame.duplicated(columns).any(),'Duplicate envelope/footprint pair')
    lookup={key:set(g.external_efua_id) for key,g in pairs.groupby('origin_id')}
    members={key:list(g.origin_id) for key,g in footprints.groupby('unit_id')}
    expected_pairs=set(); expected_candidates={}
    for r in audit.itertuples():
        ids=members.get(r.unit_id,[])
        core=lookup.get(r.core_origin_id,set());whole=set(core)
        for oid in ids:
            whole &= lookup.get(oid,set())
        uncertainty=(r.unknown_population_records_not_assumed_positive>0
                     or r.positive_member_coordinates_unknown>0 or not r.core_coordinates_known)
        expected=len(whole) if not uncertainty and ids else 0
        require(expected==r.compatible_complete_input_envelope_count,
                'Whole-envelope intersection mismatch: '+str(r.unit_id))
        require(len(whole)==r.whole_known_positive_envelope_count,
                'Known-positive envelope count mismatch: '+str(r.unit_id))
        require(not r.external_envelope_is_independent_validation and not r.empirical_sgrt_level_assigned,
                'External input incorrectly claimed as empirical identification')
        for efua in core:
            key=(r.unit_id,efua);expected_pairs.add(key)
            expected_candidates[key]=(len(ids),sum(efua in lookup.get(oid,set()) for oid in ids),
                                      bool(efua in whole and not uncertainty and ids))
    require(set(zip(candidates.unit_id,candidates.external_efua_id))==expected_pairs,
            'Core-envelope candidate set mismatch')
    for r in candidates.itertuples():
        size,covered,complete=expected_candidates[r.unit_id,r.external_efua_id]
        require((size,covered,size-covered,complete)==(
            r.required_positive_whole_records,r.required_positive_whole_inside,
            r.required_positive_whole_outside_or_unknown,bool(r.complete_input_compatibility)),
            'Candidate whole-footprint mismatch: '+str(r.unit_id))
    return {'independent_footprint_intersections_checked':len(audit),
        'candidate_pairs_checked':len(candidates),'intersection_count_mismatches':0,
        'core_candidate_pair_mismatches':0,'candidate_member_count_mismatches':0,
        'status_counts':audit.compatibility_status.value_counts().to_dict(),
        'overlap_points':int(pairs.groupby('origin_id').size().gt(1).sum()),
        'scope':'intersection_of_published_point_envelopes_not_independent_polygon_or_flow_validation'}


def temporal_values(raw,comparison,summary):
    require(comparison.oktmo.is_unique,'Duplicate temporal territory identity')
    require(summary['first_year']==2021 and summary['last_year']==2025,
            'This independent audit covers annual 2021/2025 observations')
    selected=raw[raw.indicator_code.eq('Y48423005')
        & raw.indicator_period.eq('Январь-декабрь')
        & raw.okved2.eq('Всего по обследуемым видам экономической деятельности')]
    verified={}
    for year,suffix in [(2021,'first'),(2025,'last')]:
        annual=selected[selected.year.eq(year)]
        require(annual.oktmo.is_unique,'Duplicate raw annual total territory')
        require(annual.indicator_unit.eq('Человек').all(),'Unexpected raw workforce unit')
        values=annual.set_index('oktmo').indicator_value
        observed=comparison[comparison['workforce_numeric_'+suffix].notna()]
        expected=pd.to_numeric(observed.oktmo.map(values),errors='coerce')
        require(np.allclose(expected,observed['workforce_numeric_'+suffix],rtol=0,atol=1e-9),
                'Raw annual workforce value mismatch: '+str(year))
        verified[str(year)]=len(observed)
    both=comparison.workforce_numeric_first.notna() & comparison.workforce_numeric_last.notna()
    matched=comparison[both]
    require(len(matched)==summary['same_code_observed_both'],'Paired code count mismatch')
    rho=float(spearmanr(matched.workforce_numeric_first,matched.workforce_numeric_last).statistic)
    expected_rho=summary['recorded_partial_workforce_stability']['same_code_numeric_both']['spearman_recorded_partial_workforce_2021_2025']
    require(np.isclose(rho,expected_rho,rtol=0,atol=1e-12,equal_nan=True),'Workforce correlation mismatch')
    require(not comparison.territorial_boundary_equivalence_verified.any(),'Unverified boundary equivalence claimed')
    require(not comparison.difference_is_net_commuting.any(),'Different workforce sets claimed as commuting')
    return {'verified_actual_source_values_by_year':verified,'same_code_numeric_both':len(matched),
        'union_observed_codes':len(comparison),'observed_code_only_one_year':int((~both).sum()),
        'fraction_code_union_only_one_year':float((~both).mean()),'recorded_spearman':rho,
        'source_value_mismatches':0,'boundary_equivalence_verified_count':0,'commuting_inferred_count':0,
        'scope':'published_comparison_values_and_correlation_not_independent_scope_selection_or_boundary_verification'}


def run(results,output):
    paths={
      'census_bound_lp_check': ['census_diagnostics/buryatia_eight_np_parent_bounds.parquet'],
      'national_envelope_intersection_check': ['external_envelopes/'+n+'.parquet' for n in
         ['units_envelope_audit','unit_external_envelope_candidates','point_external_envelope_pairs','checked_positive_whole_footprints']],
      'temporal_independent_check': ['workforce/data_Y48423005_112_v20260928.parquet',
         'workforce_temporal/workforce_2021_2025_code_comparison.parquet','workforce_temporal/summary.json']}
    reports={}
    for key,relative in paths.items():
        actual=[results/name for name in relative]
        frames=[json.loads(p.read_text()) if p.suffix=='.json' else pd.read_parquet(p) for p in actual]
        function={'census_bound_lp_check':census_bounds,'national_envelope_intersection_check':envelope_intersections,
                  'temporal_independent_check':temporal_values}[key]
        report=function(*frames)
        report['input_sha256']={name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in zip(relative,actual)}
        report['audit_implementation_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        reports[key]=report
    output.mkdir(parents=True,exist_ok=True)
    for key,report in reports.items():
        (output/(key+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return reports


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    reports=run(args.results,args.output)
    print(json.dumps({name:{k:v for k,v in report.items() if k not in ['rows','input_sha256']}
                      for name,report in reports.items()},ensure_ascii=False))
