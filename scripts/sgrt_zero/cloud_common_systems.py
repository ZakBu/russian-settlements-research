"""Rebuild common service systems from pinned inputs and publish immutable outputs.

GitHub Actions owns publication credentials. HTTP range extraction transfers only
requested ZIP members when supported; each uncompressed member is independently
checked against the existing portable catalogue. A full-download fallback also
checks the complete archive digest. Neither path changes the population base.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.research_data import archive_member, destination
from scripts.sgrt_zero.identity_control import table_hash

REPOSITORY = 'ZakBu/russian-settlements-research'
TAG = 'sgrt-common-systems-20261027-v1'
PREFIX = 'sgrt/common20261027/'
EXPECTED = REPO/'research_context/analysis_snapshots/common_systems_control_20261027.json'
IDENTITY_CATALOG = REPO/'data/identity_catalog_20261026.json'
ZERO_CATALOG = REPO/'data/zero_catalog_20261025.json'
MASS_CATALOG = REPO/'data/mass_catalog_20261024.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def link_or_copy(source, target):
    """Avoid duplicating large immutable result files within one workspace."""
    if target.exists(): raise ValueError('Output asset already exists')
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def verify(path, spec):
    if not path.is_file() or path.stat().st_size != spec['bytes'] or sha(path) != spec['sha256']:
        raise ValueError('Pinned file size/SHA mismatch: '+str(path))


class RangeUnsupported(Exception):
    pass


class RemoteZip(io.RawIOBase):
    """Seekable, authenticated-data-free view of one public immutable archive."""
    def __init__(self, url, size, opener=urllib.request.urlopen):
        self.url, self.size, self.position, self.opener = url, size, 0, opener
        self.transferred = 0

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.position

    def seek(self, offset, whence=0):
        target = offset if whence == 0 else self.position+offset if whence == 1 else self.size+offset if whence == 2 else None
        if target is None or target < 0:
            raise ValueError('Invalid ZIP seek')
        self.position = target
        return target

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.size, self.position+size)
        if end <= self.position: return b''
        request = urllib.request.Request(self.url, headers={
            'Range': f'bytes={self.position}-{end-1}', 'Accept-Encoding': 'identity',
            'User-Agent': 'sgrt-common-systems/1'})
        with self.opener(request, timeout=120) as response:
            if response.status == 200:
                raise RangeUnsupported('Server does not support HTTP byte ranges')
            expected = f'bytes {self.position}-{end-1}/{self.size}'
            if response.status != 206 or response.headers.get('Content-Range') != expected:
                raise ValueError('Invalid HTTP byte range or changed archive size')
            data = response.read(end-self.position+1)
        if len(data) != end-self.position:
            raise ValueError('Truncated or oversized HTTP byte range')
        self.position = end
        self.transferred += len(data)
        return data


def extract_checked(archive, selections, target):
    counts = Counter(archive.namelist())
    proof = []
    for logical, member, spec in selections:
        if counts[member] != 1 or archive.getinfo(member).is_dir():
            raise ValueError('Absent, duplicate or directory ZIP member: '+member)
        if archive.getinfo(member).file_size != spec['bytes']:
            raise ValueError('ZIP member size differs from pinned catalogue')
        path = destination(target, logical)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name+'.incoming')
        try:
            with archive.open(member) as incoming, temporary.open('wb') as outgoing:
                count = 0
                while block := incoming.read(1 << 20):
                    count += len(block)
                    if count > spec['bytes']: raise ValueError('Oversized uncompressed ZIP member')
                    outgoing.write(block)
            verify(temporary, spec)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        proof.append({'path': logical, 'archive_member': member,
                      'bytes': spec['bytes'], 'sha256': spec['sha256']})
    return proof


def acquire(catalog_path, predicate, target, cache):
    catalog = json.loads(catalog_path.read_text())
    selected = [row for row in catalog['files'] if predicate(row['path'])]
    if not selected: raise ValueError('No pinned source files selected')
    assets = {a['asset']: a for a in catalog['assets']}
    grouped = {}
    for row in selected:
        obj = catalog['objects'][row['blob']]
        grouped.setdefault(row['asset'], []).append((row['path'], archive_member(obj, row['blob']), obj))
    result = []
    for name, selections in grouped.items():
        spec = assets[name]
        remote = RemoteZip(spec['url'], spec['bytes'])
        mode = 'http_ranges_member_sha256_verified'
        try:
            with zipfile.ZipFile(remote) as archive:
                files = extract_checked(archive, selections, target)
        except RangeUnsupported:
            mode = 'full_archive_and_members_sha256_verified'
            cache.mkdir(parents=True, exist_ok=True)
            local = cache/name
            request = urllib.request.Request(spec['url'], headers={'User-Agent': 'sgrt-common-systems/1'})
            with urllib.request.urlopen(request, timeout=180) as incoming, local.open('wb') as outgoing:
                shutil.copyfileobj(incoming, outgoing, 4 << 20)
            verify(local, spec)
            with zipfile.ZipFile(local) as archive:
                files = extract_checked(archive, selections, target)
            local.unlink()
        result.append({'catalog': catalog_path.relative_to(REPO).as_posix(),
            'catalog_sha256': sha(catalog_path), 'source_release': catalog['release_tag'],
            'source_commit': catalog['source_commit'], 'archive': name,
            'archive_expected_bytes': spec['bytes'], 'archive_expected_sha256': spec['sha256'],
            'verification_mode': mode, 'range_bytes_transferred': remote.transferred,
            'files': files})
    return result


def control(results):
    tables = {}
    for path in sorted(Path(results).rglob('*.parquet')):
        frame = pd.read_parquet(path)
        tables[path.relative_to(results).as_posix()] = table_hash(frame, list(frame.columns))
    if not tables: raise ValueError('No scientific output tables to compare')
    summaries = {}
    sensitivity = Path(results)/'sensitivity/summary.json'
    if sensitivity.is_file():
        summaries['sensitivity/summary.json'] = {k:v for k,v in json.loads(sensitivity.read_text()).items()
            if k not in {'inputs', 'code_sha256'}}
    return {'schema': 'sgrt.common_systems_control.v1', 'tables': tables, 'summaries': summaries,
            'numeric_comparison_decimal_places': 8,
            'row_multiplicity_and_every_column_compared': True}


def clean_commit(commit):
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() != commit:
        raise ValueError('Exact scientific producer commit required')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip():
        raise ValueError('Commit scientific code and expected control before rebuilding')


def run(*arguments):
    subprocess.run([sys.executable, *map(str, arguments)], cwd=REPO, check=True)


def build(work, commit):
    clean_commit(commit)
    if work.exists() or work.resolve().is_relative_to(REPO):
        raise ValueError('Use a new work directory outside Git')
    if not EXPECTED.is_file():
        raise ValueError('Independent completed local all-row control is required before cloud rebuild')
    source = work/'input'; source.mkdir(parents=True)
    identity_root = 'sgrt/identity20261026/'
    zero_root = 'sgrt/zero20261025/'
    from scripts.sgrt_zero.functional_orders import STAGES
    families = {family for stage in STAGES for family in stage['families']}
    identity_members = {identity_root+'analysis/scenarios/daily_20_school30_wb/daily_edges.parquet',
                        identity_root+'registry/level0_centres.csv', identity_root+'registry/level0_memberships.parquet'}
    identity_members.update(identity_root+'routes/nearest/'+family+'.parquet'
                            for family in families if not family.startswith('medical_'))
    zero_members = {zero_root+'context/analysis_reference.parquet'}
    zero_members.update(zero_root+'routes/nearest/'+family+'.parquet'
                        for family in families if family.startswith('medical_'))
    for catalog_path, wanted in [(IDENTITY_CATALOG, identity_members), (ZERO_CATALOG, zero_members)]:
        available = {row['path'] for row in json.loads(catalog_path.read_text())['files']}
        if wanted - available: raise ValueError('Requested source not in pinned catalogue: '+str(sorted(wanted-available)))
    proof = acquire(IDENTITY_CATALOG, lambda p: p in identity_members, source, work/'cache')
    proof += acquire(ZERO_CATALOG, lambda p: p in zero_members, source, work/'cache')
    proof += acquire(MASS_CATALOG, lambda p: p == 'sgrt/mass20261024/context/settlement_context.parquet',
                     source, work/'cache')
    write(work/'source_facts.json', proof)
    results = work/'results'; results.mkdir()
    reference = source/zero_root/'context/analysis_reference.parquet'
    run('scripts/sgrt_zero/common_systems.py', '--edges', source/identity_root/'analysis/scenarios/daily_20_school30_wb/daily_edges.parquet',
        '--reference', reference, '--centres', source/identity_root/'registry/level0_centres.csv',
        '--memberships', source/identity_root/'registry/level0_memberships.parquet', '--output', results/'level0',
        '--skip-cooperation')
    run('scripts/sgrt_zero/audit_function_weights.py', '--edges',
        source/identity_root/'analysis/scenarios/daily_20_school30_wb/daily_edges.parquet',
        '--reference', reference, '--centres', source/identity_root/'registry/level0_centres.csv',
        '--output', results/'sensitivity')
    run('scripts/sgrt_zero/common_economic_context.py', '--memberships', results/'level0/memberships.parquet',
        '--units', results/'level0/units.parquet', '--context', source/'sgrt/mass20261024/context/settlement_context.parquet',
        '--output', results/'economic')
    run('scripts/sgrt_zero/functional_orders.py', '--memberships', results/'level0/memberships.parquet',
        '--units', results/'level0/units.parquet',
        '--reference', reference, '--service-memberships', source/identity_root/'registry/level0_memberships.parquet',
        '--route-directory', source/identity_root/'routes/nearest',
        '--medical-route-directory', source/zero_root/'routes/nearest', '--demand-scope', 'positive-whole',
        '--time-scale', '1', '--output', results/'orders')
    run('scripts/sgrt_zero/audit_common_results.py', '--edges',
        source/identity_root/'analysis/scenarios/daily_20_school30_wb/daily_edges.parquet',
        '--reference', reference, '--centres', source/identity_root/'registry/level0_centres.csv',
        '--original-service-memberships', source/identity_root/'registry/level0_memberships.parquet',
        '--zero-directory', results/'level0', '--upper-directory', results/'orders',
        '--route-directory', source/identity_root/'routes/nearest',
        '--medical-route-directory', source/zero_root/'routes/nearest',
        '--require-complete', '--output', results/'independent-audit')
    prepare_site_exports(results)
    actual = control(results); write(work/'actual_control.json', actual)
    if actual != json.loads(EXPECTED.read_text()):
        raise ValueError('Cloud all-row scientific control differs from completed local calculation')
    # Recheck every source file after all computation, not just before reading.
    for archive in proof:
        for item in archive['files']: verify(source/item['path'], item)
    return package(results, work/'built', commit, proof, actual)


def membership_site_frame(members, centres):
    """Small map labels with the exact original census identity for selection."""
    if members.origin_id.duplicated().any() or centres.unit_id.duplicated().any():
        raise ValueError('Map membership/centre identities must be unique')
    required = {'origin_id', 'name', 'lat', 'lon', 'unit_id', 'membership_status',
                'positive_whole_origin', 'is_registered_centre'}
    if not required <= set(members.columns): raise ValueError('Membership map fields missing')
    names = centres.set_index('unit_id').name
    source = members[members.positive_whole_origin | members.is_registered_centre].copy()
    target = source.unit_id.map(names)
    if (source.unit_id.notna() & target.isna()).any():
        raise ValueError('A mapped primary centre has no recorded label')
    labels = source.name.fillna('').astype(str)
    assigned = source.unit_id.notna() & ~source.is_registered_centre
    labels = labels.where(~assigned, labels+' → '+target.fillna('').astype(str))
    labels = labels.where(~source.is_registered_centre, labels+' — центр')
    no_unique = ~source.is_registered_centre & source.unit_id.isna()
    labels = labels.where(~no_unique, labels+' — единый центр не установлен')
    codes = {'registered_centre_preserved_as_self_anchor': 1, 'three_function_primary': 2,
             'two_of_three_function_primary': 3, 'two_function_primary_partial': 4,
             'one_known_function_primary_provisional': 4, 'distributed_equal_known_support': 5}
    result = source[['lat', 'lon']].copy()
    result.insert(0, 'id', source.origin_id.astype(str))
    result.insert(1, 'name', labels)
    result['value'] = source.membership_status.map(codes).astype('Int64')
    if not result.id.is_unique: raise ValueError('Original map identities repeated')
    return result


def hierarchy_created_nodes(unit_frames):
    """Keep a newly created node at its actual depth, not at the stage number."""
    rows = []
    for frame in unit_frames:
        required = {'unit_id', 'new_territorial_merger', 'effective_merge_depth', 'name', 'lat', 'lon'}
        if not required <= set(frame): raise ValueError('Territorial hierarchy node fields missing')
        part = frame[frame.new_territorial_merger.eq(True) & frame.effective_merge_depth.gt(0)].copy()
        rows.append(part)
    if not rows: raise ValueError('No territorial stage tables are available')
    result = pd.concat(rows, ignore_index=True)
    if result.unit_id.duplicated().any():
        duplicates = result[result.unit_id.duplicated(keep=False)]
        for _, group in duplicates.groupby('unit_id'):
            if len(group.drop_duplicates()) != 1:
                raise ValueError('The same newly created hierarchy node has conflicting descriptions')
        result = result.drop_duplicates('unit_id')
    return result.sort_values(['effective_merge_depth', 'unit_id'], kind='stable').reset_index(drop=True)


def prepare_site_exports(results):
    results = Path(results)
    membership_site_frame(pd.read_parquet(results/'level0/memberships.parquet'),
        pd.read_parquet(results/'level0/units.parquet')).to_csv(
            results/'level0/primary_membership_points.csv', index=False)
    tables = []
    for path in sorted((results/'orders').glob('*/units.parquet')):
        summary = path.with_name('summary.json')
        if summary.is_file() and json.loads(summary.read_text()).get('territorial_membership_applied') is False:
            continue
        tables.append(pd.read_parquet(path))
    nodes = hierarchy_created_nodes(tables)
    folder = results/'depth_layers'; folder.mkdir(exist_ok=True)
    nodes.to_parquet(folder/'hierarchy_created_nodes.parquet', index=False)
    counts = {}
    for depth, group in nodes.groupby('effective_merge_depth', sort=True):
        depth = int(depth)
        frame = group[['unit_id', 'name', 'lat', 'lon']].copy()
        frame['name'] = frame.name+' — глубина '+str(depth)
        frame['value'] = depth
        filename = 'service-assembly-depth-'+str(depth)+'-centres.csv'
        frame.to_csv(folder/filename, index=False)
        counts[str(depth)] = len(frame)
    write(folder/'summary.json', {'map_layer_counts_by_actual_depth': counts,
        'source': 'union_of_new_territorial_mergers_from_all_territorial_stages',
        'stage_index_is_not_effective_merge_depth': True,
        'referral_channel_included_as_territorial_level': False,
        'empirical_agglomeration_rank_identified': False})


def package(results, built, commit, proof, actual):
    if built.exists(): raise ValueError('Output package directory must be new')
    built.mkdir(parents=True)
    if not (results/'level0/primary_membership_points.csv').is_file():
        raise ValueError('Prepare and verify site exports before packaging')
    entries = {'results/'+p.relative_to(results).as_posix(): p
               for p in results.rglob('*') if p.is_file() and p.suffix in {'.parquet', '.csv', '.json', '.md', '.png', '.svg'}
               and p.name != 'zero_units.csv'}
    assets = []
    for path in sorted(results.rglob('*.csv')):
        if 'centres' not in path.name and path.name != 'primary_membership_points.csv': continue
        frame = pd.read_csv(path)
        if not {'name', 'lat', 'lon', 'value'} <= set(frame.columns): continue
        if path.stat().st_size > 20_000_000: raise ValueError('Map CSV exceeds existing site adapter limit')
        if frame[['lat', 'lon']].isna().any().any(): raise ValueError('Mapped centres need real coordinates')
        if not frame.lat.between(-90, 90).all() or not frame.lon.between(-180, 180).all():
            raise ValueError('Out-of-range mapped coordinates')
        if frame.value.dropna().nunique() > 5: raise ValueError('Existing categorical palette supports five categories')
        filename = path.parent.name+'-'+path.name
        target = built/filename; link_or_copy(path, target); assets.append(target)
    if not assets: raise ValueError('At least one real map source CSV is required')
    for path in sorted(results.rglob('*.png')):
        filename = path.parent.name+'-'+path.name
        target = built/filename
        if target.exists(): raise ValueError('Standalone figure asset name collision')
        link_or_copy(path, target); assets.append(target)
    context = ['AGENTS.md', 'decisions.json', 'research_context/current_state.json',
        'research_context/primary/word_concept_extracted.txt', 'sgrt/MODEL_DESIGN.md',
        'docs/WRITING_GUIDE.md', 'references/sources.json', 'references/usage.json',
        'references/provenance/common_routes_equivalence_20261027.json',
        'data/identity_catalog_20261026.json', 'data/zero_catalog_20261025.json', 'data/mass_catalog_20261024.json',
        '.github/workflows/publish-common-systems.yml', 'requirements-common-systems.txt',
        EXPECTED.relative_to(REPO).as_posix()]
    context += [p.relative_to(REPO).as_posix() for directory in ['scripts/sgrt_zero', 'scripts/sgrt_pilot']
                for p in (REPO/directory).glob('*.py')]
    context += [p.relative_to(REPO).as_posix() for p in (REPO/'tests').glob('test_sgrt_zero_*common*.py')]
    context += ['tests/test_sgrt_zero_functional_orders.py']
    for name in sorted(set(context)):
        path = REPO/name
        if not path.is_file(): raise FileNotFoundError(path)
        entries['reproduction/'+name] = path
    manifest = {'schema': 'sgrt.common_systems_bundle.v1', 'source_commit': commit,
        'release_tag': TAG, 'archive_root': PREFIX, 'input_provenance': proof,
        'semantic_control': actual, 'observed_trips_established': False,
        'scientific_scope': 'Modelled common local systems and explicit functional stages; no inferred commuting flows.',
        'files': {name: {'bytes': path.stat().st_size, 'sha256': sha(path)} for name,path in sorted(entries.items())},
        'standalone_assets': {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in assets}}
    archive = built/'common-systems.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as zipped:
        for name, path in sorted(entries.items()): zipped.write(path, PREFIX+name)
        zipped.writestr(PREFIX+'bundle_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    manifest['archive'] = {'asset': archive.name, 'bytes': archive.stat().st_size, 'sha256': sha(archive)}
    write(built/'manifest.json', manifest)
    (built/'release_notes.md').write_text('Общие модельные местные системы и функциональные ступени, 27 октября 2026 года.\n\n'
        'Окружения, ядра и неизвестные связи сохранены раздельно; наличие учреждения не доказывает поездок. '
        'Все строки пересчитаны из закреплённых источников и сопоставлены с независимым локальным расчётом.\n\n'
        'Данные, составы, воспроизводящий код, контрольные суммы и происхождение входов находятся в архиве. '
        'Отдельные CSV предназначены для существующего интерактивного редактора атласа.\n')
    return built


def releases():
    pages = json.loads(subprocess.check_output(['gh', 'api', '--paginate', '--slurp',
        f'repos/{REPOSITORY}/releases?per_page=100'], text=True))
    return [row for page in pages for row in page]


def publish(built, commit):
    clean_commit(commit)
    manifest = json.loads((built/'manifest.json').read_text())
    if manifest['source_commit'] != commit or manifest['release_tag'] != TAG:
        raise ValueError('Built package producer/tag differs')
    assets = [built/manifest['archive']['asset'], built/'manifest.json']
    verify(assets[0], manifest['archive'])
    for name, spec in manifest['standalone_assets'].items():
        path = built/name; verify(path, spec); assets.append(path)
    if any(row.get('tag_name') == TAG for row in releases()):
        raise ValueError('New immutable tag required; existing releases/drafts are never replaced')
    tag = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/git/ref/tags/{TAG}'], capture_output=True, text=True)
    if tag.returncode == 0 or 'HTTP 404' not in tag.stderr:
        raise ValueError('Cannot establish absence of publication tag')
    subprocess.run(['gh', 'release', 'create', TAG, '--repo', REPOSITORY, '--target', commit,
        '--draft', '--title', 'Местные системы и функциональные ступени: расчёт 27 октября 2026',
        '--notes-file', str(built/'release_notes.md'), *map(str, assets)], check=True)
    matches = [row for row in releases() if row.get('tag_name') == TAG and row.get('draft') is True]
    if len(matches) != 1: raise ValueError('Exactly one complete created draft required')
    release = matches[0]
    expected = {p.name: (p.stat().st_size, 'sha256:'+sha(p)) for p in assets}
    uploaded = release.get('assets', [])
    if release.get('target_commitish') != commit or len(uploaded) != len(expected) or {
            a['name']: (a['size'], a.get('digest')) for a in uploaded} != expected:
        raise ValueError('Draft producer or all-asset digests differ; draft retained unpublished')
    subprocess.run(['gh', 'api', '--method', 'PATCH', f'repos/{REPOSITORY}/releases/{release["id"]}',
        '-F', 'draft=false', '-f', 'make_latest=false', '--silent'], check=True)
    return release['id']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit')
    parser.add_argument('--workdir', type=Path)
    parser.add_argument('--publish-built', type=Path)
    parser.add_argument('--control-results', type=Path)
    parser.add_argument('--control-output', type=Path)
    args = parser.parse_args()
    if args.control_results:
        if not args.control_output: parser.error('--control-output required')
        prepare_site_exports(args.control_results)
        write(args.control_output, control(args.control_results)); return
    if not args.source_commit: parser.error('--source-commit required')
    if args.publish_built:
        print(json.dumps({'release_id': publish(args.publish_built, args.source_commit)})); return
    if not args.workdir: parser.error('--workdir required')
    print(build(args.workdir, args.source_commit))


if __name__ == '__main__': main()
