"""Apply reviewed rows, then reuse sourced points along accepted identity paths.

Frozen data remain inputs. Rule-review lists and a separately reviewed merged
graph gate admission. Existing decisions and coordinate rows are preserved.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import itertools
import json
import math
from collections import defaultdict, deque
from pathlib import Path
import sys
from datetime import datetime, timezone
import duckdb
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_rebuild.mass_linkage.coverage import identity_sets, measure
from research_rebuild.mass_linkage.propagate_continuation_points import stage_point_use, read_blocked_targets


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def distance(a, b):
    x, y = map(math.radians, (float(a['latitude']), float(b['latitude'])))
    d = math.radians(float(a['longitude']) - float(b['longitude']))
    return 12742 * math.asin(min(1, math.sqrt(math.sin((x-y)/2)**2 + math.cos(x)*math.cos(y)*math.sin(d/2)**2)))


def run(a):
    requested = datetime.fromisoformat(a.reviewed_at.replace('Z','+00:00'))
    if requested.tzinfo is None: raise ValueError('reviewed-at requires an explicit timezone')
    a.reviewed_at = min(requested, datetime.now(timezone.utc)).isoformat()
    f, stage, dry, out = map(Path, (a.frozen, a.stage, a.dry, a.output))
    if out.exists() and any(out.iterdir()): raise FileExistsError(out)
    graph_review = json.loads(Path(a.graph_review).read_text())
    graph_review_sha = sha(Path(a.graph_review))
    graph_path = dry / 'merged_identity_edges.parquet'
    # The independent reviewer must name the exact graph and explicitly pass it.
    if not graph_review.get('passed'): raise ValueError('independent merged graph review did not pass')
    if graph_review.get('graph_sha256') != sha(graph_path): raise ValueError('independent graph review checksum mismatch')
    reviews = stage / 'independent_review'
    rule_path = reviews / 'temporal_independent_review_receipt.json'
    rule_receipt = json.loads(rule_path.read_text())
    eligible = set()
    for filename, family in [('temporal_mass_eligible_edges_pre_DFS.csv','temporal_mass'),
                             ('legacy_temporal_eligible_edges.csv','legacy_temporal')]:
        p = reviews / filename
        if sha(p) != rule_receipt[family]['eligible_edge_list_sha256']: raise ValueError('identity rule-list checksum mismatch')
        with p.open() as stream:
            for r in csv.DictReader(stream):
                eligible.add((r['from_source_record_id'], r['to_source_record_id'], r.get('rule_family') or r['decision_class']))
    con = duckdb.connect(config={'threads':1})
    selected = pd.read_parquet(f / 'selected_observations.parquet')
    graph = pd.read_parquet(graph_path)
    new = graph.integration_layer.eq('new_identity_candidate')
    for r in graph.loc[new].itertuples():
        if (r.from_source_record_id, r.to_source_record_id, r.integration_rule_family) not in eligible:
            raise ValueError('unreviewed identity row in merged graph')
    graph.loc[new, 'decision_status'] = 'checked_rule_accepted'
    graph.loc[new, 'admission_status'] = 'checked_rule_accepted'
    graph.loc[new, 'candidate_only'] = False
    graph.loc[new, 'reviewer'] = 'independent_rule_and_merged_graph_review; root_application'
    graph.loc[new, 'reviewed_at'] = a.reviewed_at
    graph.loc[new, 'evidence_sha256'] = sha(rule_path)
    graph.loc[new, 'application_review_sha256'] = graph_review_sha
    graph.loc[new, 'selection_projection_status'] = 'active_endpoints_selected'
    graph.loc[new, 'integration_review_status'] = 'accepted_after_independent_rule_and_graph_review'
    linked, full, components = identity_sets(selected, graph)
    # Do not carry dry-run propagation forward: apply direct independently
    # reviewed points and recompute paths over the canonical accepted graph.
    dry_points = pd.read_parquet(dry / 'merged_point_uses.parquet')
    direct = dry_points.loc[dry_points.integration_layer.eq('new_point_use_candidate') &
                           dry_points.supporting_carrier_source_record_id.isna()].copy()
    for name, key, count in [('historical_bridge_independent_receipt.json','historical',1013),
                              ('wikidata_review_receipt_final.json','wikidata',12800)]:
        receipt = json.loads((reviews / name).read_text())
        filename = 'historical_bridge_eligible_point_uses.csv' if key == 'historical' else 'wikidata_review_eligible_point_uses_final.csv'
        if receipt['outputs_sha256'][filename] != sha(reviews / filename): raise ValueError('point review-list checksum mismatch')
        rows = list(csv.DictReader((reviews / filename).open()))
        if len(rows) != count: raise ValueError('point eligible count changed')
        by_id = {r.get('target_source_record_id') or r['source_record_id']: r for r in rows}
        for r in direct.itertuples():
            if r.target_source_record_id not in by_id: continue
            q = by_id[r.target_source_record_id]
            lat, lon = (q['latitude'],q['longitude']) if key == 'historical' else (q['P625_latitude'],q['P625_longitude'])
            if float(r.latitude) != float(lat) or float(r.longitude) != float(lon): raise ValueError('reviewed coordinate value changed')
    allowed_ids = set()
    for name in ['historical_bridge_eligible_point_uses.csv','wikidata_review_eligible_point_uses_final.csv']:
        with (reviews / name).open() as stream:
            allowed_ids.update(r.get('target_source_record_id') or r['source_record_id'] for r in csv.DictReader(stream))
    if not set(direct.target_source_record_id).issubset(allowed_ids): raise ValueError('unreviewed direct point')
    # Preserve actual population-source origins for Wikidata target rows.
    with (stage / 'wikidata_points/wikidata_primary_staged_ledger.csv').open() as stream:
        wd_origin = {r['source_record_id']:r for r in csv.DictReader(stream)}
    origin_hashes = {}
    for i, r in direct.iterrows():
        if r.target_source_record_id in wd_origin:
            q = wd_origin[r.target_source_record_id]
            for field in ['file','sha256','locator']: direct.at[i,'source_'+field] = q['target_source_'+field]
        if any(pd.isna(v) or not str(v).strip() for v in [r.point_origin_file,r.point_origin_sha256,r.point_origin_locator]):
            raise ValueError('direct source point origin missing')
        if r.point_origin_file not in origin_hashes: origin_hashes[r.point_origin_file] = sha(r.point_origin_file)
        if origin_hashes[r.point_origin_file] != r.point_origin_sha256: raise ValueError('direct point origin byte hash mismatch')
    direct['coordinate_admission_status'] = 'reviewed_extension_rule_accepted'
    direct['coordinate_quality'] = 'automatically_accepted_checked_rule'
    direct['coordinate_admitted'] = True; direct['point_admitted'] = True; direct['admission_allowed'] = True
    direct['coordinate_application_family'] = 'reviewed_ordinary_direct_point_extension_20261004'
    direct['integration_review_status'] = 'accepted_root_application_of_independently_reviewed_exact_rows'
    base_points = pd.read_parquet(f / 'accepted_point_uses.parquet')
    points = pd.concat([base_points, direct], ignore_index=True)
    if points.target_source_record_id.duplicated().any(): raise ValueError('duplicate direct point target')
    point_by_id = {r.target_source_record_id:r._asdict() for r in points.itertuples(index=False)}
    point_ids = set(point_by_id)
    blocked = read_blocked_targets(Path(a.blocked))
    blocked |= set(json.loads((reviews / 'wikidata_review_receipt_final.json').read_text())['decision']['hard_geo_point_choice_hold_ids'])
    evidence = {}
    needed = {sid for members in components for sid in members if sid not in point_by_id}
    for r in pd.read_parquet(f / 'source_evidence.parquet', filters=[('source_record_id','in',sorted(needed))]).itertuples():
        evidence[r.source_record_id] = json.loads(r.source_evidence_json)
    target_rows = selected.set_index('source_record_id',drop=False)
    adjacency = defaultdict(list)
    for r in graph[['decision_id','from_source_record_id','to_source_record_id']].itertuples(index=False):
        adjacency[r.from_source_record_id].append((r.to_source_record_id,r.decision_id))
        adjacency[r.to_source_record_id].append((r.from_source_record_id,r.decision_id))
    propagation, holds = [], []
    years = selected.set_index('source_record_id').census_year.to_dict()
    for members in components:
        seeds = [point_by_id[sid] for sid in members if sid in point_by_id and sid not in blocked]
        missing = members - point_ids
        if not seeds or not missing: continue
        spread = max((distance(x,y) for x,y in itertools.combinations(seeds,2)), default=0)
        if spread > 5:
            holds.append({'members_json':json.dumps(sorted(members)), 'hold':'accepted_point_witness_spread_over_5km','spread_km':spread})
            continue
        carrier = min(seeds, key=lambda r:(-int(years[r['target_source_record_id']]),r['target_source_record_id']))
        origin = carrier['target_source_record_id']; pred={origin:None}; queue=deque([origin])
        while queue:
            sid = queue.popleft()
            for nxt, did in sorted(adjacency[sid]):
                if nxt not in pred: pred[nxt]=(sid,did); queue.append(nxt)
        for target in sorted(missing):
            e = evidence[target]
            if target in blocked or e.get('is_federal_aggregate') or e.get('legacy_verified_successor_settlement_id'): continue
            path=[]; node=target
            while node!=origin: node,did=pred[node]; path.append(did)
            # Helper expects target-to-carrier path and preserves origin claims.
            row=stage_point_use(target_rows.loc[target], e, carrier, origin, e, path)
            row.update(coordinate_admission_status='reviewed_extension_rule_accepted',
                       coordinate_quality='automatically_accepted_checked_rule',
                       coordinate_application_family='R_reviewed_same_place_sourced_point_continuity_20261004',
                       application_inference_kind='sourced_representative_point_reuse_across_accepted_observed_years',
                       native_id_binding_asserted=False, provider_binding_status='point_origin_binding_only_not_target_native_identifier',
                       coordinate_admitted=True, point_admitted=True, admission_allowed=True,
                       review_id='root_scoped_continuity_application_20261004',
                       application_gate_status='passed_accepted_graph_sourced_point_continuity',
                       coordinate_application_review_sha256=graph_review_sha,
                       accepted_component_point_spread_km=spread)
            propagation.append(row)
    points = pd.concat([points, pd.DataFrame(propagation)],ignore_index=True)
    if points.target_source_record_id.duplicated().any(): raise ValueError('duplicate propagated target')
    out.mkdir(parents=True,exist_ok=True)
    graph.to_parquet(out / 'accepted_identity_edges.parquet',index=False)
    # DuckDB aligns optional columns without coercing frozen bool/string metadata.
    con.register('points', points)
    con.execute(f"COPY points TO '{out / 'accepted_point_uses.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    pd.DataFrame(holds).to_csv(out / 'point_continuity_holds.csv',index=False)
    legacy = pd.read_parquet(f / 'legacy_availability_projected_r5.parquet')
    selected['is_federal_aggregate_from_grain_evidence'] = selected.population_scope.eq('federal_city_region')
    federal_ids=set(pd.read_parquet(stage / 'federal_application/accepted_territory_reference_points.parquet').source_record_id)
    selected.loc[selected.source_record_id.isin(federal_ids),'is_federal_aggregate_from_grain_evidence']=True
    coverage=measure(selected,legacy,graph,points,{2002:145166731,2010:142856536,2021:147182123})
    fed_chains = pd.read_parquet(stage / 'federal_application/accepted_typed_city_continuity.parquet')
    fed_full = set()
    for r in fed_chains.itertuples():
        if r.chain_status == 'continuing_city_three_observed_censuses_changing_population_scope':
            fed_full.update(json.loads(r.source_record_ids_json))
    spatial_ids = set(points.target_source_record_id) | federal_ids
    mixed_joint = (full | fed_full) & spatial_ids
    coverage['current_user_target_fraction'] = .99
    coverage['mixed_scope_joint_coordinate_and_three_observed_censuses'] = []
    for year, g in selected.groupby('census_year'):
        control={2002:145166731,2010:142856536,2021:147182123}[int(year)]
        covered=g.source_record_id.isin(mixed_joint)
        population=int(g.loc[covered,'population'].sum())
        coverage['mixed_scope_joint_coordinate_and_three_observed_censuses'].append({
            'year':int(year),'rows':int(covered.sum()),'row_fraction':float(covered.mean()),
            'known_population':population,'official_control_population_fraction':population/control,
            'remaining_population_to_99':max(0,math.ceil(control*.99)-population),
            'scope':'physical NP plus separately accepted continuing federal-city identity with changing observation grain',
            'parent_child_rule':'exclusive parent; no federal children added in current selected layer',
            'boundary_population_comparability_asserted':False})
    for row in coverage['census_metrics']:
        row['original_quality_target_fraction']=.999
    (out / 'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
    selected.assign(joint_full=selected.source_record_id.isin(full & set(points.target_source_record_id))).query('not joint_full').sort_values('population',ascending=False).to_parquet(out / 'joint_residual.parquet',index=False)
    receipt={'status':'applied_reviewed_mass_batch','new_identity_rows':int(new.sum()),'accepted_graph_rows':len(graph),
             'application_reviewed_at_utc':a.reviewed_at,
             'new_direct_point_uses':len(direct),'new_continuity_point_uses':len(propagation),
             'full_census_components':len(full)//3, 'source_population_values_modified':False,
             'inputs':{str(p):sha(p) for p in [graph_path,Path(a.graph_review),rule_path,dry / 'merged_point_uses.parquet']},
             'script_sha256':sha(__file__), 'outputs':{p.name:sha(p) for p in out.iterdir() if p.is_file()}}
    (out / 'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ['frozen','stage','dry','output','graph-review','blocked','reviewed-at']:p.add_argument('--'+key,required=True)
    run(p.parse_args())
