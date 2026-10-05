#!/usr/bin/env python3
"""Stage novel dated Wikidata P1082 assertions as unaccepted annual candidates.

This preserves statement-level provenance without joining claims to census
observations, coordinates, or an accepted current place identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

CLAIMS = Path('/workspace/settlements-work/continuation_20261004/R4/fetched_full_entity_secondary_history_20261004/fetched_p1082_claim_inventory.parquet')
BINDINGS = Path('/workspace/settlements-work/continuation_20261004/R4/fetched_full_entity_secondary_history_20261004/new_claim_current_qid_binding_candidates.parquet')
OVERLAY = Path('/workspace/settlements-work/continuation_20261004/root/long_graph16_with_364032_secondary_display/secondary_history_overlay.parquet')
SUMMARY = Path('/workspace/settlements-work/continuation_20261004/R4/fetched_full_entity_secondary_history_20261004/summary.json')
EXPECTED = {
    'claims': 'f975b799dc2f9ca94c401dfff632a2d59b27adde74f2da24bcc5dcf6877df6f5',
    'bindings': '45a65af213b5acc018d139be0d23b5cdceefe9dc65f6dcf3722285fd2d9eb757',
    'overlay': '87dace49eef02b28df742e09fa14c7b6d044d4f4784d0313694723bee7adee89',
    'summary': '8b3e876efae6ef517f16ef497794129d4af795ce08bb5b000afa0bf038ecf7b3',
}
CENSUS_YEARS = {2002, 2010, 2021}
NOVEL_STATUS = 'new_subject_GUID_candidate_not_in_frozen_history_overlay'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def run(out: Path) -> dict:
    if out.exists():
        raise FileExistsError(f'Output exists; use a new versioned directory: {out}')
    for key, path in {'claims': CLAIMS, 'bindings': BINDINGS, 'overlay': OVERLAY, 'summary': SUMMARY}.items():
        actual = sha256(path)
        if actual != EXPECTED[key]:
            raise ValueError(f'{key} input hash mismatch: {actual}')
    claims = pd.read_parquet(CLAIMS)
    novel = claims.loc[
        claims.claim_snapshot_status.eq(NOVEL_STATUS)
        & pd.to_numeric(claims.date_precision, errors='coerce').eq(9)
        & pd.to_numeric(claims.observed_year, errors='coerce').notna()
    ].copy()
    novel['observed_year'] = pd.to_numeric(novel.observed_year, errors='raise').astype(int)
    novel = novel.loc[~novel.observed_year.isin(CENSUS_YEARS)].copy()
    overlay_statement_ids = set(pd.read_parquet(OVERLAY, columns=['wikidata_statement_id'])
                                .wikidata_statement_id.dropna().astype(str))
    if set(novel.statement_guid_normalized_for_dedup.astype(str)) & overlay_statement_ids:
        raise ValueError('claim GUID already exists in frozen overlay')
    novel['population_value_numeric'] = pd.to_numeric(novel.population_value_numeric, errors='coerce')
    if len(novel) != 49 or novel.p1082_statement_guid_raw.duplicated().any():
        raise ValueError(f'Expected 49 unique novel year-precision noncensus claims, got {len(novel)}')
    if not novel.quantity_status.eq('finite_nonnegative_quantity').all():
        raise ValueError('claim quantity status is not finite nonnegative for every row')
    if novel.population_value_numeric.isna().any() or (novel.population_value_numeric < 0).any():
        raise ValueError('invalid population amount')
    if novel.groupby(['wikidata_qid', 'observed_year']).population_value_numeric.nunique().gt(1).any():
        raise ValueError('conflicting values exist within QID/year')
    if novel.duplicated(['wikidata_qid', 'observed_year']).any():
        raise ValueError('multiple claims exist for a QID/year; resolve instead of silently summing')
    if not novel.current_binding_status.eq('candidate_pending_independent_current_binding_review').all():
        raise ValueError('unexpected accepted/held current QID binding status')
    if not novel.entity_batch_hash_verified.astype(str).str.lower().eq('true').all():
        raise ValueError('raw entity batch hash verification failed')
    raw_batches = novel[['entity_batch_file_verified_path', 'entity_batch_sha256']].drop_duplicates()
    for path, expected in raw_batches.itertuples(index=False, name=None):
        raw_path = Path(str(path))
        if not raw_path.exists() or sha256(raw_path) != str(expected):
            raise ValueError(f'raw entity batch is missing or hash-mismatched: {raw_path}')

    bindings = pd.read_parquet(BINDINGS)
    qids = set(novel.wikidata_qid.astype(str))
    candidate = bindings.loc[bindings.wikidata_qid.astype(str).isin(qids)].copy()
    if set(candidate.wikidata_qid.astype(str)) != qids or candidate.wikidata_qid.astype(str).duplicated().any():
        raise ValueError('candidate current binding is absent or nonunique for a claim QID')
    required_true = [
        'wikidata_truthy_exact_p764_match', 'current_source_name_exact',
        'current_source_type_exact', 'current_source_region_exact',
        'source_code_unique_qid', 'qid_unique_current_source_code',
        'native_competition_clear', 'physical_p31_lineage', 'no_contradictory_admin_region',
    ]
    for col in required_true:
        if not candidate[col].astype(str).str.lower().eq('true').all():
            raise ValueError(f'candidate binding failed required screen: {col}')
    if not candidate.binding_status.eq('scoped_secondary_history_binding_candidate_pending_independent_review').all():
        raise ValueError('binding status differs from pending review')
    binding_cols = [
        'wikidata_qid', 'source_record_id', 'settlement_name', 'settlement_type',
        'region_raw', 'source_oktmo_exact_digits', 'population', 'binding_status',
        'truthy_p625_point_count', 'accepted_point_use_count',
        'historical_scope_status', 'historical_identity_status', 'historical_coordinate_status',
    ]
    binding_map = candidate.set_index('wikidata_qid')[binding_cols[1:]].to_dict('index')

    # Verify raw P1082 statement payload and expose references without treating
    # their presence as independent verification of the cited publication.
    refs = []
    for raw in novel.raw_statement_json.astype(str):
        statement = json.loads(raw)
        if statement.get('mainsnak', {}).get('property') != 'P1082':
            raise ValueError('raw statement is not P1082')
        qualifiers = statement.get('qualifiers', {}).get('P585', [])
        if len(qualifiers) != 1 or qualifiers[0].get('datavalue', {}).get('value', {}).get('precision') != 9:
            raise ValueError('raw P585 is not one exact year-precision qualifier')
        refs.append(statement.get('references', []))

    output_rows = []
    for i, (_, claim) in enumerate(novel.iterrows()):
        qid = str(claim.wikidata_qid)
        bind = binding_map[qid]
        refs_for_claim = refs[i]
        row = {
            'wikidata_qid': qid,
            'population_value': float(claim.population_value_numeric),
            'observed_year': int(claim.observed_year),
            'statement_guid': str(claim.p1082_statement_guid_raw),
            'rank': str(claim.rank_raw),
            'date_precision': int(float(claim.date_precision)),
            'raw_date_literal': str(claim.date_value_literal),
            'raw_population_value': str(claim.population_value_raw),
            'quantity_unit_raw': str(claim.population_quantity_unit_raw),
            'reference_count': len(refs_for_claim),
            'references_json': json.dumps(refs_for_claim, ensure_ascii=False, separators=(',', ':')),
            'raw_statement_json': str(claim.raw_statement_json),
            'retrieval_timestamp': str(claim.entity_retrieved_at_utc),
            'raw_entity_batch_path': str(claim.entity_batch_file_verified_path),
            'raw_entity_batch_sha256': str(claim.entity_batch_sha256),
            'current_source_record_id_candidate': str(bind['source_record_id']),
            'current_source_native_OKTMO_candidate': str(bind['source_oktmo_exact_digits']),
            'current_name_candidate': str(bind['settlement_name']),
            'current_type_candidate': str(bind['settlement_type']),
            'current_region_candidate': str(bind['region_raw']),
            'current_binding_status': str(bind['binding_status']),
            'accepted_point_use_count': int(float(bind['accepted_point_use_count'])),
            'historical_scope_status': str(bind['historical_scope_status']),
            'historical_identity_status': str(bind['historical_identity_status']),
            'historical_coordinate_status': str(bind['historical_coordinate_status']),
            'observation_status': 'secondary_Wikidata_assertion_candidate_pending_current_QID_binding_review',
            'population_value_accepted': False,
            'coordinate_attached': False,
            'census_identity_edge_asserted': False,
            'population_scope_comparability': 'unknown',
        }
        output_rows.append(row)
    out.mkdir(parents=True)
    output = pd.DataFrame(output_rows).sort_values(['wikidata_qid', 'observed_year'])
    output.to_json(out / 'annual_claim_candidates.jsonl', orient='records', lines=True, force_ascii=False)

    by_year = output.groupby('observed_year').population_value.sum().astype(int).to_dict()
    reference_counts = [len(x) for x in refs]
    qid_source_map = output[['wikidata_qid', 'current_source_record_id_candidate']].drop_duplicates()
    if qid_source_map.wikidata_qid.duplicated().any() or qid_source_map.current_source_record_id_candidate.duplicated().any():
        raise ValueError('current candidate mapping is not one-to-one across claim QIDs')
    residual_qids = {'Q24484253', 'Q28525985'}
    residual = output.loc[output.wikidata_qid.isin(residual_qids)]
    result = {
        'status': '49_novel_non_census_dated_secondary_claim_candidates_staged_not_accepted',
        'counts': {'claims': len(output), 'distinct_qids': int(output.wikidata_qid.nunique()),
                   'distinct_years': int(output.observed_year.nunique()),
                   'qids_with_pending_binding': int(output.wikidata_qid.nunique())},
        'population_sum_by_claim_year': by_year,
        'sum_unique_qid_year_values': int(output.population_value.sum()),
        'reference_coverage': {'claims_with_any_reference': int(sum(x > 0 for x in reference_counts)),
                               'claims_without_reference': int(sum(x == 0 for x in reference_counts))},
            'claim_quality': {'all_year_precision': bool(output.date_precision.eq(9).all()),
                          'all_nonnegative_finite': bool(output.population_value.map(math.isfinite).all() and output.population_value.ge(0).all()),
                          'same_qid_year_value_conflicts': 0},
        'current_binding_candidate_checks': {'all_exact_P764_physical_name_type_region_unique_code_flags_pass': True,
                                             'binding_status': 'candidate pending independent current-QID review',
                                             'accepted_binding_count': 0,
                                             'all_candidate_points_accepted': False},
        'raw_entity_batches': {'distinct_batches_verified': int(len(raw_batches)),
                               'all_raw_entity_batch_hashes_verified': True},
        'current_residual_overlap': {
            'claims': int(len(residual)), 'distinct_qids': int(residual.wikidata_qid.nunique()),
            'sum_unique_qid_year_values': int(residual.population_value.sum()),
            'accepted_point_uses': 0,
            'rows': [{'qid': q, 'claims': int(len(g)), 'population_sum': int(g.population_value.sum()),
                      'years': sorted(g.observed_year.astype(int).tolist()),
                      'candidate_source_record_id': str(g.current_source_record_id_candidate.iloc[0]),
                      'candidate_name': str(g.current_name_candidate.iloc[0])}
                     for q, g in residual.groupby('wikidata_qid')],
        },
        'limitations': [
            'These are secondary Wikidata statements, not primary-source census observations.',
            'The 49 claims are novel by statement GUID versus the frozen overlay; QID/year values do not conflict within this candidate set.',
            'Each associated present-day selected row/QID binding remains pending independent review despite passing candidate flags.',
            'No coordinates, temporal identity edges, source scope, or population-boundary comparability are asserted.',
            'The total is a sum of dated QID claims, not unique national population and not additive across years.',
        ],
        'inputs': {k: {'path': str(p), 'sha256': sha256(p)} for k, p in {
            'claim_inventory': CLAIMS, 'current_binding_candidates': BINDINGS,
            'frozen_secondary_overlay': OVERLAY, 'source_summary': SUMMARY,
        }.items()},
        'outputs': {'annual_claim_candidates.jsonl': {'path': str(out / 'annual_claim_candidates.jsonl'),
                    'sha256': sha256(out / 'annual_claim_candidates.jsonl'),
                    'bytes': (out / 'annual_claim_candidates.jsonl').stat().st_size}},
    }
    (out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-dir', type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(run(args.output_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
