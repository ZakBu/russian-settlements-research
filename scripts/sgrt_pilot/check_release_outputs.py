#!/usr/bin/env python3
"""Fail publication if reproduced numbers/provenance contradict the pilot text.

Snapshot-specific regression checks, not parameter fitting, stakeholder approval,
or validation of real patient trips. This script creates no approval artifact.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

OSM_CASES = ('medical_presence', 'medical_count', 'school_presence', 'school_count')
CASES = (*OSM_CASES, 'official_udmurt_selected_plan',
         *(f'reference_all_regions/{case}' for case in OSM_CASES))
SOURCE_INPUTS = {
    'legacy_axis': 'research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet',
    'medical2021': 'research/sgrt_word_completion_20261021/medical/history_20210101/osm_medical_inventory.parquet',
    'education2021': 'research/sgrt_word_completion_20261021/education/education_objects_2021.parquet',
    'udmurt2025': 'research/sgrt_word_completion_20261021/medical/udmurt_official_2025/physical_fap_inventory.parquet',
    'lo2024': 'research/sgrt_word_completion_20261021/validation/medical_territories_2024_all_rows.parquet',
}
LO_SHA256 = 'efad8790b5339bdc4b1dfa94d60f590ff8bebe3a9c2828bbad725440d0ebb61b'
UDM_SHA256 = '34322c8ef538efa79617af0f80ecc330c99d7f60539216478ef4e6f64dcd070c'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    def invalid(value):
        raise ValueError(f'Nonstandard JSON constant {value} in {path}')
    return json.loads(Path(path).read_text(), parse_constant=invalid)


def check_source_metadata(preparation, transcription, independent, catalog):
    require(preparation['population_foundation_changed'] is False, 'Population foundation was changed')
    require(preparation['spatial_reference_year'] == 2021, 'Spatial year changed')
    require(preparation['primary_2021_with_accepted_point'] == 153800, 'Accepted ordinary spatial grain changed')
    require(sum(preparation['pilot_rows_by_region'].values()) == 13968, 'Pilot spatial denominator changed')
    require(preparation['official_udmurt_spatial_settlements'] == 478, 'Selected FAP denominator changed')
    records = preparation['inputs']
    require(len(records) == len(SOURCE_INPUTS), 'Missing/duplicate source-input provenance')
    require({r['label'] for r in records} == set(SOURCE_INPUTS), 'Unexpected source-input labels')
    indexed = {r['path']: r for r in catalog['files']}
    for record in records:
        label = record['label']
        require(record['path'] == SOURCE_INPUTS[label], f'Wrong source path for {label}')
        source = indexed[record['path']]
        expected = catalog['objects'][source['blob']]
        require(record['sha256'] == expected['sha256'], f'Source digest drift: {label}')
        require(record['bytes'] == expected['bytes'], f'Source size drift: {label}')
    require(transcription['fresh_download_sha256'] == LO_SHA256, 'LO workbook bytes changed')
    require(transcription['document_date'] == '2023-11-29', 'LO date changed')
    require(transcription['extracted_rows_checked'] == 3180, 'LO transcription denominator changed')
    require(transcription['transcription_differences'] == 0, 'LO source transcription mismatch')
    for field in ['exact_origin_text_matches', 'exact_provider_literal_matches', 'exact_published_population_matches']:
        require(transcription[field] == 3180, f'Incomplete source-first check: {field}')
    require(transcription['normative_attachments_not_observed_patient_trips'] is True, 'Normative records relabelled trips')
    official = preparation['official_udmurt_fresh_workbook_check']
    require(official['raw_sha256'] == UDM_SHA256, 'UDM workbook bytes changed')
    require(official['rows_reread'] == 564 and official['rows_equal_preserved_extraction'] is True,
            'UDM raw source was not reproduced')
    require(independent['quarantined_source_rows'] == 6, 'Source-context quarantine changed')
    require(independent['resolved_rows_after_context_quarantine'] == 306, 'Resolved-row denominator changed')
    require(independent['medical_attachment_is_observed_trip'] is False, 'Normative records relabelled trips')


def check_reference_metrics(metrics, comparison):
    require(comparison['unique_external_pairs'] == 216, 'External-pair denominator changed')
    require(comparison['unique_external_origins'] == 216, 'External-origin denominator changed')
    require(comparison['parameters_fitted_or_selected'] is False, 'Parameters selected on evaluation relations')
    reference = metrics.loc[metrics.decay_family.eq('exponential') & metrics.half_life_minutes.eq(30) & metrics.kernel_floor.eq(.05)]
    expected = {('medical_presence', 'functional'): 40, ('medical_presence', 'nearest'): 40,
                ('medical_presence', 'population'): 1, ('medical_count', 'functional'): 9,
                ('medical_count', 'nearest'): 40, ('medical_count', 'population'): 1}
    require(len(reference) == len(expected), 'Missing/duplicated reference comparison row')
    require(not reference.duplicated(['run', 'model']).any(), 'Duplicated reference comparison key')
    require(set(zip(reference.run, reference.model)) == set(expected), 'Reference model/source keys changed')
    for row in reference.itertuples():
        require(row.resolved_external_origins == 216 and row.origins_in_model_frame == 216,
                'Reference denominator is not the same 216 resolved origins')
        require(row.origins_exactly_matching_any_normative_provider == expected[row.run, row.model],
                f'Reference agreement drift: {row.run}/{row.model}')
        require(row.origins_with_any_normative_provider_in_source_supply == 53, 'Source provider coverage denominator changed')
        numerator = expected[row.run, row.model]
        require(math.isclose(row.agreement_all_resolved_origins, numerator / 216, rel_tol=0, abs_tol=1e-12), 'Reference percentage does not match numerator/denominator')
        require(math.isclose(row.source_provider_coverage_all_resolved_origins, 53 / 216, rel_tol=0, abs_tol=1e-12), 'Coverage percentage uses wrong denominator')
        require(row.evidence == 'normative_attachment_not_observed_trip', 'Wrong validation evidence kind')
        require(not row.parameters_fitted_to_these_relations and not row.preregistered_blind_holdout,
                'Unsupported fitting/holdout claim')


def check_outputs(root, catalog_path):
    root = Path(root)
    preparation = load_json(root/'data/preparation_summary.json')
    source_audit = load_json(root/'validation/medical_source_audit.json')
    independent = load_json(root/'independent/independent_diagnostics.json')
    check_source_metadata(preparation, source_audit, independent, load_json(catalog_path))
    comparison = load_json(root/'validation/medical_comparison_summary.json')
    check_reference_metrics(pd.read_csv(root/'validation/medical_attachment_model_comparison.csv'), comparison)
    manifest = load_json(root/'model/run_manifest.json')
    require(manifest['status'] == 'completed', 'Model recipe did not complete')
    require(len(manifest['completed_cases']) == len(CASES) and set(manifest['completed_cases']) == set(CASES),
            'Nine distinct model cases were not completed')
    type_paths = {p.parent.relative_to(root/'types').as_posix(): p
                  for p in (root/'types').rglob('candidate_zone_types.parquet')}
    require(set(type_paths) == set(CASES), 'Nine model cases do not have nine type tables')
    total_rows = 0
    for case in CASES:
        outpath = root/'model'/case/'scenario_outcomes.parquet'
        expected_rows = 35298 if case == 'official_udmurt_selected_plan' else 41904 if case.startswith('reference_all_regions/') else 264330
        rows = pq.ParquetFile(outpath).metadata.num_rows
        require(rows == expected_rows, f'Model-row denominator changed: {case}')
        total_rows += rows
        outcomes = pd.read_parquet(outpath, columns=['source_record_id', 'established_external_link', 'local_supply_status',
            'missing_local_supply_could_change_choice', 'common_transport_ceiling_minutes', 'observation_year'])
        require(not outcomes.established_external_link.any(), f'Model links relabelled observed: {case}')
        require(outcomes.loc[outcomes.local_supply_status.eq('unknown'), 'missing_local_supply_could_change_choice'].all(),
                f'Unknown supply hidden: {case}')
        require(outcomes.common_transport_ceiling_minutes.eq(180).all(), f'Unequal routing ceiling: {case}')
        if case == 'official_udmurt_selected_plan':
            require(outcomes.observation_year.isna().all(), 'Planning list incorrectly dated as operating observation')
            years = pd.read_parquet(outpath, columns=['document_catalogue_year', 'planning_target_year'])
            require(years.document_catalogue_year.eq(2025).all() and years.planning_target_year.eq(2026).all(),
                    'Official planning/publication years not preserved')
        else:
            require(outcomes.observation_year.eq(2021).all(), f'OSM source year changed: {case}')
        types = pd.read_parquet(type_paths[case], columns=['type_code', 'causal_word_type', 'functional_level'])
        require(len(types) > 0 and types.type_code.notna().all() and types.type_code.astype(str).str.len().gt(0).all(),
                f'Untyped candidate unit: {case}')
        require(types.causal_word_type.eq('not_inferred_without_specialization_evidence').all(), f'Unsupported causal typing: {case}')
        require(types.functional_level.eq('single_function_service_order_not_sgrt_hierarchy').all(), f'Unsupported hierarchy: {case}')
        require(any((root/'maps'/case).glob('*.png')), f'No geographic figures for {case}')
    require(total_rows == 1260234, 'Total computed-row count changed')
    anchors = pd.read_parquet(root/'data/external_context_anchors.parquet')
    require(set(anchors.center_id) == {'ctx:RU-FED-MOW', 'ctx:RU-FED-SPB'}, 'External context keys changed')
    require(anchors.source_record_id.isna().all() and anchors.root.isna().all() and not anchors.working_credit_present.any(),
            'External contexts given fabricated census IDs or population credit')
    atlas = root/'pilot_atlas.pdf'
    require(atlas.exists() and atlas.open('rb').read(5) == b'%PDF-', 'Atlas is missing/not a PDF')
    print('Reproduced source-first comparisons: 216 origins; reference matches 40/9/1; nine typed cases; no observed-trip/hierarchy claim.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--catalog', type=Path, default=Path(__file__).resolve().parents[2]/'data/catalog.json')
    a = p.parse_args()
    check_outputs(a.root, a.catalog)


if __name__ == '__main__':
    main()
