"""Verify supplied identity-release bytes against the frozen Git producer.

This client checks archive integrity, producer code and archived scientific
attestations. It neither reruns the scientific model nor retrieves a public URL.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from urllib.parse import quote
import zipfile

REPO = Path(__file__).resolve().parents[2]
CONTROL = 'research_context/analysis_snapshots/identity_model_control_20261026.json'
HOLDS = 'references/provenance/coordinate_holds_20261026.json'
ERRATA = 'references/provenance/coordinate_evidence_errata_20261026.json'
SCIENTIFIC_FLAGS = ('all_source_offer_rows_and_eligibility_equal', 'all12_routing_layers_equal',
                    'all_admitted_choices_equal', 'all_level0_centre_and_member_identities_equal',
                    'independent_registry_recheck_completed')
REGISTRY_FLAGS = ('independent_of_centre_and_registry_builders', 'all_centre_ids_equal',
                  'all_direct_pairs_and_single_anchors_equal', 'all_own_function_sets_and_types_equal',
                  'all_member_reference_metadata_equal', 'all_population_budgets_and_partial_flags_equal',
                  'all_ownership_evidence_classes_equal', 'all_retained_basic_links_equal',
                  'all_external_basic_car_times_within_source_caps',
                  'all_admitted_outcomes_exclude_coordinate_held_NPs', 'inputs_unchanged')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_member(name):
    require(isinstance(name, str) and bool(name) and '\\' not in name and '\0' not in name
            and ':' not in name and not PurePosixPath(name).is_absolute()
            and all(part not in {'', '.', '..'} for part in name.split('/')),
            'Unsafe archive path: ' + repr(name))
    return name


def hash_stream(stream):
    digest, size = hashlib.sha256(), 0
    while chunk := stream.read(4 * 1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def file_spec(path):
    with Path(path).open('rb') as stream:
        return hash_stream(stream)


def strict_json(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(payload, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + value)))


def read_json(archive, name):
    return strict_json(archive.read(name))


def without_archive(manifest):
    return {key: value for key, value in manifest.items() if key != 'archive'}


def verify_archive_integrity(manifest, archive_path):
    """Read every member, including the embedded manifest, to its final byte."""
    prefix = manifest['archive_root']
    require(isinstance(prefix, str) and prefix.endswith('/'), 'Archive root must end in /')
    safe_member(prefix[:-1])
    expected = {}
    for relative, spec in manifest['files'].items():
        safe_member(relative)
        require(relative != 'manifest.json', 'Embedded manifest cannot hash itself')
        require(isinstance(spec.get('bytes'), int) and spec['bytes'] >= 0
                and re.fullmatch('[0-9a-f]{64}', str(spec.get('sha256', ''))), 'Invalid file size or SHA: ' + relative)
        expected[prefix + relative] = spec
    require(bool(expected), 'An empty result archive is not a release')
    outer = file_spec(archive_path)
    require(outer == {key: manifest['archive'][key] for key in ['bytes', 'sha256']},
            'Outer archive size/SHA mismatch')
    checked = {}
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [safe_member(info.filename) for info in infos]
        require(len(names) == len(set(names)), 'Duplicate archive member')
        require(set(names) == set(expected) | {prefix + 'manifest.json'}, 'Archive file set differs from manifest')
        for info in infos:
            require(not info.is_dir() and not stat.S_ISLNK(info.external_attr >> 16)
                    and not info.flag_bits & 1, 'Directories, symlinks or encrypted members are not accepted')
            with archive.open(info) as stream:
                spec = hash_stream(stream)
            require(spec['bytes'] == info.file_size, 'ZIP member size mismatch: ' + info.filename)
            if info.filename in expected:
                require(spec == {key: expected[info.filename][key] for key in ['bytes', 'sha256']},
                        'Member size/SHA mismatch: ' + info.filename)
            checked[info.filename] = spec
        embedded = read_json(archive, prefix + 'manifest.json')
        require(without_archive(embedded) == without_archive(manifest), 'Embedded and external manifests differ')
    return checked


def git_bytes(commit, relative, repo=REPO):
    safe_member(relative)
    return subprocess.check_output(['git', 'show', commit + ':' + relative], cwd=repo,
                                   stderr=subprocess.PIPE)


def git_blob_spec(commit, relative, repo=REPO):
    with subprocess.Popen(['git', 'show', commit + ':' + safe_member(relative)], cwd=repo,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        with process.stdout as stream:
            result = hash_stream(stream)
        with process.stderr as stream:
            error = stream.read()
        require(process.wait() == 0, 'Producer has no archived reproduction file: ' + relative + ': ' + error.decode(errors='replace'))
    return result


def verify_reproduction(archive, prefix, checked, commit, repo=REPO):
    require(re.fullmatch('[0-9a-f]{40}', commit), 'A complete producer commit SHA is required')
    resolved = subprocess.check_output(['git', 'rev-parse', commit + '^{commit}'], cwd=repo, text=True).strip()
    require(resolved == commit, 'Producer commit does not resolve exactly')
    tree = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit], cwd=repo).decode().splitlines()
    required_python = {path for path in tree if path.endswith('.py') and (
        str(PurePosixPath(path).parent) in {'scripts/sgrt_zero', 'scripts/sgrt_mass', 'scripts/sgrt_local'}
        or (str(PurePosixPath(path).parent) == 'tests' and PurePosixPath(path).name.startswith('test_sgrt_zero_')))}
    reproduction = prefix + 'reproduction/'
    actual = {name[len(reproduction):] for name in checked if name.startswith(reproduction)}
    require(required_python <= actual, 'Producer Python scripts/tests missing from reproduction: ' + repr(sorted(required_python - actual)))
    require(bool(actual), 'No archived reproduction context')
    for path in sorted(actual):
        require(checked[reproduction + path] == git_blob_spec(commit, path, repo),
                'Archived reproduction bytes differ from producer commit: ' + path)
    return {'all_reproduction_files_match_producer': True, 'reproduction_files': len(actual),
            'required_producer_python_files': len(required_python)}


def producer_constant(commit, name, repo=REPO):
    tree = ast.parse(git_bytes(commit, 'scripts/sgrt_zero/pack_identity_results.py', repo))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Producer packer constant missing: ' + name)


def verify_scientific_attestations(archive, manifest, checked, commit, repo=REPO):
    prefix = manifest['archive_root']
    require(prefix == producer_constant(commit, 'PREFIX', repo), 'Archive prefix differs from producer')
    require(manifest['release_tag'] == producer_constant(commit, 'TAG', repo), 'Release tag differs from producer')
    require(manifest['source_places'] == producer_constant(commit, 'SOURCE_ZIP', repo), 'Raw place source differs from producer')
    dependencies = producer_constant(commit, 'DEPENDENCY_CONTEXT', repo) + [CONTROL]
    require(all(prefix + 'reproduction/' + safe_member(path) in checked for path in dependencies),
            'A required frozen reproduction dependency is missing')
    expected_bytes = git_bytes(commit, CONTROL, repo)
    expected = strict_json(expected_bytes)
    actual = read_json(archive, prefix + 'analysis/cloud_identity_control.json')
    require(actual == expected, 'Archived all-row scientific control differs from producer control')
    forward = read_json(archive, prefix + 'routes/independent_forward_checks.json')
    require({key: forward[key] for key in ['services', 'cases', 'all_equal']} == expected['forward_checks']
            and forward['services'] == 12 and forward['cases'] >= 12 and forward['all_equal'] is True,
            'Archived independent forward checks differ from producer control')
    verification = read_json(archive, prefix + 'analysis/scientific_verification.json')
    require(verification.get('source_commit') == commit and all(verification.get(key) is True for key in SCIENTIFIC_FLAGS),
            'Incomplete scientific verification flags or wrong producer')
    require(verification.get('expected_control_sha256') == hashlib.sha256(expected_bytes).hexdigest(), 'Scientific control SHA mismatch')
    require(verification.get('observed_journeys_established') is False, 'Attestation incorrectly claims observed journeys')
    summary = read_json(archive, prefix + 'registry/summary.json')
    counts = {key: value for key, value in summary.items() if key != 'inputs_sha256'}
    require(counts == manifest['registry_counts'], 'Manifest registry counts differ from archived summary')
    semantic_counts = {key: value for key, value in summary.items() if key not in {'inputs_sha256', 'diameter_km', 'full_centres_diameter_km'}}
    require(semantic_counts == expected['registry_counts'], 'Registry counts differ from producer scientific control')
    independent = read_json(archive, prefix + 'analysis/independent_level0_check.json')
    require(all(independent.get(key) is True for key in REGISTRY_FLAGS), 'Incomplete independent registry attestation')
    require(independent['registered_centres'] == counts['registered_level0_centres']
            and independent['centre_member_pairs'] == counts['centre_member_pairs']
            and independent['by_own_known_basic_function_count'] == counts['by_recorded_own_basic_function_count'],
            'Independent registry counts disagree')
    require(independent.get('earth_radius_km') == 6371.0088 and independent.get('ellipsoid_used') is False
            and independent.get('largest_reported_diameters_independently_checked') == 50
            and len(independent.get('diameter_cases', [])) == 50, 'Fifty spherical diameter checks are required')
    require(independent.get('actual_trips_or_all_institution_suitability_verified') is False,
            'Independent check must not claim observed trips or universal institution suitability')
    require(independent['verification_code_sha256'] == checked[prefix + 'reproduction/scripts/sgrt_zero/verify_level0_registry.py']['sha256'],
            'Independent check used different verifier code')
    for path, digest in independent['inputs_sha256'].items():
        for relative in ['registry/level0_centres.parquet', 'registry/level0_memberships.parquet', 'registry/level0_basic_links.parquet']:
            if path.endswith('/' + relative.split('/')[-1]):
                require(checked[prefix + relative]['sha256'] == digest, 'Independent check used a different registry input')
        if path.endswith('/daily_edges.parquet'):
            require(checked[prefix + 'analysis/scenarios/daily_20_school30_wb/daily_edges.parquet']['sha256'] == digest,
                    'Independent check used different daily outcomes')
    require(manifest.get('population_default_catalog_unchanged') is True
            and manifest.get('unchanged_population_default_catalog') == 'data/catalog.json'
            and manifest.get('recomputed_nearest_layers') == 12
            and manifest.get('exclusive_country_partition_established') is False
            and manifest.get('observed_journeys_established') is False, 'Incorrect research scope or population default')
    frozen = read_json(archive, prefix + 'analysis/immutable_inputs_check.json')
    require(frozen.get('frozen_bundle_before_equals_after') is True and frozen.get('population_default_catalog_unchanged') is True
            and frozen.get('source_places_zip_sha256') == manifest['source_places']['sha256'], 'Immutable input evidence failed')
    holds = strict_json(git_bytes(commit, HOLDS, repo))['records']
    require(checked[prefix + 'reproduction/data/catalog.json'] == git_blob_spec(commit, 'data/catalog.json', repo),
            'Frozen default population catalogue differs from producer')
    require(set(independent['coordinate_hold_ids_independently_checked']) == {record['source_record_id'] for record in holds},
            'Independent check used a different coordinate hold set')
    proofs = read_json(archive, prefix + 'analysis/external_evidence/official_coordinate_evidence.json')
    wanted = [{'source_record_id': record['source_record_id'], **record['official_pdf_source'],
               'retained_filename': record['official_pdf_source']['sha256'] + '.pdf'}
              for record in holds if record.get('official_pdf_source')]
    require(proofs == wanted and bool(proofs), 'Official PDF proof differs from pinned coordinate evidence')
    for proof in proofs:
        member = prefix + 'analysis/external_evidence/' + safe_member(proof['retained_filename'])
        require(proof['status'] == 200 and checked[member] == {'bytes': proof['bytes'], 'sha256': proof['sha256']},
                'Retained official PDF does not match its proof')
    errata = read_json(archive, prefix + 'reproduction/' + ERRATA)
    for item in errata['errata']:
        require(checked[prefix + 'reproduction/' + safe_member(item['original_path'])]['sha256'] == item['original_sha256']
                and checked[prefix + 'reproduction/' + safe_member(item['corrected_snapshot_path'])]['sha256'] == item['corrected_snapshot_sha256'],
                'Bibliographic correction lost its two-version history')
        require(item['primary_pdf_sha256'] in {proof['sha256'] for proof in proofs}, 'Erratum refers to a different primary PDF')
    return {'producer_control_sha256': hashlib.sha256(expected_bytes).hexdigest(), 'registry_counts': counts,
            'official_pdf_sha256': [proof['sha256'] for proof in proofs], 'scientific_attestations_consistent': True,
            'bibliographic_erratum_history_preserved': True}, independent


def verify_registry_csv(archive, manifest, checked, independent):
    prefix = manifest['archive_root']
    member = prefix + 'registry/level0_centres.csv'
    standalone = manifest['standalone_assets']['level0_centres.csv']
    require(standalone['archive_member'] == member and standalone['asset'] == 'level0_centres.csv'
            and {key: standalone[key] for key in ['bytes', 'sha256']} == checked[member], 'Standalone CSV metadata differs from its archived copy')
    ids, functions, rows, external = set(), {}, 0, 0
    diameters = {}
    with archive.open(member) as raw:
        for row in csv.DictReader(io.TextIOWrapper(raw, encoding='utf-8', newline='')):
            # The public CSV intentionally exposes the stable census NP ID.
            # Internal star_id belongs to Parquet and the producer's full-row
            # control, both covered by the scientific attestation above.
            require(bool(row['centre_settlement_id']) and row['centre_settlement_id'] not in ids,
                    'Duplicate or empty CSV centre identity')
            ids.add(row['centre_settlement_id']); rows += 1
            count = str(int(row['own_known_basic_function_count']))
            functions[count] = functions.get(count, 0) + 1
            external += int(row['external_participant_count'])
            diameters[row['centre_settlement_id']] = float(row['core_diameter_km'])
    counts = manifest['registry_counts']
    require(rows == counts['registered_level0_centres'] and functions == counts['by_recorded_own_basic_function_count']
            and rows + external == counts['centre_member_pairs'], 'CSV rows/function counts/direct pair counts differ')
    require(independent['external_pairs'] == external, 'Independent external pair count differs from CSV')
    cases = independent['diameter_cases']
    require(len({case['centre_settlement_id'] for case in cases}) == 50, 'Repeated independent diameter case')
    threshold = sorted(diameters.values(), reverse=True)[49]
    checked_ids = {case['centre_settlement_id'] for case in cases}
    require({uid for uid, diameter in diameters.items() if diameter > threshold + 1e-7} <= checked_ids,
            'An unchecked CSV diameter is larger than the checked tail')
    for case in cases:
        uid = case['centre_settlement_id']
        require(uid in diameters and math.isclose(diameters[uid], case['reported_diameter_km'], abs_tol=1e-7, rel_tol=0)
                and diameters[uid] >= threshold - 1e-7
                and math.isclose(case['reported_diameter_km'], case['independent_spherical_diameter_km'], abs_tol=1e-7, rel_tol=0),
                'Independent diameter case differs from the published CSV')
    require(math.isclose(max(diameters.values()), counts['diameter_km']['maximum'], abs_tol=1e-7, rel_tol=0), 'CSV maximum diameter differs')
    return {'registry_csv_rows': rows, 'registry_csv_identity_column': 'centre_settlement_id',
            'registry_csv_identities_unique': True, 'registry_csv_function_and_pair_counts_equal': True,
            'fifty_diameter_cases_equal_published_CSV': True}


def create_catalog(manifest, checked, proof):
    asset = manifest['archive']['asset']
    safe_member(asset)
    require('/' not in asset, 'An archive asset must be a filename')
    objects, files = {}, []
    for member, spec in sorted(checked.items()):
        digest = spec['sha256']
        if digest not in objects:
            objects[digest] = {**spec, 'asset': asset, 'archive_member': member}
        files.append({'path': member, 'blob': digest, 'bytes': spec['bytes'], 'profiles': ['core', 'all'], 'asset': asset})
    tag = manifest['release_tag']
    return {'schema': 'sgrt.portable_data.v1', 'status': 'verified_complete', 'source_commit': manifest['source_commit'],
            'release_tag': tag, 'repository': 'ZakBu/russian-settlements-research',
            'scientific_scope': 'Conditional direct level-zero service catchments; overlapping, not observed journeys. Companion catalogue; default population database unchanged.',
            'verification_scope': 'Supplied local archive bytes and producer attestations verified; public URL retrieval is not verified by this utility.',
            'public_URL_retrieval_verified': False, 'population_default_catalog_unchanged': True,
            'unchanged_population_default_catalog': 'data/catalog.json',
            'profiles': {'core': 'All files in this explicitly selected companion archive', 'all': 'Same companion files'},
            'files': files, 'objects': objects,
            'assets': [{'asset': asset, 'status': 'verified', **{key: manifest['archive'][key] for key in ['bytes', 'sha256']},
                        'objects': sorted(objects), 'url': 'https://github.com/ZakBu/russian-settlements-research/releases/download/' + quote(tag, safe='') + '/' + quote(asset, safe='')}],
            'counts': {'files': len(files), 'unique_objects': len(objects), 'logical_bytes': sum(row['bytes'] for row in files)},
            'verification_proof': {'producer_control_sha256': proof['producer_control_sha256'], 'manifest_sha256': proof['manifest_sha256']}}


def verify_release(manifest_path, archive_path, commit, output, catalog_output=None, repo=REPO):
    require(re.fullmatch('[0-9a-f]{40}', commit), 'A complete producer commit SHA is required')
    manifest_path, archive_path, output = map(Path, [manifest_path, archive_path, output])
    protected = {manifest_path.resolve(), archive_path.resolve(), (Path(repo)/'data/catalog.json').resolve()}
    require(output.resolve() not in protected, 'Proof output must not overwrite inputs or default population catalogue')
    if catalog_output:
        require(Path(catalog_output).resolve() not in protected | {output.resolve()},
                'Companion catalogue must not overwrite inputs, proof or default population catalogue')
    manifest_spec = file_spec(manifest_path)
    manifest = strict_json(manifest_path.read_bytes())
    require(manifest.get('schema') == 'sgrt.identity_results_bundle.v1', 'Unsupported result manifest schema')
    require(manifest.get('source_commit') == commit, 'Manifest source commit differs from requested producer')
    asset = safe_member(manifest['archive']['asset'])
    require('/' not in asset and asset.endswith('.zip'), 'Archive asset must be a ZIP filename')
    checked = verify_archive_integrity(manifest, archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        reproduction = verify_reproduction(archive, manifest['archive_root'], checked, commit, repo)
        science, independent = verify_scientific_attestations(archive, manifest, checked, commit, repo)
        csv_proof = verify_registry_csv(archive, manifest, checked, independent)
    require(file_spec(manifest_path) == manifest_spec and file_spec(archive_path) == {
        key: manifest['archive'][key] for key in ['bytes', 'sha256']}, 'Release inputs changed during verification')
    proof = {'schema': 'sgrt.identity_release_verification.v1', 'verification_status': 'verified_supplied_local_files',
             'public_URL_retrieval_verified': False, 'scientific_model_rerun_by_this_utility': False,
             'source_commit': commit, 'manifest_sha256': manifest_spec['sha256'],
             'archive': manifest['archive'], 'streamed_member_count': len(checked),
             'all_member_sizes_and_sha256_equal': True, 'exact_safe_unique_member_set': True,
             'embedded_manifest_equals_external_without_archive': True, **reproduction, **science, **csv_proof}
    if catalog_output:
        catalog_output = Path(catalog_output)
        catalog_output.parent.mkdir(parents=True, exist_ok=True)
        catalog_output.write_text(json.dumps(create_catalog(manifest, checked, proof), ensure_ascii=False, indent=2) + '\n')
        proof['catalog_sha256'] = file_spec(catalog_output)['sha256']
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(proof, ensure_ascii=False, indent=2))
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['manifest', 'archive', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--catalog-output', type=Path)
    args = parser.parse_args()
    verify_release(args.manifest, args.archive, args.source_commit, args.output, args.catalog_output)
