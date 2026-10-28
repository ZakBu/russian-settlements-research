"""Rebuild primary-centre demography; create a verified draft for root review.

No release is made public automatically. Old overlapping-star inputs are retained
only for an explicit same-centre comparison, never substituted for primary members.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import pandas as pd
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_zero.cloud_common_systems import acquire,clean_commit,link_or_copy,releases,run,sha,verify,write,REPOSITORY
from scripts.sgrt_zero.identity_control import table_hash

TAG='sgrt-primary-demography-20261027-v1'
PREFIX='sgrt/primary-demography20261027/'
CONTROL=REPO/'research_context/analysis_snapshots/primary_demography_control_20261027.json'
C='sgrt/common20261027/results/level0/'
R='sgrt/zero20261025/context/analysis_reference.parquet'
OLD='sgrt/centre-demography20261026/readout/centre_demographic_classes.parquet'
INPUTS={'data/common_systems_catalog_20261027.json':[C+'units.parquet',C+'memberships.parquet'],
    'data/zero_catalog_20261025.json':[R], 'data/centre_demography_catalog_20261026.json':[OLD]}
TABLES=('primary_centre_memberships','primary_centre_demographic_components',
    'primary_centre_demographic_classes','primary_population_evidence')
MAP='primary-centre-demography.csv'
LEGEND={'1':'Центр и сельское основное окружение убывают',
    '2':'Центр и сельское основное окружение растут',
    '3':'Разнонаправленная динамика или точное равенство',
    '4':'Недостаточно сопоставимых данных о центре или сельском окружении',
    '5':'В основном распределении нет внешних сельских участников'}
DIRECTIONS={'decline':'убыль','growth':'рост','unchanged':'без изменения','unknown':'не установлено',
    'no_external_rural':'нет внешних сельских участников в основном распределении'}


def site_frame(classes,units):
    centres=units[units.is_registered_external_serving_centre.eq(True)].copy()
    accepted=classes[classes.evidence_mode.eq('accepted_values')].copy()
    if centres.star_id.duplicated().any() or accepted.star_id.duplicated().any():
        raise ValueError('Duplicate mapped centre identity')
    if set(centres.star_id)!=set(accepted.star_id):raise ValueError('Every registered centre needs one accepted description')
    part=accepted[['star_id','centre_settlement_id','centre_direction_2002_2021',
        'external_primary_rural_state_2002_2021','descriptive_primary_type_2002_2021',
        'descriptive_primary_type_2002_2010','descriptive_primary_type_2010_2021']]
    result=centres[['star_id','centre_settlement_id','centre_name','lat','lon']].merge(
        part,on=['star_id','centre_settlement_id'],validate='one_to_one')
    a=result.centre_direction_2002_2021;b=result.external_primary_rural_state_2002_2021
    if not a.isin(['growth','decline','unchanged','unknown']).all() or not b.isin(DIRECTIONS).all():
        raise ValueError('Unexpected demographic status')
    result['value']=3
    result.loc[a.eq('decline') & b.eq('decline'),'value']=1
    result.loc[a.eq('growth') & b.eq('growth'),'value']=2
    result.loc[a.eq('unknown') | b.eq('unknown'),'value']=4
    # Explicit empty rural component is distinct even if centre history is unknown.
    result.loc[b.eq('no_external_rural'),'value']=5
    result['id']=result.star_id
    result['name']=result.centre_name+' — центр: '+a.map(DIRECTIONS)+'; сельское основное окружение: '+b.map(DIRECTIONS)
    result['evidence_mode']='accepted_values'
    result['word_causal_type_established']=False
    result['fixed_composition_year']=2021
    if result[['lat','lon']].isna().any().any() or not result.lat.between(-90,90).all() or not result.lon.between(-180,180).all():
        raise ValueError('Mapped centres require valid existing coordinates')
    return result[['id','name','lat','lon','value','centre_settlement_id','descriptive_primary_type_2002_2021',
        'descriptive_primary_type_2002_2010','descriptive_primary_type_2010_2021','evidence_mode',
        'word_causal_type_established','fixed_composition_year']]


def control(readout,units,export_map=None):
    readout=Path(readout)
    classes=pd.read_parquet(readout/'primary_centre_demographic_classes.parquet')
    points=site_frame(classes,pd.read_parquet(units))
    if export_map:
        target=Path(export_map)
        if target.exists():raise ValueError('Map export must be new')
        points.to_csv(target,index=False)
        if target.stat().st_size>20_000_000:raise ValueError('CSV exceeds existing editor limit')
        decoded=pd.read_csv(target)
        if table_hash(decoded,list(decoded.columns))!=table_hash(points,list(points.columns)):
            raise ValueError('CSV round trip changes map content')
    summary=json.loads((readout/'summary.json').read_text())
    tables={name:table_hash(frame,list(frame.columns)) for name in TABLES
        for frame in [pd.read_parquet(readout/(name+'.parquet'))]}
    actual={'schema':'sgrt.primary_demography_control.v1','tables':tables,'summary':summary,
        'site_points':table_hash(points,list(points.columns)),'legend':LEGEND,
        'main_period':[2002,2021],'main_evidence_mode':'accepted_values',
        'row_multiplicity_and_every_column_compared':True,'numeric_comparison_decimal_places':8,
        'causal_word_types_established':False,'historical_service_flows_established':False}
    return actual,points


def calculate(source,results):
    run('scripts/sgrt_zero/primary_centre_demography.py','--units',source/C/'units.parquet',
        '--memberships',source/C/'memberships.parquet','--reference',source/R,
        '--old-star-classes',source/OLD,'--output',results)


def validate_payload(built,commit):
    manifest=json.loads((built/'manifest.json').read_text())
    expected=json.loads(CONTROL.read_text())
    if (manifest.get('source_commit')!=commit or manifest.get('release_tag')!=TAG
        or manifest.get('archive_root')!=PREFIX or manifest.get('semantic_control')!=expected
        or manifest.get('legend')!=LEGEND or set(manifest.get('standalone_assets',{}))!={MAP}):
        raise ValueError('Producer, tag, control, scope or map asset differs')
    expected_inputs=set()
    for catalog,names in INPUTS.items():
        source_catalog=json.loads((REPO/catalog).read_text())
        rows={row['path']:row for row in source_catalog['files']}
        for name in names:
            obj=source_catalog['objects'][rows[name]['blob']]
            key='inputs/'+name;expected_inputs.add(key)
            if manifest['files'].get(key)!={'bytes':obj['bytes'],'sha256':obj['sha256']}:
                raise ValueError('Bundled input differs from immutable source catalogue')
    if {key for key in manifest['files'] if key.startswith('inputs/')}!=expected_inputs:
        raise ValueError('Exactly the four scientific inputs must be bundled')
    for key,spec in manifest['files'].items():
        if key.startswith('reproduction/'):
            relative=key.removeprefix('reproduction/')
            path=REPO/relative
            if not path.resolve().is_relative_to(REPO) or not path.is_file():raise ValueError('Invalid reproduction path')
            verify(path,spec)
    archive=built/manifest['archive']['asset'];verify(archive,manifest['archive'])
    for name,spec in manifest['standalone_assets'].items():verify(built/name,spec)
    points=pd.read_csv(built/MAP)
    if table_hash(points,list(points.columns))!=expected['site_points']:
        raise ValueError('All map rows must match the independent control')
    with zipfile.ZipFile(archive) as z:
        embedded=json.loads(z.read(PREFIX+'bundle_manifest.json'))
        if embedded!={k:v for k,v in manifest.items() if k!='archive'}:raise ValueError('Embedded manifest differs')
        names=z.namelist()
        wanted={PREFIX+key for key in manifest['files']}|{PREFIX+'bundle_manifest.json'}
        if len(names)!=len(wanted) or set(names)!=wanted:raise ValueError('Duplicate, missing or unexpected archive members')
        import hashlib
        for name,spec in manifest['files'].items():
            member=PREFIX+name
            if z.getinfo(member).file_size!=spec['bytes']:raise ValueError('Member byte size differs')
            with z.open(member) as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=spec['sha256']:raise ValueError('Member SHA differs')
    return manifest


def package(work,source,results,commit,proof,actual,points):
    built=work/'built';built.mkdir()
    points.to_csv(built/MAP,index=False)
    entries={'results/'+name+'.parquet':results/(name+'.parquet') for name in TABLES}
    entries.update({'results/summary.json':results/'summary.json',MAP:built/MAP,'actual_control.json':work/'actual_control.json'})
    # Bundle all four exact input tables, including historical population evidence.
    for names in INPUTS.values():
        for name in names:entries['inputs/'+name]=source/name
    context=['scripts/sgrt_zero/cloud_primary_demography.py','scripts/sgrt_zero/primary_centre_demography.py',
        'scripts/sgrt_zero/centre_demographic_readout.py','scripts/sgrt_zero/cloud_common_systems.py',
        'scripts/sgrt_zero/identity_control.py','scripts/research_data.py','requirements-common-systems.txt',
        'tests/test_sgrt_zero_primary_centre_demography.py','tests/test_sgrt_zero_cloud_primary_demography.py',
        'tests/test_sgrt_zero_centre_demographic_readout.py',
        '.github/workflows/publish-primary-demography.yml','docs/PRIMARY_CENTRE_DEMOGRAPHY_METHOD_20261027.md',
        'docs/PRIMARY_DEMOGRAPHY_RELEASE.md',CONTROL.relative_to(REPO).as_posix(),*INPUTS,
        'research_context/primary/word_concept_extracted.txt','references/sources.json','references/usage.json']
    for name in context:
        if not (REPO/name).is_file():raise FileNotFoundError(name)
        entries['reproduction/'+name]=REPO/name
    manifest={'schema':'sgrt.primary_demography_bundle.v1','source_commit':commit,'release_tag':TAG,'archive_root':PREFIX,
        'source_facts':proof,'semantic_control':actual,'legend':LEGEND,'main_evidence_mode':'accepted_values',
        'scientific_scope':'Fixed primary membership demographic descriptions; direct-observed and accepted panels; no causal Word types or historical flows.',
        'causal_word_types_established':False,'root_verification_required_before_publication':True,
        'files':{name:{'bytes':path.stat().st_size,'sha256':sha(path)} for name,path in sorted(entries.items())},
        'standalone_assets':{MAP:{'bytes':(built/MAP).stat().st_size,'sha256':sha(built/MAP)}}}
    archive=built/'primary-demography.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
        for name,path in sorted(entries.items()):z.write(path,PREFIX+name)
        z.writestr(PREFIX+'bundle_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    manifest['archive']={'asset':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive)}
    write(built/'manifest.json',manifest)
    (built/'release_notes.md').write_text('Демография 28 512 зарегистрированных местных центров и их основного окружения.\n\nЧетыре полные таблицы, три демографических отрезка, два варианта качества, сравнение со старыми пересекающимися окружениями и CSV для редактора карт. Все четыре входные таблицы и код включены в архив. У 13 650 центров в основном распределении осталась только собственная запись: это не доказательство отсутствия внешнего обслуживания. Причинные типы Word и исторические потоки не установлены.\n\nЧерновик требует независимой проверки перед публичным раскрытием.\n')
    validate_payload(built,commit)
    return built


def build(work,commit):
    clean_commit(commit)
    if work.exists() or work.resolve().is_relative_to(REPO):raise ValueError('New workspace outside Git required')
    if not CONTROL.is_file():raise ValueError('Completed independent all-row control required')
    source=work/'inputs';source.mkdir(parents=True);proof=[]
    for catalog,names in INPUTS.items():
        available={r['path'] for r in json.loads((REPO/catalog).read_text())['files']}
        if set(names)-available:raise ValueError('Pinned input absent from catalog')
        proof+=acquire(REPO/catalog,lambda path:path in names,source,work/'cache')
    write(work/'source_facts.json',proof)
    results=work/'results';calculate(source,results)
    actual,points=control(results,source/C/'units.parquet');write(work/'actual_control.json',actual)
    if actual!=json.loads(CONTROL.read_text()):raise ValueError('All-row control differs; packaging stopped')
    return package(work,source,results,commit,proof,actual,points)


def draft(built,commit):
    clean_commit(commit);manifest=validate_payload(built,commit)
    if any(r.get('tag_name')==TAG for r in releases()):raise ValueError('Existing releases and drafts must never be overwritten')
    tag=subprocess.run(['gh','api',f'repos/{REPOSITORY}/git/ref/tags/{TAG}'],capture_output=True,text=True)
    if tag.returncode==0 or 'HTTP 404' not in tag.stderr:raise ValueError('Tag absence unproven')
    assets=[built/'manifest.json',built/manifest['archive']['asset'],built/MAP]
    subprocess.run(['gh','release','create',TAG,'--repo',REPOSITORY,'--target',commit,'--draft',
        '--title','Демография основного окружения: 27 октября 2026','--notes-file',str(built/'release_notes.md'),*map(str,assets)],check=True)
    matches=[r for r in releases() if r.get('tag_name')==TAG and r.get('draft') is True]
    if len(matches)!=1:raise ValueError('Exactly one newly created draft required')
    release=matches[0];expected={p.name:(p.stat().st_size,'sha256:'+sha(p)) for p in assets}
    if (release.get('target_commitish')!=commit or len(release.get('assets',[]))!=len(expected)
        or {a['name']:(a['size'],a.get('digest')) for a in release.get('assets',[])}!=expected):
        raise ValueError('Draft target or uploaded assets differ; retained unpublished')
    return {'draft_release_id':release['id'],'draft':True,'requires_root_verification_before_publication':True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-commit');p.add_argument('--workdir',type=Path);p.add_argument('--draft-built',type=Path)
    p.add_argument('--control-results',type=Path);p.add_argument('--units',type=Path)
    p.add_argument('--control-output',type=Path);p.add_argument('--export-map',type=Path)
    args=p.parse_args()
    if args.control_results:
        if not args.units or not args.control_output:p.error('Control requires --units and --control-output')
        actual,_=control(args.control_results,args.units,args.export_map);write(args.control_output,actual);return
    if not args.source_commit:p.error('--source-commit required')
    if args.draft_built:print(draft(args.draft_built,args.source_commit));return
    if not args.workdir:p.error('--workdir required')
    print(build(args.workdir,args.source_commit))
if __name__=='__main__':main()
