"""Check supplied demographic release files against their frozen Git producer.

Publication and public HTTP retrieval are separate actions. This verifier checks
local supplied bytes, including every Parquet/CSV row, without publishing.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
from pathlib import Path
import re
import sys
import zipfile

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.sgrt_zero.identity_control import table_hash
from scripts.sgrt_zero.verify_identity_release import (
    REPO, create_catalog, file_spec, git_blob_spec, git_bytes, read_json,
    require, safe_member, strict_json, verify_archive_integrity,
)

WORKER = 'scripts/sgrt_zero/cloud_centre_demography.py'
CONTROL = 'research_context/analysis_snapshots/centre_demography_control_20261026.json'
FACTS = 'references/provenance/centre_demography_inputs_20261026.json'


def producer_constant(commit, name):
    for node in ast.parse(git_bytes(commit, WORKER)).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Producer constant missing: ' + name)


def verify(root, source_commit, output, catalog_output=None):
    root, output = Path(root), Path(output)
    require(re.fullmatch('[0-9a-f]{40}', source_commit), 'A complete producer SHA is required')
    manifest_path = root/'manifest.json'
    manifest_spec = file_spec(manifest_path)
    manifest = strict_json(manifest_path.read_bytes())
    require(manifest.get('schema') == 'sgrt.centre_demography_bundle.v1'
            and manifest.get('source_commit') == source_commit, 'Manifest schema or producer differs')
    asset = safe_member(manifest['archive']['asset'])
    require('/' not in asset, 'Archive asset must be a filename')
    archive_path = root/asset
    protected = {manifest_path.resolve(), archive_path.resolve(), (REPO/'data/catalog.json').resolve()}
    protected |= {(root/safe_member(name)).resolve() for name in manifest['standalone_assets']}
    require(output.resolve() not in protected, 'Proof must not overwrite release inputs or population catalogue')
    if catalog_output:
        require(Path(catalog_output).resolve() not in protected | {output.resolve()},
                'Companion catalogue must not overwrite inputs, proof or population catalogue')
    checked = verify_archive_integrity(manifest, archive_path)
    prefix = manifest['archive_root']
    require(prefix == producer_constant(source_commit, 'PREFIX')
            and manifest['release_tag'] == producer_constant(source_commit, 'TAG')
            and manifest['legend'] == producer_constant(source_commit, 'CATEGORIES'), 'Producer release scope differs')
    require(manifest.get('word_causal_types_established') is False
            and manifest.get('observed_trips_established') is False
            and manifest.get('main_evidence_mode') == 'strict_direct_observed'
            and manifest.get('main_period') == [2002, 2021]
            and manifest.get('main_scope') == 'centre_and_rural_external_fixed_2021_membership',
            'Demographic descriptions must not become causal or observed-trip classifications')
    reproduction = prefix+'reproduction/'
    reproduction_names = [name for name in checked if name.startswith(reproduction)]
    require(bool(reproduction_names), 'Reproduction context missing')
    for name in reproduction_names:
        require(checked[name] == git_blob_spec(source_commit, name[len(reproduction):]),
                'Reproduction bytes differ from producer: '+name)
    # The all-row hash implementation is also pinned, not silently borrowed
    # from an incompatible later model version in the consumer checkout.
    require(file_spec(REPO/'scripts/sgrt_zero/identity_control.py') ==
            git_blob_spec(source_commit, 'scripts/sgrt_zero/identity_control.py'),
            'Use a consumer with the producer-compatible semantic hash implementation')
    expected = strict_json(git_bytes(source_commit, CONTROL))
    facts = strict_json(git_bytes(source_commit, FACTS))
    require(manifest['semantic_control'] == expected and manifest['source_facts'] == facts,
            'Manifest differs from producer scientific control or source facts')
    tables = {}
    standalone = {}
    with zipfile.ZipFile(archive_path) as archive:
        require(read_json(archive, prefix+'actual_control.json') == expected,
                'Archived actual control differs from producer control')
        summary = read_json(archive, prefix+'readout/summary.json')
        require({key: value for key, value in summary.items() if key != 'input_sha256'} == expected['summary'],
                'Archived summary differs from producer semantic summary')
        figures = read_json(archive, prefix+'readout/figures/figure_values.json')
        require(figures == expected['figure_values'] and figures.get('causal_word_types_assigned') is False,
                'Figure values differ from the controlled descriptive counts')
        for name, spec in expected['tables'].items():
            frame = pd.read_parquet(io.BytesIO(archive.read(prefix+'readout/'+safe_member(name)+'.parquet')))
            require(list(frame.columns) == spec['columns'] and table_hash(frame, list(frame.columns)) == spec,
                    'All-row Parquet control differs: '+name)
            tables[name] = frame
        components = tables['centre_demographic_components']
        classes = tables['centre_demographic_classes']
        membership = tables['fixed_membership_population_evidence']
        n = summary['centres']
        require(len(classes) == 2*n and len(components) == 12*n
                and len(membership) == summary['centre_member_pairs'], 'Incomplete demographic table coverage')
        require(not any('_observed_known_' in column for column in components)
                and all(f'{label}_mode_eligible_known_sum' in components for label in ['start', 'end']),
                'Accepted values are incorrectly labelled observed')
        require(not classes.duplicated(['star_id', 'evidence_mode']).any()
                and all(len(group) == n for _, group in classes.groupby('evidence_mode')),
                'Class coverage is not exactly one row per centre and mode')
        require(classes.word_causal_type_established.eq(False).all()
                and classes.historical_boundary_equivalence_established.eq(False).all(), 'Causal or historical-boundary claims were introduced')
        for flag in ['accepted_values_mode_is_not_claimed_observed', 'protected_secondary_2010_is_not_primary_observed',
                     'secondary_confidentiality_value_not_automatically_imputed', 'partial_known_sums_are_not_component_totals',
                     'sums_across_catchments_are_invalid_due_to_overlap']:
            require(summary.get(flag) is True, 'Required evidence qualification missing: '+flag)
        require(summary.get('word_causal_types_assigned') is False and summary.get('historical_boundary_equivalence_established') is False,
                'Summary claims historical boundaries or causal types')
        points = pd.read_csv(root/'centre_demography.csv')
        require(list(points.columns) == expected['site_points']['columns']
                and table_hash(points, list(points.columns)) == expected['site_points'], 'All-row standalone site CSV differs')
        require(len(points) == n and points.centre_settlement_id.is_unique and points.star_id.is_unique
                and points.word_causal_type_established.eq(False).all()
                and points.historical_boundary_equivalence_established.eq(False).all(), 'Site CSV identities or scope are invalid')
        strict_classes = classes[classes.evidence_mode.eq('strict_direct_observed')].set_index('star_id')
        require(points.strict_joint_centre_rural_external_2002_2021.tolist() ==
                strict_classes.reindex(points.star_id).joint_centre_rural_external_2002_2021.tolist(),
                'Site CSV main classification differs from class Parquet')
        require(points.demography_rural_2002_category.value_counts().to_dict() == {
            manifest['legend'][key]: value for key, value in figures['counts'].items() if value},
            'All mapped category counts differ from figure values')
        for name, spec in manifest['standalone_assets'].items():
            require('/' not in safe_member(name), 'Standalone asset must be a filename')
            require(file_spec(root/name) == spec, 'Standalone size/SHA differs: '+name)
            member = 'centre_demography.csv' if name == 'centre_demography.csv' else 'readout/figures/'+producer_constant(source_commit, 'FIGURES')[name]
            require(checked[prefix+member] == spec, 'Standalone differs from packed copy: '+name)
            standalone[name] = spec
    require(set(standalone) == {'centre_demography.csv', 'preview.png', 'comparison.png'}, 'Exactly three standalone outputs are required')
    require(file_spec(manifest_path) == manifest_spec and file_spec(archive_path) == {
        key: manifest['archive'][key] for key in ['bytes', 'sha256']}, 'Release inputs changed during verification')
    proof = {'schema': 'sgrt.centre_demography_release_verification.v1',
             'verification_status': 'verified_supplied_local_files', 'public_URL_retrieval_verified': False,
             'publication_performed': False, 'source_commit': source_commit,
             'manifest_sha256': manifest_spec['sha256'], 'archive': manifest['archive'],
             'all_member_sizes_and_sha256_equal': True, 'safe_exact_unique_member_set': True,
             'streamed_members': len(checked), 'all_reproduction_bytes_match_producer': True,
             'reproduction_files': len(reproduction_names), 'all_three_Parquet_tables_allrow_hash_equal': True,
             'standalone_siteCSV_allrow_hash_equal': True, 'summary_and_figure_values_equal': True,
             'standalone_assets_equal_packed_copies': standalone,
             'accepted_values_not_labelled_observed': True, 'causal_and_historical_boundary_claims_absent': True,
             'centres': n, 'fixed_membership_pairs': len(membership), 'class_rows': len(classes),
             'component_rows': len(components), 'producer_control_sha256': git_blob_spec(source_commit, CONTROL)['sha256']}
    if catalog_output:
        catalog = create_catalog(manifest, checked, proof)
        catalog['scientific_scope'] = ('Demographic descriptions of fixed overlapping service catchments; strict primary and accepted-values panels are separate. '
            'No historical boundary equivalence, observed travel or causal Word-type claim. Companion catalogue; default population database unchanged.')
        target = Path(catalog_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n')
        proof['catalog_sha256'] = file_spec(target)['sha256']
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(proof, ensure_ascii=False, indent=2))
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--catalog-output', type=Path)
    args = parser.parse_args()
    verify(args.root, args.source_commit, args.output, args.catalog_output)
