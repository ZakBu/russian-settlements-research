"""Clean frozen-source rebuild and guarded publication of repaired level-zero centres."""
from __future__ import annotations
import argparse
import gc
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import urllib.request

from cloud_centre_rebuild import fetch, run, sha, REPO, SCRIPT, REPOSITORY, ROAD_PREFIX, PILOT_PREFIX
from pack_identity_results import TAG, SOURCE_ZIP

DRAFT_RELEASE_ID = 424116040
MAIN = 'daily_20_school30_wb'
CONTROL_DEFAULT = REPO / 'research_context/analysis_snapshots/identity_model_control_20261026.json'
SOURCE_ASSETS = {'source-places.zip', 'source-acquisition.json'}
SOURCE_ASSET_IDS = {'source-places.zip': 677846564, 'source-acquisition.json': 677846563}
COORDINATE_HOLDS = REPO / 'references/provenance/coordinate_holds_20261026.json'


def retain_official_coordinate_evidence(manifest, output):
    """Retrieve the pinned official PDF; never substitute a live revised document."""
    records = json.loads(Path(manifest).read_text())['records']
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    proofs = []
    for record in records:
        source = record.get('official_pdf_source')
        if not source:
            continue
        if source.get('status') != 200:
            raise ValueError('Pinned official coordinate evidence was not HTTP200')
        target = output / (source['sha256'] + '.pdf')
        if not target.exists():
            request = urllib.request.Request(source['url'], headers={'User-Agent': 'sgrt-reproducible-research/1.0'})
            with urllib.request.urlopen(request, timeout=120) as response:
                if response.status != 200:
                    raise ValueError('Official coordinate evidence HTTP status changed')
                content = response.read(source['bytes'] + 1)
            if len(content) != source['bytes']:
                raise ValueError('Official coordinate evidence size changed')
            import hashlib
            if hashlib.sha256(content).hexdigest() != source['sha256']:
                raise ValueError('Official coordinate evidence SHA changed')
            temporary = target.with_suffix('.partial')
            temporary.write_bytes(content)
            temporary.replace(target)
        if target.stat().st_size != source['bytes'] or sha(target) != source['sha256']:
            raise ValueError('Retained official coordinate PDF was modified')
        proofs.append({'source_record_id': record['source_record_id'], **source,
                       'retained_filename': target.name})
    (output / 'official_coordinate_evidence.json').write_text(json.dumps(proofs, ensure_ascii=False, indent=2) + '\n')
    return proofs


def read_source_release(*, expected_asset_ids=None):
    """Read immutable inputs from either their draft or sealed public release.

    Result assets may coexist with the retained raw sources after publication.
    This guard does not authorize upload, editing or publication.
    """
    release = json.loads(subprocess.check_output(
        ['gh', 'api', f'repos/{REPOSITORY}/releases/{DRAFT_RELEASE_ID}'], text=True))
    assets = {a['name']: a for a in release['assets']}
    if release['tag_name'] != TAG:
        raise ValueError('The retained source release has a different tag')
    if not SOURCE_ASSETS <= set(assets):
        raise ValueError('Source release lacks the two retained raw source assets')
    if assets[SOURCE_ZIP['asset']]['size'] != SOURCE_ZIP['bytes']:
        raise ValueError('Retained raw source size differs')
    for name, asset_id in (expected_asset_ids or {}).items():
        if name not in SOURCE_ASSETS or assets[name].get('id') != asset_id:
            raise ValueError('A retained raw source asset was replaced: ' + name)
    return release


def retained_source_draft():
    """Write guard: only the original two-input unpublished draft is mutable."""
    release = read_source_release(expected_asset_ids=SOURCE_ASSET_IDS)
    if not release['draft'] or {a['name'] for a in release['assets']} != SOURCE_ASSETS:
        raise ValueError('Require the existing draft with exactly the two retained source assets; never overwrite assets')
    return release


