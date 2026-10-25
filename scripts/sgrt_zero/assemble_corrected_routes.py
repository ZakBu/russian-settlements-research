#!/usr/bin/env python3
"""Assemble an explicit routing overlay from two immutable correction passes.

The second pass replaces grocery only. Other commerce classes retain the first
pass: their original offer fields must be independently shown unchanged.
"""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent))
from reroute_corrected import EDUCATION, COMMERCE, retain_source, changed_rows
from transport import sha256
from combine_nearest import run as combine_run


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ['bundle','first-pass','grocery-pass','output']:
        p.add_argument('--'+flag,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Final overlay must use a new output directory')
    check=a.grocery_pass/'unaffected_commerce_offer_pool_check.json'
    checks=json.loads(check.read_text())
    if len(checks)!=10 or not all(x.get('all_original_fields_exact') for x in checks.values()):
        raise ValueError('Missing proof that five other commerce offer pools are unchanged')
    a.output.mkdir(parents=True)
    results=[]
    first=json.loads((a.first_pass/'summary.json').read_text())
    second=json.loads((a.grocery_pass/'summary.json').read_text())
    metadata={x['service_code']:x for x in first['services']}
    metadata.update({x['service_code']:x for x in second['services']})
    for service in EDUCATION+COMMERCE:
        origin=a.grocery_pass if service=='daily_grocery' else a.first_pass
        source=origin/'nearest'/(service+'.parquet')
        if sha256(source)!=metadata[service]['output_sha256']:raise ValueError('Routed table checksum differs: '+service)
        retain_source(source,a.output/'nearest'/source.name)
        retain_source(origin/'changes'/source.name,a.output/'changes'/source.name)
        results.append({**metadata[service],'calculation_pass':'assortment_grocery' if service=='daily_grocery' else 'first_semantic_pass'})
    for role,origin in [('education',a.first_pass),('commerce',a.grocery_pass)]:
        for folder in ['sources','geometry_cache']:
            for source in (origin/folder/role).glob('*'):
                if source.is_file():retain_source(source,a.output/folder/role/source.name)
    for name,origin in [('first_pass',a.first_pass),('grocery_pass',a.grocery_pass)]:
        retain_source(origin/'summary.json',a.output/'provenance'/(name+'.json'))
    retain_source(check,a.output/'provenance'/check.name)
    # Preserve raw directed graph evidence; aliases expose the same checked
    # component size to downstream quality checks without reinterpreting it.
    quality_source=a.first_pass/'endpoint_network_quality.parquet'
    quality=pd.read_parquet(quality_source)
    quality['audit_component_size']=quality.verified_component_node_count
    quality.to_parquet(a.output/'endpoint_inventory.parquet',index=False,compression='zstd')
    combine_run([('osm_grocery_2021',a.output/'nearest/daily_grocery.parquet'),
                 ('current_food_host_2026',a.bundle/'routes/nearest/daily_grocery_current_retail_host.parquet')],
                a.output/'derived_nearest/daily_grocery_evidence_union.parquet')
    old=pd.read_parquet(a.bundle/'derived_nearest/daily_grocery_evidence_union.parquet')
    new=pd.read_parquet(a.output/'derived_nearest/daily_grocery_evidence_union.parquet')
    delta,counts=changed_rows(old,new)
    delta.to_parquet(a.output/'changes/daily_grocery_evidence_union.parquet',index=False,compression='zstd')
    manifest={'services':results,'source_bundle':str(a.bundle),'observed_trips_validated':False,
              'territorial_systems_computed':False,'grocery_union_changed_origins_vs_v1':len(delta),
              'grocery_union_change_fields':counts,'old_bundle_modified':False,
              'endpoint_quality_source_sha256':sha256(quality_source),
              'endpoint_quality_sha256':sha256(a.output/'endpoint_inventory.parquet'),
              'retained_source_scope':'education first pass; commerce assortment second pass; five other commerce route tables first pass with exact unchanged offer-pool proof',
              'files_sha256':{str(f.relative_to(a.output)):sha256(f) for f in sorted(a.output.rglob('*')) if f.is_file()},
              'assembly_code_sha256':sha256(Path(__file__))}
    (a.output/'summary.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
