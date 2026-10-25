#!/usr/bin/env python3
"""Package new centre evidence without copying the unchanged national inputs.

Dependencies are the pinned zero-v1 release (reference, unchanged services)
and the pinned road graph; the main census release is never replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

REPO=Path(__file__).resolve().parents[2]


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def build(analysis,routes,output,commit):
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    if actual!=commit or len(commit)!=40:raise ValueError('Require exact source commit')
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True).strip():
        raise ValueError('Commit all source and context before packaging')
    if output.resolve().is_relative_to(REPO):raise ValueError('Generated data stay outside Git')
    entries={}
    for prefix,root in [('analysis',analysis),('routes',routes)]:
        for p in sorted(root.rglob('*')):
            if p.is_file():entries[prefix+'/'+p.relative_to(root).as_posix()]=p
    for folder in ['scripts/sgrt_zero','scripts/sgrt_mass','scripts/sgrt_local']:
        for p in sorted((REPO/folder).glob('*.py')):entries['reproduction/'+p.relative_to(REPO).as_posix()]=p
    for p in sorted(REPO.glob('requirements-sgrt-*.txt')):
        entries['reproduction/'+p.name]=p
    for name in ['AGENTS.md','README.md','requirements-sgrt-zero.txt','requirements-sgrt-mass.txt','requirements-sgrt-pilot.txt',
                 'sgrt/zero/CENTRE_SYSTEMS_20261025.md','research_context/current_state.json','research_context/diary/2026-10-25.md',
                 'research_context/analysis_snapshots/zero_centre_model_results_20261025.json',
                 'research_context/analysis_snapshots/centre_stars_exact_performance_20261025.json',
                 'references/sources.json','references/usage.json','research_context/primary/word_concept_extracted.txt','decisions.json']:
        entries['reproduction/'+name]=REPO/name
    files={name:{'bytes':p.stat().st_size,'sha256':sha(p)} for name,p in entries.items()}
    manifest={'release_tag':'sgrt-zero-centre-systems-20261025-v1','source_commit':commit,
              'input_release':'sgrt-zero-systems-20261025-v1','input_catalog':'data/zero_catalog_20261025.json',
              'population_default_catalog_unchanged':True,'recomputed_nearest_layers':10,
              'complete_national_exclusive_sgrt_partition':False,'observed_journeys_established':False,
              'files':files}
    output.mkdir(parents=True,exist_ok=True)
    archive=output/'centre-systems.zip'
    if archive.exists():raise FileExistsError('Do not overwrite an existing package')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4) as z:
        for name,p in entries.items():z.write(p,arcname='sgrt/centre20261025/'+name)
        z.writestr('sgrt/centre20261025/manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    for name,p in entries.items():
        if sha(p)!=files[name]['sha256']:raise RuntimeError('Source changed during packaging: '+name)
    manifest['archive']={'asset':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive)}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('Archive CRC failure')
    print(json.dumps({'files':len(files),'archive':manifest['archive']},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ['analysis','routes','output']:p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--source-commit',required=True);a=p.parse_args();build(a.analysis,a.routes,a.output,a.source_commit)
