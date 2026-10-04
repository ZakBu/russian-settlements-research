"""Apply only manifest-pinned reviewed extensions to the accepted mass batch.

This is an application tool, not a review producer. It does not decide which
review rows are eligible: every identity edge and point use must be present in
an explicitly pinned independent eligible list. The JSON manifest schema is
shown by --example-manifest. No output directory is written until all input,
review-list, collision, source-origin, and graph checks have passed.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import itertools
import json
import math
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_rebuild.mass_linkage.coverage import identity_sets, measure
from research_rebuild.mass_linkage.propagate_continuation_points import (
    read_blocked_targets, stage_point_use,
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def pinned(spec: dict, label: str) -> Path:
    p = Path(spec['path'])
    if not p.is_file():
        raise FileNotFoundError(f'{label}: {p}')
    got = sha(p)
    if got != spec['sha256']:
        raise ValueError(f'{label} checksum mismatch: expected {spec["sha256"]}, got {got}')
    return p


def truth(v) -> bool:
    return str(v).strip().lower() in {'true', '1', 'yes', 'y'}


def preserve_nullable_booleans(frame, columns):
    """Keep false/unknown flags typed after heterogeneous source concatenation.

    DuckDB may infer VARCHAR for object columns containing both boolean and
    missing values. In particular, the string 'False' is truthy in Python.
    Unknown values stay unknown; unexpected literals fail before writing.
    """
    for column in columns:
        if column not in frame:
            continue
        values = []
        for value in frame[column]:
            if value is None or pd.isna(value) or str(value).strip() == '':
                values.append(pd.NA)
            elif str(value).strip().lower() in {'true', '1', '1.0'}:
                values.append(True)
            elif str(value).strip().lower() in {'false', '0', '0.0'}:
                values.append(False)
            else:
                raise ValueError(f'invalid boolean source flag {column}: {value!r}')
        frame[column] = pd.array(values, dtype='boolean')
    return frame


def lazy_point_carriers(points):
    """Materialize complete carrier evidence only for components needing a point."""
    ids = points.target_source_record_id.astype(str).tolist()
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate carrier targets')
    positions = {sid: position for position, sid in enumerate(ids)}
    cache = {}
    def get_carrier(sid):
        if sid not in cache:
            cache[sid] = points.iloc[positions[sid]].to_dict()
        return cache[sid]
    return set(positions), get_carrier


def key_from(row, fields):
    return tuple(str(row[f]).strip() for f in fields)


def distance(a, b):
    x, y = map(math.radians, (float(a['latitude']), float(b['latitude'])))
    d = math.radians(float(a['longitude']) - float(b['longitude']))
    return 12742 * math.asin(min(1, math.sqrt(math.sin((x-y)/2)**2 +
              math.cos(x)*math.cos(y)*math.sin(d/2)**2)))


def read_table(path: Path):
    if path.suffix.lower() == '.parquet':
        return pd.read_parquet(path)
    # The C CSV parser is unsafe for several large legacy source extracts in
    # this build environment; all application CSVs use the Python engine.
    return pd.read_csv(path, dtype='string', keep_default_na=False, engine='python')


def read_csv_rows(path: Path):
    # Reviewed source-block witnesses can exceed the CSV module's 128 KiB
    # default. Preserve the complete evidence rather than truncating fields.
    csv.field_size_limit(100_000_000)
    with path.open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def load_historical_pre_event_scopes(manifest, selected):
    """Read narrowly reviewed old-city uses; never grant a successor identity."""
    scopes, pairs, pins = {}, set(), []
    records = selected.set_index('source_record_id', drop=False)
    for spec in manifest.get('historical_pre_event_exceptions', []):
        path = pinned(spec['review_receipt'], 'historical pre-event independent review')
        review = json.loads(path.read_text())
        if review.get('status') != 'independent_pre_event_review_complete_candidate_only':
            raise ValueError('unexpected pre-event review status')
        if review['decision']['2002_to_2010_same_place_pair'] != 'supported_for_scoped_root_review':
            raise ValueError('pre-event identity scope is not independently supported')
        if review['decision']['2011_point_use_for_2002_and_2010'] != 'supported_as_separate_spatial_continuity_candidate':
            raise ValueError('pre-event point scope is not independently supported')
        approved = review['approved_scope_candidate']
        pair = (approved['from_source_record_id'], approved['to_source_record_id'])
        observed = {r['source_record_id']: r for r in review['published_city_observations']}
        if set(observed) != set(pair) or set(approved['exact_source_hashes']) != set(pair):
            raise ValueError('pre-event review must bind exactly its published pair')
        publication_specs = spec['published_sources']
        if set(publication_specs) != set(pair):
            raise ValueError('pre-event exception must pin both exact publication files')
        for sid in pair:
            asset = pinned(publication_specs[sid], 'pre-event primary publication')
            if publication_specs[sid]['sha256'] != approved['exact_source_hashes'][sid]:
                raise ValueError('pre-event primary publication hash differs from reviewed source')
            if not asset.as_posix().endswith('/' + observed[sid]['source_path']):
                raise ValueError('pre-event publication path differs from reviewed source path')
        floor = int(review['successor_event']['event_candidate']['legacy_asserted_year'])
        origin = review['input_pins']['GeoKLADR_DBf']
        pinned(origin, 'pre-event raw point origin')
        point = review['historical_city_identity_and_point']['2011_GeoKLADR']
        if point['is_deleted'] or point['type_raw'].strip() != 'г':
            raise ValueError('pre-event historical point is not an active city record')
        for sid in pair:
            if sid not in records.index or sid in scopes:
                raise ValueError('pre-event source ID is absent or duplicated')
            row, old = records.loc[sid], observed[sid]
            if int(row.census_year) != int(old['observation_year']) or int(row.census_year) >= floor:
                raise ValueError('pre-event observation must precede the entire stated event year')
            if row.settlement_type != 'город' or row.settlement_name != old['settlement_name']:
                raise ValueError('pre-event city source name/type changed')
            if float(row.population) != float(old['population_value']):
                raise ValueError('pre-event source population changed')
            if str(row.source_file) != old['source_path']:
                raise ValueError('pre-event selected source path differs from reviewed publication')
            if pd.notna(row.source_sha256) and str(row.source_sha256) != approved['exact_source_hashes'][sid]:
                raise ValueError('pre-event source hash differs from independently reviewed publication')
            scopes[sid] = {'review_receipt_sha256': sha(path), 'event_year_floor': floor,
                           'latitude': float(point['latitude']), 'longitude': float(point['longitude']),
                           'origin_file': origin['path'], 'origin_sha256': origin['sha256']}
        pairs.add(pair)
        pins.append({'path': str(path), 'sha256': sha(path), 'source_record_ids': list(pair),
                     'scope': 'only the independently reviewed pre-event pair and old-city point uses; no successor identity'})
    return scopes, pairs, pins


def validate_historical_pre_event_pairs(new_graph, scopes, pairs):
    for row in new_graph.itertuples(index=False):
        pair = (str(row.from_source_record_id), str(row.to_source_record_id))
        if set(pair) & set(scopes) and pair not in pairs:
            raise ValueError('pre-event exception cannot authorize another pair or a successor identity')


def validate_components_have_unique_years(selected, components):
    years=selected.set_index('source_record_id').census_year.to_dict()
    for component in components:
        component_years=[int(years[sid]) for sid in component if sid in years]
        if len(component_years)!=len(set(component_years)):
            raise ValueError('accepted identity graph contains a same-year union-find collision')


def validate_identity_source_evidence(new_graph, evidence, pre_event_scopes, collision_resolutions):
    """Validate source hard blocks per exact new edge and endpoint."""
    checked_clear=set()
    for r in new_graph[['from_source_record_id','to_source_record_id']].itertuples(index=False):
        a,b=str(r.from_source_record_id),str(r.to_source_record_id)
        for sid in (a,b):
            ev=evidence.get(sid)
            if not ev:
                raise ValueError(f'identity endpoint lacks frozen source evidence: {sid}')
            if sid not in checked_clear:
                if not truth(ev.get('is_additive_settlement_record')) or truth(ev.get('is_federal_aggregate')) or (ev.get('legacy_verified_successor_settlement_id') and sid not in pre_event_scopes):
                    raise ValueError(f'identity endpoint is nonadditive, an aggregate, or a verified successor event: {sid}')
                checked_clear.add(sid)
            if truth(ev.get('legacy_same_year_collision')):
                resolution=collision_resolution_for_pair(collision_resolutions,a,b,sid)
                if not resolution:
                    raise ValueError(f'identity endpoint has an authoritative same-year collision without exact reviewed pair scope: {sid}')


def validate_direct_point_source_evidence(ev, sid, pre_event_scopes):
    """Direct points never inherit the narrow identity-collision exemption."""
    if (not ev or not truth(ev.get('is_additive_settlement_record')) or
        truth(ev.get('is_federal_aggregate')) or
        (ev.get('legacy_verified_successor_settlement_id') and sid not in pre_event_scopes) or
        truth(ev.get('legacy_same_year_collision'))):
        raise ValueError(f'point target is not an additive unblocked physical source row: {sid}')


def example_manifest():
    return {
      "frozen": {
        "selected": {"path":"/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet","sha256":"<sha256>"},
        "source_evidence": {"path":"/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet","sha256":"<sha256>"},
        "legacy_availability": {"path":"/workspace/settlements-delivery/continuation-consolidated-20261003/legacy_availability_projected_r5.parquet","sha256":"<sha256>"}
      },
      "base": {
        "graph":{"path":"/workspace/settlements-work/continuation_20261004/accepted_mass_batch/accepted_identity_edges.parquet","sha256":"<sha256>"},
        "points":{"path":"/workspace/settlements-work/continuation_20261004/accepted_mass_batch/accepted_point_uses.parquet","sha256":"<sha256>"}
      },
      "identity_sources":[{
        "candidate":{"path":"/path/to/reviewed_candidate_edges.parquet","sha256":"<sha256>"},
        "eligible":{"path":"/path/to/independent_eligible_edges.csv","sha256":"<sha256>"},
        "review_receipt":{"path":"/path/to/independent_review_receipt.json","sha256":"<sha256>"},
        "candidate_columns":{"from":"from_source_record_id","to":"to_source_record_id","family":"integration_rule_family","id":"decision_id","status":"integration_layer","candidate_value":"new_identity_candidate","collision":"same_year_collision","event":"verified_successor_event","global_block":"global_block"},
        "eligible_columns":{"from":"from_source_record_id","to":"to_source_record_id","family":"rule_family"},
        "accepted_candidate_statuses":["staged_candidate_pending_independent_review"],
        "exclude_if_true":["collision","event","global_block"]
      }],
      "legacy_collision_resolution_reviews":[{
        "eligible":{"path":"/path/to/independently_eligible_flagged_endpoints.csv","sha256":"<sha256>"},
        "review_receipt":{"path":"/path/to/independent_legacy_collision_resolution_receipt.json","sha256":"<sha256>"}
      }],
      "point_sources":[{
        "candidate":{"path":"/path/to/staged_point_uses.parquet","sha256":"<sha256>"},
        "approved":{"path":"/path/to/independently_eligible_points.csv","sha256":"<sha256>"},
        "review_receipt":{"path":"/path/to/independent_point_review_receipt.json","sha256":"<sha256>"},
        "candidate_columns":{"target":"target_source_record_id","latitude":"latitude","longitude":"longitude","origin_file":"point_origin_file","origin_sha256":"point_origin_sha256","origin_locator":"point_origin_locator"},
        "approved_columns":{"target":"target_source_record_id","latitude":"latitude","longitude":"longitude"},
        "origin":{"path":"/path/to/raw_point_origin.dbf","sha256":"<sha256>"}
      }],
      "blocked_targets":{"path":"/path/to/blocked_targets.csv","sha256":"<sha256>"},
      "federal_points":{"path":"/path/to/accepted_federal_points.parquet","sha256":"<sha256>"},
      "federal_chains":{"path":"/path/to/accepted_federal_chains.parquet","sha256":"<sha256>"},
      "reviewed_at_utc":"2026-10-04T00:00:00Z"
    }


def load_legacy_collision_resolution_reviews(manifest, selected):
    """Load exact-pair, exact-flagged-endpoint collision resolutions.

    These reviews can resolve a quarantined legacy crosswalk ambiguity for a
    specific independently supported identity edge. They never waive a
    federal/nonadditive/event block, a candidate-year conflict, or a direct
    point gate.
    """
    specs = manifest.get('legacy_collision_resolution_reviews', [])
    resolutions, records = {}, []
    selected_ids = set(selected.source_record_id.astype(str))
    selected_years = selected.set_index('source_record_id').census_year.to_dict()
    source_evidence_path = Path(manifest['frozen']['source_evidence']['path'])
    if specs:
        # The source evidence is authoritative for whether the endpoint really
        # carries the collision flag being resolved.
        evidence_sha = sha(source_evidence_path)
        con = duckdb.connect(config={'threads': 1})
        for n, spec in enumerate(specs):
            eligible_path = pinned(spec['eligible'], f'legacy collision eligible endpoints {n}')
            receipt_path = pinned(spec['review_receipt'], f'legacy collision review receipt {n}')
            eligible_sha, receipt_sha = sha(eligible_path), sha(receipt_path)
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            if receipt.get('status') != 'independent_legacy_collision_resolution_review_complete_candidate_only':
                raise ValueError('unexpected legacy collision resolution review status')
            if receipt.get('eligible_csv_sha256') != eligible_sha:
                raise ValueError('legacy collision review receipt does not pin its eligible endpoint CSV')
            if receipt.get('frozen_source_evidence_sha256') != evidence_sha:
                raise ValueError('legacy collision review receipt does not pin frozen source evidence')
            required = {'source_record_id','from_source_record_id','to_source_record_id',
                        'resolution_status','proof_json'}
            rows = read_csv_rows(eligible_path)
            if rows and not required.issubset(rows[0]):
                raise ValueError(f'legacy collision eligible CSV missing columns: {sorted(required-set(rows[0]))}')
            if not rows:
                raise ValueError('legacy collision eligible endpoint CSV is empty')
            review_ids=sorted({str(r.get('source_record_id','')).strip() for r in rows if str(r.get('source_record_id','')).strip()})
            con.register('reviewed_collision_ids', pd.DataFrame({'source_record_id':review_ids}))
            evidence_by_id={sid:json.loads(ej) for sid,ej in con.execute(
                f"SELECT e.source_record_id,e.source_evidence_json FROM read_parquet('{source_evidence_path}') e JOIN reviewed_collision_ids r USING(source_record_id)").fetchall()}
            rowkeys=set()
            for row in rows:
                sid=str(row.get('source_record_id','')).strip()
                a=str(row.get('from_source_record_id','')).strip()
                b=str(row.get('to_source_record_id','')).strip()
                status=str(row.get('resolution_status','')).strip()
                if not sid or not a or not b or a==b or sid not in {a,b}:
                    raise ValueError('legacy collision review endpoint must be one endpoint of a nonblank exact pair')
                if status!='independently_resolved_legacy_crosswalk_collision':
                    raise ValueError(f'unsupported legacy collision resolution status: {status!r}')
                key=(a,b,sid)
                if key in rowkeys or key in resolutions:
                    raise ValueError(f'duplicate legacy collision resolution scope: {key}')
                rowkeys.add(key)
                try: proof=json.loads(row.get('proof_json',''))
                except Exception as exc: raise ValueError(f'legacy collision resolution proof_json is invalid: {key}') from exc
                if not isinstance(proof,dict) or not proof or not any(v not in (None,'',[],{}) for v in proof.values()):
                    raise ValueError(f'legacy collision resolution has no substantive proof: {key}')
                if a not in selected_ids or b not in selected_ids:
                    raise ValueError(f'legacy collision resolution pair is outside frozen selected observations: {key}')
                if int(selected_years[a]) == int(selected_years[b]):
                    raise ValueError(f'legacy collision resolution cannot authorize same-year identity: {key}')
                ev=evidence_by_id.get(sid)
                if not ev:
                    raise ValueError(f'legacy collision resolution endpoint lacks frozen source evidence: {sid}')
                if not truth(ev.get('legacy_same_year_collision')):
                    raise ValueError(f'legacy collision review endpoint is not actually flagged in frozen evidence: {sid}')
                if not truth(ev.get('is_additive_settlement_record')) or truth(ev.get('is_federal_aggregate')) or ev.get('legacy_verified_successor_settlement_id'):
                    raise ValueError(f'legacy collision resolution cannot waive aggregate, nonadditive, or successor/event source flags: {sid}')
                resolutions[key]={'source_record_id':sid,'from_source_record_id':a,'to_source_record_id':b,
                    'resolution_status':status,'proof_json':json.dumps(proof,ensure_ascii=False,sort_keys=True),
                    'eligible_csv_path':str(eligible_path),'eligible_csv_sha256':eligible_sha,
                    'review_receipt_path':str(receipt_path),'review_receipt_sha256':receipt_sha}
            records.append({'eligible':{'path':str(eligible_path),'sha256':eligible_sha},
                            'review_receipt':{'path':str(receipt_path),'sha256':receipt_sha},
                            'eligible_endpoint_rows':len(rows),'review_status':receipt['status']})
    return resolutions, records


def collision_resolution_for_pair(resolutions, a, b, endpoint):
    """Return only a direction-exact reviewed endpoint scope."""
    return resolutions.get((str(a),str(b),str(endpoint)))


def load_identity(manifest):
    accepted_frames = []
    evidence = {}
    collision_resolutions = manifest.get('_legacy_collision_resolutions', {})
    for n, spec in enumerate(manifest['identity_sources']):
        cand_path = pinned(spec['candidate'], f'identity candidate {n}')
        elig_path = pinned(spec['eligible'], f'identity eligible list {n}')
        receipt_path = pinned(spec['review_receipt'], f'identity review receipt {n}')
        extra_receipts=[pinned(x,f'identity supplemental review receipt {n}') for x in spec.get('additional_review_receipts',[])]
        ccols, ecols = spec['candidate_columns'], spec['eligible_columns']
        eligible = {key_from(r, [ecols['from'], ecols['to'], ecols['family']])
                    for r in read_csv_rows(elig_path)}
        candidate_sha, eligible_sha, receipt_sha = sha(cand_path), sha(elig_path), sha(receipt_path)
        extra_receipt_records = [{'path':str(p),'sha256':sha(p)} for p in extra_receipts]
        cand = read_table(cand_path)
        required = [ccols[k] for k in ('from','to','family','status')]
        if ccols.get('id'): required.append(ccols['id'])
        missing = set(required) - set(cand.columns)
        if missing: raise ValueError(f'identity candidate missing columns: {sorted(missing)}')
        if ccols.get('id') and not cand[ccols['id']].astype(str).is_unique:
            raise ValueError('identity candidate decision IDs must be unique within each source')
        for r in cand.to_dict('records'):
            if str(r[ccols['status']]) not in set(spec['accepted_candidate_statuses']):
                continue
            k = (str(r[ccols['from']]), str(r[ccols['to']]), str(r[ccols['family']]))
            if any(not part for part in k): raise ValueError('identity keys must be nonblank')
            if k not in eligible: raise ValueError(f'unreviewed identity edge {k}')
            pair_resolutions = {sid: collision_resolution_for_pair(collision_resolutions,k[0],k[1],sid)
                                for sid in k[:2]}
            for field in spec.get('exclude_if_true', []):
                col = ccols[field]
                if col not in r: raise ValueError(f'missing identity exclusion field {col}')
                if truth(r[col]):
                    if field == "event" and k[:2] in manifest.get("_pre_event_pairs", set()):
                        continue
                    raise ValueError(f'blocked identity edge ({field}): {k}')
            # Scope-level hard gates apply even if the producing file omitted a
            # convenience boolean: relation/status must not encode event or collision.
            rel = str(r.get('relation', '')).lower()
            if 'event' in rel or 'successor' in rel or 'collision' in rel:
                raise ValueError(f'event/collision relation cannot be admitted: {k}')
            for fld in ('source_evidence_federal_aggregate_endpoint',
                        'source_evidence_same_year_collision_endpoint',
                        'source_evidence_verified_successor_event_endpoint'):
                if fld in r and truth(r[fld]):
                    if fld == 'source_evidence_same_year_collision_endpoint' and any(pair_resolutions.values()):
                        continue
                    allowed_pre_event = (fld == "source_evidence_verified_successor_event_endpoint" and k[:2] in manifest.get("_pre_event_pairs", set()))
                    if allowed_pre_event: continue
                    raise ValueError(f'global collision/event/federal block {fld}: {k}')
            row = dict(r)
            canonical = spec.get('canonical_columns', {})
            row['decision_id'] = (str(r[ccols['id']]) if ccols.get('id') else
                'reviewed-extension-' + hashlib.sha256('\x1f'.join(k).encode()).hexdigest()[:24])
            row['from_source_record_id'] = k[0]
            row['to_source_record_id'] = k[1]
            row['integration_rule_family'] = k[2]
            source_relation = str(r.get(canonical.get('relation','relation'), r.get('decision_relation','same_place')))
            if source_relation not in {'same_place', 'same_place_candidate'}:
                raise ValueError(f'unsupported reviewed identity relation: {source_relation}')
            row['source_candidate_relation_before_application'] = source_relation
            row['relation'] = 'same_place'
            row['decision_class'] = str(r.get(canonical.get('decision_class','decision_class'), k[2]))
            row['integration_layer'] = 'reviewed_extension_candidate'
            row['integration_source'] = str(r.get(canonical.get('source',''), 'independent_review_eligible_list'))
            row['decision_status'] = 'checked_rule_accepted'
            row['admission_status'] = 'checked_rule_accepted'
            row['candidate_only'] = False
            row['integration_review_status'] = 'accepted_after_manifest_pinned_independent_rule_review'
            row['reviewer'] = 'manifest_pinned_independent_review; root_application'
            row['reviewed_at'] = manifest['_reviewed_at']
            row['identity_review_receipt_sha256'] = receipt_sha
            resolved_endpoints = [pair_resolutions[sid] for sid in k[:2] if pair_resolutions[sid]]
            if resolved_endpoints:
                row['legacy_same_year_collision_original_flag_endpoint_ids_json'] = json.dumps(
                    [x['source_record_id'] for x in resolved_endpoints], ensure_ascii=False)
                row['legacy_collision_resolution_status'] = 'independently_resolved_legacy_crosswalk_collision'
                row['legacy_collision_resolution_records_json'] = json.dumps(resolved_endpoints, ensure_ascii=False, sort_keys=True)
            if k[2].startswith('R_H_'):
                row['application_raw_context_interpretation'] = (
                    'direct source district cell is blank and raw admin context remains unknown; '
                    'eligibility is grounded in exact whole-region unique typed name/region across '
                    'three years plus independently originated 2002/2021 points within 5 km; '
                    'candidate source context is preserved without asserting inherited context')
            accepted_frames.append(row)
            evidence[f'identity:{n}'] = {'candidate':str(cand_path),'sha256':candidate_sha,'eligible':str(elig_path),'eligible_sha256':eligible_sha,'review_receipt':str(receipt_path),'review_receipt_sha256':receipt_sha,'additional_review_receipts':extra_receipt_records}
    if accepted_frames:
        new = pd.DataFrame(accepted_frames)
        if {'decision_id'} <= set(new.columns) and new.decision_id.duplicated().any():
            raise ValueError('duplicate extension decision_id')
        evidence['legacy_collision_resolution_reviews'] = manifest.get('_legacy_collision_resolution_review_records', [])
        return new, evidence
    evidence['legacy_collision_resolution_reviews'] = manifest.get('_legacy_collision_resolution_review_records', [])
    return pd.DataFrame(), evidence


def load_direct_points(manifest):
    outputs, input_records = [], {}
    origin_hashes = {}
    for n, spec in enumerate(manifest['point_sources']):
        cand_path = pinned(spec['candidate'], f'point candidate {n}')
        approved_path = pinned(spec['approved'], f'point eligible list {n}')
        receipt_path = pinned(spec['review_receipt'], f'point review receipt {n}')
        extra_receipts = [pinned(x, f'point supplemental review receipt {n}')
                          for x in spec.get('additional_review_receipts', [])]
        extra_receipt_records = [{'path': str(p), 'sha256': sha(p)} for p in extra_receipts]
        origin_path = pinned(spec['origin'], f'point origin {n}')
        osha = spec['origin']['sha256']
        ccols, acols = spec['candidate_columns'], spec['approved_columns']
        candidate = read_table(cand_path)
        required_candidate={ccols[k] for k in ('target','latitude','longitude')}
        missing_candidate=required_candidate-set(candidate.columns)
        if missing_candidate: raise ValueError(f'point candidate missing mapped columns: {sorted(missing_candidate)}')
        approved = read_csv_rows(approved_path)
        # A linear pass and ID set avoid a per-candidate full-list scan.
        approved_by_id = {}
        for r in approved:
            rid = str(r[acols['target']]).strip()
            if not rid or rid in approved_by_id: raise ValueError(f'duplicate/blank approved point ID: {rid}')
            approved_by_id[rid] = r
        candidate_ids = candidate[ccols['target']].astype(str).str.strip()
        if candidate_ids.eq('').any() or candidate_ids.duplicated().any():
            raise ValueError('point candidate IDs must be nonblank and unique per source')
        chosen = candidate.loc[candidate_ids.isin(approved_by_id)].copy()
        present = set(chosen[ccols['target']].astype(str))
        if present != set(approved_by_id):
            missing = sorted(set(approved_by_id)-present)[:5]
            raise ValueError(f'approved point rows lack staged candidate payloads: {missing}')
        # Validate exact reviewed coordinates and the actual byte hash of origin.
        for r in chosen.to_dict('records'):
            rid = str(r[ccols['target']]).strip(); q = approved_by_id[rid]
            lat, lon = float(r[ccols['latitude']]), float(r[ccols['longitude']])
            if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f'impossible reviewed coordinates: {rid}')
            if float(r[ccols['latitude']]) != float(q[acols['latitude']]) or float(r[ccols['longitude']]) != float(q[acols['longitude']]):
                raise ValueError(f'reviewed point coordinate mismatch: {rid}')
            origin_file = str(r[ccols['origin_file']]) if ccols.get('origin_file') else str(origin_path)
            if Path(origin_file).resolve() != origin_path.resolve():
                raise ValueError(f'point origin path differs from manifest-pinned origin: {rid}')
            recorded_sha = str(r[ccols['origin_sha256']]) if ccols.get('origin_sha256') else osha
            if recorded_sha != osha:
                raise ValueError(f'point origin recorded hash differs from manifest: {rid}')
            for key, val in [('origin_file',origin_file),('origin_sha256',recorded_sha)]:
                approved_col=acols.get(key)
                if approved_col and str(q.get(approved_col,'')) != val:
                    raise ValueError(f'point origin {key} differs from independent eligible row: {rid}')
            approved_locator=acols.get('origin_locator')
            candidate_locator=(str(r[ccols['origin_locator']]) if ccols.get('origin_locator') else None)
            if approved_locator and candidate_locator is not None and str(q.get(approved_locator,'')) != candidate_locator:
                raise ValueError(f'point origin locator differs from independent eligible row: {rid}')
            if origin_file not in origin_hashes: origin_hashes[origin_file] = sha(Path(origin_file))
            if origin_hashes[origin_file] != osha: raise ValueError(f'point origin byte hash mismatch: {rid}')
        # Canonical target/coordinate/origin fields are explicit column mappings;
        # source provenance remains on each staged row alongside them.
        chosen['target_source_record_id'] = chosen[ccols['target']].astype(str)
        chosen['latitude'] = chosen[ccols['latitude']].astype(float)
        chosen['longitude'] = chosen[ccols['longitude']].astype(float)
        chosen['point_origin_sha256'] = (chosen[ccols['origin_sha256']].astype(str) if ccols.get('origin_sha256') else osha)
        if ccols.get('origin_file'):
            chosen['point_origin_file'] = chosen[ccols['origin_file']].astype(str)
        else:
            chosen['point_origin_file'] = str(origin_path)
        if ccols.get('origin_locator'):
            chosen['point_origin_locator'] = chosen[ccols['origin_locator']].astype(str)
        else:
            template=spec['origin'].get('locator_template')
            values=spec['origin'].get('locator_columns',{})
            if not template: raise ValueError('point source without row origin locator needs origin.locator_template')
            chosen['point_origin_locator']=[template.format(**{name:str(row[col]) for name,col in values.items()}) for row in chosen.to_dict('records')]
        for output_col, source_col in spec.get('output_columns',{}).items():
            chosen[output_col]=chosen[source_col]
        for output_col, value in spec.get('output_values',{}).items():
            chosen[output_col]=value
        # Preserve full candidate row, but only after explicit exact CSV approval.
        outputs.append(chosen)
        input_records[f'point:{n}'] = {'candidate':str(cand_path),'sha256':sha(cand_path),'approved':str(approved_path),'approved_sha256':sha(approved_path),'review_receipt':str(receipt_path),'review_receipt_sha256':sha(receipt_path),'additional_review_receipts':extra_receipt_records,'origin':str(origin_path),'origin_sha256':osha,'approved_count':len(approved)}
    return (pd.concat(outputs,ignore_index=True) if outputs else pd.DataFrame()), input_records


def run(manifest_path: Path, output: Path):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    target_fraction = float(manifest.get('current_user_goal_population_fraction', .99))
    if not 0 < target_fraction <= 1:
        raise ValueError('current_user_goal_population_fraction must be in (0,1]')
    requested = datetime.fromisoformat(manifest['reviewed_at_utc'].replace('Z','+00:00'))
    if requested.tzinfo is None: raise ValueError('reviewed_at_utc must include timezone')
    manifest['_reviewed_at'] = min(requested, datetime.now(timezone.utc)).isoformat()
    output = Path(output)
    if output.exists() and any(output.iterdir()): raise FileExistsError(f'output must be absent or empty: {output}')
    # Pin all fixed inputs before reading any of them.
    frozen = {k:pinned(v,f'frozen {k}') for k,v in manifest['frozen'].items()}
    base = {k:pinned(v,f'base {k}') for k,v in manifest['base'].items()}
    blocked_path = pinned(manifest['blocked_targets'],'blocked target list')
    fed_points_path = pinned(manifest['federal_points'],'federal points')
    fed_chains_path = pinned(manifest['federal_chains'],'federal chains')
    selected = pd.read_parquet(frozen['selected'])
    pre_event_scopes, pre_event_pairs, pre_event_pins = load_historical_pre_event_scopes(manifest, selected)
    manifest['_pre_event_pairs'] = pre_event_pairs
    collision_resolutions, collision_review_records = load_legacy_collision_resolution_reviews(manifest, selected)
    manifest['_legacy_collision_resolutions'] = collision_resolutions
    manifest['_legacy_collision_resolution_review_records'] = collision_review_records
    graph = pd.read_parquet(base['graph'])
    boolean_graph_columns = {field.name for field in pq.read_schema(base['graph'])
                             if pa.types.is_boolean(field.type)}
    base_graph_n = len(graph)
    new_graph, graph_inputs = load_identity(manifest)
    if not new_graph.empty:
        # Base graph remains byte-value-preserved row-for-row; only append.
        graph = pd.concat([graph,new_graph],ignore_index=True,sort=False)
    if graph.decision_id.astype(str).duplicated().any(): raise ValueError('decision_id collision with base graph')
    if not new_graph.empty:
        selected_ids=set(selected.source_record_id.astype(str))
        validate_historical_pre_event_pairs(new_graph, pre_event_scopes, pre_event_pairs)
        endpoints=set(new_graph.from_source_record_id.astype(str)) | set(new_graph.to_source_record_id.astype(str))
        if not endpoints.issubset(selected_ids):
            raise ValueError('reviewed identity edge has an endpoint outside frozen selected observations')
        if {'from_year','to_year'} <= set(new_graph.columns):
            same_year=new_graph.from_year.notna() & new_graph.to_year.notna() & (new_graph.from_year.astype(str)==new_graph.to_year.astype(str))
            if same_year.any(): raise ValueError('same-year identity extension is prohibited')
        graph.loc[graph.index[-len(new_graph):],'selection_projection_status']='active_endpoints_selected'
    linked, full, components = identity_sets(selected, graph)
    validate_components_have_unique_years(selected,components)
    points = pd.read_parquet(base['points'])
    boolean_point_columns = set(points.select_dtypes(include=['bool', 'boolean']).columns)
    # Physical Arrow bool columns can retain old pandas object metadata after a
    # canonical projection, so dtype inference alone misses these known flags.
    boolean_point_columns.update({'boundary_comparability_asserted',
        'population_scope_comparability_asserted', 'direct_historical_coordinate_measurement',
        'coordinate_measurement_date_unknown'})
    # The third application serialized this particular false/unknown flag as
    # VARCHAR. Recover its type explicitly without promoting unknown to false.
    if 'census_date_point_measurement_proven' in points:
        boolean_point_columns.add('census_date_point_measurement_proven')
    if points.target_source_record_id.astype(str).duplicated().any(): raise ValueError('base points contain duplicate targets')
    base_point_ids = set(points.target_source_record_id.astype(str))
    blocked=read_blocked_targets(blocked_path)
    # A separate raw-publication review supersedes only these old-city uses.
    blocked_for_application = blocked - set(pre_event_scopes)
    direct, point_inputs = load_direct_points(manifest)
    if not direct.empty:
        if 'target_source_record_id' not in direct:
            raise ValueError('point candidate missing canonical target_source_record_id')
        # Only new target IDs are eligible; an existing target is preserved and skipped.
        direct_ids=direct.target_source_record_id.astype(str)
        excluded_direct_ids=set().union(*(set(x.get('exclude_target_ids',[])) for x in manifest['point_sources']))
        direct = direct.loc[~direct_ids.isin(base_point_ids | blocked_for_application | excluded_direct_ids)].copy()
        if direct.target_source_record_id.astype(str).duplicated().any(): raise ValueError('duplicate direct point target')
        if 'candidate_only' in direct:
            direct['source_candidate_only_before_application'] = direct['candidate_only']
        direct['candidate_only'] = False
        direct['coordinate_admission_status']='reviewed_extension_rule_accepted'
        if 'coordinate_quality' not in direct:
            direct['coordinate_quality']='automatically_accepted_checked_rule'
        direct['coordinate_admitted']=True; direct['point_admitted']=True; direct['admission_allowed']=True
        direct['integration_review_status']='accepted_after_manifest_pinned_independent_point_review'
        direct['review_id']='manifest_pinned_point_extension_20261004'
        direct['reviewed_at']=manifest['_reviewed_at']
        points=pd.concat([points,direct],ignore_index=True,sort=False)
    if points.target_source_record_id.astype(str).duplicated().any(): raise ValueError('duplicate point targets after direct extensions')
    point_ids, get_point_carrier = lazy_point_carriers(points)
    # One source-evidence scan for all newly reviewed point targets, edge
    # endpoints, and unpointed component members. This checks authoritative
    # source flags rather than trusting candidate convenience columns.
    needed=set().union(*components) - point_ids if components else set()
    if not new_graph.empty:
        needed |= set(new_graph.from_source_record_id.astype(str)) | set(new_graph.to_source_record_id.astype(str))
    if not direct.empty: needed |= set(direct.target_source_record_id.astype(str))
    con=duckdb.connect(config={'threads':1})
    con.register('needed_ids',pd.DataFrame({'source_record_id':list(needed)}))
    evidence={r.source_record_id:json.loads(r.source_evidence_json) for r in con.execute(
       f"SELECT e.source_record_id,e.source_evidence_json FROM read_parquet('{frozen['source_evidence']}') e JOIN needed_ids n USING(source_record_id)").fetchdf().itertuples(index=False)}
    if not new_graph.empty:
        validate_identity_source_evidence(new_graph,evidence,pre_event_scopes,collision_resolutions)
    if not direct.empty:
        selected_by_id=selected.set_index('source_record_id',drop=False)
        for r in direct.itertuples(index=False):
            sid=str(r.target_source_record_id)
            if sid not in selected_by_id.index: raise ValueError(f'point target not selected: {sid}')
            ev=evidence.get(sid)
            validate_direct_point_source_evidence(ev,sid,pre_event_scopes)
            if sid in pre_event_scopes:
                scope = pre_event_scopes[sid]
                if (float(r.latitude) != scope['latitude'] or float(r.longitude) != scope['longitude'] or
                    str(r.point_origin_sha256) != scope['origin_sha256'] or
                    Path(str(r.point_origin_file)).resolve() != Path(scope['origin_file']).resolve()):
                    raise ValueError('pre-event point differs from the independently reviewed old-city raw point')
            if not math.isfinite(float(r.latitude)) or not math.isfinite(float(r.longitude)):
                raise ValueError(f'point target has nonfinite coordinates: {sid}')
    target_rows=selected.set_index('source_record_id',drop=False)
    years=selected.set_index('source_record_id').census_year.to_dict()
    adjacency=defaultdict(list)
    graph_rows_by_decision={}
    for r in graph[['decision_id','from_source_record_id','to_source_record_id']].itertuples(index=False):
        adjacency[str(r.from_source_record_id)].append((str(r.to_source_record_id),str(r.decision_id)))
        adjacency[str(r.to_source_record_id)].append((str(r.from_source_record_id),str(r.decision_id)))
    collision_meta_columns=['decision_id','from_source_record_id','to_source_record_id',
        'legacy_same_year_collision_original_flag_endpoint_ids_json','legacy_collision_resolution_records_json']
    if set(collision_meta_columns).issubset(graph.columns):
        meta=graph.loc[graph['legacy_same_year_collision_original_flag_endpoint_ids_json'].fillna('').astype(str).str.len().gt(2),collision_meta_columns]
        for r in meta.itertuples(index=False):
            graph_rows_by_decision[str(r.decision_id)]={'from_source_record_id':r.from_source_record_id,
                'to_source_record_id':r.to_source_record_id,
                'legacy_same_year_collision_original_flag_endpoint_ids_json':r.legacy_same_year_collision_original_flag_endpoint_ids_json,
                'legacy_collision_resolution_records_json':r.legacy_collision_resolution_records_json}
    propagated,holds=[],[]
    for members in components:
        missing=members-point_ids
        if not missing: continue
        seeds=[get_point_carrier(sid) for sid in members if sid in point_ids and sid not in blocked_for_application]
        if not seeds: continue
        spread=max((distance(x,y) for x,y in itertools.combinations(seeds,2)),default=0)
        if spread>5:
            holds.append({'members_json':json.dumps(sorted(members)),'hold':'accepted_point_witness_spread_over_5km','spread_km':spread}); continue
        carrier=min(seeds,key=lambda r:(-int(years[str(r['target_source_record_id'])]),str(r['target_source_record_id'])))
        origin=str(carrier['target_source_record_id']); pred={origin:None}; queue=deque([origin])
        while queue:
            sid=queue.popleft()
            for nxt,did in sorted(adjacency[sid]):
                if nxt not in pred: pred[nxt]=(sid,did); queue.append(nxt)
        for target in sorted(missing):
            e=evidence.get(target,{})
            if target not in pred:
                holds.append({'target_source_record_id':target,'hold':'no_accepted_graph_path_to_point_seed'}); continue
            if (target in blocked_for_application or not truth(e.get('is_additive_settlement_record')) or
                truth(e.get('is_federal_aggregate')) or
                (e.get('legacy_verified_successor_settlement_id') and target not in pre_event_scopes)):
                holds.append({'target_source_record_id':target,'hold':'federal_event_or_global_block'}); continue
            path=[]; node=target
            while node!=origin:
                node,did=pred[node]; path.append(did)
            collision_path=[]
            for did in path:
                edge=graph_rows_by_decision.get(str(did),{})
                try: flagged=json.loads(edge.get('legacy_same_year_collision_original_flag_endpoint_ids_json','[]') or '[]')
                except Exception: flagged=[]
                if flagged:
                    collision_path.append({'decision_id':str(did),'from_source_record_id':str(edge.get('from_source_record_id')),
                        'to_source_record_id':str(edge.get('to_source_record_id')),'flagged_endpoint_ids':flagged,
                        'resolution_records_json':edge.get('legacy_collision_resolution_records_json','[]')})
            if e.get('legacy_same_year_collision') and not any(target in x['flagged_endpoint_ids'] for x in collision_path):
                holds.append({'target_source_record_id':target,'hold':'authoritative_same_year_collision_not_resolved_on_exact_accepted_identity_path'}); continue
            row=stage_point_use(target_rows.loc[target],e,carrier,origin,e,path)
            row['source_candidate_only_before_application'] = row.get('candidate_only')
            row['candidate_only'] = False
            row.update(coordinate_admission_status='reviewed_extension_rule_accepted',
                coordinate_quality='automatically_accepted_checked_rule',
                coordinate_application_family='R_reviewed_same_place_sourced_point_continuity_20261004',
                application_inference_kind='sourced_representative_point_reuse_across_accepted_observed_years',
                native_id_binding_asserted=False,
                provider_binding_status='point_origin_binding_only_not_target_native_identifier',
                coordinate_admitted=True,point_admitted=True,admission_allowed=True,
                review_id='manifest_pinned_continuity_application_20261004',
                application_gate_status='passed_accepted_graph_sourced_point_continuity',
                coordinate_application_review_sha256=sha(manifest_path),
                accepted_component_point_spread_km=spread)
            if collision_path:
                row['legacy_same_year_collision_original_flag'] = bool(e.get('legacy_same_year_collision'))
                row['legacy_collision_resolution_path_json'] = json.dumps(collision_path,ensure_ascii=False,sort_keys=True)
            propagated.append(row)
    if propagated: points=pd.concat([points,pd.DataFrame(propagated)],ignore_index=True,sort=False)
    if points.target_source_record_id.astype(str).duplicated().any(): raise ValueError('duplicate point target after continuity')
    points = preserve_nullable_booleans(points, boolean_point_columns)
    # Outputs are written only after all application gates above pass.
    graph = preserve_nullable_booleans(graph, boolean_graph_columns)
    output.mkdir(parents=True,exist_ok=True)
    graph.to_parquet(output/'accepted_identity_edges.parquet',index=False)
    con.register('final_points',points)
    con.execute(f"COPY final_points TO '{output/'accepted_point_uses.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    pd.DataFrame(holds).to_csv(output/'point_continuity_holds.csv',index=False)
    legacy=pd.read_parquet(frozen['legacy_availability'])
    selected['is_federal_aggregate_from_grain_evidence']=selected.population_scope.eq('federal_city_region')
    federal_ids=set(pd.read_parquet(fed_points_path).source_record_id.astype(str))
    selected.loc[selected.source_record_id.astype(str).isin(federal_ids),'is_federal_aggregate_from_grain_evidence']=True
    coverage=measure(selected,legacy,graph,points,{2002:145166731,2010:142856536,2021:147182123})
    fed_chains=pd.read_parquet(fed_chains_path); fed_full=set()
    for r in fed_chains.itertuples():
        if r.chain_status=='continuing_city_three_observed_censuses_changing_population_scope': fed_full.update(json.loads(r.source_record_ids_json))
    mixed_joint=(full|fed_full)&(set(points.target_source_record_id.astype(str))|federal_ids)
    coverage['current_user_target_fraction']=target_fraction
    coverage['mixed_scope_joint_coordinate_and_three_observed_censuses']=[]
    for year,g in selected.groupby('census_year'):
        control={2002:145166731,2010:142856536,2021:147182123}[int(year)]
        covered=g.source_record_id.astype(str).isin(mixed_joint); population=int(g.loc[covered,'population'].sum())
        coverage['mixed_scope_joint_coordinate_and_three_observed_censuses'].append({'year':int(year),'rows':int(covered.sum()),'row_fraction':float(covered.mean()),'known_population':population,'official_control_population_fraction':population/control,'remaining_population_to_99':max(0,math.ceil(control*.99)-population),'scope':'physical NP plus separately accepted continuing federal-city identity with changing observation grain','parent_child_rule':'exclusive parent; no federal children added in current selected layer','boundary_population_comparability_asserted':False})
        coverage['mixed_scope_joint_coordinate_and_three_observed_censuses'][-1]['remaining_population_to_target']=max(0,math.ceil(control*target_fraction)-population)
    for r in coverage['census_metrics']: r['original_quality_target_fraction']=.999
    (output/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
    selected.assign(joint_full=selected.source_record_id.astype(str).isin(full & set(points.target_source_record_id.astype(str)))).query('not joint_full').sort_values('population',ascending=False).to_parquet(output/'joint_residual.parquet',index=False)
    receipt={'status':'applied_manifest_pinned_reviewed_mass_extensions','base_graph_rows':base_graph_n,'accepted_graph_rows':len(graph),'new_identity_rows':len(new_graph),'new_direct_point_uses':len(direct),'new_continuity_point_uses':len(propagated),'full_census_components':len(full)//3,'application_reviewed_at_utc':manifest['_reviewed_at'],'source_population_values_modified':False,'historical_pre_event_scoped_reviews':pre_event_pins,'legacy_collision_resolution_reviews':collision_review_records,'manifest_path':str(manifest_path),'manifest_sha256':sha(manifest_path),'script_sha256':sha(Path(__file__)),'inputs':{'frozen':{k:{'path':str(v),'sha256':sha(v)} for k,v in frozen.items()},'base':{k:{'path':str(v),'sha256':sha(v)} for k,v in base.items()},'identity':graph_inputs,'points':point_inputs,'blocked_targets':{'path':str(blocked_path),'sha256':sha(blocked_path)},'federal_points':{'path':str(fed_points_path),'sha256':sha(fed_points_path)},'federal_chains':{'path':str(fed_chains_path),'sha256':sha(fed_chains_path)}},'outputs':{p.name:sha(p) for p in output.iterdir() if p.is_file()}}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--manifest',required=False)
    ap.add_argument('--output',required=False)
    ap.add_argument('--example-manifest',action='store_true')
    args=ap.parse_args()
    if args.example_manifest:
        print(json.dumps(example_manifest(),ensure_ascii=False,indent=2))
    else:
        if not args.manifest or not args.output: ap.error('--manifest and --output are required')
        run(Path(args.manifest),Path(args.output))
