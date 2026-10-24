#!/usr/bin/env python3
"""Full source-backed national pass, or explicitly compact road-evidence reuse.

No publishing or Git mutation except fetching the pinned historical medical
commit. The primary population base is read-only. Published archives are never
replaced. --plan works without installing the scientific Python dependencies.
"""
from __future__ import annotations
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

REPO=Path(__file__).resolve().parents[2]
SCRIPT=REPO/'scripts/sgrt_mass'
TAG='sgrt-mass-local-systems-20261024-v1'
PREFIX='sgrt/mass20261024'
OLD='sgrt/pilot20261024'
TRANSPORT=OLD+'/outputs/transport'
HIST='research/sgrt_word_completion_20261021'
ROAD_COORDS=HIST+'/transport/cycle06_network2021_access_v2/road_nodes'
PARENT=HIST+'/data/source_controls_cycle05/explicit2021_source_parent_bridge.parquet'
PILOT_PATTERNS=[OLD+'/outputs/data/settlements_all_2021.parquet',
    OLD+'/inputs/'+HIST+'/education/education_objects_2021.parquet',
    TRANSPORT+'/legacy_nodes_minimal.parquet',TRANSPORT+'/route_origin_index.parquet',
    TRANSPORT+'/graph/graph_npz_parts/*.bin']
HISTORICAL_PATTERNS=[ROAD_COORDS+'/*.parquet',PARENT]
SOURCES={
 'rosstat':{'name':'stat.info_NP_2025.rar',
    'url':'https://github.com/ZakBu/russian-settlements-research/releases/download/sgrt-rosstat-settlement-books-2025-source-v1/stat.info_NP_2025.rar',
    'sha256':'520b79e3a7a9263f89712df3715b7f1fe1b121055c8bf56d1d6d0835b13cf9e3','bytes':230053990},
 'fns':{'name':'fns_sshr_20260925.zip',
    'url':'https://file.nalog.ru/opendata/7707329152-sshr2019/data-20260925-structure-20200408.zip',
    'sha256':'a4a2972b5d424d49424723cb77837f4605f390ee6edef42f382a0b9504f3f85a'},
 'agriculture':{'name':'agriculture_source.zip',
    'url':'https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_bdmo_118_v20250918/by_section/data_section7_112_v20250918_section_file.zip',
    'parquet_name':'data_section7_112_v20250918.parquet',
    'parquet_sha256':'e6ca2906f49fd0fe561ae98f535206990cebc2675884571bced546c3374c198d'},
}


def digest(path,algorithm='sha256'):
    h=hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def run(script,*arguments):
    command=[sys.executable,str(script),*map(str,arguments)]
    print('RUN',' '.join(command),flush=True)
    env=os.environ.copy();env['OMP_NUM_THREADS']='1';env['OPENBLAS_NUM_THREADS']='1'
    subprocess.run(command,cwd=REPO,check=True,env=env)


def catalog_plan(catalog,patterns,profile):
    c=json.loads(Path(catalog).read_text())
    rows=[r for r in c['files'] if profile in r['profiles'] and any(fnmatch.fnmatchcase(r['path'],m) for m in patterns)]
    missing=[p for p in patterns if not any(fnmatch.fnmatchcase(r['path'],p) for r in rows)]
    if missing:raise ValueError('Required catalogued inputs absent: '+repr(missing))
    assets={c['objects'][r['blob']].get('asset') for r in rows}-{None}
    a=[x for x in c['assets'] if x['asset'] in assets]
    return {'files':len(rows),'logical_bytes':sum(x['bytes'] for x in rows),
        'archive_download_bytes':sum(x['bytes'] for x in a),'assets':[x['asset'] for x in a],
        'patterns':patterns,'profile':profile}


