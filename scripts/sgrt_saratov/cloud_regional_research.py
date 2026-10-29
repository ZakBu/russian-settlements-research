"""Rebuild the complete Saratov functional pilot from immutable public inputs.

The expected control is made from a completed local calculation. This producer
compares every output row and matrix entry before creating a new draft release;
it never replaces a previous release or publishes its own unchecked draft.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd
from shapely.geometry import shape
from scipy.sparse import load_npz

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_zero.cloud_common_systems import REPOSITORY, acquire, clean_commit, releases, run, sha, verify, write
from scripts.sgrt_saratov.cloud_isochrones import geometry_digest, table_control, canonical, PROFILE_FOLDER
from scripts.sgrt_saratov.regional_context import MEMBERS as CONTEXT_MEMBERS
from scripts.sgrt_saratov.source_inventory import TRANSPORT, REFERENCE, ENDPOINTS

TAG = 'sgrt-saratov-fields-20261029-v2'
EXPECTED = REPO/'research_context/analysis_snapshots/regional_fields_control_20261029_v2.json'
FROZEN = REPO/'data/saratov_regional_inputs_20261029.json'
HISTORICAL_SCHOOL = REPO/'sgrt/saratov/historical_school_inventory_metadata_2013_2014.csv'
MAGNIT_SOURCE = REPO/'data/saratov_magnit_stores_20261028.json'
MAGNIT_PROVENANCE = REPO/'references/provenance/saratov_magnit_public_locator_20261028.json'
PRIMARY2010_TEXT = REPO/'references/primary/saratov_census2010/reader_extract.txt'
POPULATION_LONG = 'data/population/settlements_census_long.parquet'
FEDERAL_CSV = 'data/population/federal_territories.csv'
GEOGRAPHY_CORRECTIONS = REPO/'sgrt/saratov/documented_coordinate_overlay_20261029.csv'
OLD = 'sgrt/saratov-isochrones20261028/results/'
PROVIDER_PREFIX = 'sgrt/identity20261026/routes/'
PROVIDER_MEMBERS = ['sources/'+group+'/'+name for group,name in (
    ('education','physical_sites.parquet'),('education','np_supply.parquet'),
    ('health','physical_sites.parquet'),('health','np_supply.parquet'),
    ('commerce','sites.parquet'),('food_host','sites.parquet'))]
PROVIDER_MEMBERS += ['geometry_cache/'+group+'/provider_road_seeds.parquet' for group in ('education','health','commerce','food_host')]
SLUGS = ('saratov','engels','balakovo','balashov','novouzensk','piterka')
ISO_STANDALONE = tuple('isochrones_generalized_'+slug+'.geojson' for slug in SLUGS)
ASSET_PATHS = {name:'maps/'+name for name in ISO_STANDALONE}
ASSET_PATHS['saratov-basic-centres.geojson'] = 'maps/saratov-basic-centres.geojson'
ASSET_PATHS.update({scenario+'_'+kind+'.geojson':'school_competition/'+scenario+'_'+kind+'.geojson'
    for scenario in ('baseline','documented_campus_enriched') for kind in ('zones','nearest_timebands')})
ASSET_PATHS.update({family+'_zones.geojson':'medical_competition/'+family+'_zones.geojson' for family in ('medical_basic','medical_physician')})
ASSET_PATHS.update({name:'figures/'+name for name in ('saratov-school-baseline.png','saratov-school-enriched.png',
    'saratov-medical-basic.png','saratov-medical-physician.png')})
STANDALONE = tuple(ASSET_PATHS)
FOLDERS = ('functions','fields','field_sensitivity','geography_overlay','organisation','context','context_baseline','regional_supplement','context_regional_supplement','physical_official','intercentre','context_physical_official','context_physical_official_primary2010','primary2010','context_primary2010','magnit','maps','school_competition','medical_competition','figures','rural_routes','source_documents')
SKIP_PARTS = {'cost_chunks','preview','__pycache__'}
SKIP_NAMES = {'fields_in_progress.parquet','input_invocation.json','graph_prepare_in_progress.json'}
# These three files came from an earlier manual eight-origin experiment, not
# from this producer. Keep its values in the dated research-history snapshot;
# never mix them into the complete regional result or its reproduction control.
HISTORICAL_PROBE_FILES = {
    'field_sensitivity/unbounded_federal_city_costs.parquet',
    'field_sensitivity/unbounded_selected_origins.parquet',
    'field_sensitivity/summary.json',
}
REQUIRED = ('fields/summary.json','fields/regional_roster.parquet','fields/destination_costs.npz',
    'fields/regional_costs.npy','fields/fields.parquet','fields/halo_fields.parquet',
    'functions/functional_links.parquet','functions/functional_system_members.parquet',
    'functions/functional_systems.parquet','functions/basic_configuration_groups.parquet',
    'functions/baseline_functional_links.parquet','functions/documented_school_comparison.parquet',
    'context/np_context.parquet','context/functional_system_dynamic_types.parquet',
    'context/known_partial_worker_fields.parquet','organisation/point_maxima.parquet',
    'maps/isochrones_generalized_bands.geojson')


def inputs():
    selected=defaultdict(set)
    selected['data/catalog.json'].update(TRANSPORT+f'graph_npz_parts/part_{n:03d}.bin' for n in range(3))
    selected['data/catalog.json'].add(FEDERAL_CSV)
    if PRIMARY2010_TEXT.is_file():selected['data/catalog.json'].add(POPULATION_LONG)
    if MAGNIT_SOURCE.is_file():
        selected['data/catalog.json'].update(TRANSPORT+f'road_nodes/part_{n:03d}.parquet' for n in range(24))
    selected['data/zero_catalog_20261025.json'].add(REFERENCE)
    selected['data/identity_catalog_20261026.json'].update([ENDPOINTS]+[PROVIDER_PREFIX+p for p in PROVIDER_MEMBERS])
    selected['data/saratov_isochrones_catalog_20261028.json'].update(OLD+p for p in (
        'inputs/all_current_settlements.parquet','model/isochrones_cumulative.geojson','model/settlement_travel_times.parquet',
        'model/native_edges.parquet','model/reachable_roads_wkb.parquet'))
    for catalog, member in CONTEXT_MEMBERS.values():selected[catalog].add(member)
    return {catalog:sorted(members) for catalog,members in sorted(selected.items())}


def scientific_files(results):
    for folder in FOLDERS:
        for path in sorted((Path(results)/folder).rglob('*')):
            if path.relative_to(results).as_posix() in HISTORICAL_PROBE_FILES:
                continue
            if folder=='maps' and 'water_source' in path.relative_to(Path(results)/folder).parts:
                continue
            if path.is_file() and not SKIP_PARTS.intersection(path.relative_to(results).parts) and path.name not in SKIP_NAMES:
                yield path


def array_control(array):
    """Preserve shape, dtype class, all cells and the explicit missing-value mask."""
    a=np.asarray(array);h=hashlib.sha256();h.update(json.dumps(list(a.shape)).encode())
    if a.dtype.kind in 'fc':
        if a.dtype.kind=='c':raise ValueError('Complex scientific matrices are not supported')
        a=np.asarray(a,dtype='<f8').copy();h.update(b'float64-rounded-8')
        h.update(np.isnan(a).tobytes());h.update(np.isposinf(a).tobytes());h.update(np.isneginf(a).tobytes())
        a[~np.isfinite(a)]=0.;a=np.round(a,8);a[a==0]=0.;h.update(a.tobytes(order='C'))
    elif a.dtype.kind in 'iu':
        h.update(b'integer64');h.update(np.asarray(a,dtype='<i8').tobytes(order='C'))
    elif a.dtype.kind=='b':h.update(b'bool');h.update(a.tobytes(order='C'))
    else:raise ValueError('Unsupported matrix dtype: '+str(a.dtype))
    return {'shape':list(a.shape),'sha256':h.hexdigest(),'every_cell_compared':True}


def matrix_control(path):
    if path.suffix=='.npy':return {'kind':'dense_npy',**array_control(np.load(path,allow_pickle=False))}
    with np.load(path,allow_pickle=False) as data:
        if 'format' not in data.files:
            return {'kind':'named_npz_arrays','arrays':{name:array_control(data[name]) for name in sorted(data.files)}}
    m=load_npz(path).tocsr(copy=True)
    if not m.has_canonical_format:raise ValueError('Sparse matrix must have unique explicit column entries')
    m.sort_indices()
    return {'kind':'csr','shape':list(m.shape),'stored_entries':int(m.nnz),
        'indptr':array_control(m.indptr),'indices':array_control(m.indices),'data':array_control(m.data),
        'explicit_zero_entries':int(np.count_nonzero(m.data==0)),
        'absent_entries_are_not_converted_to_zero':True}


EXCLUDED_SUMMARY_KEYS={'path','paths','inputs','source_files','sources','files','tables','outputs','output_dir',
    'elapsed_seconds','wall_seconds','elapsed_regional_and_halo_seconds','build_seconds',
    'single_query_benchmark_seconds','serial_regional_query_seconds_estimate',
    'provider_catalog_sha256','physical_catalog_sha256','additional_physical_catalog_sha256','input_sha256','source_root','fields_root','output_root'}

def summary_control(value):
    if isinstance(value,dict):return {k:summary_control(v) for k,v in sorted(value.items()) if k not in EXCLUDED_SUMMARY_KEYS}
    if isinstance(value,list):return [summary_control(v) for v in value]
    return canonical(value)


def geojson_control(path):
    doc=json.loads(Path(path).read_text())
    if doc.get('type')!='FeatureCollection':raise ValueError('GeoJSON FeatureCollection required')
    rows=[];seen=set()
    for i,feature in enumerate(doc['features']):
        if feature.get('type')!='Feature' or feature.get('geometry') is None:raise ValueError('Missing geometry')
        props=feature.get('properties',{});identity=str(props.get('id',feature.get('id',i)))
        if identity in seen:raise ValueError('Duplicate geometry identity: '+identity)
        seen.add(identity);geom=shape(feature['geometry'])
        if geom.is_empty:raise ValueError('Empty delivered geometry')
        rows.append(json.dumps({'id':identity,'properties':canonical(props),
            'geometry_sha256':geometry_digest(geom,1e-12)},ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))
    return {'features':len(rows),'sha256':hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest(),
        'fingerprint_coordinate_rounding_degrees':1e-12,'delivered_geometry_not_modified':True}


def control(results):
    results=Path(results)
    required=list(REQUIRED)+['fields/population_mass_sources.parquet','fields/external_city_costs.parquet',
        'field_sensitivity/mass_scope_summary.json','field_sensitivity/selected_unbounded_full_costs.npz']
    if GEOGRAPHY_CORRECTIONS.is_file():
        required.extend('geography_overlay/'+name for name in ('analysis_reference.parquet',
            'endpoint_network_quality.parquet','coordinate_corrections.parquet','geography_overlay_summary.json'))
    if HISTORICAL_SCHOOL.is_file() or MAGNIT_SOURCE.is_file():
        required.extend(['regional_supplement/functional_links.parquet','regional_supplement/np_functional_roles.parquet',
            'context_regional_supplement/functional_system_dynamic_types.parquet'])
    if PRIMARY2010_TEXT.is_file():required.extend(['primary2010/population_2010_evidence.parquet','context_primary2010/functional_system_dynamic_types.parquet'])
    if MAGNIT_SOURCE.is_file():
        required.extend(['magnit/provider_catalog.parquet','magnit/physical_provider_candidates.parquet',
            'physical_official/functional_links.parquet','context_physical_official/functional_system_dynamic_types.parquet',
            'intercentre/centre_function_outcomes.parquet','intercentre/direct_centre_function_edges.parquet',
            'intercentre/functional_relation_summary.parquet','intercentre/cross_function_complementarity_pairs.parquet'])
        required.extend('physical_official/basic_centre_'+name+'_current_inhabited_only.parquet'
            for name in ('profiles','members'))
        scope_contexts=['context_physical_official']
        if PRIMARY2010_TEXT.is_file():scope_contexts.append('context_physical_official_primary2010')
        for folder in scope_contexts:
            required.extend(folder+'/basic_centre_inhabited_only_'+name+'.parquet'
                for name in ('demographic_components','dynamic_types','quality','economic_context'))
            required.append(folder+'/basic_centre_demographic_scope_comparison.parquet')
        if PRIMARY2010_TEXT.is_file():required.append('context_physical_official_primary2010/functional_system_dynamic_types.parquet')
    for name in required:
        if not (results/name).is_file():raise ValueError('Completed regional result missing: '+name)
    population_summary=json.loads((results/'fields/summary.json').read_text())
    if population_summary.get('whole_population_field_unbounded') is not True:
        raise ValueError('Unbounded accepted-population field must finish before control generation')
    for folder in ('functions','regional_supplement','physical_official'):
        path=results/folder/'functional_summary.json'
        if not path.is_file():continue
        scope=json.loads(path.read_text()).get('functional_field_integration',{})
        if scope.get('field_costs_unbounded') is not True:
            raise ValueError('Functional potential refresh is incomplete: '+folder)
    worker_summary=json.loads((results/'context/worker_field_summary.json').read_text())
    if worker_summary.get('worker_field_uses_unbounded_accepted_car_graph') is not True:
        raise ValueError('Unbounded known-worker potential must finish before control generation')
    if MAGNIT_SOURCE.is_file():
        for folder in scope_contexts:
            scope_summary=json.loads((results/folder/'summary.json').read_text())
            if scope_summary.get('inhabited_only_basic_sensitivity_included') is not True:
                raise ValueError('Zero-inclusive versus inhabited-only demographic comparison is incomplete: '+folder)
    tables={};matrices={};geometries={};summaries={}
    for path in scientific_files(results):
        key=path.relative_to(results).as_posix()
        # Frozen input documents are checked byte-for-byte at acquisition and
        # packaged unchanged; they are not newly derived scientific tables.
        if key.startswith('source_documents/'):continue
        if path.suffix in {'.parquet','.csv'}:
            try:tables[key]=table_control(path)
            except pd.errors.EmptyDataError:
                # Empty documented changes are a legitimate no-change source case.
                if path.stat().st_size>1:raise
                tables[key]={'rows':0,'columns':[],'empty_file_sha256':sha(path)}
        elif path.suffix in {'.npy','.npz'}:matrices[key]=matrix_control(path)
        elif path.suffix=='.geojson':geometries[key]=geojson_control(path)
        elif path.name in {'summary.json','graph_summary.json','functional_summary.json','worker_field_summary.json','current_provider_summary.json','mass_scope_summary.json','basic_centres_summary.json','geography_overlay_summary.json'}:
            summaries[key]=summary_control(json.loads(path.read_text()))
    for name,relative in ASSET_PATHS.items():
        if not name.endswith('.geojson'):continue
        if relative not in geometries or not geometries[relative]['features']:
            raise ValueError('Completed nonempty standalone map asset missing: '+name)
    for name in ISO_STANDALONE:
        if geometries.get('maps/'+name,{}).get('features')!=4:raise ValueError('Four map bands required: '+name)
    return {'schema':'sgrt.saratov.regional_control.v1','tables':tables,'matrices':matrices,
        'geojson':geometries,'scientific_summaries':summaries,'numeric_decimal_places':8,
        'every_table_row_and_column_compared':True,'every_matrix_entry_and_missingness_compared':True,
        'computed_fields_are_not_observed_trip_flows':True}


def relative_path(root,name):
    p=Path(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Unsafe frozen input path')
    target=root/p
    if not target.resolve().is_relative_to(root.resolve()):raise ValueError('Frozen input escapes directory')
    return target


def acquire_frozen(target,manifest_path=FROZEN):
    manifest=json.loads(Path(manifest_path).read_text());proof=[];target.mkdir(parents=True)
    for spec in manifest['assets']:
        path=relative_path(target,spec['path']);path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():raise ValueError('Duplicate frozen asset path')
        request=urllib.request.Request(spec['url'],headers={'User-Agent':'sgrt-saratov-regional-research/1'})
        if not spec['url'].startswith('https://') or '/latest/' in spec['url'] or '/main/' in spec['url']:
            raise ValueError('Frozen input requires immutable HTTPS URL')
        with urllib.request.urlopen(request,timeout=180) as source,path.open('wb') as output:
            count=0
            while chunk:=source.read(1<<20):
                count+=len(chunk)
                if count>spec['bytes']:raise ValueError('Frozen asset exceeds pinned size')
                output.write(chunk)
        verify(path,spec);proof.append({k:spec[k] for k in ('url','path','bytes','sha256')})
        if path.suffix=='.zip':
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if member.is_dir():continue
                    destination=relative_path(target,member.filename)
                    if destination.exists():raise ValueError('Duplicate frozen ZIP member')
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    with archive.open(member) as source,destination.open('wb') as output:shutil.copyfileobj(source,output)
            path.unlink()
    for spec in manifest.get('files',[]):verify(relative_path(target,spec['path']),spec)
    frozen_water(target)
    return proof


def frozen_water(root):
    for relative in ('water/water_mask.geojson','maps/water_source/water_mask.geojson'):
        path=root/relative
        if path.is_file():return path
    raise ValueError('Pinned cartographic water mask required')


def require_audit(path):
    report=json.loads(Path(path).read_text())
    if report.get('violations',0) or report.get('errors'):raise ValueError('Independent output audit failed: '+str(path.name))


def curated_source_proofs():
    proofs=[]
    for table,provenance_path,key in (
        (HISTORICAL_SCHOOL,REPO/'references/provenance/saratov_historical_school_codes_2013_2014.json','curated_csv'),
        (MAGNIT_SOURCE,MAGNIT_PROVENANCE,'curated_model_source')):
        if not table.is_file():continue
        provenance=json.loads(provenance_path.read_text());spec=provenance[key]
        if spec['path']!=table.relative_to(REPO).as_posix():raise ValueError('Curated source identity differs from provenance')
        verify(table,spec)
        proofs.append({'kind':'frozen_curated_primary_source_in_producer_git','path':spec['path'],
            'bytes':spec['bytes'],'sha256':spec['sha256'],
            'provenance':provenance_path.relative_to(REPO).as_posix(),'provenance_sha256':sha(provenance_path)})
    return proofs


def archive_frozen_magnit_response(folder):
    """Retain the exact original primary response, never a fresh substitute."""
    if not MAGNIT_SOURCE.is_file():return None
    provenance=json.loads(MAGNIT_PROVENANCE.read_text())
    primary=REPO/'references/primary/saratov_magnit_20261028'
    compressed=primary/'locator_raw.json.gz'
    expected_compressed={'bytes':64920,'sha256':'7071d9479a9d343ecbb19798f0ff8c24b52dc970956efede8d8096255522c112'}
    verify(compressed,expected_compressed)
    folder=Path(folder)/'commerce';folder.mkdir(parents=True,exist_ok=True)
    raw=folder/'locator_raw.json';raw.write_bytes(gzip.decompress(compressed.read_bytes()))
    verify(raw,provenance['raw_response'])
    for name in ('locator_query.json','locator_shops_route_Da75p-8i.js'):
        shutil.copyfile(primary/name,folder/name)
    proof={'kind':'exact_frozen_primary_publisher_response','used_to_curate_frozen_model_source':True,
        'bytes':raw.stat().st_size,'sha256':sha(raw),'compression':'lossless_gzip',
        'compressed_source':compressed.relative_to(REPO).as_posix(),
        'compressed_bytes':expected_compressed['bytes'],'compressed_sha256':expected_compressed['sha256']}
    proof['decompressed_bytes']=raw.stat().st_size;proof['decompressed_sha256']=sha(raw)
    write(folder/'locator_primary_provenance.json',proof)
    return proof


def package(work,commit):
    results=work/'results';built=work/'built';built.mkdir();entries=[]
    archive=built/'saratov-fields.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        def add(path,name):
            z.write(path,name);entries.append({'path':name,'bytes':path.stat().st_size,'sha256':sha(path)})
        for path in scientific_files(results):add(path,'results/'+path.relative_to(results).as_posix())
        add(results/'source_manifest.json','results/source_manifest.json')
        add(work/'actual_control.json','controls/actual_control.json');add(EXPECTED,'controls/expected_control.json')
        for path in sorted((work/'checks').glob('*.json')):add(path,'checks/'+path.name)
        names=subprocess.check_output(['git','ls-files','scripts','tests','sgrt/saratov','references',
            'decisions.json','.gitattributes','repository_policy.json','AGENTS.md','README.md','POPULATION_BASE.md',
            'sgrt/MODEL_DESIGN.md','research_context/primary',
            PROFILE_FOLDER+'road_profile.py',PROFILE_FOLDER+'finite_access_policy_proposal.json',
            PROFILE_FOLDER+'assemble_graph2021.py','web/src/components/custom-map-layers.ts','web/src/components/MapWorkspace.tsx','research_context/current_state.json','research_context/diary/2026-10-29.md',
            'requirements-saratov-fields.txt','.github/workflows/publish-saratov-fields.yml',
            '.github/workflows/finalize-saratov-fields.yml',
            'research_context/analysis_snapshots/saratov_early_eight_origin_probe_20261028.json',
            str(EXPECTED.relative_to(REPO)),str(FROZEN.relative_to(REPO)),str(MAGNIT_SOURCE.relative_to(REPO)),*inputs().keys()],cwd=REPO,text=True).splitlines()
        for name in sorted(set(names)):add(REPO/name,'reproduction/'+name)
    standalone={}
    for name in STANDALONE:
        path=results/ASSET_PATHS[name];shutil.copyfile(path,built/name)
        standalone[name]={'bytes':path.stat().st_size,'sha256':sha(path)}
    manifest={'schema':'sgrt.saratov.regional_release.v1','release_tag':TAG,'source_commit':commit,
        'archive':{'asset':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive)},
        'standalone_assets':standalone,'files':entries,'source_manifest':json.loads((results/'source_manifest.json').read_text()),
        'scope':'Complete Saratov population and functional potential pilot; overlapping conditional service systems, descriptive dynamics and economic context.',
        'observed_trip_flows_or_empirically_validated_universal_hierarchy':False,
        'population_default_catalog_unchanged':True,
        'preferred_functional_variant':'physical_official' if (results/'physical_official').is_dir() else 'functions',
        'historical_school_source_sensitivity':'regional_supplement' if (results/'regional_supplement').is_dir() else None,
        'preferred_demographic_variant':'context_physical_official_primary2010' if (results/'context_physical_official_primary2010').is_dir() else 'context'}
    write(built/'manifest.json',manifest)
    (built/'release_notes.md').write_text('Саратовская область: многомасштабные поля населения, отдельные функциональные связи, местные центры и их демографический и хозяйственный контекст.\n\n'
        'Потенциалы населения, отдельных функций и известной части работников рассчитаны по полному ориентированному дорожному графу без отсечения дальних вкладов. '
        'Масса федеральных территорий Москвы и Петербурга учтена однократно; неподтверждённые и отсутствующие сведения не заменены нулями. '
        'Документированные исправления координат выделены в отдельный производный слой; опубликованная база населения и её признаки зачёта не изменены.\n\n'
        'Основной дополнительный вариант использует документированные места школьных площадок и координаты магазинов из официального локатора. Старый школьный перечень сохранён отдельным историческим сценарием. Первичные данные переписи 2010 года проверяются отдельным вариантом на тех же составах систем; исходная сшитая база не изменена.\n\n'
        'В демографическом составе сохранены связанные пункты с нулевой опубликованной численностью 2021 года, чтобы их прежнее население не исчезало из сравнения. '
        'Состав только из жилых пунктов оставлен отдельной проверкой чувствительности; пустые пункты не создают новые центры и не считаются наблюдаемыми потребителями услуг.\n\n'
        'Сохранены все текущие населённые пункты, альтернативные направления обслуживания, неопределённость исходных данных и сравнение школьных назначений до и после уточнения физических филиалов. '
        'Карты времени поездки обобщены для обзора. Модельные потенциалы и связи не объявляются наблюдёнными потоками; число уровней не назначается заранее.\n\n'
        'Архив содержит результаты, закреплённые источники новых школьных свидетельств и водной маски, весь воспроизводящий код, каталоги национальных исходников и независимые численные проверки. '
        'Национальные исходники остаются в предыдущих неизменных выпусках. Свежий облачный расчёт сравнен с завершённым локальным расчётом по всем строкам и ячейкам.\n')
    return built


def draft(built,commit):
    clean_commit(commit);manifest=json.loads((built/'manifest.json').read_text())
    if manifest['source_commit']!=commit or manifest['release_tag']!=TAG:raise ValueError('Wrong producer or tag')
    if any(row['tag_name']==TAG for row in releases()):raise ValueError('Existing release/draft cannot be overwritten')
    ref=subprocess.run(['gh','api',f'repos/{REPOSITORY}/git/ref/tags/{TAG}'],capture_output=True,text=True)
    if ref.returncode==0 or 'HTTP 404' not in ref.stderr:raise ValueError('Cannot establish absence of tag')
    assets=[built/manifest['archive']['asset'],built/'manifest.json']
    verify(assets[0],manifest['archive'])
    for name,spec in manifest['standalone_assets'].items():verify(built/name,spec);assets.append(built/name)
    subprocess.run(['gh','release','create',TAG,'--repo',REPOSITORY,'--target',commit,'--draft',
        '--title','Саратовская область: функциональные поля и местные системы, 29 октября 2026',
        '--notes-file',str(built/'release_notes.md'),*map(str,assets)],check=True)
    rows=[r for r in releases() if r['tag_name']==TAG]
    if len(rows)!=1 or rows[0].get('draft') is not True:raise ValueError('Exactly one unpublished draft required')
    row=rows[0];expected={p.name:(p.stat().st_size,'sha256:'+sha(p)) for p in assets}
    if row['target_commitish']!=commit or {a['name']:(a['size'],a.get('digest')) for a in row['assets']}!=expected:
        raise ValueError('Uploaded assets differ; draft stays unpublished')
    return row['id']


def build(work,commit):
    clean_commit(commit)
    if work.exists() or work.resolve().is_relative_to(REPO) or not EXPECTED.is_file():
        raise ValueError('Use fresh external work directory and completed committed local control')
    source=work/'input';source.mkdir(parents=True);results=work/'results';results.mkdir();checks=work/'checks';checks.mkdir()
    proofs=curated_source_proofs()
    for catalog,paths in inputs().items():
        available={row['path'] for row in json.loads((REPO/catalog).read_text())['files']}
        if not set(paths)<=available:raise ValueError('Missing pinned catalogue member: '+catalog)
        proofs.extend(acquire(REPO/catalog,lambda p,chosen=set(paths):p in chosen,source,work/'cache'))
    frozen=source/'frozen';frozen_proof=acquire_frozen(frozen);proofs.append({'frozen_manifest_sha256':sha(FROZEN),'assets':frozen_proof})
    shutil.copytree(frozen,results/'source_documents')
    if MAGNIT_SOURCE.is_file():
        proofs.append(archive_frozen_magnit_response(results/'source_documents'))
    write(results/'source_manifest.json',proofs)
    provider=source/PROVIDER_PREFIX;fields=results/'fields';functions=results/'functions';graph=source/TRANSPORT
    reference_path,endpoints_path=source/REFERENCE,source/ENDPOINTS
    if GEOGRAPHY_CORRECTIONS.is_file():
        geography=results/'geography_overlay'
        run('scripts/sgrt_saratov/geography_overlay.py','--reference',reference_path,'--endpoints',endpoints_path,
            '--corrections',GEOGRAPHY_CORRECTIONS,'--road-nodes',source/TRANSPORT/'road_nodes',
            '--road-catalog','data/catalog.json','--output',geography)
        reference_path,endpoints_path=geography/'analysis_reference.parquet',geography/'endpoint_network_quality.parquet'
        proofs.append({'kind':'explicit_derived_pilot_coordinate_overlay','path':GEOGRAPHY_CORRECTIONS.relative_to(REPO).as_posix(),
            'sha256':sha(GEOGRAPHY_CORRECTIONS),'bytes':GEOGRAPHY_CORRECTIONS.stat().st_size,
            'original_population_foundation_changed':False})
        write(results/'source_manifest.json',proofs)
    run('scripts/sgrt_saratov/functional_fields.py','--prepare-catalog','--source-root',provider,'--output',functions,
        *(['--geography-inputs',results/'geography_overlay'] if GEOGRAPHY_CORRECTIONS.is_file() else []))
    run('scripts/sgrt_saratov/regional_fields.py','--reference',reference_path,'--endpoints',endpoints_path,
        '--regional-roster',source/OLD/'inputs/all_current_settlements.parquet','--graph-dir',graph,
        '--provider-catalog',functions/'provider_catalog.parquet','--output',fields,'--workers','4','--horizon','480')
    run('scripts/sgrt_saratov/regional_fields.py','--reference',reference_path,'--endpoints',endpoints_path,
        '--regional-roster',source/OLD/'inputs/all_current_settlements.parquet','--graph-dir',graph,'--output',fields,'--finalize-existing')
    full_cache=work/'full-field-costs'
    run('scripts/sgrt_saratov/population_mass_scope.py','--fields',fields,'--federal-csv',source/FEDERAL_CSV,
        '--graph-dir',graph,'--catalog','data/catalog.json','--output',results/'field_sensitivity',
        '--cost-cache-dir',full_cache,'--workers','4')
    full_arguments=['--full-field-costs',full_cache/'full_destination_costs.npy',
        '--full-origin-axis',full_cache/'origin_axis.parquet','--full-destination-axis',full_cache/'destination_axis.parquet']
    run('scripts/sgrt_saratov/regional_fields.py','--reference',reference_path,'--endpoints',endpoints_path,
        '--regional-roster',source/OLD/'inputs/all_current_settlements.parquet','--graph-dir',graph,
        '--provider-catalog',functions/'provider_catalog.parquet','--output',fields,'--workers','4','--current-provider-only')
    run('scripts/sgrt_saratov/spatial_organisation.py','--fields',fields,'--output',results/'organisation')
    run('scripts/sgrt_saratov/functional_fields.py','--fields-root',fields,'--provider-root',functions,'--output',functions,
        '--documented-presence','sgrt/saratov/documented_school_campuses_2025.csv',
        '--documented-presence','sgrt/saratov/documented_school_branch_sites.csv',
        '--documented-presence','sgrt/saratov/documented_school_sites_20261029.csv',
        '--documented-assignments','sgrt/saratov/documented_school_catchments_2025.csv',
        '--current-candidates',fields/'physical_provider_candidates_current.parquet',*full_arguments)
    supplemental_args=[];physical_args=[]
    if HISTORICAL_SCHOOL.is_file():supplemental_args.extend(['--supplementary-presence',HISTORICAL_SCHOOL])
    if MAGNIT_SOURCE.is_file():
        # Re-evaluate literal physical-address ownership against the explicit
        # pilot coordinate overlay, without querying or changing the source.
        run('scripts/sgrt_saratov/official_magnit.py','--raw',results/'source_documents/commerce/locator_raw.json',
            '--reference',fields/'national_reference_with_endpoints.parquet',
            '--query',results/'source_documents/commerce/locator_query.json','--output',results/'magnit')
        run('scripts/sgrt_saratov/official_magnit.py','--route-only','--curated',results/'magnit/physical_stores.json',
            '--road-nodes',source/TRANSPORT/'road_nodes','--road-catalog','data/catalog.json',
            '--fields',fields,'--output',results/'magnit','--workers','4')
        physical_args.extend(['--supplementary-provider-catalog',results/'magnit/provider_catalog.parquet',
            '--supplementary-candidates',results/'magnit/physical_provider_candidates.parquet'])
        supplemental_args.extend(physical_args)
    if supplemental_args:
        run('scripts/sgrt_saratov/functional_fields.py','--fields-root',fields,'--provider-root',functions,
            '--output',results/'regional_supplement',
            '--documented-presence','sgrt/saratov/documented_school_campuses_2025.csv',
            '--documented-presence','sgrt/saratov/documented_school_branch_sites.csv',
            '--documented-presence','sgrt/saratov/documented_school_sites_20261029.csv',
            '--documented-assignments','sgrt/saratov/documented_school_catchments_2025.csv',
            '--current-candidates',fields/'physical_provider_candidates_current.parquet',*supplemental_args,*full_arguments)
    if physical_args:
        run('scripts/sgrt_saratov/functional_fields.py','--fields-root',fields,'--provider-root',functions,
            '--output',results/'physical_official','--single-inventory','physical_official_enrichment',
            '--documented-presence','sgrt/saratov/documented_school_campuses_2025.csv',
            '--documented-presence','sgrt/saratov/documented_school_branch_sites.csv',
            '--documented-presence','sgrt/saratov/documented_school_sites_20261029.csv',
            '--documented-assignments','sgrt/saratov/documented_school_catchments_2025.csv',
            '--current-candidates',fields/'physical_provider_candidates_current.parquet',*physical_args,*full_arguments)
        run('scripts/sgrt_saratov/intercentre_profiles.py','--functions',results/'physical_official','--output',results/'intercentre')
    args=[]
    for name,(_,member) in CONTEXT_MEMBERS.items():args.extend(['--'+name.replace('_','-'),source/member])
    # Demographic aggregation consumes immutable population observations and
    # classifications by identity, never the corrected model coordinates.
    # Keep its independent source-SHA verification against the original base.
    for baseline in (False,True):
        prefix='baseline_' if baseline else ''
        run('scripts/sgrt_saratov/regional_context.py',*args,'--output',results/('context_baseline' if baseline else 'context'),
            '--links',functions/(prefix+'functional_links.parquet'),'--configurations',functions/(prefix+'basic_configuration_groups.parquet'),
            '--system-reference',source/REFERENCE,
            '--basic-profiles',functions/(prefix+'basic_centre_profiles.parquet'),
            '--basic-members',functions/(prefix+'basic_centre_members.parquet'))
    if supplemental_args:
        supplement=results/'regional_supplement'
        run('scripts/sgrt_saratov/regional_context.py',*args,'--output',results/'context_regional_supplement',
            '--links',supplement/'functional_links.parquet','--configurations',supplement/'basic_configuration_groups.parquet',
            '--system-reference',source/REFERENCE,'--basic-profiles',supplement/'basic_centre_profiles.parquet',
            '--basic-members',supplement/'basic_centre_members.parquet')
    if PRIMARY2010_TEXT.is_file():
        run('scripts/sgrt_saratov/primary_census2010.py','--population-long',source/POPULATION_LONG,'--output',results/'primary2010')
        run('scripts/sgrt_saratov/primary2010_independent_checks.py',
            '--reader','references/primary/saratov_census2010/reader_extract.txt',
            '--parsed',results/'primary2010/primary_np_rows.parquet',
            '--evidence',results/'primary2010/population_2010_evidence.parquet',
            '--population-long',source/POPULATION_LONG,'--output',checks/'primary2010_independent.json')
        chosen=results/'regional_supplement' if supplemental_args else functions
        run('scripts/sgrt_saratov/regional_context.py',*args,'--output',results/'context_primary2010',
            '--links',chosen/'functional_links.parquet','--configurations',chosen/'basic_configuration_groups.parquet',
            '--system-reference',source/REFERENCE,'--basic-profiles',chosen/'basic_centre_profiles.parquet',
            '--basic-members',chosen/'basic_centre_members.parquet',
            '--primary2010-evidence',results/'primary2010/population_2010_evidence.parquet')
        run('scripts/sgrt_saratov/primary_census2010.py','--compare-baseline',results/'context_regional_supplement' if supplemental_args else results/'context',
            '--compare-primary',results/'context_primary2010','--output',results/'primary2010/comparison')
    if physical_args:
        preferred=results/'physical_official'
        for primary in (False,True) if PRIMARY2010_TEXT.is_file() else (False,):
            folder='context_physical_official_primary2010' if primary else 'context_physical_official'
            run('scripts/sgrt_saratov/regional_context.py',*args,'--output',results/folder,
                '--links',preferred/'functional_links.parquet','--configurations',preferred/'basic_configuration_groups.parquet',
                '--system-reference',source/REFERENCE,'--basic-profiles',preferred/'basic_centre_profiles.parquet',
                '--basic-members',preferred/'basic_centre_members.parquet',
                '--inhabited-only-basic-profiles',preferred/'basic_centre_profiles_current_inhabited_only.parquet',
                '--inhabited-only-basic-members',preferred/'basic_centre_members_current_inhabited_only.parquet',
                *(['--primary2010-evidence',results/'primary2010/population_2010_evidence.parquet'] if primary else []))
        if PRIMARY2010_TEXT.is_file():
            run('scripts/sgrt_saratov/primary_census2010.py','--compare-baseline',results/'context_physical_official',
                '--compare-primary',results/'context_physical_official_primary2010',
                '--output',results/'primary2010/physical_official_comparison')
    run('scripts/sgrt_saratov/regional_context.py','--worker-fields-only','--field-input',fields,
        '--partial-workers',source/CONTEXT_MEMBERS['partial_workers'][1],
        '--full-field-costs',full_cache/'full_destination_costs.npy','--output',results/'context')
    run('scripts/sgrt_saratov/generalized_maps.py','--source',source/OLD/'model/isochrones_cumulative.geojson',
        '--water-mask',frozen_water(frozen),'--output',results/'maps')
    if physical_args:
        run('scripts/sgrt_saratov/regional_centres_map.py','--functions',results/'physical_official',
            '--reference',fields/'regional_roster.parquet','--output',results/'maps')
    run('scripts/sgrt_saratov/school_competition.py','--graph-dir',graph,
        '--native-path',source/OLD/'model/native_edges.parquet',
        '--reachable-path',source/OLD/'model/reachable_roads_wkb.parquet',
        '--provider-path',functions/'provider_catalog.parquet','--roster-path',fields/'regional_roster.parquet',
        '--presence-path',functions/'np_function_presence.parquet',
        '--official-paths','sgrt/saratov/documented_school_campuses_2025.csv','sgrt/saratov/documented_school_branch_sites.csv',
        'sgrt/saratov/documented_school_sites_20261029.csv',
        '--water-path',frozen_water(frozen),'--output',results/'school_competition')
    run('scripts/sgrt_saratov/medical_competition.py','--graph-dir',graph,
        '--native-path',source/OLD/'model/native_edges.parquet','--reachable-path',source/OLD/'model/reachable_roads_wkb.parquet',
        '--provider-path',functions/'provider_catalog.parquet','--roster-path',fields/'regional_roster.parquet',
        '--water-path',frozen_water(frozen),'--output',results/'medical_competition')
    run('-m','scripts.sgrt_saratov.rural_route_diagnostics','--roster',fields/'regional_roster.parquet','--graph-dir',graph,
        '--road-nodes','references/primary/saratov_rural_roads_2021/graph_vertex_subset.json',
        '--native-sources','references/primary/saratov_rural_roads_2021','--output',results/'rural_routes')
    audit='scripts/sgrt_saratov/regional_independent_checks.py'
    run('scripts/sgrt_saratov/unbounded_independent_checks.py','--fields',fields,
        '--federal-csv',source/FEDERAL_CSV,'--catalog','data/catalog.json',
        '--scope-root',results/'field_sensitivity','--cost-cache',full_cache,
        '--graph-dir',graph,'--output',checks/'unbounded_population_independent.json')
    run(audit,'--precompute-routes','--regional-roster',fields/'regional_roster.parquet','--graph-dir',graph,
        '--previous-isochrones',source/OLD/'model/settlement_travel_times.parquet','--output',checks/'original_graph_route_controls.json')
    run(audit,'--catalog-only','--functions-root',functions,'--provider-source-root',provider,
        '--provider-catalog','data/identity_catalog_20261026.json',
        *(['--geography-inputs',results/'geography_overlay'] if GEOGRAPHY_CORRECTIONS.is_file() else []),
        '--output',checks/'provider_raw_source_reconciliation.json')
    run(audit,'--maps-root',results/'maps','--output',checks/'cartography_independent.json')
    run(audit,'--actual-fields-root',fields,'--route-controls',checks/'original_graph_route_controls.json',
        '--organisation-root',results/'organisation','--full-cost-cache',full_cache,'--output',checks/'actual_regional_output_audit.json')
    run(audit,'--actual-fields-root',fields,'--functions-results-root',functions,
        '--full-cost-cache',full_cache,'--output',checks/'actual_functional_output_audit.json')
    run(audit,'--actual-fields-root',fields,'--context-root',results/'context',
        '--full-cost-cache',full_cache,'--output',checks/'actual_worker_output_audit.json')
    run(audit,'--actual-fields-root',fields,'--functions-results-root',functions,
        '--unit-context-root',results/'context','--output',checks/'actual_unit_demography_audit.json')
    run(audit,'--actual-fields-root',fields,'--basic-centres-root',functions,
        '--output',checks/'actual_basic_centres_audit.json')
    run(audit,'--medical-competition-root',results/'medical_competition','--graph-dir',graph,
        '--output',checks/'medical_competition_independent.json')
    run(audit,'--medical-scope-source-root',provider,'--functions-results-root',functions,
        '--actual-fields-root',fields,'--output',checks/'medical_source_scope_names.json')
    if MAGNIT_SOURCE.is_file():
        run(audit,'--magnit-raw-source',results/'source_documents/commerce/locator_raw.json',
            '--magnit-curated',results/'magnit/physical_stores.json','--magnit-provider-root',results/'magnit',
            '--road-nodes-dir',source/TRANSPORT/'road_nodes','--graph-dir',graph,
            '--actual-fields-root',fields,'--output',checks/'magnit_source_routes_independent.json')
    if MAGNIT_SOURCE.is_file():
        run(audit,'--intercentre-root',results/'intercentre','--functions-results-root',results/'physical_official',
            '--output',checks/'intercentre_independent.json')
        if PRIMARY2010_TEXT.is_file():
            run('scripts/sgrt_saratov/primary2010_independent_checks.py',
                '--base-context',results/'context_physical_official',
                '--primary-context',results/'context_physical_official_primary2010',
                '--evidence',results/'primary2010/population_2010_evidence.parquet',
                '--comparison',results/'primary2010/physical_official_comparison',
                '--output',checks/'primary2010_physical_official_cohorts_independent.json')
    if PRIMARY2010_TEXT.is_file() and HISTORICAL_SCHOOL.is_file():
        run('scripts/sgrt_saratov/primary2010_independent_checks.py',
            '--base-context',results/'context_regional_supplement',
            '--primary-context',results/'context_primary2010',
            '--evidence',results/'primary2010/population_2010_evidence.parquet',
            '--comparison',results/'primary2010/comparison',
            '--output',checks/'primary2010_historical_supplement_cohorts_independent.json')
    for variant in ('regional_supplement','physical_official'):
        if not (results/variant).is_dir():continue
        run(audit,'--actual-fields-root',fields,'--functions-results-root',results/variant,
            '--baseline-provider-root',functions,'--full-cost-cache',full_cache,'--output',checks/(variant+'_functional_output_audit.json'))
        run(audit,'--actual-fields-root',fields,'--basic-centres-root',results/variant,
            '--output',checks/(variant+'_basic_centres_audit.json'))
        context_folder='context_'+variant
        run(audit,'--actual-fields-root',fields,'--functions-results-root',results/variant,
            '--unit-context-root',results/context_folder,'--output',checks/(variant+'_unit_demography_audit.json'))
    if PRIMARY2010_TEXT.is_file():
        for variant,context_folder in [('regional_supplement','context_primary2010'),('physical_official','context_physical_official_primary2010')]:
            if not (results/variant).is_dir():continue
            run(audit,'--actual-fields-root',fields,'--functions-results-root',results/variant,
                '--unit-context-root',results/context_folder,
                '--primary2010-evidence',results/'primary2010/population_2010_evidence.parquet',
                '--output',checks/(context_folder+'_unit_demography_audit.json'))
    for path in checks.glob('*.json'):require_audit(path)
    require_audit(results/'context/worker_field_independent_numeric.json')
    require_audit(results/'rural_routes/rural_school_transport_counterexamples.json')
    actual=control(results);write(work/'actual_control.json',actual)
    if actual!=json.loads(EXPECTED.read_text()):
        # Preserve complete fresh values for an independent all-row numerical
        # comparison. A fingerprint mismatch never grants publication and is
        # never repaired by fitting counts or silently relaxing tolerances.
        with zipfile.ZipFile(work/'unpublished_mismatch_results.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for path in scientific_files(results):
                z.write(path,'results/'+path.relative_to(results).as_posix())
            z.write(work/'actual_control.json','controls/actual_control.json')
            z.write(EXPECTED,'controls/expected_control.json')
            z.writestr('UNPUBLISHED.txt','Diagnostic fresh outputs only. Expected all-row control did not match; no release or scientific publication was created.\n')
        raise ValueError('Fresh cloud outputs differ from independently completed local calculation; unpublished full outputs retained for independent comparison')
    subprocess.run(['node',str(REPO/'scripts/sgrt_saratov/render_figures.mjs'),
        '--results',str(results),'--output',str(results/'figures'),'--source-commit',commit,
        '--require-clean-producer'],cwd=REPO,check=True)
    figure_proof=json.loads((results/'figures/render_proof.json').read_text())
    if figure_proof.get('public_dataset_qa') is not False or len(figure_proof.get('figures',[]))!=4:
        raise ValueError('Four source-rendered figures with explicit scope required')
    built=package(work,commit);release_id=draft(built,commit)
    write(work/'draft.json',{'release_id':release_id,'release_tag':TAG,'source_commit':commit,'draft':True,
        'publication_requires_separate_byte_verification':True})
    return release_id


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-commit');p.add_argument('--workdir',type=Path)
    p.add_argument('--control-results',type=Path);p.add_argument('--control-output',type=Path)
    a=p.parse_args()
    if a.control_results:
        if not a.control_output:p.error('--control-output required')
        write(a.control_output,control(a.control_results))
    else:
        if not a.source_commit or not a.workdir:p.error('--source-commit and --workdir required')
        print(json.dumps({'draft_release_id':build(a.workdir,a.source_commit)}))

if __name__=='__main__':main()
