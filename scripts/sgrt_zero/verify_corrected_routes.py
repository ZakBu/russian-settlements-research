#!/usr/bin/env python3
"""Independent forward-search checks of corrected national service routing.

One changed and one unchanged origin per service are selected deterministically.
The forward search visits every eligible provider seed; it checks the actual
minimum on the frozen graph, not real travel, institution status or boundaries.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent))
from transport import (prepare_provider_rows, reuse_prepared_geometry,
                       independent_nearest_samples, load_graph, sha256)
from reroute_corrected import EDUCATION, COMMERCE, verify_cache


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ['bundle','education','commerce','education-cache','commerce-cache','graph-dir','routes']:
        p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--services', help='Comma-separated classes to verify; default verifies all10 classes')
    a=p.parse_args()
    ep=pd.read_parquet(a.bundle/'routes/endpoints.parquet')
    graph=load_graph(a.graph_dir)
    from scipy.sparse.csgraph import connected_components
    _, labels = connected_components(graph, directed=True, connection='weak')
    sizes = np.bincount(labels)
    nodes = pd.to_numeric(ep.road_node_index, errors='coerce')
    good = ep.road_endpoint_accepted.fillna(False) & nodes.notna() & nodes.ge(0) & nodes.lt(graph.shape[0])
    inventory = ep[[c for c in ['source_record_id','origin_id','name','region','road_node_index','snap_km','road_endpoint_accepted','weak_component'] if c in ep]].copy()
    inventory['verified_component_id'] = pd.Series(pd.NA, index=ep.index, dtype='Int64')
    inventory['verified_component_node_count'] = pd.Series(pd.NA, index=ep.index, dtype='Int64')
    inventory['verified_road_out_degree'] = pd.Series(pd.NA, index=ep.index, dtype='Int64')
    inventory['verified_road_in_degree'] = pd.Series(pd.NA, index=ep.index, dtype='Int64')
    idx=nodes.loc[good].to_numpy(dtype=np.int64)
    inventory.loc[good,'verified_component_id']=labels[idx]
    inventory.loc[good,'verified_component_node_count']=sizes[labels[idx]]
    inventory.loc[good,'verified_road_out_degree']=np.diff(graph.indptr)[idx]
    inventory.loc[good,'verified_road_in_degree']=np.asarray((graph != 0).sum(axis=0)).ravel()[idx]
    inventory['small_component_under_100_nodes']=inventory.verified_component_node_count.lt(100)
    inventory['small_component_is_quality_risk_not_proven_unreachable']=True
    inventory.to_parquet(a.routes/'endpoint_network_quality.parquet',index=False,compression='zstd')
    del labels,sizes
    evidence=[]
    for domain,folder,cache_path,site,supply,services in [
        ('education',a.education,a.education_cache,'physical_sites.parquet','np_supply.parquet',EDUCATION),
        ('commerce',a.commerce,a.commerce_cache,'sites.parquet','supply.parquet',COMMERCE)]:
        if a.services:
            services=tuple(x for x in services if x in a.services.split(','))
            if not services:continue
        verify_cache(cache_path,ep)
        providers=prepare_provider_rows([(folder/site,pd.read_parquet(folder/site))],
                                       [(folder/supply,pd.read_parquet(folder/supply))],ep)
        providers=reuse_prepared_geometry(providers,pd.read_parquet(cache_path))
        for service in services:
            table=pd.read_parquet(a.routes/'nearest'/(service+'.parquet'))
            delta=pd.read_parquet(a.routes/'changes'/(service+'.parquet'))
            valid=set(ep.loc[ep.road_endpoint_accepted,'source_record_id'])
            changed=sorted(set(delta.origin_id)&valid)
            unchanged=sorted((set(table.origin_id)-set(delta.origin_id))&valid)
            samples=[]
            if changed:samples.append(changed[0])
            if unchanged:samples.append(unchanged[0])
            result=independent_nearest_samples(ep,providers,graph,{service:table},samples)
            if not result.equal_cost.all():raise ValueError('Independent forward minimum differs: '+service)
            result['sample_selection']='first_sorted_changed_and_first_sorted_unchanged_accepted_origin'
            evidence.append(result)
            print(service,len(result),flush=True)
    out=pd.concat(evidence,ignore_index=True)
    path=a.routes/'independent_forward_checks.parquet'
    out.to_parquet(path,index=False,compression='zstd')
    summary={'check':'forward_single_origin_Dijkstra_vs_reverse_multisource_all_eligible_seeds',
             'cases':len(out),'services':out.service_code.nunique(),'all_equal':bool(out.equal_cost.all()),
             'max_absolute_difference_minutes':float(out.absolute_difference_minutes.max()),
             'observed_trips_checked':False,'specific_institution_suitability_checked':False,
             'output_sha256':sha256(path),'verification_code_sha256':sha256(Path(__file__)),
             'endpoint_quality_inventory_rows':len(inventory),
             'endpoint_small_component_under100_count':int(inventory.small_component_under_100_nodes.fillna(False).sum()),
             'endpoint_network_quality_sha256':sha256(a.routes/'endpoint_network_quality.parquet')}
    (a.routes/'independent_forward_checks.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':main()
