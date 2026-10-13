"""Bounded promotion of frozen own-NP points onto actual native State47 rows."""
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
E = ROOT / 'research_rebuild/evidence'
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import distance_km

spec = importlib.util.spec_from_file_location('finite_replay', E / 'working_full_chain_20261007/replay_additional_native_20261008.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def measure(state):
    result = {}
    for year, rows in state.obs.groupby('census_year'):
        pointed = rows.source_record_id.isin(state.point_rows)
        result[str(int(year))] = {
            'native_source_rows': len(rows), 'accepted_point_rows': int(pointed.sum()),
            'finite_population_with_accepted_point': int(rows.loc[pointed & np.isfinite(rows.population), 'population'].sum())}
    return result

def main():
    pins = {}
    def pin(path, expected=None):
        path = Path(path)
        actual = sha(path)
        if expected:
            assert actual == expected, str(path)
        pins[str(path)] = actual
        return actual

    folders = [
        ('moscow_three_direct_inclusion_events_application_20261008', 'accepted_former_locality_own_points.csv', 'application_receipt.json'),
        ('absorbed_large_direct_events_followup_20261008', 'candidate_former_locality_own_points.csv.gz', 'root_application_receipt.json'),
        ('absorbed_residual_direct_events_next_20261008', 'candidate_former_locality_own_points.csv.gz', 'root_application_receipt.json')]
    candidates = []
    for folder, filename, receipt_name in folders:
        path = E / folder / filename
        receipt_path = E / folder / receipt_name
        receipt = json.loads(receipt_path.read_text())
        pin(receipt_path)
        expected = receipt.get('output_pins', {}).get(filename)
        pin(path, expected)
        rows = pd.read_csv(path, keep_default_na=False).to_dict('records')
        for row in rows:
            assert row['own_locality_point'] is True and row['recipient_point_assigned_to_child'] is False
            row['candidate_source_file'] = str(path)
            candidates.append(row)

    base = E / 'remaining_moscow_complete_sourceyear_scopes_20261008'
    pgt_folder = base / 'urban_predecessor_formation_event_candidate'
    factory_folder = base / 'mosrentgen_formation_branch_followup_candidate'
    for folder, receipt_name in [(pgt_folder, 'candidate_event_receipt.json'), (factory_folder, 'candidate_branch_receipt.json')]:
        receipt_path = folder / receipt_name
        pin(receipt_path)
        receipt = json.loads(receipt_path.read_text())
        for filename, expected in receipt['outputs'].items():
            pin(folder / filename, expected)
        for filename, expected in receipt['source_manifest'].items():
            pin(filename, expected)
    pgts = pd.read_csv(pgt_folder / 'candidate_historical_own_PGT_observations.csv', keep_default_na=False)
    for row in pgts.to_dict('records'):
        assert not row['municipal_P625_projected_to_NP'] and not row['ownNP2021_count_created']
        candidates.append(dict(target_source_record_id=row['source_record_id'], latitude=row['latitude'], longitude=row['longitude'],
            point_origin_file=row['point_source_file'], point_origin_sha256=row['point_source_sha256'], point_origin_locator=row['point_source_locator'],
            point_origin_kind=row['point_origin_kind'], point_temporal_interpretation=row['historical_point_grade'],
            candidate_source_file=str(pgt_folder / 'candidate_historical_own_PGT_observations.csv')))
    factory = pd.read_csv(factory_folder / 'candidate_separate_own_properNP_physical_point.csv', keep_default_na=False).iloc[0].to_dict()
    assert not factory['municipal_P625_substituted'] and not factory['ownNP2021_count_created']
    candidates.append(dict(target_source_record_id=factory['source_record_id'], latitude=factory['latitude'], longitude=factory['longitude'],
        point_origin_file=factory['raw_source_file'], point_origin_sha256=factory['raw_source_sha256'],
        point_origin_locator=f"DBFrecord={factory['raw_record_number_1based']};byte={factory['raw_byte_offset_0based']}",
        point_origin_kind='cached_raw_geokladr2011_typed_ownphysical_factory_NP_with2009actualNPclassifier',
        point_temporal_interpretation=factory['point_grade'], candidate_source_file=str(factory_folder / 'candidate_separate_own_properNP_physical_point.csv')))
    # Reopen the physical DBF bytes, including record type and actual coordinates.
    raw_points = pd.read_csv(base / 'urban_point_resolution/raw2011_own_physical_PGT_points.csv', keep_default_na=False).to_dict('records')
    raw_points.append(dict(physical_source_file=factory['raw_source_file'], raw_record_byte_offset_0based=factory['raw_byte_offset_0based'],
        raw_record_length=395, raw_fields_json=factory['original_DBFFields_json']))
    import struct
    for row in raw_points:
        with Path(row['physical_source_file']).open('rb') as stream:
            header = stream.read(32)
            header_len = struct.unpack('<H', header[8:10])[0]
            fields = []
            while stream.tell() < header_len - 1:
                block = stream.read(32)
                if block[:1] == b'\r': break
                fields.append((block[:11].split(b'\x00')[0].decode('ascii'), block[16]))
            stream.seek(int(row['raw_record_byte_offset_0based']))
            record = stream.read(int(row['raw_record_length']))
        assert record[:1] == b' '
        offset = 1
        expected = json.loads(row['raw_fields_json'])
        for name, length in fields:
            actual = record[offset:offset+length].decode('cp1251')
            if name in ['LAT', 'LONG', 'SCOKATO', 'KLADRCODE', 'TYPE_NP']:
                assert actual.strip() == expected[name].strip(), (name, actual, expected[name])
            offset += length

    state = load(47)
    for path in state.inputs: pin(path)
    pin(E / 'working_full_chain_20261007/replay_additional_native_20261008.py')
    before, finite_before = measure(state), helper.finite(state)
    assert finite_before == {'histories': 138838, 'populations_by_year': {'2002': 126710197, '2010': 123868655, '2021': 124470630}}
    original_values = sha('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
    points, kept, witnesses = [], [], []
    ids = set()
    for row in candidates:
        sid = row['target_source_record_id']
        assert sid in state.by_id.index and sid not in ids, sid
        ids.add(sid)
        native = state.by_id.loc[sid]
        assert int(native.census_year) in [2002, 2010]
        assert math.isfinite(float(row['latitude'])) and math.isfinite(float(row['longitude']))
        pin(row['point_origin_file'], row['point_origin_sha256'])
        witnesses.append(dict(target_source_record_id=sid, census_year=int(native.census_year), settlement_name=native.settlement_name,
            settlement_type=native.settlement_type, population=native.population, population_value_quality=native.population_value_quality,
            source_file=native.source_file, source_path=native.source_path, source_sha256=native.source_sha256, source_locator=native.source_locator,
            candidate_source_file=row['candidate_source_file'], candidate_source_sha256=pins[row['candidate_source_file']],
            point_origin_file=row['point_origin_file'], point_origin_sha256=row['point_origin_sha256'], point_origin_locator=row['point_origin_locator']))
        if sid in state.point_rows:
            old = state.point_rows[sid]
            kept.append(dict(target_source_record_id=sid, existing_latitude=old['latitude'], existing_longitude=old['longitude'],
                alternative_latitude=row['latitude'], alternative_longitude=row['longitude'],
                distance_km=distance_km((old['latitude'], old['longitude']), (float(row['latitude']), float(row['longitude']))),
                existing_ledger=old['point_ledger_path'], candidate_source_file=row['candidate_source_file'], decision='retain_existing_admitted_point_no_override'))
            continue
        row.update(coordinate_admission_status='reviewed_extension_rule_accepted', coordinate_source_record_id=sid,
            source_sha256=native.source_sha256, source_locator=native.source_locator, own_locality_point=True,
            admission_allowed=True, admission_rule='Frozen independently identified own historical NP physical point; actual native ID; retrospective physical continuity only',
            censusday_point_measured_exactly=False, municipal_P625_projected_to_NP=False, child2021_population_assigned=False,
            boundary_comparability_asserted=False)
        points.append(row)
    edges, edge_checks = [], []
    for case, rows in pgts.groupby('case_id'):
        a, b = rows.sort_values('census_year').source_record_id.tolist()
        linked = state.uf.find(a) == state.uf.find(b)
        edge_checks.append(dict(case_id=case, from_source_record_id=a, to_source_record_id=b, already_same_component=linked))
        if not linked:
            assert state.years[state.uf.find(a)] == {2002} and state.years[state.uf.find(b)] == {2010}, case
            edges.append(dict(from_source_record_id=a, to_source_record_id=b, relation='same_place', decision_status='checked_rule_accepted',
                admission_rule='Native literal own PGT names/types; unique ownphysical Geo2011 point plus actual2009 settlement classifier; 2002 to2010 only',
                boundary_comparability_asserted=False, ownNP2021_count_created=False, source_context_witness_file=str(pgt_folder / 'cached_native_context_and_formation_proofs.csv')))
    pd.DataFrame(points).to_csv(OUT / 'accepted_point_use_delta.csv', index=False)
    pd.DataFrame(edges, columns=['from_source_record_id', 'to_source_record_id', 'relation', 'decision_status', 'admission_rule', 'boundary_comparability_asserted', 'ownNP2021_count_created', 'source_context_witness_file']).to_csv(OUT / 'accepted_identity_edge_delta.csv', index=False)
    pd.DataFrame(witnesses).to_csv(OUT / 'native_pin_witness.csv', index=False)
    pd.DataFrame(kept).to_csv(OUT / 'retained_existing_point_alternatives.csv', index=False)
    pd.DataFrame(edge_checks).to_csv(OUT / 'native_PGT_identity_checks.csv', index=False)
    state.add_deltas([OUT / 'accepted_identity_edge_delta.csv'], [OUT / 'accepted_point_use_delta.csv'])
    after, finite_after = measure(state), helper.finite(state)
    assert finite_after == finite_before
    assert len(state.obs) == sum(item['native_source_rows'] for item in before.values())
    assert original_values == sha('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
    outputs = {p.name: sha(p) for p in OUT.glob('*.csv')}
    receipt = dict(status='verified_bounded_actual_State47_native_ownpoint_application', baseline_stage=47,
        actual_native_source_rows=len(state.obs), actual_native_source_unique_ids=int(state.obs.source_record_id.nunique()),
        frozen_candidate_point_rows=len(candidates), accepted_new_point_uses=len(points), retained_existing_point_uses=len(kept),
        accepted_new_identity_edges=len(edges), before_by_year=before, after_by_year=after,
        net_by_year={year: {field: after[year][field]-before[year][field] for field in before[year]} for year in before},
        before_finite_native_all3_allpoints=finite_before, after_finite_native_all3_allpoints=finite_after, finite_native_all3_net_histories=0,
        population_values_quality_and_selected_source_bytes_unchanged=True, municipal_point_projection=False,
        child2021_counts_created=False, censusday_coordinate_accuracy_asserted=False, network_requests=0,
        frozen_source_receipts_and_candidates_unchanged=True, input_pins=pins, output_pins=outputs, code_sha256=sha(__file__))
    (OUT / 'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    verification = dict(status='passed', application_receipt_sha256=sha(OUT / 'application_receipt.json'),
        accepted_ledger_pins=outputs, input_pin_count=len(pins), DBF_actual_byte_checks=3,
        selected_native_UID_checks=len(witnesses), actual_State47_consumptions=1, finite_native_all3_gain=0)
    (OUT / 'verification_receipt.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: receipt[k] for k in ['status','accepted_new_point_uses','retained_existing_point_uses','accepted_new_identity_edges','net_by_year']}))

if __name__ == '__main__':
    main()
