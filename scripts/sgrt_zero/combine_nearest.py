#!/usr/bin/env python3
"""Combine already eligible nearest tables, retaining each chosen row's provenance.

This is a dated positive-evidence union, not a new route calculation, current
inventory reconstruction, or additional independent functional channel.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ORIGIN_COLUMNS = ['source_record_id','root','name','region','lat','lon','population',
                  'population_raw','working_credit_present','credited_population_2021',
                  'road_endpoint_status','road_endpoint_accepted','snap_km','road_node_index',
                  'origin_is_additional_context','budget_population_credit','road_snapshot_utc']


def truth(series):
    return series.fillna(False).astype(str).str.lower().isin(['true','1','1.0','yes'])


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def combine(components, service_code='daily_grocery_evidence_union'):
    """Ordered (name, frame) components: local wins ties, then first component.

    Finite input costs have already passed source admission and routing. Optional
    eligible/route_eligible False flags are additionally respected. No cutoff,
    distance proxy or population weight is introduced. Rows must have identical
    ordered origin IDs and consistent immutable origin attributes.
    """
    if not components or len({name for name,_ in components}) != len(components):
        raise ValueError('Nonempty, uniquely named ordered components required')
    base = components[0][1].reset_index(drop=True)
    if 'origin_id' not in base or base.origin_id.isna().any() or not base.origin_id.is_unique:
        raise ValueError('Unique nonnull origin_id axis required')
    prepared=[];validity=[];costs=[];local_flags=[]
    for rank,(name,original) in enumerate(components):
        frame=original.reset_index(drop=True).copy()
        if 'origin_id' not in frame or not frame.origin_id.equals(base.origin_id):
            raise ValueError('Component origin axes differ; no silent join or reordering')
        for col in ORIGIN_COLUMNS:
            if col in base and col in frame and not frame[col].equals(base[col]):
                raise ValueError('Origin attribute differs between components: '+col)
        if not {'cost_minutes','service_code'}.issubset(frame):
            raise ValueError('Raw nearest cost_minutes and service_code required')
        provider_cols=[c for c in ['provider_site_id','selected_provider_id','provider_id'] if c in frame]
        if not provider_cols:
            raise ValueError('Selected provider identity column required')
        provider=frame[provider_cols[0]]
        cost=pd.to_numeric(frame.cost_minutes,errors='coerce').astype(float)
        if cost.lt(0).any():raise ValueError('Negative travel cost')
        local=truth(frame.get('known_local_supply',pd.Series(False,index=frame.index)))
        if (local & (~np.isfinite(cost)|cost.ne(0))).any():
            raise ValueError('Known-local rows require their explicit finite zero-cost input assumption')
        eligible=np.isfinite(cost)&provider.notna()
        for flag in ['eligible','route_eligible']:
            if flag in frame:eligible &= truth(frame[flag])
        frame['_union_origin_order']=np.arange(len(frame))
        frame['_union_component_rank']=rank
        frame['_union_component']=name
        frame['_union_sort_cost']=cost.where(eligible,np.inf)
        frame['_union_local_rank']=(~local).astype(int)
        frame['_union_eligible']=eligible
        prepared.append(frame);validity.append(eligible.to_numpy());costs.append(cost.to_numpy());local_flags.append(local.to_numpy())
    candidates=pd.concat(prepared,ignore_index=True,sort=False)
    ordered=candidates.sort_values(['_union_origin_order','_union_sort_cost','_union_local_rank','_union_component_rank'],kind='stable')
    chosen=ordered.drop_duplicates('_union_origin_order').sort_values('_union_origin_order').reset_index(drop=True)
    selected_component=chosen['_union_component'].where(chosen['_union_eligible'])
    valid=np.vstack(validity);numbers=np.vstack(costs)
    minimum=np.where(valid,numbers,np.inf).min(axis=0)
    selected_finite=np.isfinite(minimum)
    tie_count=((numbers==minimum)&valid).sum(axis=0)
    chosen['union_original_service_code']=chosen.service_code
    chosen['service_code']=service_code
    chosen['union_selected_component']=selected_component
    chosen['union_has_eligible_finite_cost']=selected_finite
    chosen['union_equal_minimum_component_count']=tie_count
    chosen['union_component_tie']=tie_count>1
    chosen['union_tie_rule']='known_local_then_ordered_component_priority_on_exact_equal_cost'
    chosen['union_known_local_supply_any_component']=np.vstack(local_flags).any(axis=0)
    chosen['union_component_names_json']=json.dumps([n for n,_ in components])
    chosen['union_component_cost_minutes_json']=[json.dumps({name:float(numbers[i,j]) if valid[i,j] else None for i,(name,_) in enumerate(components)},allow_nan=False) for j in range(len(base))]
    chosen['union_method']='minimum_finite_already_admitted_component_cost_whole_row_selected'
    chosen['union_source_years_harmonized']=False
    chosen['union_counts_as_independent_service_channel']=False
    chosen['known_offer_records_scope']='selected_component_only_not_deduplicated_union_inventory'
    # Canonical unconstrained fields stay untouched from the same selected row.
    # Global external minima are additional diagnostics with separate lineage.
    unconstrained=[]
    for _,frame in components:
        col='unconstrained_nearest_cost_minutes'
        unconstrained.append(pd.to_numeric(frame[col],errors='coerce').to_numpy() if col in frame else np.full(len(base),np.nan))
    external=np.vstack(unconstrained);external_safe=np.where(np.isfinite(external)&(external>=0),external,np.inf)
    ext_rank=external_safe.argmin(axis=0);ext_min=external_safe.min(axis=0)
    chosen['union_unconstrained_min_cost_minutes']=np.where(np.isfinite(ext_min),ext_min,np.nan)
    chosen['union_unconstrained_min_component']=[components[int(i)][0] if np.isfinite(v) else None for i,v in zip(ext_rank,ext_min)]
    external_ids=np.vstack([frame.get('unconstrained_nearest_provider_id',pd.Series(None,index=frame.index,dtype=object)).to_numpy(dtype=object) for _,frame in components])
    chosen['union_unconstrained_min_provider_id']=np.where(np.isfinite(ext_min),external_ids[ext_rank,np.arange(len(base))],None)
    # All-missing inputs remain unknown; never carry an excluded finite choice.
    unknown=~selected_finite
    chosen.loc[unknown,'cost_minutes']=np.nan
    chosen.loc[unknown,'union_original_service_code']=pd.NA
    if 'primary_cost_minutes' in chosen:chosen.loc[unknown,'primary_cost_minutes']=np.nan
    for col in chosen:
        if col.startswith(('selected_provider_','provider_')) or col in ['provider_id','primary_candidate_id','source_id','source_year','source_snapshot','evidence_quality','evidence_kind','location_precision']:
            chosen[col]=chosen[col].where(~unknown,pd.NA)
    if 'route_status' in chosen:chosen.loc[unknown,'route_status']='union_no_known_eligible_finite_direction'
    if 'known_local_supply' in chosen:chosen.loc[unknown,'known_local_supply']=False
    if 'zero_cost_np_assumption' in chosen:chosen.loc[unknown,'zero_cost_np_assumption']=False
    return chosen.drop(columns=[c for c in chosen if c.startswith('_union_')])


def run(component_paths,output,service_code='daily_grocery_evidence_union'):
    if output.resolve() in {path.resolve() for _,path in component_paths}:
        raise ValueError('Derived output must not overwrite a raw component')
    frames=[(name,pd.read_parquet(path)) for name,path in component_paths]
    hashes={name:{'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)} for name,path in component_paths}
    result=combine(frames,service_code)
    result['union_component_source_sha256_json']=json.dumps(hashes,sort_keys=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    result.to_parquet(output,index=False,compression='zstd')
    # Ensure no source changed while being combined.
    for name,path in component_paths:
        if sha(path)!=hashes[name]['sha256']:raise RuntimeError('Raw source changed during combination')
    selected=result.union_selected_component.value_counts(dropna=False)
    base=pd.to_numeric(frames[0][1].cost_minutes,errors='coerce').to_numpy()
    cost=pd.to_numeric(result.cost_minutes,errors='coerce').to_numpy()
    summary={'service_code':service_code,'origin_rows':len(result),'ordered_components':hashes,
             'selected_component_counts':{str(k):int(v) for k,v in selected.items()},
             'finite_union_directions':int(np.isfinite(cost).sum()),
             'known_local_any_component':int(result.union_known_local_supply_any_component.sum()),
             'known_local_selected':int(truth(result.known_local_supply).sum()) if 'known_local_supply' in result else 0,
             'equal_minimum_component_ties':int(result.union_component_tie.sum()),
             'improved_finite_cost_vs_first_component':int((np.isfinite(base)&np.isfinite(cost)&(cost<base)).sum()),
             'new_finite_direction_vs_unknown_first_component':int((~np.isfinite(base)&np.isfinite(cost)).sum()),
             'source_years_harmonized':False,'raw_components_modified':False,
             'independent_function_count':1,'output_sha256':sha(output)}
    output.with_suffix('.summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--component',action='append',required=True,metavar='NAME=PARQUET')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--service-code',default='daily_grocery_evidence_union')
    a=p.parse_args();paths=[]
    for value in a.component:
        if '=' not in value:p.error('--component must be NAME=PARQUET')
        name,path=value.split('=',1);paths.append((name,Path(path)))
    if a.output.resolve() in {path.resolve() for _,path in paths}:p.error('Derived output must not overwrite a raw component')
    run(paths,a.output,a.service_code)
