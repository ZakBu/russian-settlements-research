"""Reconstruct pinned public Saratov sources and upload them to an empty draft.

Only small JSON provenance is committed. Reader extracts and water geometry are
re-fetched from the recorded public URLs and must match every original SHA.
No input source is silently substituted; publication remains a separate step.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import urllib.request
import sys
import zipfile

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
REPOSITORY='ZakBu/russian-settlements-research'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify(path,spec):
    if Path(path).stat().st_size!=spec['bytes'] or sha(path)!=spec['sha256']:
        raise ValueError('Frozen asset differs from pinned size/SHA')

def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def check_archive(archive,manifest):
    verify(archive,manifest['archive'])
    expected={r['path']:r for r in manifest['files']}
    if len(expected)!=len(manifest['files']):raise ValueError('Duplicate source members')
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!=set(expected):
            raise ValueError('Archive source members differ from pinned manifest')
        for name,spec in expected.items():
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('Unsafe source path')
            value=z.read(name)
            if len(value)!=spec['bytes'] or hashlib.sha256(value).hexdigest()!=spec['sha256']:
                raise ValueError('Frozen source bytes differ: '+name)
    return {'files_compared':len(expected),'all_archive_and_member_bytes_verified':True}


def upload(archive,manifest_path,output):
    manifest=json.loads(manifest_path.read_text());facts=check_archive(archive,manifest)
    if archive.stat().st_size>1_000_000:raise ValueError('Bootstrap must stay below the small Git file cap')
    tag=manifest['release_tag']
    row=json.loads(subprocess.check_output(['gh','api',f'repos/{REPOSITORY}/releases/tags/{tag}'],text=True))
    if not row.get('draft') or row.get('assets'):raise ValueError('An existing empty draft is required; no overwrite')
    subprocess.run(['gh','release','upload',tag,'--repo',REPOSITORY,str(archive),str(manifest_path)],check=True)
    row=json.loads(subprocess.check_output(['gh','api',f'repos/{REPOSITORY}/releases/{row["id"]}'],text=True))
    expected={p.name:(p.stat().st_size,'sha256:'+sha(p)) for p in (archive,manifest_path)}
    if not row.get('draft') or {a['name']:(a['size'],a.get('digest')) for a in row['assets']}!=expected:
        raise ValueError('Uploaded frozen-source assets differ; release remains unpublished')
    write(output,{'release_id':row['id'],'release_tag':tag,'draft':True,**facts,
        'assets':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in (archive,manifest_path)]})


def reconstruct(recipe_path,folder):
    from scripts.sgrt_saratov.generalized_maps import fetch_water
    recipe=json.loads(Path(recipe_path).read_text());folder=Path(folder)
    if folder.exists():raise ValueError('Use a fresh bootstrap working directory')
    files=folder/'files';files.mkdir(parents=True)
    for spec in recipe['readers']:
        target=files/spec['path'];target.parent.mkdir(parents=True,exist_ok=True)
        request=urllib.request.Request(spec['url'],headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(request,timeout=180) as source,target.open('wb') as output:
            count=0
            while block:=source.read(1<<16):
                count+=len(block)
                if count>spec['bytes']:raise ValueError('Public reader changed: '+spec['path'])
                output.write(block)
        verify(target,spec)
    water_manifest=REPO/recipe['water_source_manifest']
    water=json.loads(water_manifest.read_text())
    fetch_water(water['requested_bounds_wgs84'],files/'maps/water_source',water['tile_zoom'],water_manifest)
    # Preserve the original frozen source metadata. The new retrieval report is
    # separate; its current clock is not a substitute for the original snapshot.
    for relative,git_path in recipe['metadata_files'].items():
        target=files/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/git_path,target)
    for spec in recipe['files']:verify(files/spec['path'],spec)
    archive=folder/'saratov-frozen-inputs.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for spec in recipe['files']:
            info=zipfile.ZipInfo(spec['path'],date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,(files/spec['path']).read_bytes(),compresslevel=6)
    manifest={k:recipe[k] for k in ('schema','release_tag','scope','files')}
    manifest['archive']={'asset':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive)}
    path=folder/'manifest.json';write(path,manifest);check_archive(archive,manifest)
    return archive,path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path)
    p.add_argument('--manifest',type=Path)
    p.add_argument('--recipe',type=Path,default=REPO/'references/provenance/saratov_frozen_input_recipe_20261029.json')
    p.add_argument('--workdir',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    if a.workdir:a.archive,a.manifest=reconstruct(a.recipe,a.workdir)
    if not a.archive or not a.manifest:p.error('Use --workdir to reconstruct or provide --archive and --manifest')
    if a.check_only:write(a.output,check_archive(a.archive,json.loads(a.manifest.read_text())))
    else:upload(a.archive,a.manifest,a.output)

if __name__=='__main__':main()
