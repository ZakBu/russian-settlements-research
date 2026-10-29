"""Assemble preserved v2 results after exact and existing-tolerance verification.

The original unequal controls remain unequal and are packaged without changes.
No transport query or mathematical model is rerun during this assembly.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_saratov import cloud_regional_research as producer
from scripts.sgrt_saratov.finalize_regional_research import safe_extract, UNPUBLISHED_NOTICE
from scripts.sgrt_zero.cloud_common_systems import clean_commit, sha, verify, write

COMPUTATION_COMMIT = '3a8c35339d2719a8c433c669ea98bc99a3685f5e'
COMPUTATION_RUN = 40827228874
DIAGNOSTIC_ID = 427566999
DIAGNOSTIC_TAG = 'diagnostic-saratov-fields-v2-40827228874'
EXPECTED_PATH = 'research_context/analysis_snapshots/regional_fields_control_20261029_v2.json'
WORKFLOW_PATH = '.github/workflows/finalize-saratov-fields-v2.yml'
V1_URL = 'https://github.com/ZakBu/russian-settlements-research/releases/download/sgrt-saratov-fields-20261029-v1/saratov-fields.zip'
V1_SPEC = {'bytes': 645292645, 'sha256': '2328cf7a6b2572c84e8cdf6450c5563feb956e32c1ccfc8d72ba174e05d6a9b2'}
PINNED = {
    'actual_control.json': {'bytes': 549425, 'sha256': '8f55ac37201da299d278cac99fc5019578e4e1da40c85ae8a93f2da641e7c8eb'},
    'expected_control.json': {'bytes': 549425, 'sha256': '4c76dcad6d449d9bcec6bccea4c90df04cd693b5c770338f9630a75a13ed828a'},
    'independent_checks.zip': {'bytes': 21325, 'sha256': '6e69b15c190b5e3d2fb488657081830a4ae52ab891187793286d455cc0ecd1f2'},
    'unpublished_mismatch_results.zip': {'bytes': 639773422, 'sha256': 'c51d54f8f2fdaac9c6383baa6498b1d2e910dacddd5f817db9794489a38a44ed'},
}
NUMERIC_TABLES = {
    'context/known_partial_worker_fields.parquet',
    'field_sensitivity/ordinary_horizon480_reference/fields.parquet',
    'field_sensitivity/ordinary_horizon480_reference/halo_fields.parquet',
    'fields/fields.parquet', 'fields/halo_fields.parquet',
    'organisation/point_maxima.parquet',
}


def verify_control_difference(expected, actual):
    """Permit only the six already diagnosed hash leaves, never changed controls."""
    if set(expected) != set(actual):
        raise ValueError('Scientific control groups changed')
    differences = set()
    for group in expected:
        if group != 'tables':
            if expected[group] != actual[group]:
                raise ValueError('Non-table scientific controls differ: '+group)
            continue
        if set(expected[group]) != set(actual[group]):
            raise ValueError('Table inventory changed')
        for name, before in expected[group].items():
            after = actual[group][name]
            if before == after:
                continue
            if name not in NUMERIC_TABLES or set(before) != set(after):
                raise ValueError('Unexpected changed table: '+name)
            if {k:v for k,v in before.items() if k != 'sha256'} != {k:v for k,v in after.items() if k != 'sha256'}:
                raise ValueError('Table schema, count or metadata changed: '+name)
            differences.add(name)
    if differences != NUMERIC_TABLES:
        raise ValueError('Original six control differences must remain present')
    return sorted(differences)


def allowed_assembly_change(path):
    exact = {
        'scripts/sgrt_saratov/finalize_v2_regional_research.py',
        'scripts/sgrt_saratov/preserved_numeric_comparison.py',
        'scripts/sgrt_saratov/register_release.py',
        'scripts/sgrt_saratov/publish_verified_regional.py',
        'tests/test_sgrt_saratov_finalize_v2_regional_research.py',
        'tests/test_sgrt_saratov_preserved_numeric_comparison.py',
        'tests/test_sgrt_saratov_release_registration.py',
        'tests/test_sgrt_saratov_verified_publication.py',
        WORKFLOW_PATH, '.github/workflows/transfer-saratov-v2-diagnostics.yml',
        '.github/workflows/extract-saratov-v2-diagnostics.yml',
        'research_context/current_state.json',
        'research_context/analysis_snapshots/saratov_v2_centre_scale_20261029.json',
        'research_context/analysis_snapshots/saratov_v2_failed_fresh_40827228874_actual.json',
        'research_context/analysis_snapshots/saratov_v2_failed_fresh_40827228874_diff.json',
    }
    return (path in exact or path.endswith('.md') or path.startswith('web/content/')
            or path.startswith('research_context/analysis_snapshots/saratov_v2_numeric_'))


def verify_scientific_source(assembly_commit, repository=REPO):
    if not re.fullmatch(r'[0-9a-f]{40}', assembly_commit):
        raise ValueError('Exact assembly SHA required')
    changed = subprocess.check_output(['git','diff','--name-only',COMPUTATION_COMMIT,assembly_commit],cwd=repository,text=True).splitlines()
    forbidden = [p for p in changed if not allowed_assembly_change(p)]
    if forbidden:
        raise ValueError('Protected scientific code, inputs, expected control or dependencies changed: '+repr(forbidden))
    return {'computation_commit':COMPUTATION_COMMIT,'assembly_commit':assembly_commit,
        'changed_nonmathematical_paths':changed,'all_other_tracked_files_byte_identical':True,
        'mathematical_producer_and_expected_control_byte_identical':True,
        'numerical_precision_or_tolerances_changed':False}


def verify_source_run():
    run=json.loads(subprocess.check_output(['gh','api',f'repos/{producer.REPOSITORY}/actions/runs/{COMPUTATION_RUN}'],text=True))
    if (run['id'] != COMPUTATION_RUN or run['head_sha'] != COMPUTATION_COMMIT
            or run['path'] != '.github/workflows/publish-saratov-fields.yml'
            or run['status'] != 'completed' or run['conclusion'] != 'failure'):
        raise ValueError('Original preserved run identity differs')
    release=json.loads(subprocess.check_output(['gh','api',f'repos/{producer.REPOSITORY}/releases/{DIAGNOSTIC_ID}'],text=True))
    if release['id'] != DIAGNOSTIC_ID or not release['draft'] or release['tag_name'] != DIAGNOSTIC_TAG or release['target_commitish'] != COMPUTATION_COMMIT:
        raise ValueError('Original diagnostic draft identity differs')
    assets={a['name']:a for a in release['assets']}
    for name,spec in PINNED.items():
        if assets[name]['size'] != spec['bytes'] or assets[name]['digest'] != 'sha256:'+spec['sha256']:
            raise ValueError('Diagnostic asset changed: '+name)
    return {k:run[k] for k in ('id','head_sha','path','status','conclusion','html_url')}


def declared_inputs(results, receipt):
    declarations=[]
    for catalog,selected in producer.inputs().items():
        doc=json.loads((REPO/catalog).read_text());records={r['path']:r for r in doc['files']};files=[]
        for name in selected:
            r=records[name];obj=doc['objects'][r['blob']]
            files.append({'path':name,'bytes':obj['bytes'],'sha256':obj['sha256'],'asset':r['asset'],'blob':r['blob']})
        declarations.append({'kind':'original_run_pinned_input_declarations','catalog':catalog,
            'catalog_sha256':sha(REPO/catalog),'source_release':doc['release_tag'],'source_commit':doc['source_commit'],
            'files':files,'verification_run_id':COMPUTATION_RUN,'downloaded_again_by_finalizer':False})
    frozen=json.loads(producer.FROZEN.read_text());documents=results/'source_documents'
    for spec in frozen['files']:verify(documents/spec['path'],spec)
    verify(documents/'commerce/locator_raw.json',json.loads(producer.MAGNIT_PROVENANCE.read_text())['raw_response'])
    for name in ('locator_query.json','locator_shops_route_Da75p-8i.js'):
        if (documents/'commerce'/name).read_bytes() != (REPO/'references/primary/saratov_magnit_20261028'/name).read_bytes():
            raise ValueError('Frozen commerce source changed')
    declarations.extend(producer.curated_source_proofs())
    declarations.extend([{'kind':'original_run_verified_frozen_input_documents','frozen_manifest_sha256':sha(producer.FROZEN),
        'files':frozen['files'],'original_archive_declarations':frozen['assets'],
        'original_archive_downloaded_or_reverified_by_finalizer':False,'verification_run_id':COMPUTATION_RUN,
        'downloaded_again_by_finalizer':False},{'kind':'preserved_computation_provenance',**receipt}])
    return declarations


def add_assembly_workflow(built, assembly_commit):
    """Add only this new assembly workflow, authenticated against its Git blob."""
    manifest_path=built/'manifest.json';manifest=json.loads(manifest_path.read_text())
    name='reproduction/'+WORKFLOW_PATH;data=(REPO/WORKFLOW_PATH).read_bytes()
    if data != subprocess.check_output(['git','show',assembly_commit+':'+WORKFLOW_PATH],cwd=REPO):
        raise ValueError('Assembly workflow differs from exact Git source')
    archive=built/manifest['archive']['asset']
    with zipfile.ZipFile(archive,'a',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        if name in z.namelist() or any(r['path']==name for r in manifest['files']):
            raise ValueError('Duplicate assembly workflow')
        z.writestr(name,data)
    manifest['files'].append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    manifest['archive'].update(bytes=archive.stat().st_size,sha256=sha(archive))
    return manifest


def verify_numeric_proof(numeric):
    if (numeric.get('scientific_results_reproduce_with_existing_arithmetic_tolerance') is not True
            or numeric.get('strict_control_equal') is not False):
        raise ValueError('Numeric proof must confirm scientific reproduction and preserve unequal controls')


def finalize(preserved, reference, work, assembly_commit):
    from scripts.sgrt_saratov.preserved_numeric_comparison import compare_preserved
    clean_commit(assembly_commit)
    preserved,reference,work=Path(preserved).resolve(),Path(reference).resolve(),Path(work).resolve()
    if not preserved.is_dir() or preserved.is_relative_to(REPO) or work.exists() or work.is_relative_to(REPO):
        raise ValueError('Use preserved inputs and a fresh work directory outside Git')
    source=verify_scientific_source(assembly_commit);run=verify_source_run()
    if producer.TAG!='sgrt-saratov-fields-20261029-v2' or any(r['tag_name']==producer.TAG for r in producer.releases()):
        raise ValueError('Wrong target version or existing v2 release; no overwrite')
    for name,spec in PINNED.items():verify(preserved/name,spec)
    verify(reference,V1_SPEC)
    expected_raw=(preserved/'expected_control.json').read_bytes();actual_raw=(preserved/'actual_control.json').read_bytes()
    if producer.EXPECTED.read_bytes()!=expected_raw:raise ValueError('Original expected control changed')
    expected,actual=json.loads(expected_raw),json.loads(actual_raw)
    verify_control_difference(expected,actual)
    safe_extract(preserved/'unpublished_mismatch_results.zip',work,allowed_roots={'results','controls'},allowed_root_files={'UNPUBLISHED.txt'})
    if (work/'UNPUBLISHED.txt').read_text()!=UNPUBLISHED_NOTICE:raise ValueError('Original notice changed')
    for name,raw in [('expected_control.json',expected_raw),('actual_control.json',actual_raw)]:
        if (work/'controls'/name).read_bytes()!=raw:raise ValueError('Embedded original control changed')
    checks=work/'checks';names=safe_extract(preserved/'independent_checks.zip',checks,expected_members=24)
    if any(Path(n).name!=n or not n.endswith('.json') for n in names):raise ValueError('Non-flat check payload')
    for name in names:producer.require_audit(checks/name)
    results=work/'results'
    producer.require_audit(results/'context/worker_field_independent_numeric.json')
    producer.require_audit(results/'rural_routes/rural_school_transport_counterexamples.json')
    if producer.control(results)!=actual:raise ValueError('Preserved fresh outputs no longer reproduce their original control')
    numeric=compare_preserved(preserved/'unpublished_mismatch_results.zip',reference,expected,actual)
    verify_numeric_proof(numeric)
    write(checks/'preserved_numeric_comparison.json',numeric)
    # Keep both original, unequal control documents byte-for-byte.
    (work/'actual_control.json').write_bytes(actual_raw)
    receipt={'schema':'sgrt.saratov.preserved_v2_computation.v1','computation_source_commit':COMPUTATION_COMMIT,
        'computation_run_id':COMPUTATION_RUN,'assembly_source_commit':assembly_commit,'assembly_run_id':os.environ.get('GITHUB_RUN_ID'),
        'source_run':run,'source_compatibility':source,'preserved_assets':PINNED,'numeric_reference':V1_SPEC,
        'all_output_rows_cells_missingness_and_geometries_rehashed':True,'preserved_actual_control_reproduced_exactly':True,
        'exact_current_control_equal':False,'original_expected_and_actual_controls_preserved_unequal':True,
        'numerical_precision_or_tolerances_changed':False,'existing_scientific_numeric_comparison':numeric,
        'original_independent_checks_verified':len(names),'scientific_computation_repeated_during_assembly':False}
    write(checks/'preserved_computation_provenance.json',receipt)
    write(results/'source_manifest.json',declared_inputs(results,receipt))
    subprocess.run(['node',str(REPO/'scripts/sgrt_saratov/render_figures.mjs'),'--results',str(results),'--output',str(results/'figures'),'--source-commit',assembly_commit,'--require-clean-producer'],cwd=REPO,check=True)
    figure=json.loads((results/'figures/render_proof.json').read_text())
    if figure.get('public_dataset_qa') is not False or len(figure.get('figures',[]))!=4:raise ValueError('Four verified source-rendered figures required')
    built=producer.package(work,assembly_commit);manifest=add_assembly_workflow(built,assembly_commit)
    manifest.update(computation_source_commit=COMPUTATION_COMMIT,computation_run_id=COMPUTATION_RUN,
        assembly_source_commit=assembly_commit,assembly_run_id=os.environ.get('GITHUB_RUN_ID'),
        scientific_computation_repeated_during_assembly=False,preserved_computation=receipt)
    write(built/'manifest.json',manifest)
    with (built/'release_notes.md').open('a') as stream:
        stream.write('\nOriginal local and fresh control fingerprints differ in six floating-point table hashes and are preserved unchanged. Every affected cell is checked against the unchanged pre-existing scientific numerical tolerance; all other controls match exactly. No mathematical calculation is rerun by assembly.\n')
    release_id=producer.draft(built,assembly_commit)
    write(work/'draft.json',{'release_id':release_id,'release_tag':producer.TAG,'draft':True,'source_commit':assembly_commit,
        'computation_source_commit':COMPUTATION_COMMIT,'computation_run_id':COMPUTATION_RUN,
        'publication_requires_separate_byte_and_numeric_verification':True})
    return release_id


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preserved-dir',type=Path,required=True);p.add_argument('--numeric-reference-archive',type=Path,required=True)
    p.add_argument('--workdir',type=Path,required=True);p.add_argument('--source-commit',required=True);a=p.parse_args()
    print(json.dumps({'draft_release_id':finalize(a.preserved_dir,a.numeric_reference_archive,a.workdir,a.source_commit)}))


if __name__=='__main__':main()
