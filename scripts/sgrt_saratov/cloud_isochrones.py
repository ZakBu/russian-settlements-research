"""Rebuild inbound Saratov isochrones from pinned public bytes.

An independent completed local calculation supplies the expected semantic
control. Publication creates a new draft only; it neither overwrites releases
nor publishes an unchecked draft. Original national inputs stay in their
previous immutable releases instead of being duplicated in the new ZIP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_zero.cloud_common_systems import (
    REPOSITORY, acquire, clean_commit, releases, run, sha, verify, write,
)
from scripts.sgrt_zero.identity_control import table_hash
from scripts.sgrt_saratov.source_inventory import (
    TRANSPORT, REFERENCE, ENDPOINTS, EDGES, UNITS,
    BOUNDARY_URL, BOUNDARY_BYTES, BOUNDARY_SHA256,
)

TAG = 'sgrt-saratov-isochrones-20261028-v1'
EXPECTED = REPO/'research_context/analysis_snapshots/saratov_isochrones_control_20261028.json'
PBF_PREFIX = 'research/sgrt_word_completion_20261021/transport/cycle06_network2021/sources/'
PBF_NAME = 'roads2021_reference_complete.osm.pbf'
PBF_BYTES = 491143669
PBF_SHA256 = '294807be65aa2bf8061bd8eeb91350160523b34a30322dfa196eb0ce5b8d5520'
PROFILE_FOLDER = 'archive/sgrt_2026-10-18_21/sgrt_word_completion_20261021/transport/cycle06_network2021_access_v2/'
INPUTS = {
    'data/zero_catalog_20261025.json': [REFERENCE],
    'data/identity_catalog_20261026.json': [ENDPOINTS, EDGES],
    'data/common_systems_catalog_20261027.json': [UNITS],
    'data/catalog.json': [TRANSPORT+f'graph_npz_parts/part_{n:03d}.bin' for n in range(3)]
        + [TRANSPORT+f'road_nodes/part_{n:03d}.parquet' for n in range(24)]
        + [PBF_PREFIX+PBF_NAME+f'.part{n:03d}' for n in range(6)],
}
SLUGS = ('saratov', 'engels', 'balakovo', 'balashov', 'novouzensk', 'piterka')
STANDALONE = tuple(f'isochrones_bands_{slug}.geojson' for slug in SLUGS)
MAX_STANDALONE_BYTES = 20_000_000


def canonical(value):
    if isinstance(value, np.generic):
        return canonical(value.item())
    if isinstance(value, np.ndarray):
        return [canonical(v) for v in value.tolist()]
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    if isinstance(value, float):
        return round(value, 8)
    return value


def geometry_digest(geometry, grid):
    """Ignore ring/line ordering while retaining all geometric content."""
    if geometry is None:
        return None
    if not geometry.is_valid:
        raise ValueError('Invalid derived geometry')
    # Fingerprinting must not run a topology-changing precision overlay on the
    # delivered geometry. Round coordinates only in an in-memory copy, then
    # normalize order; validation and the independent overlay use the original.
    coordinates = shapely.get_coordinates(geometry)
    rounded = np.round(coordinates/grid)*grid
    normalized = shapely.normalize(shapely.set_coordinates(geometry, rounded))
    encoded = shapely.to_wkb(normalized, byte_order=1, include_srid=False)
    return hashlib.sha256(encoded).hexdigest()


def geometry_control(path):
    document = json.loads(Path(path).read_text())
    if document.get('type') != 'FeatureCollection' or not isinstance(document.get('features'), list):
        raise ValueError('A derived GeoJSON must be a FeatureCollection')
    rows = []
    identities = set()
    for index, feature in enumerate(document['features']):
        if feature.get('type') != 'Feature' or feature.get('geometry') is None:
            raise ValueError('A derived feature has no geometry')
        properties = feature.get('properties', {})
        identity = str(properties.get('id', properties.get('adm1_id', index)))
        if identity in identities:
            raise ValueError('Duplicate geometry identity: '+identity)
        identities.add(identity)
        geometry = shape(feature['geometry'])
        if geometry.geom_type not in {'Polygon', 'MultiPolygon'}:
            raise ValueError('Polygonal display geometry is required')
        row = {'id': identity, 'properties': canonical(properties),
               'geometry_sha256': geometry_digest(geometry, 1e-12)}
        rows.append(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False))
    encoded = '\n'.join(sorted(rows)).encode('utf-8')
    return {'features': len(rows), 'sha256': hashlib.sha256(encoded).hexdigest(),
            'method': 'sorted_properties_and_normalized_geometry_wkb',
            'fingerprint_coordinate_rounding_degrees': 1e-12,
            'delivered_geometry_not_modified': True,
            'all_properties_and_geometric_content_compared': True}


def table_control(path):
    frame = pd.read_parquet(path) if path.suffix == '.parquet' else pd.read_csv(path)
    # Raw reachable-road geometries use projected metres. Their orientation and
    # component order do not change the represented reachable network.
    geometry_columns = [column for column in frame if column.endswith('_wkb')]
    if geometry_columns:
        frame = frame.copy()
        crs_column = 'geometry_crs' if 'geometry_crs' in frame else 'crs'
        if crs_column not in frame:
            raise ValueError('WKB tables require an explicit CRS column')
        precision = {'EPSG:4326': 1e-12, 'EPSG:32638': 1e-6}
        for column in geometry_columns:
            values = []
            for value, crs in zip(frame[column], frame[crs_column]):
                if value is None:
                    values.append(None)
                    continue
                if crs not in precision:
                    raise ValueError('Unsupported or unknown WKB CRS: '+str(crs))
                values.append(geometry_digest(shapely.from_wkb(value), precision[crs]))
            frame[column] = values
    # OSM way refs are ordered nested arrays. They must be compared completely,
    # not stringified by a host-dependent NumPy repr or treated as missing.
    for column in frame:
        if frame[column].dtype == object and frame[column].map(
                lambda v: isinstance(v, (list, tuple, dict, np.ndarray))).any():
            frame = frame.copy()
            frame[column] = frame[column].map(lambda value:
                'nested-json:'+json.dumps(canonical(value), ensure_ascii=False,
                    sort_keys=True, separators=(',', ':'), allow_nan=False)
                if isinstance(value, (list, tuple, dict, np.ndarray)) else value)
    result = table_hash(frame, list(frame.columns))
    if geometry_columns:
        result['binary_geometry_semantics'] = {
            'columns': geometry_columns, 'crs_column': crs_column,
            'fingerprint_rounding_by_crs': precision,
            'orientation_and_component_order_ignored': True,
            'delivered_geometry_not_modified': True,
        }
    return result


def scientific_summary(value, field=None):
    excluded = {'files', 'coordinate_source_files', 'source_files',
                'path', 'pbf_path', 'profile_path', 'needed_ids_path',
                'output_dir', 'elapsed_seconds', 'wall_seconds', 'paths',
                'outputs', 'needed_vertices_sha256'}
    if field == 'source_pbf':
        excluded.update({'mode', 'part_retrieval'})
    if isinstance(value, dict):
        return {k: scientific_summary(v, k) for k, v in sorted(value.items()) if k not in excluded}
    if isinstance(value, list):
        return [scientific_summary(v) for v in value]
    return canonical(value)


def validate_model_summary(summary):
    if summary.get('geometry_source') != 'original_accepted_source_way_polylines':
        raise ValueError('Source-way geometry is required; compressed endpoint chords cannot be published')
    if summary.get('topology_precision_grid_degrees') != 0:
        raise ValueError('Final overlay must preserve full intersection precision')
    facts = summary.get('native_geometry_validation', {})
    if facts.get('missing_minimum_arcs') != 0 or facts.get('minimum_arc_cost_disagreements') != 0:
        raise ValueError('Original geometry must reconstruct the relevant archived minimum arcs')


def control(results):
    results = Path(results)
    required = ('inputs/centres.csv', 'inputs/all_current_settlements.parquet',
                'geometry_recovery/ways.parquet', 'geometry_recovery/nodes.parquet',
                'model/native_edges.parquet', 'model/needed_road_vertices.parquet',
                'model/settlement_travel_times.parquet', 'model/road_arrivals.parquet',
                'model/reachable_roads_wkb.parquet', 'model/geometry_diagnostics.csv',
                'model/isochrones_cumulative.geojson', 'model/isochrones_bands.geojson')
    for name in required:
        if not (results/name).is_file():
            raise ValueError('Completed scientific output is missing: '+name)
    validate_model_summary(json.loads((results/'model/summary.json').read_text()))
    tables, geometries, summaries = {}, {}, {}
    for folder in ('inputs', 'geometry_recovery', 'model'):
        for path in sorted((results/folder).rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(results).as_posix()
            if path.suffix in {'.parquet', '.csv'}:
                tables[relative] = table_control(path)
            elif path.suffix == '.geojson':
                geometries[relative] = geometry_control(path)
        summary = results/folder/'summary.json'
        if summary.is_file():
            summaries[folder] = scientific_summary(json.loads(summary.read_text()))
    for name in STANDALONE:
        path = results/'model'/name
        if not path.is_file() or path.stat().st_size > MAX_STANDALONE_BYTES:
            raise ValueError('A small standalone map asset is required: '+name)
        if geometries['model/'+name]['features'] != 4:
            raise ValueError('Four time bands per centre required')
    return {'schema': 'sgrt.saratov_isochrones.control.v1', 'tables': tables,
            'geojson': geometries, 'scientific_summaries': summaries,
            'every_table_row_and_column_compared': True, 'numeric_decimal_places': 8,
            'service_systems_or_hierarchy_established': False}


def acquire_boundary(target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError('Use a fresh source directory')
    temporary = target.with_suffix('.incoming')
    try:
        request = urllib.request.Request(BOUNDARY_URL, headers={'User-Agent': 'sgrt-saratov-isochrones/1'})
        count = 0
        with urllib.request.urlopen(request, timeout=120) as incoming, temporary.open('wb') as outgoing:
            while block := incoming.read(1 << 20):
                count += len(block)
                if count > BOUNDARY_BYTES:
                    raise ValueError('Oversized boundary input')
                outgoing.write(block)
        verify(temporary, {'bytes': BOUNDARY_BYTES, 'sha256': BOUNDARY_SHA256})
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {'kind': 'direct_immutable_geojson', 'url': BOUNDARY_URL,
            'bytes': BOUNDARY_BYTES, 'sha256': BOUNDARY_SHA256,
            'scope': 'Administrative display context, not a routing or water mask'}


def join_native_pbf(source, target):
    """Join exactly the six already-verified immutable PBF parts."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError('Assembled PBF target already exists')
    digest = hashlib.sha256(); count = 0
    temporary = target.with_suffix('.incoming')
    try:
        with temporary.open('wb') as output:
            for n in range(6):
                part = source/PBF_PREFIX/(PBF_NAME+f'.part{n:03d}')
                with part.open('rb') as incoming:
                    while block := incoming.read(1 << 20):
                        count += len(block)
                        if count > PBF_BYTES:
                            raise ValueError('Oversized assembled PBF')
                        digest.update(block); output.write(block)
        if count != PBF_BYTES or digest.hexdigest() != PBF_SHA256:
            raise ValueError('Assembled native PBF differs from public source')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {'kind': 'assembled_immutable_osm_pbf', 'parts': 6,
            'bytes': count, 'sha256': digest.hexdigest()}


