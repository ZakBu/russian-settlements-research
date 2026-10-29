"""Finalize the preserved, fully computed Saratov run without rerouting it.

The original failure was three obsolete local probe files in the expected
inventory. Every common scientific control matched exactly. This narrow reuse
path authenticates the preserved bytes, protects the original scientific code,
rehashes all output cells, and creates an unpublished draft only. The ordinary
cloud producer remains the independent rebuild-from-inputs entry point.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_saratov import cloud_regional_research as producer
from scripts.sgrt_zero.cloud_common_systems import clean_commit, sha, verify, write

COMPUTATION_COMMIT = '51052edc968a3eb4ac31f88bf81f59ed9481ab9b'
COMPUTATION_RUN = 40806711713
DIAGNOSTIC_TAG = 'diagnostic-saratov-fields-40806711713'
EXPECTED_PATH = 'research_context/analysis_snapshots/regional_fields_control_20261029.json'
WRAPPER_PATH = 'scripts/sgrt_saratov/cloud_regional_research.py'
SELF_PATH = 'scripts/sgrt_saratov/finalize_regional_research.py'
WORKFLOW_PATH = '.github/workflows/finalize-saratov-fields.yml'
UNPUBLISHED_NOTICE = ('Diagnostic fresh outputs only. Expected all-row control did not match; '
    'no release or scientific publication was created.\n')
HISTORICAL = {
    'tables': {'field_sensitivity/unbounded_federal_city_costs.parquet',
               'field_sensitivity/unbounded_selected_origins.parquet'},
    'scientific_summaries': {'field_sensitivity/summary.json'},
}
PINNED = {
    'actual_control.json': {'bytes': 549425, 'sha256': 'a8828c7a61f0dbdd691640723bdf55e430ac2d468f7a04a30c4e15945b67fe6b'},
    'expected_control.json': {'bytes': 558556, 'sha256': 'ed1b98e1c858d5430bb86238aa9c63f6c2ba3dda5ec3c59c516f1b3bfb64e064'},
    'independent_checks.zip': {'bytes': 21326, 'sha256': '440b206779292c8f4ddd3a33ceb1511ab2822d08311631a9091d3817f36a316e'},
    'unpublished_mismatch_results.zip': {'bytes': 639778651, 'sha256': '348d5cda0837831b6ea1f7171e342d39965f2729af5662b065e4d1848227da5a'},
}


def trimmed_original_control(original):
    result = copy.deepcopy(original)
    for group, names in HISTORICAL.items():
        for name in names:
            if name not in result[group]:
                raise ValueError('Original expected inventory lacks the documented historical probe: '+name)
            del result[group][name]
    return result


def verify_control_inventory(original, current_expected, preserved_actual):
    expected = trimmed_original_control(original)
    if current_expected != expected:
        raise ValueError('New expected control must be exactly the original minus the three historical probe names')
    if preserved_actual != expected:
        raise ValueError('Preserved actual control differs from the exact current scientific inventory')
    return expected


def protected_wrapper_ast(text):
    module = ast.parse(text)
    module.body = [node for node in module.body if not (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {'scientific_files', 'package'}
        or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'HISTORICAL_PROBE_FILES' for t in node.targets))]
    return ast.dump(module, include_attributes=False)


def verify_wrapper_change(original, current):
    if protected_wrapper_ast(original) != protected_wrapper_ast(current):
        raise ValueError('Protected producer build, inputs, acquisition, constants or numerical comparators changed')
    assignments = [node for node in ast.parse(current).body if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'HISTORICAL_PROBE_FILES' for t in node.targets)]
    if len(assignments) != 1 or ast.literal_eval(assignments[0].value) != set().union(*HISTORICAL.values()):
        raise ValueError('Historical probe exclusions must contain exactly the documented three relative paths')


def allowed_noncomputational_change(path):
    exact = {EXPECTED_PATH, WRAPPER_PATH, SELF_PATH, WORKFLOW_PATH,
        '.github/workflows/transfer-saratov-diagnostics.yml',
        'tests/test_sgrt_saratov_finalize_regional_research.py',
        'tests/test_sgrt_saratov_producer_inventory.py', 'research_context/current_state.json',
        'research_context/analysis_snapshots/saratov_early_eight_origin_probe_20261028.json',
        'references/sources.json'}
    return path in exact or path.endswith('.md') or path.startswith('web/content/')


def verify_scientific_source(assembly_commit, repository=REPO):
    repository = Path(repository)
    if not re.fullmatch(r'[0-9a-f]{40}', assembly_commit):
        raise ValueError('Full assembly commit SHA required')
    changed = subprocess.check_output(['git', 'diff', '--name-only', COMPUTATION_COMMIT, assembly_commit],
        cwd=repository, text=True).splitlines()
    forbidden = [name for name in changed if not allowed_noncomputational_change(name)]
    if forbidden:
        raise ValueError('Scientific code, sources, dependencies, catalogues or frontend changed: '+repr(forbidden))
    original = subprocess.check_output(['git', 'show', COMPUTATION_COMMIT+':'+WRAPPER_PATH], cwd=repository, text=True)
    current = subprocess.check_output(['git', 'show', assembly_commit+':'+WRAPPER_PATH], cwd=repository, text=True)
    verify_wrapper_change(original, current)
    return {'computation_commit': COMPUTATION_COMMIT, 'assembly_commit': assembly_commit,
        'changed_noncomputational_paths': changed, 'all_other_tracked_files_byte_identical': True,
        'protected_producer_ast_identical': True, 'numerical_precision_or_tolerances_changed': False}


def safe_extract(path, target, *, allowed_roots=None, allowed_root_files=(), expected_members=None):
    """Reject path escapes, symlinks, duplicate names and unexpected payloads."""
    target = Path(target)
    if target.exists() and any(target.iterdir()):
        raise ValueError('Extraction target must be empty')
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 1000 or sum(v.file_size for v in entries) > 2_000_000_000:
            raise ValueError('Preserved archive exceeds its bounded scientific payload')
        if expected_members is not None and len(entries) != expected_members:
            raise ValueError('Preserved archive member count differs')
        names = [v.filename for v in entries]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive member')
        for info in entries:
            p = PurePosixPath(info.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in info.filename or not p.parts:
                raise ValueError('Unsafe archive path')
            if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK or info.flag_bits & 1:
                raise ValueError('Symlink or encrypted archive member rejected')
            if allowed_roots is not None and p.parts[0] not in allowed_roots and info.filename not in allowed_root_files:
                raise ValueError('Unexpected archive root')
            if not (target/p).resolve().is_relative_to(target.resolve()):
                raise ValueError('Archive path escapes extraction directory')
        target.mkdir(parents=True, exist_ok=True)
        archive.extractall(target)
    return names


def original_run_metadata():
    run = json.loads(subprocess.check_output(['gh', 'api',
        f'repos/{producer.REPOSITORY}/actions/runs/{COMPUTATION_RUN}'], text=True))
    if (run['id'] != COMPUTATION_RUN or run['head_sha'] != COMPUTATION_COMMIT
            or run['path'] != '.github/workflows/publish-saratov-fields.yml'
            or run['status'] != 'completed' or run['conclusion'] != 'failure'):
        raise ValueError('Preserved computation run identity or state differs')
    return {key: run[key] for key in ('id', 'head_sha', 'path', 'status', 'conclusion', 'html_url')}


def declared_original_inputs(results, receipt):
    """Reconstruct declarations honestly: verification occurred in the source run."""
    declarations = []
    for catalog, selected in producer.inputs().items():
        doc = json.loads((REPO/catalog).read_text())
        records = {r['path']: r for r in doc['files']}
        files = []
        for name in selected:
            record = records[name]; obj = doc['objects'][record['blob']]
            files.append({'path': name, 'bytes': obj['bytes'], 'sha256': obj['sha256'],
                'asset': record['asset'], 'blob': record['blob']})
        declarations.append({'kind': 'original_run_pinned_input_declarations', 'catalog': catalog,
            'catalog_sha256': sha(REPO/catalog), 'source_release': doc['release_tag'],
            'source_commit': doc['source_commit'], 'files': files,
            'verification_run_id': COMPUTATION_RUN, 'downloaded_again_by_finalizer': False})
    frozen = json.loads(producer.FROZEN.read_text())
    documents = results/'source_documents'
    for spec in frozen['files']:
        verify(documents/spec['path'], spec)
    provenance = json.loads(producer.MAGNIT_PROVENANCE.read_text())
    verify(documents/'commerce/locator_raw.json', provenance['raw_response'])
    for name in ('locator_query.json', 'locator_shops_route_Da75p-8i.js'):
        source = REPO/'references/primary/saratov_magnit_20261028'/name
        if (documents/'commerce'/name).read_bytes() != source.read_bytes():
            raise ValueError('Frozen Magnit primary source differs: '+name)
    declarations.extend(producer.curated_source_proofs())
    declarations.append({'kind': 'original_run_verified_frozen_input_documents',
        'frozen_manifest_sha256': sha(producer.FROZEN), 'files': frozen['files'],
        'original_archive_declarations': frozen['assets'],
        'original_archive_downloaded_or_reverified_by_finalizer': False,
        'verification_run_id': COMPUTATION_RUN, 'downloaded_again_by_finalizer': False})
    declarations.append({'kind': 'preserved_computation_provenance', **receipt})
    return declarations


def finalize(preserved, work, assembly_commit):
    clean_commit(assembly_commit)
    preserved, work = Path(preserved).resolve(), Path(work).resolve()
    if not preserved.is_dir() or preserved.is_relative_to(REPO) or work.exists() or work.is_relative_to(REPO):
        raise ValueError('Use existing external preserved inputs and a fresh external work directory')
    source_proof = verify_scientific_source(assembly_commit)
    source_run = original_run_metadata()
    for name, spec in PINNED.items():
        verify(preserved/name, spec)
    original = json.loads((preserved/'expected_control.json').read_text())
    saved_actual = json.loads((preserved/'actual_control.json').read_text())
    expected = json.loads(producer.EXPECTED.read_text())
    verify_control_inventory(original, expected, saved_actual)
    names = safe_extract(preserved/'unpublished_mismatch_results.zip', work,
        allowed_roots={'results', 'controls'}, allowed_root_files={'UNPUBLISHED.txt'}, expected_members=324)
    if (work/'UNPUBLISHED.txt').read_text() != UNPUBLISHED_NOTICE:
        raise ValueError('Original unpublished diagnostic notice differs')
    if (work/'controls/actual_control.json').read_bytes() != (preserved/'actual_control.json').read_bytes():
        raise ValueError('Preserved actual control differs between trusted containers')
    if (work/'controls/expected_control.json').read_bytes() != (preserved/'expected_control.json').read_bytes():
        raise ValueError('Preserved original expected control differs between trusted containers')
    checks = work/'checks'
    check_names = safe_extract(preserved/'independent_checks.zip', checks, expected_members=24)
    if any(len(PurePosixPath(name).parts) != 1 or not name.endswith('.json') for name in check_names):
        raise ValueError('Independent checks must be the original flat JSON reports')
    for name in check_names:
        producer.require_audit(checks/name)
    results = work/'results'
    producer.require_audit(results/'context/worker_field_independent_numeric.json')
    producer.require_audit(results/'rural_routes/rural_school_transport_counterexamples.json')
    actual = producer.control(results)
    verify_control_inventory(original, expected, actual)
    write(work/'actual_control.json', actual)
    receipt = {'schema': 'sgrt.saratov.preserved_computation.v1',
        'computation_source_commit': COMPUTATION_COMMIT, 'computation_run_id': COMPUTATION_RUN,
        'assembly_source_commit': assembly_commit, 'assembly_run_id': os.environ.get('GITHUB_RUN_ID'),
        'source_run': source_run, 'source_compatibility': source_proof, 'preserved_assets': PINNED,
        'historical_inventory_omissions_only': {k: sorted(v) for k, v in HISTORICAL.items()},
        'all_output_rows_cells_missingness_and_geometries_rehashed': True,
        'exact_current_control_equal': True, 'numerical_precision_or_tolerances_changed': False,
        'original_independent_checks_verified': len(check_names), 'preserved_result_members': len(names),
        'scientific_computation_repeated_during_assembly': False}
    write(checks/'preserved_computation_provenance.json', receipt)
    write(results/'source_manifest.json', declared_original_inputs(results, receipt))
    subprocess.run(['node', str(REPO/'scripts/sgrt_saratov/render_figures.mjs'),
        '--results', str(results), '--output', str(results/'figures'),
        '--source-commit', assembly_commit, '--require-clean-producer'], cwd=REPO, check=True)
    proof = json.loads((results/'figures/render_proof.json').read_text())
    if proof.get('public_dataset_qa') is not False or len(proof.get('figures', [])) != 4:
        raise ValueError('Four source-rendered figures with explicit local-render scope required')
    built = producer.package(work, assembly_commit)
    manifest = json.loads((built/'manifest.json').read_text())
    manifest.update(computation_source_commit=COMPUTATION_COMMIT, computation_run_id=COMPUTATION_RUN,
        assembly_source_commit=assembly_commit, assembly_run_id=os.environ.get('GITHUB_RUN_ID'),
        scientific_computation_repeated_during_assembly=False, preserved_computation=receipt)
    write(built/'manifest.json', manifest)
    with (built/'release_notes.md').open('a') as stream:
        stream.write('\nНаучные данные рассчитаны запуском '+str(COMPUTATION_RUN)+' из коммита '+COMPUTATION_COMMIT+
            '. После удаления только трёх исторических проб из ожидаемого перечня все строки и ячейки сохранённых результатов проверены повторно и совпали точно. '
            'Сборка и экспорт иллюстраций выполнены коммитом '+assembly_commit+'; повторного моделирования при сборке не было.\n')
    release_id = producer.draft(built, assembly_commit)
    write(work/'draft.json', {'release_id': release_id, 'release_tag': producer.TAG,
        'draft': True, 'source_commit': assembly_commit, 'computation_source_commit': COMPUTATION_COMMIT,
        'computation_run_id': COMPUTATION_RUN, 'publication_requires_separate_byte_verification': True})
    return release_id


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preserved-dir', type=Path, required=True)
    p.add_argument('--workdir', type=Path, required=True)
    p.add_argument('--source-commit', required=True)
    args = p.parse_args()
    print(json.dumps({'draft_release_id': finalize(args.preserved_dir, args.workdir, args.source_commit)}))


if __name__ == '__main__':
    main()
