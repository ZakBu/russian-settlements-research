#!/usr/bin/env python3
"""Fetch pinned inputs, reproduce the local study, and build a portable release.

No credentials, publishing or Git mutation. Large national road graph remains a
versioned dependency of the earlier pilot release rather than a duplicate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/sgrt_pilot'))
from package_release import package
from economy import SOURCE_URL, SOURCE_SHA, JS_URL, JS_SHA, FNS_URL, FNS_SHA


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


def run(*args):
    print('RUN',*map(str,args),flush=True)
    subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,check=True)


def fetch(url,path,sha=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and (sha is None or digest(path)==sha):return path
    temporary=path.with_suffix(path.suffix+'.partial')
    error=None
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'sgrt-local-research/1'})
            with urllib.request.urlopen(request,timeout=90) as response,temporary.open('wb') as out:
                shutil.copyfileobj(response,out,4*1024*1024)
            if sha and digest(temporary)!=sha:raise ValueError('Downloaded source SHA256 differs: '+url)
            temporary.replace(path);return path
        except (OSError,ValueError) as e:
            error=e
            if attempt<2:time.sleep(2*(attempt+1))
    raise error


def fetch_catalog(catalog,dest,cache,patterns,profile='all'):
    command=[ROOT/'scripts/research_data.py','fetch','--catalog',catalog,'--profile',profile,'--dest',dest,'--cache',cache]
    for pattern in patterns:command+=['--match',pattern]
    run(*command)


def prepare(work):
    import pandas as pd
    deps=work/'dependencies';cache=work/'download-cache'
    wide=deps/'data/population/settlements_census_wide.parquet'
    fetch_catalog(ROOT/'data/catalog.json',deps,cache,['data/population/settlements_census_wide.parquet'],'core')
    run(ROOT/'scripts/sgrt_local/services.py','--population',wide,'--output',work/'services','--fetch')
    agprefix='research/sgrt_functional_dynamics_20261019/agriculture'
    fetch_catalog(ROOT/'data/catalog.json',deps,cache,[agprefix+'/*.csv'])
    archive=deps/agprefix
    raw=work/'economy/raw';raw.mkdir(parents=True,exist_ok=True)
    source=raw/'data_section7_112_v20250918.parquet'
    if not source.exists():
        agriculture_zip=fetch(SOURCE_URL,raw/'agriculture_source.zip')
        with zipfile.ZipFile(agriculture_zip) as bundle:
            matches=[x for x in bundle.namelist() if x.endswith('.parquet')]
            if len(matches)!=1:raise ValueError('Expected one primary agricultural Parquet')
            with bundle.open(matches[0]) as src,source.open('wb') as dst:shutil.copyfileobj(src,dst)
        agriculture_zip.unlink()
    if digest(source)!=SOURCE_SHA:raise ValueError('Agricultural source differs')
    js=fetch(JS_URL,raw/'bairamgul_app.js',JS_SHA)
    fns=fetch(FNS_URL,raw/'fns_sshr_20260925.zip',FNS_SHA)
    run(ROOT/'scripts/sgrt_local/economy.py','--agriculture-source',source,'--archive-inputs',archive,
        '--employer-js',js,'--fns-source',fns,'--accepted-population',wide,'--output',work/'economy/outputs')
    # Retain the small historical row-level evidence used by economy.py.
    target=work/'economy/archive'/agprefix
    target.mkdir(parents=True,exist_ok=True)
    for path in archive.glob('*.csv'):shutil.copy2(path,target/path.name)
    roadprefix='sgrt/pilot20261024/outputs/transport'
    fetch_catalog(ROOT/'data/pilot_catalog_20261024.json',deps,cache,
        [roadprefix+'/graph/graph_npz_parts/*.bin',roadprefix+'/route_origin_index.parquet',roadprefix+'/legacy_nodes_minimal.parquet'],'core')
    transport=deps/roadprefix
    nodes=pd.read_parquet(work/'services/nodes.parquet')
    requested=nodes[['source_record_id','name']].copy()
    requested['context_anchor']=nodes.core_fragment
    w=pd.read_parquet(wide)
    # Both the town and the village of Uchaly are context destinations, never
    # inferred functional centres. Exact IDs are pinned, not nearest names.
    extra=w[w.source_record_id_2021.str.endswith((':148722',':148824'),na=False)][['source_record_id_2021','settlement_name_2021']].rename(columns={'source_record_id_2021':'source_record_id','settlement_name_2021':'name'})
    if len(extra)!=2:raise ValueError('Uchaly context census records changed')
    extra['context_anchor']=False
    requested=pd.concat([requested,extra],ignore_index=True)
    roads=work/'roads';roads.mkdir(exist_ok=True)
    requested.to_csv(roads/'requested_nodes.csv',index=False)
    run(ROOT/'scripts/sgrt_local/roads.py','--nodes',roads/'requested_nodes.csv','--wide',wide,
        '--legacy-nodes',transport/'legacy_nodes_minimal.parquet','--road-origins',transport/'route_origin_index.parquet',
        '--graph-dir',transport/'graph','--context-km','25','--output',roads)
    # A reproducible census input snapshot avoids duplicating the complete base.
    endpoints=pd.read_parquet(roads/'road_endpoints.parquet')
    membership=pd.read_parquet(work/'economy/outputs/accepted_municipal_membership.parquet')
    ids=set(endpoints.source_record_id)|set(membership.source_record_id_2021)
    snapshot=w[w.source_record_id_2021.isin(ids)]
    inputs=work/'inputs';inputs.mkdir(exist_ok=True)
    snapshot.to_parquet(inputs/'population_snapshot.parquet',index=False,compression='zstd')
    provenance={'source_catalog':'data/catalog.json','source_population_release':'sgrt-census-population-20261022-v1',
                'full_population_sha256':digest(wide),'snapshot_records':len(snapshot),
                'snapshot_sha256':digest(inputs/'population_snapshot.parquet'),
                'not_a_replacement_for_primary_population_base':True}
    (inputs/'population_snapshot_source.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')


def from_bundle(source,work):
    """Recompute tables/figures from complete local evidence, without federal scans."""
    source=Path(source)
    manifest=json.loads((source/'checksums.json').read_text())
    for relative,expected in manifest.items():
        if digest(source/relative)!=expected:raise ValueError('Bundle input changed: '+relative)
    for folder in ['services','roads','economy','inputs']:
        shutil.copytree(source/folder,work/folder,dirs_exist_ok=True)
    population=work/'inputs/population_snapshot.parquet'
    run(ROOT/'scripts/sgrt_local/services.py','--population',population,'--output',work/'services')
    archive=work/'economy/archive/research/sgrt_functional_dynamics_20261019/agriculture'
    xmls=list((work/'economy/outputs').glob('VO_OTKRDAN*.xml'))
    if len(xmls)!=1:raise ValueError('Expected one matched original FNS XML member')
    run(ROOT/'scripts/sgrt_local/economy.py','--agriculture-source',work/'economy/raw/agriculture_source_rows.parquet',
        '--archive-inputs',archive,'--employer-js',work/'economy/raw/bairamgul_app.js',
        '--fns-source',xmls[0],'--accepted-population',population,'--output',work/'economy/outputs')


def build_package(work,tag,commit):
    # Curated payload: sources, machine-readable results and scientific figures.
    payload=work/'payload';local=payload/'sgrt/local20261024'
    if payload.exists():shutil.rmtree(payload)
    local.mkdir(parents=True)
    for folder in ['analysis','figures','inputs','roads']:
        if (work/folder).exists():shutil.copytree(work/folder,local/folder,ignore=shutil.ignore_patterns('*.log','__pycache__'))
    service=local/'services';service.mkdir()
    for path in (work/'services').iterdir():
        if path.is_file() and path.suffix in ['.csv','.parquet','.json']:shutil.copy2(path,service/path.name)
    (service/'sources').mkdir()
    for name in ['uchaly_school_2025.pdf','uchaly_fap.html','uchaly_structure.html','uchaly_news_all.html']:
        p=work/'services/sources'/name
        if p.exists():shutil.copy2(p,service/'sources'/name)
    economy=local/'economy'
    shutil.copytree(work/'economy/outputs',economy/'outputs')
    shutil.copytree(work/'economy/archive',economy/'archive')
    raw=economy/'raw';raw.mkdir()
    shutil.copy2(work/'economy/raw/bairamgul_app.js',raw/'bairamgul_app.js')
    # Retain all raw municipal observations actually used and the original XML
    # containing the employer. Entire federal files remain pinned URL/SHA inputs
    # of the full reproduction recipe, not duplicate bulk in this local bundle.
    shutil.copy2(work/'economy/outputs/agriculture_source_rows.parquet',raw/'agriculture_source_rows.parquet')
    # Citations/read scope are sufficient; do not republish entire journal HTML.
    if (work/'method/sources.json').exists():
        (local/'method').mkdir();shutil.copy2(work/'method/sources.json',local/'method/sources.json')
    for folder in ['scripts/sgrt_local','sgrt/local_systems']:
        target=local/'reproduction'/folder
        shutil.copytree(ROOT/folder,target,ignore=shutil.ignore_patterns('__pycache__'))
    helper=local/'reproduction/scripts/sgrt_pilot';helper.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'scripts/sgrt_pilot/package_release.py',helper/'package_release.py')
    shutil.copy2(ROOT/'requirements-sgrt-pilot.txt',local/'reproduction/requirements-sgrt-pilot.txt')
    (local/'README.txt').write_text('Документированные локальные системы Учалинского района.\n'
        'Текущий обзор и команды: sgrt/local_systems/README.md в GitHub.\n'
        'Нормативное прикрепление, наличие учреждения, модель времени и фактический поток разделены.\n'
        'ФНС205 — работники юридического лица, не доказанное число мест в Уральске.\n'
        'Исходники и данные здесь; большой дорожный граф — зависимость предыдущего релиза.\n'
        f'Код: {commit}\n',encoding='utf-8')
    checks={p.relative_to(local).as_posix():digest(p) for p in sorted(local.rglob('*')) if p.is_file()}
    (local/'checksums.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
    built=work/'built'
    if built.exists():shutil.rmtree(built)
    package(payload,built,tag,commit)
    original=built/'sgrt-pilot-data.zip';archive=built/'local-systems-data.zip';original.rename(archive)
    cat=json.loads((built/'pilot_catalog.json').read_text())
    cat['scientific_scope']='Documented local school/FAP systems, service-specific accessibility baseline, dated census demography, agricultural context and organisation-level employment; not nationwide multilevel SGRT.'
    cat['profiles']={'core':'Complete local study bundle','all':'Same local bundle'}
    for row in cat['files']:row['asset']=archive.name
    for obj in cat['objects'].values():obj['asset']=archive.name
    cat['assets'][0].update(asset=archive.name,url=f'https://github.com/{cat["repository"]}/releases/download/{tag}/{archive.name}')
    (built/'local_catalog.json').write_text(json.dumps(cat,ensure_ascii=False,indent=2)+'\n')
    (built/'pilot_catalog.json').unlink()
    shutil.copy2(work/'figures/local_systems_atlas.pdf',built/'local_systems_atlas.pdf')
    shutil.copy2(work/'figures/01_local_system.png',built/'local_system_preview.png')
    return cat


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workdir',type=Path,required=True)
    p.add_argument('--tag',default='sgrt-local-systems-20261024-v1')
    p.add_argument('--source-commit',required=True)
    p.add_argument('--prepared',action='store_true',help='Use already materialized, source-backed inputs; rerun analysis/maps/package')
    p.add_argument('--from-bundle',type=Path,help='Verified local bundle: rerun source-derived tables and figures, reuse road-cost evidence')
    a=p.parse_args();a.workdir.mkdir(parents=True,exist_ok=True)
    if a.prepared and a.from_bundle:p.error('Choose prepared or from-bundle, not both')
    if a.from_bundle:from_bundle(a.from_bundle,a.workdir)
    elif not a.prepared:prepare(a.workdir)
    run(ROOT/'scripts/sgrt_local/analyze.py','--root',a.workdir)
    run(ROOT/'scripts/sgrt_local/figures.py','--root',a.workdir)
    cat=build_package(a.workdir,a.tag,a.source_commit)
    print(json.dumps({'release_tag':a.tag,'counts':cat['counts'],'asset':{k:v for k,v in cat['assets'][0].items() if k!='objects'}},ensure_ascii=False))
