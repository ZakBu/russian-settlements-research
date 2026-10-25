#!/usr/bin/env python3
"""Rebuild direct centre systems on a clean worker from pinned public sources.

No live institution or pickup APIs, hidden local geometry cache, population
changes or transitively merged territorial units are used. Publication requires
agreement with the independently retained scientific control, not archive SHA.
"""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2]
SCRIPT=REPO/'scripts/sgrt_zero'
TAG='sgrt-zero-centre-systems-20261025-v1'
REPOSITORY='ZakBu/russian-settlements-research'
DRAFT_RELEASE_ID=423643173
MAIN='daily_20_school30_wb'
# SHA of sorted JSON(origin_id,centre_settlement_id) pairs; scientific identity
# control retained independently from the cloud build, not a Parquet/ZIP hash.
EXPECTED_MEMBERSHIP_SHA256='c1613c7d9a279894b8b063dbb7dc8648a3c8c1bc35011af444ca586a739d2c46'
EXPECTED_DAILY_LINK_SHA256='e3031fd88686e4cb241af1227d4e0a75a42a77e110abc855723e87a03bdc8bb5'
DAILY_CONTROL='research_context/analysis_snapshots/zero_centre_corrected_daily_control_20261025.json'
ROAD_PREFIX='research/sgrt_word_completion_20261021/transport/cycle06_network2021_access_v2/road_nodes'
PILOT_PREFIX='sgrt/pilot20261024/outputs/transport'


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def run(logs,label,script,*arguments):
    """Persist the actual command and subprocess output; show useful failure tail."""
    logs.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,str(script),*map(str,arguments)]
    print('RUN',label,flush=True)
    started=time.monotonic()
    logpath=logs/(label+'.log')
    with logpath.open('w') as log:
        log.write(json.dumps({'command':command},ensure_ascii=False)+'\n');log.flush()
        status=subprocess.run(command,cwd=REPO,stdout=log,stderr=subprocess.STDOUT).returncode
    if status:
        print('\n'.join(logpath.read_text(errors='replace').splitlines()[-70:]),flush=True)
        raise subprocess.CalledProcessError(status,command)
    print(label,'completed',round(time.monotonic()-started,2),'seconds',flush=True)


def fetch(logs,label,catalog,dest,cache,patterns=(),profile='core'):
    arguments=['fetch','--catalog',REPO/catalog,'--dest',dest,'--cache',cache,'--profile',profile]
    for pattern in patterns:arguments.extend(['--match',pattern])
    # Verified materialized objects are reused if a transient download fails.
    for attempt in range(3):
        try:
            run(logs,f'{label}_{attempt+1}',REPO/'scripts/research_data.py',*arguments)
            return
        except subprocess.CalledProcessError:
            if attempt==2:raise
            time.sleep(5)


