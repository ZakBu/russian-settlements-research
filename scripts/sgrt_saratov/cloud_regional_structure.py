"""Reproduce and publish the Saratov regional structure experiment, not a final typology."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

import pandas as pd

from scripts.sgrt_zero.cloud_common_systems import acquire
from scripts.sgrt_saratov import regional_structure, regional_controls, regional_validation
from scripts.sgrt_saratov import regional_explanation, regional_structure_maps
from scripts.sgrt_saratov.source_inventory import BOUNDARY_URL, BOUNDARY_BYTES, BOUNDARY_SHA256

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'ZakBu/russian-settlements-research'
TAG = 'sgrt-saratov-regional-structure-20261106-v1'
PREFIX = 'sgrt/saratov-fields20261029-v2/results'
CATALOG_SHA256 = '0930dbe48cb4542819792041c97ccf3bd280dee1b7275141e3b39eed6da4aa51'
SNAPSHOT = ROOT/'research_context/analysis_snapshots/saratov_regional_structure_local_20261106.json'
INPUTS = frozenset({
    'fields/regional_roster.parquet', 'fields/fields.parquet', 'fields/halo_fields.parquet',
    'fields/halo_roster.parquet', 'fields/national_neighbors.parquet', 'fields/regional_costs.npy',
    'organisation/point_maxima.parquet', 'organisation/scale_neighbourhood_maxima.parquet',
    'physical_official/functional_links.parquet', 'context/known_partial_worker_fields.parquet',
    'context_physical_official/np_context.parquet',
    'context_physical_official/municipal_agriculture_context.parquet',
    'context_physical_official/municipal_workforce_summary.parquet',
    'context_physical_official_primary2010/np_context.parquet'})
MAPS = {
    'maps_full_radius/exponential__h10__full_radius.geojson': 'regional-field-h10.geojson',
    'maps_full_radius/exponential__h20__full_radius.geojson': 'regional-field-h20.geojson',
    'maps_full_radius/exponential__h40__full_radius.geojson': 'regional-field-h40.geojson',
    'maps_paired_ascent/exponential__h15__full_radius.geojson': 'regional-field-h15-paired-ascent.geojson',
    'maps_controls/exponential__h15__full_radius__nearest_same_peaks.geojson': 'regional-field-h15-paired-nearest.geojson'}
DOCUMENTS = ('documented_school_catchments_2025.csv', 'documented_medical_frameworks_2025.csv',
             'medical_identity_overrides_20261106.csv')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def download_checked(spec, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with urllib.request.urlopen(spec['url'], timeout=180) as response:
            target.write_bytes(response.read())
    if target.stat().st_size != spec['bytes'] or digest(target) != spec['sha256']:
        raise ValueError('Pinned source differs: '+str(target))
    return target


def acquire_inputs(work):
    catalogue = ROOT/'data/saratov_fields_catalog_20261029_v2.json'
    if digest(catalogue) != CATALOG_SHA256:
        raise ValueError('The pinned v2 catalogue changed')
    inventory = json.loads(catalogue.read_text())
    selected = {r['path'][len(PREFIX)+1:] for r in inventory['files']
                if r['path'].startswith(PREFIX+'/') and r['path'][len(PREFIX)+1:] in INPUTS}
    if selected != INPUTS:
        raise ValueError('Incomplete regional input selection')
    proof = acquire(catalogue, lambda p: p.startswith(PREFIX+'/') and
                    p[len(PREFIX)+1:] in INPUTS, work/'input', work/'cache')
    previous = json.loads((ROOT/'research_context/analysis_snapshots/saratov_service_systems_manifest_20261106.json').read_text())
    if previous['release'] != 'sgrt-saratov-service-systems-20261106-v1':
        raise ValueError('Unexpected service-control release')
    asset = next(a for a in previous['assets'] if a['asset'] == 'saratov-service-systems.zip')
    if asset['sha256'] != '01e0142c940b11a489772c4d14706cfb31f55c0df1c72b487eeb9ba2f639fba8':
        raise ValueError('Pinned service-control archive changed')
    archive = download_checked(asset, work/'cache'/asset['asset'])
    with zipfile.ZipFile(archive) as z:
        members = z.read('saratov-service-systems/results/structure/system_members.parquet')
    target = work/'input/documented_system_members.parquet'
    documented = pd.read_parquet(io.BytesIO(members))
    documented = documented[documented.membership_basis.astype(str).str.startswith('documented_')]
    documented.to_parquet(target, index=False, compression='zstd')
    count = documented.source_record_id.nunique()
    if count != 77:
        raise ValueError('Expected exactly 77 distinct documented control records')
    boundary_spec = {'url': BOUNDARY_URL, 'bytes': BOUNDARY_BYTES, 'sha256': BOUNDARY_SHA256}
    download_checked(boundary_spec, work/'input/RUS-adm1.geojson')
    documents = [{'path': 'sgrt/saratov/'+name, 'sha256': digest(ROOT/'sgrt/saratov'/name)}
                 for name in DOCUMENTS]
    provenance = {'fields_v2': proof, 'document_control_release': previous['release'],
        'document_control_archive': asset, 'document_members_sha256': digest(target),
        'original_members_archive_member_sha256': hashlib.sha256(members).hexdigest(),
        'document_member_filter': 'membership_basis startswith documented_; no inferred members',
        'document_control_unique_records': count, 'boundary': boundary_spec,
        'committed_document_extracts': documents,
        'archived_country_transit_revalidated': False}
    write(work/'input_provenance.json', provenance)
    return provenance


def summary_from_results(results):
    """Can also collect the already completed local run without recalculation."""
    results = Path(results)
    names = {'full_radius': 'summary.json', 'full_radius_controls': 'control_summary.json',
        'full_radius_validation': 'summary.json', 'explanation': 'summary.json',
        'explanation_full_radius': 'summary.json', 'maps_full_radius': 'cartographic_summary.json',
        'maps_paired_ascent': 'cartographic_summary.json', 'maps_controls': 'cartographic_summary.json'}
    answer = {name: json.loads((results/name/file).read_text()) for name, file in names.items()}
    # The original local explanation also described the superseded kNN run.
    # Those optional counts are not part of the all-oblast comparison.
    answer['explanation'].pop('conditional_population_basin_profiles', None)
    for name in ['maps_full_radius', 'maps_paired_ascent', 'maps_controls']:
        answer[name] = {'scenarios': [{key: row[key] for key in [
            'scenario_id', 'comparison_cohort_drawing_mask_applied',
            'comparison_cohort_input_records', 'comparison_cohort_visible_sampled_records',
            'assigned_display_basins', 'resolved_display_basins',
            'sampled_without_nonself_comparison_display_basins',
            'final_geographic_displaced_sampled_sites'] if key in row}
            for row in answer[name]['scenarios']]}
    stress = results/'structure/summary.json'
    answer['stress_test_72'] = json.loads(stress.read_text()) if stress.exists() else None
    answer['claim'] = 'Population concentration scenarios and external checks; no final functional settlement systems established.'
    return answer


def semantic_equal(actual, expected):
    """Exact structural/count comparison; tolerate immaterial floating error."""
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(semantic_equal(actual[k], expected[k]) for k in actual)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(semantic_equal(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, float) or isinstance(expected, float):
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return (math.isnan(actual) and math.isnan(expected)) or math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-8)
    return actual == expected


def calculate(work, include_stress=True):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    acquire_inputs(work)
    source, out = work/'input'/PREFIX, work/'results'
    fields = source/'fields'
    roster, links = fields/'regional_roster.parquet', source/'physical_official/functional_links.parquet'
    boundary = work/'input/RUS-adm1.geojson'
    regional_structure.run_full_radius(fields, out/'full_radius')
    membership = out/'full_radius/basin_membership.parquet'
    regional_controls.run(membership, roster, fields/'regional_costs.npy', out/'full_radius_controls')
    nearest = out/'full_radius_controls/nearest_same_peaks_membership.parquet'
    regional_validation.run(membership, roster, links,
        ROOT/'sgrt/saratov'/DOCUMENTS[0], ROOT/'sgrt/saratov'/DOCUMENTS[1],
        ROOT/'sgrt/saratov'/DOCUMENTS[2], out/'full_radius_validation', nearest)
    regional_explanation.run(source, work/'input/documented_system_members.parquet',
        out/'explanation', fields/'regional_costs.npy')
    regional_explanation.run_basin_only(source, membership, out/'explanation_full_radius',
                                      out/'explanation/np_explanation.parquet')
    regional_structure_maps.run(membership, roster, links, boundary, out/'maps_full_radius')
    primary, control = pd.read_parquet(membership), pd.read_parquet(nearest)
    sid = 'exponential__h15__full_radius'
    cohort = regional_structure_maps.common_supported_cohort(primary, control, sid, sid+'__nearest_same_peaks')
    regional_structure_maps.run(membership, roster, links, boundary, out/'maps_paired_ascent',
                               scenarios=[sid], comparison_cohort=cohort)
    regional_structure_maps.run(nearest, roster, links, boundary, out/'maps_controls',
                               scenarios=[sid+'__nearest_same_peaks'], comparison_cohort=cohort)
    if include_stress:
        regional_structure.run(fields, out/'structure')
    elif (out/'structure').exists():
        raise ValueError('Use a fresh work directory when disabling the stress test')
    actual = summary_from_results(out)
    write(work/'scientific_summary.json', actual)
    return actual


def package(work, producer, actual):
    work = Path(work)
    out, assets = work/'results', work/'publication_assets'
    assets.mkdir(exist_ok=True)
    for source, name in MAPS.items():
        shutil.copyfile(out/source, assets/name)
    archive = assets/'saratov-regional-structure.zip'
    folders = ['full_radius', 'full_radius_controls', 'full_radius_validation', 'explanation',
               'explanation_full_radius', 'maps_full_radius', 'maps_paired_ascent', 'maps_controls']
    if actual['stress_test_72'] is not None:
        folders.append('structure')
    entries = []
    for folder in folders:
        for p in sorted((out/folder).rglob('*')):
            # Parquet is the canonical table; CSV mirrors are intentionally omitted.
            if p.is_file() and p.suffix in {'.parquet', '.json', '.geojson'}:
                entries.append((p, 'results/'+p.relative_to(out).as_posix()))
    entries.extend([(work/'input_provenance.json', 'input_provenance.json'),
                    (work/'scientific_summary.json', 'scientific_summary.json')])
    inventory = [{'path': name, 'bytes': p.stat().st_size, 'sha256': digest(p)} for p, name in entries]
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p, name in entries:
            z.write(p, 'saratov-regional-structure/'+name)
        z.writestr('saratov-regional-structure/bundle_manifest.json', json.dumps({
            'source_commit': producer, 'release': TAG, 'files': inventory}, ensure_ascii=False, indent=2)+'\n')
    paths = [archive, *(assets/name for name in MAPS.values())]
    manifest = {'release': TAG, 'source_commit': producer, 'assets': [
        {'asset': p.name, 'bytes': p.stat().st_size, 'sha256': digest(p),
         'url': f'https://github.com/{REPOSITORY}/releases/download/{TAG}/'+p.name} for p in paths]}
    write(assets/'manifest.json', manifest)
    checksum_paths = [*paths, assets/'manifest.json']
    (assets/'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in checksum_paths))
    return manifest, [*checksum_paths, assets/'SHA256SUMS']


def publish(work, include_stress=True):
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('Commit all producer changes before publication')
    producer = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    # An existing tag/release must never be amended by this producer.
    existing = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/git/ref/tags/{TAG}'], capture_output=True)
    if existing.returncode == 0:
        raise ValueError('Immutable release tag already exists')
    actual = calculate(work, include_stress)
    expected = json.loads(SNAPSHOT.read_text())
    if not include_stress:
        expected['stress_test_72'] = None
    if not semantic_equal(actual, expected):
        raise ValueError('Cloud scientific summary differs from the committed local result')
    manifest, paths = package(work, producer, actual)
    subprocess.run(['gh', 'release', 'create', TAG, '--repo', REPOSITORY, '--target', producer,
        '--title', 'Саратовская область: демографическое поле и проверка пространственной структуры',
        '--notes', '18 полнорадиусных сценариев, контроль ближайшими теми же вершинами, документные проверки, хозяйство и отдельная чувствительность к переписи 2010 года. Карты — обобщённые картограммы состава, не изохроны. Готовые функциональные системы не установлены; прежние выпуски сохранены.',
        *map(str, paths)], check=True)
    for asset in manifest['assets']:
        with urllib.request.urlopen(asset['url'], timeout=180) as response:
            raw = response.read()
        if len(raw) != asset['bytes'] or hashlib.sha256(raw).hexdigest() != asset['sha256']:
            raise ValueError('Public asset differs: '+asset['asset'])
    dest = ROOT/'research_context/analysis_snapshots'
    write(dest/'saratov_regional_structure_20261106.json', actual)
    write(dest/'saratov_regional_structure_manifest_20261106.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--calculate-only', action='store_true')
    p.add_argument('--include-stress', action=argparse.BooleanOptionalAction, default=True)
    args = p.parse_args()
    result = calculate(args.work, args.include_stress) if args.calculate_only else publish(args.work, args.include_stress)
    print(json.dumps(result, ensure_ascii=False, indent=2))