def restore_source_zip(work):
    read_source_release(expected_asset_ids=SOURCE_ASSET_IDS)
    dest = work / 'frozen_place_source'
    dest.mkdir(parents=True)
    subprocess.run(['gh', 'release', 'download', TAG, '--repo', REPOSITORY,
                    '--pattern', 'source-places.zip', '--pattern', 'source-acquisition.json',
                    '--dir', str(dest)], check=True)
    archive = dest / SOURCE_ZIP['asset']
    if archive.stat().st_size != SOURCE_ZIP['bytes'] or sha(archive) != SOURCE_ZIP['sha256']:
        raise ValueError('Downloaded frozen raw source archive differs')
    acquisition = json.loads((dest / 'source-acquisition.json').read_text())
    if acquisition['source_members_verified'] != 50 or acquisition['archive']['sha256'] != SOURCE_ZIP['sha256']:
        raise ValueError('Retained source-acquisition proof differs')
    # Check source identity again after transfer, without restricting read-only
    # reproduction to the pre-publication lifecycle of the release.
    read_source_release(expected_asset_ids=SOURCE_ASSET_IDS)
    extracted = work / 'place_source'
    extracted.mkdir()
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            path = Path(member.filename)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe source archive path')
        if source.testzip() is not None: raise ValueError('Raw source archive CRC failure')
        source.extractall(extracted)
    provenance = REPO / 'references/provenance/geofabrik_place_polygons_20261026.json'
    if sha(extracted / 'provenance.json') != sha(provenance):
        raise ValueError('Frozen raw source provenance differs from committed input')
    return extracted


