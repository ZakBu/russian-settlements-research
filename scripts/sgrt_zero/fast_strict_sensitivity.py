#!/usr/bin/env python3
"""Repeat only the strict three-core subset under changed travel scenarios.

Prefiltering removes centres that mathematically cannot meet the strict rule.
It does not calculate nationwide functional-star counts or a new full partition.
Saved main daily edges retain the original selected directions before screening.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent))
from centre_stars import build_centre_stars, CORE
from hierarchy import canonical_edges
from screens import SCENARIOS, with_admission


def strict_only(edges, reference, endpoints=None):
    """Exactly preserve full-build strict groups, without constructing weak stars.

    A strict centre necessarily has self-selected supply for all three core
    families and at least one external origin selecting the same three. This
    necessary prefilter deliberately does not infer positivity/identity quality;
    the full builder still applies those conditions on the retained candidates.
    """
    canonical = canonical_edges(edges)
    core = canonical[canonical.service_family.isin(CORE)]
    admitted = core[core.l0_admitted & core.provider_settlement_id.notna()]
    counts = admitted.groupby(['origin_id','provider_settlement_id']).service_family.nunique()
    triples = counts[counts.eq(len(CORE))].reset_index(name='core_count')
    own = set(triples.loc[triples.origin_id.eq(triples.provider_settlement_id),'provider_settlement_id'])
    external = set(triples.loc[triples.origin_id.ne(triples.provider_settlement_id),'provider_settlement_id'])
    possible = own & external
    if possible:
        retained = canonical[canonical.provider_settlement_id.isin(possible)].copy()
    else:
        # Retain one real scenario-labelled row, explicitly not admitted, to
        # preserve the builder's empty schemas without inventing a provider.
        retained = core.iloc[:1].copy()
        if retained.empty:
            retained = canonical.iloc[:1].copy()
        if retained.empty:
            raise ValueError('Supply at least one original scenario row even when no links are admitted')
        retained['l0_admitted'] = False
    tables, _ = build_centre_stars(retained,reference,endpoints)
    output = {name:tables[name] for name in ['strict_three_core_stars','strict_three_core_memberships']}
    stars = output['strict_three_core_stars'];members = output['strict_three_core_memberships']
    # Remove broad-star context totals: the necessary prefilter is exact for
    # strict membership, not for every weak/parcel-only surrounding record.
    keep = ['star_id','centre_settlement_id','centre_name','centre_region',
        'centre_in_analysis_origin','centre_population_is_nonadditive_context',
        'centre_own_selected_core_family_count','centre_own_all_three_core_confirmed',
        'centre_unmarked_whole_record','centre_positive_population_known',
        'strict_external_member_count','strict_member_count','strict_geodesic_diameter_km',
        'strict_population_2021_credited_sum','any_strict_coordinate_review',
        'any_strict_road_endpoint_review','strict_school_stage_unknown_records',
        'strict_road_component_quality_unknown','strict_any_component_lt100_diagnostic']
    output['strict_three_core_stars'] = stars[keep].copy()
    stars = output['strict_three_core_stars']
    summary = dict(scenario_id=str(canonical.scenario_id.iloc[0]),
        computation_scope='strict_three_core_subset_only_not_full_functional_star_counts',
        original_daily_edge_rows=len(canonical), original_core_edge_rows=len(core),
        necessary_condition_candidate_centres=len(possible),
        retained_original_edge_rows=len(retained),
        strict_three_core_model_screened_stars=len(stars),
        strict_three_core_external_positive_whole_records=int(members.member_role.eq('direct_surroundings').sum()),
        strict_full_build_equivalence_basis='necessary_same_centre_three_core_self_and_external_origin_prefilter',
        optional_parcel_family_not_used_by_strict_rule=True,
        no_full_functional_star_counts_computed=True,
        not_a_complete_exclusive_sgrt_partition=True,
        observed_flow_count=0)
    return output,summary


def rescreen_main_edges(main_edges, scenario):
    """Apply the existing screen to saved selected outcomes, without rerouting."""
    cfg=SCENARIOS[scenario]
    frames=[]
    for family in CORE:
        frame=main_edges[main_edges.service_family.eq(family)]
        if frame.empty:raise ValueError('Saved main outcomes lack core family: '+family)
        limit=30. if family=='medical_basic' else cfg['school_minutes'] if family=='school' else cfg['retail_minutes']
        code={'medical_basic':'medical_basic_primary','school':'school_general','grocery':'daily_grocery'}[family]
        rule=('dated_SP42_rural_primary_care_transport_scenario' if family=='medical_basic' else
            'dated_SP42_general_school_transport_stage_unknown_scenario' if family=='school' else
            'author_selected_car_minutes_sensitivity_not_regulation_or_empirical_trip_fit')
        frames.append(with_admission(frame,family,code,scenario,limit,rule))
    return pd.concat(frames,ignore_index=True)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4<<20),b''):h.update(block)
    return h.hexdigest()


def run(main_edges_path,reference_path,output,scenarios,endpoints_path=None):
    inputs=[main_edges_path,reference_path,*([endpoints_path] if endpoints_path else [])]
    fingerprints={str(p):digest(p) for p in inputs}
    edges=pd.read_parquet(main_edges_path);reference=pd.read_parquet(reference_path)
    endpoints=pd.read_parquet(endpoints_path) if endpoints_path else None
    output.mkdir(parents=True,exist_ok=True)
    result={}
    for sid in scenarios:
        tables,summary=strict_only(rescreen_main_edges(edges,sid),reference,endpoints)
        target=output/sid;target.mkdir(parents=True,exist_ok=True)
        for name,frame in tables.items():frame.to_parquet(target/(name+'.parquet'),index=False,compression='zstd')
        cfg=SCENARIOS[sid]
        summary['travel_limits_minutes']={'medical_basic':30.,'school':cfg['school_minutes'],'grocery':cfg['retail_minutes']}
        summary['input_sha256']=fingerprints
        (target/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        result[sid]=summary
        print(json.dumps(summary,ensure_ascii=False),flush=True)
    if any(digest(Path(p))!=value for p,value in fingerprints.items()):raise RuntimeError('Input changed during sensitivity calculation')
    manifest={'scenarios':result,'source_inputs_unchanged':True,
        'computation_scope':'strict_subset_only',
        'code_sha256':{Path(__file__).name:digest(Path(__file__)),
                       'centre_stars.py':digest(Path(__file__).with_name('centre_stars.py'))}}
    (output/'fast_strict_sensitivity_summary.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--main-edges',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--endpoints',type=Path)
    p.add_argument('--scenarios',nargs='+',choices=sorted(SCENARIOS),default=['daily_10_school15_wb','daily_30_school30_wb'])
    a=p.parse_args();run(a.main_edges,a.reference,a.output,a.scenarios,a.endpoints)
