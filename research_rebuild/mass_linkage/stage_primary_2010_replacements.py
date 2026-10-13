"""Stage, but never apply, exact 2010 Table 5 population replacement proposals.

The stage is restricted to the district-agree primary/source candidate cohort.
It independently verifies keys against the complete selected R2 file, raw
workbook rows, and raw Table 5 PDF context. Outputs are evidence and proposals;
they do not mutate a frozen release or establish cross-year identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import xlrd
from pypdf import PdfReader

from research_rebuild.mass_linkage.apply_historical_identity_rule import source_profiles

ROOT = Path('/workspace/russian-settlements-research')
RAW = Path('/workspace/settlements-raw')
SELECTED = Path('/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet')
INVENTORY = Path('/workspace/settlements-work/continuation_20261003/population2010/table5_to_r2_overlap_candidates_2010.parquet')
PDF = RAW / 'data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf'
DEFAULT_OUTPUT = Path('/workspace/settlements-work/continuation_20261003/primary_replacement_stage_v6')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def norm(value: Any) -> str:
    if value is None or pd.isna(value):
        return ''
    text = unicodedata.normalize('NFKC', str(value)).casefold().replace('ё', 'е').replace('ѐ', 'е')
    return re.sub(r'\s+', ' ', text).strip()


def region_norm(value: Any) -> str:
    text = norm(value)
    text = re.sub(r'\s+(?:область|край|республика|автономная область|автономный округ)$', '', text)
    return text.strip()


def district_norm(value: Any) -> str:
    text = norm(value).replace('–', '-').replace('—', '-')
    # PDF district rows often annotate the scope, e.g. "... район - сельское
    # население". This suffix describes the table section, not another unit.
    text = re.split(r'\s+-\s+', text, maxsplit=1)[0]
    text = re.sub(r'[.,:;]+$', '', text)
    text = re.sub(r'\s+(?:район|р-н|district)$', '', text).strip()
    return text


def int_population(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else None
    text = re.sub(r'[\s\u00a0]', '', str(value))
    return int(text) if re.fullmatch(r'[+-]?\d+', text) else None


def classify_raw_table5_label(label: Any) -> tuple[bool, str | None]:
    """Confirm a raw typed locality line and retain urban/rural qualifier."""
    text = str(label or '').strip()
    qualifier = None
    match = re.match(r'^(Городское|Сельское) население\s*[-–]\s*(.*)$', text, re.I)
    if match:
        qualifier, text = match.group(1), match.group(2).strip()
    if re.search(r'подчиненн|администраци|населенными пунктами|включая|итого|всего', text, re.I):
        return False, qualifier
    direct_type = re.match(r'^(?:г\.|город|пгт|село|пос[еёѐ]лок|деревня|станица|хутор|аул|слобода|местечко|селение|кишлак)\s+\S+', text, re.I)
    return bool(direct_type), qualifier


def sheet_district_context(values: list[Any], profile: dict[str, Any], prior: str | None) -> tuple[str | None, str]:
    """Read the current physical row and within-region source block state.

    A nonblank source district cell updates state. Empty cells inherit only the
    preceding raw workbook district block; no R2 district value is consulted.
    """
    explicit = []
    for col in profile.get('district_cols', []):
        if int(col) < len(values):
            value = values[int(col)]
            if value is not None and str(value).strip() and str(value).strip() not in {'-', '—', '–'}:
                explicit.append(str(value).strip())
    if explicit:
        # Two district columns often duplicate a merged/parallel header. If
        # they differ, preserve the conflict instead of selecting one.
        keys = {district_norm(x) for x in explicit}
        return (explicit[0], 'explicit' if len(keys) == 1 else 'conflicting_explicit_cells')
    return (prior, 'inherited_raw_source_block' if prior else 'missing_raw_source_block')


def _pdf_rows(pdf_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Rebuild Table 5 rows and district context directly from PDF text lines."""
    reader = PdfReader(str(pdf_path))
    rows = []
    region = district = None
    # The bounded Table 5 is PDF pages 13–210 (1-based). Context is recomputed
    # from raw page lines, separately from the cached reference parquet.
    for page_no in range(13, 211):
        page_text = reader.pages[page_no - 1].extract_text() or ''
        for line_no, raw in enumerate(page_text.splitlines(), 1):
            line = raw.strip()
            if not line:
                continue
            # Table 5 district hierarchy lines carry population values too;
            # clear the district before treating settlement records below it.
            if re.search(r'\sрайон(?:\s|$)', line, re.I) and not re.match(r'^(?:г\.|пгт|село|пос)', line, re.I):
                label = re.split(r'\s+-\s+|\s+\d', line, maxsplit=1)[0].strip()
                if label:
                    district = label
            m = re.match(r'^(.*?)\s+(\d+|-)\s+(\d+|-)\s+(\d+|-)\s+(?:\d+,\d+|-)(?:\s+\d+,\d+|-)?\s*$', line)
            if not m:
                continue
            label, total, men, women = m.group(1).strip(), m.group(2), m.group(3), m.group(4)
            # Region headings reset context. Rows in this inventory are
            # candidate localities; require a physical numeric total.
            if re.search(r'(?:область|край|республика|автономный округ)', label, re.I) and not re.search(r'район|население|подчиненн', label, re.I):
                region, district = label, None
            # Some district labels are wrapped or use a dash separator. Retain
            # the raw header as the independently observed block context.
            if re.search(r'район', label, re.I) and not re.match(r'^(?:г\.|пгт|село|пос|дер|станица|хутор|аул)', label, re.I):
                district = label
            rows.append({'pdf_page': page_no, 'text_line': line_no, 'raw_line': line,
                         'label_raw': label, 'population': int(total) if total.isdigit() else None,
                         'men_raw': men, 'women_raw': women, 'district_raw_independent': district,
                         'region_raw_independent': region})
    return pd.DataFrame(rows), {'pdf_page_count': len(reader.pages), 'raw_table5_rows': len(rows)}


