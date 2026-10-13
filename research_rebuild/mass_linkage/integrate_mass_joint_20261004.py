"""Build an auditable dry-run joint identity/point-use application.

Frozen release files are inputs only. New identity and point decisions remain
pending unless an explicit review receipt is supplied for identities. The
working application is a diagnostic scenario, not an admitted or published
release. Point reuse records preserve their original source and decision path;
they assert neither native identifier binding nor boundary comparability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from research_rebuild.mass_linkage.coverage import identity_sets


FROZEN = Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
STAGE = Path('/workspace/settlements-work/continuation_20261004')
DEFAULT_OUT = STAGE / 'root' / 'R4' / 'working_application'
ACCEPTED_EDGE_STATUSES = {
    'checked_rule_accepted', 'checked_rule_accepted_redundant_graph_connectivity_effect',
    'accepted_rule_family_after_independent_sample_review', 'case_specific_independent_review_accepted',
    'case_review_accepted', 'independent_case_review_accepted', 'accepted_case_specific',
}
ACCEPTED_POINT_STATUSES = {
    'reviewed_rule_accepted', 'frozen_r5b_reviewed_baseline_preserved',
    'reviewed_extension_rule_accepted', 'reviewed_case_accepted',
}
CONTROLS = {2002: 145166731, 2010: 142856536, 2021: 147182123}
PINNED = {
    'selected_observations.parquet': '4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657',
    'source_evidence.parquet': 'e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327',
    'accepted_identity_edges.parquet': 'e9f402c2bda189561d56a4adcee5ecd2fa4d5ed52610b45011eab9f8bc14f075',
    'accepted_point_uses.parquet': 'a2087db421629ea66fe8c32de05b0aa68a3fff3c6ff3c7deb1cbcd1f286f3ae8',
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def safe_bool(x: Any) -> bool:
    if x is None or pd.isna(x): return False
    if isinstance(x, str): return x.strip().casefold() in {'true', '1', 'yes', 'да'}
    return bool(x)


def txt(x: Any) -> str:
    return '' if x is None or pd.isna(x) else str(x).strip()


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371.0088*2*math.asin(min(1.0,math.sqrt(a)))


def parse_ids(path: Path) -> set[str]:
    data = json.loads(path.read_text())
    return set(map(str, data.get('blocked_target_source_record_ids', [])))


class YearUF:
    def __init__(self, year_by_id: dict[str, int]):
        self.parent: dict[str, str] = {}
        self.size: dict[str, int] = {}
        self.years: dict[str, set[int]] = {}
        self.year_by_id = year_by_id

    def find(self, x: str) -> str:
        if x not in self.parent:
            self.parent[x] = x
            self.size[x] = 1
            self.years[x] = {self.year_by_id[x]} if x in self.year_by_id else set()
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def add(self, a: str, b: str) -> str:
        if a == b: return 'identical_endpoint'
        if a not in self.year_by_id or b not in self.year_by_id: return 'endpoint_absent_from_selected_layer'
        ra, rb = self.find(a), self.find(b)
        if ra == rb: return 'already_connected'
        if self.years[ra] & self.years[rb]: return 'blocked_same_year_component_collision'
        if self.size[ra] < self.size[rb]: ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size.pop(rb)
        self.years[ra] |= self.years.pop(rb)
        return 'added'


def input_hashes(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    out = {}
    for label, p in paths.items():
        if not p.is_file(): raise FileNotFoundError(f'{label} missing: {p}')
        out[label] = {'path': str(p), 'sha256': sha(p), 'bytes': p.stat().st_size}
    return out


def validate_review_artifacts(paths: dict[str, Path]) -> tuple[dict, dict]:
    hrec = json.loads(paths['historical_review_receipt'].read_text())
    wrec = json.loads(paths['wikidata_review_receipt'].read_text())
    if hrec.get('status') != 'bounded_independent_review_historical_bridge_complete':
        raise ValueError('historical independent review receipt status is not complete')
    if hrec.get('inputs', {}).get('selected_observations_sha256') != PINNED['selected_observations.parquet']:
        raise ValueError('historical review selected-release hash does not match frozen selected layer')
    if hrec.get('outputs_sha256', {}).get(paths['historical_eligible'].name) != sha(paths['historical_eligible']):
        raise ValueError('historical eligible list hash does not match review receipt')
    if hrec.get('cohort', {}).get('eligible_independent_point_uses') != 1013:
        raise ValueError('historical independent-review eligible count changed')
    if wrec.get('status') != 'bounded_independent_review_wikidata_complete':
        raise ValueError('Wikidata independent review receipt status is not complete')
    if wrec.get('input_hashes', {}).get('frozen_selected_sha256') != PINNED['selected_observations.parquet']:
        raise ValueError('Wikidata review selected-release hash does not match frozen selected layer')
    if wrec.get('outputs_sha256', {}).get(paths['wikidata_eligible'].name) != sha(paths['wikidata_eligible']):
        raise ValueError('Wikidata eligible list hash does not match review receipt')
    if wrec.get('decision', {}).get('eligible_point_uses') != 12800:
        raise ValueError('Wikidata independent-review eligible count changed')
    return hrec, wrec


def reviewed_identity_pairs(receipt_path: Path | None) -> tuple[set[tuple[str, str, str]], dict | None]:
    if receipt_path is None: return set(), None
    receipt = json.loads(receipt_path.read_text())
    csv_rel = receipt.get('accepted_edges_csv')
    if not csv_rel: raise ValueError('identity review receipt must pin accepted_edges_csv')
    csv_path = Path(csv_rel)
    if not csv_path.is_absolute(): csv_path = receipt_path.parent / csv_path
    expected = receipt.get('accepted_edges_sha256')
    if not expected or sha(csv_path) != expected: raise ValueError('identity review edge list hash mismatch')
    tbl = pd.read_csv(csv_path)
    rulecol='rule_family' if 'rule_family' in tbl else ('decision_class' if 'decision_class' in tbl else None)
    required={'from_source_record_id','to_source_record_id','review_status'}
    if not required.issubset(tbl.columns) or rulecol is None: raise ValueError(f'identity review edge list missing endpoints/status/rule')
    good=tbl.review_status.astype(str).str.casefold().isin({'accepted','approved','review_accepted'})
    pairs=set()
    for r in tbl[good].itertuples(index=False):
        pairs.add((str(r.from_source_record_id),str(r.to_source_record_id),str(getattr(r,rulecol))))
    return pairs, {'path': str(receipt_path), 'sha256': sha(receipt_path), 'accepted_pair_rule_count': len(pairs),
                   'accepted_edges_path':str(csv_path),'accepted_edges_sha256':expected}


def load_independent_temporal_review(stage_root: Path, explicit_receipt: Path | None) -> tuple[pd.DataFrame, pd.DataFrame, set[str], dict]:
    folder = stage_root / 'independent_review'
    receipt_path = explicit_receipt or folder / 'temporal_independent_review_receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('status') != 'independent_rule_review_pre_final_graph_DFS':
        raise ValueError('temporal independent review receipt is missing or has unexpected status')
    mass_path = folder / 'temporal_mass_eligible_edges_pre_DFS.csv'
    legacy_path = folder / 'legacy_temporal_eligible_edges.csv'
    if sha(mass_path) != receipt['temporal_mass']['eligible_edge_list_sha256']:
        raise ValueError('temporal mass independently eligible list checksum mismatch')
    if sha(legacy_path) != receipt['legacy_temporal']['eligible_edge_list_sha256']:
        raise ValueError('legacy temporal independently eligible list checksum mismatch')
    mass = pd.read_csv(mass_path)
    legacy = pd.read_csv(legacy_path)
    if len(mass) != int(receipt['temporal_mass']['independently_rule_eligible_pre_DFS']):
        raise ValueError('temporal mass independently eligible row count mismatch')
    if len(legacy) != int(receipt['legacy_temporal']['independently_eligible_edges']):
        raise ValueError('legacy temporal independently eligible row count mismatch')
    metadata = {'path': str(receipt_path), 'sha256': sha(receipt_path),
        'mass_edges_path': str(mass_path), 'mass_edges_sha256': sha(mass_path), 'mass_edges': len(mass),
        'legacy_edges_path': str(legacy_path), 'legacy_edges_sha256': sha(legacy_path), 'legacy_edges': len(legacy),
        'approval_scope': 'independently eligible before the root merged-graph DFS; accepted status is assigned only after this script verifies the full graph'}
    return mass, legacy, metadata


def build(args) -> dict:
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f'working application output is nonempty: {out}; choose a new --output')
    out.mkdir(parents=True, exist_ok=True)
    F, S = args.frozen, args.stage
    paths = {
        'selected': F / 'selected_observations.parquet',
        'source_evidence': F / 'source_evidence.parquet',
        'base_edges': F / 'accepted_identity_edges.parquet',
        'base_point_uses': F / 'accepted_point_uses.parquet',
        'temporal_review_receipt': S / 'independent_review' / 'temporal_independent_review_receipt.json',
        'temporal_mass_review_edges': S / 'independent_review' / 'temporal_mass_eligible_edges_pre_DFS.csv',
        'legacy_review_edges': S / 'independent_review' / 'legacy_temporal_eligible_edges.csv',
        'historical_eligible': S / 'independent_review' / 'historical_bridge_eligible_point_uses.csv',
        'historical_review_receipt': S / 'independent_review' / 'historical_bridge_independent_receipt.json',
        'wikidata_eligible': S / 'independent_review' / 'wikidata_review_eligible_point_uses_final.csv',
        'wikidata_review_receipt': S / 'independent_review' / 'wikidata_review_receipt_final.json',
        'quarantine': Path('/workspace/settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json'),
        'federal_chains': S / 'federal_application' / 'accepted_typed_city_continuity.parquet',
        'federal_points': S / 'federal_application' / 'accepted_territory_reference_points.parquet',
        'federal_receipt': S / 'federal_application' / 'receipt.json',
        'coverage_policy': F / 'coverage_policy.json',
    }
    hashes = input_hashes(paths)
    for label in ('selected','source_evidence','base_edges','base_point_uses'):
        if hashes[label]['sha256'] != PINNED[paths[label].name]:
            raise ValueError(f'frozen input hash mismatch: {label}')
    hrec, wrec = validate_review_artifacts(paths)
    mass_review, legacy_review, review_metadata = load_independent_temporal_review(S, args.identity_review_receipt)
    reviewed_pairs, identity_receipt_metadata = reviewed_identity_pairs(args.identity_review_receipt)
    historical_review_sha=sha(paths['historical_review_receipt'])
    wikidata_review_sha=sha(paths['wikidata_review_receipt'])
    historical_eligible_sha=sha(paths['historical_eligible'])
    wikidata_eligible_sha=sha(paths['wikidata_eligible'])
    identity_receipt_sha=identity_receipt_metadata['sha256'] if identity_receipt_metadata else None
    if json.loads(paths['federal_receipt'].read_text())['outputs']['accepted_typed_city_continuity.parquet'] != hashes['federal_chains']['sha256']:
        raise ValueError('typed federal city continuity hash mismatch')
    if json.loads(paths['federal_receipt'].read_text())['outputs']['accepted_territory_reference_points.parquet'] != hashes['federal_points']['sha256']:
        raise ValueError('federal territory reference point hash mismatch')
    quarantine_ids = parse_ids(paths['quarantine'])
    wd_holds = set(map(str, wrec['decision'].get('hard_geo_point_choice_hold_ids', [])))

    # Compact selected source layer and exact JSON-authoritative grain evidence.
    con = duckdb.connect()
    selected = con.execute(f"""
        SELECT source_record_id, census_year, population, population_scope,
               population_value_quality, settlement_name, settlement_type,
               region_raw, district_raw, source_file, source_sha256, source_locator,
               latitude, longitude
        FROM read_parquet('{paths['selected']}')
    """).fetchdf()
    if selected.source_record_id.isna().any() or not selected.source_record_id.is_unique:
        raise ValueError('selected source IDs must be unique and complete')
    if set(selected.census_year.astype(int)) != {2002, 2010, 2021}:
        raise ValueError('selected layer census-year scope changed')
    ids_df = pd.DataFrame({'source_record_id': selected.source_record_id.astype(str).unique()})
    con.register('needed_source_ids', ids_df)
    flags_df = con.execute(f"""
        SELECT e.source_record_id,
          lower(coalesce(json_extract_string(e.source_evidence_json, '$.is_federal_aggregate'), 'false'))='true' AS is_federal_aggregate,
          lower(coalesce(json_extract_string(e.source_evidence_json, '$.legacy_identity_conflict'), 'false'))='true' AS legacy_identity_conflict,
          lower(coalesce(json_extract_string(e.source_evidence_json, '$.legacy_same_year_collision'), 'false'))='true' AS legacy_same_year_collision,
          nullif(json_extract_string(e.source_evidence_json, '$.legacy_verified_successor_settlement_id'), '') AS verified_successor_id,
          e.source_evidence_json
        FROM read_parquet('{paths['source_evidence']}') e
        JOIN needed_source_ids n USING(source_record_id)
    """).fetchdf()
    if len(flags_df) != len(selected):
        raise ValueError('authoritative source_evidence does not match selected source ID set')
    flag_by_id = flags_df.set_index('source_record_id').to_dict('index')
    aggregate_ids = set(flags_df.loc[flags_df.is_federal_aggregate, 'source_record_id'].astype(str))
    year_by_id = dict(zip(selected.source_record_id.astype(str), selected.census_year.astype(int)))

    # Full prior admitted graph; preserve its canonical statuses and optional fields.
    base = con.execute(f"SELECT * FROM read_parquet('{paths['base_edges']}')").fetchdf()
    if len(base) != 177707 or base.decision_status.isna().any() or not base.decision_status.isin(ACCEPTED_EDGE_STATUSES).all():
        raise ValueError('frozen accepted graph row count or canonical statuses changed')
    dsu = YearUF(year_by_id)
    base_min = base[['decision_id','from_source_record_id','to_source_record_id']].fillna('')
    for row in base_min.itertuples(index=False, name=None):
        decision_id, a, b = map(str, row)
        result = dsu.add(a, b)
        if result not in {'added','already_connected'}:
            raise ValueError(f'frozen base graph violates year constrained union-find: {decision_id}:{result}')
    base_rows = base.to_dict('records')

    # Candidate temporal identity rows. Stage order is temporal_mass first,
    # then legacy crosswalk. Relation-only legacy conflict is diagnostic; the
    # independently checked candidate family and same-year UF resolve it.
    mass = mass_review
    legacy = legacy_review
    candidate_edges = []
    edge_diag = []
    family_priority = {'R_A_accepted_2002_2010_alias_plus_unique_2021_signature':0,
                       'R_D_explicit_parenthetical_preserves_prior_name_2002_2010':1,
                       'R_D_explicit_parenthetical_future_alias_2010_2021':1,
                       'R_B_unique_exact_signature_stable_context_2002_2010':2,
                       'R_B_unique_exact_signature_stable_context_2010_2021':2,
                       'R_F_unique_legacy_RU_OKTMO_id_plus_region_and_name_or_point_2010_2021':3,
                       'R_C_unique_name_region_type_transition_with_admin_or_pointer_or_close_point_2010_2021':4}
    work = []
    for i,r in mass.iterrows():
        did = 'mass-temporal-' + hashlib.sha256((str(r.rule_family)+'|'+str(r.from_source_record_id)+'|'+str(r.to_source_record_id)).encode()).hexdigest()[:20]
        work.append((0, family_priority.get(txt(r.rule_family), 9), int(r.from_year), did, 'temporal_mass', r))
    for i,r in legacy.iterrows():
        did = txt(r.decision_id)
        work.append((1, 0, int(r.from_year), did, 'legacy_temporal', r))
    work.sort(key=lambda z:(z[0],z[1],z[2],z[3]))
    for _,_,_,did,source,r in work:
        a,b = txt(r.from_source_record_id),txt(r.to_source_record_id)
        y1,y2=int(r.from_year),int(r.to_year)
        reason=[]
        if a not in year_by_id or b not in year_by_id: reason.append('endpoint_absent_from_selected_layer')
        elif year_by_id[a] != y1 or year_by_id[b] != y2: reason.append('endpoint_year_metadata_mismatch')
        if source == 'temporal_mass':
            if not safe_bool(r.graph_safe_under_existing_plus_higher_priority_staged_edges): reason.append('upstream_graph_safe_flag_false')
            rule = txt(r.rule_family)
            rule_evidence = txt(r.rule_support_json)
        else:
            if txt(r.decision_status) != 'staged_accepted_stable_ordinary_place_inference': reason.append('legacy_edge_not_staged_accepted')
            if not safe_bool(r.legacy_additive_source_grain): reason.append('legacy_source_grain_not_additive')
            rule = txt(r.decision_class)
            rule_evidence = txt(r.decision_rule)
        endpoint_flags=[flag_by_id.get(x,{}) for x in (a,b)]
        if any(safe_bool(x.get('is_federal_aggregate')) for x in endpoint_flags): reason.append('authoritative_source_evidence_federal_aggregate_endpoint')
        if any(safe_bool(x.get('legacy_same_year_collision')) for x in endpoint_flags): reason.append('authoritative_source_evidence_same_year_collision')
        if any(txt(x.get('verified_successor_id')) for x in endpoint_flags): reason.append('authoritative_source_evidence_verified_successor_event')
        legacy_conflict_warning=any(safe_bool(x.get('legacy_identity_conflict')) for x in endpoint_flags)
        status='candidate_pending_independent_identity_review'
        graph_result='not_attempted'
        if not reason:
            graph_result=dsu.add(a,b)
            if graph_result == 'blocked_same_year_component_collision': reason.append(graph_result)
            elif graph_result == 'endpoint_absent_from_selected_layer': reason.append(graph_result)
            elif graph_result == 'identical_endpoint': reason.append(graph_result)
            elif graph_result == 'already_connected': status='candidate_redundant_existing_or_prior_graph'
        approved = (a,b,rule) in reviewed_pairs or (b,a,rule) in reviewed_pairs
        if approved and not reason:
            status='checked_rule_accepted' if graph_result == 'added' else 'checked_rule_accepted_redundant_graph_connectivity_effect'
        elif reason:
            status='held_in_dry_run'
        elif graph_result == 'added':
            status='candidate_added_to_dry_run_graph_pending_review'
        candidate = {
            'decision_id':did,'relation':'same_place','from_source_record_id':a,'from_year':str(y1),
            'to_source_record_id':b,'to_year':str(y2),'decision_class':rule,
            'decision_status':status,'decision_rule':rule_evidence,'reviewer':'', 'reviewed_at':'',
            'evidence_uri':'','evidence_sha256':'','population_scope_interpretation':'not_asserted',
            'selection_projection_status':'active_endpoints_selected' if not reason else 'candidate_hold',
            'candidate_only':status.startswith('candidate_') or status=='held_in_dry_run',
            'admission_status':status,'integration_source':source,'integration_rule_family':rule,
            'integration_graph_result':graph_result,'integration_hold_reasons_json':json.dumps(sorted(set(reason)),ensure_ascii=False),
            'legacy_identity_conflict_warning_not_global_veto':legacy_conflict_warning,
            'source_evidence_federal_aggregate_endpoint':any(safe_bool(x.get('is_federal_aggregate')) for x in endpoint_flags),
            'source_evidence_same_year_collision_endpoint':any(safe_bool(x.get('legacy_same_year_collision')) for x in endpoint_flags),
            'source_evidence_verified_successor_event_endpoint':any(txt(x.get('verified_successor_id')) for x in endpoint_flags),
            'boundary_comparability_asserted':False,'coordinate_admitted':False,
            'identity_review_receipt_sha256':identity_receipt_sha if approved else None,
        }
        # Keep source-specific raw support outside canonical interpretation fields.
        candidate['candidate_rule_support_json']=rule_evidence
        edge_diag.append(candidate)
        if not reason and graph_result in {'added','already_connected'}:
            # Keep old edge schema intact in base rows; candidate row adds fields
            # by name and remains pending unless the receipt identifies it.
            candidate_edges.append(candidate)
    edge_diag_df=pd.DataFrame(edge_diag)
    edge_diag_df.to_csv(out/'identity_edge_diagnostics.csv',index=False)

    # Build the scenario graph: all graph-safe additions for potential metrics;
    # reviewed additions form a separate accepted-only scenario.
    candidate_graph_df=edge_diag_df[edge_diag_df.integration_graph_result.isin(['added','already_connected'])].copy()
    candidate_graph_edges=candidate_graph_df[['from_source_record_id','to_source_record_id']].copy()
    base_edge_slim=base[['from_source_record_id','to_source_record_id']].copy()
    scenario_edge_slim=pd.concat([base_edge_slim,candidate_graph_edges],ignore_index=True)
    accepted_review_df=edge_diag_df[edge_diag_df.decision_status.str.startswith('checked_rule_')]
    admitted_edge_slim=pd.concat([base_edge_slim,accepted_review_df[['from_source_record_id','to_source_record_id']]],ignore_index=True)
    # Independent DFS is the final check for all ordinary identity scenarios.
    base_linked,base_full,base_components=identity_sets(selected[['source_record_id','census_year']],base_edge_slim)
    scenario_linked,scenario_full,scenario_components=identity_sets(selected[['source_record_id','census_year']],scenario_edge_slim)
    admitted_linked,admitted_full,admitted_components=identity_sets(selected[['source_record_id','census_year']],admitted_edge_slim)

    # Aggregate membership comes only from exact JSON evidence. No ordinary
    # candidate edge or settlement point is admitted for these rows.
    base_points=con.execute(f"""
        SELECT target_source_record_id, target_year, latitude, longitude,
               coordinate_source, coordinate_source_record_id, coordinate_provider,
               coordinate_provider_id, coordinate_provenance, admission_rule,
               coordinate_admission_status, coordinate_source_file,
               coordinate_source_sha256, coordinate_source_locator,
               source_file, source_sha256, source_locator, point_origin_kind,
               point_origin_file, point_origin_sha256, point_origin_locator,
               inference_coordinate_origin_carrier_target_source_record_id,
               supporting_carrier_source_record_id, native_id_binding_asserted,
               boundary_comparability_asserted
        FROM read_parquet('{paths['base_point_uses']}')
        WHERE coordinate_admission_status IN {tuple(ACCEPTED_POINT_STATUSES)}
    """).fetchdf()
    if base_points.target_source_record_id.duplicated().any():
        raise ValueError('frozen admitted point uses have multiple rows per target')
    baseline_point_ids=set(base_points.target_source_record_id.astype(str))
    # Read eligibility lists only after their independent-review receipts and hashes pass.
    hist=pd.read_csv(paths['historical_eligible'])
    wd=pd.read_csv(paths['wikidata_eligible'])
    historical_origins=con.execute(f"SELECT target_source_record_id,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind FROM read_parquet('{S / 'historical_points' / 'staged_point_uses.parquet'}')").fetchdf().set_index('target_source_record_id')
    wd_ledger=pd.read_csv(S / 'wikidata_points' / 'wikidata_primary_staged_ledger.csv')
    wd_ledger=wd_ledger.set_index('source_record_id')
    wd_raw_hash_cache={}
    if hist.target_source_record_id.duplicated().any() or wd.source_record_id.duplicated().any():
        raise ValueError('review-eligible point lists have duplicate targets')
    point_candidates=[]
    point_diag=[]
    for r in hist.itertuples(index=False):
        target=txt(r.target_source_record_id); lat=float(r.latitude);lon=float(r.longitude)
        point_candidates.append({'target_source_record_id':target,'target_year':int(r.target_year),'latitude':lat,'longitude':lon,
            'coordinate_source':'raw named typed GeoKLADR 2011 representative point','coordinate_source_record_id':'',
            'coordinate_provider':'GeoKLADR','coordinate_provider_id':'','source_name':txt(r.settlement_name),
            'source_type':txt(r.settlement_type),'source_region':txt(r.region_norm),'source_file':txt(r.selected_source_file),
            'source_sha256':txt(r.selected_source_file_sha256_manifest),'source_locator':txt(r.selected_source_locator),
            'point_origin_file':txt(historical_origins.loc[target].point_origin_file),
            'point_origin_sha256':txt(historical_origins.loc[target].point_origin_sha256),
            'point_origin_locator':txt(historical_origins.loc[target].point_origin_locator),
            'point_origin_kind':txt(historical_origins.loc[target].point_origin_kind),'point_review_receipt_sha256':historical_review_sha,
            'point_review_rule':txt(r.point_date_interpretation)+'; '+txt(r.code_bridge_basis),
            'population_value':int(r.population),'point_candidate_status':'pending_root_application_review'})
    for r in wd.itertuples(index=False):
        target=txt(r.source_record_id);lat=float(r.P625_latitude);lon=float(r.P625_longitude)
        point_candidates.append({'target_source_record_id':target,'target_year':2021,'latitude':lat,'longitude':lon,
            'coordinate_source':'Wikidata P625 representative point','coordinate_source_record_id':txt(r.wikidata_qid),
            'coordinate_provider':'Wikidata','coordinate_provider_id':txt(r.wikidata_qid),
            'source_name':txt(r.current_name),'source_type':txt(r.settlement_type),'source_region':txt(r.current_region),
            'source_file':'wikidata_review_eligible_point_uses_final.csv','source_sha256':wikidata_eligible_sha,
            'source_locator':f"qid={txt(r.wikidata_qid)};P625",'point_origin_file':'','point_origin_sha256':'',
            'point_origin_locator':'',
            'point_origin_kind':'wikidata_P625_point_claim','point_review_receipt_sha256':wikidata_review_sha,
            'point_review_rule':txt(r.independent_review_rule)+'; '+txt(r.point_scope_assumption),
            'population_value':int(r.current_population),'point_candidate_status':'pending_root_application_review'})
        p=point_candidates[-1]
        ledger=wd_ledger.loc[target]
        locator_items=json.loads(txt(ledger.P625_raw_claim_locators_json) or '[]')
        if not locator_items: raise ValueError(f'approved Wikidata point has no raw P625 locator: {target}')
        locator=locator_items[0]
        raw_file=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/txt(locator.get('source_file'))
        p['point_origin_file']=str(raw_file)
        if str(raw_file) not in wd_raw_hash_cache: wd_raw_hash_cache[str(raw_file)]=sha(raw_file)
        p['point_origin_sha256']=wd_raw_hash_cache[str(raw_file)]
        p['point_origin_locator']=json.dumps(locator,ensure_ascii=False,sort_keys=True)
        p['wikidata_ledger_evidence_file']=txt(ledger.evidence_file)
        p['wikidata_ledger_evidence_file_sha256']=txt(ledger.evidence_file_sha256)
    current_points={str(r.target_source_record_id):(float(r.latitude),float(r.longitude)) for r in base_points.itertuples()}
    for p in point_candidates:
        target=p['target_source_record_id']; reasons=[]
        if target not in year_by_id: reasons.append('target_absent_from_selected_layer')
        elif year_by_id[target] != p['target_year']: reasons.append('target_year_mismatch')
        if target in aggregate_ids: reasons.append('authoritative_source_evidence_federal_aggregate')
        if target in quarantine_ids: reasons.append('frozen_target_quarantine_31')
        if target in wd_holds: reasons.append('wikidata_point_choice_hold')
        if target in current_points:
            q=current_points[target]
            if q == (p['latitude'],p['longitude']): p['point_candidate_status']='already_present_identical_frozen_point'
            else: reasons.append('frozen_point_exists_coordinates_differ_preserve_frozen_point')
        p['point_hold_reasons_json']=json.dumps(reasons,ensure_ascii=False)
        if reasons: p['point_candidate_status']='held_in_dry_run'
        point_diag.append(p.copy())
    point_diag_df=pd.DataFrame(point_diag)
    point_diag_df.to_csv(out/'direct_point_use_diagnostics.csv',index=False)
    # Eligible direct point seeds are candidates only when the frozen target
    # does not already have a point and no hard hold applies.
    new_direct=[p for p in point_candidates if p['point_candidate_status']=='pending_root_application_review']

    # Build adjacency from the base graph plus graph-safe candidate additions.
    adjacency=defaultdict(list)
    for r in base[['decision_id','from_source_record_id','to_source_record_id']].itertuples(index=False):
        did=txt(r.decision_id) or 'base-edge-'+hashlib.sha256((txt(r.from_source_record_id)+'|'+txt(r.to_source_record_id)).encode()).hexdigest()[:16]
        a,b=txt(r.from_source_record_id),txt(r.to_source_record_id)
        adjacency[a].append((b,did,False));adjacency[b].append((a,did,False))
    for r in candidate_graph_df.itertuples(index=False):
        a,b=txt(r.from_source_record_id),txt(r.to_source_record_id)
        did=txt(r.decision_id)
        adjacency[a].append((b,did,True));adjacency[b].append((a,did,True))
    all_components=[set(c) for c in scenario_components]
    comp_nodes=set().union(*all_components) if all_components else set()
    all_components.extend([{x} for x in year_by_id if x not in comp_nodes])
    component_point_seeds=[]
    base_point_by_id={str(r.target_source_record_id):r._asdict() for r in base_points.itertuples(index=False)}
    new_direct_by_id={p['target_source_record_id']:p for p in new_direct}
    base_point_rows=list(base_points.itertuples(index=False))
    for ci,members in enumerate(all_components):
        seeds=[]
        for node in members:
            if node in aggregate_ids: continue
            if node in base_point_by_id:
                q=base_point_by_id[node]
                seeds.append({'target_source_record_id':node,'latitude':float(q['latitude']),'longitude':float(q['longitude']),
                    'seed_kind':'frozen_admitted_point_use','seed_priority':0,'coordinate_source':txt(q.get('coordinate_source')),
                    'point_origin_file':txt(q.get('point_origin_file') or q.get('coordinate_source_file')),
                    'point_origin_sha256':txt(q.get('point_origin_sha256') or q.get('coordinate_source_sha256')),
                    'point_origin_locator':txt(q.get('point_origin_locator') or q.get('coordinate_source_locator')),
                    'point_origin_kind':txt(q.get('point_origin_kind')),'point_review_status':'frozen_admitted'})
        if not seeds: continue
        witness=max(seeds,key=lambda s:(int(year_by_id.get(s['target_source_record_id'],0)),str(s['target_source_record_id'])))
        max_distance=max(distance_km(float(witness['latitude']),float(witness['longitude']),float(s['latitude']),float(s['longitude'])) for s in seeds)
        if max_distance>5.0:
            component_point_seeds.append({'component_index':ci,'member_count':len(members),'admitted_seed_count':len(seeds),'max_seed_distance_km':round(max_distance,3),'status':'propagation_held_admitted_point_witnesses_over_5km','witness_seed_target_source_record_id':witness['target_source_record_id'],'target_ids_withheld':sum(1 for x in members if x not in baseline_point_ids and x not in new_direct_by_id)})
            continue
        root=txt(witness['target_source_record_id'])
        # BFS yields explicit source-to-target decision-ID and node paths.
        pred={root:None};q=deque([root])
        while q:
            u=q.popleft()
            for v,did,pending in sorted(adjacency.get(u,[]),key=lambda z:(z[0],z[1])):
                if v not in members or v in pred: continue
                pred[v]=(u,did,pending);q.append(v)
        for target in sorted(members):
            if target in aggregate_ids or target in baseline_point_ids or target in new_direct_by_id or target in quarantine_ids or target in wd_holds or target==root: continue
            if target not in pred: continue
            path_nodes=[target];path_ids=[];uses_pending=False;cur=target
            while cur!=root:
                item=pred[cur]
                if item is None: break
                prev,did,pending=item;path_ids.append(did);uses_pending=uses_pending or bool(pending);cur=prev;path_nodes.append(cur)
            path_ids.reverse();path_nodes.reverse()
            component_point_seeds.append({'target_source_record_id':target,'target_year':year_by_id[target],
                'latitude':witness['latitude'],'longitude':witness['longitude'],
                'coordinate_source':witness.get('coordinate_source','frozen admitted source point'),'coordinate_source_record_id':root,
                'coordinate_provider':'','coordinate_provider_id':'','point_origin_file':witness.get('point_origin_file',''),
                'point_origin_sha256':witness.get('point_origin_sha256',''),'point_origin_locator':witness.get('point_origin_locator',''),
                'point_origin_kind':witness.get('point_origin_kind',''),'supporting_carrier_source_record_id':root,
                'identity_path_source_record_ids_json':json.dumps(path_nodes,ensure_ascii=False),
                'identity_path_decision_ids_json':json.dumps(path_ids,ensure_ascii=False),
                'identity_path_edge_count':len(path_ids),'identity_path_uses_pending_candidate':uses_pending,
                'point_use_status':'pending_identity_review_and_root_point_application_review' if uses_pending or witness.get('seed_priority',0)>0 else 'pending_root_point_application_review',
                'continuity_inference':'Reuse the source point along the listed same-place identity decisions; this is explicit continuity inference, not historical measurement.',
                'native_id_binding_asserted':False,'provider_binding_status':'not_asserted',
                'boundary_comparability_asserted':False,'population_scope_comparability_asserted':False,
                'coordinate_admitted':False,'point_admitted':False})
    propagated=[x for x in component_point_seeds if 'target_source_record_id' in x]
    prop_df=pd.DataFrame(propagated)
    prop_df.to_csv(out/'propagated_point_use_candidates.csv',index=False)
    pd.DataFrame([x for x in component_point_seeds if 'target_source_record_id' not in x]).to_csv(out/'point_propagation_component_holds.csv',index=False)

    # Federally scoped territory chains are kept in a separate typed ledger and
    # never enter ordinary NP point propagation or ordinary settlement metrics.
    fed=con.execute(f"SELECT * FROM read_parquet('{paths['federal_chains']}')").fetchdf()
    fed_rows=[]
    for r in fed.itertuples(index=False):
        ids=json.loads(r.source_record_ids_json)
        if len(ids)<2: continue
        for i,(a,b) in enumerate(zip(ids,ids[1:])):
            fed_rows.append({'decision_id':f'{r.chain_id}:{i+1}','chain_id':r.chain_id,'city':r.city,
                'from_source_record_id':a,'from_year':year_by_id.get(a),'to_source_record_id':b,'to_year':year_by_id.get(b),
                'relation':r.relation_type,
                'decision_status':r.decision_status,
                'atomic_same_place_edge':safe_bool(r.atomic_same_place_edge),'population_scope_comparability':r.population_scope_comparability,
                'territory_point_reuse':r.territory_point_reuse,'ordinary_settlement_point_use_allowed':False,
                'source_json_aggregate_flags':[safe_bool(flag_by_id.get(a,{}).get('is_federal_aggregate')),safe_bool(flag_by_id.get(b,{}).get('is_federal_aggregate'))]})
    fed_df=pd.DataFrame(fed_rows)
    fed_df.to_csv(out/'federal_territory_chain_candidates.csv',index=False)
    con.execute(f"COPY (SELECT * FROM read_parquet('{paths['federal_chains']}')) TO '{out / 'federal_typed_city_continuity.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.execute(f"COPY (SELECT * FROM read_parquet('{paths['federal_points']}')) TO '{out / 'federal_territory_reference_points.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    # Materialize a merged review table with every frozen edge retained verbatim
    # and only graph-safe candidates appended by column name.
    merged_rows=[]
    for r in candidate_graph_df.to_dict('records'):
        merged_rows.append(r)
    candidate_frame=pd.DataFrame(merged_rows)
    con.register('candidate_edges_frame',candidate_frame)
    con.execute(f"""
        COPY (
          SELECT *, 'existing_frozen_accepted'::VARCHAR AS integration_layer,
                     'accepted_frozen'::VARCHAR AS integration_review_status
          FROM read_parquet('{paths['base_edges']}')
          UNION ALL BY NAME
          SELECT *, 'new_identity_candidate'::VARCHAR AS integration_layer,
                     CASE WHEN decision_status LIKE 'checked_rule_accepted%' THEN 'accepted_by_identity_review_receipt'
                          ELSE 'pending_identity_review' END::VARCHAR AS integration_review_status
          FROM candidate_edges_frame
        ) TO '{out / 'merged_identity_edges.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    # Materialize direct and propagated point-use proposals while retaining all
    # existing point-use rows and optional fields unchanged.
    direct_new=[p for p in point_candidates if p['point_candidate_status']=='pending_root_application_review']
    direct_rows=[]
    for p in direct_new:
        direct_rows.append({'target_source_record_id':p['target_source_record_id'],'target_year':p['target_year'],
            'latitude':p['latitude'],'longitude':p['longitude'],'coordinate_quality':'independent_review_eligible_candidate',
            'coordinate_source':p['coordinate_source'],'coordinate_source_record_id':p['coordinate_source_record_id'],
            'coordinate_provider':p['coordinate_provider'],'coordinate_provider_id':p['coordinate_provider_id'],
            'source_name':p['source_name'],'source_type':p['source_type'],'source_region':p['source_region'],
            'source_file':p['source_file'],'source_sha256':p['source_sha256'],'source_locator':p['source_locator'],
            'coordinate_provenance':p['point_review_rule'],'admission_rule':p['point_review_rule'],
            'coordinate_admission_status':'staged_candidate_pending_root_review','coordinate_measurement_date_unknown':True,
            'boundary_comparability_asserted':False,'provider_binding_status':'not_asserted','provider_fias_binding_status':'not_asserted',
            'point_origin_file':p['point_origin_file'],'point_origin_sha256':p['point_origin_sha256'],
            'point_origin_locator':p['point_origin_locator'],'point_origin_kind':p['point_origin_kind'],
            'coordinate_application_review_sha256':p['point_review_receipt_sha256'],
            'target_population':p['population_value'],'native_id_binding_asserted':False,
            'coordinate_admitted':False,'point_admitted':False,'admission_allowed':False,
            'integration_review_status':'pending_root_point_application_review','population_scope_comparability_asserted':False})
    propagated_rows=[]
    for p in propagated:
        propagated_rows.append({'target_source_record_id':p['target_source_record_id'],'target_year':p['target_year'],
            'latitude':p['latitude'],'longitude':p['longitude'],'coordinate_quality':'continuity_inference_candidate',
            'coordinate_source':p['coordinate_source'],'coordinate_source_record_id':p['coordinate_source_record_id'],
            'coordinate_provider':'','coordinate_provider_id':'','coordinate_provenance':p['continuity_inference'],
            'admission_rule':p['continuity_inference'],'coordinate_admission_status':'staged_candidate_pending_root_review',
            'coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,
            'provider_binding_status':'not_asserted','provider_fias_binding_status':'not_asserted',
            'point_origin_file':p['point_origin_file'],'point_origin_sha256':p['point_origin_sha256'],
            'point_origin_locator':p['point_origin_locator'],'point_origin_kind':p['point_origin_kind'],
            'supporting_carrier_source_record_id':p['supporting_carrier_source_record_id'],
            'inference_path_source_to_target_decision_ids_json':p['identity_path_decision_ids_json'],
            'inference_path_source_to_target_source_record_ids_json':p['identity_path_source_record_ids_json'],
            'inference_identity_path_edge_count':p['identity_path_edge_count'],
            'native_id_binding_asserted':False,'coordinate_admitted':False,'point_admitted':False,
            'admission_allowed':False,'integration_review_status':p['point_use_status'],
            'population_scope_comparability_asserted':False})
    new_point_frame=pd.DataFrame(direct_rows+propagated_rows)
    con.register('new_point_frame',new_point_frame)
    con.execute(f"""
        COPY (
          SELECT *, 'existing_frozen_accepted'::VARCHAR AS integration_layer,
                     'preserved_existing_point_use'::VARCHAR AS integration_review_status
          FROM read_parquet('{paths['base_point_uses']}')
          UNION ALL BY NAME
          SELECT * EXCLUDE(integration_review_status), 'new_point_use_candidate'::VARCHAR AS integration_layer,
                     coalesce(integration_review_status,'pending_root_point_application_review')::VARCHAR AS integration_review_status
          FROM new_point_frame
        ) TO '{out / 'merged_point_uses.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    # Coverage by independent DFS component membership. Candidate coverage is a
    # potential scenario, clearly separate from frozen admitted baseline.
    selected_idx=selected.set_index('source_record_id',drop=False)
    base_point_ids=baseline_point_ids
    candidate_point_ids=set(direct_new_ids for direct_new_ids in (p['target_source_record_id'] for p in direct_new))
    propagated_point_ids={str(p['target_source_record_id']) for p in propagated}
    scenario_point_ids=base_point_ids|candidate_point_ids|propagated_point_ids
    metrics=[]
    for year in (2002,2010,2021):
        g=selected[selected.census_year.eq(year)]
        ids=set(g.source_record_id.astype(str))
        ordinary_ids=ids-aggregate_ids
        known=g.population.notna()
        n_known=int(g.population[known].sum())
        for name,linked,full,points,scope in [
            ('frozen_admitted',base_linked,base_full,base_point_ids,'accepted baseline'),
            ('all_graph_safe_candidates_pending_review',scenario_linked,scenario_full,base_point_ids,'candidate graph plus frozen accepted points'),
            ('all_candidates_plus_review_eligible_direct_points',scenario_linked,scenario_full,base_point_ids|candidate_point_ids,'candidate graph plus eligible point use candidates'),
            ('working_application_with_point_propagation_candidates',scenario_linked,scenario_full,scenario_point_ids,'candidate graph plus direct and propagated point use candidates'),
            ('only_identity_edges_with_explicit_external_review_receipt',admitted_linked,admitted_full,base_point_ids,'accepted graph plus review-receipt edges'),
        ]:
            linked_set=linked&ordinary_ids
            full_set=full&ordinary_ids
            point_set=points&ordinary_ids
            joint_full=full_set&point_set
            linked_pop=int(g.loc[g.source_record_id.isin(linked_set)&known,'population'].sum())
            full_pop=int(g.loc[g.source_record_id.isin(full_set)&known,'population'].sum())
            point_pop=int(g.loc[g.source_record_id.isin(point_set)&known,'population'].sum())
            joint_pop=int(g.loc[g.source_record_id.isin(joint_full)&known,'population'].sum())
            metrics.append({'year':year,'scenario':name,'scenario_scope':scope,
                'selected_rows':len(g),'known_population_rows':int(known.sum()),'unknown_population_rows':int((~known).sum()),
                'selected_known_population':n_known,'official_control_population':CONTROLS[year],
                'recognized_federal_aggregate_rows':int(g.source_record_id.astype(str).isin(aggregate_ids).sum()),
                'recognized_federal_aggregate_population':int(g.loc[g.source_record_id.astype(str).isin(aggregate_ids)&known,'population'].sum()),
                'ordinary_identity_linked_rows':len(linked_set),'ordinary_identity_linked_known_population':linked_pop,
                'ordinary_identity_linked_fraction_official_control':linked_pop/CONTROLS[year],
                'ordinary_full_chain_rows':len(full_set),'ordinary_full_chain_known_population':full_pop,
                'ordinary_full_chain_fraction_official_control':full_pop/CONTROLS[year],
                'coordinate_point_rows':len(point_set),'point_known_population':point_pop,
                'joint_point_and_full_chain_rows':len(joint_full),'joint_point_and_full_chain_known_population':joint_pop,
                'joint_point_and_full_chain_fraction_official_control':joint_pop/CONTROLS[year],
                'population_comparability_asserted':False,'boundary_comparability_asserted':False,
                'admissions_made_by_dry_run':False})
        residual=g[g.source_record_id.astype(str).isin(ordinary_ids-scenario_full)]
        residual=residual.sort_values('population',ascending=False,na_position='last').head(500)
        residual.to_csv(out/f'top_residuals_{year}.csv',index=False)
    pd.DataFrame(metrics).to_csv(out/'yearly_coverage_dry_run.csv',index=False)
    residual_summary=[]
    for year in (2002,2010,2021):
        g=selected[selected.census_year.eq(year)]
        ids=set(g.source_record_id.astype(str))-aggregate_ids
        missing=ids-scenario_full
        residual=g[g.source_record_id.astype(str).isin(missing)]
        residual_summary.append({'year':year,'ordinary_selected_rows':len(ids),'full_chain_residual_rows':len(missing),
            'residual_known_population_rows':int(residual.population.notna().sum()),
            'residual_known_population':int(residual.population.sum()),
            'residual_unknown_population_rows':int(residual.population.isna().sum())})
    pd.DataFrame(residual_summary).to_csv(out/'full_chain_residual_counts.csv',index=False)

    # Receipt and reproducibility inventory.
    output_files={}
    for p in sorted(out.iterdir()):
        if p.is_file() and p.name!='working_application_receipt.json':
            output_files[p.name]={'sha256':sha(p),'bytes':p.stat().st_size}
    result={'status':'diagnostic_dry_run_candidate_application_no_new_admissions',
        'mode':'dry_run_only','frozen_release':str(F),'source_evidence_json_is_authoritative':True,
        'inputs':hashes,'frozen_checksums_verified':True,
        'independent_reviews':{'historical_bridge':{'receipt_sha256':sha(paths['historical_review_receipt']),'eligible_point_uses':len(hist)},
                               'wikidata':{'receipt_sha256':sha(paths['wikidata_review_receipt']),'eligible_point_uses':len(wd),'held_point_choices':len(wd_holds)}},
        'temporal_identity_review':{'independent_eligibility_receipt':review_metadata,'application_acceptance_receipt':identity_receipt_metadata,
                                    'accepted_pair_rule_count':len(reviewed_pairs),'pre_final_DFS_eligibility_is_not_admission':True},
        'identity_graph':{'frozen_edges':len(base),'candidate_edges':len(edge_diag_df),
            'candidate_graph_safe_edges':int(candidate_graph_df.shape[0]),
            'new_graph_components_added':int((edge_diag_df.integration_graph_result=='added').sum()),
            'redundant_to_base_or_prior_candidate':int((edge_diag_df.integration_graph_result=='already_connected').sum()),
            'held_edges':int((edge_diag_df.decision_status=='held_in_dry_run').sum()),
            'independently_receipt_approved_edges':int(edge_diag_df.decision_status.str.startswith('checked_rule_accepted').sum()),
            'federal_aggregate_edges_blocked_from_ordinary_graph':int(edge_diag_df.integration_hold_reasons_json.str.contains('federal_aggregate').sum()),
            'legacy_identity_conflict_warnings_not_global_veto':int(edge_diag_df.legacy_identity_conflict_warning_not_global_veto.sum()),
            'base_old_optional_columns_preserved':True},
        'point_uses':{'frozen_point_rows_preserved':len(base_points),'historical_independent_review_eligible':len(hist),
            'wikidata_independent_review_eligible':len(wd),'direct_new_point_candidates':len(direct_new),
            'direct_point_conflicts_or_holds':int((point_diag_df.point_candidate_status=='held_in_dry_run').sum()),
            'identical_existing_point_candidates_redundant':int((point_diag_df.point_candidate_status=='already_present_identical_frozen_point').sum()),
            'propagated_point_candidates':len(propagated),'propagation_component_point_conflict_holds':sum('distinct_point_pairs' in x for x in component_point_seeds),
            'quarantined_targets':len(quarantine_ids),'wikidata_point_choice_holds':len(wd_holds),
            'native_provider_binding_asserted':False,'boundary_comparability_asserted':False},
        'federal_chain':{'typed_accepted_edge_rows':len(fed_df),'kept_separate_from_ordinary_settlement_graph':True,'federal_aggregate_NP_point_use_allowed':False,
                         'typed_edge_file':'federal_typed_city_continuity.parquet','territory_reference_point_file':'federal_territory_reference_points.parquet'},
        'official_controls':{str(k):v for k,v in CONTROLS.items()},'yearly_coverage_file':'yearly_coverage_dry_run.csv',
        'limitations':['Candidate identity edges do not become admissions without a decision receipt.',
            'All source point uses beyond the frozen baseline remain candidates pending root application review.',
            'Continuity propagation is a point-use inference and does not prove census-date measurement, native provider binding, boundary equivalence, or population comparability.',
            'Federal territorial chains remain typed and separate from physical settlement points.',
            'Population values and unknowns are preserved; no interpolation or residual allocation occurs.'],
        'outputs':output_files,'builder_sha256':sha(Path(__file__))}
    (out/'working_application_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'receipt':str(out/'working_application_receipt.json'),'identity_graph':result['identity_graph'],
        'point_uses':result['point_uses'],'yearly_coverage':pd.DataFrame(metrics).to_dict('records')},ensure_ascii=False,indent=2))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frozen',type=Path,default=FROZEN)
    p.add_argument('--stage',type=Path,default=STAGE)
    p.add_argument('--output',type=Path,default=DEFAULT_OUT)
    p.add_argument('--identity-review-receipt',type=Path,default=None,
                   help='Optional receipt with accepted_decision_ids or accepted_edges_csv + accepted_edges_sha256')
    a=p.parse_args();build(a)


if __name__=='__main__':main()