def refresh_place_guards(source, reference, output):
    """Refresh all mapped/held geometries in a separate, memory-releasing process."""
    sys.path.insert(0, str(REPO))
    import pandas as pd
    from scripts.sgrt_zero.cartographic_identity import recompute_other_positive_places
    if source.resolve() == output.resolve(): raise ValueError('Never overwrite a frozen polygon input')
    temporary = output.with_name(output.name + '.partial')
    if output.exists() or output.is_symlink() or temporary.exists():
        raise FileExistsError('Guard refresh requires a new output file')
    before = {str(p): sha(p) for p in [source, reference]}
    original = pd.read_parquet(source)
    refreshed = recompute_other_positive_places(original, pd.read_parquet(reference))
    guard_columns = {'other_positive_census_places', 'other_positive_census_place_ids_json',
                     'physical_neighbour_guard_uses_budget_credit', 'physical_neighbour_guard_uses_analysis_origin'}
    retained = [c for c in original if c not in guard_columns]
    pd.testing.assert_frame_equal(original[retained], refreshed[retained], check_exact=True)
    if before != {str(p): sha(p) for p in [source, reference]}:
        raise ValueError('Polygon/ref input changed during physical-neighbour refresh')
    output.parent.mkdir(parents=True, exist_ok=True)
    refreshed.to_parquet(temporary, index=False, compression='zstd')
    temporary.rename(output)
    proof = {'all_geometry_records_refreshed': len(refreshed),
             'owners_geometries_and_other_source_fields_unchanged': True,
             'physical_neighbour_guard_uses_budget_credit': False,
             'physical_neighbour_guard_uses_analysis_origin': False,
             'input_sha256': before, 'output_sha256': sha(output),
             'guard_code_sha256': sha(SCRIPT / 'cartographic_identity.py')}
    output.with_suffix('.guard_refresh.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))
    return proof


def build(work, commit, control):
    if work.exists() and any(work.iterdir()): raise ValueError('Use an empty rebuild work directory')
    if work.resolve().is_relative_to(REPO): raise ValueError('Generated data must stay outside Git')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() != commit:
        raise ValueError('Require the exact checked-out scientific commit')
    if not control.is_file(): raise FileNotFoundError('Commit the independently computed scientific control first: ' + str(control))
    work.mkdir(parents=True, exist_ok=True)
    logs = work / 'logs'; data = work / 'dependencies'; cache = work / 'download-cache'
    extracted = restore_source_zip(work)
    run(logs, 'restore_frozen_place_table', SCRIPT / 'acquire_geofabrik_places.py',
        '--provenance', REPO / 'references/provenance/geofabrik_place_polygons_20261026.json',
        '--output', extracted, '--offline')
    fetch(logs, 'restore_zero', 'data/zero_catalog_20261025.json', data, cache)
    fetch(logs, 'restore_graph', 'data/pilot_catalog_20261024.json', data, cache,
          [PILOT_PREFIX + '/graph/graph_npz_parts/*.bin', PILOT_PREFIX + '/route_origin_index.parquet'])
    fetch(logs, 'restore_road_coordinates', 'data/catalog.json', data, cache,
          [ROAD_PREFIX + '/*.parquet'], profile='all')
    bundle = data / 'sgrt/zero20261025'; inputs = bundle / 'inputs'
    reference = bundle / 'context/analysis_reference.parquet'
    sys.path.insert(0, str(REPO))
    from scripts.sgrt_zero.reproduce import verify_bundle
    before = verify_bundle(bundle)
    frozen_manifest_sha = sha(bundle / 'checksums.json')
    population_catalog_sha = sha(REPO / 'data/catalog.json')
    base = work / 'base_sources'
    run(logs, 'rebuild_base_education', SCRIPT / 'education.py',
        '--current', inputs / 'education_current.parquet', '--historical', inputs / 'education_history.parquet',
        '--official', inputs / 'preschool.parquet', '--reference', reference, '--legacy', inputs / 'legacy.parquet',
        '--city-context', bundle / 'context/city_context_origins.parquet', '--output', base / 'education')
    run(logs, 'rebuild_base_commerce', SCRIPT / 'commerce.py',
        '--osm', inputs / 'commerce.parquet', '--wb', inputs / 'frozen_public_sources/wildberries.json.gz',
        '--reference', reference, '--legacy', inputs / 'legacy.parquet', '--population', inputs / 'population.parquet',
        '--wb-snapshot', '2026-10-25', '--output', base / 'commerce')
    boundary_build = work / 'boundary_build'
    run(logs, 'named_place_polygons', SCRIPT / 'geofabrik_identity.py',
        '--places', extracted / 'places_polygons_v2.parquet', '--reference', reference,
        '--allow-nominal-outside', '--output', boundary_build)
    refreshed_boundaries = work / 'boundary_refreshed'
    run(logs, 'all_geometry_physical_neighbour_guards', Path(__file__), '--source-commit', commit,
        '--refresh-place-guards', boundary_build / 'locality_polygons.parquet',
        '--reference', reference, '--output', refreshed_boundaries / 'locality_polygons.parquet')
    boundaries = work / 'boundaries'
    run(logs, 'named_nested_locality_masks', SCRIPT / 'nested_locality_masks.py',
        '--inventory', refreshed_boundaries / 'locality_polygons.parquet', '--reference', reference,
        '--coordinate-holds', COORDINATE_HOLDS, '--output', boundaries)
    shutil.copyfile(boundary_build / 'polygon_rejections.parquet', boundaries / 'polygon_rejections.parquet')
    boundary_manifest = json.loads((boundaries / 'manifest.json').read_text())
    shutil.copyfile(refreshed_boundaries / 'locality_polygons.guard_refresh.json',
                    boundaries / 'locality_polygons.guard_refresh.json')
    shutil.copyfile(boundary_build / 'manifest.json', boundaries / 'raw_builder_manifest.json')
    boundary_manifest['all_geometry_guard_refresh'] = 'locality_polygons.guard_refresh.json'
    boundary_manifest['final_inventory_sha256'] = sha(boundaries / 'locality_polygons.parquet')
    (boundaries / 'manifest.json').write_text(json.dumps(boundary_manifest, ensure_ascii=False, indent=2) + '\n')
    sources = work / 'model_sources'
    run(logs, 'repair_source_identities', SCRIPT / 'repair_source_identities.py',
        '--bundle', bundle, '--education', base / 'education', '--commerce', base / 'commerce',
        '--polygons', boundaries / 'locality_polygons.parquet', '--output', sources)
    graph = data / PILOT_PREFIX / 'graph'; road_nodes = data / ROAD_PREFIX
    geometry = work / 'fresh_geometry'
    domains = [('education', 'physical_sites.parquet', 'np_supply.parquet'),
               ('commerce', 'sites.parquet', 'supply.parquet'),
               ('health', 'physical_sites.parquet', 'np_supply.parquet'),
               ('food_host', 'sites.parquet', 'supply.parquet')]
    for domain, sites, supply in domains:
        run(logs, 'fresh_geometry_' + domain, SCRIPT / 'transport.py',
            '--sites', sources / domain / sites, '--np-supply', sources / domain / supply,
            '--endpoints', bundle / 'routes/endpoints.parquet', '--road-nodes', road_nodes,
            '--road-origins', data / PILOT_PREFIX / 'route_origin_index.parquet',
            '--catalog', REPO / 'data/catalog.json', '--graph-dir', graph,
            '--prepare-only', '--output', geometry / domain)
    common = ['--bundle', bundle, '--education', sources / 'education', '--commerce', sources / 'commerce',
              '--medical', sources / 'health', '--food-host', sources / 'food_host',
              '--education-cache', geometry / 'education/provider_road_seeds.parquet',
              '--commerce-cache', geometry / 'commerce/provider_road_seeds.parquet',
              '--medical-cache', geometry / 'health/provider_road_seeds.parquet',
              '--food-host-cache', geometry / 'food_host/provider_road_seeds.parquet',
              '--allow-local-presence-without-geometry', '--graph-dir', graph]
    routes = work / 'routes'
    run(logs, 'reroute_all12', SCRIPT / 'reroute_corrected.py', *common, '--output', routes)
    run(logs, 'new_grocery_union', SCRIPT / 'combine_nearest.py',
        '--component', 'osm_grocery_2021=' + str(routes / 'nearest/daily_grocery.parquet'),
        '--component', 'current_food_host_2026=' + str(routes / 'nearest/daily_grocery_current_retail_host.parquet'),
        '--output', routes / 'derived_nearest/daily_grocery_evidence_union.parquet')
    run(logs, 'independent_all12_forward_checks', SCRIPT / 'verify_corrected_routes.py', *common, '--routes', routes)
    import pandas as pd
    quality = pd.read_parquet(routes / 'endpoint_network_quality.parquet')
    quality['audit_component_size'] = quality.verified_component_node_count
    inventory = routes / 'endpoint_inventory.parquet'
    quality.to_parquet(inventory, index=False, compression='zstd')
    del quality; gc.collect()
    analysis = work / 'analysis'
    run(logs, 'direct_centres', SCRIPT / 'centre_scenarios.py', '--bundle', bundle,
        '--corrected-routes', routes, '--endpoints', inventory, '--output', analysis / 'scenarios',
        '--coordinate-holds', COORDINATE_HOLDS, '--scenarios', MAIN)
    scenario = analysis / 'scenarios' / MAIN
    registry = work / 'registry'
    run(logs, 'level0_registry', SCRIPT / 'level0_centres.py', '--scenario', scenario, '--output', registry)
    verifier = SCRIPT / 'verify_level0_registry.py'
    if not verifier.exists(): raise FileNotFoundError('Commit the independent level-zero registry verifier before publication')
    run(logs, 'independent_level0_registry', verifier, '--scenario', scenario, '--registry', registry,
        '--reference', reference, '--coordinate-holds', COORDINATE_HOLDS,
        '--output', analysis / 'independent_level0_check.json')
    run(logs, 'all_scientific_identity_controls', SCRIPT / 'identity_control.py',
        '--sources', sources, '--routes', routes, '--scenario', scenario, '--registry', registry,
        '--polygons', boundaries / 'locality_polygons.parquet', '--expected', control,
        '--output', analysis / 'cloud_identity_control.json')
    (analysis / 'scientific_verification.json').write_text(json.dumps({
        'all_source_offer_rows_and_eligibility_equal': True, 'all12_routing_layers_equal': True,
        'all_admitted_choices_equal': True, 'all_level0_centre_and_member_identities_equal': True,
        'independent_registry_recheck_completed': True, 'expected_control_sha256': sha(control),
        'source_commit': commit, 'numeric_decimal_places': 8,
        'observed_journeys_established': False}, indent=2) + '\n')
    atlas_args = ['--registry', registry, '--scenario', scenario, '--reference', reference, '--output', analysis / 'figures']
    baseline = REPO / 'research_context/analysis_snapshots/level0_pre_identity_registry_20261026.json'
    if baseline.is_file(): atlas_args += ['--before-summary', baseline]
    run(logs, 'six_page_atlas', SCRIPT / 'identity_repair_atlas.py', *atlas_args)
    if (before != verify_bundle(bundle) or sha(bundle / 'checksums.json') != frozen_manifest_sha
            or sha(REPO / 'data/catalog.json') != population_catalog_sha):
        raise ValueError('Frozen population or source inputs changed')
    (analysis / 'immutable_inputs_check.json').write_text(json.dumps({
        'verified_frozen_input_files': before, 'frozen_bundle_before_equals_after': True,
        'frozen_manifest_sha256': frozen_manifest_sha, 'population_default_catalog_unchanged': True,
        'source_places_zip_sha256': SOURCE_ZIP['sha256']}, indent=2) + '\n')
    for domain, _, _ in domains:
        target = analysis / 'source_readout' / domain; target.mkdir(parents=True)
        shutil.copyfile(sources / domain / 'summary.json', target / 'summary.json')
    shutil.copyfile(sources / 'summary.json', analysis / 'source_readout/summary.json')
    retain_official_coordinate_evidence(COORDINATE_HOLDS, analysis / 'external_evidence')
    shutil.copytree(logs, analysis / 'cloud_logs')
    built = work / 'built'
    run(logs, 'package', SCRIPT / 'pack_identity_results.py', '--analysis', analysis, '--routes', routes,
        '--registry', registry, '--boundaries', boundaries, '--output', built, '--source-commit', commit)
    shutil.copyfile(analysis / 'figures/identity_repair_atlas.pdf', built / 'identity_repair_atlas.pdf')
    shutil.copyfile(analysis / 'figures/01_level0_country.png', built / 'preview.png')
    shutil.copyfile(registry / 'level0_centres.csv', built / 'level0_centres.csv')
    manifest = json.loads((built / 'manifest.json').read_text())
    counts = manifest['registry_counts']
    format_count = lambda value: f'{value:,}'.replace(',', ' ')
    notes = (f'Исправлена принадлежность учреждений населённым пунктам и пересчитаны центры нулевого уровня.\n\n'
        f'В модели {format_count(counts["registered_level0_centres"])} центров с внешними участниками; '
        f'у {format_count(counts["full_three_function_centres_with_external_participants"])} записаны три базовые функции. '
        f'Собственное предложение и совпадение внешних направлений показаны раздельно. '
        f'Это пересекающиеся прямые окружения, не исключительное районирование страны и не наблюдённые поездки.\n\n'
        f'Облачный повтор восстановил 50 закреплённых исходных компонентов, заново подготовил четыре области источников '
        f'и дорожную геометрию, пересчитал 12 слоёв. Сверены все владельцы и признаки допуска поставщиков, '
        f'все выбранные направления и все зарегистрированные пары центра/участника.\n\n'
        f'Исходный коммит: `{commit}`.\nАрхив: `{manifest["archive"]["bytes"]}` байт.\n'
        f'SHA256: `{manifest["archive"]["sha256"]}`.\n\n'
        f'Сырые place-полигоны сохранены отдельным source-places.zip; картографическое основание не объявляется юридическим адресом. '
        f'Готовая связанная база переписей остаётся основным набором для скачивания.\n')
    (built / 'release_notes.md').write_text(notes, encoding='utf-8')
    return manifest


def publish(built, commit):
    release = retained_source_draft()
    initial = {a['name']: a for a in release['assets']}
    manifest = json.loads((built / 'manifest.json').read_text())
    if manifest['source_commit'] != commit: raise ValueError('Publication target differs from frozen producer')
    archive = built / manifest['archive']['asset']
    if archive.stat().st_size != manifest['archive']['bytes'] or sha(archive) != manifest['archive']['sha256']:
        raise ValueError('Result archive differs from verified manifest')
    with zipfile.ZipFile(archive) as result:
        prefix = manifest['archive_root']
        actual = json.loads(result.read(prefix + 'analysis/cloud_identity_control.json'))
        expected = json.loads(CONTROL_DEFAULT.read_text())
        if actual != expected: raise ValueError('Packed all-row scientific control differs from committed independent result')
        verification = json.loads(result.read(prefix + 'analysis/scientific_verification.json'))
        if verification.get('source_commit') != commit or not all(verification.get(key) is True for key in [
                'all_source_offer_rows_and_eligibility_equal', 'all12_routing_layers_equal',
                'all_admitted_choices_equal', 'all_level0_centre_and_member_identities_equal',
                'independent_registry_recheck_completed']):
            raise ValueError('The packed rebuild has no complete scientific verification')
        verify_standalone_registry(built, manifest, result)
    assets = [archive, built / 'manifest.json', built / 'identity_repair_atlas.pdf', built / 'preview.png',
              built / 'level0_centres.csv']
    if any(not path.is_file() for path in assets): raise ValueError('Five complete result assets are required')
    subprocess.run(['gh', 'release', 'upload', TAG, *map(str, assets), '--repo', REPOSITORY], check=True)
    uploaded = json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPOSITORY}/releases/{DRAFT_RELEASE_ID}'], text=True))
    expected = {name: a['size'] for name, a in initial.items()}
    expected.update({p.name: p.stat().st_size for p in assets})
    if not uploaded['draft'] or {a['name']: a['size'] for a in uploaded['assets']} != expected:
        raise ValueError('Draft assets differ; no replacement or partial publication is allowed')
    for item in uploaded['assets']:
        if item['name'] in initial and item['id'] != initial[item['name']]['id']:
            raise ValueError('Retained raw source asset was replaced')
    subprocess.run(['gh', 'release', 'edit', TAG, '--repo', REPOSITORY,
        '--notes-file', str(built / 'release_notes.md'), '--target', commit, '--draft=false', '--latest=false',
        '--title', 'Центры нулевого уровня: исправленные привязки и прямое окружение — 26 октября 2026'], check=True)
    print(json.dumps({'published_tag': TAG, 'source_commit': commit, 'assets': expected, 'archive': manifest['archive']}))