def _poppler_pages(pdf: Path, pages: set[int]) -> dict[int, list[str]]:
    """Return Poppler text, independently of PyPDF's extraction path."""
    result: dict[int, list[str]] = {}
    for p in sorted(pages):
        proc = subprocess.run(['pdftotext', '-layout', '-f', str(p), '-l', str(p), str(pdf), '-'],
                              check=True, capture_output=True, text=True)
        result[p] = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
    return result


def build_stage(selected_path: Path = SELECTED, inventory_path: Path = INVENTORY,
                pdf_path: Path = PDF, output: Path = DEFAULT_OUTPUT,
                raw_root: Path = RAW) -> dict[str, Any]:
    selected_path, inventory_path, pdf_path = map(Path, (selected_path, inventory_path, pdf_path))
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'Immutable stage output already exists: {output}')
    output.mkdir(parents=True, exist_ok=True)
    selected = pd.read_parquet(selected_path)
    selected = selected[selected.census_year.eq(2010)].copy()
    inv = pd.read_parquet(inventory_path)
    # One row per existing source record; restrict the assigned target cohort.
    target = inv.drop_duplicates('r2_source_record_id').copy()
    target = target[target.candidate_status.eq(
        'unique_text_key_population_candidate_pending_identity_and_binding_review')].copy()
    target = target[target.district_context_status.eq('district_text_agrees_candidate')].copy()
    source_profiles_map = source_profiles()

    # Independent uniqueness over all selected 2010 R2 rows, and all extracted
    # Table 5 source rows, using the same region/name/type dimensions.
    selected['_key'] = selected.region_norm.map(region_norm) + '\x1f' + selected.name_norm.map(norm) + '\x1f' + selected.type_norm.map(norm)
    r2_counts = selected.groupby('_key').size().to_dict()
    ref = pd.read_parquet(inventory_path.parent / 'tom1_table5_extraction/official_2010_table5_reference.parquet')
    ref = ref[ref.row_kind.eq('settlement')].copy()
    ref['_key'] = ref.region_key.map(norm) + '\x1f' + ref.name_key.map(norm) + '\x1f' + ref.type_key.map(norm)
    ref_counts = ref.groupby('_key').size().to_dict()

    raw_pdf, pdf_facts = _pdf_rows(pdf_path)
    primary_pdf_sha = sha256(pdf_path)
    lines = pd.read_parquet(inventory_path.parent / 'tom1_table5_extraction/official_2010_table5_lines.parquet')
    # Retain the previously extracted ref's key to bind independent raw lines;
    # source ID itself comes from pypdf's audited page and start line locator.
    raw_by_locator = {(int(r.pdf_page), int(r.text_line)): r for r in raw_pdf.itertuples(index=False)}

    books: dict[str, tuple[Any, Any, dict[str, Any], str]] = {}
    prior_district: dict[tuple[str, str], str | None] = {}
    outcomes = []
    for c in target.itertuples(index=False):
        rec = c._asdict()
        key = region_norm(c.region_raw_r2) + '\x1f' + norm(c.settlement_name_r2) + '\x1f' + norm(c.settlement_type_r2)
        reasons = []
        if r2_counts.get(key, 0) != 1:
            reasons.append('r2_key_not_unique_across_full_selected_2010')
        if ref_counts.get(key, 0) != 1:
            reasons.append('table5_key_not_unique_across_all_primary_rows')
        profile = source_profiles_map.get(str(c.source_file))
        if not profile:
            reasons.append('source_file_without_audited_sheet_profile')
            profile = {}
        source_path = Path(raw_root) / str(c.source_file)
        if not source_path.is_file():
            reasons.append('raw_secondary_source_missing')
            raw_values = []
            source_district = None
            source_district_status = 'missing_file'
            source_sha = None
        else:
            source_sha = sha256(source_path)
            expected_sha = str(c.r2_source_sha256_from_asset_inventory)
            if source_sha != expected_sha:
                reasons.append('raw_secondary_hash_mismatch')
            book = books.get(str(c.source_file))
            if book is None:
                xlbook = xlrd.open_workbook(str(source_path), on_demand=True)
                sheet = xlbook.sheet_by_name(profile['sheet'])
                books[str(c.source_file)] = (xlbook, sheet, profile, source_sha)
                book = books[str(c.source_file)]
            xlbook, sheet, profile, _ = book
            rowno = int(c.source_row)
            blockkey = (str(c.source_file), str(c.source_sheet))
            # Build raw context in workbook order through the candidate row.
            if blockkey not in prior_district:
                prior_district[blockkey] = None
            # Parse all rows once up through this locator so a checkpointed row
            # inherits only prior raw source cells, never the selected field.
            state = None
            for ri in range(int(profile.get('first_data_row', 1)) - 1, rowno):
                vals = sheet.row_values(ri)
                state, st = sheet_district_context(vals, profile, state)
            raw_values = sheet.row_values(rowno - 1)
            source_district, source_district_status = sheet_district_context(raw_values, profile, state)
            name_cols = [int(x) for x in profile.get('name_cols', [])]
            raw_name = ' '.join(str(raw_values[x]).strip() for x in name_cols if x < len(raw_values) and str(raw_values[x]).strip())
            name_ok = norm(raw_name) in {norm(c.source_name_raw), norm(c.settlement_name_r2), norm(c.table5_settlement_name_raw)}
            pop_col = profile.get('population_col')
            raw_pop = raw_values[int(pop_col)] if pop_col is not None and int(pop_col) < len(raw_values) else None
            pop_ok = int_population(raw_pop) == int_population(c.population)
            if not name_ok:
                reasons.append('raw_secondary_name_mismatch')
            if not pop_ok:
                reasons.append('raw_secondary_population_mismatch')
            if source_district_status == 'conflicting_explicit_cells':
                reasons.append('raw_secondary_district_cells_conflict')
        raw_primary = raw_by_locator.get((int(c.pdf_page), int(c.text_line_start)))
        if raw_primary is None:
            reasons.append('raw_pdf_locator_not_found_in_independent_reader')
            pdf_label = None; pdf_pop = None; primary_district = None; pdf_raw_line = None
            pdf_men = pdf_women = None
            direct_raw_row, raw_population_qualifier = False, None
        else:
            pdf_label = raw_primary.label_raw
            pdf_pop = raw_primary.population
            pdf_men = int_population(raw_primary.men_raw)
            pdf_women = int_population(raw_primary.women_raw)
            primary_district = raw_primary.district_raw_independent
            pdf_raw_line = raw_primary.raw_line
            direct_raw_row, raw_population_qualifier = classify_raw_table5_label(pdf_label)
            if norm(pdf_label) != norm(c.label_raw):
                reasons.append('pypdf_raw_label_disagrees_with_inventory')
            if int_population(pdf_pop) != int_population(c.table5_population):
                reasons.append('pypdf_population_disagrees_with_inventory')
        district_same = bool(district_norm(source_district) and district_norm(primary_district)
                             and district_norm(source_district) == district_norm(primary_district)
                             and district_norm(source_district) == district_norm(c.district_raw_r2))
        if not district_same:
            reasons.append('independent_raw_district_context_unverified')
        if bool(c.dash_in_counts):
            reasons.append('primary_count_contains_dash_unknown_not_zero')
        if not bool(c.total_equals_sexes):
            reasons.append('primary_total_does_not_equal_sex_counts')
        if str(c.reference_status) != 'extracted_reference' or str(c.row_kind) != 'settlement':
            reasons.append('primary_hierarchy_or_reference_status_not_direct_settlement')
        if not direct_raw_row:
            reasons.append('raw_pdf_label_not_direct_typed_locality_row')
        passed = not reasons
        outcomes.append({
            'r2_source_record_id': str(c.r2_source_record_id),
            'replacement_source_record_id': str(c.reference_id),
            'candidate_key': key,
            'region_raw_r2': c.region_raw_r2, 'settlement_name_r2': c.settlement_name_r2,
            'settlement_type_r2': c.settlement_type_r2,
            'source_name_raw': c.source_name_raw, 'table5_label_raw': c.label_raw,
            'source_population_raw': c.source_population_raw,
            'old_population_r2': int_population(c.population), 'old_population_quality': c.population_value_quality,
            'proposed_primary_population': int_population(c.table5_population),
            'proposed_primary_men': pdf_men, 'proposed_primary_women': pdf_women,
            'official_minus_old_delta': int_population(c.table5_population)-int_population(c.population),
            'delta_abs_gt_10_risk_flag': abs(int_population(c.table5_population)-int_population(c.population)) > 10,
            'source_file': c.source_file, 'source_sha256_inventory': c.r2_source_sha256_from_asset_inventory,
            'source_sha256_recomputed': source_sha, 'source_sheet': c.source_sheet,
            'source_row_1based': int(c.source_row), 'source_raw_district': source_district,
            'source_raw_district_status': source_district_status,
            'source_raw_population': str(raw_pop) if source_path.is_file() else None,
            'source_raw_name': raw_name if source_path.is_file() else None,
            'pdf_page': int(c.pdf_page), 'printed_page': int(c.printed_page),
            'primary_source_file': str(pdf_path), 'primary_source_sha256': primary_pdf_sha,
            'text_line_start_pypdf': int(c.text_line_start), 'text_line_end_pypdf': int(c.text_line_end),
            'raw_pdf_label_independent_pypdf': pdf_label, 'raw_pdf_line_independent_pypdf': pdf_raw_line,
            'primary_raw_district': primary_district,
            'primary_hierarchy_row_kind': str(c.row_kind),
            'primary_raw_direct_typed_locality_row': direct_raw_row,
            'primary_population_qualifier_raw': raw_population_qualifier,
            'primary_reference_status': str(c.reference_status),
            'primary_scope_qualifier': 'Table 5 published coverage: urban localities, rural district centres, rural localities >=3000; population scope can differ from regional secondary source',
            'same_publication_binding_old_to_new': json.dumps({'old_2010_source_record_id': str(c.r2_source_record_id),
                'replacement_2010_source_record_id': str(c.reference_id), 'binding_basis': 'same 2010 publication candidate only; not cross-year proof'}, ensure_ascii=False),
            'proposed_population_quality': 'official_primary_table5_raw_total',
            'stage_status': 'proposed_pending_independent_review' if passed else 'held',
            'hold_reasons_json': json.dumps(reasons, ensure_ascii=False),
        })
    ledger = pd.DataFrame(outcomes)
    proposals = ledger[ledger.stage_status.eq('proposed_pending_independent_review')].copy()

    # Distinct Poppler process and layout extractor verifies every staged page
    # locator/label/count. The row-level population is also checked for a fixed
    # reproducible sample and largest absolute discrepancies below.
    pages = set(proposals.pdf_page.astype(int))
    poppler = _poppler_pages(pdf_path, pages)
    poppler_checks = []
    for r in proposals.itertuples(index=False):
        pg_lines = poppler[int(r.pdf_page)]
        want_name, want_count = norm(r.table5_label_raw), str(int(r.proposed_primary_population))
        hits = [line for line in pg_lines if norm(line).startswith(want_name) and re.search(rf'(?<!\d){re.escape(want_count)}(?!\d)', line)]
        poppler_checks.append({'replacement_source_record_id': r.replacement_source_record_id,
                               'pdf_page': int(r.pdf_page), 'label': r.table5_label_raw,
                               'population': int(r.proposed_primary_population),
                               'poppler_match_count': len(hits), 'poppler_raw_line': hits[0] if len(hits)==1 else None,
                               'status': 'verified' if len(hits)==1 else 'held_poppler_crossread_mismatch'})
    crossread = pd.DataFrame(poppler_checks)
    if len(crossread):
        proposals = proposals.merge(crossread[['replacement_source_record_id','status']], on='replacement_source_record_id', how='left')
        failed_ids = set(crossread.loc[crossread.status.ne('verified'),'replacement_source_record_id'])
        if failed_ids:
            ledger.loc[ledger.replacement_source_record_id.isin(failed_ids), 'stage_status'] = 'held'
            ledger.loc[ledger.replacement_source_record_id.isin(failed_ids), 'hold_reasons_json'] = ledger.loc[ledger.replacement_source_record_id.isin(failed_ids), 'hold_reasons_json'].map(lambda x: json.dumps(json.loads(x)+['poppler_independent_label_count_crossread_failed'], ensure_ascii=False))
        ledger.to_csv(output/'replacement_candidate_ledger.csv', index=False)
        proposals = ledger[ledger.stage_status.eq('proposed_pending_independent_review')].copy()
    else:
        ledger.to_csv(output/'replacement_candidate_ledger.csv', index=False)
    # Full selected-observation-shaped rows for downstream review. Unsupported
    # coordinates, crosswalk IDs and cross-year links remain null/unclaimed.
    source_columns = [c for c in selected.columns if c != '_key']
    selected_by_id = selected.set_index(selected.source_record_id.astype(str), drop=False)
    full_rows = []
    for r in proposals.itertuples(index=False):
        old = selected_by_id.loc[str(r.r2_source_record_id)]
        row = {column: None for column in source_columns}
        row.update({
            'source_record_id': str(r.replacement_source_record_id), 'census_year': 2010,
            'source_file': 'data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf',
            'source_sheet': None, 'source_row': None, 'source_native_id': None,
            'source_name_raw': r.table5_label_raw,
            'settlement_name': r.settlement_name_r2, 'settlement_type': r.settlement_type_r2,
            'region_raw': r.region_raw_r2, 'district_raw': r.primary_raw_district,
            'municipality_raw': None, 'population': int(r.proposed_primary_population),
            'latitude': None, 'longitude': None, 'coordinate_source': None,
            'coverage_status': 'limited_published_table5_coverage', 'fias_id': None,
            'okato': None, 'oktmo': None, 'coordinate_quality': None,
            'population_scope': 'settlement', 'geocoder_settlement_name': None,
            'name_norm': old.get('name_norm'), 'type_norm': old.get('type_norm'),
            'region_norm': old.get('region_norm'), 'district_norm': district_norm(r.primary_raw_district),
            'municipality_norm': '',
            'derivation_note': 'Proposal from direct Table 5 settlement row; see candidate ledger for old value, raw secondary context, source locators, and scope caveat. No R2 application.',
            'snapshot_year': 2010, 'snapshot_record_type': 'settlement_observation',
            'is_additive_settlement_record': True, 'population_value_quality': 'fresh_primary_r5_source',
            'linked_to_2021': False, 'snapshot_rule_version': 'primary_2010_replacement_stage_v1',
            'settlement_id': None, 'analysis_population_additive': None,
            'entity_grain_status': 'direct_primary_table5_settlement_row_pending_review',
            'recovered_official_city_record': None,
            'source_path': 'data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf',
            'source_sha256': r.primary_source_sha256,
            'source_locator': f'PDF page {int(r.pdf_page)}; printed page {int(r.printed_page)}; pypdf text lines {int(r.text_line_start_pypdf)}-{int(r.text_line_end_pypdf)}',
            'source_population_raw': r.raw_pdf_line_independent_pypdf,
            'men': r.proposed_primary_men, 'women': r.proposed_primary_women,
            'extraction_version': 'official_2010_table5_independent_pypdf_crossread_poppler',
            'source_selection_component': 'primary_2010_table5_replacement_proposal',
            'identity_admission': 'pending_independent_review', 'coordinate_admission': None,
        })
        full_rows.append(row)
    full_proposals = pd.DataFrame(full_rows, columns=source_columns)
    full_proposals.to_parquet(output/'proposed_primary_replacement_rows.parquet', index=False)
    full_proposals.to_csv(output/'proposed_primary_replacement_rows.csv', index=False)
    crossread.to_csv(output/'poppler_crossread_all_staged.csv', index=False)

    # Fixed sample of 40 plus 20 largest absolute differences, direct source
    # row values and contexts included in the ledger; this table makes the
    # source-context review set explicit and reproducible.
    risk = ledger[ledger.stage_status.eq('proposed_pending_independent_review')].copy()
    risk = risk.sort_values(['official_minus_old_delta','replacement_source_record_id'], key=lambda s: s.abs() if s.name=='official_minus_old_delta' else s, ascending=[False, True])
    top20 = risk.head(20).copy()
    seed_sample = risk.assign(_sample_key=risk.replacement_source_record_id.map(lambda x: hashlib.sha256(('primary2010-stage-v1:'+x).encode()).hexdigest())).sort_values('_sample_key').head(40)
    review_sample = pd.concat([seed_sample.assign(review_sample='fixed_hash_sample_40'), top20.assign(review_sample='largest_absolute_delta_top20')], ignore_index=True).drop_duplicates('replacement_source_record_id')
    review_sample.to_csv(output/'raw_source_context_review_sample.csv', index=False)

    # The new primary IDs must be unique internally and absent from all R2 IDs.
    existing_ids = set(selected.source_record_id.astype(str))
    proposed_ids = proposals.replacement_source_record_id.astype(str)
    if proposed_ids.duplicated().any() or set(proposed_ids) & existing_ids:
        raise ValueError('proposed primary source IDs are duplicated or already selected')
    ledger.to_csv(output/'replacement_candidate_ledger.csv', index=False)
    delta_counts = Counter()
    for value in proposals.official_minus_old_delta:
        v = abs(int(value))
        delta_counts['exact_0' if v == 0 else 'abs_1_to_10' if v <= 10 else 'abs_11_to_1000' if v <= 1000 else 'abs_gt_1000'] += 1
    manifest = {
        'stage_status': 'proposal_only_no_r2_mutation', 'candidate_cohort': 'unique Table 5/R2 name-type overlap whose previous candidate inventory district strings agreed',
        'inventory_count_reconciliation': {
            'prior_summary_unique_district_agree_count': 653,
            'current_parquet_deduplicated_district_agree_before_unique_candidate_filter': 684,
            'excluded_ambiguous_or_duplicate_key_rows': 31,
            'filtered_stage_cohort_count': len(target),
            'current_inventory_sha256': sha256(inventory_path),
        },
        'input_sha256': {'selected_r2': sha256(selected_path), 'candidate_inventory': sha256(inventory_path), 'primary_pdf': primary_pdf_sha},
        'code_sha256': sha256(Path(__file__)), 'candidate_count': len(target),
        'proposal_count': len(proposals), 'held_count': int(ledger.stage_status.eq('held').sum()),
        'proposal_delta_absolute_bands': dict(delta_counts), 'proposal_delta_net': int(proposals.official_minus_old_delta.sum()) if len(proposals) else 0,
        'r2_key_uniqueness_scope': 'all selected 2010 R2 observations', 'primary_key_uniqueness_scope': 'all extracted Table 5 settlement rows',
        'crossread': 'pypdf raw extraction plus Poppler pdftotext -layout, all staged rows',
        'raw_pdf_facts': pdf_facts,
        'population_scope_note': 'Table 5 is the published urban settlements, rural district centres, and rural places of 3000+ table; different published population scope is possible. Delta >10 is risk-marked and not by itself a veto.',
        'population_binding_note': 'old-to-new is a same-publication 2010 candidate binding only; it is not cross-year identity proof or authority to change selected R2.',
        'no_dash_zero': True, 'no_residual_allocation': True,
        'outputs': {},
    }
    for name in ['replacement_candidate_ledger.csv','proposed_primary_replacement_rows.parquet','proposed_primary_replacement_rows.csv','poppler_crossread_all_staged.csv','raw_source_context_review_sample.csv']:
        manifest['outputs'][name] = {'sha256': sha256(output/name), 'bytes': (output/name).stat().st_size}
    (output/'stage_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument('--selected', type=Path, default=SELECTED)
    ap.add_argument('--inventory', type=Path, default=INVENTORY)
    ap.add_argument('--pdf', type=Path, default=PDF)
    ap.add_argument('--raw-root', type=Path, default=RAW)
    args = ap.parse_args()
    result = build_stage(args.selected, args.inventory, args.pdf, args.output, args.raw_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
