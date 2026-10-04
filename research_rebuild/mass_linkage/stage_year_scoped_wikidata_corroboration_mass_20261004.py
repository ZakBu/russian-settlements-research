#!/usr/bin/env python3
"""Stage candidate-only year-scoped census/Wikidata temporal corroboration.

The historical P1082 row is a secondary, year-labelled corroboration only. It
does not replace a census value or by itself establish historical identity,
scope, exact date, coordinates, or admission. A hypothetical identity edge is
kept only when it is safe against the current accepted graph's year topology.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import duckdb
import pandas as pd

from build_long_table import (ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES,
                              ACCEPTED_PROJECTION_STATUSES)

BASE = Path('/workspace/settlements-work/continuation_20261004')
FROZEN = Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
OUT = BASE / 'R4/year_scoped_wikidata_corroboration_mass_v1'
SELECTED = FROZEN / 'selected_observations.parquet'
SOURCE_EVIDENCE = FROZEN / 'source_evidence.parquet'
DIAG = BASE / 'root/year_scoped_wikidata_temporal_key_diagnostic.parquet'
HISTORY = BASE / 'root/R4/history_application/reviewed_secondary_history_observations.parquet'
EDGES = BASE / 'accepted_mass_extensions/accepted_identity_edges.parquet'
POINTS = BASE / 'accepted_mass_extensions/accepted_point_uses.parquet'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def norm(value) -> str:
    if value is None or pd.isna(value):
        return ''
    s = unicodedata.normalize('NFKC', str(value)).casefold().replace('ё', 'е')
    return re.sub(r'\s+', ' ', s).strip()


class UF:
    def __init__(self, ids):
        self.p = {str(x): str(x) for x in ids}
        self.years = {str(x): {} for x in ids}

    def find(self, x):
        x = str(x)
        p = self.p[x]
        if p != x:
            self.p[x] = self.find(p)
        return self.p[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        low, high = sorted((ra, rb))
        self.p[high] = low
        for year, stats in self.years[high].items():
            if year in self.years[low]:
                a = self.years[low][year]
                self.years[low][year] = [a[0]+stats[0], a[1]+stats[1], a[2]+stats[2], a[3]+stats[3]]
            else:
                self.years[low][year] = stats
        self.years[high] = {}
        return low


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    # Read source population and grain from the immutable selected census rows.
    selected = con.execute("""select source_record_id, census_year::int as census_year,
      settlement_name, settlement_type, region_raw, district_raw, population,
      population_value_quality, population_value_quality_original_tag,
      is_additive_settlement_record, population_scope, source_sha256, source_path, source_sheet,
      source_row, source_locator, source_native_id, publication_binding_basis
      from read_parquet(?) where census_year in (2002,2010,2021)""", [str(SELECTED)]).df()
    selected['source_record_id'] = selected.source_record_id.astype(str)
    if selected.source_record_id.duplicated().any():
        raise RuntimeError('selected source_record_id is not unique')
    by_id = selected.set_index('source_record_id', drop=False)

    # Use the corrected diagnostic, which scopes exact name/province uniqueness
    # independently to each old census year and to the entire selected 2021 set.
    d = con.execute("select * from read_parquet(?)", [str(DIAG)]).df()
    d = d[d.unique_whole_region_year_old.eq(True) & d.unique_whole_region_year_current.eq(True)].copy()
    d = d[d.quantitative_year_eligible.eq(True)].copy()
    d['year'] = d.census_year_old.astype(int)
    d['old_id'] = d.source_record_id_old.astype(str)
    d['current_id'] = d.source_record_id_current.astype(str)
    d = d[d.old_id.isin(by_id.index) & d.current_id.isin(by_id.index)].copy()

    # Replay the reviewed, QID-bound P1082 history row so every candidate carries
    # its exact witness locator/hash and all variant/date conflict flags.
    h = con.execute("""select current_source_record_id, current_wikidata_qid,
      wikidata_statement_id, try_cast(quantitative_year_label as integer) as history_year,
      try_cast(population_value_raw_for_secondary_display as decimal(18,4)) as wd_population,
      population_value_raw_for_secondary_display, history_source_tier, date_precision,
      date_literal_flat_tsv, full_year_prefixes_json, date_raw_full_statement,
      history_raw_source_sha256, history_raw_record_locator, raw_reference_payload_json,
      raw_statement_json, date_variant_conflict, population_variant_conflict,
      quantitative_year_eligible, historical_identity_status, historical_scope_status
      from read_parquet(?) where quantitative_year_eligible
        and population_value_raw_for_secondary_display is not null""", [str(HISTORY)]).df()
    h = h[h.history_year.isin([2002, 2010])].copy()
    h['wd_int'] = h.wd_population.map(lambda x: int(x) if pd.notna(x) and float(x).is_integer() else None)
    h = h[h.wd_int.notna()].copy()
    h['wd_int'] = h.wd_int.astype('int64')
    h['current_source_record_id'] = h.current_source_record_id.astype(str)
    h['year_value_n'] = h.groupby(['current_source_record_id', 'history_year']).wd_int.transform('nunique')
    h['year_statement_n'] = h.groupby(['current_source_record_id', 'history_year']).wikidata_statement_id.transform('nunique')
    h = h[h.year_value_n.eq(1) & ~h.date_variant_conflict.fillna(False) & ~h.population_variant_conflict.fillna(False)].copy()
    # Collapse truly duplicated source rows only; distinct statements for the same
    # single-valued year remain auditable and are represented as a JSON witness set.
    h = h.sort_values(['history_raw_source_sha256','history_raw_record_locator','wikidata_statement_id'], kind='stable')
    h = h.drop_duplicates(['current_source_record_id','history_year'], keep='first').copy()
    d = d.merge(h, left_on=['current_id', 'year'], right_on=['current_source_record_id', 'history_year'], how='inner', validate='many_to_one')
    d['current_source_record_id'] = d.current_id

    # Join original population quality and source evidence without conflating old
    # pointer quarantine flags with contradictions in this independent rule.
    d['census_population'] = d.old_id.map(by_id.population)
    d['old_type'] = d.old_id.map(by_id.settlement_type)
    d['current_type'] = d.current_id.map(by_id.settlement_type)
    d['old_name'] = d.old_id.map(by_id.settlement_name)
    d['current_name'] = d.current_id.map(by_id.settlement_name)
    d['old_region'] = d.old_id.map(by_id.region_raw)
    d['current_region'] = d.current_id.map(by_id.region_raw)
    d['old_district'] = d.old_id.map(by_id.district_raw)
    d['current_district'] = d.current_id.map(by_id.district_raw)
    d['old_source_hash'] = d.old_id.map(by_id.source_sha256)
    d['old_source_path'] = d.old_id.map(by_id.source_path)
    d['old_source_sheet'] = d.old_id.map(by_id.source_sheet)
    d['old_source_row'] = d.old_id.map(by_id.source_row)
    d['old_source_locator'] = d.old_id.map(by_id.source_locator)
    d['old_native_id'] = d.old_id.map(by_id.source_native_id)
    d['current_source_hash'] = d.current_id.map(by_id.source_sha256)
    d['current_source_path'] = d.current_id.map(by_id.source_path)
    d['current_source_locator'] = d.current_id.map(by_id.source_locator)
    d['old_quality'] = d.old_id.map(by_id.population_value_quality)
    d['old_quality_original_tag'] = d.old_id.map(by_id.population_value_quality_original_tag)
    d['old_additive'] = d.old_id.map(by_id.is_additive_settlement_record)
    d['old_population_scope'] = d.old_id.map(by_id.population_scope)
    d['current_population_scope'] = d.current_id.map(by_id.population_scope)
    d['current_population'] = d.current_id.map(by_id.population)
    d['old_int'] = d.census_population.map(lambda x: int(x) if pd.notna(x) and float(x).is_integer() else None)
    d = d[d.old_int.notna()].copy()
    d['old_int'] = d.old_int.astype('int64')
    d['abs_difference'] = (d.wd_int - d.old_int).abs()
    d['exact_population_match'] = d.abs_difference.eq(0)
    d['protected_2010_near_match'] = (
        d.year.eq(2010)
        & d.old_quality.eq('secondary_confidentiality_protected_value_exact_scope_unverified')
        & d.old_quality_original_tag.eq('confidentiality_perturbed_within_ten')
        & d.abs_difference.between(1, 10)
    )
    d = d[d.exact_population_match | d.protected_2010_near_match].copy()
    d['corroboration_class'] = 'exact_numeric_match_secondary_only'
    d.loc[d.protected_2010_near_match, 'corroboration_class'] = 'protected_2010_within_10_secondary_only'

    # Preserve explicit source evidence for review and gate only directly declared
    # successor/event evidence; stale/fuzzy/ordinal legacy pointer flags alone are
    # not physical contradictions under this separately specified rule.
    se = con.execute("select source_record_id, source_evidence_json from read_parquet(?)", [str(SOURCE_EVIDENCE)]).df()
    ev = dict(zip(se.source_record_id.astype(str), se.source_evidence_json.fillna('{}').astype(str)))
    d['old_source_evidence_json'] = d.old_id.map(ev).fillna('{}')
    d['current_source_evidence_json'] = d.current_id.map(ev).fillna('{}')
    def explicit_nonphysical(s):
        try: x=json.loads(s)
        except Exception: return False
        return bool(x.get('is_federal_aggregate') is True)
    d['explicit_federal_aggregate_hold'] = d.old_source_evidence_json.map(explicit_nonphysical) | d.current_source_evidence_json.map(explicit_nonphysical)
    def event_hold(s):
        try:
            x = json.loads(s)
        except Exception:
            return False
        # Only affirmative, direct successor assertion; relation quarantine flags
        # such as legacy_identity_conflict are preserved, not blanket-gated.
        v = x.get('legacy_verified_successor_settlement_id')
        return v is not None and str(v).strip() not in ('', '0', 'nan', 'None')
    d['explicit_successor_event_hold'] = d.old_source_evidence_json.map(event_hold) | d.current_source_evidence_json.map(event_hold)
    d['typed_name_region_agree'] = d.apply(lambda r: norm(r.old_name)==norm(r.current_name) and norm(r.old_region)==norm(r.current_region) and norm(r.old_type)==norm(r.current_type), axis=1)
    d['explicit_district_disagreement'] = d.apply(lambda r: bool(norm(r.old_district) and norm(r.current_district) and norm(r.old_district)!=norm(r.current_district)), axis=1)

    # Canonical ledger validation: optional historical booleans are not acceptance gates.
    edges = con.execute('select * from read_parquet(?)', [str(EDGES)]).df()
    points = con.execute('select * from read_parquet(?)', [str(POINTS)]).df()
    if set(edges.decision_status.dropna().astype(str)) - ACCEPTED_EDGE_STATUSES:
        raise RuntimeError('accepted edge ledger contains a noncanonical status')
    if set(edges.selection_projection_status.dropna().astype(str)) - ACCEPTED_PROJECTION_STATUSES:
        raise RuntimeError('accepted edge ledger contains a noncanonical projection status')
    if set(points.coordinate_admission_status.dropna().astype(str)) - ACCEPTED_COORDINATE_STATUSES:
        raise RuntimeError('accepted point ledger contains a noncanonical status')
    if edges.decision_status.isna().any() or points.coordinate_admission_status.isna().any():
        raise RuntimeError('canonical accepted ledger status is null')
    all_point_ids = set(points.target_source_record_id.astype(str))
    direct_2021_points = set(points.loc[points.target_year.eq(2021), 'target_source_record_id'].astype(str))
    d['has_2021_accepted_point_carrier'] = d.current_id.isin(direct_2021_points)
    p21=points[points.target_year.eq(2021)].copy()
    p21['_prop'] = p21.apply(lambda r: (str(r.get('application_inference_kind') or '').strip() not in ('','None','nan')
        or 'continuity' in str(r.get('coordinate_source') or '').casefold()
        or 'reuse' in str(r.get('coordinate_source') or '').casefold()),axis=1)
    p21=p21.sort_values(['_prop','coordinate_source_file','source_sha256','source_locator'],kind='stable').drop_duplicates('target_source_record_id')
    pmap=p21.set_index(p21.target_source_record_id.astype(str))
    for c, col in [('current_point_coordinate_source','coordinate_source'),('current_point_coordinate_provider','coordinate_provider'),
                   ('current_point_source_file','coordinate_source_file'),('current_point_source_sha256','source_sha256'),
                   ('current_point_source_locator','source_locator'),('current_point_application_inference_kind','application_inference_kind'),
                   ('current_point_coordinate_application_family','coordinate_application_family'),('current_point_admission_status','coordinate_admission_status')]:
        d[c]=d.current_id.map(pmap[col])
    d['current_point_is_propagated_or_continuity'] = d.current_id.map(pmap['_prop']).fillna(False)

    # Reconstruct actual accepted components and baseline joint coverage.
    ids = selected.source_record_id.astype(str).tolist()
    uf = UF(ids)
    for r in selected.itertuples(index=False):
        root = uf.find(r.source_record_id)
        year=int(r.census_year); pop=0 if pd.isna(r.population) else int(r.population)
        stats=uf.years[root].setdefault(year,[0,0,0,0])
        stats[0]+=1; stats[1]+=pop
        if str(r.source_record_id) in all_point_ids:
            stats[2]+=1; stats[3]+=pop
    for r in edges.itertuples(index=False):
        a, b = str(r.from_source_record_id), str(r.to_source_record_id)
        if a not in uf.p or b not in uf.p:
            continue
        # Accepted graph can have same-year group structure from earlier reviewed
        # decisions; it is preserved in baseline, while all proposed merges are
        # required to add disjoint year sets.
        uf.union(a, b)
    expected = {2002:(105536,116990219),2010:(105514,114527509),2021:(105542,115269151)}
    baseline = coverage(uf)
    for y, want in expected.items():
        got = baseline[y]
        if (got['joint_rows'], got['joint_population']) != want:
            raise RuntimeError(f'actual current joint baseline mismatch {y}: {got} != {want}')

    # Candidate endpoint status and graph safety. Type differences and explicit
    # known district differences remain visible as holds for separate review.
    d['graph_relation'] = 'not_simulated'
    d['graph_hold_reason'] = ''
    eligible = []
    for i, r in d.iterrows():
        a, b = r.old_id, r.current_id
        ra, rb = uf.find(a), uf.find(b)
        reason = []
        if not bool(r.old_additive): reason.append('old_source_not_explicitly_additive')
        if bool(r.explicit_federal_aggregate_hold): reason.append('explicit_federal_aggregate_hold')
        if norm(r.old_population_scope) in {'region','municipality','federal_city','federal_city_region','federal_territory','territorial_aggregate','federal_city_aggregate'} or norm(r.current_population_scope) in {'region','municipality','federal_city','federal_city_region','federal_territory','territorial_aggregate','federal_city_aggregate'}:
            reason.append('selected_population_scope_not_physical_locality')
        if not bool(r.has_2021_accepted_point_carrier): reason.append('no_2021_accepted_point_carrier')
        if bool(r.explicit_successor_event_hold): reason.append('explicit_successor_event_hold')
        if not bool(r.typed_name_region_agree): reason.append('name_region_or_type_disagreement')
        if bool(r.explicit_district_disagreement): reason.append('explicit_raw_district_disagreement')
        if ra == rb: reason.append('already_same_accepted_component')
        else:
            ya, yb = set(uf.years[ra]), set(uf.years[rb])
            if ya & yb: reason.append('accepted_component_year_collision')
        if reason:
            d.at[i,'graph_relation'] = 'held_or_redundant'
            d.at[i,'graph_hold_reason'] = '|'.join(reason)
        else:
            d.at[i,'graph_relation'] = 'candidate_graph_safe_before_simulation'
            eligible.append(i)

    # Greedy deterministic union simulation in descending projected population;
    # this is a non-additive ceiling, not a commitment to accept any edge.
    eligible = sorted(eligible, key=lambda i: (-int(d.at[i,'current_population'] or 0), -int(d.at[i,'census_population'] or 0), d.at[i,'old_id'], d.at[i,'current_id']))
    d['simulation_status'] = 'not_graph_safe_or_not_simulated'
    d['candidate_identity_rule'] = 'exact_year_scoped_name_region_unique + current accepted QID binding + single-valued year-labelled P1082; candidate-only corroboration'
    sim_rows = []
    conditional = deepcopy(baseline)
    for i in eligible:
        r = d.loc[i]
        a,b = r.old_id,r.current_id
        ra,rb = uf.find(a),uf.find(b)
        if ra == rb:
            d.at[i,'simulation_status'] = 'redundant_after_prior_candidate_union'
            continue
        if set(uf.years[ra]) & set(uf.years[rb]):
            d.at[i,'simulation_status'] = 'blocked_by_prior_candidate_year_collision'
            continue
        before_a = component_metrics(uf, ra)
        before_b = component_metrics(uf, rb)
        uf.union(a,b)
        after_c = component_metrics(uf, uf.find(a))
        update_coverage(conditional, before_a, -1)
        update_coverage(conditional, before_b, -1)
        update_coverage(conditional, after_c, +1)
        d.at[i,'simulation_status'] = 'conditional_graph_safe_candidate'
        sim_rows.append({'old_source_record_id':a,'current_source_record_id':b,'year':int(r.year),
          'old_population':int(r.census_population),'current_2021_population':int(r.current_population),
          'candidate_priority_population_sum':int(r.census_population+r.current_population),
          'full_chain_component_gain':sum(max(0,after_c[y]['full_rows']-before_a[y]['full_rows']-before_b[y]['full_rows']) for y in (2002,2010,2021)),
          'conditional_joint_population_gain_2002':conditional[2002]['joint_population']-baseline[2002]['joint_population'],
          'conditional_joint_population_gain_2010':conditional[2010]['joint_population']-baseline[2010]['joint_population'],
          'conditional_joint_population_gain_2021':conditional[2021]['joint_population']-baseline[2021]['joint_population']})

    cond = conditional
    d['candidate_status'] = d.simulation_status.map(lambda s: 'candidate_only_independent_identity_review_required' if s=='conditional_graph_safe_candidate' else s)
    # Artifact schema intentionally exposes all proof and limitation fields.
    keep = [
      'corroboration_class','candidate_status','candidate_identity_rule','year','history_year',
      'old_id','current_id','current_source_record_id','source_record_id_old','source_record_id_current',
      'settlement_name_old','settlement_name_current','settlement_type_old','settlement_type_current',
      'region_norm_old','region_norm_current','region_key','name_key','old_district','current_district',
      'typed_name_region_agree','explicit_district_disagreement','explicit_successor_event_hold',
      'explicit_federal_aggregate_hold','old_population_scope','current_population_scope',
      'population_old','population_current','census_population','old_int','wd_int','abs_difference',
      'old_quality','old_quality_original_tag','old_additive','current_wikidata_qid','wikidata_statement_id',
      'wd_population','population_value_raw_for_secondary_display','history_source_tier','date_precision',
      'date_literal_flat_tsv','full_year_prefixes_json','date_raw_full_statement','history_witness_rows_json',
      'history_raw_source_sha256','history_raw_record_locator','raw_reference_payload_json','raw_statement_json',
      'date_variant_conflict','population_variant_conflict','historical_identity_status','historical_scope_status',
      'old_source_hash','old_source_path','old_source_sheet','old_source_row','old_source_locator','old_native_id',
      'current_source_hash','current_source_path','current_source_locator','current_id','has_2021_accepted_point_carrier',
      'current_point_coordinate_source','current_point_coordinate_provider','current_point_source_file','current_point_source_sha256','current_point_source_locator','current_point_application_inference_kind','current_point_coordinate_application_family','current_point_admission_status','current_point_is_propagated_or_continuity',
      'unique_whole_region_year_old','unique_whole_region_year_current','graph_relation','graph_hold_reason','simulation_status',
      'old_source_evidence_json','current_source_evidence_json']
    # repair diagnostics' source record IDs and keep named fields stable
    d['source_record_id_old'] = d.old_id
    d['source_record_id_current'] = d.current_id
    d['settlement_name_old'] = d.old_name
    d['settlement_name_current'] = d.current_name
    d['settlement_type_old'] = d.old_type
    d['settlement_type_current'] = d.current_type
    d['region_norm_old'] = d.old_region
    d['region_norm_current'] = d.current_region
    d['population_old'] = d.census_population
    d['population_current'] = d.current_population
    out = d[[x for x in keep if x in d.columns]].copy()
    out = out.sort_values(['year','source_record_id_old','source_record_id_current'], kind='stable')
    out.to_csv(OUT/'candidate_temporal_corroboration_edges.csv', index=False)
    pd.DataFrame(sim_rows).to_csv(OUT/'conditional_graph_safe_simulation.csv', index=False)
    holds = out[out.graph_relation.eq('held_or_redundant') | out.simulation_status.ne('conditional_graph_safe_candidate')].copy()
    holds.to_csv(OUT/'candidate_holds.csv', index=False)

    scenario = []
    for label, frame in [('all_potential',out),('graph_safe_simulated',out[out.simulation_status.eq('conditional_graph_safe_candidate')]),
                         ('exact_only',out[out.corroboration_class.eq('exact_numeric_match_secondary_only')]),
                         ('protected_2010_near',out[out.corroboration_class.eq('protected_2010_within_10_secondary_only')])]:
        for year in (2002,2010,2021):
            scenario.append({'scenario':label,'year':year,'candidate_rows':len(frame),
              'old_source_rows':frame.source_record_id_old.nunique(), 'current_source_rows':frame.source_record_id_current.nunique(),
              'potential_old_population_sum':int(frame.population_old.sum()),
              'potential_current_population_unique':int(frame.drop_duplicates('current_source_record_id').population_current.sum()),
              'graph_safe_candidate_rows':int(frame.simulation_status.eq('conditional_graph_safe_candidate').sum()),
              'conditional_joint_population_gain_after_greedy_graph_simulation':(cond[year]['joint_population']-baseline[year]['joint_population']) if label=='graph_safe_simulated' else None,
              'baseline_joint_population':baseline[year]['joint_population'] if label=='graph_safe_simulated' else None,
              'conditional_joint_population':cond[year]['joint_population'] if label=='graph_safe_simulated' else None,
              'interpretation':'candidate-only potential; source-reported year/scope/date not independently verified'})
    pd.DataFrame(scenario).to_csv(OUT/'potential_joint_gain_scenarios.csv',index=False)
    rec = {
      'status':'candidate_only_independent_identity_review_required_not_applied',
      'rule':'Exact normalized source settlement name + whole-province key unique among all selected rows in the old census year and among all selected 2021 rows; current source record bound to reviewed QID and has an accepted 2021 point carrier (carrier dependency is exposed, not claimed independent); cached P1082 statement has one unconflicted integer for the labeled year; equality to selected old census population, or only documented 2010 confidentiality perturbation within ±10. Type/district/event and current graph checks remain explicit.',
      'input_sha256':{str(p):sha(p) for p in [SELECTED,SOURCE_EVIDENCE,DIAG,HISTORY,EDGES,POINTS]},
      'canonical_status_sets_imported_from':'research_rebuild/mass_linkage/build_long_table.py',
      'accepted_ledger_rows':{'identity_edges':len(edges),'point_uses':len(points),'direct_2021_point_targets':len(direct_2021_points)},
      'baseline_joint':baseline,
      'candidate_counts':{'unique_key_and_p1082_match_rows':len(out),'exact_numeric_rows':int(out.corroboration_class.eq('exact_numeric_match_secondary_only').sum()),'protected_2010_within_10_rows':int(out.corroboration_class.eq('protected_2010_within_10_secondary_only').sum()),'graph_safe_candidates_after_simulation':int(out.simulation_status.eq('conditional_graph_safe_candidate').sum()),'holds_or_redundant':len(holds),'old_2002_population_sum':int(out.loc[out.year.eq(2002),'population_old'].sum()),'old_2010_population_sum':int(out.loc[out.year.eq(2010),'population_old'].sum())},
      'conditional_after_greedy_simulation':cond,
      'outputs_sha256':{},
      'limitations':['Candidate-only; no identity or coordinate admission and no source population is modified.','Wikidata P1082 is a secondary corroboration, not an independent historical census source; exact year scope/date and physical identity remain unresolved.','Old and current selected publication row identities are preserved; current 2021 point carrier must already be canonically accepted.','Type changes, explicit source district disagreements, direct successor assertions, accepted graph year collisions and redundant component pairs are held.','Potential gains use the accepted graph baseline and a greedy duplicate-year-safe union simulation; they are conditional, non-additive, and not attained coverage.']
    }
    for f in sorted(OUT.iterdir()):
        if f.is_file() and f.name!='receipt.json': rec['outputs_sha256'][f.name]=sha(f)
    (OUT/'receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rec['candidate_counts'],ensure_ascii=False,indent=2))
    print(json.dumps({y:{'joint_rows':cond[y]['joint_rows'],'joint_population':cond[y]['joint_population'],'gain':cond[y]['joint_population']-baseline[y]['joint_population']} for y in cond},indent=2))


def component_metrics(uf, root):
    ys=uf.years[uf.find(root)]
    out={y:{'full_rows':0,'full_population':0,'joint_rows':0,'joint_population':0} for y in (2002,2010,2021)}
    if all(y in ys for y in (2002,2010,2021)):
        for y in (2002,2010,2021):
            rows,pop,pointrows,pointpop=ys[y]
            out[y]={'full_rows':rows,'full_population':pop,'joint_rows':pointrows,'joint_population':pointpop}
    return out


def update_coverage(total, delta, sign):
    for y in (2002,2010,2021):
        for k in total[y]: total[y][k] += sign*delta[y][k]


def coverage(uf):
    out={y:{'full_rows':0,'full_population':0,'joint_rows':0,'joint_population':0} for y in (2002,2010,2021)}
    for root in list(uf.years):
        if uf.find(root)==root: update_coverage(out,component_metrics(uf,root),+1)
    return out


if __name__=='__main__':
    main()