def verify_standalone_registry(built, manifest, archive):
    """The public map CSV must be the same immutable registry as inside the ZIP."""
    import hashlib
    assets = manifest.get('standalone_assets', {})
    if set(assets) != {'level0_centres.csv'}:
        raise ValueError('Exactly the standalone centre registry CSV is required')
    spec = assets['level0_centres.csv']
    expected_member = manifest['archive_root'] + 'registry/level0_centres.csv'
    if spec.get('asset') != 'level0_centres.csv' or spec.get('archive_member') != expected_member:
        raise ValueError('Standalone registry identity differs from the frozen archive')
    csv = Path(built) / 'level0_centres.csv'
    if not csv.is_file() or csv.stat().st_size != spec['bytes'] or sha(csv) != spec['sha256']:
        raise ValueError('Standalone registry size/SHA differs from the frozen manifest')
    with archive.open(expected_member) as stream:
        embedded_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    embedded = archive.getinfo(expected_member)
    if embedded.file_size != spec['bytes'] or embedded_sha != spec['sha256']:
        raise ValueError('Standalone registry differs from the archived registry')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-commit', required=True)
    p.add_argument('--workdir', type=Path)
    p.add_argument('--control', type=Path, default=CONTROL_DEFAULT)
    p.add_argument('--publish-built', type=Path)
    p.add_argument('--check-source-draft', action='store_true')
    p.add_argument('--refresh-place-guards', type=Path)
    p.add_argument('--reference', type=Path)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.check_source_draft: retained_source_draft()
    elif a.refresh_place_guards:
        if not a.reference or not a.output:p.error('--refresh-place-guards requires --reference and --output')
        refresh_place_guards(a.refresh_place_guards, a.reference, a.output)
    elif a.publish_built: publish(a.publish_built, a.source_commit)
    elif a.workdir: build(a.workdir.resolve(), a.source_commit, a.control.resolve())
    else: p.error('Choose --workdir, --publish-built or --check-source-draft')
