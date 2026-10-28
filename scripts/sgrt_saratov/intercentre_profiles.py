"""Direct functional relations of basic centres, without a forced hierarchy.

A centre remains a centre when a rarer need points elsewhere. All coequal
nearest alternatives survive; crossing directions do not become observed flows
or permission to merge a transitive chain into one district.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd


def build(profiles, links):
    keys=['centre_id','evidence_scenario']
    if profiles.duplicated(keys).any():raise ValueError('Centre profiles must be unique per evidence scenario')
    origins=profiles.loc[profiles.centre_in_regional_roster.eq(True),keys].rename(columns={'centre_id':'origin_id'})
    if links.duplicated(['origin_id','evidence_scenario','family']).any():raise ValueError('Repeated origin/function outcome')
    selected=origins.merge(links,on=['origin_id','evidence_scenario'],how='left',validate='one_to_many')
    if selected.family.isna().any():raise ValueError('Regional centre lacks functional outcomes')
    edges=[]
    for row in selected.itertuples(index=False):
        if not np.isfinite(row.cost_minutes):continue
        targets=json.loads(row.coequal_primary_keys_json)
        if not targets:raise ValueError('Known choice has no destination')
        if len(set(targets))!=len(targets):raise ValueError('Repeated coequal target')
        for key in sorted(targets):
            target=key[3:] if key.startswith('np:') else None
            edges.append({'origin_id':row.origin_id,'family':row.family,
                'evidence_scenario':row.evidence_scenario,'inventory_scenario':row.inventory_scenario,
                'destination_group_key':key,'destination_np_id':target,
                'cost_minutes':float(row.cost_minutes),'is_local_self':target==row.origin_id,
                'model_choice_unique':len(targets)==1,'coequal_candidate_count':len(targets),
                'actual_intercentre_flow_observed':False,'is_hierarchical_parent_assignment':False})
    e=pd.DataFrame(edges)
    summary=[]
    for (scenario,family),g in selected.groupby(['evidence_scenario','family'],sort=True):
        known=g.cost_minutes.notna();local=known&g.known_local_supply.eq(True)
        np_known=g.provider_settlement_id.notna();external=known&~local
        scope=e[e.evidence_scenario.eq(scenario)&e.family.eq(family)]
        summary.append({'evidence_scenario':scenario,'family':family,'regional_basic_centres':len(g),
            'known_local_offer':int(local.sum()),'known_external_np_choice':int((external&np_known).sum()),
            'known_external_site_np_unresolved':int((external&~np_known).sum()),
            'accessibility_unknown':int((~known).sum()),'ambiguous_choice_outcomes':int(g.ambiguous_primary.sum()),
            'external_choice_median_minutes':float(g.loc[external,'cost_minutes'].median()) if external.any() else None,
            'distinct_known_np_destinations':int(scope.destination_np_id.nunique()),
            'actual_trip_flows_established':False,'provider_counts_are_not_an_inferred_function_order':True})
    pairs=[]
    for scenario,g in e.loc[e.destination_np_id.notna()&~e.is_local_self].groupby('evidence_scenario',sort=True):
        directional={}
        for (a,b),v in g.groupby(['origin_id','destination_np_id'],sort=True):
            directional[a,b]=v
        for a,b in sorted(directional):
            if a>=b or (b,a) not in directional:continue
            ab,ba=directional[a,b],directional[b,a]
            pairs.append({'evidence_scenario':scenario,'centre_a':a,'centre_b':b,
                'a_to_b_families_json':json.dumps(sorted(ab.family.unique().tolist()),ensure_ascii=False),
                'b_to_a_families_json':json.dumps(sorted(ba.family.unique().tolist()),ensure_ascii=False),
                'all_directions_have_unique_nearest_choice':bool(ab.model_choice_unique.all() and ba.model_choice_unique.all()),
                'interpretation':'conditional_direct_cross_function_complementarity_not_observed_cooperation',
                'merge_into_one_system':False})
    pair_columns=['evidence_scenario','centre_a','centre_b','a_to_b_families_json','b_to_a_families_json',
        'all_directions_have_unique_nearest_choice','interpretation','merge_into_one_system']
    return selected,e,pd.DataFrame(summary),pd.DataFrame(pairs,columns=pair_columns)


def run(functions, output):
    functions,output=Path(functions),Path(output);output.mkdir(parents=True,exist_ok=True)
    p=pd.read_parquet(functions/'basic_centre_profiles.parquet');l=pd.read_parquet(functions/'functional_links.parquet')
    outcomes,edges,summary,pairs=build(p,l)
    for name,frame in [('centre_function_outcomes',outcomes),('direct_centre_function_edges',edges),
                       ('functional_relation_summary',summary),('cross_function_complementarity_pairs',pairs)]:
        frame.to_parquet(output/(name+'.parquet'),index=False,compression='zstd')
    report={'regional_centre_function_outcomes':len(outcomes),'direct_candidate_edges':len(edges),
        'cross_function_bidirectional_pairs':len(pairs),'actual_flows_established':False,
        'number_of_functional_levels_assigned':False,'transitive_membership_merging_performed':False}
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--functions',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.functions,a.output)))