def plan():
    return {'mode':'full_primary_reproduction','stages':['fetch','reference_context','primary_medical','primary_education',
            'geometry','directed_nearest_np_and_sites','model','centre_types','audit','figures','package'],
        'catalogues':{
            'population':catalog_plan(REPO/'data/catalog.json',['data/population/settlements_census_wide.parquet'],'core'),
            'pilot':catalog_plan(REPO/'data/pilot_catalog_20261024.json',PILOT_PATTERNS,'core'),
            'historical':catalog_plan(REPO/'data/catalog.json',HISTORICAL_PATTERNS,'all')},
        'dated_primary_sources':SOURCES,'medical_grok_commit':'c5116d1360d5c97e71aeec52a9b8e182dbcfb8ea',
        'medical_supplements':'Two freshly hash-verified regional primary workbooks; URLs and SHA in medical.py',
        'scope':'Potential service cells and descriptive types; no observed flow or complete nationwide SGRT claim',
        'compact_mode':'Reuse frozen source tables, context and directed road evidence; recompute model/types/audit/figures, not federal scans or new routes',
        'graph_and_road_coordinates_not_duplicated_in_payload':True,
        'primary_population_modified':False,'identical_parquet_or_pdf_bytes_across_machines_promised':False}


def fetch_catalog(catalog,patterns,dest,cache,profile):
    args=['fetch','--catalog',catalog,'--profile',profile,'--dest',dest,'--cache',cache,'--keep-archives']
    for p in patterns:args+=['--match',p]
    run(REPO/'scripts/research_data.py',*args)