def package(work, commit):
    results = work/'results'; built = work/'built'; built.mkdir()
    entries = []
    archive = built/'saratov-isochrones.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        def add(path, relative):
            zipped.write(path, relative)
            entries.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': sha(path)})
        for path in sorted(results.rglob('*')):
            if path.is_file():
                add(path, 'results/'+path.relative_to(results).as_posix())
        add(work/'actual_control.json', 'controls/actual_control.json')
        add(EXPECTED, 'controls/expected_control.json')
        for path in sorted((work/'checks').glob('*.json')):
            add(path, 'checks/'+path.name)
        paths = subprocess.check_output(['git', 'ls-files', 'scripts', 'tests', 'sgrt/saratov',
            'references/provenance/saratov*', 'references/sources.json', 'references/usage.json',
            'requirements-saratov-isochrones.txt', '.github/workflows/publish-saratov-isochrones.yml',
            'decisions.json', 'sgrt/MODEL_DESIGN.md',
            PROFILE_FOLDER+'road_profile.py', PROFILE_FOLDER+'finite_access_policy_proposal.json',
            PROFILE_FOLDER+'assemble_graph2021.py',
            *INPUTS.keys()], cwd=REPO, text=True).splitlines()
        for name in paths:
            add(REPO/name, 'reproduction/'+name)
    standalone = {}
    for name in STANDALONE:
        source = results/'model'/name
        (built/name).write_bytes(source.read_bytes())
        standalone[name] = {'bytes': source.stat().st_size, 'sha256': sha(source)}
    manifest = {'schema': 'sgrt.saratov_isochrones.release.v1', 'release_tag': TAG,
        'source_commit': commit, 'archive': {'asset': archive.name, 'bytes': archive.stat().st_size, 'sha256': sha(archive)},
        'standalone_assets': standalone, 'files': entries,
        'source_manifest': json.loads((results/'source_manifest.json').read_text()),
        'display_scope': 'Reachable directed road segments with explicit cartographic corridors, not complete landscape reachability.',
        'service_systems_or_hierarchy_established': False}
    write(built/'manifest.json', manifest)
    (built/'release_notes.md').write_text('Саратовская область: сетевые изохроны к шести центрам.\n\n'
        'Интервалы 10/20/30/60 модельных автомобильных минут, полный направленный дорожный граф. '
        'Геометрия восстановлена из исходных дорожных линий 2021 года, а не из хорд между узлами. '
        'Достижимые полные и частичные участки показаны картографической полосой по 250 м '
        'с каждой стороны дороги; вариант по 100 м сохранён отдельно. '
        'Полоса не доказывает доступность каждого места внутри неё. '
        'Административная граница не обрезает маршруты. Это не готовые зоны обслуживания или уровни СГРТ.\n\n'
        'В ZIP находятся таблицы, геометрии, исходный код, каталоги, независимые численные сравнения '
        'и оба контроля полного повторения. Исходный национальный граф и его координаты доступны '
        'в прежних закреплённых выпусках и повторно не архивируются.\n')
    return built


