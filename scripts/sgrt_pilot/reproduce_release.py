#!/usr/bin/env python3
"""Recompute and package the dated functional pilot using public, hash-pinned inputs.

No credential, upload, remote-storage workaround or Git mutation is performed.
GitHub Actions can publish built/* with its ordinary contents-write GITHUB_TOKEN
AFTER this command succeeds. The produced catalogue contains the new archive
hashes; timestamps and Parquet bytes need not match a previous machine's run.
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

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'scripts/sgrt_pilot'
HISTORICAL = 'research/sgrt_word_completion_20261021'
ROADS = HISTORICAL + '/transport/cycle06_network2021_access_v2'
DATA_INPUTS = [
    HISTORICAL + '/axis/full_settlement_axis.parquet',
    HISTORICAL + '/medical/history_20210101/osm_medical_inventory.parquet',
    HISTORICAL + '/education/education_objects_2021.parquet',
    HISTORICAL + '/medical/udmurt_official_2025/physical_fap_inventory.parquet',
    HISTORICAL + '/validation/medical_territories_2024_all_rows.parquet',
]
OVERLAY = 'publication/stage71/applied_primary_population_source_overlay_2010.csv.gz'
AUDIT = HISTORICAL + '/analysis/node_source2010_recovery_audit.parquet'
LEGACY_NODES = HISTORICAL + '/model_inputs_cycle07/institutional_mass477_v2/computed/effective_full_nodes.parquet'
MATCHES = DATA_INPUTS + [OVERLAY, AUDIT, LEGACY_NODES,
    ROADS + '/route_origin_index.parquet', ROADS + '/route_destination_index.parquet',
    ROADS + '/candidate_travel_times_parts/*', ROADS + '/graph_npz_parts/*']
STAGES = ('fetch', 'official', 'prepare', 'demography', 'transport', 'models', 'validation', 'maps', 'package')
OFFICIAL = {
    'udmurt_fap_internet_2025.xlsx': {
        'url': 'https://rmiac18.ru/upload/iblock/951/ip0qw4d8o7jfyels8z0quirpq4g39zlv/5.-Prilozhenie-5-Internet-v-FAP.xlsx',
        'bytes': 90097,
        'sha256': '34322c8ef538efa79617af0f80ecc330c99d7f60539216478ef4e6f64dcd070c'},
    'medical_territories_2024.xls': {
        'url': 'https://lofoms.spb.ru/files/reshenie_2023_15_pril3_1.xls?1',
        'bytes': 1565184,
        'sha256': 'efad8790b5339bdc4b1dfa94d60f590ff8bebe3a9c2828bbad725440d0ebb61b'},
}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(script, *arguments):
    command = [sys.executable, str(SCRIPTS/script), *map(str, arguments)]
    print('RUN', ' '.join(command), flush=True)
    subprocess.run(command, cwd=REPO, check=True)


def download_official(root):
    root.mkdir(parents=True, exist_ok=True)
    for name, source in OFFICIAL.items():
        target = root/name
        if target.exists():
            if target.stat().st_size != source['bytes'] or sha256(target) != source['sha256']:
                raise ValueError('Existing dated official source differs: ' + name)
            continue
        temporary = target.with_suffix(target.suffix+'.partial')
        for attempt in range(3):
            try:
                request = urllib.request.Request(source['url'], headers={'User-Agent': 'sgrt-pilot-reproduction/1'})
                # Default networking/proxy settings are respected without modification.
                with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as output:
                    if response.status != 200:
                        raise ValueError('Official source HTTP status is not200')
                    shutil.copyfileobj(response, output, 4*1024*1024)
                if temporary.stat().st_size != source['bytes'] or sha256(temporary) != source['sha256']:
                    raise ValueError('Official source changed; inspect as a new dated version: ' + name)
                temporary.replace(target)
                break
            except (OSError, TimeoutError):
                temporary.unlink(missing_ok=True)
                if attempt == 2:
                    raise
                time.sleep(3*(attempt+1))
        print('Official input verified:', name, source['sha256'], flush=True)


def plan(catalog):
    """Machine-readable preflight; no downloads or numerical dependencies required."""
    import fnmatch
    c = json.loads(catalog.read_text())
    rows = [r for r in c['files'] if any(fnmatch.fnmatchcase(r['path'], m) for m in MATCHES)]
    missing = [m for m in MATCHES if not any(fnmatch.fnmatchcase(r['path'],m) for r in rows)]
    if missing:
        raise ValueError('Required historical inputs absent from catalogue: '+repr(missing))
    asset_names = {c['objects'][r['blob']].get('asset') for r in rows} - {None}
    assets = [a for a in c['assets'] if a['asset'] in asset_names]
    return {'stages': list(STAGES), 'historical_files': len(rows),
            'historical_input_bytes': sum(r['bytes'] for r in rows),
            'historical_download_bytes': sum(a['bytes'] for a in assets),
            'archives': [a['asset'] for a in assets],
            'population_release_fetched_separately': True,
            'official_sources': OFFICIAL,
            'transport_algorithm': 'Decode old75parts, route only missing source-backed external providers to180min; preserve old180/360min scope',
            'routing_estimate_minutes': '10–20 depending on runner; previous3583-destination supplement613seconds',
            'model_case_count': 9,
            'byte_identical_archive_promised': False}


def reproduce(args):
    import pandas as pd
    work = args.workdir.resolve()
    inputs = work/'inputs'
    outputs = work/'outputs'
    cache = work/'download-cache'
    built = work/'built'
    data = outputs/'data'
    transport = outputs/'transport'
    models = outputs/'model'
    population = inputs/'data/population'
    official = inputs/'official'
    for directory in (inputs, outputs):
        directory.mkdir(parents=True, exist_ok=True)
    start = STAGES.index(args.start_at)
    stop = STAGES.index(args.stop_after)
    if start > stop:
        raise ValueError('--start-at is after --stop-after')
    def active(stage):
        return start <= STAGES.index(stage) <= stop

    if active('fetch'):
        fetch = [sys.executable, str(REPO/'scripts/research_data.py'), 'fetch', '--catalog', str(args.catalog),
                 '--dest', str(inputs), '--cache', str(cache)]
        subprocess.run(fetch+['--profile', 'population'], cwd=REPO, check=True)
        # One union fetch avoids redownloading archives shared by unrelated paths.
        historical = fetch+['--profile', 'all']
        for pattern in MATCHES:
            historical += ['--match', pattern]
        subprocess.run(historical, cwd=REPO, check=True)
        subprocess.run([sys.executable, str(REPO/'scripts/verify_population_base.py'), '--root', str(inputs)], cwd=REPO, check=True)
    if active('official'):
        download_official(official)
    if active('prepare'):
        run('prepare_data.py', '--population-root', inputs, '--input-root', inputs,
            '--output', data, '--catalog', args.catalog, '--udmurt-workbook', official/'udmurt_fap_internet_2025.xlsx')
        summary = json.loads((data/'preparation_summary.json').read_text())
        if sum(summary['pilot_rows_by_region'].values()) != 13968 or summary['primary_2021_with_accepted_point'] != 153800:
            raise ValueError('Prepared census frame changed; inspect before publication')
        if summary['official_udmurt_spatial_settlements'] != 478:
            raise ValueError('Official planning-list crosswalk changed')
    if active('demography'):
        run('audit_demography2010.py', '--population-dir', population, '--accepted-overlay', inputs/OVERLAY,
            '--historical-root', inputs/HISTORICAL, '--output', outputs/'demography')
    if active('transport'):
        run('transport.py', 'extract', '--inputs', inputs, '--output', transport,
            '--catalog', args.catalog, '--wide', population/'settlements_census_wide.parquet',
            '--legacy-nodes', inputs/LEGACY_NODES)
        supplies = [data/'supply_all_2021.parquet', data/'supply_official_udmurt_2025.parquet', data/'supply_context2021.parquet']
        run('transport.py', 'prepare', '--output', transport, '--supply', *supplies, '--max-minutes', '180')
        run('transport.py', 'route', '--inputs', inputs, '--output', transport,
            '--origins', inputs/ROADS/'route_origin_index.parquet',
            '--providers', transport/'missing_providers_external.csv', '--provider-column', 'center_id',
            '--max-minutes', '180', '--finite-only', '--output-name', 'supplemental_all_pilots_external')
        run('transport.py', 'combine', '--output', transport, '--supply', *supplies,
            '--supplement', transport/'supplemental_all_pilots_external.parquet')
        # Preserve compact inputs for graph-only reproduction in the new release.
        minimal = pd.read_parquet(inputs/LEGACY_NODES,
            columns=['id','root','source_record_id_2021','name','region','lat','lon'])
        minimal.to_parquet(transport/'legacy_nodes_minimal.parquet', index=False, compression='zstd')
        for filename in ('route_origin_index.parquet', 'route_destination_index.parquet'):
            shutil.copyfile(inputs/ROADS/filename, transport/filename)
        shutil.copytree(inputs/ROADS/'graph_npz_parts', transport/'graph/graph_npz_parts', dirs_exist_ok=True)
    if active('models'):
        run('run_scenarios.py', '--data', data, '--costs', transport/'combined_costs.parquet',
            '--output', models, '--reference-all-regions')
    if active('validation'):
        run('validate_medical_source.py', '--raw', official/'medical_territories_2024.xls',
            '--extracted', data/'medical_attachments_lo_2024.parquet', '--output', outputs/'validation')
        run('independent_checks.py', '--data', data, '--population', population,
            '--output', outputs/'independent', '--transport', transport, '--models', models)
        run('compare_medical_attachments.py', '--attachments', data/'medical_attachments_lo_2024.parquet',
            '--quarantine', outputs/'independent/medical_context_quarantine.parquet',
            '--supply', data/'supply_all_2021.parquet',
            '--outcomes', models/'medical_presence/scenario_outcomes.parquet',
            '--outcomes', models/'medical_count/scenario_outcomes.parquet', '--output', outputs/'validation')
    if active('maps'):
        paths = sorted(models.rglob('scenario_outcomes.parquet'))
        if len(paths) != 9:
            raise ValueError(f'Expected9 dated case outputs, got{len(paths)}')
        for path in paths:
            case = path.parent.relative_to(models)
            types = outputs/'types'/case
            run('typology.py', '--assignments', path, '--settlements', data/'settlements_all_2021.parquet',
                '--context-settlements', data/'external_context_anchors.parquet',
                '--wide', population/'settlements_census_wide.parquet', '--out', types, '--reference-only')
            run('visualize.py', '--settlements', data/'settlements_all_2021.parquet',
                '--context-settlements', data/'external_context_anchors.parquet', '--outcomes', path,
                '--types', types/'candidate_zone_types.parquet', '--out', outputs/'maps'/case,
                '--functions', 'education' if path.parent.name.startswith('school') else 'healthcare',
                '--source-label', ('План подключения ФАП/ФП: каталог 2025, план 2026; работа объектов не подтверждена'
                    if path.parent.name == 'official_udmurt_selected_plan' else 'OSM, снимок 2021; неполное наличие объектов'))
        run('visualize.py', '--settlements', data/'settlements_all_2021.parquet',
            '--attachments', data/'medical_attachments_lo_2024.parquet',
            '--quarantine', outputs/'independent/medical_context_quarantine.parquet',
            '--supply', data/'supply.parquet', '--official', data/'supply_official_udmurt_2025.parquet', '--out', outputs/'maps')
        run('build_atlas.py', '--maps', outputs/'maps', '--output', outputs/'pilot_atlas.pdf')
    if active('package'):
        run('check_release_outputs.py', '--root', outputs)
        payload = work/'payload'
        destination = payload/'sgrt/pilot20261024'
        if destination.exists():
            raise ValueError('Payload already exists; use a new workdir or remove only your own previous build')
        destination.mkdir(parents=True)
        # Raw all-pair supplement is not shipped; it contains mostly unknown costs.
        # Default population base remains its own release, not a second copy here.
        shutil.copytree(outputs, destination/'outputs', ignore=shutil.ignore_patterns(
            '*.partial', '__pycache__', 'pilot_costs.parquet', 'supplemental*.parquet',
            'transport_census_crosswalk.parquet', 'missing_providers*.csv'))
        for relative in DATA_INPUTS+[OVERLAY, AUDIT]:
            target = destination/'inputs'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(inputs/relative, target)
        shutil.copytree(official, destination/'inputs/official')
        run('package_release.py', '--payload-root', payload, '--output', built,
            '--tag', args.tag, '--source-commit', args.source_commit)
        shutil.copyfile(outputs/'pilot_atlas.pdf', built/'pilot_atlas.pdf')
        # Built catalogue is the authority for new binary hashes, never the old one.
        subprocess.run([sys.executable, str(REPO/'scripts/research_data.py'), 'verify', '--catalog', str(built/'pilot_catalog.json'),
                        '--profile', 'core', '--dest', str(payload)], cwd=REPO, check=True)
        print(json.dumps({'built':str(built),'assets':['sgrt-pilot-data.zip','pilot_catalog.json','pilot_atlas.pdf'],
                          'all_scientific_checks_passed':True, 'uploaded':False},ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--catalog', type=Path, default=REPO/'data/catalog.json')
    parser.add_argument('--start-at', choices=STAGES, default='fetch')
    parser.add_argument('--stop-after', choices=STAGES, default='package')
    parser.add_argument('--plan', action='store_true', help='Print exact download scope without executing')
    args=parser.parse_args()
    args.catalog=args.catalog.resolve()
    if args.plan:
        print(json.dumps(plan(args.catalog),ensure_ascii=False,indent=2))
    else:
        reproduce(args)

if __name__=='__main__':
    main()
