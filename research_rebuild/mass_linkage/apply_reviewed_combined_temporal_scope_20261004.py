"""Apply reviewed primary/secondary date unions without guessing old census IDs.

The output is a separate spatial-temporal scope. Secondary values are never
nationally additive; existing selected primary IDs may be counted once. Nothing
in this application asserts comparable boundaries or exact secondary populations.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import duckdb

from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def qualifying_date(value, year):
    """Retain year precision; day precision must be the actual census date."""
    if value.get('calendarmodel') != 'http://www.wikidata.org/entity/Q1985727':
        return False
    if value.get('before', 0) or value.get('after', 0):
        return False
    precision = int(value['precision'])
    if precision == 9:
        return value['time'].startswith(f'+{year}-')
    census_dates = {2002: '+2002-10-09T00:00:00Z', 2010: '+2010-10-14T00:00:00Z'}
    return precision == 11 and value['time'] == census_dates[year]


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    z = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088*2*math.asin(min(1, math.sqrt(z)))


def run(config, eligible, eligible_sha256, review, review_sha256, output):
    config, eligible, review, output = map(Path, (config, eligible, review, output))
    assert not output.exists(), 'Choose a new immutable application directory'
    assert sha(eligible) == eligible_sha256 and sha(review) == review_sha256
    reviewed = json.loads(review.read_text())
    assert reviewed['status'] == 'independent_candidate_rule_review_complete_no_application'
    assert reviewed['outputs'][str(eligible)]['sha256'] == eligible_sha256
    config_bytes = config.read_bytes()
    cfg = json.loads(config_bytes)
    graph, points, selected = (Path(cfg[k]) for k in ('working_identity_graph', 'working_point_uses', 'working_population_layer'))
    assert sha(graph) == cfg['working_identity_graph_sha256']
    assert sha(points) == cfg['working_point_uses_sha256']
    rows = list(csv.DictReader(eligible.open()))
    assert rows and len({r['current_source_record_id'] for r in rows}) == len(rows)
    db = duckdb.connect(config={'threads': 1, 'memory_limit': '512MB'})
    db.read_parquet(str(selected)).create_view('sel')
    ids = {r['current_source_record_id'] for r in rows}
    for r in rows:
        for year in (2002, 2010):
            ids.update(m['source_record_id'] for m in json.loads(r[f'accepted_graph13_primary_{year}_members']))
    import pyarrow as pa
    db.register('wanted', pa.table({'sid': sorted(ids)}))
    facts = {r['source_record_id']: r for r in db.execute('select s.* from sel s join wanted w on s.source_record_id=w.sid').fetch_arrow_table().to_pylist()}
    uses = {r['target_source_record_id']: r for r in db.execute('select p.target_source_record_id,p.latitude,p.longitude,p.coordinate_admission_status from read_parquet(?) p join wanted w on p.target_source_record_id=w.sid', [str(points)]).fetch_arrow_table().to_pylist()}
    parent = {}
    def find(v):
        parent.setdefault(v, v)
        while v != parent[v]:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v
    for a, b in db.execute('select from_source_record_id,to_source_record_id from read_parquet(?)', [str(graph)]).fetchall():
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a
    pins = {str(p): sha(p) for p in (config, eligible, review, graph, points, selected, graph.parent/'receipt.json')}
    entities_cache = {}
    trajectories, credit, holds = [], {}, []
    for row in rows:
        assert row['review_status'] == 'eligible_reviewed_temporal_candidate'
        sid, qid = row['current_source_record_id'], row['current_QID']
        current = facts[sid]
        assert int(current['census_year']) == 2021 and current['population_scope'] == 'settlement' and current['is_additive_settlement_record']
        assert int(current['population']) == int(float(row['current_population_2021_primary_once']))
        point = (float(row['current_point_latitude']), float(row['current_point_longitude']))
        assert -90 <= point[0] <= 90 and -180 <= point[1] <= 180
        origin = Path(row['current_point_origin_file'])
        if str(origin) not in pins:
            pins[str(origin)] = sha(origin)
        assert pins[str(origin)] == row['current_point_origin_sha256']
        if sid in uses:
            assert uses[sid]['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES
            assert (uses[sid]['latitude'], uses[sid]['longitude']) == point
        dates, observations = {2021}, []
        source_claims = []
        for year in (2002, 2010):
            members = json.loads(row[f'accepted_graph13_primary_{year}_members'])
            assert len(members) <= 1
            for member in members:
                oldid = member['source_record_id']; old = facts[oldid]
                assert find(oldid) == find(sid) and int(old['census_year']) == year
                # Preserve already accepted primary membership despite optional
                # null scope or a more specific literal census-population scope.
                assert old['is_additive_settlement_record'] and old['population_scope'] in (None, 'settlement', 'permanent_residents_at_2010_census', 'settlement_population_2010_census_date')
                assert int(old['population']) == int(float(member['population']))
                dates.add(year)
                observations.append({'year': year, 'source_class': 'existing_selected_primary_census_row', 'source_record_id': oldid, 'population': int(old['population']), 'population_quality': old['population_value_quality']})
                use = uses.get(oldid)
                if use and use['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES and distance((use['latitude'], use['longitude']), point) <= 5:
                    credit[oldid] = {'source_record_id': oldid, 'year': year, 'population': int(old['population']), 'coordinate_latitude': use['latitude'], 'coordinate_longitude': use['longitude'], 'coordinate_status': use['coordinate_admission_status'], 'current_source_record_id': sid}
                else:
                    holds.append({'source_record_id': oldid, 'current_source_record_id': sid, 'reason': 'old_point_missing_or_over_5km; identity_and_current_temporal_path_retained'})
            claim = json.loads(row[f'secondary_claim_{year}']) if row[f'secondary_claim_{year}'] else None
            if not claim:
                continue
            replay = json.loads(row['independent_secondary_claim_replay_json'])[str(year)]
            if not replay['claim_use_allowed']:
                assert members and replay['excluded_as_optional_unreferenced_secondary']
                continue
            assert all(replay['checks'].values())
            path = Path(claim['entity_file'])
            if str(path) not in entities_cache:
                pins[str(path)] = sha(path)
                entities_cache[str(path)] = json.loads(path.read_text())['entities']
            assert pins[str(path)] == claim['entity_file_sha256']
            entity = entities_cache[str(path)][qid]
            raw = [c for c in entity.get('claims', {}).get('P1082', []) if c['id'] == claim['statement_GUID']]
            assert len(raw) == 1 and raw[0] == json.loads(claim['statement_json'])
            statement = raw[0]; quantity = statement['mainsnak']['datavalue']['value']
            assert statement['rank'] != 'deprecated' and quantity['unit'] == '1'
            assert float(quantity['amount']).is_integer() and float(quantity['amount']) >= 0
            ts = [x['datavalue']['value'] for x in statement.get('qualifiers', {}).get('P585', [])]
            assert len(ts) == 1 and qualifying_date(ts[0], year)
            assert statement.get('references'), 'Only explicitly reviewed source-backed claims'
            dates.add(year); source_claims.append((entity, claim))
            observations.append({'year': year, 'source_class': 'secondary_dated_wikidata_P1082', 'source_record_id': None, 'population': int(float(quantity['amount'])), 'national_additive': False, 'population_quality': 'secondary_census_citation_primary_value_not_independently_verified', 'claim': claim, 'date_precision': ts[0]['precision']})
        assert dates == {2002, 2010, 2021} and source_claims
        # Literal native current binding is re-read from the raw publisher row.
        native = row['current_native_OKTMO']
        entity = source_claims[0][0]
        codes = [c['mainsnak']['datavalue']['value'] for c in entity['claims'].get('P764', []) if c.get('rank') != 'deprecated' and c['mainsnak'].get('snaktype') == 'value']
        assert codes == [native], 'No numeric padding or fuzzy native-code binding'
        coords = [c['mainsnak']['datavalue']['value'] for c in entity['claims'].get('P625', []) if c.get('rank') != 'deprecated' and c['mainsnak'].get('snaktype') == 'value']
        earth = [c for c in coords if c['globe'] == 'http://www.wikidata.org/entity/Q2' and -90 <= c['latitude'] <= 90 and -180 <= c['longitude'] <= 180]
        distances = [distance(point, (c['latitude'], c['longitude'])) for c in earth]
        assert distances and min(distances) <= 5
        # The coordinate remains the independently accepted publisher point.
        # Multiple WD coordinates are context; no nearest P625 is selected or
        # promoted to a uniquely verified Wikidata coordinate assertion.
        assert sid in uses, 'This application preserves accepted current points'
        credit[sid] = {'source_record_id': sid, 'year': 2021, 'population': int(current['population']), 'coordinate_latitude': point[0], 'coordinate_longitude': point[1], 'coordinate_status': 'accepted_reviewed_native_binding_scoped_point', 'current_source_record_id': sid}
        trajectories.append({'current_source_record_id': sid, 'subject_qid': qid, 'native_current_oktmo': native, 'current_population': int(current['population']), 'current_point': point, 'current_point_origin': {'file': str(origin), 'sha256': pins[str(origin)], 'locator': row['current_point_origin_locator']}, 'wikidata_P625_context': {'active_valid_earth_points': earth, 'distances_to_accepted_publisher_point_km': distances, 'one_P625_selected': False}, 'observations': observations, 'decision_status': 'accepted_scoped_primary_secondary_date_union', 'ordinary_primary_NP3': False, 'boundary_comparability_asserted': False, 'modern_boundary_harmonized': False, 'historical_point_measurement_asserted': False})
    # Validate publisher native-code and point values for every current target.
    raw_path = {r['current_point_origin_file'] for r in rows}
    assert len(raw_path) == 1
    raw_data = db.execute('select file_row_number raw_index,oktmo,latitude_dadata,longitude_dadata from read_parquet(?,file_row_number=true)', [next(iter(raw_path))]).fetchall()
    raw_map = {int(r[0]): r[1:] for r in raw_data}
    for row in rows:
        s = facts[row['current_source_record_id']]
        native, lat, lon = raw_map[int(float(s['source_row']))-1]
        assert str(native) == row['current_native_OKTMO']
        assert (lat, lon) == (float(row['current_point_latitude']), float(row['current_point_longitude']))
    output.mkdir(parents=True)
    (output/'frozen_application_config.json').write_bytes(config_bytes)
    (output/'executed_application_script.py').write_bytes(Path(__file__).read_bytes())
    pins.pop(str(config))
    pins[str(output/'frozen_application_config.json')] = hashlib.sha256(config_bytes).hexdigest()
    files = {'accepted_scoped_trajectories.json': trajectories, 'accepted_existing_primary_credit_references.json': list(credit.values()), 'held_old_point_credit.json': holds}
    for name, data in files.items():
        (output/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    names = list(files) + ['frozen_application_config.json', 'executed_application_script.py']
    receipt = {'status': 'applied_reviewed_combined_primary_secondary_temporal_scope', 'trajectories': len(trajectories), 'credit_references': len(credit), 'held_old_point_references': len(holds), 'input_pins': pins, 'outputs': {name: sha(output/name) for name in names}, 'script_sha256': sha(__file__), 'population_values_modified': False, 'old_secondary_population_nationally_added': 0, 'ordinary_primary_NP3_modified': False, 'boundary_comparability': 'unknown', 'coverage_measured': False}
    (output/'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('config', 'eligible', 'eligible-sha256', 'review', 'review-sha256', 'output'):
        p.add_argument('--'+key, required=True)
    print(json.dumps(run(**vars(p.parse_args())), ensure_ascii=False))