def draft(built, commit):
    clean_commit(commit)
    manifest = json.loads((built/'manifest.json').read_text())
    if manifest['source_commit'] != commit or manifest['release_tag'] != TAG:
        raise ValueError('Wrong scientific producer or release tag')
    if set(manifest.get('standalone_assets', {})) != set(STANDALONE):
        raise ValueError('Exactly six standalone centre assets are required')
    assets = [built/manifest['archive']['asset'], built/'manifest.json']
    verify(assets[0], manifest['archive'])
    for name, spec in manifest['standalone_assets'].items():
        verify(built/name, spec); assets.append(built/name)
    if any(row['tag_name'] == TAG for row in releases()):
        raise ValueError('Published releases and existing drafts are never overwritten')
    tag = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/git/ref/tags/{TAG}'], capture_output=True, text=True)
    if tag.returncode == 0 or 'HTTP 404' not in tag.stderr:
        raise ValueError('Cannot establish absence of publication tag')
    subprocess.run(['gh', 'release', 'create', TAG, '--repo', REPOSITORY, '--target', commit,
        '--draft', '--title', 'Саратовская область: сетевые изохроны к центрам, 28 октября 2026',
        '--notes-file', str(built/'release_notes.md'), *map(str, assets)], check=True)
    matches = [row for row in releases() if row['tag_name'] == TAG]
    if len(matches) != 1 or matches[0].get('draft') is not True:
        raise ValueError('Exactly one new draft must exist')
    release = matches[0]
    expected = {path.name: (path.stat().st_size, 'sha256:'+sha(path)) for path in assets}
    if release['target_commitish'] != commit or {
            row['name']: (row['size'], row.get('digest')) for row in release['assets']} != expected:
        raise ValueError('Uploaded draft assets differ; draft remains unpublished')
    return release['id']


