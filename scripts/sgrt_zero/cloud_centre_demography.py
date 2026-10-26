"""Rebuild the fixed-centre demographic readout and publish a new immutable release."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_zero.identity_control import table_hash

REPOSITORY = 'ZakBu/russian-settlements-research'
TAG = 'sgrt-zero-centre-demography-20261026-v1'
PREFIX = 'sgrt/centre-demography20261026/'
FACTS = REPO/'references/provenance/centre_demography_inputs_20261026.json'
CONTROL = REPO/'research_context/analysis_snapshots/centre_demography_control_20261026.json'
TABLES = ['centre_demographic_components', 'centre_demographic_classes', 'fixed_membership_population_evidence']
CATEGORIES = {'unknown': 0, 'decline__decline': 1, 'growth__growth': 2, 'growth__decline': 3,
    'decline__growth': 4, 'decline__unchanged': 5, 'unchanged__decline': 6,
    'unchanged__growth': 7, 'growth__unchanged': 8, 'unchanged__unchanged': 9}
DIRECTIONS = {'decline': 'убывает', 'growth': 'растёт', 'unchanged': 'не изменилось'}
FIGURES = {'preview.png': 'centre_rural_demography_2002_2021.png',
           'comparison.png': 'centre_rural_demography_comparability.png'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def check(path, spec):
    if not path.is_file() or path.stat().st_size != spec['bytes'] or sha(path) != spec['sha256']:
        raise ValueError('Immutable file size/SHA mismatch: '+str(path))


def absent_tag():
    for endpoint in [f'releases/tags/{TAG}', f'git/ref/tags/{TAG}']:
        result = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/{endpoint}'], capture_output=True, text=True)
        if result.returncode == 0:
            raise ValueError('Publication requires a completely new tag: '+TAG)
        if 'HTTP 404' not in result.stderr:
            raise RuntimeError('Cannot establish absence of release/tag: '+result.stderr)


def site_frame(classes, centres):
    keys = ['star_id', 'centre_settlement_id']
    if centres.star_id.duplicated().any() or centres.centre_settlement_id.duplicated().any():
        raise ValueError('Site registry identities must be unique')
    result = centres[keys+['centre_name', 'centre_region', 'lat', 'lon']].rename(
        columns={'centre_name': 'name', 'centre_region': 'region'}).copy()
    for mode, label in [('strict_direct_observed', 'strict'), ('accepted_values', 'accepted')]:
        part = classes.loc[classes.evidence_mode.eq(mode)]
        if part.star_id.duplicated().any() or set(part.star_id) != set(result.star_id):
            raise ValueError('Every mode must describe every centre exactly once')
        columns = keys+['joint_centre_rural_external_2002_2021', 'joint_centre_rural_external_2010_2021']
        renamed = {c: label+'_'+c for c in columns if c not in keys}
        result = result.merge(part[columns].rename(columns=renamed), on=keys, validate='one_to_one')
    main = result.strict_joint_centre_rural_external_2002_2021
    if not main.isin(CATEGORIES).all():
        raise ValueError('Unexpected demographic direction class')
    result['demography_rural_2002_category'] = main.map(CATEGORIES).astype('int64')
    def label(value):
        if value == 'unknown':
            return 'Недостаточно сопоставимых первичных данных'
        centre, rural = value.split('__')
        return 'Центр '+DIRECTIONS[centre]+'; сельское окружение '+DIRECTIONS[rural]
    result['demography_rural_2002_label'] = main.map(label)
    result['word_causal_type_established'] = False
    result['historical_boundary_equivalence_established'] = False
    if result[['lat', 'lon']].isna().any().any():
        raise ValueError('Every mapped centre needs its existing coordinates')
    return result


def control(readout, registry):
    summary = json.loads((readout/'summary.json').read_text())
    summary.pop('input_sha256', None)  # absolute paths belong in source facts, not semantic comparison
    result = {'schema': 'sgrt.centre_demography_control.v1', 'summary': summary, 'tables': {}}
    for name in TABLES:
        frame = pd.read_parquet(readout/(name+'.parquet'))
        result['tables'][name] = table_hash(frame, list(frame.columns))
    frame = site_frame(pd.read_parquet(readout/'centre_demographic_classes.parquet'),
                       pd.read_parquet(registry/'level0_centres.parquet'))
    result['site_points'] = table_hash(frame, list(frame.columns))
    result['figure_values'] = json.loads((readout/'figures/figure_values.json').read_text())
    return result, frame


def command(*args):
    subprocess.run([sys.executable, *map(str, args)], cwd=REPO, check=True)


def clean_commit(commit):
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() != commit:
        raise ValueError('The exact scientific source commit is required')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip():
        raise ValueError('Commit scientific code and expected control before rebuilding')


def build(work, commit):
    if work.exists() or work.resolve().is_relative_to(REPO):
        raise ValueError('Use a new work directory outside Git')
    clean_commit(commit)
    absent_tag()
    facts = json.loads(FACTS.read_text()); source = work/'source'; source.mkdir(parents=True)
    subprocess.run(['gh', 'release', 'download', facts['identity_tag'], '--repo', REPOSITORY,
                    '--pattern', 'manifest.json', '--pattern', 'identity-centres.zip', '--dir', str(source)], check=True)
    check(source/'manifest.json', facts['manifest'])
    public = json.loads((source/'manifest.json').read_text())
    if public['source_commit'] != facts['identity_producer_commit'] or public['archive'] != facts['archive']:
        raise ValueError('Identity producer or archive changed')
    check(source/'identity-centres.zip', facts['archive'])
    registry = work/'registry'; registry.mkdir()
    with zipfile.ZipFile(source/'identity-centres.zip') as archive:
        for name in ['level0_centres.parquet', 'level0_memberships.parquet']:
            key = 'registry/'+name; member = public['archive_root']+key
            if archive.namelist().count(member) != 1 or public['files'][key] != facts['registry'][name]:
                raise ValueError('Registry archive identity changed: '+name)
            with archive.open(member) as incoming, (registry/name).open('wb') as outgoing:
                shutil.copyfileobj(incoming, outgoing)
            check(registry/name, facts['registry'][name])
    # Only these two registry members are retained, never the 700MB input ZIP.
    (source/'identity-centres.zip').unlink()
    command('scripts/research_data.py', 'fetch', '--catalog', 'data/zero_catalog_20261025.json',
        '--profile', 'all', '--match', facts['reference']['catalog_path'], '--dest', source,
        '--cache', work/'cache')
    reference = source/facts['reference']['catalog_path']; check(reference, facts['reference'])
    readout = work/'readout'
    command('scripts/sgrt_zero/centre_demographic_readout.py', '--registry', registry,
            '--reference', reference, '--output', readout)
    command('scripts/sgrt_zero/centre_demographic_figures.py', '--registry', registry,
            '--readout', readout, '--output', readout/'figures')
    actual, points = control(readout, registry)
    expected = json.loads(CONTROL.read_text())
    write(work/'actual_control.json', actual)
    if actual != expected:
        raise ValueError('All-row demographic results differ from the independent local snapshot')
    for name, spec in facts['registry'].items(): check(registry/name, spec)
    check(reference, facts['reference'])
    return package(work, commit, readout, points, facts)


def package(work, commit, readout, points, facts):
    actual = json.loads((work/'actual_control.json').read_text())
    built = work/'built'; built.mkdir()
    points.to_csv(built/'centre_demography.csv', index=False)
    if (built/'centre_demography.csv').stat().st_size > 20_000_000:
        raise ValueError('Site CSV exceeds 20MB')
    for asset, filename in FIGURES.items(): shutil.copyfile(readout/'figures'/filename, built/asset)
    entries = {f'readout/{p.relative_to(readout).as_posix()}': p for p in readout.rglob('*')
               if p.is_file() and p.name != 'centre_demographic_classes.csv'}
    entries['centre_demography.csv'] = built/'centre_demography.csv'
    entries['actual_control.json'] = work/'actual_control.json'
    context = ['scripts/sgrt_zero/cloud_centre_demography.py', 'scripts/sgrt_zero/centre_demographic_readout.py',
        'scripts/sgrt_zero/centre_demographic_figures.py', 'scripts/sgrt_zero/identity_control.py', 'scripts/research_data.py',
        'tests/test_sgrt_zero_centre_demographic_readout.py', 'data/zero_catalog_20261025.json',
        'tests/test_sgrt_zero_cloud_demography.py', '.github/workflows/publish-centre-demography.yml',
        FACTS.relative_to(REPO).as_posix(), CONTROL.relative_to(REPO).as_posix(),
        'research_context/primary/word_concept_extracted.txt', 'research_context/primary/word_concept.docx',
        'sgrt/zero/LITERATURE_AND_LIMITS.md', 'references/sources.json', 'references/usage.json',
        'requirements-centre-demography.txt']
    for name in context:
        if not (REPO/name).is_file(): raise FileNotFoundError(name)
        entries['reproduction/'+name] = REPO/name
    manifest = {'schema': 'sgrt.centre_demography_bundle.v1', 'source_commit': commit, 'release_tag': TAG,
        'archive_root': PREFIX, 'source_facts': facts, 'semantic_control': actual,
        'legend': CATEGORIES, 'main_evidence_mode': 'strict_direct_observed', 'main_period': [2002, 2021],
        'main_scope': 'centre_and_rural_external_fixed_2021_membership',
        'word_causal_types_established': False, 'observed_trips_established': False,
        'files': {k: {'bytes': p.stat().st_size, 'sha256': sha(p)} for k, p in sorted(entries.items())},
        'standalone_assets': {name: {'bytes': (built/name).stat().st_size, 'sha256': sha(built/name)}
                             for name in ['centre_demography.csv', *FIGURES]}}
    archive = built/'centre-demography.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as zipped:
        for name, path in sorted(entries.items()): zipped.write(path, PREFIX+name)
        zipped.writestr(PREFIX+'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    manifest['archive'] = {'asset': archive.name, 'bytes': archive.stat().st_size, 'sha256': sha(archive)}
    write(built/'manifest.json', manifest)
    return built


def publish(built, commit):
    clean_commit(commit)
    absent_tag()
    manifest = json.loads((built/'manifest.json').read_text())
    expected = json.loads(CONTROL.read_text())
    if (manifest['source_commit'] != commit or manifest['semantic_control'] != expected
            or manifest['source_facts'] != json.loads(FACTS.read_text())
            or manifest['release_tag'] != TAG or manifest['legend'] != CATEGORIES
            or set(manifest['standalone_assets']) != {'centre_demography.csv', *FIGURES}):
        raise ValueError('Publication source or semantic control differs')
    points = pd.read_csv(built/'centre_demography.csv')
    if table_hash(points, list(points.columns)) != expected['site_points']:
        raise ValueError('Every site CSV row must match the checked demographic classification')
    archive = built/manifest['archive']['asset']; check(archive, manifest['archive'])
    with zipfile.ZipFile(archive) as zipped:
        embedded = json.loads(zipped.read(PREFIX+'manifest.json'))
        if embedded != {k: v for k, v in manifest.items() if k != 'archive'} or zipped.testzip():
            raise ValueError('Archive manifest or CRC differs')
        for name, spec in manifest['files'].items():
            info = zipped.getinfo(PREFIX+name)
            with zipped.open(PREFIX+name) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if info.file_size != spec['bytes'] or digest != spec['sha256']:
                raise ValueError('Packed output checksum differs: '+name)
        for name, spec in manifest['standalone_assets'].items():
            check(built/name, spec)
            member = 'centre_demography.csv' if name == 'centre_demography.csv' else 'readout/figures/'+FIGURES[name]
            if hashlib.sha256(zipped.read(PREFIX+member)).hexdigest() != spec['sha256']:
                raise ValueError('Standalone asset differs from packed output')
    assets = [archive, built/'manifest.json', *[built/name for name in ['centre_demography.csv', *FIGURES]]]
    notes = built/'release_notes.md'
    notes.write_text('Демография фиксированных окружений 2021 года: центр и сельское окружение. '
        'Основная карта использует сопоставимые первичные значения 2002–2021. '
        'В архиве отдельно сохранены строгий и расширенный варианты для двух периодов. '
        'Это описательные направления роста и убыли, не причинные типы Word и не наблюдённые потоки.\n'
        f'Исходный коммит: {commit}. Все строки сверены с независимым контрольным расчётом.\n')
    subprocess.run(['gh', 'release', 'create', TAG, '--repo', REPOSITORY, '--target', commit,
                    '--draft', '--latest=false', '--title', 'Демография центров и сельского окружения — 26 октября 2026',
                    '--notes-file', str(notes), *map(str, assets)], check=True)
    release = json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPOSITORY}/releases/tags/{TAG}'], text=True))
    if not release['draft'] or release['target_commitish'] != commit or {
        a['name']: a['size'] for a in release['assets']} != {p.name: p.stat().st_size for p in assets}:
        raise ValueError('Incomplete draft; publication stopped without replacing any assets')
    subprocess.run(['gh', 'release', 'edit', TAG, '--repo', REPOSITORY, '--draft=false', '--latest=false'], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit')
    parser.add_argument('--workdir', type=Path)
    parser.add_argument('--publish-built', type=Path)
    parser.add_argument('--snapshot-from', type=Path)
    parser.add_argument('--registry', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.snapshot_from:
        if not args.registry or not args.output: parser.error('Snapshot requires --registry and --output')
        result, _ = control(args.snapshot_from, args.registry); write(args.output, result)
    elif args.source_commit and args.publish_built: publish(args.publish_built, args.source_commit)
    elif args.source_commit and args.workdir: build(args.workdir.resolve(), args.source_commit)
    else: parser.error('Choose snapshot, build or publication')
