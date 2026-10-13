#!/usr/bin/env python3
"""Stage candidate-only stable-type historical classifier corridor edges.

For selected old census rows and exact-name/type/region-unique 2021 rows, this
generator checks a literal 2009 OKATO SQL record and a live typed 2011
GeoKLADR object/point, then compares that raw point with a direct accepted
2021 point. It preserves opaque census source IDs and records no admissions,
legal events, or population-boundary comparability claims.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import duckdb

W = Path('/workspace')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(W / 'russian-settlements-research/research_rebuild/mass_linkage'))
from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, ACCEPTED_PROJECTION_STATUSES
from stage_rural_native_okato_points_20261004 import raw_sql_row, raw_dbf_rows, sha

F = W / 'settlements-delivery/continuation-consolidated-20261003'
C = W / 'settlements-work/continuation_20261004'
OUT_DEFAULT = C / 'R4/stable_type_corridor_mass_v2'
SELECTED = F / 'selected_observations.parquet'
SOURCE_EVIDENCE = F / 'source_evidence.parquet'
INPUT_MANIFEST = F / 'input_manifest.parquet'
RESIDUAL = C / 'accepted_mass_extensions/joint_residual.parquet'
GRAPH = C / 'accepted_mass_extensions/accepted_identity_edges.parquet'
POINTS = C / 'accepted_mass_extensions/accepted_point_uses.parquet'
HIST = W / 'settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet'
RAW_SQL = W / 'settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
RAW_DBF = W / 'settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
PRIMARY_V3 = C / 'root/R4/temporal_mass/primary_comparison_extension/review_freeze_v3/staged_identity_edges.csv'
TYPE_EDGES = C / 'R4/type_change_mass/staged_status_change_edges.csv'
TYPE_ALL = C / 'R4/type_change_mass/observed_type_change_event_pairs.csv'
BLOCKED = W / 'settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json'
QUARANTINES = [W / 'settlements-work/continuation_20261003' / name for name in (
    'mezhgorye_quarantine_decision.json', 'podlipkovsky_point_hold_decision_v1.json',
    'rural_shared_point_quarantine_decision.json')]
YEARS = (2002, 2010, 2021)
PHYSICAL_TYPES = {'деревня', 'село', 'поселок', 'посёлок', 'город', 'пгт', 'станица',
                  'хутор', 'аул', 'кишлак', 'слобода', 'арбан', 'выселок', 'починок',
                  'местечко', 'разъезд', 'станция'}
BAD_GRAINS = {'federal_city_region', 'federal_territory', 'municipality', 'region',
              'territorial_aggregate', 'federal_city', 'federal_city_aggregate'}


def norm(v):
    if v is None or pd.isna(v):
        return ''
    s = unicodedata.normalize('NFKC', str(v)).casefold().replace('ё', 'е').replace('\xa0', ' ')
    return ' '.join(s.split())


def compact(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'), sort_keys=True, default=str)


def blank(v):
    return v is None or pd.isna(v) or not str(v).strip()


def truth(v):
    return not blank(v) and str(v).casefold() in {'true', '1', 't', 'yes'}


def false(v):
    return v is False or (not blank(v) and str(v).casefold() in {'false', '0', 'f', 'no'})


def js(v):
    if isinstance(v, dict):
        return v
    if blank(v):
        return {}
    try:
        return json.loads(v)
    except Exception:
        return {}


def code(v):
    if blank(v):
        return ''
    s = str(v).strip()
    return re.sub(r'\.0$', '', s)


def classifier_type(v):
    s = norm(v)
    return {
        'деревня': 'деревня', 'село': 'село', 'поселок': 'поселок', 'посёлок': 'поселок',
        'поселок городского типа': 'пгт', 'посёлок городского типа': 'пгт', 'пгт': 'пгт',
        'город': 'город', 'станица': 'станица', 'хутор': 'хутор', 'аул': 'аул',
        'кишлак': 'кишлак', 'слобода': 'слобода', 'арбан': 'арбан', 'выселок': 'выселок',
        'починок': 'починок', 'местечко': 'местечко', 'разъезд': 'разъезд', 'станция': 'станция',
    }.get(s, '')


def hav(a, b):
    p1, p2 = map(math.radians, (a[0], b[0]))
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    z = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(z))


class DSU:
    def __init__(self, frame):
        self.ids = frame.source_record_id.astype(str).tolist()
        self.ix = {sid: i for i, sid in enumerate(self.ids)}
        if len(self.ix) != len(self.ids):
            raise ValueError('duplicate selected source_record_id')
        self.p = list(range(len(self.ids)))
        self.rank = [0] * len(self.ids)
        yr = dict(zip(frame.source_record_id.astype(str), frame.census_year.astype(int)))
        bit = {2002: 1, 2010: 2, 2021: 4}
        self.mask = [bit[yr[sid]] for sid in self.ids]

    def find(self, i):
        p = self.p[i]
        while p != self.p[p]:
            p = self.p[p]
        while i != p:
            q = self.p[i]
            self.p[i] = p
            i = q
        return p

    def root(self, sid):
        return self.find(self.ix[str(sid)])

    def union(self, a, b, check=False):
        x, y = self.root(a), self.root(b)
        if x == y:
            return 'already_connected'
        if check and self.mask[x] & self.mask[y]:
            return 'same_year_component_collision'
        if self.rank[x] < self.rank[y]:
            x, y = y, x
        self.p[y] = x
        self.mask[x] |= self.mask[y]
        if self.rank[x] == self.rank[y]:
            self.rank[x] += 1
        return 'merged'


def load_excluded_pairs(path, edge_file):
    if not path.is_file():
        return set()
    excluded = set()
    with path.open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            a = r.get('from_source_record_id') or r.get('from_source_id')
            b = r.get('to_source_record_id') or r.get('to_source_id')
            if a and b:
                excluded.add(tuple(sorted((a, b))))
    return excluded


def point_direct(row):
    # Only the canonical admission status decides acceptance. Imported nullable
    # convenience flags are deliberately ignored.
    return (str(row.coordinate_admission_status) in ACCEPTED_COORDINATE_STATUSES
            and int(row.target_year) == 2021
            and blank(row.inference_modern_point_use_target_source_record_id)
            and blank(row.inference_identity_path_decision_ids_json)
            and not str(row.point_origin_kind or '').startswith('retrospective_')
            and not pd.isna(row.latitude) and not pd.isna(row.longitude))


def coverage(frame, dsu, point_ids):
    years = {sid: y for sid, y in zip(frame.source_record_id.astype(str), frame.census_year.astype(int))}
    members = defaultdict(list)
    for sid in dsu.ids:
        members[dsu.root(sid)].append(sid)
    full = {root for root, ids in members.items() if {years[x] for x in ids} >= set(YEARS)}
    totals = {y: {'full_rows': 0, 'full_population': 0, 'joint_rows': 0, 'joint_population': 0}
              for y in YEARS}
    for r in frame.itertuples(index=False):
        sid = str(r.source_record_id)
        root = dsu.root(sid)
        y = int(r.census_year)
        pop = 0 if pd.isna(r.population) else int(r.population)
        if root in full:
            totals[y]['full_rows'] += 1
            totals[y]['full_population'] += pop
        # The target is row-level joint coverage: the census row itself needs
        # an admitted coordinate and a full identity chain. A point attached
        # only to another year's observation does not satisfy this axis.
        if root in full and sid in point_ids:
            totals[y]['joint_rows'] += 1
            totals[y]['joint_population'] += pop
    return totals


def main(out: Path):
    if out.exists():
        raise FileExistsError(f'Use a new immutable output directory: {out}')
    inputs = [SELECTED, SOURCE_EVIDENCE, INPUT_MANIFEST, RESIDUAL, GRAPH, POINTS, HIST,
              RAW_SQL, RAW_DBF, PRIMARY_V3, TYPE_EDGES, TYPE_ALL, BLOCKED] + [p for p in QUARANTINES if p.exists()]
    pins = {str(p): sha(p) for p in inputs}
    sql_hash = pins[str(RAW_SQL)]
    dbf_hash = pins[str(RAW_DBF)]

    # Load the complete selected census graph frame. Status sets are the same
    # canonical source-of-truth sets used by build_long_table.
    selected_cols = ['source_record_id', 'census_year', 'source_file', 'source_sheet', 'source_row',
                     'source_native_id', 'source_name_raw', 'settlement_name', 'settlement_type',
                     'region_raw', 'region_norm', 'district_raw', 'municipality_raw', 'population',
                     'population_scope', 'is_additive_settlement_record', 'source_sha256', 'source_locator',
                     'okato', 'oktmo']
    selected = pd.read_parquet(SELECTED, columns=selected_cols)
    selected = selected[selected.census_year.isin(YEARS)].copy()
    selected['source_record_id'] = selected.source_record_id.astype(str)
    selected['census_year'] = selected.census_year.astype(int)
    selected['name_key'] = selected.settlement_name.map(norm)
    selected['region_key'] = selected.region_norm.map(norm)
    selected['type_key'] = selected.settlement_type.map(norm)
    selected['district_key'] = selected.district_raw.map(norm)

    # The accepted inputs must be complete and status-recognized; never infer
    # admission from optional nullable booleans.
    graph = pd.read_parquet(GRAPH)
    if graph.decision_status.isna().any() or not graph.decision_status.astype(str).isin(ACCEPTED_EDGE_STATUSES).all():
        raise ValueError('accepted graph contains missing or unrecognized canonical decision status')
    if graph.selection_projection_status.isna().any() or not graph.selection_projection_status.astype(str).isin(ACCEPTED_PROJECTION_STATUSES).all():
        raise ValueError('accepted graph contains missing or unrecognized canonical selection projection status')
    point_cols = ['target_source_record_id', 'target_year', 'latitude', 'longitude',
                  'coordinate_admission_status', 'inference_modern_point_use_target_source_record_id',
                  'inference_identity_path_decision_ids_json', 'point_origin_kind', 'point_origin_file',
                  'point_origin_sha256', 'point_origin_locator', 'coordinate_source_file',
                  'coordinate_source_sha256', 'coordinate_source_locator', 'application_gate_status']
    points = pd.read_parquet(POINTS, columns=point_cols)
    if points.coordinate_admission_status.isna().any() or not points.coordinate_admission_status.astype(str).isin(ACCEPTED_COORDINATE_STATUSES).all():
        raise ValueError('accepted point ledger contains missing or unrecognized canonical admission status')
    accepted_point_rows = len(points)
    coordinate_status_counts = dict(points.coordinate_admission_status.astype(str).value_counts())
    # Build candidate endpoints first; retain direct point geometry only for
    # potential 2021 anchors and the old residual rows.
    residual = pd.read_parquet(RESIDUAL, columns=['source_record_id', 'census_year', 'population'])
    residual_ids = set(residual.source_record_id.astype(str))
    old = selected[selected.census_year.isin([2002, 2010]) & selected.source_record_id.isin(residual_ids)].copy()
    counts = selected.groupby(['census_year', 'name_key', 'region_key'], dropna=False).source_record_id.nunique().to_dict()
    bykey = defaultdict(lambda: defaultdict(list))
    for r in selected.itertuples(index=False):
        if r.name_key and r.region_key:
            bykey[(r.name_key, r.region_key)][int(r.census_year)].append(r)
    preliminary_pairs = []
    for r in old.itertuples(index=False):
        yrs = bykey.get((r.name_key, r.region_key), {})
        modern = yrs.get(2021, [])
        if len(modern) != 1 or norm(r.settlement_type) not in PHYSICAL_TYPES or norm(modern[0].settlement_type) not in PHYSICAL_TYPES:
            continue
        if norm(r.settlement_type) != norm(modern[0].settlement_type):
            continue
        if counts.get((int(r.census_year), r.name_key, r.region_key), 0) == 1 and counts.get((2021, r.name_key, r.region_key), 0) == 1:
            if int(r.census_year) == 2002:
                mid10 = yrs.get(2010, [])
                if len(mid10) == 1 and norm(mid10[0].settlement_type) == norm(r.settlement_type) and counts.get((2010, r.name_key, r.region_key), 0) == 1:
                    preliminary_pairs.append((r, mid10[0], modern[0]))
            preliminary_pairs.append((r, modern[0], modern[0]))
    potential_target_ids = {str(w.source_record_id) for _, _, w in preliminary_pairs}
    potential_old_ids = {str(r.source_record_id) for r, _, _ in preliminary_pairs}
    needed_point_targets = potential_target_ids | potential_old_ids
    # Shared source IDs can have status-preserved duplicates across legacy rows;
    # collect all accepted point targets for coverage and only retain coordinates
    # for candidate endpoints to keep the run within memory limits.
    point_coords = defaultdict(list)
    direct_2021 = defaultdict(list)
    base_point_ids = set()
    for p in points.itertuples(index=False):
        sid = str(p.target_source_record_id)
        if str(p.coordinate_admission_status) in ACCEPTED_COORDINATE_STATUSES:
            base_point_ids.add(sid)
        if sid in needed_point_targets and not pd.isna(p.latitude) and not pd.isna(p.longitude):
            point_coords[sid].append((float(p.latitude), float(p.longitude)))
        if sid in potential_target_ids and point_direct(p):
            direct_2021[sid].append({
                'lat': float(p.latitude), 'lon': float(p.longitude),
                'point_origin_kind': p.point_origin_kind, 'point_origin_file': p.point_origin_file,
                'point_origin_sha256': p.point_origin_sha256, 'point_origin_locator': p.point_origin_locator,
                'coordinate_source_file': p.coordinate_source_file, 'coordinate_source_sha256': p.coordinate_source_sha256,
                'coordinate_source_locator': p.coordinate_source_locator,
                'coordinate_admission_status': p.coordinate_admission_status,
                'application_gate_status': p.application_gate_status,
            })
    if sum(len(v) for v in direct_2021.values()) == 0:
        raise ValueError('no canonical direct accepted 2021 point witnesses loaded')

    del points
    # All-type, whole-region exact-name uniqueness was calculated from the
    # selected frame above. Do not retain wide evidence payloads for all rows.

    # Exclude frozen primary comparison and the type-change cohort by exact
    # source endpoint IDs. Key-wide type-change exclusions are unnecessary once
    # both source type labels are verified equal below.
    excluded = load_excluded_pairs(PRIMARY_V3, 'primary')
    for file in (TYPE_EDGES, TYPE_ALL):
        excluded |= load_excluded_pairs(file, 'type')

    # Hard point quarantines remain hard. Other legacy pointer/text-similarity/
    # ordinal hypotheses are retained as warnings and do not decide this route.
    hard = set(json.loads(BLOCKED.read_text()).get('blocked_target_source_record_ids', []))
    for p in QUARANTINES:
        if p.exists():
            hard.update(json.loads(p.read_text()).get('quarantine_target_source_record_ids', []))

    # Pre-index exact raw named typed historical objects. Objects without live
    # physical status, code bridge, raw geometry, or region concordance are held.
    hist_cols = ['historical_okato_2009_raw', 'name_raw_2009', 'name', 'status', 'is_settlement_raw',
                 'source_line_1based', 'source_sha256_2009', 'source_snapshot_version',
                 'historical_okato_2011_raw', 'record_number_1based', 'record_byte_offset_0based',
                 'is_deleted', 'kod3_raw_text', 'name_raw_2011', 'settlement_type_raw',
                 'latitude_from_lat', 'longitude_from_long', 'source_sha256_2011',
                 'historical_point_modern_region', 'historical_key_region_name_type_count',
                 'historical_name_exact', 'historical_type_exact']
    h = pd.read_parquet(HIST, columns=hist_cols)
    h = h[(h.is_settlement_raw.astype(str).str.casefold().eq('t')) & (~h.is_deleted.fillna(False)) &
          h.historical_name_exact.eq(True) & h.historical_type_exact.eq(True) &
          h.historical_point_modern_region.notna() & h.latitude_from_lat.notna() & h.longitude_from_long.notna()].copy()
    # `name` is the parser's exact locality token, while name_raw_2009 is the
    # source-faithful label retaining the classifier type prefix (e.g. "с X").
    # Join on parsed token; retain the raw label as proof. Prefix stripping is
    # not guessed here: this field comes from the established source parser.
    h['name_key'] = h.name.map(norm)
    h['type_key'] = h.status.map(classifier_type)
    h['region_key'] = h.historical_point_modern_region.map(norm)
    h = h[h.type_key.ne('')].copy()
    h_counts = h.groupby(['name_key', 'type_key', 'region_key']).size().to_dict()
    hist_by = defaultdict(list)
    for q in h.itertuples(index=False):
        hist_by[(q.name_key, q.type_key, q.region_key)].append(q)

    # Read raw classifier SQL once. Candidates later reopen the exact SQL line
    # and DBF record locators emitted by the historical named-object cache.
    with RAW_SQL.open('r', encoding='utf-8', newline='') as f:
        sql_lines = f.readlines()

    # Candidate discovery: exact stable type/name/region in one old census and
    # 2021; unique across all types per endpoint year; source row is in the
    # accepted extension residual. No fuzzy name or proximity discovery.
    provisional = []
    discovery_holds = Counter()
    for r in old.itertuples(index=False):
        key = (r.name_key, r.region_key)
        yrs = bykey.get(key, {})
        modern = yrs.get(2021, [])
        if len(modern) != 1:
            discovery_holds['no_unique_2021_exact_whole_region_name_record'] += 1
            continue
        m = modern[0]
        if norm(r.settlement_type) not in PHYSICAL_TYPES or norm(m.settlement_type) not in PHYSICAL_TYPES:
            discovery_holds['type_outside_physical_settlement_scope'] += 1
            continue
        if norm(r.settlement_type) != norm(m.settlement_type):
            discovery_holds['type_changed_reserved_to_type_change_agent'] += 1
            continue
        if counts.get((int(r.census_year), r.name_key, r.region_key), 0) != 1 or counts.get((2021, r.name_key, r.region_key), 0) != 1:
            discovery_holds['whole_region_name_not_unique_across_types_or_source_rows'] += 1
            continue
        if int(r.census_year) == 2002:
            mid10 = yrs.get(2010, [])
            if len(mid10) == 1 and norm(mid10[0].settlement_type) == norm(r.settlement_type) and counts.get((2010, r.name_key, r.region_key), 0) == 1:
                pair10 = tuple(sorted((str(r.source_record_id), str(mid10[0].source_record_id))))
                if pair10 not in excluded:
                    provisional.append((r, mid10[0], m))
                else:
                    discovery_holds['frozen_primary_or_type_change_exact_pair_exclusion'] += 1
        pair = tuple(sorted((str(r.source_record_id), str(m.source_record_id))))
        if pair in excluded:
            discovery_holds['frozen_primary_or_type_change_exact_pair_exclusion'] += 1
            continue
        provisional.append((r, m, m))

    for r, target, witness in provisional:
        if int(witness.census_year) != 2021:
            raise ValueError(f'point witness is not a 2021 selected row: {witness.source_record_id}')
        if not (norm(r.settlement_name) == norm(target.settlement_name) == norm(witness.settlement_name)
                and norm(r.region_norm) == norm(target.region_norm) == norm(witness.region_norm)
                and norm(r.settlement_type) == norm(target.settlement_type) == norm(witness.settlement_type)):
            raise ValueError(f'corridor triple violates exact stable name/type/region: {r.source_record_id} -> {target.source_record_id} -> {witness.source_record_id}')
        if int(target.census_year) == 2021 and str(target.source_record_id) != str(witness.source_record_id):
            raise ValueError('2021 target must itself be its direct-point witness')

    # Filter source evidence to the precise endpoint IDs already discovered.
    # This avoids materializing the full set of long JSON evidence rows.
    evidence_ids = sorted({str(x.source_record_id) for pair in provisional for x in pair})
    id_frame = pd.DataFrame({'source_record_id': evidence_ids})
    evidence_db = duckdb.connect()
    evidence_db.register('candidate_ids', id_frame)
    evidence_rows = evidence_db.execute(
        "SELECT e.source_record_id, e.source_evidence_json "
        f"FROM read_parquet('{SOURCE_EVIDENCE}') e INNER JOIN candidate_ids c USING(source_record_id)"
    ).fetchall()
    evidence_db.close()
    evidence_raw = {str(sid): str(raw) for sid, raw in evidence_rows}
    evidence_map = {sid: js(raw) for sid, raw in evidence_raw.items()}
    if set(evidence_raw) != set(evidence_ids):
        raise ValueError(f'source evidence missing for {len(set(evidence_ids)-set(evidence_raw))} exact corridor endpoint(s)')

    # Retain unique historic raw classifier/point objects and compute direct
    # 2021 witness distances. Each GeoKLADR object has a literal 2009 code line.
    candidates = []
    holds = []
    dbf_needed = []
    for r, m, w in provisional:
        why = []
        rid, mid, wid = str(r.source_record_id), str(m.source_record_id), str(w.source_record_id)
        er, em, ew = evidence_map.get(rid, {}), evidence_map.get(mid, {}), evidence_map.get(wid, {})
        typ, nk, rk = norm(r.settlement_type), r.name_key, r.region_key
        hist_rows = hist_by.get((nk, classifier_type(typ), rk), [])
        if h_counts.get((nk, classifier_type(typ), rk), 0) != 1 or len(hist_rows) != 1:
            holds.append({'from_source_record_id': rid, 'to_source_record_id': mid,
                          'from_year': int(r.census_year), 'to_year': 2021,
                          'from_population': r.population, 'to_population': m.population,
                          'rule_family': 'stable_type_raw_okato_geokladr_direct_2021_corridor',
                          'hold_reason': 'historical_named_typed_point_not_unique_in_region'})
            continue
        q = hist_rows[0]
        # Hold explicit source-context contradictions but do not inherit legacy
        # pointer mismatch flags as proof of physical ambiguity.
        district_contexts = [norm(x) for x in (r.district_raw, m.district_raw, w.district_raw) if not blank(x)]
        if len(set(district_contexts)) > 1:
            why.append('explicit_source_district_context_differs')
        for x, e, label in ((r, er, 'from'), (m, em, 'to'), (w, ew, 'point_witness')):
            if not truth(x.is_additive_settlement_record) or not truth(e.get('is_additive_settlement_record')):
                why.append(label + '_not_explicitly_additive_settlement_record')
            if truth(e.get('is_federal_aggregate')) or norm(x.population_scope) in BAD_GRAINS:
                why.append(label + '_federal_or_nonphysical_grain_hard_block')
            if truth(e.get('legacy_same_year_collision')):
                why.append(label + '_source_evidence_same_year_collision')
            if e.get('legacy_verified_successor_settlement_id'):
                why.append(label + '_source_evidence_verified_successor_event')
            if str(x.source_record_id) in hard:
                why.append(label + '_point_quarantine')
        # Verify raw SQL line and code, name, type and physical status.
        sqlrow = raw_sql_row(sql_lines, int(q.source_line_1based))
        rawcode = code(q.historical_okato_2009_raw)
        rawname = norm(q.name)
        sql_parsed_name = norm(sqlrow['name'])
        rawtype = classifier_type(sqlrow['status'])
        if code(sqlrow['code']) != rawcode:
            why.append('raw_2009_sql_code_differs_from_historical_named_object')
        if rawname != nk or sql_parsed_name != nk:
            why.append('raw_2009_sql_name_not_exact_source_name')
        if rawtype != typ or classifier_type(q.status) != typ:
            why.append('raw_2009_sql_or_2011_type_not_exact_stable_type')
        if str(sqlrow['is_settlement']).casefold() != 't' or str(q.is_settlement_raw).casefold() != 't':
            why.append('raw_classifier_or_geokladr_not_physical_settlement')
        if int(q.historical_key_region_name_type_count) != 1:
            why.append('historical_key_region_name_type_not_unique')
        c09, c11 = code(q.historical_okato_2009_raw), code(q.historical_okato_2011_raw)
        k3 = str(q.kod3_raw_text or '').strip()
        bridge = ((len(c09) == 11 and c11 == c09) or (len(c09) == 8 and c11 == c09 + '000' and k3 == '000'))
        if not bridge:
            why.append('raw_classifier_to_geokladr_code_bridge_not_exact_8_to_11_or_11_exact')
        dbf_needed.append((r, m, w, q, sqlrow, rawcode, why))
    raw_geo = raw_dbf_rows(RAW_DBF, pd.DataFrame([{
        'record_number_1based': q.record_number_1based,
        'record_byte_offset_0based': q.record_byte_offset_0based,
    } for _, _, _, q, _, _, _ in dbf_needed]).drop_duplicates('record_number_1based')) if dbf_needed else {}

    graph_ids = set(selected.source_record_id.astype(str))
    dsu = DSU(selected)
    for e in graph.itertuples(index=False):
        a, b = str(e.from_source_record_id), str(e.to_source_record_id)
        if a not in graph_ids or b not in graph_ids:
            raise ValueError('accepted graph endpoint missing from selected observations')
        dsu.union(a, b, check=True)
    baseline = coverage(selected, dsu, base_point_ids)
    expected_baseline = {
        2002: (105536, 116990219),
        2010: (105514, 114527509),
        2021: (105542, 115269151),
    }
    for year, (rows_expected, pop_expected) in expected_baseline.items():
        if (baseline[year]['joint_rows'], baseline[year]['joint_population']) != (rows_expected, pop_expected):
            raise ValueError(f'canonical baseline mismatch for {year}: {baseline[year]}')

    records = []
    point_records = []
    # Rival checks on the exact 2011 point and all direct modern point alternatives.
    for r, m, w, q, sqlrow, rawcode, why in dbf_needed:
        rid, mid, wid = str(r.source_record_id), str(m.source_record_id), str(w.source_record_id)
        georaw = raw_geo[int(q.record_number_1based)]
        if georaw['code'] != code(q.historical_okato_2011_raw) or georaw['deleted_marker'] != ' ':
            why.append('raw_2011_dbf_code_or_live_marker_mismatch')
        if norm(georaw['name_raw']) != norm(q.name_raw_2011) or classifier_type(georaw['type_raw']) != classifier_type(q.settlement_type_raw):
            why.append('raw_2011_dbf_name_or_type_mismatch')
        old_points = direct_2021.get(wid, [])
        if not old_points:
            why.append('no_direct_canonical_accepted_2021_point')
        hist_point = (float(georaw['lat_raw']), float(georaw['lon_raw']))
        distances = []
        point_witnesses = []
        for pt in old_points:
            dist = hav(hist_point, (pt['lat'], pt['lon']))
            same_origin = (str(pt['point_origin_sha256']) == dbf_hash and
                           str(q.record_number_1based) in str(pt['point_origin_locator']))
            point_witnesses.append({'historical_raw_point': hist_point, 'direct_current_point': pt,
                                    'distance_km': dist, 'same_raw_origin_excluded': same_origin})
            if not same_origin:
                distances.append(dist)
        if old_points and not distances:
            why.append('historical_and_modern_point_origins_not_independent')
        if distances and min(distances) > 5:
            why.append('all_historical_to_direct_modern_point_distances_over_5km')
        if distances and max(distances) > 5:
            why.append('alternative_point_witnesses_span_over_5km')
        # If a source native OKATO is present, it must agree with the literal
        # historical code or be preserved as a discrepancy for human review.
        source_code = code(r.okato)
        source_code_match = bool(source_code and source_code == rawcode)
        if source_code and not source_code_match:
            why.append('selected_old_source_okato_disagrees_with_historical_classifier_code')
        target_source_code = code(m.okato) if int(m.census_year) in (2002, 2010) else ''
        target_code_match = bool(target_source_code and target_source_code == rawcode)
        if target_source_code and not target_code_match:
            why.append('selected_target_source_okato_disagrees_with_historical_classifier_code')
        # Existing accepted coordinates on the old row are not silently
        # overwritten; a new raw point use is needed only if none exists.
        existing_old_points = point_coords.get(rid, [])
        old_point_distances = [hav(hist_point, p) for p in existing_old_points]
        if old_point_distances and max(old_point_distances) > 5:
            why.append('new_historical_point_conflicts_with_existing_accepted_target_point')
        # Include history warnings, but only verified physical event/collision
        # evidence above can block this exact corridor rule.
        legacy_warning = {label: e.get('legacy_identity_reasons') for label, e in (('from', er), ('to', em), ('point_witness', ew))}
        ga, gb = dsu.root(rid), dsu.root(mid)
        graph_status = 'already_connected' if ga == gb else ('same_year_component_collision' if dsu.mask[ga] & dsu.mask[gb] else 'safe_component_merge')
        if graph_status == 'same_year_component_collision':
            why.append('accepted_graph_merge_would_duplicate_a_census_year')
        edge = {
            'edge_id': 'SC-' + hashlib.sha256((rid + '|' + mid).encode()).hexdigest()[:18],
            'relation': 'same_place', 'from_source_record_id': rid, 'from_year': int(r.census_year),
            'to_source_record_id': mid, 'to_year': int(m.census_year),
            'point_witness_2021_source_record_id': wid,
            'from_source_publication_row_id': rid, 'to_source_publication_row_id': mid,
            'from_source_file': str(r.source_file), 'from_source_sha256': str(r.source_sha256),
            'from_source_locator': str(r.source_locator), 'from_source_native_id_opaque': str(r.source_native_id),
            'to_source_file': str(m.source_file), 'to_source_sha256': str(m.source_sha256),
            'to_source_locator': str(m.source_locator), 'to_source_native_id_opaque': str(m.source_native_id),
            'name_exact_norm': r.name_key, 'type_from_raw': str(r.settlement_type), 'type_to_raw': str(m.settlement_type),
            'region_from_raw': str(r.region_raw), 'region_to_raw': str(m.region_raw),
            'district_from_raw': '' if blank(r.district_raw) else str(r.district_raw),
            'district_to_raw': '' if blank(m.district_raw) else str(m.district_raw),
            'from_population': None if pd.isna(r.population) else int(r.population),
            'to_population': None if pd.isna(m.population) else int(m.population),
            'from_population_scope': str(r.population_scope), 'to_population_scope': str(m.population_scope),
            'from_okato_raw': '' if blank(r.okato) else str(r.okato), 'from_oktmo_raw': '' if blank(r.oktmo) else str(r.oktmo),
            'to_okato_raw': '' if blank(m.okato) else str(m.okato), 'to_oktmo_raw': '' if blank(m.oktmo) else str(m.oktmo),
            'whole_region_exact_name_unique_across_types_from': counts.get((int(r.census_year), r.name_key, r.region_key)) == 1,
            'whole_region_exact_name_unique_across_types_to': counts.get((2021, m.name_key, m.region_key)) == 1,
            'historical_classifier_sql_file': str(RAW_SQL), 'historical_classifier_sql_sha256': sql_hash,
            'historical_classifier_sql_line_1based': int(q.source_line_1based),
            'historical_classifier_okato2009_raw': rawcode, 'historical_classifier_name_raw': sqlrow['name_raw'],
            'historical_classifier_name_parsed': sqlrow['name'],
            'historical_named_object_name_raw_2009': q.name_raw_2009,
            'historical_named_object_name_parsed_2009': q.name,
            'historical_classifier_type_raw': sqlrow['status'], 'historical_classifier_is_settlement_raw': sqlrow['is_settlement'],
            'historical_geokladr_dbf_file': str(RAW_DBF), 'historical_geokladr_dbf_sha256': dbf_hash,
            'historical_geokladr_row_1based': int(q.record_number_1based), 'historical_geokladr_byte_offset_0based': int(q.record_byte_offset_0based),
            'historical_geokladr_okato2011_raw': georaw['code'], 'historical_geokladr_name_raw': georaw['name_raw'],
            'historical_geokladr_type_raw': georaw['type_raw'], 'historical_geokladr_region_raw': str(q.historical_point_modern_region),
            'historical_geokladr_ter_raw': georaw['ter'], 'historical_geokladr_kod1_raw': georaw['kod1'],
            'historical_geokladr_kod2_raw': georaw['kod2'], 'historical_geokladr_kod3_raw': georaw['kod3'],
            'historical_geokladr_raw_latitude': float(georaw['lat_raw']), 'historical_geokladr_raw_longitude': float(georaw['lon_raw']),
            'historical_name_type_region_match_count': int(q.historical_key_region_name_type_count),
            'classifier_to_geokladr_code_bridge': 'exact_11_digit' if len(code(q.historical_okato_2009_raw)) == 11 else 'literal_8_digit_plus_000',
            'source_old_okato_matches_historic_classifier': source_code_match,
            'source_target_okato_matches_historic_classifier': target_code_match,
            'source_evidence_from_json': evidence_raw[rid], 'source_evidence_to_json': evidence_raw[mid],
            'source_evidence_point_witness_2021_json': evidence_raw[wid],
            'legacy_identity_warnings_preserved_json': compact(legacy_warning),
            'direct_2021_point_witnesses_json': compact(point_witnesses),
            'max_direct_point_distance_km': max(distances) if distances else None,
            'accepted_graph_status_before_staging': graph_status,
            'point_source_date_claimed': False, 'census_date_measurement_claimed': False,
            'population_boundary_comparability_claimed': False, 'legal_or_rename_event_claimed': False,
            'hold_reasons_json': compact(sorted(set(why))),
            'candidate_status': 'candidate_for_independent_review' if not why else 'hold',
            'candidate_only': not bool(why), 'identity_admission': False,
        }
        records.append(edge)
        if not why:
            point_records.append({
                'point_use_id': 'SP-' + hashlib.sha256((rid + '|' + rawcode + '|' + str(q.record_number_1based)).encode()).hexdigest()[:18],
                'target_source_record_id': rid, 'target_year': int(r.census_year),
                'source_publication_row_id': rid, 'source_file': str(r.source_file),
                'source_sha256': str(r.source_sha256), 'source_locator': str(r.source_locator),
                'source_native_id_opaque': str(r.source_native_id), 'source_name_raw': str(r.source_name_raw),
                'source_type_raw': str(r.settlement_type), 'source_region_raw': str(r.region_raw),
                'latitude': float(georaw['lat_raw']), 'longitude': float(georaw['lon_raw']),
                'coordinate_source_file': str(RAW_DBF), 'coordinate_source_sha256': dbf_hash,
                'coordinate_source_locator': f"raw_dbf_record_number_1based={int(q.record_number_1based)};byte_offset_0based={int(q.record_byte_offset_0based)}",
                'coordinate_source_kind': 'GeoKLADR_2011_raw_live_physical_point',
                'historical_classifier_sql_file': str(RAW_SQL), 'historical_classifier_sql_sha256': sql_hash,
                'historical_classifier_sql_locator': f"COPY_text_line_1based={int(q.source_line_1based)}",
                'historical_classifier_okato2009_raw': rawcode, 'historical_classifier_name_raw': sqlrow['name_raw'],
                'historical_classifier_name_parsed': sqlrow['name'],
                'historical_named_object_name_raw_2009': q.name_raw_2009,
                'historical_named_object_name_parsed_2009': q.name,
                'historical_classifier_type_raw': sqlrow['status'],
                'coordinate_measurement_date_unknown': True, 'candidate_only': True,
                'coordinate_admission': False, 'source_population_changed': False,
                'identity_edge_id': edge['edge_id'], 'direct_2021_witness_distance_max_km': edge['max_direct_point_distance_km'],
            })

    # Rebuild the accepted graph and simulate only eligible pairs in descending
    # old-population order. Coverage is checked against canonical accepted
    # point statuses; optional imported booleans never filter the baseline.
    sim = DSU(selected)
    for e in graph.itertuples(index=False):
        sim.union(str(e.from_source_record_id), str(e.to_source_record_id))
    after_ids = set(base_point_ids)
    staged = sorted((x for x in records if x['candidate_only']),
                    key=lambda x: (-(x['from_population'] or 0), x['edge_id']))
    sim_accepted = []
    simulated_holds = []
    for e in staged:
        status = sim.union(e['from_source_record_id'], e['to_source_record_id'], check=True)
        e['simulation_union_result'] = status
        if status == 'merged':
            sim_accepted.append(e)
            after_ids.add(e['from_source_record_id'])
        elif status == 'already_connected':
            e['candidate_status'] = 'already_connected_point_use_candidate'
            e['identity_edge_candidate'] = False
            e['point_use_candidate'] = True
            after_ids.add(e['from_source_record_id'])
        else:
            e['candidate_status'] = 'hold_graph_year_collision_after_higher_priority_candidates'
            e['candidate_only'] = False
            e['hold_reasons_json'] = compact(sorted(set(js(e['hold_reasons_json']) + ['graph_year_collision_after_priority_simulation'])))
            simulated_holds.append(e)
    after = coverage(selected, sim, after_ids)

    # Disjoint dispositions by source row, plus overlapping reason marginals.
    reason_counts = Counter()
    for e in records:
        for reason in js(e['hold_reasons_json']):
            reason_counts[reason] += 1
    dispositions = pd.DataFrame(records)
    hold_df = pd.DataFrame([e for e in records if not e['candidate_only']])
    staged_edges = pd.DataFrame([e for e in records if e['candidate_only'] and e.get('identity_edge_candidate', True)])
    valid_point_edge_ids = {e['edge_id'] for e in records
                             if e.get('candidate_only') or e.get('candidate_status') == 'already_connected_point_use_candidate'}
    staged_points = pd.DataFrame([p for p in point_records if p['identity_edge_id'] in valid_point_edge_ids])
    out.mkdir(parents=True)
    dispositions.to_csv(out / 'all_candidate_dispositions.csv', index=False, encoding='utf-8')
    staged_edges.to_csv(out / 'staged_identity_edges.csv', index=False, encoding='utf-8')
    hold_df.to_csv(out / 'disjoint_holds.csv', index=False, encoding='utf-8')
    staged_points.to_csv(out / 'staged_point_uses.csv', index=False, encoding='utf-8')
    summary = {
        'status': 'candidate_only_no_admissions',
        'scope': 'Stable source type; residual 2002/2010 selected observation to unique exact-name/type/region 2021 source row.',
        'rule': 'Whole-region exact name uniqueness across locality types and source rows at both endpoint years; stable exact observed type; literal raw 2009 OKATO SQL line plus live physical typed 2011 GeoKLADR DBF row and exact historical name/type/region; independently admitted direct 2021 point within 5 km of every retained historic/modern alternative; existing event, quarantine, source-context and graph-year collision holds preserved.',
        'legacy_flags': 'Old legacy pointer, text-similarity, ordinal hypothesis, or stale-target warnings do not veto an independently evidenced new edge; flags remain verbatim in evidence JSON. Actual source same-year collision, verified successor event, explicit district contradiction, and hard point quarantine do block.',
        'sources': {'sha256': pins, 'accepted_status_sets_imported_from': str(HERE / 'build_long_table.py'),
                    'accepted_edge_rows': int(len(graph)), 'accepted_point_rows': int(accepted_point_rows),
                    'accepted_edge_statuses_seen': dict(graph.decision_status.astype(str).value_counts()),
                    'accepted_coordinate_statuses_seen': coordinate_status_counts},
        'exclusions': {'primary_v3_exact_pairs': len(load_excluded_pairs(PRIMARY_V3, 'primary')),
                       'type_change_exact_pairs': len(load_excluded_pairs(TYPE_EDGES, 'type')),
                       'type_change_all_disposition_pairs': len(load_excluded_pairs(TYPE_ALL, 'type')),
                       'hard_quarantine_ids': len(hard)},
        'inventory': {'residual_old_source_rows_considered': int(len(old)),
                      'provisional_stable_unique_exact_pairs': len(provisional),
                      'raw_historic_point_rows_resolved': len(dbf_needed),
                      'candidate_identity_edges_before_simulation': int(sum(e['candidate_only'] for e in records)),
                      'staged_identity_edges_after_simulation': int(len(staged_edges)),
                      'disjoint_holds': int(len(hold_df)),
                      'staged_point_uses': int(len(staged_points)),
                      'staged_endpoint_population_sum_diagnostic_only': int(sum((x['from_population'] or 0) + (x['to_population'] or 0) for x in records if x['candidate_only']))},
        'discovery_holds': dict(discovery_holds), 'overlapping_hold_reason_marginals': dict(reason_counts),
        'accepted_graph_simulation': {'baseline_joint_by_year': baseline, 'conditional_after_staged_edges_and_points_by_year': after,
                                      'joint_population_gain_by_year': {str(y): after[y]['joint_population'] - baseline[y]['joint_population'] for y in YEARS},
                                      'identity_edges_merged': len(sim_accepted), 'graph_and_populations_untouched': True},
        'interpretation_limits': ['Identity and point rows are staged only; no admission or applied graph change.',
                                  'Historic GeoKLADR point is from 2011, not a census-date measurement.',
                                  'Population boundaries and census-date population comparability are not asserted.',
                                  'OKATO is preserved as a raw historical classifier code, never synthesized as a modern source ID.',
                                  'Whole-region name uniqueness and independent spatial agreement are evidence gates; they do not establish legal boundaries.'],
        'outputs_sha256': {name: sha(out / name) for name in ('all_candidate_dispositions.csv', 'staged_identity_edges.csv', 'disjoint_holds.csv', 'staged_point_uses.csv')},
    }
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    print(json.dumps({'inventory': summary['inventory'], 'joint_population_gain_by_year': summary['accepted_graph_simulation']['joint_population_gain_by_year'],
                      'outputs_sha256': summary['outputs_sha256']}, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, default=OUT_DEFAULT)
    main(ap.parse_args().output)
