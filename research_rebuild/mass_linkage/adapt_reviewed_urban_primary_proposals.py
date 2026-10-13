"""Project reviewed 2010 urban-settlement bindings into application proposal schema.

This is a schema adapter only. It trusts the pinned independent binding review
and the already staged primary rows; it does not reread source workbooks or
reparse the full census PDF, and it never applies replacements.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path('/workspace')
STAGE = ROOT / 'settlements-work/continuation_20261003/primary_urban_publication_binding_stage_v1'
REVIEW = ROOT / 'settlements-work/continuation_20261003/primary_urban_publication_binding_rule_review_v1'
SELECTED = ROOT / 'settlements-work/continuation_20261003/primary_population_application_v1/selected_observations.parquet'
PDF = ROOT / 'settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf'
APPROVED_MAP = REVIEW / 'approved_old_new_binding_mapping.csv'
EXPECTED_MAPPING_SHA = '9f2689ca54db557329eb33bcdc97acf23f39c641009b4432865321ce743ab1db'
PROPOSAL_INPUT = STAGE / 'urban_pgt_proposal_rows.csv'
DEFAULT_OUTPUT = ROOT / 'settlements-work/continuation_20261003/urban_primary_application_proposal_adapter_v3'
EXPECTED_OLD_QUALITY = 'secondary_confidentiality_protected_value_exact_scope_unverified'
PENDING = 'PENDING_SEPARATE_APPLICATION_REVIEW'
REQUIRED_VERDICT = 'APPROVE_BOUNDED_PRIMARY_PUBLICATION_REPLACEMENTS'
INDEPENDENT_REVIEW = REVIEW / 'review_verdict.json'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def extract_counts(raw_line: str) -> tuple[str, int, int, int]:
    """Extract label and literal total/men/women tokens from one pinned PDF line."""
    m = re.match(r'^\s*(.*?)\s+(\d+)\s+(\d+)\s+(\d+)(?:\s|$)', str(raw_line))
    if not m:
        raise ValueError(f'Primary line lacks three integral count tokens: {raw_line!r}')
    label, total, men, women = m.group(1).strip(), int(m.group(2)), int(m.group(3)), int(m.group(4))
    typed_label = re.sub(r'^(?:городское|сельское) население\s*[-–]\s*', '', label, flags=re.I).strip()
    if not typed_label.casefold().startswith('пгт '):
        raise ValueError(f'Primary row is not a directly typed urban locality: {raw_line!r}')
    if men + women != total:
        raise ValueError(f'Primary row sexes do not sum to total: {raw_line!r}')
    return label, total, men, women


def read_rows(path: Path, keep: set[str]) -> pd.DataFrame:
    """Read only needed columns using Python's CSV parser.

    The prior stage CSV contains large, multiline raw context fields. Pandas'
    CSV tokenizers segfault on that file in the pinned environment, so avoid
    loading irrelevant context and use the standard-library parser here.
    """
    with Path(path).open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        missing = keep - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'Missing columns in {path}: {sorted(missing)}')
        return pd.DataFrame([{k: row.get(k) for k in keep} for row in reader])


def build(output: Path = DEFAULT_OUTPUT) -> dict:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'Immutable output already exists: {output}')
    output.mkdir(parents=True, exist_ok=True)

    selected = pd.read_parquet(SELECTED)
    staged_columns = {
        'r2_source_record_id', 'reference_id', 'population', 'table5_population',
        'source_hash_actual', 'pypdf_raw_line', 'poppler_raw_line', 'primary_population_int',
        'primary_is_proper_physical_settlement_row', 'independent_pypdf_poppler_agree',
        'district_raw_table5', 'pdf_page', 'printed_page', 'pypdf_line_number',
        'primary_source_locator', 'population_scope', 'population_value_quality_original_tag',
    }
    approved_columns = {
        'r2_source_record_id', 'reference_id', 'population', 'table5_population',
        'source_hash_actual', 'source_row', 'pdf_page', 'printed_page', 'text_line_start',
        'population_value_quality_original_tag', 'population_scope',
    }
    staged = read_rows(PROPOSAL_INPUT, staged_columns)
    approved = read_rows(APPROVED_MAP, approved_columns)
    for column in ['population', 'table5_population']:
        approved[column] = pd.to_numeric(approved[column], errors='raise').astype('int64')
        staged[column] = pd.to_numeric(staged[column], errors='raise').astype('int64')
    staged['primary_population_int'] = pd.to_numeric(staged.primary_population_int, errors='raise').astype('int64')
    for column in ['primary_is_proper_physical_settlement_row', 'independent_pypdf_poppler_agree']:
        staged[column] = staged[column].astype(str).str.casefold().eq('true')
    actual_mapping_sha = sha(APPROVED_MAP)
    if actual_mapping_sha != EXPECTED_MAPPING_SHA:
        raise ValueError('Independent review mapping SHA differs from its approval receipt')
    if len(approved) != 780 or approved.r2_source_record_id.duplicated().any() or approved.reference_id.duplicated().any():
        raise ValueError('Expected a one-to-one 780-row approved old/new binding map')
    if len(staged) != 780 or staged.r2_source_record_id.duplicated().any():
        raise ValueError('Expected the exact 780-row staged urban proposal cohort')
    if set(staged.r2_source_record_id) != set(approved.r2_source_record_id):
        raise ValueError('Staged old-ID cohort differs from independently approved mapping')

    # Bind the proposal to exact independently reviewed old/new pairs and input
    # values, never merely to a name key.
    joined = approved.merge(staged, on='r2_source_record_id', how='left', validate='one_to_one', suffixes=('_review', '_stage'))
    if joined.reference_id_review.ne(joined.reference_id_stage).any():
        raise ValueError('Approved replacement IDs differ from staged Table 5 reference IDs')
    if joined.population_review.ne(joined.population_stage).any() or joined.table5_population_review.ne(joined.table5_population_stage).any():
        raise ValueError('Independent review old/new counts differ from staged rows')
    if joined.source_hash_actual_review.ne(joined.source_hash_actual_stage).any():
        raise ValueError('Independent mapping raw-source pins differ from staged source hashes')

    indexed = selected.set_index('source_record_id', drop=False)
    if not set(joined.r2_source_record_id).issubset(indexed.index):
        raise ValueError('Approved old source IDs are absent from current selected set')
    old = indexed.loc[joined.r2_source_record_id]
    if not old.population_value_quality.eq(EXPECTED_OLD_QUALITY).all():
        raise ValueError('Current selected old-value quality differs from the expected preserved quality label')
    if old.population.to_numpy().tolist() != joined.population_review.to_numpy().tolist():
        raise ValueError('Current selected old populations differ from reviewed mapping')

    pdf_sha = sha(PDF)
    source_csv_sha = sha(PROPOSAL_INPUT)
    rows = []
    for r in joined.itertuples(index=False):
        label, total, men, women = extract_counts(r.pypdf_raw_line)
        if total != int(r.table5_population_review) or total != int(r.primary_population_int):
            raise ValueError(f'Primary total mismatch for {r.r2_source_record_id}')
        if not bool(r.primary_is_proper_physical_settlement_row) or not bool(r.independent_pypdf_poppler_agree):
            raise ValueError(f'Primary physical-row or two-reader gate failed for {r.r2_source_record_id}')
        context = None if pd.isna(r.district_raw_table5) else str(r.district_raw_table5)
        context_flag = 'missing' if context is None else 'inherited_parsed_header_context_unverified'
        rows.append({
            'r2_source_record_id': r.r2_source_record_id,
            'replacement_source_record_id': r.reference_id_review,
            'old_population_r2': int(r.population_review),
            'old_population_quality': EXPECTED_OLD_QUALITY,
            'old_population_quality_original_tag': r.population_value_quality_original_tag_review,
            'proposed_primary_population': total,
            'proposed_primary_men': men,
            'proposed_primary_women': women,
            'table5_label_raw': label,
            'primary_raw_district': context,
            'primary_district_context_flag': context_flag,
            'primary_context_note': 'Table 5 header context only; no historical administrative claim.',
            'primary_raw_direct_typed_locality_row': True,
            'pdf_page': int(r.pdf_page_review),
            'printed_page': int(r.printed_page_review),
            'text_line_start_pypdf': int(r.pypdf_line_number),
            'text_line_end_pypdf': int(r.pypdf_line_number),
            'raw_pdf_line_independent_pypdf': r.pypdf_raw_line,
            'raw_pdf_line_independent_poppler': r.poppler_raw_line,
            'primary_source_sha256': pdf_sha,
            'primary_source_locator': r.primary_source_locator,
            'primary_source_row_label_sha256': hashlib.sha256(label.encode('utf-8')).hexdigest(),
            'population_scope': r.population_scope_review,
            'same_census_delta': total - int(r.population_review),
            'source_raw_population_hash': r.source_hash_actual_review,
            'independent_review_mapping_sha256': actual_mapping_sha,
            'proposal_input_sha256': source_csv_sha,
            'stage_status': 'proposed_pending_independent_review',
        })
    proposals = pd.DataFrame(rows)
    proposals = proposals.sort_values('r2_source_record_id').reset_index(drop=True)
    if proposals.replacement_source_record_id.duplicated().any():
        raise ValueError('Replacement source IDs are not unique')

    proposal_path = output / 'replacement_proposals.csv'
    proposals.to_csv(proposal_path, index=False)
    application_path = output / 'replacement_proposals.parquet'
    proposals.to_parquet(application_path, index=False)
    proposal_sha = sha(application_path)
    proposal_csv_sha = sha(proposal_path)
    selected_sha = sha(SELECTED)
    review_projection = {
        'verdict': REQUIRED_VERDICT,
        'decision_author': 'primary_agent_after_independent_validation',
        'independent_review_path': str(INDEPENDENT_REVIEW),
        'independent_review_sha256': sha(INDEPENDENT_REVIEW),
        'scope': 'Same-census 2010 urban settlement primary source binding only; no cross-year identity or district-history claim.',
        'selected_sha256': selected_sha,
        'proposals_sha256': proposal_sha,
        'proposals_csv_sha256': proposal_csv_sha,
        'primary_pdf_sha256': pdf_sha,
        'approved_replacement_source_record_ids': sorted(proposals.replacement_source_record_id.tolist()),
        'independent_review_mapping_path': str(APPROVED_MAP),
        'independent_review_mapping_sha256': actual_mapping_sha,
        'approved_pairs': len(approved),
        'binding_pairs_sha256': hashlib.sha256('\n'.join(
            f'{r.r2_source_record_id}\t{r.replacement_source_record_id}'
            for r in proposals.sort_values('r2_source_record_id').itertuples(index=False)
        ).encode('utf-8')).hexdigest(),
        'review_source_proposal_csv_sha256': source_csv_sha,
        'notes': [
            'The 780 old/new pairs match the independent rule review mapping exactly.',
            'The row-level proposals remain proposed_pending_independent_review; this projection carries only the prior rule review and exact input pins.',
            'Current protected old values use the already-updated exact-scope-unverified label; original quality tag is retained per proposal.',
            'Table 5 district field records missing versus inherited parsed header context only; it is not a historical administrative assertion.'
        ]
    }
    (output / 'review_projection.json').write_text(json.dumps(review_projection, ensure_ascii=False, indent=2) + '\n')
    summary = {
        'status': 'PROPOSAL_SCHEMA_ADAPTER_ONLY_NOT_APPLIED',
        'rows': len(proposals),
        'old_population': int(proposals.old_population_r2.sum()),
        'primary_population': int(proposals.proposed_primary_population.sum()),
        'gross_same_census_delta': int(proposals.same_census_delta.sum()),
        'missing_primary_district_context': int(proposals.primary_district_context_flag.eq('missing').sum()),
        'inherited_parsed_primary_district_context_unverified': int(proposals.primary_district_context_flag.eq('inherited_parsed_header_context_unverified').sum()),
        'all_sexes_sum_to_total': bool((proposals.proposed_primary_men + proposals.proposed_primary_women == proposals.proposed_primary_population).all()),
        'all_stage_status_pending': bool(proposals.stage_status.eq('proposed_pending_independent_review').all()),
        'review_mapping_sha256': actual_mapping_sha,
        'proposals_sha256': proposal_sha,
        'proposals_csv_sha256': proposal_csv_sha,
        'review_projection_sha256': sha(output / 'review_projection.json'),
        'selected_sha256': selected_sha,
        'primary_pdf_sha256': pdf_sha,
        'source_proposal_csv_sha256': source_csv_sha,
        'adapter_module_sha256': sha(Path(__file__)),
        'inputs': {str(p): sha(p) for p in [SELECTED, PROPOSAL_INPUT, APPROVED_MAP, PDF]},
    }
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    print(json.dumps(build(parser.parse_args().output), ensure_ascii=False, indent=2))
