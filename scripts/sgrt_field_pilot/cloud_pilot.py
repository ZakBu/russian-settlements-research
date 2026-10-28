"""Rebuild a bounded scientific pilot; prepare a new immutable draft release.

Inputs are existing public releases. The all-row control comes from a separate
local calculation, and the scalar independent audit uses no production kernel.
The workflow never makes the draft public or changes the census base.
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
sys.path.insert(0, str(REPO))
from scripts.sgrt_zero.cloud_common_systems import acquire, clean_commit, releases, run, sha, verify, write, REPOSITORY
from scripts.sgrt_zero.identity_control import table_hash
from scripts.sgrt_field_pilot.input_inventory import REFERENCE, ENDPOINTS, TRANSPORT

TAG = 'sgrt-field-pilot-20261028-v1'
EXPECTED = REPO / 'research_context/analysis_snapshots/field_pilot_control_20261028.json'
EDGES = 'sgrt/identity20261026/analysis/scenarios/daily_20_school30_wb/daily_edges.parquet'
UNITS = 'sgrt/common20261027/results/level0/units.parquet'
UPPER = 'sgrt/upper20261027/results/'
CROSS = UPPER + 'municipal/reference_parent_crosswalk.parquet'
PROFILES = UPPER + 'municipal/municipal_scale_comparisons.parquet'
WORKFORCE = UPPER + 'workforce/data_Y48423005_112_v20260928.parquet'
INPUTS = {
    'data/zero_catalog_20261025.json': [REFERENCE],
    'data/identity_catalog_20261026.json': [ENDPOINTS, EDGES],
    'data/common_systems_catalog_20261027.json': [UNITS],
    'data/upper_research_catalog_20261027.json': [CROSS, PROFILES, WORKFORCE],
    'data/catalog.json': [TRANSPORT + f'graph_npz_parts/part_{n:03d}.bin' for n in range(3)],
}


def site_export(results):
    results = Path(results)
    roster = pd.read_csv(results/'inputs/evaluation.csv')
    fields = pd.read_parquet(results/'model/fields.parquet')
    peaks = pd.read_parquet(results/'model/peaks.parquet')
    functions = pd.read_parquet(results/'functions/settlement_function_comparison.parquet')
    out = roster[['source_record_id', 'name', 'lat', 'lon', 'pilot', 'evaluation_core', 'population_2021']].copy()
    out = out.rename(columns={'source_record_id': 'id', 'population_2021': 'population2021'})
    for half in (20, 80):
        f = fields.loc[fields.kernel.eq('exponential') & fields.include_self.eq(True) & fields.half_time_minutes.eq(half)]
        p = peaks.loc[peaks.kernel.eq('exponential') & peaks.include_self.eq(True) & peaks.half_time_minutes.eq(half) & peaks.neighbor_count.eq(6)]
        out[f'field_exp{half}_self'] = out.id.map(f.set_index('source_record_id').known_routed_potential)
        out[f'peak_exp{half}_self'] = out.id.map(p.set_index('source_record_id').is_sampled_local_maximum)
        out[f'known_mass_upper_exp{half}'] = out.id.map(f.set_index('source_record_id').known_mass_potential_upper)
    out['peak_change_20_80'] = 4
    known = out.peak_exp20_self.notna() & out.peak_exp80_self.notna()
    a = out.peak_exp20_self.fillna(False).astype(bool)
    b = out.peak_exp80_self.fillna(False).astype(bool)
    out.loc[known & ~a & ~b, 'peak_change_20_80'] = 0
    out.loc[known & a & b, 'peak_change_20_80'] = 1
    out.loc[known & a & ~b, 'peak_change_20_80'] = 2
    out.loc[known & ~a & b, 'peak_change_20_80'] = 3
    out['own_function_count_known'] = out.id.map(functions.set_index('source_record_id').known_local_basic_function_count)
    out['published_external_serving_centre'] = out.id.map(functions.set_index('source_record_id').published_external_serving_centre)
    out['complete_field_or_hierarchy_established'] = False
    if out.id.duplicated().any() or len(out) != len(roster):
        raise ValueError('Map export changes evaluation identities')
    out.to_csv(results/'field-pilot-points.csv', index=False)
    return out


def control(results):
    """All table rows/columns, including missingness; no path-dependent metadata."""
    results = Path(results)
    tables = {}
    for folder in ('inputs', 'model', 'functions'):
        for path in sorted((results/folder).glob('*')):
            if path.suffix not in {'.parquet', '.csv'}:
                continue
            frame = pd.read_parquet(path) if path.suffix == '.parquet' else pd.read_csv(path)
            tables[path.relative_to(results).as_posix()] = table_hash(frame, list(frame.columns))
    path = results/'field-pilot-points.csv'
    frame = pd.read_csv(path)
    tables[path.name] = table_hash(frame, list(frame.columns))
    if not any(p.startswith('model/') for p in tables) or not any(p.startswith('functions/') for p in tables):
        raise ValueError('A completed model and functional comparison are required')
    return {'schema': 'sgrt.field_pilot.control.v1', 'tables': tables,
            'every_row_and_column_compared': True, 'decimal_places': 8,
            'spatial_system_levels_established': False}


def package(work, commit):
    results = work/'results'
    built = work/'built'; built.mkdir()
    archive = built/'field-pilot.zip'
    entries = []
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(results.rglob('*')):
            if path.is_file():
                relative = 'results/' + path.relative_to(results).as_posix()
                z.write(path, relative)
                entries.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': sha(path)})
        paths = subprocess.check_output(['git', 'ls-files', 'scripts', 'tests', 'sgrt/field_pilot',
            'references/provenance/field*', 'references/sources.json', 'references/usage.json',
            'requirements-field-pilot.txt', '.github/workflows/publish-field-pilot.yml',
            *INPUTS.keys()], cwd=REPO, text=True).splitlines()
        for rel in paths:
            path = REPO/rel
            z.write(path, 'reproduction/'+rel)
            entries.append({'path': 'reproduction/'+rel, 'bytes': path.stat().st_size, 'sha256': sha(path)})
    export = results/'field-pilot-points.csv'
    (built/export.name).write_bytes(export.read_bytes())
    manifest = {'schema': 'sgrt.field_pilot.release.v1', 'release_tag': TAG, 'source_commit': commit,
        'archive': {'asset': archive.name, 'bytes': archive.stat().st_size, 'sha256': sha(archive)},
        'standalone_assets': {export.name: {'bytes': export.stat().st_size, 'sha256': sha(export)}},
        'files': entries, 'source_manifest': json.loads((results/'source_manifest.json').read_text()),
        'spatial_system_levels_established': False}
    write(built/'manifest.json', manifest)
    (built/'release_notes.md').write_text('Сравнительный пилот поля населения: Саратов—Энгельс, Учалы, Устье.\n\n'
        'Несколько сценариев затухания и собственного вклада сопоставлены с известными местными функциями. '
        'Это расчёт в точках поселений, не установленные районы, поездки или уровни иерархии. '
        'Исходные данные доступны в прежних неизменных выпусках; их версии и SHA закреплены.\n')
    return built


def draft(built, commit):
    clean_commit(commit)
    manifest = json.loads((built/'manifest.json').read_text())
    if manifest['source_commit'] != commit or manifest['release_tag'] != TAG:
        raise ValueError('Wrong producer or tag')
    assets = [built/manifest['archive']['asset'], built/'manifest.json']
    verify(assets[0], manifest['archive'])
    for name, spec in manifest['standalone_assets'].items():
        verify(built/name, spec); assets.append(built/name)
    if any(r['tag_name'] == TAG for r in releases()):
        raise ValueError('Existing releases are immutable; use a new version')
    result = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/git/ref/tags/{TAG}'], capture_output=True, text=True)
    if result.returncode == 0 or 'HTTP 404' not in result.stderr:
        raise ValueError('Cannot establish absence of tag')
    subprocess.run(['gh', 'release', 'create', TAG, '--repo', REPOSITORY, '--target', commit, '--draft',
        '--title', 'Поле расселения и местные функции: сравнительный пилот 28 октября 2026',
        '--notes-file', str(built/'release_notes.md'), *map(str, assets)], check=True)
    # Publication is deliberately separate, after inspection of the built bytes.


def build(work, commit):
    clean_commit(commit)
    if work.exists() or work.resolve().is_relative_to(REPO) or not EXPECTED.is_file():
        raise ValueError('Use a new external directory and committed independent local control')
    source = work/'input'; source.mkdir(parents=True)
    results = work/'results'; results.mkdir()
    proofs = []
    for catalog, paths in INPUTS.items():
        proofs.extend(acquire(REPO/catalog, lambda p, allowed=set(paths): p in allowed, source, work/'cache'))
    write(results/'source_manifest.json', proofs)
    run('scripts/sgrt_field_pilot/input_inventory.py', '--input-root', source, '--output', results/'inputs')
    run('scripts/sgrt_field_pilot/field_model.py', '--reference', source/REFERENCE, '--endpoints', source/ENDPOINTS,
        '--evaluation', results/'inputs/evaluation.csv', '--graph-dir', source/TRANSPORT, '--output', results/'model')
    run('scripts/sgrt_field_pilot/function_comparison.py', '--roster', results/'inputs/evaluation.csv',
        '--edges', source/EDGES, '--units', source/UNITS, '--reference', source/REFERENCE,
        '--peaks', results/'model/peaks.parquet', '--peak-column', 'is_sampled_local_maximum',
        '--municipal-crosswalk', source/CROSS, '--municipal-profiles', source/PROFILES,
        '--municipal-workforce-raw', source/WORKFORCE, '--output', results/'functions')
    run('scripts/sgrt_field_pilot/independent_checks.py', '--model', results/'model',
        '--inputs', results/'inputs', '--output', work/'checks/numerical_audit.json')
    audit = json.loads((work/'checks/numerical_audit.json').read_text())
    if audit.get('errors'):
        raise ValueError('Independent numerical audit found discrepancies: '+str(audit['errors']))
    write(results/'independent_numerical_audit.json', audit)
    site_export(results)
    actual = control(results); write(work/'actual_control.json', actual)
    if actual != json.loads(EXPECTED.read_text()):
        raise ValueError('Cloud outputs differ from the completed local all-row control')
    package(work, commit)
    draft(work/'built', commit)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-commit')
    ap.add_argument('--workdir', type=Path)
    ap.add_argument('--control-results', type=Path)
    ap.add_argument('--control-output', type=Path)
    args = ap.parse_args()
    if args.control_results:
        site_export(args.control_results)
        write(args.control_output, control(args.control_results))
    else:
        if not args.source_commit or not args.workdir:
            ap.error('--source-commit and --workdir required')
        build(args.workdir, args.source_commit)


if __name__ == '__main__':
    main()
