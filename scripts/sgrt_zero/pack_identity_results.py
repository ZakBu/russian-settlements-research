"""Package only new identity-repair results and their frozen reproducible context."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

REPO = Path(__file__).resolve().parents[2]
TAG = 'sgrt-zero-centres-20261026-v2'
PREFIX = 'sgrt/identity20261026/'
SOURCE_ZIP = {'asset': 'source-places.zip', 'bytes': 106845654,
              'sha256': 'd113fd0056a42fa8595489f21d58abbee376778261eac53cd6f5e893c14ae5f0'}
DEPENDENCY_CONTEXT = ['data/zero_catalog_20261025.json', 'data/pilot_catalog_20261024.json',
                      'data/catalog.json', 'scripts/research_data.py',
                      'references/provenance/coordinate_holds_20261026.json',
                      'references/provenance/official_local_school_cards_20261026.json',
                      'research_context/analysis_snapshots/level0_pre_identity_registry_20261026.json']


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(analysis, routes, registry, boundaries, output, commit):
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() != commit:
        raise ValueError('The exact checked-out scientific source commit is required')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip():
        raise ValueError('Scientific code and context must be committed before packaging')
    if output.resolve().is_relative_to(REPO): raise ValueError('Keep generated data outside Git')
    entries = {}
    for prefix, root in [('analysis', analysis), ('routes', routes), ('registry', registry), ('boundaries', boundaries)]:
        for path in sorted(root.rglob('*')):
            if path.is_file(): entries[prefix + '/' + path.relative_to(root).as_posix()] = path
    for folder in ['scripts/sgrt_zero', 'scripts/sgrt_mass', 'scripts/sgrt_local']:
        for path in sorted((REPO / folder).glob('*.py')):
            entries['reproduction/' + path.relative_to(REPO).as_posix()] = path
    context = ['AGENTS.md', 'README.md', 'AI_START_HERE.md', 'decisions.json',
               'research_context/current_state.json', 'research_context/diary/2026-10-26.md',
               'research_context/primary/word_concept_extracted.txt', 'research_context/primary/word_concept.docx',
               'references/sources.json', 'references/usage.json',
               'references/provenance/geofabrik_place_polygons_20261026.json']
    for name in DEPENDENCY_CONTEXT:
        if not (REPO / name).is_file():
            raise FileNotFoundError('Required reproducible dependency context is missing: ' + name)
    context += DEPENDENCY_CONTEXT
    context += [p.relative_to(REPO).as_posix() for p in
                (REPO / 'references/primary/settlement_identity_20261026').rglob('*') if p.is_file()]
    context += [p.relative_to(REPO).as_posix() for p in REPO.glob('requirements-sgrt-*.txt')]
    context += [p.relative_to(REPO).as_posix() for p in (REPO / 'sgrt/zero').glob('*.md')]
    context += [p.relative_to(REPO).as_posix() for p in (REPO / 'research_context/analysis_snapshots').glob('identity_*.json')]
    for name in context:
        if (REPO / name).is_file(): entries['reproduction/' + name] = REPO / name
    files = {name: {'bytes': path.stat().st_size, 'sha256': sha(path)} for name, path in sorted(entries.items())}
    summary = json.loads((registry / 'summary.json').read_text())
    manifest = {'schema': 'sgrt.identity_results_bundle.v1', 'release_tag': TAG, 'source_commit': commit,
        'archive_root': PREFIX, 'source_places': SOURCE_ZIP,
        'unchanged_input_release': 'sgrt-zero-systems-20261025-v1',
        'unchanged_population_default_catalog': 'data/catalog.json',
        'dependency_catalogs': ['data/zero_catalog_20261025.json', 'data/pilot_catalog_20261024.json', 'data/catalog.json'],
        'population_default_catalog_unchanged': True, 'recomputed_nearest_layers': 12,
        'registry_counts': {k: v for k, v in summary.items() if k != 'inputs_sha256'},
        'exclusive_country_partition_established': False, 'observed_journeys_established': False,
        'files': files}
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'identity-centres.zip'
    if archive.exists(): raise FileExistsError('A completed result archive is immutable')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as result:
        for name, path in sorted(entries.items()): result.write(path, arcname=PREFIX + name)
        result.writestr(PREFIX + 'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    for name, path in entries.items():
        if path.stat().st_size != files[name]['bytes'] or sha(path) != files[name]['sha256']:
            raise ValueError('An archived scientific input changed: ' + name)
    with zipfile.ZipFile(archive) as result:
        if result.testzip() is not None: raise ValueError('Scientific archive CRC failure')
    manifest['archive'] = {'asset': archive.name, 'bytes': archive.stat().st_size, 'sha256': sha(archive)}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'archive': manifest['archive'], 'files': len(files)}))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['analysis', 'routes', 'registry', 'boundaries', 'output']:
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    a = parser.parse_args()
    package(a.analysis, a.routes, a.registry, a.boundaries, a.output, a.source_commit)
