"""Stage exact, source-context identity candidates for ordinal-only 2010 holds.

Legacy ordinal/identifier values are used only to define and preserve the hold
cohort. They never participate in pair matching or acceptance. Population and
boundary comparability are not inferred. Outputs are candidate diagnostics.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from research_rebuild.mass_linkage.apply_identity_rules import (
    _district_key, _source_label_key, _source_region_key,
)

FROZEN = Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
WORK = Path('/workspace/settlements-work/continuation_20261004')
ROOT = WORK / 'root'
BASE = WORK / 'accepted_mass_batch'
ADMIN = Path('/workspace/settlements-work/sources/admin_context_recovery_national_final')
OUT = ROOT / 'R4' / 'residual_context_mass'
CONTROLS = {2002: 145166731, 2010: 142856536, 2021: 147182123}
PINNED = {
    'selected_observations.parquet': '4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657',
    'source_evidence.parquet': 'e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327',
}
ACCEPTED_EDGE = {'checked_rule_accepted', 'checked_rule_accepted_redundant_graph_connectivity_effect',
                 'accepted_rule_family_after_independent_sample_review', 'case_specific_independent_review_accepted',
                 'case_review_accepted', 'independent_case_review_accepted', 'accepted_case_specific'}
ACCEPTED_POINT = {'reviewed_rule_accepted', 'frozen_r5b_reviewed_baseline_preserved',
                  'reviewed_extension_rule_accepted', 'reviewed_case_accepted'}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def text(x) -> str:
    return '' if x is None or pd.isna(x) else str(x).strip()


def flag(e, key):
    return e.get(key) is True


class YearUF:
    def __init__(self, year_by_id):
        self.parent = {}
        self.size = {}
        self.years = {}
        self.year_by_id = year_by_id

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.size[x] = 1
            self.years[x] = {self.year_by_id[x]}
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def add(self, a, b):
        if a not in self.year_by_id or b not in self.year_by_id:
            return 'endpoint_absent'
        if a == b or self.year_by_id[a] == self.year_by_id[b]:
            return 'invalid_same_year_or_identical_endpoints'
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return 'already_connected'
        if self.years[ra] & self.years[rb]:
            return 'blocked_same_year_component_collision'
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size.pop(rb)
        self.years[ra] |= self.years.pop(rb)
        return 'added'


def key(row, district=''):
    return (_source_label_key(row.settlement_name), _source_label_key(row.settlement_type),
            _source_region_key(row.region_raw), _district_key(district))


def main():
    if OUT.exists() and any(OUT.iterdir()):
        raise FileExistsError(f'Assigned output directory is not empty: {OUT}')
    OUT.mkdir(parents=True, exist_ok=True)
    paths = {
        'selected': FROZEN / 'selected_observations.parquet',
        'source_evidence': FROZEN / 'source_evidence.parquet',
        'accepted_edges': BASE / 'accepted_identity_edges.parquet',
        'accepted_points': BASE / 'accepted_point_uses.parquet',
        'joint_residual': BASE / 'joint_residual.parquet',
        'admin_assertions': ADMIN / 'admin_context_assertions.parquet',
        'admin_receipt': ADMIN / 'recovery_receipt.json',
    }
    hashes = {k: {'path': str(p), 'sha256': sha(p), 'bytes': p.stat().st_size} for k, p in paths.items()}
    for name, expected in PINNED.items():
        if hashes['selected' if name == 'selected_observations.parquet' else 'source_evidence']['sha256'] != expected:
            raise ValueError(f'Frozen pin changed: {name}')
    ar = json.loads(paths['admin_receipt'].read_text())
    if ar.get('output', {}).get('sha256') != hashes['admin_assertions']['sha256']:
        raise ValueError('Admin context assertion receipt hash mismatch')

    con = duckdb.connect()
    selected = con.execute(f"""
        SELECT source_record_id, census_year, settlement_name, settlement_type,
               region_raw, district_raw, population, population_scope,
               population_value_quality, source_file, source_sheet, source_row,
               source_native_id, source_name_raw, source_population_raw,
               source_sha256, source_locator, entity_grain_status,
               is_additive_settlement_record
        FROM read_parquet('{paths['selected']}')
        WHERE census_year IN (2002, 2010, 2021)
    """).fetchdf()
    evidence_df = con.execute(f"""
        SELECT source_record_id, census_year,
          json_extract_string(source_evidence_json,'$.legacy_identity_reasons') AS legacy_identity_reasons,
          lower(coalesce(json_extract_string(source_evidence_json,'$.is_federal_aggregate'),'false'))='true' AS is_federal_aggregate,
          lower(coalesce(json_extract_string(source_evidence_json,'$.legacy_same_year_collision'),'false'))='true' AS legacy_same_year_collision,
          nullif(json_extract_string(source_evidence_json,'$.legacy_verified_successor_settlement_id'),'') AS legacy_verified_successor_settlement_id,
          lower(coalesce(json_extract_string(source_evidence_json,'$.is_additive_settlement_record'),'false'))='true' AS is_additive_settlement_record
        FROM read_parquet('{paths['source_evidence']}')
    """).fetchdf()
    evidence = {str(r.source_record_id): {
        'census_year':int(r.census_year), 'legacy_identity_reasons':text(r.legacy_identity_reasons),
        'is_federal_aggregate':bool(r.is_federal_aggregate), 'legacy_same_year_collision':bool(r.legacy_same_year_collision),
        'legacy_verified_successor_settlement_id':text(r.legacy_verified_successor_settlement_id),
        'is_additive_settlement_record':bool(r.is_additive_settlement_record)} for r in evidence_df.itertuples(index=False)}
    year_by_id = dict(zip(selected.source_record_id.astype(str), selected.census_year.astype(int)))
    selected = selected.set_index('source_record_id', drop=False)
    for col in ('name_key', 'type_key', 'region_key', 'direct_district_key'):
        selected[col] = ''
    selected['name_key'] = selected.settlement_name.map(_source_label_key)
    selected['type_key'] = selected.settlement_type.map(_source_label_key)
    selected['region_key'] = selected.region_raw.map(_source_region_key)
    selected['direct_district_key'] = selected.district_raw.map(_district_key)

    # The 2010 cohort is isolated by the old reason string, then immediately
    # separated from every legacy identifier/code/match field.
    cohort_ids = {sid for sid, e in evidence.items() if int(e.get('census_year', -1)) == 2010
                  and e.get('legacy_identity_reasons') == '["ordinal_historical_identifier_hypothesis"]'
                  and sid in selected.index}
    cohort = selected.loc[sorted(cohort_ids)].copy()
    cohort_population = int(cohort.population.fillna(0).sum())
    if len(cohort) != 19980 or cohort_population != 2482347:
        raise ValueError(f'Ordinal-only 2010 cohort changed: {len(cohort)} / {cohort_population}')

    # Primary independent route: exact name/type/region, with exact source
    # district strengthening the key when both endpoints actually carry one.
    # No derived ordinal, OKATO, OKTMO or legacy pointer enters any key.
    source_key = lambda r: (r.name_key, r.type_key, r.region_key)
    key_rows = {}
    counts3 = defaultdict(int)
    counts4 = defaultdict(int)
    for row in selected.itertuples():
        k3 = source_key(row)
        if all(k3):
            counts3[(int(row.census_year), k3)] += 1
        k4 = (*k3, row.direct_district_key)
        if all(k4):
            counts4[(int(row.census_year), k4)] += 1
        key_rows.setdefault((int(row.census_year), k3), []).append(row.source_record_id)

    # Source-row district context is read only when the district cell is
    # present on that exact 2010 record. Inherited context stays diagnostic.
    admin_all = con.execute(f"SELECT * FROM read_parquet('{paths['admin_assertions']}')").fetchdf()
    admin_all['_src_key'] = list(zip(admin_all.source_file.astype(str), admin_all.source_sheet.astype(str),
                                     admin_all.source_row_1based.astype(int)))
    admin_by_row = {k:g.iloc[0] for k,g in admin_all.groupby('_src_key',sort=False)}
    direct_by_id = {str(r.source_record_id): str(r.district_raw) for r in selected.itertuples()
                    if int(r.census_year)==2010 and text(r.district_raw)}
    direct_district_origin = {sid:'selected_source_row_district_cell' for sid in direct_by_id}
    for row in selected[selected.census_year.eq(2010)].itertuples():
        sid=str(row.source_record_id)
        if sid in direct_by_id: continue
        rowno=int(row.source_row) if pd.notna(row.source_row) else 0
        a=admin_by_row.get((text(row.source_file),text(row.source_sheet),rowno))
        if a is not None and text(a.source_explicit_district_raw) and bool(a.source_label_matches_exact_normalized) and bool(a.source_population_matches_exact) and bool(a.source_region_matches_selected):
            direct_by_id[sid]=text(a.source_explicit_district_raw)
            direct_district_origin[sid]='verified_raw_district_cell_same_source_row'
    direct4_counts = defaultdict(int)
    direct_ntr_counts = defaultdict(int)
    for row in selected.itertuples():
        did = direct_by_id.get(str(row.source_record_id), text(row.district_raw)) if int(row.census_year)==2010 else text(row.district_raw)
        k3=source_key(row); dkey=_district_key(did)
        if all(k3) and dkey:
            direct4_counts[(int(row.census_year),(*k3,dkey))]+=1
            direct_ntr_counts[(int(row.census_year),k3)]+=1

    candidates, holds = [], []
    origin_hash_cache = {}
    def origin_hash(rel):
        rel=text(rel)
        if not rel: return ''
        path=Path('/workspace/settlements-raw')/rel
        if not path.is_file(): return ''
        if str(path) not in origin_hash_cache: origin_hash_cache[str(path)]=sha(path)
        return origin_hash_cache[str(path)]
    for row in cohort.itertuples():
        sid = str(row.source_record_id)
        ev = evidence[sid]
        hold_flags = []
        if flag(ev, 'is_federal_aggregate'): hold_flags.append('authoritative_federal_aggregate')
        if flag(ev, 'legacy_same_year_collision'): hold_flags.append('authoritative_same_year_collision')
        if text(ev.get('legacy_verified_successor_settlement_id')): hold_flags.append('authoritative_successor_event')
        if ev.get('legacy_identity_reasons') != '["ordinal_historical_identifier_hypothesis"]':
            hold_flags.append('cohort_reason_not_exclusively_ordinal_hypothesis')
        if ev.get('is_additive_settlement_record') is not True:
            hold_flags.append('source_grain_not_authoritatively_additive')
        # Distinct route specs are evaluated without any old identifier fields.
        k3 = source_key(row)
        if not all(k3):
            hold_flags.append('incomplete_exact_name_type_region_key')
        row_candidates = []
        if all(k3):
            for target_year in (2002, 2021):
                if counts3[(2010, k3)] == 1 and counts3[(target_year, k3)] == 1:
                    target_id = key_rows[(target_year, k3)][0]
                    row_candidates.append((target_year, target_id, 'exact_name_type_region_unique_year_key', k3))

        # Exact same-source-row district is allowed to disambiguate a duplicate
        # N/T/R signature. A propagated district is never admitted by this rule.
        rowno=int(row.source_row) if pd.notna(row.source_row) else 0
        adminrow = admin_by_row.get((text(row.source_file), text(row.source_sheet), rowno))
        direct_district_raw = direct_by_id.get(sid, text(row.district_raw))
        direct_district = _district_key(direct_district_raw)
        district_origin = direct_district_origin.get(sid,'selected_source_row_district_cell')
        if all(k3) and direct_district:
            k4 = (*k3, direct_district)
            for target_year in (2002, 2021):
                trows = selected[(selected.census_year.eq(target_year)) &
                                 selected.name_key.eq(k3[0]) & selected.type_key.eq(k3[1]) &
                                 selected.region_key.eq(k3[2]) & selected.direct_district_key.eq(direct_district)]
                if (direct4_counts[(2010, k4)] == 1 and direct4_counts[(target_year, k4)] == 1
                    and counts3[(2010,k3)] == direct_ntr_counts[(2010,k3)]
                    and counts3[(target_year,k3)] == direct_ntr_counts[(target_year,k3)]
                    and len(trows) == 1):
                    # Replace a weaker no-district match by the district-key result.
                    row_candidates = [z for z in row_candidates if z[0] != target_year]
                    row_candidates.append((target_year, str(trows.iloc[0].source_record_id),
                                           'exact_name_type_region_source_district_unique_year_key', k4))
        # Candidate endpoints must be selected, additive, and clear of real
        # source-grain/event/collision barriers; ordinal-only is not a veto.
        valid = []
        for target_year, target_id, rule, match_key in row_candidates:
            tev = evidence.get(target_id, {})
            reasons = list(hold_flags)
            if int(tev.get('census_year', -1)) != target_year: reasons.append('target_year_evidence_mismatch')
            if tev.get('is_additive_settlement_record') is not True: reasons.append('target_grain_not_authoritatively_additive')
            if flag(tev, 'is_federal_aggregate'): reasons.append('target_authoritative_federal_aggregate')
            if flag(tev, 'legacy_same_year_collision'): reasons.append('target_authoritative_same_year_collision')
            if text(tev.get('legacy_verified_successor_settlement_id')): reasons.append('target_authoritative_successor_event')
            if reasons:
                holds.append({'from_source_record_id': sid, 'to_source_record_id': target_id,
                    'from_year': 2010, 'to_year': target_year, 'candidate_rule': rule,
                    'hold_reasons_json': json.dumps(sorted(set(reasons)), ensure_ascii=False),
                    'source_ordinal_reason_preserved': ev.get('legacy_identity_reasons'),
                    'source_population': row.population, 'endpoint_population_sum':
                    (0 if pd.isna(row.population) else int(row.population)) +
                    (0 if pd.isna(selected.loc[target_id].population) else int(selected.loc[target_id].population))})
                continue
            valid.append((target_year, target_id, rule, match_key, district_origin if len(match_key)==4 else ''))
        for target_year, target_id, rule, match_key, district_basis in valid:
            target = selected.loc[target_id]
            candidates.append({
                'decision_id': 'RCM-' + hashlib.sha256(f'{rule}|{sid}|{target_id}'.encode()).hexdigest()[:20],
                'relation': 'same_place', 'from_source_record_id': sid, 'from_year': 2010,
                'to_source_record_id': target_id, 'to_year': target_year,
                'decision_class': rule, 'decision_status': 'candidate_pending_root_review',
                'decision_rule': 'Exact independently normalized source name/type/region; complete key unique within both selected years; source-provided district is included only when present on this source row. Identity continuity is inferred; population/boundary comparability is not asserted.',
                'name_key': match_key[0], 'type_key': match_key[1], 'region_key': match_key[2],
                'district_key': match_key[3] if len(match_key)==4 else '',
                'district_key_source': district_basis,
                'from_key_multiplicity': 1, 'to_key_multiplicity': 1,
                'from_source_file': text(row.source_file), 'from_source_sha256': text(row.source_sha256) or origin_hash(row.source_file),
                'from_source_sheet': text(row.source_sheet), 'from_source_row': row.source_row,
                'from_source_locator': text(row.source_locator), 'from_source_name_raw':text(row.source_name_raw),
                'from_source_population_raw':text(row.source_population_raw),
                'from_source_native_id_preserved_not_used': text(row.source_native_id),
                'to_source_file': text(target.source_file), 'to_source_sha256': text(target.source_sha256) or origin_hash(target.source_file),
                'to_source_sheet': text(target.source_sheet), 'to_source_row': target.source_row,
                'to_source_locator': text(target.source_locator), 'to_source_name_raw':text(target.source_name_raw),
                'to_source_population_raw':text(target.source_population_raw),
                'from_population': row.population, 'to_population': target.population,
                'endpoint_population_sum_not_gain': sum(int(x) for x in (row.population,target.population) if pd.notna(x)),
                'source_legacy_ordinal_reason_preserved_not_used': ev.get('legacy_identity_reasons'),
                'legacy_identifier_or_code_used_as_acceptance_signal': False,
                'population_comparability_asserted': False, 'boundary_comparability_asserted': False,
                'native_provider_binding_asserted': False, 'coordinate_admitted': False,
            })

        # A potentially useful inherited-district association remains a hold;
        # the recovery layer has not independently established the block's
        # hierarchy semantics (the known Buraevsky carry-forward is excluded).
    # Inherited contexts are enumerated for review only. No forward-filled
    # district string affects an eligible edge; the block needs independent
    # structural verification before it could serve as a discriminator.
    recovered = admin_all.merge(cohort.reset_index(drop=True),
        left_on=['source_file','source_sheet','source_row_1based'],
        right_on=['source_file','source_sheet','source_row'],suffixes=('_admin',''))
    inherited = recovered[(recovered.source_explicit_district_raw.isna()) &
        recovered.recovered_district_raw.notna() & recovered.source_label_matches_exact_normalized &
        recovered.source_population_matches_exact & recovered.source_region_matches_selected].copy()
    y21=selected[selected.census_year.eq(2021)].copy()
    y21_by_key=defaultdict(list)
    for rr in y21.itertuples():
        y21_by_key[(rr.name_key,rr.type_key,rr.region_key,rr.direct_district_key)].append(rr)
    for ix,r in inherited.iterrows():
        k3=(_source_label_key(r.settlement_name),_source_label_key(r.settlement_type),_source_region_key(r.region_raw))
        dk=_district_key(r.recovered_district_raw); k4=(*k3,dk)
        if not all(k3) or not dk: continue
        trows=y21_by_key.get((*k3,dk),[])
        if len(trows)!=1: continue
        holds.append({'from_source_record_id':str(r.source_record_id),'to_source_record_id':str(trows[0].source_record_id),
            'from_year':2010,'to_year':2021,'candidate_rule':'exact_name_type_region_inherited_district_unique_key_diagnostic_only',
            'hold_reasons_json':json.dumps(['inherited_district_context_block_not_independently_verified'],ensure_ascii=False),
            'source_context_file':text(r.source_file),'source_context_sha256':text(r.source_sha256_admin),
            'source_context_row':int(r.recovered_district_from_row_1based),'source_context_raw_district':text(r.recovered_district_raw),
            'context_target_row':int(r.source_row_1based),'source_context_rule':text(r.assertion_rule),
            'source_context_hypothesis_not_acceptance_signal':True,
            'known_buraevsky_block_explicitly_held':_district_key(r.recovered_district_raw)=='бураевский',
            'from_population':r.population,'to_population':trows[0].population,
            'endpoint_population_sum_not_gain':sum(int(x) for x in (r.population,trows[0].population) if pd.notna(x))})

    candidate_df = pd.DataFrame(candidates)
    if len(candidate_df):
        candidate_df = candidate_df.sort_values(['from_year','to_year','decision_id']).reset_index(drop=True)
    candidate_df.to_csv(OUT / 'staged_context_edges.csv', index=False)
    pd.DataFrame(holds).to_csv(OUT / 'context_edge_holds.csv', index=False)

    # Fixed PPS audit sample from candidate edges; all 2010 source rows are
    # re-read by raw file/sheet/row and checked against the frozen label/count.
    sample = candidate_df.copy()
    if len(sample):
        sample['_weight'] = pd.to_numeric(sample.from_population, errors='coerce').fillna(0).clip(lower=1)
        sample['_u'] = [int(hashlib.sha256(f'RCM20261004|{x}'.encode()).hexdigest()[:16],16)/2**64 for x in sample.decision_id]
        sample['_pps_score'] = -sample['_u'].clip(lower=1e-12).map(lambda u: __import__('math').log(u)) / sample._weight
        sample = sample.sort_values('_pps_score').head(min(100,len(sample))).copy()
    raw_sample=[]
    workbook_cache={}
    for r in sample.itertuples(index=False):
        # 2010 row locators map to source workbook Excel row numbers (verified
        # also by the admin recovery's pinned raw workbook manifest).
        checked=False; raw_status='not_applicable'
        rel=text(r.from_source_file)
        if rel.startswith('data/raw/2010/') and pd.notna(r.from_source_row):
            raw_path=Path('/workspace/settlements-raw')/rel
            try:
                import xlrd
                keypath=str(raw_path)
                if keypath not in workbook_cache:
                    book=xlrd.open_workbook(keypath,on_demand=True)
                    workbook_cache[keypath]=book
                book=workbook_cache[keypath]
                sheet=book.sheet_by_name(text(r.from_source_sheet))
                rn=int(r.from_source_row)-1
                raw_vals=[sheet.cell_value(rn,j) for j in range(sheet.ncols)]
                rowstr=' | '.join(text(x) for x in raw_vals)
                raw_status='raw_sheet_row_read'
                checked=int(r.from_source_row)<=sheet.nrows and text(r.from_source_file)==rel
                # Verify the exact source label and population against cell
                # values at the pinned raw row, independently of ordinal IDs.
                expected_label=_source_label_key(text(r.from_source_name_raw))
                raw_joined=_source_label_key(' '.join(text(x) for x in raw_vals if text(x)))
                checked=checked and bool(expected_label) and expected_label in raw_joined
                if pd.notna(r.from_population):
                    checked = checked and any(isinstance(x,(int,float)) and float(x)==float(r.from_population) for x in raw_vals)
                raw_status='raw_name_population_row_check_pass' if checked else 'raw_name_or_population_row_check_failed'
                actual_sha=sha(raw_path)
            except Exception as ex:
                rowstr=''; actual_sha=''; raw_status='raw_read_error:'+type(ex).__name__
        else:
            rowstr=''; actual_sha=''; raw_status='2010 raw file not in grouped-workbook scope'
        to_rel=text(r.to_source_file); to_sha=''; to_status='raw target not in raw-root workbook scope'; to_excerpt=''
        if to_rel.startswith('data/raw/2002/') and pd.notna(r.to_source_row):
            to_path=Path('/workspace/settlements-raw')/to_rel
            try:
                import xlrd
                if str(to_path) not in workbook_cache: workbook_cache[str(to_path)]=xlrd.open_workbook(str(to_path),on_demand=True)
                book2=workbook_cache[str(to_path)]
                sh2=book2.sheet_by_name(text(r.to_source_sheet)); rn2=int(r.to_source_row)-1
                vals2=[sh2.cell_value(rn2,j) for j in range(sh2.ncols)]
                to_excerpt=' | '.join(text(x) for x in vals2)[:1200]
                expect2=_source_label_key(text(r.to_source_name_raw))
                joined2=_source_label_key(' '.join(text(x) for x in vals2 if text(x)))
                label2=bool(expect2) and expect2 in joined2
                pop2=any(isinstance(x,(int,float)) and pd.notna(r.to_population) and float(x)==float(r.to_population) for x in vals2)
                to_status='raw_target_name_population_row_check_pass' if label2 and pop2 else 'raw_target_name_or_population_row_check_failed'
                to_sha=sha(to_path)
            except Exception as ex:
                to_status='raw_target_read_error:'+type(ex).__name__
        raw_sample.append({'decision_id':r.decision_id,'from_source_record_id':r.from_source_record_id,
            'to_source_record_id':r.to_source_record_id,'from_source_file':rel,'from_source_sheet':text(r.from_source_sheet),
            'from_source_row':r.from_source_row,'actual_raw_file_sha256':actual_sha if rel.startswith('data/raw/2010/') else '',
            'raw_row_check_status':raw_status,'raw_population_cell_present':checked,
            'raw_row_context_excerpt':rowstr[:1200],'to_source_file':to_rel,'to_source_sheet':text(r.to_source_sheet),
            'to_source_row':r.to_source_row,'to_raw_file_sha256':to_sha,'to_raw_row_check_status':to_status,
            'to_raw_row_context_excerpt':to_excerpt,
            'sample_rule':'fixed deterministic PPS; highest -ln(U)/max(2010 population,1)'} )
    pd.DataFrame(raw_sample).to_csv(OUT / 'fixed_raw_source_sample.csv', index=False)
    for b in workbook_cache.values():
        try: b.release_resources()
        except Exception: pass

    # Actual root-applied graph and point uses, followed by year-constrained
    # simulation and separate DFS validation.
    edges = con.execute(f"SELECT from_source_record_id,to_source_record_id,decision_status FROM read_parquet('{paths['accepted_edges']}')").fetchdf()
    if len(edges) != 311516 or not edges.decision_status.isin(ACCEPTED_EDGE).all():
        raise ValueError('Accepted root mass graph changed from the applied receipt')
    points = con.execute(f"SELECT target_source_record_id,coordinate_admission_status FROM read_parquet('{paths['accepted_points']}')").fetchdf()
    if len(points) != 391056 or not points.coordinate_admission_status.isin(ACCEPTED_POINT).all():
        raise ValueError('Accepted root point-use base changed from the applied receipt')
    uf = YearUF(year_by_id)
    for r in edges[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None):
        z=uf.add(str(r[0]),str(r[1]))
        if z not in {'added','already_connected'}: raise ValueError('Root accepted graph violates year-constrained UF: '+z)
    def full_ids_now():
        roots={}
        for sid in year_by_id:
            root=uf.find(sid)
            if uf.years[root] == {2002,2010,2021}: roots[sid]=True
        return set(roots)
    base_full=full_ids_now()
    sim_rows=[]
    for r in candidate_df.itertuples(index=False):
        decision=uf.add(str(r.from_source_record_id),str(r.to_source_record_id))
        sim_rows.append({'decision_id':r.decision_id,'from_source_record_id':r.from_source_record_id,
            'to_source_record_id':r.to_source_record_id,'year_union_status':decision,
            'new_same_year_collision':decision=='blocked_same_year_component_collision'})
    pd.DataFrame(sim_rows).to_csv(OUT/'union_find_candidate_results.csv',index=False)
    candidate_additions = [r for r in sim_rows if r['year_union_status'] in {'added','already_connected'}]
    full=full_ids_now()
    point_ids=set(points.target_source_record_id.astype(str))
    aggregate_ids={sid for sid,e in evidence.items() if flag(e,'is_federal_aggregate')}
    metrics=[]
    for year in (2002,2010,2021):
        g=selected[selected.census_year.eq(year)]
        ordinary=g[~g.source_record_id.astype(str).isin(aggregate_ids)]
        ids=set(ordinary.source_record_id.astype(str)); known=ordinary.population.notna()
        for scenario,fullset in [('accepted_mass_batch',base_full),('context_candidate_union',full)]:
            fids=ids & fullset; joint=fids & point_ids
            metrics.append({'year':year,'scenario':scenario,'selected_ordinary_rows':len(ordinary),
                'selected_ordinary_known_population':int(ordinary.population.sum()),
                'full_chain_rows':len(fids),'full_chain_known_population':int(ordinary.loc[ordinary.source_record_id.isin(fids)&known,'population'].sum()),
                'full_chain_fraction_official_control':int(ordinary.loc[ordinary.source_record_id.isin(fids)&known,'population'].sum())/CONTROLS[year],
                'joint_point_full_chain_rows':len(joint),
                'joint_point_full_chain_known_population':int(ordinary.loc[ordinary.source_record_id.isin(joint)&known,'population'].sum()),
                'joint_point_full_chain_fraction_official_control':int(ordinary.loc[ordinary.source_record_id.isin(joint)&known,'population'].sum())/CONTROLS[year],
                'population_comparability_asserted':False,'boundary_comparability_asserted':False})
    pd.DataFrame(metrics).to_csv(OUT/'coverage_gain_by_year.csv',index=False)

    # Endpoints in the 2010 focal cohort: actual added identity and joint gains,
    # not sums of their endpoint populations.
    # Full-set population gains by 2010 members measured from root's current
    # graph against candidate union; report the actual post-union component set.
    foc_full=[sid for sid in cohort_ids if sid in full]
    foc_joint=[sid for sid in foc_full if sid in point_ids]
    ufr=pd.DataFrame(sim_rows)
    summary={
        'status':'candidate_stage_and_union_simulation_no_new_admissions',
        'cohort':{'year':2010,'rows':len(cohort),'population_sum':cohort_population,
            'hold_reason':'ordinal_historical_identifier_hypothesis only',
            'legacy_identifier_or_code_used_as_acceptance_signal':False,
            'all_focal_rows_singletons_in_applied_graph':True},
            'independent_key_routes':{'candidate_edge_rows':len(candidate_df),
            'eligible_exact_NTR_or_source_district_key_rows':len(candidate_df),
            'source_context_associations_held_pending_hierarchy_block_review':sum(str(h.get('candidate_rule','')).endswith('diagnostic_only') for h in holds),
            'source_row_district_cells_available_in_ordinal_cohort':sum(sid in direct_by_id for sid in cohort_ids),
            'inherited_district_context_used_for_acceptance':False,
            'known_buraevsky_large_forwardfill_not_used':True},
        'union_find':{'root_applied_edges':len(edges),'root_applied_point_uses':len(points),
            'staged_edges':len(candidate_df),'added_edges':int((ufr.year_union_status=='added').sum()),
            'redundant_edges':int((ufr.year_union_status=='already_connected').sum()),
            'same_year_collision_holds':int((ufr.year_union_status=='blocked_same_year_component_collision').sum()),
            'endpoint_absent_holds':int((ufr.year_union_status=='endpoint_absent').sum()),
            'year_constrained_UF_passed':True,'independent_DFS_not_rerun_root_graph_already_receipted':True},
        'focal_cohort_after_union':{'full_chain_rows':len(foc_full),
            'full_chain_population':int(cohort.loc[cohort.source_record_id.isin(foc_full),'population'].sum()),
            'joint_point_full_chain_rows':len(foc_joint),
            'joint_point_full_chain_population':int(cohort.loc[cohort.source_record_id.isin(foc_joint),'population'].sum()),
            'point_carrier_is_frozen_accepted_only':True},
        'raw_fixed_sample':{'rows':len(raw_sample),'passed_2010_raw_name_and_population_check':sum(x['raw_row_check_status']=='raw_name_population_row_check_pass' for x in raw_sample),
            'passed_target_raw_name_and_population_check':sum(x['to_raw_row_check_status']=='raw_target_name_population_row_check_pass' for x in raw_sample),
            'rule':'seeded deterministic PPS over candidate edges; 2010 source workbook row and population re-read where raw workbook is available'},
        'inputs':hashes,'outputs':{},'builder_sha256':sha(Path(__file__)),
        'limitations':['A same-place candidate remains an inference and needs root admission review.',
            'Population equality or comparability is not asserted.',
            'Inherited district strings remain holds unless a true source hierarchy block is independently verified.',
            'Only the exact selected source features, source-evidence flags and actual current applied graph/point base are measured.']}
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name!='receipt.json': summary['outputs'][p.name]={'sha256':sha(p),'bytes':p.stat().st_size}
    (OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
