#!/usr/bin/env python3
"""Compare a new educational interpretation with immutable public v1 choices.

Does not reroute or change published groups. Counts are the scope of old choices
requiring review, not the number of systems whose membership necessarily changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd

FAMILIES=('school_general','preschool','vocational_education','higher_education')
IDENTITY=['name','tags_json','source_record_id','legacy_id','current_identity_status',
    'identity_status','source_address_locality','source_address_state','lat','lon']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(bundle,revision,output):
    bundle=Path(bundle);revision=Path(revision);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    old_path=bundle/'education/source_inventory_current.parquet';new_path=revision/'source_inventory_current.parquet'
    old=pd.read_parquet(old_path).set_index('provider_id');new=pd.read_parquet(new_path).set_index('provider_id')
    if not old.index.is_unique or not new.index.is_unique or set(old.index)!=set(new.index):raise ValueError('Source provider roster changed')
    new=new.loc[old.index]
    unchanged={}
    for c in IDENTITY:
        a=old[c];b=new[c]
        same=a.eq(b)|(a.isna()&b.isna())
        unchanged[c]=int((~same).sum())
    if any(unchanged.values()):raise ValueError('Address identity or raw source changed: '+str(unchanged))
    fields=['name','service_code','eligible','supply_status','education_need_scope','programme_mismatch_reason','source_record_id']
    joined=old[fields].join(new[fields+['instructional_site_role','instructional_site_role_basis','source_operational_conflict','education_semantic_name']],lsuffix='_public',rsuffix='_revised')
    changed_mask=pd.Series(False,index=joined.index)
    for c in ['service_code','eligible','supply_status','education_need_scope','programme_mismatch_reason']:
        a=joined[c+'_public'];b=joined[c+'_revised'];changed_mask|=~(a.eq(b)|(a.isna()&b.isna()))
    changes=joined[changed_mask].reset_index();changes.to_parquet(output/'all_provider_interpretation_changes.parquet',index=False)
    changes.to_csv(output/'all_provider_interpretation_changes.csv',index=False)
    held=joined[joined.eligible_public&~joined.eligible_revised].reset_index()
    restored=joined[~joined.eligible_public&joined.eligible_revised].reset_index()
    active_keys=set(map(tuple,new.loc[new.eligible&new.source_record_id.notna(),['source_record_id','service_code']].to_numpy()))
    impact=[];selected_counts=[]
    for family in FAMILIES:
        route=pd.read_parquet(bundle/'routes/nearest'/f'{family}.parquet',columns=['origin_id','name','region','population','cost_minutes','selected_provider_id','known_local_supply','selected_provider_source_record_id'])
        route['service_code']=family
        route['origin_positive_population']=pd.to_numeric(route.population,errors='coerce').gt(0)
        targets=held.loc[held.service_code_public.eq(family),'provider_id']
        affected=route[route.selected_provider_id.isin(targets)].copy()
        affected['valid_site_evidence_still_in_same_known_np']=[(sid,family) in active_keys if pd.notna(sid) else False for sid in affected.selected_provider_source_record_id]
        impact.append(affected)
        counts=affected.groupby('selected_provider_id').agg(public_selected_origins=('origin_id','nunique'),public_selected_inhabited_origins=('origin_positive_population','sum')).reset_index().rename(columns={'selected_provider_id':'provider_id'})
        counts['service_code_public']=family;selected_counts.append(counts)
    witnesses=pd.concat(impact,ignore_index=True);witnesses.to_parquet(output/'public_routes_to_newly_held_points.parquet',index=False)
    held=held.merge(pd.concat(selected_counts,ignore_index=True),on=['provider_id','service_code_public'],how='left',validate='one_to_one')
    for c in ['public_selected_origins','public_selected_inhabited_origins']:held[c]=held[c].fillna(0).astype(int)
    held.to_parquet(output/'newly_held_provider_impacts.parquet',index=False);held.to_csv(output/'newly_held_provider_impacts.csv',index=False)
    edge=pd.read_parquet(bundle/'screens_final/daily_edges.parquet',columns=['scenario_id','service_family','provider_site_id','origin_id','l0_admitted','origin_positive_population'])
    edge=edge[edge.scenario_id.eq('daily_20_school30_wb')&edge.service_family.eq('school')&edge.l0_admitted&edge.provider_site_id.isin(set(held.provider_id))]
    memberships=pd.read_parquet(bundle/'hierarchy/daily_20_school30_wb/level0_memberships.parquet')
    affected_units=memberships.loc[memberships.origin_id.isin(edge.origin_id),'unit_id'].nunique()
    old_np=pd.read_parquet(bundle/'education/np_supply.parquet');new_np=pd.read_parquet(revision/'np_supply.parquet')
    keys=lambda d:set(map(tuple,d[['source_record_id','service_code','source_pool']].to_numpy()))
    groups=[]
    for family in FAMILIES:
        w=witnesses[witnesses.service_code.eq(family)]
        groups.append({'family':family,'newly_held_old_eligible_points':int(held.service_code_public.eq(family).sum()),
            'chosen_newly_held_points':w.selected_provider_id.nunique(),'old_route_origins':w.origin_id.nunique(),
            'old_route_inhabited_origins':w.loc[w.origin_positive_population,'origin_id'].nunique(),
            'within30_origins':w.loc[w.cost_minutes.le(30),'origin_id'].nunique(),
            'within90_origins':w.loc[w.cost_minutes.le(90),'origin_id'].nunique(),
            'within90_inhabited_origins':w.loc[w.cost_minutes.le(90)&w.origin_positive_population,'origin_id'].nunique(),
            'known_np_other_valid_site_evidence_remains_origins':w.loc[w.valid_site_evidence_still_in_same_known_np,'origin_id'].nunique()})
    summary={'public_source_rows':len(old),'reassessed_source_rows':len(new),'address_and_raw_source_changed_rows':unchanged,
        'public_eligible_points':int(old.eligible.sum()),'revised_eligible_points':int(new.eligible.sum()),
        'changed_interpretation_rows':len(changes),'newly_held_old_eligible_points':len(held),'restored_points':len(restored),
        'public_route_impacts':groups,'main_l0_admitted_school_origins_requiring_reselection':edge.origin_id.nunique(),
        'main_l0_admitted_inhabited_school_origins_requiring_reselection':edge.loc[edge.origin_positive_population,'origin_id'].nunique(),
        'old_level_zero_units_containing_these_origins':int(affected_units),
        'this_does_not_establish_changed_group_membership':True,
        'np_supply_keys_removed':[list(k) for k in sorted(keys(old_np)-keys(new_np))],
        'np_supply_keys_added':[list(k) for k in sorted(keys(new_np)-keys(old_np))],
        'public_inventory_sha256':sha(old_path),'revision_inventory_sha256':sha(new_path),'comparison_code_sha256':sha(__file__)}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True,type=Path);p.add_argument('--revision',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();run(a.bundle,a.revision,a.output)