def compare_scientific_control(analysis, routes):
    import numpy as np
    import pandas as pd
    expected=pd.read_csv(REPO/'sgrt/zero/checked_model_centres_20261025.csv')
    actual=pd.read_csv(analysis/'checked_model_centres.csv')
    if len(expected)!=197 or len(actual)!=197:raise ValueError('Scientific control must contain exactly197 centres')
    keys=['star_id','centre_settlement_id']
    expected=expected.sort_values(keys).reset_index(drop=True)
    actual=actual.sort_values(keys).reset_index(drop=True)
    if set(actual.columns)!=set(expected.columns):raise ValueError('Scientific centre CSV fields differ')
    numeric=[]
    for column in expected:
        a,b=expected[column],actual[column]
        if pd.api.types.is_numeric_dtype(a):
            if not np.allclose(a.to_numpy(float),b.to_numpy(float),rtol=0,atol=1e-10,equal_nan=True):
                raise ValueError('Scientific centre CSV numeric mismatch: '+column)
            numeric.append(column)
        elif not a.fillna('__NULL__').equals(b.fillna('__NULL__')):
            raise ValueError('Scientific centre CSV identity/type mismatch: '+column)
    readout=json.loads((analysis/'readout.json').read_text())
    summary=json.loads((analysis/'scenarios'/MAIN/'summary.json').read_text())
    fixed={'admitted_direct_service_links':455069,'functional_stars':86992,
           'strict_three_core_model_screened_stars':197,
           'strict_three_core_external_positive_whole_records':528}
    for key,value in fixed.items():
        if summary[key]!=value:raise ValueError(f'National scientific control differs: {key}: {summary[key]} != {value}')
    for key,value in {'known_daily_centres_with_positive_whole_external_core_members':21630,
                      'unique_centre_member_pairs':725,'unique_origin_records':725}.items():
        if readout[key]!=value:raise ValueError('Readout control differs: '+key)
    quality_counts={'all_groups_with_coordinate_review':0,'all_groups_with_endpoint_review':0,
                    'groups_with_unknown_component_size':0,'groups_with_component_lt100_diagnostic':0,
                    'groups_with_unknown_school_stage':191}
    for key,value in quality_counts.items():
        if readout[key]!=value:raise ValueError('Strict quality control differs: '+key)
    retained=json.loads((REPO/DAILY_CONTROL).read_text())
    if readout['core_identity_and_admission_coverage']!=retained['core_identity_and_admission_coverage']:
        raise ValueError('Core provider identity and coverage control differs')
    dynamics={'decline__decline':110,'decline__growth':37,'growth__growth':23,
              'growth__decline':22,'decline__unchanged':1,'unknown':4}
    if readout['joint_centre_surrounding_2002_2021']!=dynamics:raise ValueError('Joint demographic control differs')
    for item in json.loads((routes/'summary.json').read_text())['services']:
        if item['origins']!=153803:raise ValueError('Routing lost or added origins')
    memberships=pd.read_parquet(analysis/'scenarios'/MAIN/'strict_three_core_memberships.parquet')
    pairs=sorted(map(tuple,memberships[['origin_id','centre_settlement_id']].astype(str).to_numpy()))
    pair_sha=hashlib.sha256(json.dumps(pairs,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    if len(pairs)!=725 or pair_sha!=EXPECTED_MEMBERSHIP_SHA256:
        raise ValueError('Strict centre-member identities differ from the725-pair scientific control')
    links=pd.read_parquet(analysis/'scenarios'/MAIN/'functional_links.parquet',
                          columns=['origin_id','service_family','provider_key'])
    link_pairs=sorted(map(tuple,links.astype(str).to_numpy()))
    link_sha=hashlib.sha256(json.dumps(link_pairs,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    if len(link_pairs)!=455069 or link_sha!=EXPECTED_DAILY_LINK_SHA256:
        raise ValueError('Direct functional choices differ from the455069-link scientific control')
    subset=json.loads((analysis/'independent_subset_check.json').read_text())
    expected_subset={'daily_20_school30_wb':(725,197,528),'daily_10_school15_wb':(541,157,384),'daily_30_school30_wb':(767,200,567)}
    for sid,(n,c,e) in expected_subset.items():
        value=subset['scenarios'][sid]
        if (value['centre_member_pairs'],value['centres'],value['external_pairs'])!=(n,c,e) or not value['all_pairs_equal']:
            raise ValueError('Independent strict-pair check differs: '+sid)
    checks=json.loads((routes/'independent_forward_checks.json').read_text())
    if checks['services']!=10 or checks['cases']!=18 or not checks['all_equal']:
        raise ValueError('Independent forward checks are incomplete')
    result={'all_197_centres_and_all_csv_fields_equal':True,'numeric_absolute_tolerance':1e-10,
            'numeric_columns':numeric,'expected_csv_sha256':sha(REPO/'sgrt/zero/checked_model_centres_20261025.csv'),
            'actual_csv_sha256':sha(analysis/'checked_model_centres.csv'),
            'strict_member_pair_semantic_sha256':pair_sha,'all725_member_identities_equal':True,
            'all455069_direct_functional_choices_equal':True,'direct_choice_semantic_sha256':link_sha,
            'corrected_daily_control_sha256':sha(REPO/DAILY_CONTROL),
            'national_counts':fixed,'unique_members':725,'known_daily_centres':21630,
            'joint_demographic_counts':dynamics,'strict_quality_counts':quality_counts,
            'core_identity_and_admission_coverage_equal':True,'all_nearest_layers_have_153803_origins':True,
            'independent_forward_checks':checks,'archive_sha_is_not_a_scientific_equality_test':True}
    (analysis/'cloud_scientific_control.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def build(work,commit):
    if work.exists() and any(work.iterdir()):raise ValueError('Use an empty cloud work directory')
    if work.resolve().is_relative_to(REPO):raise ValueError('Generated data must remain outside Git')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()!=commit:
        raise ValueError('Require exact checked-out source commit')
    work.mkdir(parents=True,exist_ok=True)
    logs=work/'logs';data=work/'dependencies';cache=work/'download-cache'
    fetch(logs,'restore_zero','data/zero_catalog_20261025.json',data,cache)
    fetch(logs,'restore_graph','data/pilot_catalog_20261024.json',data,cache,
          [PILOT_PREFIX+'/graph/graph_npz_parts/*.bin',PILOT_PREFIX+'/route_origin_index.parquet'])
    fetch(logs,'restore_road_coordinates','data/catalog.json',data,cache,[ROAD_PREFIX+'/*.parquet'],profile='all')
    fetch(logs,'restore_documents','data/local_systems_catalog_20261024.json',data,cache,
          ['sgrt/local20261024/services/nodes.parquet','sgrt/local20261024/services/links.parquet'])
    bundle=data/'sgrt/zero20261025';inp=bundle/'inputs';ref=bundle/'context/analysis_reference.parquet'
    sys.path.insert(0,str(REPO))
    from scripts.sgrt_zero.reproduce import verify_bundle
    before=verify_bundle(bundle)
    original_manifest_sha=sha(bundle/'checksums.json')
    sources=work/'source_rebuild';education=sources/'education';commerce=sources/'commerce'
    run(logs,'rebuild_education',SCRIPT/'education.py','--current',inp/'education_current.parquet',
        '--historical',inp/'education_history.parquet','--official',inp/'preschool.parquet',
        '--reference',ref,'--legacy',inp/'legacy.parquet','--city-context',bundle/'context/city_context_origins.parquet',
        '--output',education)
    run(logs,'rebuild_commerce',SCRIPT/'commerce.py','--osm',inp/'commerce.parquet',
        '--wb',inp/'frozen_public_sources/wildberries.json.gz','--reference',ref,'--legacy',inp/'legacy.parquet',
        '--population',inp/'population.parquet','--wb-snapshot','2026-10-25','--output',commerce)
    graph=data/PILOT_PREFIX/'graph';road_nodes=data/ROAD_PREFIX
    # These are new snaps on all9.5million verified vertices, not exports of the
    # private earlier cache. Each child process releases its spatial tree before
    # national Dijkstra starts, keeping memory within a standard public worker.
    geometry=work/'fresh_geometry'
    for domain,folder,sites,supply in [('education',education,'physical_sites.parquet','np_supply.parquet'),
                                      ('commerce',commerce,'sites.parquet','supply.parquet')]:
        run(logs,'fresh_geometry_'+domain,SCRIPT/'transport.py','--sites',folder/sites,
            '--np-supply',folder/supply,'--endpoints',bundle/'routes/endpoints.parquet',
            '--road-nodes',road_nodes,'--road-origins',data/PILOT_PREFIX/'route_origin_index.parquet',
            '--catalog',REPO/'data/catalog.json','--graph-dir',graph,
            '--prepare-only','--output',geometry/domain)
    routes=work/'routes'
    common=['--bundle',bundle,'--education',education,'--commerce',commerce,
            '--education-cache',geometry/'education/provider_road_seeds.parquet',
            '--commerce-cache',geometry/'commerce/provider_road_seeds.parquet','--graph-dir',graph]
    run(logs,'reroute_all10',SCRIPT/'reroute_corrected.py',*common,'--output',routes)
    run(logs,'grocery_union',SCRIPT/'combine_nearest.py',
        '--component','osm_grocery_2021='+str(routes/'nearest/daily_grocery.parquet'),
        '--component','current_food_host_2026='+str(bundle/'routes/nearest/daily_grocery_current_retail_host.parquet'),
        '--output',routes/'derived_nearest/daily_grocery_evidence_union.parquet')
    run(logs,'independent_forward_minima',SCRIPT/'verify_corrected_routes.py',*common,'--routes',routes)
    import pandas as pd
    endpoint_quality=pd.read_parquet(routes/'endpoint_network_quality.parquet')
    endpoint_quality['audit_component_size']=endpoint_quality.verified_component_node_count
    inventory=routes/'endpoint_inventory.parquet'
    endpoint_quality.to_parquet(inventory,index=False,compression='zstd')
    del endpoint_quality;gc.collect()
    analysis=work/'analysis'
    run(logs,'education_programme_review',SCRIPT/'diagnose_education_supplementary.py',
        '--before',bundle/'education','--after',education,'--routes-before',bundle/'routes/nearest',
        '--routes-after',routes/'nearest','--output',analysis/'education_supplementary_review')
    run(logs,'main_centres',SCRIPT/'centre_scenarios.py','--bundle',bundle,'--corrected-routes',routes,
        '--endpoints',inventory,'--output',analysis/'scenarios','--scenarios',MAIN)
    main=analysis/'scenarios'/MAIN
    run(logs,'strict_sensitivity',SCRIPT/'fast_strict_sensitivity.py','--main-edges',main/'daily_edges.parquet',
        '--reference',ref,'--endpoints',inventory,'--output',analysis/'scenarios')
    run(logs,'centre_readout',SCRIPT/'centre_readout.py','--root',analysis,'--reference',ref)
    document_inputs=analysis/'document_inputs';document_inputs.mkdir()
    for name in ['links.parquet','nodes.parquet']:
        shutil.copyfile(data/'sgrt/local20261024/services'/name,document_inputs/name)
    run(logs,'documented_links',SCRIPT/'documented_zero_links.py','--links',document_inputs/'links.parquet',
        '--nodes',document_inputs/'nodes.parquet','--school-routes',routes/'nearest/school_general.parquet',
        '--medical-routes',bundle/'routes/nearest/medical_basic_primary.parquet','--output',analysis/'documents')
    run(logs,'independent_subset',SCRIPT/'verify_centre_subset.py','--edges',main/'daily_edges.parquet',
        '--reference',ref,'--scenarios',analysis/'scenarios','--output',analysis/'independent_subset_check.json')
    run(logs,'independent_extent_tail',SCRIPT/'audit_centre_extent_tail.py','--scenario-dir',main,
        '--reference',ref,'--output',analysis/'independent_tail_audit.json',
        '--source-context','post_supplementary_programme_reclassification')
    run(logs,'atlas',SCRIPT/'centre_atlas.py','--root',analysis,'--reference',ref,'--output',analysis/'figures')
    result=compare_scientific_control(analysis,routes)
    after=verify_bundle(bundle)
    if before!=after or sha(bundle/'checksums.json')!=original_manifest_sha:
        raise ValueError('Frozen published control changed during rebuild')
    (analysis/'immutable_inputs_check.json').write_text(json.dumps({'verified_input_file_count':before,
        'before_equals_after':True,'original_checksums_manifest_sha256':original_manifest_sha,
        'population_main_catalog_unchanged':True},indent=2)+'\n')
    # Child logs are inspectable evidence, not a replacement for the comparisons.
    shutil.copytree(logs,analysis/'cloud_logs')
    built=work/'built'
    run(logs,'package',SCRIPT/'pack_centre_results.py','--analysis',analysis,'--routes',routes,
        '--output',built,'--source-commit',commit)
    shutil.copyfile(analysis/'figures/centre_atlas.pdf',built/'centre_atlas.pdf')
    shutil.copyfile(analysis/'figures/06_wider_service_network.png',built/'preview.png')
    manifest=json.loads((built/'manifest.json').read_text())
    notes=(f'Прямые территории обслуживания: расчёт от закреплённых публичных источников.\n\n'
           f'197 строгих модельных групп,725 участников;21 630 центров имеют прямое внешнее окружение хотя бы по одной базовой функции. '
           f'Это проверенный модельный поднабор, не завершённое районирование России и не наблюдённые поездки.\n\n'
           f'Облако заново построило образовательные и торговые источники, привязало их к проверенным дорожным вершинам '
           f'и пересчитало 10 слоёв по 153 803 началам. Все 197 строк и все научные поля контрольного CSV совпали '
           f'(численный допуск 1e-10); 18 прямых проверок минимумов и независимый пересчёт всех строгих пар прошли.\n\n'
           f'Исходный коммит: `{commit}`.\n'
           f'Архив: `{manifest["archive"]["bytes"]}` байт.\n'
           f'SHA256: `{manifest["archive"]["sha256"]}`.\n\n'
           f'Неизменные входы: выпуск sgrt-zero-systems-20261025-v1; граф и документы восстанавливаются по каталогам репозитория. '
           f'Готовая связанная база переписей остаётся основным набором данных.\n')
    (built/'release_notes.md').write_text(notes,encoding='utf-8')
    return manifest


def draft_empty():
    output=subprocess.check_output(['gh','api',f'repos/{REPOSITORY}/releases/{DRAFT_RELEASE_ID}'],text=True)
    release=json.loads(output)
    if release.get('tag_name')!=TAG:raise ValueError('The retained draft has a different tag')
    if not release['draft'] or release.get('assets'):
        raise ValueError('Publication requires the existing empty draft; published or nonempty releases are immutable')
    return release


def publish(built,commit):
    draft_empty()
    manifest=json.loads((built/'manifest.json').read_text())
    if manifest['source_commit']!=commit:raise ValueError('Built source commit differs from publication target')
    archive=built/manifest['archive']['asset']
    if sha(archive)!=manifest['archive']['sha256'] or archive.stat().st_size!=manifest['archive']['bytes']:
        raise ValueError('Publication archive differs from manifest')
    assets=[archive,built/'manifest.json',built/'centre_atlas.pdf',built/'preview.png']
    if any(not p.is_file() for p in assets):raise ValueError('Four complete publication assets are required')
    subprocess.run(['gh','release','upload',TAG,*map(str,assets),'--repo',REPOSITORY],check=True)
    release=json.loads(subprocess.check_output(['gh','api',f'repos/{REPOSITORY}/releases/{DRAFT_RELEASE_ID}'],text=True))
    expected={p.name:p.stat().st_size for p in assets}
    actual={p['name']:p['size'] for p in release['assets']}
    if not release['draft'] or actual!=expected:raise ValueError('Uploaded draft assets differ from the complete package')
    subprocess.run(['gh','release','edit',TAG,'--repo',REPOSITORY,'--notes-file',str(built/'release_notes.md'),
                    '--title','Локальные центры и прямые территории обслуживания — 25 октября 2026',
                    '--target',commit,'--draft=false','--latest=false'],check=True)
    print(json.dumps({'published_tag':TAG,'source_commit':commit,'assets':expected,'archive':manifest['archive']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workdir',type=Path);p.add_argument('--source-commit',required=True)
    p.add_argument('--publish-built',type=Path);p.add_argument('--check-empty-draft',action='store_true')
    a=p.parse_args()
    if a.check_empty_draft:draft_empty()
    elif a.publish_built:publish(a.publish_built,a.source_commit)
    elif a.workdir:
        result=build(a.workdir.resolve(),a.source_commit)
        print(json.dumps({'archive':result['archive'],'files':len(result['files'])}),flush=True)
    else:p.error('Choose --workdir, --publish-built or --check-empty-draft')
