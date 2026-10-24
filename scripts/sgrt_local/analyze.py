#!/usr/bin/env python3
"""Reconcile documented relations with a service-specific accessibility baseline.

The comparison uses already read documents, not a blind validation set. Origins
without documented service/grade demand are deliberately not assigned a zone.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from assignment import assign_nearest


def save(frame, path):
    frame.to_csv(path.with_suffix('.csv'), index=False)
    frame.to_parquet(path.with_suffix('.parquet'), index=False, compression='zstd')


def direction(value):
    return 'unknown' if pd.isna(value) else 'growth' if value > 0 else 'decline' if value < 0 else 'unchanged'


def analyze(root):
    root = Path(root)
    out = root/'analysis'; out.mkdir(parents=True, exist_ok=True)
    nodes = pd.read_parquet(root/'services/nodes.parquet')
    links = pd.read_parquet(root/'services/links.parquet')
    supply = pd.read_parquet(root/'services/supply.parquet')
    costs = pd.read_parquet(root/'roads/costs.parquet')
    assert nodes.source_record_id.is_unique
    assert set(links.origin_id) <= set(nodes.source_record_id)
    assert set(links.destination_id) <= set(nodes.source_record_id)
    assert not links.observed_flow.any()
    assert not costs.duplicated(['origin_id', 'destination_id']).any()
    links = links.merge(costs[['origin_id','destination_id','cost_minutes','network_minutes','connector_minutes']],
                        on=['origin_id','destination_id'], how='left', validate='many_to_one')
    if links.cost_minutes.isna().any():
        raise ValueError('A documented relation has no accepted recorded road cost')
    save(links, out/'documented_relations_with_costs')
    compared = links[links.service_code.ne('school_grade_unspecified')].copy()
    results=[]; all_candidates=[]; legacy=[]
    for service, observations in compared.groupby('service_code'):
        origins=nodes[nodes.source_record_id.isin(observations.origin_id)].copy()
        sites=supply[supply.service_code.eq(service)].copy()
        routes=costs[costs.origin_id.isin(origins.source_record_id)].drop(columns='provider_id',errors='ignore').merge(
            sites[['provider_id','source_record_id']].drop_duplicates(),left_on='destination_id',right_on='source_record_id',how='inner')
        routes=routes.drop(columns=['source_record_id','destination_id'])
        for allow_proxy in [False,True]:
            assignments,candidates=assign_nearest(origins,sites,routes,service_codes=[service],allow_proxy=allow_proxy)
            assignments['scenario']='known_service_only' if not allow_proxy else 'school_type_proxy_sensitivity'
            joined=observations.merge(assignments,on=['origin_id','service_code'],validate='one_to_one')
            joined['matches_documented_destination']=joined.destination_id.eq(joined.selected_provider_settlement_id)
            joined['comparison_is_blind_holdout']=False
            joined['provider_pool_is_complete']=False
            results.append(joined)
            if not allow_proxy:
                all_candidates.append(candidates)
            if allow_proxy:
                candidates=candidates.merge(nodes[['source_record_id','population_2021']],left_on='provider_settlement_id',right_on='source_record_id',how='left',validate='many_to_one')
                candidates['legacy_population_score']=candidates.population_2021*np.exp(-np.log(2)*candidates.cost_minutes/30)
                selected=candidates.sort_values(['origin_id','legacy_population_score','cost_minutes','provider_id'],ascending=[True,False,True,True]).groupby('origin_id',sort=False).head(1)
                selected=selected[['origin_id','provider_settlement_id','cost_minutes','legacy_population_score']]
                selected=observations.merge(selected,on='origin_id',validate='one_to_one')
                selected['matches_documented_destination']=selected.destination_id.eq(selected.provider_settlement_id)
                selected['scenario']='diagnostic_population_weight_with_school_type_proxies_exp30'
                selected['is_validated_behavioral_model']=False
                legacy.append(selected)
    comparisons=pd.concat(results,ignore_index=True)
    save(comparisons,out/'service_comparison')
    save(pd.concat(all_candidates,ignore_index=True),out/'known_service_candidates')
    old=pd.concat(legacy,ignore_index=True)
    save(old,out/'population_weight_counterexample')

    units=[]
    # Four selected full school territories, plus the explicitly reported FAP
    # pair. These overlap and must never be summed as disjoint SGRTs.
    for (function,dest),group in links.groupby(['function','destination_id']):
        center=nodes.set_index('source_record_id').loc[dest]
        member_ids=set(group.origin_id)|{dest}
        members=nodes[nodes.source_record_id.isin(member_ids)]
        periphery=members[members.source_record_id.ne(dest)]
        row={'function':function,'center_id':dest,'center_name':center['name'],
             'member_count':len(members),'external_member_count':len(periphery),
             'membership_basis':'selected_complete_school_territory' if function=='education' else 'provider_reported_two_village_service',
             'service_codes':'|'.join(sorted(group.service_code.unique())),
             'is_disjoint_partition':False,'is_complete_sgrt':False,
             'membership_year':2025 if function=='education' else None,
             'historical_membership_equivalence_proven':False,
             'external_max_static_car_minutes':float(group.loc[group.external,'cost_minutes'].max())}
        for year in [2002,2010,2021]:
            col=f'effective_population_{year}'
            c=center[col]
            values=periphery[col]
            credited=periphery[f'working_credit_present_{year}'].eq(True)
            known=values.notna()&credited
            p=float(values.sum()) if known.all() else np.nan
            row.update({f'center_population_{year}':float(c) if pd.notna(c) and center[f'working_credit_present_{year}'] else np.nan,
                        f'periphery_population_{year}':p,
                        f'periphery_known_records_{year}':int(known.sum()),
                        f'population_{year}':float(c+p) if pd.notna(c) and pd.notna(p) else np.nan})
        cd=row['center_population_2021']-row['center_population_2002']
        pdiff=row['periphery_population_2021']-row['periphery_population_2002']
        row['center_direction_2002_2021']=direction(cd)
        row['periphery_direction_2002_2021']=direction(pdiff)
        row['descriptive_type']='insufficient_comparable_demography' if pd.isna(cd) or pd.isna(pdiff) else 'center_'+direction(cd)+'__surroundings_'+direction(pdiff)
        row['type_is_causal_word_type']=False
        row['type_rule']='exact_sign_2002_2021_not_statistical_significance_or_economic_stability'
        units.append(row)
    unitframe=pd.DataFrame(units)
    save(unitframe,out/'documented_unit_demography')
    schools=links[links.function.eq('education')]
    external=links[links.external]
    strict=comparisons[comparisons.scenario.eq('known_service_only')]
    strict_external=strict[strict.external]
    summary={
        'status':'documented_local_functional_fragments_not_national_multilevel_sgrt',
        'nodes':len(nodes),'documented_relations':len(links),'external_documented_relations':len(external),
        'school_relations':len(schools),'fap_relations':int(links.function.eq('healthcare').sum()),
        'school_territories':schools.groupby('destination_name').origin_id.nunique().to_dict(),
        'school_grade_unspecified_relations':int(schools.service_code.eq('school_grade_unspecified').sum()),
        'explicit_service_comparisons':len(strict),'explicit_service_matches':int(strict.matches_documented_destination.sum()),
        'external_explicit_comparisons':len(strict_external),'external_explicit_matches':int(strict_external.matches_documented_destination.sum()),
        'blind_holdout':False,'complete_provider_network':False,'estimated_flow_count':0,
        'external_documented_cost_min':float(external.cost_minutes.min()),
        'external_documented_cost_max':float(external.cost_minutes.max()),
        'diagnostic_population_weight_with_proxies_matches':int(old.matches_documented_destination.sum()),
        'diagnostic_population_weight_with_proxies_rows':len(old),
        'full_functional_unit_count_not_established':True,
        'important_limits':['2025 normative school territories, 2021 static car roads and census points have different dates.',
            'Reported FAP population330 is undated and is not replaced by the 2021 census total.',
            'Capacity, school-age demand and actual journeys are unknown. Matches on known documents are not validation accuracy.',
            'No inference of local-hospital referral from the presence of 10 beds.',
            '2002–2021 population is described on selected current membership, not proof of historically unchanged functional boundaries.',
            'All known 2010 quality fields remain in nodes; 2010 is not used to give a causal type.',
            'Unspecified school grades remain unspecified; unsourced demand is not assigned to distant known providers.']}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    print(json.dumps(analyze(p.parse_args().root),ensure_ascii=False,indent=2))