def build(work, commit):
    clean_commit(commit)
    subprocess.run(['git', 'ls-files', '--error-unmatch', PROFILE_FOLDER+'road_profile.py',
                    PROFILE_FOLDER+'finite_access_policy_proposal.json'], cwd=REPO,
                   check=True, stdout=subprocess.DEVNULL)
    if work.exists() or work.resolve().is_relative_to(REPO) or not EXPECTED.is_file():
        raise ValueError('Use a new external work directory and committed completed local control')
    source = work/'input'; source.mkdir(parents=True)
    results = work/'results'; results.mkdir()
    proofs = []
    for catalogue, paths in INPUTS.items():
        available = {row['path'] for row in json.loads((REPO/catalogue).read_text())['files']}
        if not set(paths) <= available:
            raise ValueError('Pinned catalogue member is missing')
        proofs.extend(acquire(REPO/catalogue, lambda p, selected=set(paths): p in selected, source, work/'cache'))
    boundary = source/'external/RUS-adm1.geojson'
    proofs.append(acquire_boundary(boundary))
    write(results/'source_manifest.json', proofs)
    road_nodes = source/TRANSPORT/'road_nodes'
    run('scripts/sgrt_saratov/source_inventory.py', '--input-root', source, '--road-nodes', road_nodes,
        '--boundary-source', boundary, '--output', results/'inputs')
    model_arguments = ['scripts/sgrt_saratov/isochrones.py', '--centres', results/'inputs/centres.csv',
        '--settlements', results/'inputs/all_current_settlements.parquet', '--graph-dir', source/TRANSPORT,
        '--road-nodes', road_nodes, '--catalog', REPO/'data/catalog.json', '--output', results/'model']
    run(*model_arguments, '--routes-only')
    pbf = work/'native_source'/PBF_NAME
    proofs.append(join_native_pbf(source, pbf))
    write(results/'source_manifest.json', proofs)
    run('scripts/sgrt_saratov/native_source_geometry.py', '--pbf', pbf,
        '--source-parts', source/PBF_PREFIX,
        '--needed-road-vertices', results/'model/needed_road_vertices.parquet',
        '--output', results/'geometry_recovery')
    run(*model_arguments, '--geometry-only', '--native-ways', results/'geometry_recovery/ways.parquet',
        '--native-nodes', results/'geometry_recovery/nodes.parquet')
    run('scripts/sgrt_saratov/independent_checks.py', '--model', results/'model',
        '--inputs', results/'inputs', '--graph-dir', source/TRANSPORT,
        '--output', work/'checks/independent_numeric.json')
    audit = json.loads((work/'checks/independent_numeric.json').read_text())
    if audit.get('violations', 0) or audit.get('errors'):
        raise ValueError('Independent numerical/geometry comparison found discrepancies')
    actual = control(results); write(work/'actual_control.json', actual)
    if actual != json.loads(EXPECTED.read_text()):
        raise ValueError('Cloud outputs differ from the independently completed local control')
    package(work, commit)
    release_id = draft(work/'built', commit)
    write(work/'draft.json', {'release_id': release_id, 'release_tag': TAG, 'source_commit': commit,
                             'draft': True, 'publication_requires_separate_byte_verification': True})
    return release_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit')
    parser.add_argument('--workdir', type=Path)
    parser.add_argument('--control-results', type=Path)
    parser.add_argument('--control-output', type=Path)
    args = parser.parse_args()
    if args.control_results:
        if not args.control_output:
            parser.error('--control-output required')
        write(args.control_output, control(args.control_results))
    else:
        if not args.source_commit or not args.workdir:
            parser.error('--source-commit and --workdir required')
        print(json.dumps({'draft_release_id': build(args.workdir, args.source_commit)}))


if __name__ == '__main__':
    main()
