#!/usr/bin/env python3
"""Retain a routing control and overlay a new, separately completed revision.

No old route, source or control is overwritten. A revised education source
replaces source/geometry exports, while every layer keeps its actual run record.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from reroute_corrected import retain_source
from transport import sha256


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ['base','revision','output']:
        p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--services',required=True)
    a=p.parse_args()
    old=json.loads((a.base/'summary.json').read_text())
    revised=json.loads((a.revision/'summary.json').read_text())
    services=set(a.services.split(','))
    if {r['service_code'] for r in revised['services']}!=services:raise ValueError('Explicit revision layer set differs')
    if a.output.exists():raise ValueError('Choose a new overlay output')
    a.output.mkdir(parents=True)
    for source in a.base.rglob('*'):
        if not source.is_file():continue
        relative=source.relative_to(a.base)
        if relative.as_posix()=='summary.json' or relative.parts[0]=='verification':continue
        if relative.parts[:2] in [('sources','education'),('geometry_cache','education')]:continue
        if relative.parts[0] in ['nearest','changes'] and source.stem in services:continue
        retain_source(source,a.output/relative)
    for folder in ['sources/education','geometry_cache/education']:
        for source in (a.revision/folder).rglob('*'):
            if source.is_file():retain_source(source,a.output/source.relative_to(a.revision))
    for service in sorted(services):
        for folder in ['nearest','changes']:
            source=a.revision/folder/(service+'.parquet')
            retain_source(source,a.output/folder/source.name)
    retain_source(a.base/'summary.json',a.output/'provenance/pre_programme_control_summary.json')
    retain_source(a.revision/'summary.json',a.output/'provenance/programme_revision_summary.json')
    rows={r['service_code']:r for r in old['services']}
    for r in revised['services']:rows[r['service_code']]={**r,'calculation_pass':'bounded_programme_revision'}
    for r in rows.values():
        source=a.output/'nearest'/(r['service_code']+'.parquet')
        if sha256(source)!=r['output_sha256']:raise ValueError('Overlay route differs from actual run manifest')
    meta={'services':list(rows.values()),'previous_control_retained':str(a.base),
          'overlaid_classes':sorted(services),'no_source_or_geometry_overwrite':True,
          'observed_trips_validated':False,'territorial_systems_computed':False,
          'independent_forward_verification':'pending_new_full_verification',
          'source_manifest_sha256':{'base':sha256(a.base/'summary.json'),'revision':sha256(a.revision/'summary.json')},
          'code_sha256':sha256(Path(__file__)),
          'files_sha256':{str(x.relative_to(a.output)):sha256(x) for x in a.output.rglob('*') if x.is_file()}}
    (a.output/'summary.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
