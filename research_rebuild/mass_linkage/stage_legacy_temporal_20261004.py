"""Stage conservative mass temporal identity edges from the pinned legacy crosswalk.

The legacy settlement_id is only a candidate pointer. Admission to the staged
ordinary-place rule additionally requires a unique physical source row for the
year and independently matching name, type, region, and available district on
the exact linked 2021 selected observation. This infers stable continuity; it
does not prove historical continuity.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import pandas as pd


DB = Path('/workspace/settlements-assets/baseline/legacy_database_20260929.duckdb')
DB_SHA = '26a2fe5b2ce05119d919a196beb57cd655a49ffffb0ff8f194762aa78e6b5b64'
F = Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
OUT = Path('/workspace/settlements-work/continuation_20261004/legacy_temporal')
SEED = 20261004


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def norm(x) -> str:
    if x is None or pd.isna(x):
        return ''
    s = str(x).lower().replace('ё', 'е').strip()
    s = re.sub(r'[^0-9a-zа-я]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def admin_norm(x) -> str:
    """Normalize admin labels while retaining their substantive named tokens."""
    s = norm(x)
    drop = {'область', 'обл', 'край', 'республика', 'респ', 'автономная',
            'округ', 'автономный', 'район', 'муниципальный', 'городской',
            'федерального', 'значения'}
    return ' '.join(t for t in s.split() if t not in drop)


def region_key(x) -> str:
    """Same reviewed alias/suffix rules used by apply_historical_identity_rule."""
    s = re.sub(r'[-–—]+', ' ', norm(x))
    aliases = {'рсо': 'северная осетия алания', 'кчр': 'карачаево черкесская',
               'кбр': 'кабардино балкарская', 'якутия': 'саха якутия',
               'удмуртия': 'удмуртская', 'чувашия': 'чувашская',
               'нижегород': 'нижегородская',
               'чувашская республика чувашия': 'чувашская'}
    s = aliases.get(' '.join(s.split()), s)
    s = re.sub(r'^республика\s+', '', s)
    s = re.sub(r'\s+(область|обл\.?|край|края|республика|респ\.?|автономный округ|автономная область)$', '', s)
    return ' '.join(s.split())


def text(x) -> str:
    return '' if x is None or pd.isna(x) else str(x).strip()


def main() -> None:
    if sha(DB) != DB_SHA:
        raise RuntimeError('legacy database sha256 mismatch')
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)
    selected = con.execute(f"""
        SELECT source_record_id, census_year, source_file, source_sheet, source_row,
               source_native_id, source_name_raw, settlement_name, settlement_type,
               region_raw, district_raw, municipality_raw, population, latitude,
               longitude, population_scope, is_additive_settlement_record,
               population_value_quality, entity_grain_status, settlement_id,
               coordinate_source, coordinate_quality, source_path, source_sha256, source_locator
        FROM read_parquet('{F}/selected_observations.parquet')
    """).fetchdf()
    cw = con.execute("""
        SELECT source_record_id, census_year, source_native_id, source_name_raw,
               settlement_name, settlement_type, region_raw, district_raw,
               municipality_raw, population, settlement_id,
               matched_to_source_record_id, match_method, match_score, accepted,
               quality_flag, entity_year_record_count,
               is_preferred_entity_year_observation, present_in_2021,
               relationship_to_2021, is_additive_settlement_record,
               verified_successor_settlement_id
        FROM census_crosswalk
    """).fetchdf()
    bindings = con.execute(f"""
        SELECT old_source_record_id, new_source_record_id, census_year
        FROM read_parquet('{F}/accepted_publication_bindings.parquet')
    """).fetchdf()
    con.close()

    # Selected rows have the replacement 2010 source ID. Carry exact source-ID
    # migration to the legacy crosswalk; do not treat the binding as identity.
    old_to_new = {str(r.old_source_record_id): str(r.new_source_record_id)
                  for r in bindings.itertuples() if int(r.census_year) == 2010}
    cw['selected_source_record_id'] = cw.source_record_id.astype(str).map(
        lambda x: old_to_new.get(x, x))
    selected = selected.drop_duplicates('source_record_id').copy()
    sel = selected.set_index('source_record_id', drop=False)
    cw['selected_present'] = cw.selected_source_record_id.isin(sel.index)
    c2021 = cw[cw.census_year.eq(2021)].copy()
    # Current anchor is the crosswalk's actual 2021 record, not the legacy
    # settlement pointer by itself. Resolve each historical edge to that exact
    # selected record, and independently verify the pointer in both year rows.
    c2021_by_source = c2021.set_index('source_record_id', drop=False)
    sel21 = selected[selected.census_year.eq(2021)].set_index('source_record_id', drop=False)

    # Count source-level duplicate observations by physical year/name/admin grain.
    # The legacy collision flags are retained and checked, not converted to zero.
    exact_anchor_counts = Counter()
    region_anchor_counts = Counter()
    source_exact_counts = Counter()
    for r in c2021.itertuples():
        k = (norm(r.settlement_name), norm(r.settlement_type), region_key(r.region_raw), admin_norm(r.district_raw))
        exact_anchor_counts[k] += 1
        region_anchor_counts[(norm(r.settlement_name), norm(r.settlement_type), region_key(r.region_raw))] += 1
    for r in cw[cw.census_year.isin([2002, 2010])].itertuples():
        source_exact_counts[(int(r.census_year), norm(r.settlement_name), norm(r.settlement_type), region_key(r.region_raw))] += 1

    output = []
    holds = []
    for r in cw[cw.census_year.isin([2002, 2010])].itertuples():
        source_id = r.selected_source_record_id
        reasons = []
        if source_id not in sel.index:
            reasons.append('selected_source_id_unresolved')
            old = None
        else:
            old = sel.loc[source_id]
            if isinstance(old, pd.DataFrame):
                reasons.append('selected_source_id_nonunique')
                old = old.iloc[0]
        if not bool(r.accepted): reasons.append('legacy_crosswalk_not_accepted')
        if not bool(r.is_preferred_entity_year_observation): reasons.append('not_preferred_entity_year_row')
        if int(r.entity_year_record_count or 0) != 1: reasons.append('legacy_same_year_collision')
        if not bool(r.is_additive_settlement_record): reasons.append('legacy_source_grain_not_additive')
        if text(r.verified_successor_settlement_id): reasons.append('verified_successor_event_excluded_from_ordinary_rule')
        if not text(r.settlement_id): reasons.append('no_legacy_group_pointer')
        target_id = text(r.matched_to_source_record_id)
        target = c2021_by_source.loc[target_id] if target_id in c2021_by_source.index else None
        if isinstance(target, pd.DataFrame):
            reasons.append('2021_anchor_source_id_nonunique')
            target = target.iloc[0]
        if target is None:
            reasons.append('exact_2021_anchor_unresolved')
            anchor = None
        elif target_id not in sel21.index:
            reasons.append('2021_anchor_not_in_selected_release')
            anchor = None
        else:
            anchor = sel21.loc[target_id]
        # Require same crosswalk group on source and exact target, but never use
        # that inherited group pointer as the sole acceptance evidence.
        if target is not None and text(r.settlement_id) != text(target.settlement_id):
            reasons.append('legacy_group_pointer_disagrees_with_2021_anchor')
        fields = {}
        if target is not None:
            fields = {
                'name_exact': norm(r.settlement_name) != '' and norm(r.settlement_name) == norm(target.settlement_name),
                'type_exact': norm(r.settlement_type) != '' and norm(r.settlement_type) == norm(target.settlement_type),
                'region_exact': region_key(r.region_raw) != '' and region_key(r.region_raw) == region_key(target.region_raw),
                'district_exact': admin_norm(r.district_raw) != '' and admin_norm(r.district_raw) == admin_norm(target.district_raw),
                'district_available': bool(admin_norm(r.district_raw) and admin_norm(target.district_raw)),
            }
            if not fields['name_exact']: reasons.append('independent_name_disagreement')
            if not fields['type_exact']: reasons.append('independent_type_disagreement')
            if not fields['region_exact']: reasons.append('independent_region_disagreement')
            if fields['district_available'] and not fields['district_exact']:
                reasons.append('available_district_disagreement')
            region_name_type_key = (norm(target.settlement_name), norm(target.settlement_type), region_key(target.region_raw))
            anchor_key = (*region_name_type_key, admin_norm(target.district_raw))
            if fields['district_available']:
                if exact_anchor_counts[anchor_key] != 1:
                    reasons.append('nonunique_2021_exact_admin_name_type_anchor')
            else:
                source_key = (int(r.census_year), norm(r.settlement_name), norm(r.settlement_type), region_key(r.region_raw))
                if region_anchor_counts[region_name_type_key] != 1 or source_exact_counts[source_key] != 1:
                    reasons.append('district_missing_and_name_type_region_not_unique_in_both_years')
        if anchor is not None:
            if old is not None:
                for c, legacy_col in [('settlement_name','settlement_name'),('settlement_type','settlement_type'),
                                      ('region_raw','region_raw'),('district_raw','district_raw')]:
                    # Selected-source metadata must still agree with the legacy
                    # row; this checks migration and source-row identity.
                    if c == 'region_raw': left, right = region_key(old[c]), region_key(getattr(r, legacy_col))
                    elif c == 'district_raw': left, right = admin_norm(old[c]), admin_norm(getattr(r, legacy_col))
                    else: left, right = norm(old[c]), norm(getattr(r, legacy_col))
                    if left and right and left != right:
                        reasons.append('selected_source_metadata_disagrees_with_legacy_row:' + c)
            if not bool(anchor.get('is_additive_settlement_record', False)):
                reasons.append('2021_anchor_grain_not_additive')
            if text(anchor.get('entity_grain_status')).lower() in {'aggregate', 'municipal_aggregate', 'federal_aggregate'}:
                reasons.append('2021_anchor_aggregate_grain')
        # Null optional population-scope metadata is recorded without veto.
        scope_unknown = old is None or not text(old.get('population_scope'))
        reason_set = sorted(set(reasons))
        status = 'staged_accepted_stable_ordinary_place_inference' if not reason_set else 'held_for_review'
        row = {
            'decision_id': f"legacy-temporal-{r.census_year}-{hashlib.sha256((str(source_id)+'|'+target_id).encode()).hexdigest()[:18]}",
            'relation': 'same_place_temporal_continuity',
            'from_source_record_id': source_id,
            'from_year': int(r.census_year),
            'to_source_record_id': target_id,
            'to_year': 2021,
            'decision_status': status,
            'decision_rule': 'legacy_pointer_plus_unique_exact_name_type_region_and_available_district_plus_unique_preferred_additive_source_row; stable ordinary-place continuity assumed',
            'decision_class': 'ordinary_stable_place_continuity_inference' if not reason_set else 'legacy_crosswalk_pointer_candidate_only',
            'legacy_source_record_id': str(r.source_record_id),
            'legacy_settlement_id_candidate': text(r.settlement_id),
            'legacy_matched_to_source_record_id': target_id,
            'legacy_match_method': text(r.match_method),
            'legacy_match_quality_flag': text(r.quality_flag),
            'legacy_match_score': r.match_score,
            'legacy_entity_year_record_count': r.entity_year_record_count,
            'legacy_preferred_year_row': bool(r.is_preferred_entity_year_observation),
            'legacy_additive_source_grain': bool(r.is_additive_settlement_record),
            'historical_verified_successor_id': text(r.verified_successor_settlement_id),
            'name_exact': fields.get('name_exact'), 'type_exact': fields.get('type_exact'),
            'region_exact': fields.get('region_exact'), 'district_exact': fields.get('district_exact'),
            'district_available': fields.get('district_available'),
            'independent_exact_anchor_multiplicity': exact_anchor_counts.get((norm(target.settlement_name), norm(target.settlement_type), region_key(target.region_raw), admin_norm(target.district_raw))) if target is not None else None,
            'independent_region_name_type_anchor_multiplicity': region_anchor_counts.get((norm(target.settlement_name), norm(target.settlement_type), region_key(target.region_raw))) if target is not None else None,
            'population_scope_metadata_unknown_no_global_veto': scope_unknown,
            'from_population': old.get('population') if old is not None else None,
            'to_population': anchor.get('population') if anchor is not None else None,
            'from_population_quality': old.get('population_value_quality') if old is not None else None,
            'to_population_quality': anchor.get('population_value_quality') if anchor is not None else None,
            'from_entity_grain_status': old.get('entity_grain_status') if old is not None else None,
            'to_entity_grain_status': anchor.get('entity_grain_status') if anchor is not None else None,
            'to_current_latitude': anchor.get('latitude') if anchor is not None else None,
            'to_current_longitude': anchor.get('longitude') if anchor is not None else None,
            'to_current_coordinate_source': anchor.get('coordinate_source') if anchor is not None else None,
            'to_current_coordinate_quality': anchor.get('coordinate_quality') if anchor is not None else None,
            'from_source_file': old.get('source_file') if old is not None else None,
            'from_source_sheet': old.get('source_sheet') if old is not None else None,
            'from_source_row': old.get('source_row') if old is not None else None,
            'from_source_locator': old.get('source_locator') if old is not None else None,
            'from_source_sha256': old.get('source_sha256') if old is not None else None,
            'hold_reasons_json': json.dumps(reason_set, ensure_ascii=False),
            'continuity_claim': 'inferred stable continuity under ordinary-place assumption; not independently proven historical continuity',
        }
        output.append(row)
        if reason_set:
            holds.append(row)

    edges = pd.DataFrame(output)
    # Validate the proposed additions against the existing accepted graph using
    # a year-constrained union-find. Existing edges are carried as-is; proposals
    # that are already implied by that graph are retained as such and do not claim
    # incremental coverage.
    parent, years, members = {}, {}, {}
    def find(x):
        if x not in parent:
            parent[x] = x
            years[x] = {int(year_by_id[x])} if x in year_by_id else set()
            members[x] = {x}
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        rx, ry = find(x), find(y)
        if rx == ry: return 'already_connected'
        if years[rx] & years[ry]: return 'multiple_same_year_conflict'
        if len(members[rx]) < len(members[ry]): rx, ry = ry, rx
        parent[ry] = rx
        years[rx] |= years.pop(ry)
        members[rx] |= members.pop(ry)
        return 'added'
    year_by_id = dict(zip(selected.source_record_id.astype(str), selected.census_year.astype(int)))
    base = con_edges = None
    # Re-open a lightweight DuckDB handle after source reads have completed.
    base_db = duckdb.connect(str(DB), read_only=True)
    base = base_db.execute(f"SELECT from_source_record_id, to_source_record_id, decision_status FROM read_parquet('{F}/accepted_identity_edges.parquet')").fetchdf()
    base_db.close()
    base_edges_loaded = 0
    for q in base.itertuples():
        # Every row in this pinned file is an accepted identity decision. The
        # file uses multiple explicit accepted decision_status labels.
        a, b = text(q.from_source_record_id), text(q.to_source_record_id)
        if a and b and a in year_by_id and b in year_by_id:
            union(a, b)
            base_edges_loaded += 1
    graph_status = [''] * len(edges)
    decision_status = edges.decision_status.tolist()
    decision_class = edges.decision_class.tolist()
    hold_reasons = edges.hold_reasons_json.tolist()
    base_edge_count_col = [base_edges_loaded] * len(edges)
    candidate_mask = edges.decision_status.eq('staged_accepted_stable_ordinary_place_inference')
    # Fixed order: year then descending independent evidence (crosswalk match
    # score) then ID. Decisions are deterministic and do not use population.
    candidates_sorted = edges.loc[candidate_mask].sort_values(['from_year','legacy_match_score','from_source_record_id'], ascending=[True,False,True], na_position='last')
    for row in candidates_sorted.itertuples():
        outcome = union(str(row.from_source_record_id), str(row.to_source_record_id))
        i = int(row.Index)
        graph_status[i] = outcome
        if outcome == 'multiple_same_year_conflict':
            decision_status[i] = 'held_for_review'
            decision_class[i] = 'legacy_crosswalk_pointer_candidate_only'
            hold_reasons[i] = '["multiple_same_year_conflict_with_accepted_graph"]'
        elif outcome == 'already_connected':
            decision_status[i] = 'already_connected_by_existing_accepted_graph'
            decision_class[i] = 'redundant_temporal_evidence'
    edges['graph_add_status'] = graph_status
    edges['base_graph_edge_count'] = base_edge_count_col
    edges['decision_status'] = decision_status
    edges['decision_class'] = decision_class
    edges['hold_reasons_json'] = hold_reasons
    accepted = edges[edges.decision_status.eq('staged_accepted_stable_ordinary_place_inference')].copy()
    held = edges[edges.decision_status.eq('held_for_review')].copy()
    edges = edges.drop(columns=[], errors='ignore')
    edges.to_csv(OUT / 'legacy_temporal_edges_and_holds.csv', index=False)
    edges[edges.decision_status.eq('staged_accepted_stable_ordinary_place_inference')].to_csv(OUT / 'staged_accepted_edges.csv', index=False)
    edges[edges.decision_status.eq('held_for_review')].to_csv(OUT / 'candidate_holds.csv', index=False)

    # Fixed stratified PPS review sample from staged accepted edges. Allocate up
    # to 400 per year by region; PPS weights are abs(source population), with a
    # unit floor for missing/zero population. Replacement sampling is avoided.
    rng = random.Random(SEED)
    sample_rows = []
    for year, group in edges[edges.decision_status.eq('staged_accepted_stable_ordinary_place_inference')].groupby('from_year'):
        # Include source region and point evidence from linked current anchor.
        group = group.copy()
        target_region = []
        point = []
        for row in group.itertuples():
            a = sel21.loc[row.to_source_record_id]
            target_region.append(region_key(a.region_raw))
            point.append(bool(pd.notna(a.latitude) and pd.notna(a.longitude)))
        group['review_stratum'] = target_region
        group['current_anchor_point_available'] = point
        strata = list(group.groupby('review_stratum'))
        allocations = {k: max(1, round(400 * len(g) / len(group))) for k,g in strata}
        # Correct rounding, preserving one per stratum when the strata count is modest.
        while sum(allocations.values()) > min(400, len(group)):
            k = max((x for x in allocations if allocations[x] > 1), key=lambda x: allocations[x], default=None)
            if k is None: break
            allocations[k] -= 1
        while sum(allocations.values()) < min(400, len(group)):
            k = max(strata, key=lambda x: len(x[1]) - allocations[x[0]])[0]
            allocations[k] += 1
        for stratum, sg in strata:
            n = min(allocations[stratum], len(sg))
            weights = [max(1.0, abs(float(x))) if pd.notna(x) else 1.0 for x in sg.from_population]
            chosen = set()
            population = list(range(len(sg)))
            while len(chosen) < n:
                indexes = [i for i in population if i not in chosen]
                iw = [weights[i] for i in indexes]
                ix = rng.choices(indexes, weights=iw, k=1)[0]
                chosen.add(ix)
            for i in sorted(chosen):
                x = sg.iloc[i].to_dict()
                x['sample_seed'] = SEED
                x['sample_design'] = 'region_stratified_PPS_without_replacement_size_abs_population_floor_1'
                x['stratum_population'] = len(sg)
                x['stratum_sample_n'] = n
                x['pps_size_measure'] = max(1.0, abs(float(x['from_population']))) if pd.notna(x['from_population']) else 1.0
                sample_rows.append(x)
    pd.DataFrame(sample_rows).to_csv(OUT / 'fixed_stratified_pps_review_sample.csv', index=False)

    # Measure annual incremental temporal and population reach from this stage.
    # Joint potential means historical population is present and its exact linked
    # current anchor has a selected point; it is potential, not point admission.
    metrics = []
    for year in [2002, 2010]:
        all_y = selected[selected.census_year.eq(year)]
        stage_y = accepted[accepted.from_year.eq(year)]
        target_ids = set(stage_y.to_source_record_id)
        pts = {x for x in target_ids if x in sel21.index and pd.notna(sel21.loc[x].latitude) and pd.notna(sel21.loc[x].longitude)}
        source_ids = set(stage_y.from_source_record_id)
        source_point_ids = set(stage_y.loc[stage_y.to_source_record_id.isin(pts), 'from_source_record_id'])
        gain = all_y[all_y.source_record_id.isin(source_ids)]
        base_edges = con_none = None
        metrics.append({
            'year': year,
            'selected_population_rows': int(len(all_y)),
            'selected_population_nonnull_rows': int(all_y.population.notna().sum()),
            'accepted_temporal_edge_count': int(len(stage_y)),
            'accepted_historical_source_rows': int(len(source_ids)),
            'historical_population_nonnull_rows_gained': int(gain.population.notna().sum()),
            'historical_population_sum_gained_raw': float(gain.population.fillna(0).sum()),
            'unique_2021_anchor_entities': int(len(target_ids)),
            'unique_2021_anchors_with_selected_points': int(len(pts)),
            'joint_population_and_current_point_potential_rows': int(gain.loc[gain.population.notna() & gain.source_record_id.isin(source_point_ids), 'source_record_id'].nunique()),
            'joint_population_and_current_point_potential_population_raw': float(gain.loc[gain.population.notna() & gain.source_record_id.isin(source_point_ids), 'population'].sum()),
            'legacy_population_scope_unknown_rows_not_vetoed': int(stage_y.population_scope_metadata_unknown_no_global_veto.sum()),
        })
    pd.DataFrame(metrics).to_csv(OUT / 'yearly_joint_potential_gains.csv', index=False)
    reasons = Counter()
    for r in held.itertuples():
        reasons.update(json.loads(r.hold_reasons_json))
    receipt = {
        'stage': 'legacy_temporal_mass_stage_20261004',
        'legacy_database': {'path': str(DB), 'sha256': DB_SHA, 'verified': True},
        'selected_release': str(F),
        'stage_script_sha256': sha(Path(__file__)),
        'selected_observations_sha256': sha(F / 'selected_observations.parquet'),
        'accepted_publication_bindings_sha256': sha(F / 'accepted_publication_bindings.parquet'),
        'rule': 'inherited legacy group and exact linked 2021 source row are candidate generation only; stage accepts only unique preferred additive ordinary source rows with exact independently checked name/type/region and matching available district; this is an explicit stable-place continuity inference',
        'population_scope_policy': 'optional scope absence is recorded, not a global identity veto; no population value is imputed or allocated',
        'counts': {'candidate_edges': int(len(edges)), 'staged_accepted_edges': int(edges.decision_status.eq('staged_accepted_stable_ordinary_place_inference').sum()), 'already_connected': int(edges.decision_status.eq('already_connected_by_existing_accepted_graph').sum()), 'held': int(edges.decision_status.eq('held_for_review').sum()), 'fixed_sample_rows': int(len(sample_rows)), 'base_accepted_graph_edges_loaded': int(base_edges_loaded)},
        'hold_reasons': dict(reasons),
        'seed': SEED,
        'outputs': {},
        'limitations': ['accepted edges encode inferred stable continuity and need root graph checks before integration', 'historical point availability in the gain table is potential reuse from the linked 2021 anchor and is not point admission', 'known successor and name/type transition cases are held for the parallel continuation/rename review', 'no source populations are changed'],
    }
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != 'stage_receipt.json':
            receipt['outputs'][p.name] = {'sha256': sha(p), 'bytes': p.stat().st_size}
    (OUT / 'stage_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'counts': receipt['counts'], 'hold_reasons': dict(reasons), 'yearly_gain': metrics}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