def download(source,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    expected=source.get('sha256')
    if path.exists():
        if expected and digest(path)!=expected:raise ValueError('Existing pinned source differs: '+str(path))
        return path
    temporary=path.with_name(path.name+'.partial')
    for attempt in range(3):
        try:
            request=urllib.request.Request(source['url'],headers={'User-Agent':'sgrt-national-research/1'})
            with urllib.request.urlopen(request,timeout=120) as response,temporary.open('wb') as out:
                shutil.copyfileobj(response,out,4*1024*1024)
            if expected and digest(temporary)!=expected:raise ValueError('Source changed: '+source['url'])
            if source.get('bytes') and temporary.stat().st_size!=source['bytes']:raise ValueError('Source byte count differs')
            temporary.replace(path);return path
        except (OSError,TimeoutError):
            temporary.unlink(missing_ok=True)
            if attempt==2:raise
            time.sleep(3*(attempt+1))


def full_prepare(work):
    deps=work/'dependencies';cache=work/'download-cache';source=work/'source'
    source.mkdir(parents=True,exist_ok=True);(work/'inputs').mkdir(exist_ok=True)
    fetch_catalog(REPO/'data/catalog.json',['data/population/settlements_census_wide.parquet'],deps,cache,'core')
    fetch_catalog(REPO/'data/pilot_catalog_20261024.json',PILOT_PATTERNS,deps,cache,'core')
    fetch_catalog(REPO/'data/catalog.json',HISTORICAL_PATTERNS,deps,cache,'all')
    population=deps/'data/population/settlements_census_wide.parquet'
    parent=deps/PARENT;shutil.copy2(parent,work/'inputs/primary_parent_bridge.parquet')
    flat=deps/OLD/'outputs/data/settlements_all_2021.parquet'
    shutil.copy2(flat,work/'inputs/settlements_all_2021.parquet')
    transport=deps/TRANSPORT;graph=transport/'graph';coords=deps/ROAD_COORDS
    origins=transport/'route_origin_index.parquet';legacy=transport/'legacy_nodes_minimal.parquet'
    objects=deps/OLD/'inputs'/HIST/'education/education_objects_2021.parquet'
    rosstat=download(SOURCES['rosstat'],source/SOURCES['rosstat']['name'])
    fns=download(SOURCES['fns'],source/SOURCES['fns']['name'])
    agriculture=source/SOURCES['agriculture']['parquet_name']
    if not agriculture.exists():
        zpath=download(SOURCES['agriculture'],source/SOURCES['agriculture']['name'])
        with zipfile.ZipFile(zpath) as z:
            names=[n for n in z.namelist() if n.endswith('.parquet')]
            if len(names)!=1:raise ValueError('Expected one primary agricultural Parquet')
            with z.open(names[0]) as src,agriculture.open('wb') as dst:shutil.copyfileobj(src,dst)
        zpath.unlink()
    if digest(agriculture)!=SOURCES['agriculture']['parquet_sha256']:raise ValueError('Primary agriculture Parquet differs')
    run(SCRIPT/'context.py','--population',population,'--agriculture',agriculture,'--parent-bridge',parent,
        '--fns-zip',fns,'--output',work/'context')
    medical_repo=REPO
    if not (REPO/'.git').exists():
        # Frozen bundle code can also perform a new full run: source history is
        # fetched into its own bare cache, not mixed into scientific data.
        medical_repo=work/'source-history.git'
        if not medical_repo.exists():
            subprocess.run(['git','init','--bare',str(medical_repo)],check=True)
            subprocess.run(['git','-C',str(medical_repo),'remote','add','origin','https://github.com/ZakBu/russian-settlements-research.git'],check=True)
    run(SCRIPT/'medical.py','--repo',medical_repo,'--materialize','--input',work/'medical/input',
        '--population',population,'--output',work/'medical-corrected')
    run(SCRIPT/'education.py','--primary-rar',rosstat,'--population',population,'--osm',objects,
        '--legacy',legacy,'--output',work/'education')
    # Add territorial workforce after education's actual-header pass, without
    # repeating a full agriculture or federal XML scan.
    sys.path.insert(0,str(SCRIPT))
    import pandas as pd
    from context import attach_partial_workforce
    workforce=work/'education/partial_workforce.parquet'
    workforce_summary=attach_partial_workforce(workforce,pd.read_parquet(work/'context/census_reference.parquet'),work/'context')
    context_meta=work/'context/context_summary.json'
    metadata=json.loads(context_meta.read_text());metadata['partial_workforce']=workforce_summary
    metadata.setdefault('inputs',[]).append({'path':str(workforce),'bytes':workforce.stat().st_size,'sha256':digest(workforce)})
    context_meta.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    run(SCRIPT/'routes.py','--settlements',flat,'--legacy-nodes',legacy,'--road-origins',origins,
        '--prepare-only','--output',work/'routes')
    geometry=['--road-nodes',coords,'--graph-dir',graph,'--road-origins',origins,'--catalog',REPO/'data/catalog.json','--output',work/'site_geometry']
    run(SCRIPT/'site_geometry.py','--objects',work/'education/osm_object_links.parquet',
        '--reference',work/'context/census_reference.parquet',*geometry)
    run(SCRIPT/'site_geometry.py','--resnap-np-endpoints',work/'routes/endpoints.parquet',*geometry)
    run(SCRIPT/'routes.py','--endpoints',work/'routes/endpoints.parquet',
        '--fresh-np-resnaps',work/'site_geometry/fresh_np_resnaps.parquet',
        '--supply',work/'medical-corrected/supply.parquet',work/'education/supply_final_corrected.parquet',
        '--graph-dir',graph,'--output',work/'routes')
    run(SCRIPT/'routes.py','--endpoints',work/'routes/endpoints.parquet',
        '--site-seeds',work/'site_geometry/site_road_seeds.parquet','--graph-dir',graph,'--output',work/'routes_sites')
    (work/'full_prepare.json').write_text(json.dumps({'mode':'full_primary_sources_and_new_directed_routes',
        'primary_population_sha256':digest(population),'parent_bridge_sha256':digest(parent),
        'dated_sources':SOURCES,'reused_legacy_matrix':False,'all_nearest_classes_recomputed':True},ensure_ascii=False,indent=2)+'\n')


def verify_bundle(bundle):
    root=Path(bundle).resolve();manifest=json.loads((root/'checksums.json').read_text())
    for relative,expected in manifest.items():
        path=(root/relative).resolve()
        if not path.is_relative_to(root):raise ValueError('Unsafe path in bundle manifest')
        if not path.is_file() or digest(path)!=expected:raise ValueError('Bundle input differs: '+relative)
    return len(manifest)


def compact_prepare(bundle,work):
    bundle=Path(bundle);count=verify_bundle(bundle)
    for folder in ['inputs','context','medical-corrected','medical/input','medical-chelyabinsk-proxy','education','site_geometry','routes','routes_sites']:
        source=bundle/folder
        if source.exists():shutil.copytree(source,work/folder,dirs_exist_ok=True)
    # Dated auxiliary normative/source evidence is preserved, not silently
    # represented as a newly fetched legal or medical registry.
    for name in ['lo_normative_comparison','sources','pilot_medical_additions']:
        source=bundle/'audit'/name
        if source.exists():shutil.copytree(source,work/'audit'/name,dirs_exist_ok=True)
    (work/'compact_prepare.json').write_text(json.dumps({'mode':'compact_table_and_figure_recomputation',
        'input_files_sha_verified':count,'new_federal_source_scan':False,'new_road_routing':False,
        'reused':['census_reference_and_source_context','institution_evidence','directed_nearest_road_tables'],
        'recomputed':['service_screens_and_units','demographic_and_functional_types','centre_clustering','audits','figures']},indent=2)+'\n')


def analyses(work):
    run(SCRIPT/'model.py','--root',work)
    run(SCRIPT/'centre_types.py','--units',work/'model/units.parquet','--reference',work/'context/census_reference.parquet',
        '--combine-source-layers','--output',work/'centre_types')
    for dirname,output,supply in [('routes','national_np_final',[work/'medical-corrected/supply.parquet',work/'education/supply_final_corrected.parquet']),
            ('routes_sites','national_physical_final',[work/'site_geometry/site_road_seeds.parquet'])]:
        assignments=sorted((work/dirname/'nearest').glob('*.parquet'))
        if not assignments:raise ValueError('No frozen nearest evidence: '+dirname)
        run(SCRIPT/'audit.py','--assignments',*assignments,'--nodes',work/'routes/endpoints.parquet',
            '--supply',*supply,'--output',work/'audit'/output)
    run(SCRIPT/'figures.py','--root',work,'--output',work/'figures')


def payload_files(work):
    """Curate reusable scientific evidence; omit duplicated bulk dependencies."""
    folders=['inputs','context','medical-corrected','medical/input','medical-chelyabinsk-proxy','education','site_geometry','routes','routes_sites',
             'model','centre_types','figures','audit']
    skip_dirs={'primary','raw','archive','download-cache','dependencies','__pycache__','checks'}
    # CSV copies of large Parquet tables do not preserve extra information.
    large_csv_stems={'primary_settlement_rows','primary_books','partial_workforce','partial_workforce_rows',
        'preschool_primary_totals','osm_object_links','rosstat_all_rows','sites_matched','sites_normalized',
        'sites_held','source_observations','site_road_seeds','fresh_np_resnaps','screened_assignments','units'}
    selected={}
    for folder in folders:
        base=work/folder
        if not base.exists():continue
        for p in base.rglob('*'):
            if not p.is_file() or p.is_symlink():continue
            rel=p.relative_to(work)
            nested=p.relative_to(base).parts[:-1]
            if any(x in skip_dirs for x in nested):continue
            if folder=='audit':
                if not nested or nested[0] not in {'national_np_final','national_physical_final','lo_normative_comparison','sources','pilot_medical_additions'}:continue
                # Full screened rows are derived again from preserved raw
                # nearest tables and would duplicate hundreds of megabytes.
                if p.name=='screened_assignments.parquet':continue
            if p.suffix in {'.log','.partial','.rar'}:continue
            if p.suffix=='.csv' and (p.stem in large_csv_stems or p.stat().st_size>2_000_000):continue
            if p.name in {'supply_final.parquet','supply_final.csv'}:continue
            if folder=='education' and p.name.startswith('rosstat_'):continue
            if folder=='education' and p.stem in {'supply','partial_workforce_rows'}:continue
            if p.name.endswith('.csv.gz') and p.with_name(p.name[:-7]+'.parquet').exists():continue
            if p.name.startswith('endpoint_preparation') or p.name.startswith('endpoint_summary'):pass
            selected[rel.as_posix()]=p
    for name in ['full_prepare.json','compact_prepare.json']:
        if (work/name).exists():selected[name]=work/name
    return selected


def package(work,tag,commit):
    required=['context/census_reference.parquet','context/organisation_headcount_2025.parquet',
        'context/agriculture_selected_source_rows.parquet','education/primary_metric_cells.parquet',
        'medical-corrected/supply.parquet','medical/input/registry_inventory.csv',
        'model/units.parquet','model/memberships.parquet','model/summary.json',
        'centre_types/centre_profiles_and_types.parquet','centre_types/summary.json',
        'figures/russia_local_systems_atlas.pdf','figures/atlas_manifest.json','figures/01_national_result.png']
    absent=[name for name in required if not (work/name).is_file()]
    if absent:raise ValueError('Cannot package an incomplete scientific result: '+repr(absent))
    expected_np={'medical_basic_primary','medical_physician_primary','medical_inpatient','medical_day_hospital',
        'medical_specialized','preschool_official','school_general','preschool','vocational_education','higher_education'}
    expected_sites={'school_general','preschool','vocational_education','higher_education'}
    if {p.stem for p in (work/'routes/nearest').glob('*.parquet')}!=expected_np:raise ValueError('NP nearest classes differ from the final source set')
    if {p.stem for p in (work/'routes_sites/nearest').glob('*.parquet')}!=expected_sites:raise ValueError('Physical site classes differ from the final source set')
    payload=work/'payload';local=payload/PREFIX;built=work/'built'
    if payload.exists():shutil.rmtree(payload)
    if built.exists():shutil.rmtree(built)
    local.mkdir(parents=True);built.mkdir()
    sources=payload_files(work)
    before={rel:digest(path) for rel,path in sources.items()}
    for rel,path in sources.items():
        dest=local/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
        if digest(dest)!=before[rel]:raise RuntimeError('Scientific input changed while copying: '+rel)
    if before!={rel:digest(path) for rel,path in sources.items()}:raise RuntimeError('Scientific snapshot changed during packaging')
    bridge=local/'inputs/primary_parent_bridge.parquet'
    if not bridge.exists():
        expected='3b88fc1c7e6f0a99456122d4bb0395f95a8bd45e6e544ecb9a9a1b74c04aa02a'
        candidates=list((work/'context/archive').rglob('explicit2021_source_parent_bridge.parquet'))
        matched=[p for p in candidates if digest(p)==expected]
        if not matched:raise ValueError('Portable primary parent identity bridge absent')
        bridge.parent.mkdir(exist_ok=True);shutil.copy2(matched[0],bridge)
    # Keep all currently used code and human explanations together with data.
    for folder in ['scripts/sgrt_mass','sgrt/mass']:
        if (REPO/folder).exists():shutil.copytree(REPO/folder,local/'reproduction'/folder,ignore=shutil.ignore_patterns('__pycache__'))
    helper=local/'reproduction/scripts/sgrt_pilot';helper.mkdir(parents=True,exist_ok=True)
    shutil.copy2(REPO/'scripts/sgrt_pilot/package_release.py',helper/'package_release.py')
    shutil.copy2(REPO/'scripts/research_data.py',local/'reproduction/scripts/research_data.py')
    catdir=local/'reproduction/data';catdir.mkdir()
    for name in ['catalog.json','pilot_catalog_20261024.json']:shutil.copy2(REPO/'data'/name,catdir/name)
    for folder,filenames in [('references',['sources.json','usage.json']),('research_context/primary',['word_concept_extracted.txt'])]:
        target=local/'reproduction'/folder;target.mkdir(parents=True,exist_ok=True)
        for name in filenames:
            if (REPO/folder/name).exists():shutil.copy2(REPO/folder/name,target/name)
    for name in ['requirements-sgrt-pilot.txt','requirements-sgrt-mass-centres.txt','requirements-sgrt-mass.txt','decisions.json','AGENTS.md','AI_START_HERE.md','README.md']:
        if (REPO/name).exists():shutil.copy2(REPO/name,local/'reproduction'/name)
    # Keep the current research direction and user corrections portable too.
    context_target=local/'reproduction/research_context'
    context_target.mkdir(parents=True,exist_ok=True)
    for name in ['current_state.json','conversation_context_20261022.md']:
        if (REPO/'research_context'/name).is_file():
            shutil.copy2(REPO/'research_context'/name,context_target/name)
    diary=REPO/'research_context/diary/2026-10-24.md'
    if diary.is_file():
        (context_target/'diary').mkdir(exist_ok=True)
        shutil.copy2(diary,context_target/'diary'/diary.name)
    (local/'README.txt').write_text('Массовые локальные функциональные ячейки, 24.10.2026.\n'
        'Не наблюдаемые потоки и не завершённое районирование СГРТ.\n'
        'Compact повтор заново считает модель, типы, диагностику и карты, переиспользуя дорожные свидетельства.\n'
        'Полный первичный расчёт получает граф, координаты дорог и федеральные исходники из закреплённых публичных источников.\n'
        f'Код: {commit}\n',encoding='utf-8')
    checksums={p.relative_to(local).as_posix():digest(p) for p in sorted(local.rglob('*')) if p.is_file()}
    (local/'checksums.json').write_text(json.dumps(checksums,ensure_ascii=False,indent=2)+'\n')
    sys.path.insert(0,str(REPO/'scripts/sgrt_pilot'))
    from package_release import package as generic_package
    generic_package(payload,built,tag,commit)
    old=built/'sgrt-pilot-data.zip';archive=built/'mass-data.zip';old.rename(archive)
    cat=json.loads((built/'pilot_catalog.json').read_text())
    cat['scientific_scope']='National candidate local service cells with service-specific evidence, planning accessibility screens, source gaps and descriptive types; no observed-flow or complete nationwide SGRT claim.'
    for row in cat['files']:row['asset']=archive.name
    for obj in cat['objects'].values():
        obj['asset']=archive.name
    cat['profiles']={'core':'Complete national local-systems companion bundle','all':'Same bundle'}
    cat['assets'][0].update(asset=archive.name,url=f'https://github.com/{cat["repository"]}/releases/download/{tag}/{archive.name}')
    content=json.dumps(cat,ensure_ascii=False,indent=2)+'\n'
    if len(content.encode())>950_000:
        # Preserve core table schemas first; repeated per-service road schemas
        # remain inspectable directly in their Parquet metadata.
        for obj in cat['objects'].values():
            if any(any(fragment in path for fragment in ['/routes/','/routes_sites/','/model/screened/','/audit/']) for path in obj['paths']):obj.pop('fields',None)
        content=json.dumps(cat,ensure_ascii=False,indent=2)+'\n'
    if len(content.encode())>950_000:
        for obj in cat['objects'].values():obj.pop('fields',None)
        content=json.dumps(cat,ensure_ascii=False,indent=2)+'\n'
    (built/'mass_catalog.json').write_text(content)
    (built/'pilot_catalog.json').unlink()
    atlas=work/'figures/russia_local_systems_atlas.pdf'
    if not atlas.exists():raise FileNotFoundError('Scientific atlas not produced: '+str(atlas))
    shutil.copy2(atlas,built/'mass_atlas.pdf')
    shutil.copy2(work/'figures/01_national_result.png',built/'preview.png')
    return cat


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workdir',type=Path)
    p.add_argument('--source-commit')
    p.add_argument('--tag',default=TAG)
    p.add_argument('--prepared',action='store_true',help='Already source-backed/routed workdir; recompute model/types/audit/figures/package')
    p.add_argument('--from-bundle',type=Path,help='Verified local bundle; reuse directed road evidence explicitly')
    p.add_argument('--plan',action='store_true',help='Print source requirements without downloading or scientific imports')
    p.add_argument('--package-only',action='store_true',help='Package an already computed and inspected result; no claimed numerical rerun')
    a=p.parse_args()
    if a.plan:print(json.dumps(plan(),ensure_ascii=False,indent=2));return
    if a.workdir is None or not a.source_commit:p.error('--workdir and --source-commit required for calculations')
    if not re.fullmatch(r'[0-9a-fA-F]{40}',a.source_commit):p.error('--source-commit must be a complete Git commit SHA')
    if a.prepared and a.from_bundle:p.error('Choose prepared or from-bundle, not both')
    work=a.workdir.resolve();work.mkdir(parents=True,exist_ok=True)
    if not a.package_only:
        if a.from_bundle:compact_prepare(a.from_bundle,work)
        elif not a.prepared:full_prepare(work)
        analyses(work)
    cat=package(work,a.tag,a.source_commit)
    print(json.dumps({'tag':a.tag,'source_commit':a.source_commit,'counts':cat['counts'],
        'archive':{k:v for k,v in cat['assets'][0].items() if k!='objects'}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
